#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path


HARD_CHILD_IDS = (
    "w4-weight5-intersection0::orbit-005",
    "w4-weight5-intersection0::orbit-007",
    "w4-weight5-intersection0::orbit-014",
    "w4-weight5-intersection0::orbit-015",
)

EXPECTED_CHILD_COUNTS = {
    "w4-weight5-intersection0::orbit-005": (815, 85, 233),
    "w4-weight5-intersection0::orbit-007": (751, 76, 175),
    "w4-weight5-intersection0::orbit-014": (727, 73, 158),
    "w4-weight5-intersection0::orbit-015": (674, 116, 187),
}

TRIPLE_CELL_ORDER = tuple(itertools.product((0, 1), repeat=3))


def weight(word: int) -> int:
    return bin(word).count("1")


def load_snapshot(
    path: Path,
) -> tuple[dict[str, object], str]:
    payload = path.read_bytes()
    return (
        json.loads(payload.decode("ascii")),
        hashlib.sha256(payload).hexdigest(),
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise SystemExit(f"path is outside the repository: {path}")
    return resolved


def display_path(path: Path, root: Path) -> str:
    return str(resolve_path(path, root).relative_to(root))


def third_coordinate_masks(
    first_word: int,
    second_word: int,
    length: int,
) -> tuple[int, int, int, int]:
    ambient = (1 << length) - 1
    return (
        first_word & second_word,
        first_word & (ambient ^ second_word),
        second_word & (ambient ^ first_word),
        ambient ^ (first_word | second_word),
    )


def parent_candidate(
    word: int,
    parent: dict[str, object],
    length: int,
) -> bool:
    first_word = int(parent["first_word"])
    second_word = int(parent["second_word"])
    threshold = parent["second_descriptor"]
    return (
        0 <= word < 1 << length
        and word not in {0, first_word, second_word}
        and weight(word) >= int(parent["minimum_weight"])
        and (
            weight(word),
            weight(word & first_word),
        )
        >= (
            int(threshold["weight"]),
            int(threshold["intersection"]),
        )
    )


def independent_third_orbits(
    parent: dict[str, object],
    length: int,
) -> list[tuple[list[int], list[int]]]:
    first_word = int(parent["first_word"])
    second_word = int(parent["second_word"])
    masks = third_coordinate_masks(first_word, second_word, length)
    grouped: dict[tuple[int, int, int, int], list[int]] = {}
    for word in range(1 << length):
        if not parent_candidate(word, parent, length):
            continue
        descriptor = tuple(weight(word & mask) for mask in masks)
        grouped.setdefault(descriptor, []).append(word)
    return [
        (list(descriptor), grouped[descriptor])
        for descriptor in sorted(grouped)
    ]


def triple_masks(
    first_word: int,
    second_word: int,
    third_word: int,
    length: int,
) -> tuple[int, ...]:
    result = []
    for signature in TRIPLE_CELL_ORDER:
        mask = 0
        for position in range(length):
            if (
                (first_word >> position) & 1,
                (second_word >> position) & 1,
                (third_word >> position) & 1,
            ) == signature:
                mask |= 1 << position
        result.append(mask)
    return tuple(result)


def matching_compatible(
    candidate: int,
    fixed_words: tuple[int, ...],
    minimum_distance: int,
) -> bool:
    selected = (*fixed_words, candidate)
    return all(
        sum(
            weight(word ^ other) == minimum_distance
            for other in selected
            if other != word
        )
        <= 1
        for word in selected
    )


def classify_words(
    parent: dict[str, object],
    child: dict[str, object],
    *,
    length: int,
    matching: bool,
) -> tuple[list[int], dict[str, int]]:
    first_word = int(parent["first_word"])
    second_word = int(parent["second_word"])
    third_word = int(child["canonical_word"])
    fixed_words = (0, first_word, second_word, third_word)
    fixed_set = set(fixed_words)
    third_orbits = independent_third_orbits(parent, length)
    orbit_index = int(child["parent_orbit_index"])
    descriptor, target_words = third_orbits[orbit_index]
    if descriptor != child["descriptor"]:
        raise SystemExit("retained child descriptor is incorrect")
    if min(target_words) != int(child["canonical_word"]):
        raise SystemExit("retained child representative is incorrect")
    if len(target_words) != int(child["orbit_size"]):
        raise SystemExit("retained child orbit size is incorrect")
    earlier_words = {
        word
        for _, words in third_orbits[:orbit_index]
        for word in words
    }
    if len(earlier_words) != int(child["earlier_word_count"]):
        raise SystemExit("retained child prefix is incorrect")

    minimum_distance = int(parent["minimum_weight"])
    counts = {
        "ambient_word_count": 1 << length,
        "fixed_word_count": 0,
        "excluded_parent_threshold_count": 0,
        "excluded_earlier_third_word_count": 0,
        "excluded_fixed_distance_count": 0,
        "excluded_matching_count": 0,
        "candidate_word_count": 0,
    }
    candidates = []
    for word in range(1 << length):
        if word in fixed_set:
            counts["fixed_word_count"] += 1
        elif not parent_candidate(word, parent, length):
            counts["excluded_parent_threshold_count"] += 1
        elif word in earlier_words:
            counts["excluded_earlier_third_word_count"] += 1
        elif any(
            weight(word ^ fixed) < minimum_distance
            for fixed in fixed_words
        ):
            counts["excluded_fixed_distance_count"] += 1
        elif (
            matching
            and not matching_compatible(
                word,
                fixed_words,
                minimum_distance,
            )
        ):
            counts["excluded_matching_count"] += 1
        else:
            counts["candidate_word_count"] += 1
            candidates.append(word)
    if sum(
        count
        for label, count in counts.items()
        if label != "ambient_word_count"
    ) != 1 << length:
        raise SystemExit("fourth-word classification is not a partition")
    return candidates, counts


def independent_fourth_orbits(
    parent: dict[str, object],
    child: dict[str, object],
    *,
    length: int,
    matching: bool,
) -> tuple[list[tuple[list[int], list[int]]], dict[str, int]]:
    candidates, counts = classify_words(
        parent,
        child,
        length=length,
        matching=matching,
    )
    masks = triple_masks(
        int(parent["first_word"]),
        int(parent["second_word"]),
        int(child["canonical_word"]),
        length,
    )
    grouped: dict[tuple[int, ...], list[int]] = {}
    for word in candidates:
        descriptor = tuple(weight(word & mask) for mask in masks)
        grouped.setdefault(descriptor, []).append(word)
    return (
        [
            (list(descriptor), grouped[descriptor])
            for descriptor in sorted(grouped)
        ],
        counts,
    )


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


def orbit_digest(orbits: list[dict[str, object]]) -> str:
    lines = []
    for orbit in orbits:
        descriptor = ",".join(
            str(value) for value in orbit["descriptor"]
        )
        lines.append(
            f"{orbit['branch_id']}:{descriptor}:"
            f"{orbit['canonical_word']}:{orbit['orbit_size']}:"
            f"{orbit['earlier_word_count']}\n"
        )
    return hashlib.sha256("".join(lines).encode("ascii")).hexdigest()


def fixed_uncovered_count(
    fixed_words: list[int],
    length: int,
) -> int:
    return sum(
        all(weight(vertex ^ word) > 3 for word in fixed_words)
        for vertex in range(1 << length)
    )


def find_child(
    frontier: dict[str, object],
    child_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    matches = [
        (parent, child)
        for parent in frontier["parents"]
        for child in parent["children"]
        if child["child_id"] == child_id
    ]
    if len(matches) != 1:
        raise SystemExit(f"child identity is not unique: {child_id}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("child_frontier", type=Path)
    parser.add_argument("fourth_word_frontier", type=Path)
    args = parser.parse_args()

    root = repository_root()
    parent_path = resolve_path(args.parent_manifest, root)
    third_path = resolve_path(args.third_word_manifest, root)
    frontier_path = resolve_path(args.child_frontier, root)
    manifest_path = resolve_path(args.fourth_word_frontier, root)
    all_paths = {
        parent_path,
        third_path,
        frontier_path,
        manifest_path,
    }
    if len(all_paths) != 4:
        raise SystemExit("audit inputs must use distinct files")
    path_list = list(all_paths)
    if any(
        os.path.samefile(left, right)
        for index, left in enumerate(path_list)
        for right in path_list[index + 1:]
    ):
        raise SystemExit("audit inputs alias the same file")
    parent_manifest, parent_sha256 = load_snapshot(parent_path)
    third_manifest, third_sha256 = load_snapshot(third_path)
    frontier, frontier_sha256 = load_snapshot(frontier_path)
    manifest, manifest_sha256 = load_snapshot(manifest_path)
    if manifest["record_type"] != "fourth-word-hard-frontier":
        raise SystemExit("unexpected fourth-word frontier record type")
    if manifest["schema_version"] != 1:
        raise SystemExit("unsupported fourth-word frontier schema")
    if tuple(manifest["selected_child_ids"]) != HARD_CHILD_IDS:
        raise SystemExit("hard-child selection is incorrect")

    expected_sources = {
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
    }
    if manifest["sources"] != expected_sources:
        raise SystemExit("fourth-word source authentication failed")

    if expected_sources["parent_manifest"]["sha256"] != frontier[
        "sources"
    ]["stage1_parent_manifest"]["sha256"]:
        raise SystemExit("parent source does not match the child frontier")
    if expected_sources["third_word_manifest"]["sha256"] != frontier[
        "sources"
    ]["third_word_manifest"]["sha256"]:
        raise SystemExit(
            "third-word source does not match the child frontier"
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
    records = []
    branch_digests = []
    total_candidates = 0
    total_orbits = 0
    total_matching_exclusions = 0
    for child_id in HARD_CHILD_IDS:
        frontier_parent, child = find_child(frontier, child_id)
        if (
            frontier_parent["status"] != "active"
            or child["branch_status"] != "live"
        ):
            raise SystemExit(f"{child_id}: hard child is not live")
        case_id = str(frontier_parent["parent_case_id"])
        parent = parents[case_id]
        retained_third = third_parents[case_id]["orbits"][
            int(child["parent_orbit_index"])
        ]
        for key in (
            "canonical_word",
            "descriptor",
            "earlier_word_count",
            "orbit_size",
        ):
            if retained_third[key] != child[key]:
                raise SystemExit(f"{child_id}: third source mismatch")

        matching = (
            int(parent["second_descriptor"]["weight"])
            != int(parent["minimum_weight"])
            and (
                int(parent["minimum_weight"])
                + int(parent["second_descriptor"]["weight"])
                - 2
                * int(parent["second_descriptor"]["intersection"])
            )
            != int(parent["minimum_weight"])
        )
        if bool(frontier_parent["matching_eligible"]) != matching:
            raise SystemExit(f"{child_id}: matching scope is incorrect")
        grouped, classification = independent_fourth_orbits(
            parent,
            child,
            length=length,
            matching=matching,
        )
        expected_counts = EXPECTED_CHILD_COUNTS[child_id]
        observed_counts = (
            classification["candidate_word_count"],
            len(grouped),
            classification["excluded_matching_count"],
        )
        if observed_counts != expected_counts:
            raise SystemExit(
                f"{child_id}: independent hard-child counts changed"
            )

        branches = []
        earlier_word_count = 0
        for orbit_index, (descriptor, words) in enumerate(grouped):
            canonical_word = min(words)
            branch = {
                "branch_id": (
                    f"{child_id}::fourth-{orbit_index:03d}"
                ),
                "parent_child_id": child_id,
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
            branch_digests.append(branch["branch_sha256"])
            branches.append(branch)
            earlier_word_count += len(words)

        fixed_words = [
            0,
            int(parent["first_word"]),
            int(parent["second_word"]),
            int(child["canonical_word"]),
        ]
        masks = triple_masks(
            fixed_words[1],
            fixed_words[2],
            fixed_words[3],
            length,
        )
        uncovered_count = fixed_uncovered_count(
            fixed_words,
            length,
        )
        if uncovered_count == 0:
            raise SystemExit(
                f"{child_id}: fixed words already cover the cube"
            )
        records.append(
            {
                "parent_child_id": child_id,
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
                "triple_cell_sizes": [
                    weight(mask) for mask in masks
                ],
                "classification": classification,
                "fourth_orbit_count": len(branches),
                "fourth_orbit_sha256": orbit_digest(branches),
                "branches": branches,
            }
        )
        total_candidates += int(
            classification["candidate_word_count"]
        )
        total_orbits += len(branches)
        total_matching_exclusions += int(
            classification["excluded_matching_count"]
        )

    expected = {
        "record_type": "fourth-word-hard-frontier",
        "schema_version": 1,
        "length": length,
        "radius": 3,
        "sources": expected_sources,
        "counts": {
            "selected_child_count": len(records),
            "candidate_word_count": total_candidates,
            "fourth_orbit_count": total_orbits,
            "excluded_matching_count": total_matching_exclusions,
        },
        "selected_child_ids": list(HARD_CHILD_IDS),
        "branch_digest_sha256": hashlib.sha256(
            "".join(
                f"{digest}\n" for digest in branch_digests
            ).encode("ascii")
        ).hexdigest(),
        "children": records,
    }
    if expected["counts"] != {
        "selected_child_count": 4,
        "candidate_word_count": 2967,
        "fourth_orbit_count": 350,
        "excluded_matching_count": 753,
    }:
        raise SystemExit("aggregate hard-child counts changed")
    if manifest != expected:
        raise SystemExit(
            "fourth-word frontier does not match independent reconstruction"
        )
    for path, digest in (
        (parent_path, parent_sha256),
        (third_path, third_sha256),
        (frontier_path, frontier_sha256),
        (manifest_path, manifest_sha256),
    ):
        if file_sha256(path) != digest:
            raise RuntimeError("audit input changed during reconstruction")
    print(
        json.dumps(
            {
                "candidate_word_count": total_candidates,
                "fourth_orbit_count": total_orbits,
                "selected_child_count": len(records),
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
