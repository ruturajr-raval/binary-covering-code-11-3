#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from fourth_word_symmetry import (
    TRIPLE_CELL_ORDER,
    fourth_orbits,
    orbit_manifest_digest,
    triple_coordinate_masks,
)
from generate_third_word_child_formula import (
    display_path,
    ensure_repository_path,
)
from third_word_symmetry import weight


def load_snapshot(path: Path) -> tuple[dict[str, object], str]:
    payload = path.read_bytes()
    return (
        json.loads(payload.decode("ascii")),
        hashlib.sha256(payload).hexdigest(),
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def fixed_uncovered_count(
    fixed_words: list[int],
    *,
    length: int,
    radius: int,
) -> int:
    return sum(
        all(weight(vertex ^ word) > radius for word in fixed_words)
        for vertex in range(1 << length)
    )


def find_selected_children(
    frontier: dict[str, object],
    child_ids: list[str],
) -> list[tuple[dict[str, object], dict[str, object]]]:
    requested = set(child_ids)
    if len(requested) != len(child_ids):
        raise SystemExit("selected child identifiers must be unique")
    selected = []
    for parent in frontier["parents"]:
        for child in parent["children"]:
            if child["child_id"] in requested:
                selected.append((parent, child))
    found = {str(child["child_id"]) for _, child in selected}
    missing = requested - found
    if missing:
        raise SystemExit(
            "unknown selected child identifiers: "
            + ", ".join(sorted(missing))
        )
    selected.sort(key=lambda item: int(item[1]["live_child_index"]))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("child_frontier", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--child-id",
        action="append",
        required=True,
    )
    args = parser.parse_args()

    root = repository_root()
    parent_path = ensure_repository_path(args.parent_manifest, root)
    third_path = ensure_repository_path(args.third_word_manifest, root)
    frontier_path = ensure_repository_path(args.child_frontier, root)
    output_path = ensure_repository_path(args.output, root)
    source_paths = {parent_path, third_path, frontier_path}
    if len(source_paths) != 3:
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
    if (
        output_path in source_paths
        or aliases_existing_file(output_path, source_paths)
    ):
        raise SystemExit("output path aliases a source manifest")
    if output_path.exists() and not output_path.is_file():
        raise SystemExit("output path exists and is not a regular file")
    if (
        output_path in repository_python_sources(root)
        or aliases_existing_file(
            output_path,
            repository_python_sources(root),
        )
    ):
        raise SystemExit("output path aliases repository source code")

    parent_manifest, parent_sha256 = load_snapshot(parent_path)
    third_manifest, third_sha256 = load_snapshot(third_path)
    frontier, frontier_sha256 = load_snapshot(frontier_path)
    if parent_sha256 != frontier["sources"][
        "stage1_parent_manifest"
    ]["sha256"]:
        raise SystemExit("parent manifest does not match the child frontier")
    if third_sha256 != frontier["sources"][
        "third_word_manifest"
    ]["sha256"]:
        raise SystemExit(
            "third-word manifest does not match the child frontier"
        )

    parents = {
        str(parent["case_id"]): parent
        for parent in parent_manifest["cases"]
    }
    third_parents = {
        str(parent["parent_case_id"]): parent
        for parent in third_manifest["parents"]
    }
    length = int(parent_manifest["length"])
    selected = find_selected_children(frontier, args.child_id)
    records = []
    all_branch_digests = []
    total_candidates = 0
    total_orbits = 0
    total_matching_exclusions = 0
    for frontier_parent, child in selected:
        if (
            frontier_parent["status"] != "active"
            or child["branch_status"] != "live"
        ):
            raise SystemExit(
                f"{child['child_id']}: selected child is not live"
            )
        case_id = str(frontier_parent["parent_case_id"])
        parent = parents[case_id]
        third_parent = third_parents[case_id]
        third_index = int(child["parent_orbit_index"])
        retained_third = third_parent["orbits"][third_index]
        for key in (
            "canonical_word",
            "descriptor",
            "earlier_word_count",
            "orbit_size",
        ):
            if retained_third[key] != child[key]:
                raise SystemExit(
                    f"{child['child_id']}: third-word source mismatch"
                )

        matching = bool(frontier_parent["matching_eligible"])
        grouped, classification = fourth_orbits(
            parent,
            child,
            length=length,
            matching=matching,
        )
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
                        canonical_word ^ int(parent["first_word"])
                    ),
                    "second": weight(
                        canonical_word ^ int(parent["second_word"])
                    ),
                    "third": weight(
                        canonical_word ^ int(child["canonical_word"])
                    ),
                },
            }
            branch["branch_sha256"] = branch_digest(branch)
            all_branch_digests.append(branch["branch_sha256"])
            branches.append(branch)
            earlier_word_count += len(words)

        first_word = int(parent["first_word"])
        second_word = int(parent["second_word"])
        third_word = int(child["canonical_word"])
        fixed_words = [0, first_word, second_word, third_word]
        masks = triple_coordinate_masks(
            first_word,
            second_word,
            third_word,
            length=length,
        )
        uncovered_count = fixed_uncovered_count(
            fixed_words,
            length=length,
            radius=3,
        )
        if uncovered_count == 0:
            raise RuntimeError(
                f"{child['child_id']}: fixed words already cover the cube"
            )
        record = {
            "parent_child_id": child["child_id"],
            "parent_case_id": case_id,
            "live_child_index": child["live_child_index"],
            "minimum_distance": parent["minimum_weight"],
            "matching_enforced": matching,
            "fixed_words": fixed_words,
            "fixed_word_uncovered_count": uncovered_count,
            "triple_cell_order": [
                "".join(str(bit) for bit in signature)
                for signature in TRIPLE_CELL_ORDER
            ],
            "triple_cell_sizes": [weight(mask) for mask in masks],
            "classification": classification,
            "fourth_orbit_count": len(branches),
            "fourth_orbit_sha256": orbit_manifest_digest(branches),
            "branches": branches,
        }
        total_candidates += int(classification["candidate_word_count"])
        total_orbits += len(branches)
        total_matching_exclusions += int(
            classification["excluded_matching_count"]
        )
        records.append(record)

    report = {
        "record_type": "fourth-word-hard-frontier",
        "schema_version": 1,
        "length": length,
        "radius": 3,
        "sources": {
            "parent_manifest": {
                "path": display_path(parent_path, root),
                "sha256": parent_sha256,
            },
            "third_word_manifest": {
                "path": display_path(third_path, root),
                "sha256": third_sha256,
            },
            "child_frontier": {
                "path": display_path(frontier_path, root),
                "sha256": frontier_sha256,
            },
        },
        "counts": {
            "selected_child_count": len(records),
            "candidate_word_count": total_candidates,
            "fourth_orbit_count": total_orbits,
            "excluded_matching_count": total_matching_exclusions,
        },
        "selected_child_ids": [
            str(record["parent_child_id"])
            for record in records
        ],
        "branch_digest_sha256": hashlib.sha256(
            "".join(
                f"{digest}\n" for digest in all_branch_digests
            ).encode("ascii")
        ).hexdigest(),
        "children": records,
    }
    for path, digest in (
        (parent_path, parent_sha256),
        (third_path, third_sha256),
        (frontier_path, frontier_sha256),
    ):
        if file_sha256(path) != digest:
            raise RuntimeError("source manifest changed during generation")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(
        json.dumps(
            {
                "candidate_word_count": total_candidates,
                "fourth_orbit_count": total_orbits,
                "output": display_path(output_path, root),
                "selected_child_count": len(records),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
