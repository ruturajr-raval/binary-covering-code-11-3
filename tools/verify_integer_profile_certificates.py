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
            distance = (
                center_inside
                + target_inside
                - 2 * inside_overlap
                + center_outside
                + target_outside
                - 2 * outside_overlap
            )
            if distance <= radius:
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


def residual_model(
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

    candidates = []
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
            candidates.append((key, capacity, coefficients, score))
    candidates.sort(key=lambda item: (-item[3], item[0]))
    return (
        [item[0] for item in candidates],
        [item[1] for item in candidates],
        [item[2] for item in candidates],
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


def verify_trace(
    trace: dict[str, object],
    capacities: list[int],
    coefficients: list[list[int]],
    requirements: list[int],
) -> int:
    leaves = {
        tuple(entry[0]): entry[1]
        for entry in trace["leaves"]
    }
    if len(leaves) != len(trace["leaves"]):
        raise ValueError("trace contains duplicate prefixes")
    suffix_capacity = [0] * (len(capacities) + 1)
    for index in range(len(capacities) - 1, -1, -1):
        suffix_capacity[index] = (
            suffix_capacity[index + 1] + capacities[index]
        )
    visited_leaves = set()
    nodes = 0

    def visit(
        prefix: tuple[int, ...],
        remaining: int,
        coverage: list[int],
    ) -> None:
        nonlocal nodes
        nodes += 1
        index = len(prefix)
        if prefix in leaves:
            reason = leaves[prefix]
            if reason == "capacity":
                if suffix_capacity[index] >= remaining:
                    raise ValueError("invalid capacity prune")
            else:
                target = int(reason)
                possible = maximum_remaining(
                    coefficients,
                    capacities,
                    index,
                    target,
                    remaining,
                )
                if coverage[target] + possible >= requirements[target]:
                    raise ValueError("invalid coverage prune")
            visited_leaves.add(prefix)
            return
        if index == len(capacities):
            raise ValueError("uncovered complete assignment in trace")
        for value in range(
            min(capacities[index], remaining),
            -1,
            -1,
        ):
            visit(
                prefix + (value,),
                remaining - value,
                [
                    current + value * coefficient
                    for current, coefficient in zip(
                        coverage,
                        coefficients[index],
                    )
                ],
            )

    visit((), 12, [0] * len(requirements))
    if visited_leaves != set(leaves):
        raise ValueError("trace contains unreachable leaves")
    return nodes


def verify_profile(
    case: dict[str, object],
    profile_entries: list[dict[str, object]],
    *,
    length: int,
    radius: int,
) -> None:
    first_size = int(case["minimum_weight"])
    outside_size = length - first_size
    profile = {
        (int(entry["inside"]), int(entry["outside"])): int(entry["value"])
        for entry in profile_entries
    }
    if sum(profile.values()) != 15:
        raise ValueError("integer profile has the wrong total size")
    if profile.get((0, 0)) != 1:
        raise ValueError("integer profile does not fix zero")
    if profile.get((first_size, 0)) != 1:
        raise ValueError("integer profile does not fix the first word")
    descriptor_payload = case["second_descriptor"]
    descriptor = (
        int(descriptor_payload["weight"]),
        int(descriptor_payload["intersection"]),
    )
    second = (descriptor[1], descriptor[0] - descriptor[1])
    if profile.get(second, 0) < 1:
        raise ValueError("integer profile misses the second orbit")

    for inside in range(first_size + 1):
        for outside in range(outside_size + 1):
            key = (inside, outside)
            value = profile.get(key, 0)
            capacity = (
                math.comb(first_size, inside)
                * math.comb(outside_size, outside)
            )
            if value < 0 or value > capacity:
                raise ValueError("integer profile violates an orbit bound")
            orbit_descriptor = (inside + outside, inside)
            if (
                key not in {(0, 0), (first_size, 0)}
                and (
                    inside + outside < first_size
                    or orbit_descriptor < descriptor
                )
                and value != 0
            ):
                raise ValueError("integer profile uses a forbidden orbit")

    for target_inside in range(first_size + 1):
        for target_outside in range(outside_size + 1):
            coverage = sum(
                value
                * incidence(
                    first_size,
                    inside,
                    outside,
                    target_inside,
                    target_outside,
                    length,
                    radius,
                )
                for (inside, outside), value in profile.items()
            )
            required = (
                math.comb(first_size, target_inside)
                * math.comb(outside_size, target_outside)
            )
            if coverage < required:
                raise ValueError(
                    "integer profile violates averaged coverage"
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_manifest", type=Path)
    parser.add_argument("certificate_manifest", type=Path)
    args = parser.parse_args()

    cases_payload = json.loads(
        args.case_manifest.read_text(encoding="ascii")
    )
    payload = json.loads(
        args.certificate_manifest.read_text(encoding="ascii")
    )
    cases = {
        case["case_id"]: case
        for case in cases_payload["cases"]
    }
    counts: dict[str, int] = {}
    for certificate in payload["certificates"]:
        case_id = certificate["case_id"]
        case = cases[case_id]
        status = certificate["status"]
        counts[status] = counts.get(status, 0) + 1
        if status == "INTEGER_FEASIBLE":
            verify_profile(
                case,
                certificate["profile"],
                length=payload["problem"]["length"],
                radius=payload["problem"]["radius"],
            )
            continue

        trace_path = Path(certificate["trace"])
        trace_bytes = trace_path.read_bytes()
        if hashlib.sha256(trace_bytes).hexdigest() != certificate["trace_sha256"]:
            raise SystemExit(f"{case_id}: trace hash mismatch")
        trace = json.loads(gzip.decompress(trace_bytes).decode("ascii"))
        (
            variables,
            capacities,
            coefficients,
            requirements,
            _,
        ) = residual_model(
            case,
            length=payload["problem"]["length"],
            radius=payload["problem"]["radius"],
        )
        expected_variables = [
            (
                int(entry["inside"]),
                int(entry["outside"]),
                int(entry["capacity"]),
            )
            for entry in trace["variables"]
        ]
        if expected_variables != [
            (key[0], key[1], capacity)
            for key, capacity in zip(variables, capacities)
        ]:
            raise SystemExit(f"{case_id}: trace variable order changed")
        if trace["requirements"] != requirements:
            raise SystemExit(f"{case_id}: trace requirements changed")
        nodes = verify_trace(
            trace,
            capacities,
            coefficients,
            requirements,
        )
        if nodes != certificate["search_nodes"]:
            raise SystemExit(f"{case_id}: search node count changed")
        if len(trace["leaves"]) != certificate["trace_leaves"]:
            raise SystemExit(f"{case_id}: trace leaf count changed")

    if counts != payload["status_counts"]:
        raise SystemExit("integer profile status counts changed")
    print(
        json.dumps(
            {
                "status_counts": counts,
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
