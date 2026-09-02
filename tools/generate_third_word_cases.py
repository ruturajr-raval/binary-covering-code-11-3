#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from third_word_symmetry import (
    canonical_word,
    coordinate_masks,
    orbit_manifest_digest,
    third_orbits,
    weight,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    parent_manifest = json.loads(
        args.parent_manifest.read_text(encoding="ascii")
    )
    length = int(parent_manifest["length"])
    parents = []
    total_orbits = 0
    for case in parent_manifest["cases"]:
        first_word = int(case["first_word"])
        second_word = int(case["second_word"])
        earlier_word_count = 0
        orbit_records = []
        for descriptor, words in third_orbits(case, length=length):
            representative = canonical_word(
                descriptor,
                first_word=first_word,
                second_word=second_word,
                length=length,
            )
            if representative not in words:
                raise RuntimeError("canonical word is outside its orbit")
            orbit_records.append(
                {
                    "descriptor": list(descriptor),
                    "canonical_word": representative,
                    "orbit_size": len(words),
                    "earlier_word_count": earlier_word_count,
                }
            )
            earlier_word_count += len(words)
        if not orbit_records:
            raise RuntimeError(f"{case['case_id']}: no third-word orbit")
        masks = coordinate_masks(
            first_word,
            second_word,
            length=length,
        )
        parents.append(
            {
                "parent_case_id": case["case_id"],
                "minimum_distance": case["minimum_weight"],
                "first_word": first_word,
                "second_word": second_word,
                "stabilizer_cell_sizes": [weight(mask) for mask in masks],
                "candidate_word_count": earlier_word_count,
                "orbit_count": len(orbit_records),
                "orbit_manifest_sha256": orbit_manifest_digest(
                    orbit_records
                ),
                "orbits": orbit_records,
            }
        )
        total_orbits += len(orbit_records)

    report = {
        "length": length,
        "source_parent_manifest": str(args.parent_manifest),
        "source_parent_manifest_sha256": hashlib.sha256(
            args.parent_manifest.read_bytes()
        ).hexdigest(),
        "parent_case_count": len(parents),
        "third_orbit_count": total_orbits,
        "descriptor_order": [
            "inside_both_fixed_words",
            "inside_first_only",
            "inside_second_only",
            "inside_neither",
        ],
        "completeness_argument": "docs/THIRD_WORD_SYMMETRY.md",
        "parents": parents,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "parent_case_count": len(parents),
                "third_orbit_count": total_orbits,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
