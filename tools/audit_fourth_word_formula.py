#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from audit_covering_cnf import read_dimacs
from audit_fourth_word_frontier import (
    find_child,
    independent_fourth_orbits,
    independent_third_orbits,
)
from audit_third_word_formula import append_matching, parent_units


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def resolve_path(value: object, root: Path) -> Path:
    path = Path(str(value))
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise SystemExit(f"path is outside the repository: {path}")
    return resolved


def display_path(path: Path, root: Path) -> str:
    return str(resolve_path(path, root).relative_to(root))


def dimacs_text(
    variables: int,
    clauses: list[tuple[int, ...]],
) -> str:
    lines = [f"p cnf {variables} {len(clauses)}"]
    lines.extend(
        " ".join(str(literal) for literal in clause) + " 0"
        for clause in clauses
    )
    return "\n".join(lines) + "\n"


def unit_digest(units: list[int]) -> str:
    payload = "".join(f"{literal}\n" for literal in units)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def word_weight(word: int) -> int:
    return bin(word).count("1")


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


def orbit_digest(branches: list[dict[str, object]]) -> str:
    lines = []
    for branch in branches:
        descriptor = ",".join(
            str(value) for value in branch["descriptor"]
        )
        lines.append(
            f"{branch['branch_id']}:{descriptor}:"
            f"{branch['canonical_word']}:{branch['orbit_size']}:"
            f"{branch['earlier_word_count']}\n"
        )
    return hashlib.sha256("".join(lines).encode("ascii")).hexdigest()


def reconstruct_branches(
    parent: dict[str, object],
    child: dict[str, object],
    fourth_orbits: list[tuple[list[int], list[int]]],
) -> list[dict[str, object]]:
    branches = []
    earlier_word_count = 0
    for orbit_index, (descriptor, words) in enumerate(fourth_orbits):
        canonical_word = min(words)
        branch = {
            "branch_id": (
                f"{child['child_id']}::fourth-{orbit_index:03d}"
            ),
            "parent_child_id": child["child_id"],
            "fourth_orbit_index": orbit_index,
            "descriptor": descriptor,
            "canonical_word": canonical_word,
            "orbit_size": len(words),
            "earlier_word_count": earlier_word_count,
            "constraint_units": {
                "selected_word_literal": canonical_word + 1,
                "excluded_earlier_word_count": earlier_word_count,
            },
            "fixed_word_distances": {
                "zero": word_weight(canonical_word),
                "first": word_weight(
                    canonical_word ^ int(parent["first_word"])
                ),
                "second": word_weight(
                    canonical_word ^ int(parent["second_word"])
                ),
                "third": word_weight(
                    canonical_word ^ int(child["canonical_word"])
                ),
            },
        }
        branch["branch_sha256"] = branch_digest(branch)
        branches.append(branch)
        earlier_word_count += len(words)
    return branches


def independently_matching(parent: dict[str, object]) -> bool:
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


