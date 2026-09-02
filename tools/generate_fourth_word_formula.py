#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from fourth_word_symmetry import fourth_orbits, orbit_manifest_digest
from generate_third_word_child_formula import (
    build_child_formula,
    dimacs_text,
    display_path,
    ensure_repository_path,
    file_sha256,
    find_parent_and_child,
    resolve_repository_path,
)
from run_two_word_portfolio import unit_digest
from third_word_symmetry import weight


def load_snapshot(
    path: Path,
) -> tuple[dict[str, object], str]:
    payload = path.read_bytes()
    return (
        json.loads(payload.decode("ascii")),
        hashlib.sha256(payload).hexdigest(),
    )


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def branch_digest(branch: dict[str, object]) -> str:
    identity = {
        key: value
        for key, value in branch.items()
        if key != "branch_sha256"
    }
    payload = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def aliases_existing_file(
    path: Path,
    sources: set[Path],
) -> bool:
    return path.exists() and any(
        os.path.samefile(path, source)
        for source in sources
    )


def repository_python_sources(root: Path) -> set[Path]:
    return {
        path.resolve()
        for directory in (root / "src", root / "tools")
        for path in directory.rglob("*.py")
    }


def reconstruct_branches(
    parent_case: dict[str, object],
    child: dict[str, object],
    grouped: list[tuple[tuple[int, ...], list[int]]],
) -> list[dict[str, object]]:
    branches = []
    earlier_word_count = 0
    for orbit_index, (descriptor, words) in enumerate(grouped):
        canonical_word = min(words)
        branch = {
            "branch_id": (
                f"{child['child_id']}::fourth-{orbit_index:03d}"
            ),
            "parent_child_id": child["child_id"],
            "fourth_orbit_index": orbit_index,
            "descriptor": list(descriptor),
            "canonical_word": canonical_word,
            "orbit_size": len(words),
            "earlier_word_count": earlier_word_count,
            "constraint_units": {
                "selected_word_literal": canonical_word + 1,
                "excluded_earlier_word_count": earlier_word_count,
            },
            "fixed_word_distances": {
                "zero": weight(canonical_word),
                "first": weight(
                    canonical_word ^ int(parent_case["first_word"])
                ),
                "second": weight(
                    canonical_word ^ int(parent_case["second_word"])
                ),
                "third": weight(
                    canonical_word ^ int(child["canonical_word"])
                ),
            },
        }
        branch["branch_sha256"] = branch_digest(branch)
        branches.append(branch)
        earlier_word_count += len(words)
    return branches


def find_branch(
    fourth_frontier: dict[str, object],
    branch_id: str,
) -> tuple[
    dict[str, object],
    dict[str, object],
]:
    matches = [
        (child, branch)
        for child in fourth_frontier["children"]
        for branch in child["branches"]
        if branch["branch_id"] == branch_id
    ]
    if len(matches) != 1:
        raise SystemExit(f"unknown or duplicate branch id: {branch_id}")
    return matches[0]


