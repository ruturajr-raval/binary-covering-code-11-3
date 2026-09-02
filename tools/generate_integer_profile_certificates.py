#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path


def incidence(
    first_size: int,
    center_inside: int,
    center_outside: int,
    target_inside: int,
    target_outside: int,
    length: int,
    radius: int,
) -> int:
    outside_size = length - first_size
    total = 0
    for inside_overlap in range(
        max(0, target_inside - (first_size - center_inside)),
        min(center_inside, target_inside) + 1,
    ):
        for outside_overlap in range(
            max(0, target_outside - (outside_size - center_outside)),
            min(center_outside, target_outside) + 1,
        ):
            if (
                center_inside
                + target_inside
                - 2 * inside_overlap
                + center_outside
                + target_outside
                - 2 * outside_overlap
                <= radius
            ):
                total += (
                    math.comb(center_inside, inside_overlap)
                    * math.comb(
                        first_size - center_inside,
                        target_inside - inside_overlap,
                    )
                    * math.comb(center_outside, outside_overlap)
                    * math.comb(
                        outside_size - center_outside,
                        target_outside - outside_overlap,
                    )
                )
    return total


def build_residual(
    case: dict[str, object],
    *,
    length: int,
    radius: int,
) -> tuple[
    list[tuple[int, int]],
    list[int],
    list[list[int]],
    list[int],
    list[tuple[int, int]],
]:
    first_size = int(case["minimum_weight"])
    outside_size = length - first_size
    descriptor_payload = case["second_descriptor"]
    descriptor = (
        int(descriptor_payload["weight"]),
        int(descriptor_payload["intersection"]),
    )
    second = (descriptor[1], descriptor[0] - descriptor[1])
    targets = [
        (inside, outside)
        for inside in range(first_size + 1)
        for outside in range(outside_size + 1)
    ]
    orbit_sizes = [
        math.comb(first_size, inside)
        * math.comb(outside_size, outside)
        for inside, outside in targets
    ]
    fixed = [(0, 0), (first_size, 0), second]
    requirements = [
        orbit_size
        - sum(
            incidence(
                first_size,
                center_inside,
                center_outside,
                target_inside,
                target_outside,
                length,
                radius,
            )
            for center_inside, center_outside in fixed
        )
        for orbit_size, (target_inside, target_outside) in zip(
            orbit_sizes,
            targets,
        )
    ]

    variables = []
    for inside in range(first_size + 1):
        for outside in range(outside_size + 1):
            key = (inside, outside)
            if key in {(0, 0), (first_size, 0)}:
                continue
            orbit_descriptor = (inside + outside, inside)
            if inside + outside < first_size or orbit_descriptor < descriptor:
                continue
            capacity = (
                math.comb(first_size, inside)
                * math.comb(outside_size, outside)
                - int(key == second)
            )
            capacity = min(12, capacity)
            if capacity <= 0:
                continue
            coefficients = [
                incidence(
                    first_size,
                    inside,
                    outside,
                    target_inside,
                    target_outside,
                    length,
                    radius,
                )
                for target_inside, target_outside in targets
            ]
            score = sum(
                Fraction(coefficient, orbit_size)
                for coefficient, orbit_size in zip(
                    coefficients,
                    orbit_sizes,
                )
            )
            variables.append((key, capacity, coefficients, score))
    variables.sort(key=lambda item: (-item[3], item[0]))
    return (
        [item[0] for item in variables],
        [item[1] for item in variables],
        [item[2] for item in variables],
        requirements,
        fixed,
    )


def maximum_remaining(
    coefficients: list[list[int]],
    capacities: list[int],
    start: int,
    target: int,
    slots: int,
) -> int:
    options = sorted(
        (
            (coefficients[index][target], capacities[index])
            for index in range(start, len(capacities))
            if coefficients[index][target] > 0
        ),
        reverse=True,
    )
    total = 0
    for coefficient, capacity in options:
        take = min(slots, capacity)
        total += take * coefficient
        slots -= take
        if slots == 0:
            break
    return total


