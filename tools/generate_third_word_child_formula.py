#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_covering_cnf import read_dimacs
from matching_constraints import append_matching_constraints
from run_two_word_portfolio import case_units, unit_digest
from third_word_symmetry import third_orbits


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="ascii"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repository_root(frontier_manifest: Path) -> Path:
    return frontier_manifest.resolve().parents[1]


def ensure_repository_path(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise SystemExit(f"path is outside the repository: {path}")
    return resolved


def resolve_repository_path(value: object, root: Path) -> Path:
    path = Path(str(value))
    if not path.is_absolute():
        path = root / path
    return ensure_repository_path(path, root)


def display_path(path: Path, root: Path) -> str:
    return str(ensure_repository_path(path, root).relative_to(root))


def dimacs_text(
    variable_count: int,
    clauses: list[tuple[int, ...]],
) -> str:
    lines = [f"p cnf {variable_count} {len(clauses)}"]
    lines.extend(
        " ".join(str(literal) for literal in clause) + " 0"
        for clause in clauses
    )
    return "\n".join(lines) + "\n"


def find_parent_and_child(
    frontier: dict[str, object],
    child_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    for parent in frontier["parents"]:
        for child in parent["children"]:
            if child["child_id"] == child_id:
                return parent, child
    raise SystemExit(f"unknown child id: {child_id}")


def build_child_formula(
    base_formula: Path,
    parent_case: dict[str, object],
    third_parent: dict[str, object],
    frontier_parent: dict[str, object],
    child: dict[str, object],
    *,
    length: int,
) -> tuple[int, list[tuple[int, ...]], dict[str, object]]:
    if frontier_parent["status"] != "active":
        raise RuntimeError("child parent is already closed")
    if child["branch_status"] != "live":
        raise RuntimeError("child is excluded by a retained constraint")
    if child["parent_status"] != "active":
        raise RuntimeError("child parent status is inconsistent")

    variables, base_clauses, base_sha256 = read_dimacs(base_formula)
    expected_base_sha256 = frontier_parent["constraint_profile"][
        "minimum_distance"
    ]["formula"]["sha256"]
    if base_sha256 != expected_base_sha256:
        raise RuntimeError("minimum-distance base formula hash mismatch")

    units = case_units(parent_case, length)
    if len(units) != int(parent_case["unit_count"]):
        raise RuntimeError("parent unit count does not match its manifest")
    if unit_digest(units) != parent_case["unit_sha256"]:
        raise RuntimeError("parent unit hash does not match its manifest")

    reconstructed_orbits = third_orbits(parent_case, length=length)
    orbit_records = third_parent["orbits"]
    if len(reconstructed_orbits) != len(orbit_records):
        raise RuntimeError("third-orbit count does not match its manifest")

    target_index = int(child["parent_orbit_index"])
    if target_index < 0 or target_index >= len(reconstructed_orbits):
        raise RuntimeError("child orbit index is outside the parent")
    earlier_words: list[int] = []
    target_words: list[int] | None = None
    for orbit_index, ((descriptor, words), orbit) in enumerate(
        zip(reconstructed_orbits, orbit_records)
    ):
        if list(descriptor) != orbit["descriptor"]:
            raise RuntimeError("third-orbit descriptor mismatch")
        if len(words) != int(orbit["orbit_size"]):
            raise RuntimeError("third-orbit size mismatch")
        if len(earlier_words) != int(orbit["earlier_word_count"]):
            raise RuntimeError("third-orbit prefix mismatch")
        canonical = int(orbit["canonical_word"])
        if canonical not in words:
            raise RuntimeError("third-orbit representative mismatch")
        if orbit_index == target_index:
            target_words = words
            break
        earlier_words.extend(words)
    if target_words is None:
        raise RuntimeError("child orbit was not reconstructed")

    target_orbit = orbit_records[target_index]
    canonical_word = int(target_orbit["canonical_word"])
    if child["canonical_word"] != canonical_word:
        raise RuntimeError("child canonical word does not match")
    if child["descriptor"] != target_orbit["descriptor"]:
        raise RuntimeError("child descriptor does not match")
    if child["orbit_size"] != len(target_words):
        raise RuntimeError("child orbit size does not match")
    if child["earlier_word_count"] != len(earlier_words):
        raise RuntimeError("child prefix count does not match")

    earlier_units = [-(word + 1) for word in earlier_words]
    clauses = list(base_clauses)
    clauses.extend((literal,) for literal in units)
    clauses.append((canonical_word + 1,))
    clauses.extend((literal,) for literal in earlier_units)

    matching = bool(frontier_parent["matching_eligible"])
    final_variables = variables
    matching_metadata = {
        "matching_allowed_vertices": 0,
        "matching_gated_vertices": 0,
        "matching_neighbor_incidences": 0,
        "matching_auxiliary_variables": 0,
        "matching_clauses": 0,
    }
    if matching:
        final_variables, matching_metadata = append_matching_constraints(
            final_variables,
            clauses,
            parent_case,
            length=length,
        )

    metadata = {
        "schema_version": 1,
        "child_id": child["child_id"],
        "live_child_index": child["live_child_index"],
        "parent_case_id": parent_case["case_id"],
        "parent_orbit_index": target_index,
        "minimum_distance": parent_case["minimum_weight"],
        "base_formula_sha256": base_sha256,
        "base_variables": variables,
        "base_clauses": len(base_clauses),
        "parent_unit_count": len(units),
        "parent_unit_sha256": unit_digest(units),
        "selected_word": canonical_word,
        "selected_word_literal": canonical_word + 1,
        "earlier_word_count": len(earlier_words),
        "earlier_word_unit_sha256": unit_digest(earlier_units),
        "enforce_minimum_distance_matching": matching,
        "variables": final_variables,
        "clauses": len(clauses),
        **matching_metadata,
    }
    return final_variables, clauses, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("frontier_manifest", type=Path)
    parser.add_argument("child_id")
    parser.add_argument("formula_output", type=Path)
    parser.add_argument("metadata_output", type=Path)
    args = parser.parse_args()

    root = repository_root(args.frontier_manifest)
    source_paths = tuple(
        ensure_repository_path(path, root)
        for path in (
            args.parent_manifest,
            args.third_word_manifest,
            args.frontier_manifest,
        )
    )
    formula_output = ensure_repository_path(args.formula_output, root)
    metadata_output = ensure_repository_path(args.metadata_output, root)
    if formula_output == metadata_output:
        raise SystemExit("formula and metadata outputs must be distinct")
    for output in (formula_output, metadata_output):
        if output in source_paths:
            raise SystemExit("an output path aliases a source manifest")

    parent_manifest = load_json(args.parent_manifest)
    third_manifest = load_json(args.third_word_manifest)
    frontier = load_json(args.frontier_manifest)
    if file_sha256(args.parent_manifest) != frontier["sources"][
        "stage1_parent_manifest"
    ]["sha256"]:
        raise SystemExit("parent manifest hash does not match the frontier")
    if file_sha256(args.third_word_manifest) != frontier["sources"][
        "third_word_manifest"
    ]["sha256"]:
        raise SystemExit("third-word manifest hash does not match the frontier")

    frontier_parent, child = find_parent_and_child(
        frontier,
        args.child_id,
    )
    parent_case_id = str(frontier_parent["parent_case_id"])
    parent_case = next(
        (
            case
            for case in parent_manifest["cases"]
            if case["case_id"] == parent_case_id
        ),
        None,
    )
    third_parent = next(
        (
            parent
            for parent in third_manifest["parents"]
            if parent["parent_case_id"] == parent_case_id
        ),
        None,
    )
    if parent_case is None or third_parent is None:
        raise SystemExit(f"missing source parent: {parent_case_id}")

    base_formula = resolve_repository_path(
        frontier_parent["constraint_profile"]["minimum_distance"][
            "formula"
        ]["path"],
        root,
    )
    if not base_formula.is_file():
        raise SystemExit(
            "minimum-distance formula is missing; run "
            "`make min-distance-branches`"
        )
    if base_formula in (formula_output, metadata_output):
        raise SystemExit("an output path aliases the base formula")
    variables, clauses, metadata = build_child_formula(
        base_formula,
        parent_case,
        third_parent,
        frontier_parent,
        child,
        length=int(parent_manifest["length"]),
    )
    text = dimacs_text(variables, clauses)
    formula_output.parent.mkdir(parents=True, exist_ok=True)
    formula_output.write_text(text, encoding="ascii")
    metadata.update(
        {
            "base_formula": display_path(base_formula, root),
            "formula": display_path(formula_output, root),
            "formula_sha256": hashlib.sha256(
                text.encode("ascii")
            ).hexdigest(),
            "frontier_manifest": display_path(
                args.frontier_manifest,
                root,
            ),
            "frontier_manifest_sha256": file_sha256(
                args.frontier_manifest
            ),
            "parent_manifest": display_path(
                args.parent_manifest,
                root,
            ),
            "parent_manifest_sha256": file_sha256(
                args.parent_manifest
            ),
            "third_word_manifest": display_path(
                args.third_word_manifest,
                root,
            ),
            "third_word_manifest_sha256": file_sha256(
                args.third_word_manifest
            ),
        }
    )
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    metadata_output.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
