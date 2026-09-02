#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def weight(word: int) -> int:
    return bin(word).count("1")


def masks(first: int, second: int, length: int) -> list[int]:
    ambient = (1 << length) - 1
    return [
        first & second,
        first & (ambient ^ second),
        second & (ambient ^ first),
        ambient ^ (first | second),
    ]


def descriptor(word: int, first: int, second: int, length: int) -> list[int]:
    return [weight(word & mask) for mask in masks(first, second, length)]


def representative(
    values: list[int],
    first: int,
    second: int,
    length: int,
) -> int:
    result = 0
    for count, mask in zip(values, masks(first, second, length)):
        positions = [
            position
            for position in range(length)
            if mask & (1 << position)
        ]
        if count < 0 or count > len(positions):
            raise SystemExit("descriptor exceeds a stabilizer cell")
        for position in positions[:count]:
            result |= 1 << position
    return result


def is_candidate(word: int, case: dict[str, object], length: int) -> bool:
    first = int(case["first_word"])
    second = int(case["second_word"])
    if word in {0, first, second}:
        return False
    payload = case["second_descriptor"]
    threshold = (
        int(payload["weight"]),
        int(payload["intersection"]),
    )
    return (
        0 <= word < 1 << length
        and weight(word) >= int(case["minimum_weight"])
        and (weight(word), weight(word & first)) >= threshold
    )


def digest(records: list[dict[str, object]]) -> str:
    lines = []
    for record in records:
        key = ",".join(str(value) for value in record["descriptor"])
        lines.append(
            f"{key}:{record['canonical_word']}:"
            f"{record['orbit_size']}:{record['earlier_word_count']}\n"
        )
    return hashlib.sha256("".join(lines).encode("ascii")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_manifest", type=Path)
    args = parser.parse_args()

    parent_manifest = json.loads(
        args.parent_manifest.read_text(encoding="ascii")
    )
    third_manifest = json.loads(
        args.third_manifest.read_text(encoding="ascii")
    )
    if hashlib.sha256(args.parent_manifest.read_bytes()).hexdigest() != (
        third_manifest["source_parent_manifest_sha256"]
    ):
        raise SystemExit("parent-manifest hash does not match")
    length = int(parent_manifest["length"])
    parents = {
        case["case_id"]: case
        for case in parent_manifest["cases"]
    }
    records = {
        parent["parent_case_id"]: parent
        for parent in third_manifest["parents"]
    }
    if set(records) != set(parents):
        raise SystemExit("third-word parents are incomplete")

    total_orbits = 0
    for case_id, case in parents.items():
        record = records[case_id]
        first = int(case["first_word"])
        second = int(case["second_word"])
        orbit_words: dict[tuple[int, int, int, int], list[int]] = {}
        candidates = []
        for word in range(1 << length):
            if not is_candidate(word, case, length):
                continue
            candidates.append(word)
            key = tuple(descriptor(word, first, second, length))
            orbit_words.setdefault(key, []).append(word)

        expected = []
        earlier = 0
        for key in sorted(orbit_words):
            words = orbit_words[key]
            values = list(key)
            canonical = representative(
                values,
                first,
                second,
                length,
            )
            if canonical not in words:
                raise SystemExit(f"{case_id}: invalid representative")
            expected.append(
                {
                    "descriptor": values,
                    "canonical_word": canonical,
                    "orbit_size": len(words),
                    "earlier_word_count": earlier,
                }
            )
            earlier += len(words)
        if record["orbits"] != expected:
            raise SystemExit(f"{case_id}: orbit list is incorrect")
        if record["candidate_word_count"] != len(candidates):
            raise SystemExit(f"{case_id}: candidate count is incorrect")
        if record["orbit_count"] != len(expected):
            raise SystemExit(f"{case_id}: orbit count is incorrect")
        if record["stabilizer_cell_sizes"] != [
            weight(mask) for mask in masks(first, second, length)
        ]:
            raise SystemExit(f"{case_id}: stabilizer cells are incorrect")
        if record["orbit_manifest_sha256"] != digest(expected):
            raise SystemExit(f"{case_id}: orbit digest is incorrect")
        total_orbits += len(expected)

    if third_manifest["parent_case_count"] != len(parents):
        raise SystemExit("parent count is inconsistent")
    if third_manifest["third_orbit_count"] != total_orbits:
        raise SystemExit("third-orbit count is inconsistent")
    print(
        json.dumps(
            {
                "parent_case_count": len(parents),
                "third_orbit_count": total_orbits,
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
