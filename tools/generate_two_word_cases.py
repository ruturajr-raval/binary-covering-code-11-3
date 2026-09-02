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
    parser.add_argument("output", type=Path)
    parser.add_argument("--length", type=int, default=11)
    parser.add_argument("--maximum-minimum-weight", type=int, default=6)
    args = parser.parse_args()

    cases = []
    ambient_size = 1 << args.length
    for minimum_weight in range(
        1,
        args.maximum_minimum_weight + 1,
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
        for descriptor_index, descriptor in enumerate(descriptors):
            word_weight, intersection = descriptor
            outside = word_weight - intersection
            second_word = (
                (1 << intersection) - 1
            ) | (((1 << outside) - 1) << minimum_weight)
            if second_word not in orbit_words[descriptor]:
                raise RuntimeError("canonical second word is outside its orbit")

            units = [
                -(word + 1)
                for word in range(1, ambient_size)
                if weight(word) < minimum_weight
            ]
            units.append(first_word + 1)
            earlier = set(descriptors[:descriptor_index])
            units.extend(
                -(word + 1)
                for word in range(1, ambient_size)
                if word != first_word
                and weight(word) >= minimum_weight
                and (
                    weight(word),
                    weight(word & first_word),
                ) in earlier
            )
            units.append(second_word + 1)

            cases.append(
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
                    "forbidden_earlier_orbit_words": (
                        len(units) - 2 -
                        sum(
                            1
                            for word in range(1, ambient_size)
                            if weight(word) < minimum_weight
                        )
                    ),
                    "unit_count": len(units),
                    "unit_sha256": unit_digest(units),
                }
            )

    manifest = {
        "length": args.length,
        "maximum_minimum_weight": args.maximum_minimum_weight,
        "descriptor_order": [
            "weight",
            "intersection_with_first_word",
        ],
        "case_count": len(cases),
        "completeness_argument": "docs/TWO_WORD_CASES.md",
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "case_count": len(cases),
                "minimum_weights": list(
                    range(1, args.maximum_minimum_weight + 1)
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
