#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
from pathlib import Path


def choose(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


def shell_coefficient(distance: int, shell: int) -> int:
    return sum(
        choose(distance, overlap)
        * choose(11 - distance, shell - overlap)
        for overlap in range(12)
        if distance + shell - 2 * overlap <= 3
    )


def krawtchouk(degree: int, distance: int) -> int:
    return sum(
        (-1) ** overlap
        * choose(distance, overlap)
        * choose(11 - distance, degree - overlap)
        for overlap in range(degree + 1)
    )


def ball_intersection(distance: int) -> int:
    other = (1 << distance) - 1
    return sum(
        1
        for word in range(1 << 11)
        if bin(word).count("1") <= 3
        and bin(word ^ other).count("1") <= 3
    )


def row_system() -> dict[str, tuple[list[int], int]]:
    rows: dict[str, tuple[list[int], int]] = {
        "pairs": ([1] * 11, 105),
    }
    for shell in range(4, 12):
        rows[f"shell_{shell}"] = (
            [
                2 * shell_coefficient(distance, shell)
                for distance in range(1, 12)
            ],
            15 * choose(11, shell),
        )
    for degree in range(1, 12):
        rows[f"delsarte_{degree}"] = (
            [
                2 * krawtchouk(degree, distance)
                for distance in range(1, 12)
            ],
            -14 * choose(11, degree),
        )
    return rows


def certify(
    name: str,
    objective: list[int],
    multipliers: dict[str, Fraction],
    rows: dict[str, tuple[list[int], int]],
) -> dict[str, object]:
    combined = [Fraction(0) for _ in objective]
    lower_bound = Fraction(0)
    for row_name, multiplier in multipliers.items():
        coefficients, bound = rows[row_name]
        lower_bound += multiplier * bound
        for index, coefficient in enumerate(coefficients):
            combined[index] += multiplier * coefficient
    if any(
        coefficient > target
        for coefficient, target in zip(combined, objective)
    ):
        raise RuntimeError(f"{name}: dual exceeds the objective")
    rounded = math.ceil(lower_bound)
    return {
        "name": name,
        "multipliers": {
            row: str(value)
            for row, value in multipliers.items()
        },
        "combined_coefficients": [
            str(value)
            for value in combined
        ],
        "objective_coefficients": objective,
        "rational_lower_bound": str(lower_bound),
        "integral_lower_bound": rounded,
        "valid": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    rows = row_system()
    pair_intersections = {
        str(distance): ball_intersection(distance)
        for distance in range(1, 12)
    }
    expected_intersections = {
        "1": 112,
        "2": 112,
        "3": 56,
        "4": 56,
        "5": 20,
        "6": 20,
        "7": 0,
        "8": 0,
        "9": 0,
        "10": 0,
        "11": 0,
    }
    if pair_intersections != expected_intersections:
        raise RuntimeError("radius-3 ball intersections changed")

    certificates = [
        certify(
            "pairs_at_distance_at_most_6",
            [
                int(distance <= 6)
                for distance in range(1, 12)
            ],
            {
                "pairs": Fraction(1, 3),
                "delsarte_1": Fraction(1, 24),
                "delsarte_11": Fraction(1, 24),
            },
            rows,
        ),
        certify(
            "pairs_at_distance_at_most_5",
            [
                int(distance <= 5)
                for distance in range(1, 12)
            ],
            {
                "pairs": Fraction(37, 615),
                "shell_4": Fraction(1, 410),
                "shell_11": Fraction(11, 82),
                "delsarte_1": Fraction(33, 820),
                "delsarte_9": Fraction(13, 2460),
            },
            rows,
        ),
    ]
    if certificates[0]["integral_lower_bound"] != 28:
        raise RuntimeError("distance-at-most-6 bound changed")
    if certificates[1]["integral_lower_bound"] != 11:
        raise RuntimeError("distance-at-most-5 bound changed")

    report = {
        "problem": {
            "length": 11,
            "radius": 3,
            "code_size": 15,
        },
        "pair_intersection_sizes": pair_intersections,
        "row_semantics": {
            "pairs": "sum of all unordered pair counts equals 105",
            "shell": "summed coverage of each distance shell",
            "delsarte": (
                "parity-refined binary Krawtchouk lower inequality"
            ),
        },
        "certificates": certificates,
        "conclusions": {
            "pairs_at_distance_at_most_6": 28,
            "pairs_at_distance_at_most_5": 11,
            "minimum_pair_distance_at_most": 5,
        },
        "consequence": (
            "every hypothetical cover has at least 11 pairs at distance "
            "at most 5, so its minimum distance is at most 5"
        ),
        "valid": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
