#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_covering_cnf import read_dimacs
from audit_third_word_formula import append_matching, parent_units


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="ascii"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repository_root(metadata_path: Path) -> Path:
    resolved = metadata_path.resolve()
    for candidate in (resolved.parent, *resolved.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "research").is_dir()
        ):
            return candidate
    raise SystemExit("could not locate the repository root")


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


def hamming_weight(word: int) -> int:
    return bin(word).count("1")


def coordinate_cells(
    first: int,
    second: int,
    length: int,
) -> tuple[int, int, int, int]:
    ambient = (1 << length) - 1
    return (
        first & second,
        first & (ambient ^ second),
        second & (ambient ^ first),
        ambient ^ (first | second),
    )


def is_candidate(
    word: int,
    parent: dict[str, object],
    length: int,
) -> bool:
    first = int(parent["first_word"])
    second = int(parent["second_word"])
    threshold = parent["second_descriptor"]
    return (
        0 <= word < 1 << length
        and word not in {0, first, second}
        and hamming_weight(word) >= int(parent["minimum_weight"])
        and (
            hamming_weight(word),
            hamming_weight(word & first),
        )
        >= (
            int(threshold["weight"]),
            int(threshold["intersection"]),
        )
    )


def independent_orbits(
    parent: dict[str, object],
    length: int,
) -> list[tuple[list[int], list[int]]]:
    first = int(parent["first_word"])
    second = int(parent["second_word"])
    cells = coordinate_cells(first, second, length)
    grouped: dict[tuple[int, int, int, int], list[int]] = {}
    for word in range(1 << length):
        if not is_candidate(word, parent, length):
            continue
        descriptor = tuple(
            hamming_weight(word & cell)
            for cell in cells
        )
        grouped.setdefault(descriptor, []).append(word)
    return [
        (list(descriptor), grouped[descriptor])
        for descriptor in sorted(grouped)
    ]


def unit_digest(units: list[int]) -> str:
    text = "".join(f"{literal}\n" for literal in units)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def independently_matching_eligible(parent: dict[str, object]) -> bool:
    minimum_distance = int(parent["minimum_weight"])
    second_weight = int(parent["second_descriptor"]["weight"])
    intersection = int(parent["second_descriptor"]["intersection"])
    first_second_distance = (
        minimum_distance + second_weight - 2 * intersection
    )
    return (
        second_weight != minimum_distance
        and first_second_distance != minimum_distance
    )


