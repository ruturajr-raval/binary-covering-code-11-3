#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("residual_manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(
        args.residual_manifest.read_text(encoding="ascii")
    )
    eliminated = []
    matching = []
    multiple_neighbor = []
    case_records = []
    for case in manifest["cases"]:
        case_id = case["case_id"]
        minimum_distance = int(case["minimum_weight"])
        second_weight = int(case["second_descriptor"]["weight"])
        intersection = int(case["second_descriptor"]["intersection"])
        first_second_distance = (
            minimum_distance + second_weight - 2 * intersection
        )
        if second_weight == minimum_distance:
            classification = "multiple_neighbor"
            multiple_neighbor.append(case_id)
        elif first_second_distance == minimum_distance:
            classification = "maximum_degree_contradiction"
            eliminated.append(case_id)
        else:
            classification = "matching"
            matching.append(case_id)
        case_records.append(
            {
                "case_id": case_id,
                "minimum_distance": minimum_distance,
                "second_weight": second_weight,
                "first_second_distance": first_second_distance,
                "classification": classification,
            }
        )

    expected_eliminated = [
        "w1-weight2-intersection1",
        "w2-weight4-intersection2",
        "w3-weight4-intersection2",
        "w3-weight6-intersection3",
        "w4-weight6-intersection3",
    ]
    if eliminated != expected_eliminated:
        raise RuntimeError("maximum-degree contradiction cases changed")
    if len(matching) != 34 or len(multiple_neighbor) != 10:
        raise RuntimeError("maximum-degree case counts changed")

    report = {
        "problem": {
            "q": 2,
            "length": 11,
            "radius": 3,
            "target_size": 15,
        },
        "source_residual_manifest": str(args.residual_manifest),
        "source_residual_manifest_sha256": hashlib.sha256(
            args.residual_manifest.read_bytes()
        ).hexdigest(),
        "normalization": (
            "choose a maximum-degree vertex in the minimum-distance graph, "
            "translate it to zero, and map one minimum-distance neighbor to "
            "the canonical first word"
        ),
        "contradiction_rule": (
            "if the canonical second word has weight above the minimum "
            "distance, zero has degree one; if its distance from the first "
            "word equals the minimum distance, the first word has degree at "
            "least two"
        ),
        "counts": {
            "maximum_degree_contradiction": len(eliminated),
            "matching": len(matching),
            "multiple_neighbor": len(multiple_neighbor),
            "total": len(case_records),
        },
        "maximum_degree_contradiction_cases": eliminated,
        "matching_cases": matching,
        "multiple_neighbor_cases": multiple_neighbor,
        "cases": case_records,
        "completeness_argument": "docs/MAXIMUM_DEGREE_NORMALIZATION.md",
        "valid": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(
        json.dumps(
            {
                "counts": report["counts"],
                "eliminated": eliminated,
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