def find_branch(
    fourth_frontier: dict[str, object],
    branch_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    matches = [
        (child, branch)
        for child in fourth_frontier["children"]
        for branch in child["branches"]
        if branch["branch_id"] == branch_id
    ]
    if len(matches) != 1:
        raise SystemExit(f"branch identity is not unique: {branch_id}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("formula", type=Path)
    parser.add_argument("metadata", type=Path)
    args = parser.parse_args()

    root = repository_root()
    formula_path = resolve_path(args.formula, root)
    metadata_path = resolve_path(args.metadata, root)
    metadata, metadata_sha256 = load_snapshot(metadata_path)
    if metadata["schema_version"] != 1:
        raise SystemExit("unsupported fourth-word formula schema")

    source_paths = {
        "parent_manifest": resolve_path(
            metadata["parent_manifest"],
            root,
        ),
        "third_word_manifest": resolve_path(
            metadata["third_word_manifest"],
            root,
        ),
        "child_frontier": resolve_path(
            metadata["child_frontier"],
            root,
        ),
        "fourth_frontier": resolve_path(
            metadata["fourth_frontier"],
            root,
        ),
    }
    all_paths = {
        formula_path,
        metadata_path,
        *source_paths.values(),
    }
    if len(all_paths) != 6:
        raise SystemExit("formula audit inputs must use distinct files")
    path_list = list(all_paths)
    if any(
        os.path.samefile(left, right)
        for index, left in enumerate(path_list)
        for right in path_list[index + 1:]
    ):
        raise SystemExit("formula audit inputs alias the same file")
    source_records = {}
    for label, path in source_paths.items():
        expected = metadata[f"{label}_sha256"]
        record, digest = load_snapshot(path)
        if digest != expected:
            raise SystemExit(f"{label} authentication failed")
        source_records[label] = record
    base_formula_path = resolve_path(metadata["base_formula"], root)
    if not base_formula_path.is_file():
        raise SystemExit("base formula is missing")

    parent_manifest = source_records["parent_manifest"]
    third_manifest = source_records["third_word_manifest"]
    child_frontier = source_records["child_frontier"]
    fourth_frontier = source_records["fourth_frontier"]
    if metadata["parent_manifest_sha256"] != child_frontier["sources"][
        "stage1_parent_manifest"
    ]["sha256"]:
        raise SystemExit("parent source does not match child frontier")
    if metadata["third_word_manifest_sha256"] != child_frontier[
        "sources"
    ]["third_word_manifest"]["sha256"]:
        raise SystemExit("third source does not match child frontier")
    for label in (
        "parent_manifest",
        "third_word_manifest",
        "child_frontier",
    ):
        if metadata[f"{label}_sha256"] != fourth_frontier["sources"][
            label
        ]["sha256"]:
            raise SystemExit(
                f"{label} does not match fourth-word frontier"
            )

    fourth_child, branch = find_branch(
        fourth_frontier,
        str(metadata["branch_id"]),
    )
    frontier_parent, child = find_child(
        child_frontier,
        str(fourth_child["parent_child_id"]),
    )
    if (
        frontier_parent["status"] != "active"
        or child["branch_status"] != "live"
    ):
        raise SystemExit("fourth-word branch parent is not live")
    case_id = str(frontier_parent["parent_case_id"])
    parent = next(
        case
        for case in parent_manifest["cases"]
        if case["case_id"] == case_id
    )
    third_parent = next(
        record
        for record in third_manifest["parents"]
        if record["parent_case_id"] == case_id
    )
    required_base = frontier_parent["constraint_profile"][
        "minimum_distance"
    ]["formula"]
    required_base_path = resolve_path(required_base["path"], root)
    if base_formula_path != required_base_path:
        raise SystemExit("base formula is not the child-frontier formula")

    length = int(parent_manifest["length"])
    third_orbits = independent_third_orbits(parent, length)
    third_index = int(child["parent_orbit_index"])
    third_descriptor, third_words = third_orbits[third_index]
    earlier_third_words = [
        word
        for _, words in third_orbits[:third_index]
        for word in words
    ]
    third_word = min(third_words)
    if child["descriptor"] != third_descriptor:
        raise SystemExit("third-word descriptor is incorrect")
    if int(child["canonical_word"]) != third_word:
        raise SystemExit("third-word representative is incorrect")
    if int(child["orbit_size"]) != len(third_words):
        raise SystemExit("third-word orbit size is incorrect")
    if int(child["earlier_word_count"]) != len(earlier_third_words):
        raise SystemExit("third-word prefix is incorrect")
    retained_third = third_parent["orbits"][third_index]
    for key in (
        "canonical_word",
        "descriptor",
        "earlier_word_count",
        "orbit_size",
    ):
        if retained_third[key] != child[key]:
            raise SystemExit("third-word retained sources disagree")

    base_variables, base_clauses, base_digest = read_dimacs(
        base_formula_path
    )
    if base_digest != required_base["sha256"]:
        raise SystemExit("base formula hash does not match child frontier")
    units = parent_units(parent, length)
    expected_child_clauses = list(base_clauses)
    expected_child_clauses.extend((literal,) for literal in units)
    expected_child_clauses.append((third_word + 1,))
    earlier_third_units = [
        -(word + 1) for word in earlier_third_words
    ]
    expected_child_clauses.extend(
        (literal,) for literal in earlier_third_units
    )
    matching = independently_matching(parent)
    if bool(frontier_parent["matching_eligible"]) != matching:
        raise SystemExit("child-frontier matching scope is incorrect")
    expected_child_variables = base_variables
    matching_metadata = {
        "matching_allowed_vertices": 0,
        "matching_gated_vertices": 0,
        "matching_neighbor_incidences": 0,
        "matching_auxiliary_variables": 0,
        "matching_clauses": 0,
    }
    if matching:
        expected_child_variables, matching_metadata = append_matching(
            expected_child_clauses,
            variable_count=expected_child_variables,
            case=parent,
            length=length,
        )
    child_metadata = {
        "schema_version": 1,
        "child_id": child["child_id"],
        "live_child_index": child["live_child_index"],
        "parent_case_id": case_id,
        "parent_orbit_index": third_index,
        "minimum_distance": parent["minimum_weight"],
        "base_formula_sha256": base_digest,
        "base_variables": base_variables,
        "base_clauses": len(base_clauses),
        "parent_unit_count": len(units),
        "parent_unit_sha256": unit_digest(units),
        "selected_word": third_word,
        "selected_word_literal": third_word + 1,
        "earlier_word_count": len(earlier_third_words),
        "earlier_word_unit_sha256": unit_digest(
            earlier_third_units
        ),
        "enforce_minimum_distance_matching": matching,
        "variables": expected_child_variables,
        "clauses": len(expected_child_clauses),
        **matching_metadata,
    }
    child_text = dimacs_text(
        expected_child_variables,
        expected_child_clauses,
    )

    fourth_orbits, classification = independent_fourth_orbits(
        parent,
        child,
        length=length,
        matching=matching,
    )
    expected_branches = reconstruct_branches(
        parent,
        child,
        fourth_orbits,
    )
    if fourth_child["branches"] != expected_branches:
        raise SystemExit("fourth-word branch manifest is incorrect")
    if int(fourth_child["fourth_orbit_count"]) != len(
        fourth_orbits
    ):
        raise SystemExit("fourth-word orbit count is incorrect")
    if fourth_child["fourth_orbit_sha256"] != orbit_digest(
        expected_branches
    ):
        raise SystemExit("fourth-word orbit digest is incorrect")
    if fourth_child["classification"] != classification:
        raise SystemExit("fourth-word classification is incorrect")
    fourth_index = int(branch["fourth_orbit_index"])
    if fourth_index < 0 or fourth_index >= len(fourth_orbits):
        raise SystemExit("fourth-word orbit index is outside the child")
    if branch != expected_branches[fourth_index]:
        raise SystemExit("fourth-word branch identity is incorrect")
    descriptor, fourth_words = fourth_orbits[fourth_index]
    earlier_fourth_words = [
        word
        for _, words in fourth_orbits[:fourth_index]
        for word in words
    ]
    fourth_word = min(fourth_words)
    if descriptor != branch["descriptor"]:
        raise SystemExit("fourth-word branch descriptor is incorrect")
    if fourth_word != int(branch["canonical_word"]):
        raise SystemExit("fourth-word representative is incorrect")
    if len(fourth_words) != int(branch["orbit_size"]):
        raise SystemExit("fourth-word orbit size is incorrect")
    if len(earlier_fourth_words) != int(branch["earlier_word_count"]):
        raise SystemExit("fourth-word prefix is incorrect")

    earlier_fourth_units = [
        -(word + 1) for word in earlier_fourth_words
    ]
    expected_clauses = list(expected_child_clauses)
    expected_clauses.append((fourth_word + 1,))
    expected_clauses.extend(
        (literal,) for literal in earlier_fourth_units
    )
    variables, clauses, formula_digest = read_dimacs(formula_path)
    if variables != expected_child_variables:
        raise SystemExit("fourth-word formula variable count is incorrect")
    if clauses != expected_clauses:
        raise SystemExit("fourth-word formula clauses are incorrect")

    expected_metadata = {
        "schema_version": 1,
        "branch_id": branch["branch_id"],
        "branch_sha256": branch["branch_sha256"],
        "parent_child_id": child["child_id"],
        "parent_case_id": case_id,
        "live_child_index": child["live_child_index"],
        "minimum_distance": parent["minimum_weight"],
        "child_formula": {
            "variables": expected_child_variables,
            "clauses": len(expected_child_clauses),
            "sha256": hashlib.sha256(
                child_text.encode("ascii")
            ).hexdigest(),
            "metadata": child_metadata,
        },
        "fourth_orbit_index": fourth_index,
        "fourth_orbit_count": len(fourth_orbits),
        "fourth_candidate_word_count": classification[
            "candidate_word_count"
        ],
        "selected_fourth_word": fourth_word,
        "selected_fourth_word_literal": fourth_word + 1,
        "earlier_fourth_word_count": len(earlier_fourth_words),
        "earlier_fourth_word_unit_sha256": unit_digest(
            earlier_fourth_units
        ),
        "variables": expected_child_variables,
        "clauses": len(expected_clauses),
        "base_formula": display_path(base_formula_path, root),
        "formula": display_path(formula_path, root),
        "formula_sha256": formula_digest,
        "parent_manifest": display_path(
            source_paths["parent_manifest"],
            root,
        ),
        "parent_manifest_sha256": metadata[
            "parent_manifest_sha256"
        ],
        "third_word_manifest": display_path(
            source_paths["third_word_manifest"],
            root,
        ),
        "third_word_manifest_sha256": metadata[
            "third_word_manifest_sha256"
        ],
        "child_frontier": display_path(
            source_paths["child_frontier"],
            root,
        ),
        "child_frontier_sha256": metadata[
            "child_frontier_sha256"
        ],
        "fourth_frontier": display_path(
            source_paths["fourth_frontier"],
            root,
        ),
        "fourth_frontier_sha256": metadata[
            "fourth_frontier_sha256"
        ],
    }
    if metadata != expected_metadata:
        raise SystemExit("fourth-word formula metadata is incorrect")
    for label, path in source_paths.items():
        if file_sha256(path) != metadata[f"{label}_sha256"]:
            raise RuntimeError(f"{label} changed during audit")
    if file_sha256(metadata_path) != metadata_sha256:
        raise RuntimeError("formula metadata changed during audit")
    if file_sha256(formula_path) != formula_digest:
        raise RuntimeError("formula changed during audit")
    print(
        json.dumps(
            {
                "branch_id": branch["branch_id"],
                "clauses": len(expected_clauses),
                "formula_sha256": formula_digest,
                "valid": True,
                "variables": expected_child_variables,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