def find_parent_and_child(
    frontier: dict[str, object],
    child_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    for parent in frontier["parents"]:
        for child in parent["children"]:
            if child["child_id"] == child_id:
                return parent, child
    raise SystemExit(f"unknown child id: {child_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("formula", type=Path)
    parser.add_argument("metadata", type=Path)
    args = parser.parse_args()

    root = repository_root(args.metadata)
    ensure_repository_path(args.formula, root)
    ensure_repository_path(args.metadata, root)
    metadata = load_json(args.metadata)
    if metadata["schema_version"] != 1:
        raise SystemExit("unsupported child-formula metadata schema")

    frontier_path = resolve_repository_path(
        metadata["frontier_manifest"],
        root,
    )
    parent_manifest_path = resolve_repository_path(
        metadata["parent_manifest"],
        root,
    )
    third_manifest_path = resolve_repository_path(
        metadata["third_word_manifest"],
        root,
    )
    base_formula_path = resolve_repository_path(
        metadata["base_formula"],
        root,
    )
    for path, expected, label in (
        (
            frontier_path,
            metadata["frontier_manifest_sha256"],
            "frontier manifest",
        ),
        (
            parent_manifest_path,
            metadata["parent_manifest_sha256"],
            "parent manifest",
        ),
        (
            third_manifest_path,
            metadata["third_word_manifest_sha256"],
            "third-word manifest",
        ),
        (
            base_formula_path,
            metadata["base_formula_sha256"],
            "base formula",
        ),
    ):
        if not path.is_file():
            raise SystemExit(f"{label} is missing")
        if file_sha256(path) != expected:
            raise SystemExit(f"{label} hash mismatch")

    frontier = load_json(frontier_path)
    parent_manifest = load_json(parent_manifest_path)
    third_manifest = load_json(third_manifest_path)
    if metadata["parent_manifest_sha256"] != frontier["sources"][
        "stage1_parent_manifest"
    ]["sha256"]:
        raise SystemExit("parent source does not match the frontier")
    if metadata["third_word_manifest_sha256"] != frontier["sources"][
        "third_word_manifest"
    ]["sha256"]:
        raise SystemExit("third-word source does not match the frontier")

    frontier_parent, child = find_parent_and_child(
        frontier,
        str(metadata["child_id"]),
    )
    if frontier_parent["status"] != "active":
        raise SystemExit("child parent is already closed")
    if child["branch_status"] != "live":
        raise SystemExit("child is excluded by a retained constraint")
    case_id = str(frontier_parent["parent_case_id"])
    parent = next(
        (
            case
            for case in parent_manifest["cases"]
            if case["case_id"] == case_id
        ),
        None,
    )
    third_parent = next(
        (
            record
            for record in third_manifest["parents"]
            if record["parent_case_id"] == case_id
        ),
        None,
    )
    if parent is None or third_parent is None:
        raise SystemExit(f"missing source parent: {case_id}")

    required_base = frontier_parent["constraint_profile"][
        "minimum_distance"
    ]["formula"]
    required_base_path = resolve_repository_path(
        required_base["path"],
        root,
    )
    if base_formula_path != required_base_path:
        raise SystemExit("base formula is not the frontier formula")
    if metadata["base_formula_sha256"] != required_base["sha256"]:
        raise SystemExit("base formula hash is not bound to the frontier")

    length = int(parent_manifest["length"])
    orbits = independent_orbits(parent, length)
    orbit_index = int(child["parent_orbit_index"])
    if orbit_index < 0 or orbit_index >= len(orbits):
        raise SystemExit("child orbit index is outside the parent")
    earlier_words = [
        word
        for _, words in orbits[:orbit_index]
        for word in words
    ]
    descriptor, target_words = orbits[orbit_index]
    canonical_word = min(target_words)
    if child["descriptor"] != descriptor:
        raise SystemExit("child descriptor is incorrect")
    if child["canonical_word"] != canonical_word:
        raise SystemExit("child canonical word is incorrect")
    if child["orbit_size"] != len(target_words):
        raise SystemExit("child orbit size is incorrect")
    if child["earlier_word_count"] != len(earlier_words):
        raise SystemExit("child prefix count is incorrect")

    base_variables, base_clauses, base_digest = read_dimacs(
        base_formula_path
    )
    variables, clauses, formula_digest = read_dimacs(args.formula)
    if file_sha256(args.formula) != formula_digest:
        raise SystemExit("formula byte hash mismatch")
    if metadata["formula"] != display_path(args.formula, root):
        raise SystemExit("formula path metadata is incorrect")
    if metadata["formula_sha256"] != formula_digest:
        raise SystemExit("formula hash metadata is incorrect")

    units = parent_units(parent, length)
    earlier_units = [-(word + 1) for word in earlier_words]
    expected = list(base_clauses)
    expected.extend((literal,) for literal in units)
    expected.append((canonical_word + 1,))
    expected.extend((literal,) for literal in earlier_units)

    matching = independently_matching_eligible(parent)
    if bool(frontier_parent["matching_eligible"]) != matching:
        raise SystemExit("frontier matching eligibility is incorrect")
    expected_variables = base_variables
    matching_metadata = {
        "matching_allowed_vertices": 0,
        "matching_gated_vertices": 0,
        "matching_neighbor_incidences": 0,
        "matching_auxiliary_variables": 0,
        "matching_clauses": 0,
    }
    if matching:
        expected_variables, matching_metadata = append_matching(
            expected,
            variable_count=expected_variables,
            case=parent,
            length=length,
        )
    if clauses != expected:
        raise SystemExit("child formula clauses are incorrect")
    if variables != expected_variables:
        raise SystemExit("child formula variable count is incorrect")

    expected_metadata = {
        "base_clauses": len(base_clauses),
        "base_formula": display_path(base_formula_path, root),
        "base_formula_sha256": base_digest,
        "base_variables": base_variables,
        "child_id": child["child_id"],
        "clauses": len(expected),
        "earlier_word_count": len(earlier_words),
        "earlier_word_unit_sha256": unit_digest(earlier_units),
        "enforce_minimum_distance_matching": matching,
        "frontier_manifest": display_path(frontier_path, root),
        "frontier_manifest_sha256": file_sha256(frontier_path),
        "live_child_index": child["live_child_index"],
        "minimum_distance": parent["minimum_weight"],
        "parent_case_id": case_id,
        "parent_manifest": display_path(parent_manifest_path, root),
        "parent_manifest_sha256": file_sha256(parent_manifest_path),
        "parent_orbit_index": orbit_index,
        "parent_unit_count": len(units),
        "parent_unit_sha256": unit_digest(units),
        "schema_version": 1,
        "selected_word": canonical_word,
        "selected_word_literal": canonical_word + 1,
        "third_word_manifest": display_path(third_manifest_path, root),
        "third_word_manifest_sha256": file_sha256(third_manifest_path),
        "variables": expected_variables,
        **matching_metadata,
    }
    for key, value in expected_metadata.items():
        if metadata.get(key) != value:
            raise SystemExit(f"metadata {key} is incorrect")

    print(
        json.dumps(
            {
                "child_id": child["child_id"],
                "clauses": len(expected),
                "formula_sha256": formula_digest,
                "matching": matching,
                "valid": True,
                "variables": expected_variables,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
