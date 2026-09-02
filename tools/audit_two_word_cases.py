#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def weight(word: int) -> int:
    return bin(word).count("1")


def unit_digest(units: list[int]) -> str:
    text = "".join(f"{literal}\n" for literal in units)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    length = manifest["length"]
    ambient_size = 1 << length
    expected_cases = []

    for minimum_weight in range(
        1,
        manifest["maximum_minimum_weight"] + 1,
    ):
        first_word = (1 << minimum_weight) - 1
        orbit_words: dict[tuple[int, int], list[int]] = {}
        for word in range(1, ambient_size):
            word_weight = weight(word)
            if word == first_word or word_weight < minimum_weight:
                continue
            descriptor = (
                word_weight,
                weight(word & first_word),
            )
            orbit_words.setdefault(descriptor, []).append(word)

        descriptors = sorted(orbit_words)
        lower_weight_words = [
            word
            for word in range(1, ambient_size)
            if weight(word) < minimum_weight
        ]
        for descriptor_index, descriptor in enumerate(descriptors):
            word_weight, intersection = descriptor
            outside = word_weight - intersection
            second_word = (
                (1 << intersection) - 1
            ) | (((1 << outside) - 1) << minimum_weight)
            earlier = set(descriptors[:descriptor_index])
            earlier_words = [
                word
                for word in range(1, ambient_size)
                if word != first_word
                and weight(word) >= minimum_weight
                and (
                    weight(word),
                    weight(word & first_word),
                ) in earlier
            ]
            units = (
                [-(word + 1) for word in lower_weight_words]
                + [first_word + 1]
                + [-(word + 1) for word in earlier_words]
                + [second_word + 1]
            )
            expected_cases.append(
                {
                    "case_id": (
                        f"w{minimum_weight}-"
                        f"weight{word_weight}-"
                        f"intersection{intersection}"
                    ),
                    "minimum_weight": minimum_weight,
                    "first_word": first_word,
                    "second_descriptor": {
                        "weight": word_weight,
                        "intersection": intersection,
                    },
                    "second_word": second_word,
                    "forbidden_earlier_orbit_words": len(earlier_words),
                    "unit_count": len(units),
                    "unit_sha256": unit_digest(units),
                }
            )

    if manifest["cases"] != expected_cases:
        raise SystemExit("two-word case manifest does not match reconstruction")
    if manifest["case_count"] != len(expected_cases):
        raise SystemExit("two-word case count is inconsistent")

    report = {
        "manifest": str(args.manifest),
        "case_count": len(expected_cases),
        "minimum_weights": sorted(
            {case["minimum_weight"] for case in expected_cases}
        ),
        "valid": True,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