def build_fourth_formula(
    base_formula: Path,
    parent_case: dict[str, object],
    third_parent: dict[str, object],
    frontier_parent: dict[str, object],
    child: dict[str, object],
    fourth_child: dict[str, object],
    branch: dict[str, object],
    *,
    length: int,
) -> tuple[int, list[tuple[int, ...]], dict[str, object]]:
    child_variables, child_clauses, child_metadata = (
        build_child_formula(
            base_formula,
            parent_case,
            third_parent,
            frontier_parent,
            child,
            length=length,
        )
    )
    if fourth_child["parent_child_id"] != child["child_id"]:
        raise RuntimeError("fourth-word child identity mismatch")
    matching = bool(frontier_parent["matching_eligible"])
    grouped, classification = fourth_orbits(
        parent_case,
        child,
        length=length,
        matching=matching,
    )
    expected_branches = reconstruct_branches(
        parent_case,
        child,
        grouped,
    )
    if fourth_child["branches"] != expected_branches:
        raise RuntimeError("fourth-word branch manifest mismatch")
    if fourth_child["classification"] != classification:
        raise RuntimeError("fourth-word classification mismatch")
    if int(fourth_child["fourth_orbit_count"]) != len(grouped):
        raise RuntimeError("fourth-word orbit count mismatch")
    if fourth_child["fourth_orbit_sha256"] != orbit_manifest_digest(
        expected_branches
    ):
        raise RuntimeError("fourth-word orbit digest mismatch")
    orbit_index = int(branch["fourth_orbit_index"])
    if orbit_index < 0 or orbit_index >= len(grouped):
        raise RuntimeError("fourth-word orbit index is outside the child")
    if branch != expected_branches[orbit_index]:
        raise RuntimeError("fourth-word branch identity mismatch")
    descriptor, words = grouped[orbit_index]
    earlier_words = [
        word
        for _, orbit_words in grouped[:orbit_index]
        for word in orbit_words
    ]
    canonical_word = min(words)
    if list(descriptor) != branch["descriptor"]:
        raise RuntimeError("fourth-word branch descriptor mismatch")
    if canonical_word != int(branch["canonical_word"]):
        raise RuntimeError("fourth-word branch representative mismatch")
    if len(words) != int(branch["orbit_size"]):
        raise RuntimeError("fourth-word branch orbit size mismatch")
    if len(earlier_words) != int(branch["earlier_word_count"]):
        raise RuntimeError("fourth-word branch prefix mismatch")

    clauses = list(child_clauses)
    clauses.append((canonical_word + 1,))
    earlier_units = [-(word + 1) for word in earlier_words]
    clauses.extend((literal,) for literal in earlier_units)
    child_text = dimacs_text(child_variables, child_clauses)
    metadata = {
        "schema_version": 1,
        "branch_id": branch["branch_id"],
        "branch_sha256": branch["branch_sha256"],
        "parent_child_id": child["child_id"],
        "parent_case_id": parent_case["case_id"],
        "live_child_index": child["live_child_index"],
        "minimum_distance": parent_case["minimum_weight"],
        "child_formula": {
            "variables": child_variables,
            "clauses": len(child_clauses),
            "sha256": hashlib.sha256(
                child_text.encode("ascii")
            ).hexdigest(),
            "metadata": child_metadata,
        },
        "fourth_orbit_index": orbit_index,
        "fourth_orbit_count": len(grouped),
        "fourth_candidate_word_count": classification[
            "candidate_word_count"
        ],
        "selected_fourth_word": canonical_word,
        "selected_fourth_word_literal": canonical_word + 1,
        "earlier_fourth_word_count": len(earlier_words),
        "earlier_fourth_word_unit_sha256": unit_digest(
            earlier_units
        ),
        "variables": child_variables,
        "clauses": len(clauses),
    }
    return child_variables, clauses, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("child_frontier", type=Path)
    parser.add_argument("fourth_frontier", type=Path)
    parser.add_argument("branch_id")
    parser.add_argument("formula_output", type=Path)
    parser.add_argument("metadata_output", type=Path)
    args = parser.parse_args()

    root = repository_root()
    parent_path = ensure_repository_path(args.parent_manifest, root)
    third_path = ensure_repository_path(args.third_word_manifest, root)
    child_frontier_path = ensure_repository_path(
        args.child_frontier,
        root,
    )
    fourth_frontier_path = ensure_repository_path(
        args.fourth_frontier,
        root,
    )
    formula_output = ensure_repository_path(args.formula_output, root)
    metadata_output = ensure_repository_path(args.metadata_output, root)
    source_paths = {
        parent_path,
        third_path,
        child_frontier_path,
        fourth_frontier_path,
    }
    if len(source_paths) != 4:
        raise SystemExit("source manifests must use distinct files")
    if not all(path.is_file() for path in source_paths):
        raise SystemExit("source manifests must be regular files")
    source_list = list(source_paths)
    if any(
        os.path.samefile(left, right)
        for index, left in enumerate(source_list)
        for right in source_list[index + 1:]
    ):
        raise SystemExit("source manifests alias the same file")
    if formula_output == metadata_output:
        raise SystemExit("formula and metadata outputs must be distinct")
    if (
        formula_output.exists()
        and metadata_output.exists()
        and os.path.samefile(formula_output, metadata_output)
    ):
        raise SystemExit("formula and metadata outputs alias the same file")
    for output in (formula_output, metadata_output):
        if output.exists() and not output.is_file():
            raise SystemExit(
                "formula and metadata outputs must be regular files"
            )
    if (
        {formula_output, metadata_output} & source_paths
        or aliases_existing_file(formula_output, source_paths)
        or aliases_existing_file(metadata_output, source_paths)
    ):
        raise SystemExit("an output path aliases a source manifest")
    python_sources = repository_python_sources(root)
    if (
        {formula_output, metadata_output} & python_sources
        or aliases_existing_file(formula_output, python_sources)
        or aliases_existing_file(metadata_output, python_sources)
    ):
        raise SystemExit("an output path aliases repository source code")

    parent_manifest, parent_sha256 = load_snapshot(parent_path)
    third_manifest, third_sha256 = load_snapshot(third_path)
    child_frontier, child_frontier_sha256 = load_snapshot(
        child_frontier_path
    )
    fourth_frontier, fourth_frontier_sha256 = load_snapshot(
        fourth_frontier_path
    )
    source_hashes = {
        "parent_manifest": parent_sha256,
        "third_word_manifest": third_sha256,
        "child_frontier": child_frontier_sha256,
        "fourth_frontier": fourth_frontier_sha256,
    }
    if source_hashes["parent_manifest"] != child_frontier["sources"][
        "stage1_parent_manifest"
    ]["sha256"]:
        raise SystemExit("parent manifest does not match child frontier")
    if source_hashes["third_word_manifest"] != child_frontier["sources"][
        "third_word_manifest"
    ]["sha256"]:
        raise SystemExit("third-word manifest does not match child frontier")
    for label in (
        "parent_manifest",
        "third_word_manifest",
        "child_frontier",
    ):
        if source_hashes[label] != fourth_frontier["sources"][label][
            "sha256"
        ]:
            raise SystemExit(
                f"{label} does not match fourth-word frontier"
            )

    fourth_child, branch = find_branch(
        fourth_frontier,
        args.branch_id,
    )
    frontier_parent, child = find_parent_and_child(
        child_frontier,
        str(fourth_child["parent_child_id"]),
    )
    case_id = str(frontier_parent["parent_case_id"])
    parent_case = next(
        case
        for case in parent_manifest["cases"]
        if case["case_id"] == case_id
    )
    third_parent = next(
        parent
        for parent in third_manifest["parents"]
        if parent["parent_case_id"] == case_id
    )
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
    if (
        base_formula in {formula_output, metadata_output}
        or aliases_existing_file(
            formula_output,
            {base_formula},
        )
        or aliases_existing_file(
            metadata_output,
            {base_formula},
        )
    ):
        raise SystemExit("an output path aliases the base formula")
    if file_sha256(base_formula) != frontier_parent[
        "constraint_profile"
    ]["minimum_distance"]["formula"]["sha256"]:
        raise SystemExit("minimum-distance formula hash mismatch")

    variables, clauses, metadata = build_fourth_formula(
        base_formula,
        parent_case,
        third_parent,
        frontier_parent,
        child,
        fourth_child,
        branch,
        length=int(parent_manifest["length"]),
    )
    text = dimacs_text(variables, clauses)
    for label, path in (
        ("parent_manifest", parent_path),
        ("third_word_manifest", third_path),
        ("child_frontier", child_frontier_path),
        ("fourth_frontier", fourth_frontier_path),
    ):
        if file_sha256(path) != source_hashes[label]:
            raise RuntimeError(f"{label} changed during generation")
    if file_sha256(base_formula) != frontier_parent[
        "constraint_profile"
    ]["minimum_distance"]["formula"]["sha256"]:
        raise RuntimeError("base formula changed during generation")
    formula_output.parent.mkdir(parents=True, exist_ok=True)
    formula_output.write_text(text, encoding="ascii")
    metadata.update(
        {
            "base_formula": display_path(base_formula, root),
            "formula": display_path(formula_output, root),
            "formula_sha256": hashlib.sha256(
                text.encode("ascii")
            ).hexdigest(),
            "parent_manifest": display_path(parent_path, root),
            "parent_manifest_sha256": source_hashes[
                "parent_manifest"
            ],
            "third_word_manifest": display_path(third_path, root),
            "third_word_manifest_sha256": source_hashes[
                "third_word_manifest"
            ],
            "child_frontier": display_path(
                child_frontier_path,
                root,
            ),
            "child_frontier_sha256": source_hashes[
                "child_frontier"
            ],
            "fourth_frontier": display_path(
                fourth_frontier_path,
                root,
            ),
            "fourth_frontier_sha256": source_hashes[
                "fourth_frontier"
            ],
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