def search_profile(
    capacities: list[int],
    coefficients: list[list[int]],
    requirements: list[int],
) -> tuple[list[int] | None, list[list[object]], int]:
    suffix_capacity = [0] * (len(capacities) + 1)
    for index in range(len(capacities) - 1, -1, -1):
        suffix_capacity[index] = (
            suffix_capacity[index + 1] + capacities[index]
        )

    leaves: list[list[object]] = []
    nodes = 0

    def visit(
        index: int,
        remaining: int,
        coverage: list[int],
        prefix: list[int],
    ) -> list[int] | None:
        nonlocal nodes
        nodes += 1
        if suffix_capacity[index] < remaining:
            leaves.append([list(prefix), "capacity"])
            return None
        for target, required in enumerate(requirements):
            if coverage[target] >= required:
                continue
            possible = maximum_remaining(
                coefficients,
                capacities,
                index,
                target,
                remaining,
            )
            if coverage[target] + possible < required:
                leaves.append([list(prefix), target])
                return None
        if index == len(capacities):
            if remaining == 0:
                return list(prefix)
            raise RuntimeError("terminal node escaped capacity pruning")

        maximum = min(capacities[index], remaining)
        for value in range(maximum, -1, -1):
            result = visit(
                index + 1,
                remaining - value,
                [
                    current + value * coefficient
                    for current, coefficient in zip(
                        coverage,
                        coefficients[index],
                    )
                ],
                prefix + [value],
            )
            if result is not None:
                return result
        return None

    witness = visit(
        0,
        12,
        [0] * len(requirements),
        [],
    )
    return witness, leaves, nodes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_manifest", type=Path)
    parser.add_argument("lp_certificates", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("output_manifest", type=Path)
    args = parser.parse_args()

    cases_payload = json.loads(
        args.case_manifest.read_text(encoding="ascii")
    )
    lp_payload = json.loads(
        args.lp_certificates.read_text(encoding="ascii")
    )
    length = lp_payload["problem"]["length"]
    radius = lp_payload["problem"]["radius"]
    cases = {
        case["case_id"]: case
        for case in cases_payload["cases"]
    }
    lp_feasible = [
        certificate["case_id"]
        for certificate in lp_payload["certificates"]
        if certificate["status"] == "LP_FEASIBLE"
    ]
    args.output_directory.mkdir(parents=True, exist_ok=True)

    certificates = []
    for case_id in lp_feasible:
        case = cases[case_id]
        (
            variables,
            capacities,
            coefficients,
            requirements,
            fixed,
        ) = build_residual(
            case,
            length=length,
            radius=radius,
        )
        witness, leaves, nodes = search_profile(
            capacities,
            coefficients,
            requirements,
        )
        if witness is not None:
            profile: dict[tuple[int, int], int] = {}
            for key in fixed:
                profile[key] = profile.get(key, 0) + 1
            for key, value in zip(variables, witness):
                profile[key] = profile.get(key, 0) + value
            certificates.append(
                {
                    "case_id": case_id,
                    "status": "INTEGER_FEASIBLE",
                    "profile": [
                        {
                            "inside": key[0],
                            "outside": key[1],
                            "value": value,
                        }
                        for key, value in sorted(profile.items())
                        if value
                    ],
                    "search_nodes": nodes,
                }
            )
            continue

        trace_payload = {
            "case_id": case_id,
            "variables": [
                {
                    "inside": key[0],
                    "outside": key[1],
                    "capacity": capacity,
                }
                for key, capacity in zip(variables, capacities)
            ],
            "requirements": requirements,
            "leaves": leaves,
        }
        trace_bytes = gzip.compress(
            (
                json.dumps(
                    trace_payload,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode("ascii"),
            mtime=0,
        )
        trace_path = args.output_directory / f"{case_id}.json.gz"
        trace_path.write_bytes(trace_bytes)
        certificates.append(
            {
                "case_id": case_id,
                "status": "INTEGER_INFEASIBLE",
                "trace": str(trace_path),
                "trace_sha256": hashlib.sha256(trace_bytes).hexdigest(),
                "trace_leaves": len(leaves),
                "search_nodes": nodes,
            }
        )

    counts: dict[str, int] = {}
    for certificate in certificates:
        status = certificate["status"]
        counts[status] = counts.get(status, 0) + 1
    output = {
        "case_manifest": str(args.case_manifest),
        "lp_certificates": str(args.lp_certificates),
        "problem": {
            "length": length,
            "radius": radius,
            "size": 15,
        },
        "residual_codewords_after_fixed_pair": 12,
        "status_counts": counts,
        "certificates": certificates,
    }
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(json.dumps(counts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
