#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from verify_distance_distribution_bounds import (
    ball_intersection,
    row_system,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    rows = row_system()
    objective = [
        ball_intersection(distance)
        for distance in range(1, 12)
    ]
    expected_objective = [112, 112, 56, 56, 20, 20, 0, 0, 0, 0, 0]
    if objective != expected_objective:
        raise RuntimeError("pair-overlap coefficients changed")

    pair_coefficients, pair_bound = rows["pairs"]
    shell_10_coefficients, shell_10_bound = rows["shell_10"]
    shell_11_coefficients, shell_11_bound = rows["shell_11"]
    delsarte_1_coefficients, delsarte_1_bound = rows["delsarte_1"]
    delsarte_11_coefficients, delsarte_11_bound = rows["delsarte_11"]
    if pair_bound != 105:
        raise RuntimeError("pair count changed")
    if any(coefficient % 2 for coefficient in shell_10_coefficients):
        raise RuntimeError("shell-10 row is not even-valued")
    if any(coefficient % 2 for coefficient in shell_11_coefficients):
        raise RuntimeError("shell-11 row is not even-valued")
    if any(coefficient % 2 for coefficient in delsarte_1_coefficients):
        raise RuntimeError("Delsarte-1 row is not even-valued")
    if any(coefficient % 2 for coefficient in delsarte_11_coefficients):
        raise RuntimeError("Delsarte-11 row is not even-valued")

    j10_coefficients = [
        coefficient // 2
        for coefficient in shell_10_coefficients
    ]
    j11_coefficients = [
        coefficient // 2
        for coefficient in shell_11_coefficients
    ]
    d1_coefficients = [
        coefficient // 2
        for coefficient in delsarte_1_coefficients
    ]
    d11_coefficients = [
        coefficient // 2
        for coefficient in delsarte_11_coefficients
    ]
    j10_bound = math.ceil(shell_10_bound / 2)
    j11_bound = math.ceil(shell_11_bound / 2)
    d1_bound = delsarte_1_bound // 2
    d11_bound = delsarte_11_bound // 2
    expected_rows = {
        "J10": ([0, 0, 0, 0, 0, 0, 4, 3, 11, 11, 11], 83),
        "J11": ([0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1], 8),
        "D1": ([9, 7, 5, 3, 1, -1, -3, -5, -7, -9, -11], -77),
        "D11": ([-1, 1, -1, 1, -1, 1, -1, 1, -1, 1, -1], -7),
    }
    actual_rows = {
        "J10": (j10_coefficients, j10_bound),
        "J11": (j11_coefficients, j11_bound),
        "D1": (d1_coefficients, d1_bound),
        "D11": (d11_coefficients, d11_bound),
    }
    if actual_rows != expected_rows:
        raise RuntimeError("normalized overlap rows changed")

    identity_multipliers = {
        "P": 20,
        "J10": 4,
        "J11": 4,
        "D1": 9,
        "D11": 9,
    }
    combined = [
        identity_multipliers["P"] * pair
        + identity_multipliers["J10"] * j10
        + identity_multipliers["J11"] * j11
        + identity_multipliers["D1"] * d1
        + identity_multipliers["D11"] * d11
        for pair, j10, j11, d1, d11 in zip(
            pair_coefficients,
            j10_coefficients,
            j11_coefficients,
            d1_coefficients,
            d11_coefficients,
        )
    ]
    base_bound = (
        identity_multipliers["P"] * pair_bound
        + identity_multipliers["J10"] * j10_bound
        + identity_multipliers["J11"] * j11_bound
        + identity_multipliers["D1"] * d1_bound
        + identity_multipliers["D11"] * d11_bound
    )
    residual = [
        target - coefficient
        for target, coefficient in zip(objective, combined)
    ]
    expected_residual = [
        20,
        20,
        0,
        0,
        0,
        0,
        0,
        0,
        4,
        4,
        40,
    ]
    if base_bound != 1708 or residual != expected_residual:
        raise RuntimeError("overlap dual identity changed")

    if any(
        (left + right) % 4
        for left, right in zip(j10_coefficients, j11_coefficients)
    ):
        raise RuntimeError("J10 + J11 is not coefficientwise divisible by 4")
    slack_residue = (-(j10_bound + j11_bound)) % 4
    if slack_residue != 1:
        raise RuntimeError("shell slack residue changed")

    sharp_distributions = [
        [0, 0, 0, 2, 41, 39, 15, 8, 0, 0, 0],
        [0, 0, 0, 2, 42, 38, 14, 9, 0, 0, 0],
        [0, 0, 1, 1, 40, 40, 15, 8, 0, 0, 0],
    ]
    sharp_records = []
    for distribution in sharp_distributions:
        if sum(distribution) != 105:
            raise RuntimeError(
                "sharp distribution has the wrong pair count"
            )
        row_values = {}
        for row_name, (coefficients, bound) in rows.items():
            value = sum(
                coefficient * count
                for coefficient, count in zip(
                    coefficients,
                    distribution,
                )
            )
            row_values[row_name] = value
            if row_name == "pairs":
                if value != bound:
                    raise RuntimeError(
                        "sharp distribution violates pair equality"
                    )
            elif value < bound:
                raise RuntimeError(
                    f"sharp distribution violates {row_name}"
                )
        sharp_objective = sum(
            coefficient * count
            for coefficient, count in zip(
                objective,
                distribution,
            )
        )
        if sharp_objective != 1712:
            raise RuntimeError("sharp distribution objective changed")
        sharp_records.append(
            {
                "distance_distribution": {
                    str(distance): count
                    for distance, count in enumerate(
                        distribution,
                        start=1,
                    )
                },
                "objective": sharp_objective,
                "all_rows_satisfied": True,
                "row_values": row_values,
            }
        )

    ball_size = sum(math.comb(11, weight) for weight in range(4))
    incidence_excess = 15 * ball_size - 2**11
    if ball_size != 232 or incidence_excess != 1432:
        raise RuntimeError("cover incidence excess changed")
    for multiplicity in range(1, 16):
        if math.comb(multiplicity, 3) < (
            math.comb(multiplicity, 2) - (multiplicity - 1)
        ):
            raise RuntimeError("pointwise triple-overlap inequality failed")
    triple_overlap_lower_bound = 1712 - incidence_excess
    if triple_overlap_lower_bound != 280:
        raise RuntimeError("triple-overlap lower bound changed")

    report = {
        "problem": {
            "length": 11,
            "radius": 3,
            "code_size": 15,
        },
        "definition": (
            "O is the sum, over unordered codeword pairs, of the "
            "intersection size of their radius-3 Hamming balls"
        ),
        "objective_coefficients_by_distance": {
            str(distance): coefficient
            for distance, coefficient in enumerate(objective, start=1)
        },
        "integer_identity": {
            "normalized_rows": {
                name: {
                    "coefficients": coefficients,
                    "lower_bound": bound,
                }
                for name, (coefficients, bound) in actual_rows.items()
            },
            "multipliers": identity_multipliers,
            "combined_coefficients": combined,
            "residual_coefficients": residual,
            "base_bound": base_bound,
            "identity": (
                "O = 20P + 4J10 + 4J11 + 9D1 + 9D11 + "
                "20(p1+p2) + 4(p9+p10) + 40p11"
            ),
        },
        "modular_refinement": {
            "J10_slack": "u = J10 - 83",
            "J11_slack": "v = J11 - 8",
            "slack_congruence": "u + v is congruent to 1 modulo 4",
            "minimum_slack_sum": 1,
            "objective_divisor": math.gcd(*objective),
            "integral_lower_bound": 1712,
            "strengthened_inequality": (
                "O >= 1712 + 20(p1+p2) + 4(p9+p10) + 40p11"
            ),
            "equivalent_distance_inequality": (
                "23(p1+p2) + 14(p3+p4) + 5(p5+p6) - "
                "(p9+p10) - 10p11 >= 428"
            ),
        },
        "sharp_for_retained_row_system": {
            "witness_count": len(sharp_records),
            "witnesses": sharp_records,
        },
        "triple_overlap_consequence": {
            "definition": (
                "T is the sum, over unordered triples of codewords, of "
                "the size of the common intersection of their radius-3 "
                "Hamming balls"
            ),
            "ball_size": ball_size,
            "total_incidence_excess": incidence_excess,
            "pointwise_inequality": (
                "C(m,3) >= C(m,2) - (m-1) for every m >= 1"
            ),
            "lower_bound": triple_overlap_lower_bound,
        },
        "conclusion": (
            "every hypothetical 15-word radius-3 cover has total pair-ball "
            "overlap at least 1712 and total triple-ball overlap at least 280"
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
