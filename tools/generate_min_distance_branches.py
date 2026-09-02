#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from audit_covering_cnf import read_dimacs


def dimacs_text(variable_count: int, clauses: list[tuple[int, ...]]) -> str:
    lines = [f"p cnf {variable_count} {len(clauses)}"]
    lines.extend(
        " ".join(str(literal) for literal in clause) + " 0"
        for clause in clauses
    )
    return "\n".join(lines) + "\n"


def minimum_distance_clauses(
    *,
    length: int,
    minimum_distance: int,
) -> list[tuple[int, int]]:
    ambient_size = 1 << length
    clauses = []
    for left in range(ambient_size):
        for offset in range(1, ambient_size):
            if bin(offset).count("1") >= minimum_distance:
                continue
            right = left ^ offset
            if left < right:
                clauses.append((-(left + 1), -(right + 1)))
    return clauses


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_formula", type=Path)
    parser.add_argument("distance_bounds", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--length", type=int, default=11)
    parser.add_argument("--radius", type=int, default=3)
    parser.add_argument("--size", type=int, default=15)
    args = parser.parse_args()

    base_variables, base_clauses, base_sha256 = read_dimacs(
        args.base_formula
    )
    distance_bounds = json.loads(
        args.distance_bounds.read_text(encoding="ascii")
    )
    maximum_minimum_distance = int(
        distance_bounds["conclusions"]["minimum_pair_distance_at_most"]
    )
    if maximum_minimum_distance != 5:
        raise SystemExit(
            "distance-bound evidence does not certify the expected limit 5"
        )
    if distance_bounds["problem"] != {
        "code_size": args.size,
        "length": args.length,
        "radius": args.radius,
    }:
        raise SystemExit("distance-bound parameters do not match the formula")

    args.output_directory.mkdir(parents=True, exist_ok=True)
    cases = []
    for minimum_distance in range(1, maximum_minimum_distance + 1):
        canonical_word = (1 << minimum_distance) - 1
        pair_clauses = minimum_distance_clauses(
            length=args.length,
            minimum_distance=minimum_distance,
        )
        expected_pair_count = (1 << (args.length - 1)) * sum(
            math.comb(args.length, distance)
            for distance in range(1, minimum_distance)
        )
        if len(pair_clauses) != expected_pair_count:
            raise RuntimeError("forbidden-pair count is inconsistent")

        clauses = list(base_clauses)
        clauses.extend(pair_clauses)
        clauses.append((canonical_word + 1,))
        text = dimacs_text(base_variables, clauses)
        output = (
            args.output_directory
            / (
                f"k2-{args.length}-{args.radius}-atmost{args.size}-"
                f"mindistance{minimum_distance}.cnf"
            )
        )
        output.write_text(text, encoding="ascii")
        cases.append(
            {
                "minimum_distance": minimum_distance,
                "canonical_pair": [0, canonical_word],
                "forbidden_pair_clauses": len(pair_clauses),
                "variables": base_variables,
                "clauses": len(clauses),
                "formula": str(output),
                "sha256": hashlib.sha256(
                    text.encode("ascii")
                ).hexdigest(),
            }
        )

    manifest = {
        "problem": {
            "q": 2,
            "length": args.length,
            "radius": args.radius,
            "size": args.size,
        },
        "base_formula": str(args.base_formula),
        "base_formula_sha256": base_sha256,
        "base_variables": base_variables,
        "base_clauses": len(base_clauses),
        "distance_bounds": str(args.distance_bounds),
        "distance_bounds_sha256": hashlib.sha256(
            args.distance_bounds.read_bytes()
        ).hexdigest(),
        "maximum_minimum_distance": maximum_minimum_distance,
        "case_rule": (
            "translate a globally closest pair to include zero, permute the "
            "other endpoint to 2^d-1, and forbid every selected pair at "
            "distance below d"
        ),
        "completeness_argument": "docs/MINIMUM_DISTANCE_BRANCHES.md",
        "cases": cases,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(
        json.dumps(
            {
                "case_count": len(cases),
                "minimum_distances": [
                    case["minimum_distance"] for case in cases
                ],
                "output": str(args.manifest),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
