#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


def build_profile(
    case: dict[str, object],
    *,
    length: int,
    radius: int,
    size: int,
) -> tuple[
    list[tuple[int, int]],
    list[int],
    dict[str, tuple[list[int], int | None, int | None]],
]:
    first_size = int(case["minimum_weight"])
    outside_size = length - first_size
    descriptor_payload = case["second_descriptor"]
    descriptor = (
        int(descriptor_payload["weight"]),
        int(descriptor_payload["intersection"]),
    )
    keys = [
        (inside, outside)
        for inside in range(first_size + 1)
        for outside in range(outside_size + 1)
    ]
    upper_bounds = [
        math.comb(first_size, inside)
        * math.comb(outside_size, outside)
        for inside, outside in keys
    ]
    rows: dict[str, tuple[list[int], int | None, int | None]] = {}

    def add(
        name: str,
        coefficients: list[int],
        lower: int | None,
        upper: int | None,
    ) -> None:
        if name in rows:
            raise ValueError("duplicate row name")
        rows[name] = (coefficients, lower, upper)

    add("size", [1] * len(keys), size, size)
    add("zero", [int(key == (0, 0)) for key in keys], 1, 1)
    add(
        "first",
        [int(key == (first_size, 0)) for key in keys],
        1,
        1,
    )
    for index, key in enumerate(keys):
        orbit_descriptor = (sum(key), key[0])
        if key in {(0, 0), (first_size, 0)}:
            continue
        if sum(key) < first_size or orbit_descriptor < descriptor:
            coefficients = [0] * len(keys)
            coefficients[index] = 1
            add(f"forbid_{key[0]}_{key[1]}", coefficients, 0, 0)
    second_key = (descriptor[1], descriptor[0] - descriptor[1])
    add(
        "second",
        [int(key == second_key) for key in keys],
        1,
        None,
    )
    for target_inside in range(first_size + 1):
        for target_outside in range(outside_size + 1):
            add(
                f"cover_{target_inside}_{target_outside}",
                [
                    incidence(
                        first_size,
                        center_inside,
                        center_outside,
                        target_inside,
                        target_outside,
                        length,
                        radius,
                    )
                    for center_inside, center_outside in keys
                ],
                (
                    math.comb(first_size, target_inside)
                    * math.comb(outside_size, target_outside)
                ),
                None,
            )
    return keys, upper_bounds, rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_manifest", type=Path)
    parser.add_argument("certificates", type=Path)
    args = parser.parse_args()

    manifest = json.loads(
        args.case_manifest.read_text(encoding="ascii")
    )
    payload = json.loads(
        args.certificates.read_text(encoding="ascii")
    )
    length = payload["problem"]["length"]
    radius = payload["problem"]["radius"]
    size = payload["problem"]["size"]
    cases = {case["case_id"]: case for case in manifest["cases"]}
    certificates = {
        certificate["case_id"]: certificate
        for certificate in payload["certificates"]
    }
    if set(cases) != set(certificates):
        raise SystemExit("certificate case set does not match the manifest")

    counts: dict[str, int] = {}
    for case_id, case in cases.items():
        keys, upper_bounds, rows = build_profile(
            case,
            length=length,
            radius=radius,
            size=size,
        )
        certificate = certificates[case_id]
        status = certificate["status"]
        counts[status] = counts.get(status, 0) + 1
        if status == "LP_INFEASIBLE":
            combined = [0] * len(keys)
            required = 0
            seen_rows = set()
            for entry in certificate["multipliers"]:
                name = entry["row"]
                multiplier = int(entry["value"])
                if name in seen_rows or name not in rows:
                    raise SystemExit(f"{case_id}: invalid dual row")
                seen_rows.add(name)
                coefficients, lower, upper = rows[name]
                bound = lower if multiplier > 0 else upper
                if multiplier == 0 or bound is None:
                    raise SystemExit(f"{case_id}: invalid dual multiplier")
                required += multiplier * bound
                for index, coefficient in enumerate(coefficients):
                    combined[index] += multiplier * coefficient
            maximum = sum(
                coefficient * upper
                for coefficient, upper in zip(combined, upper_bounds)
                if coefficient > 0
            )
            if maximum >= required:
                raise SystemExit(f"{case_id}: dual contradiction failed")
            if required != certificate["required_lower_bound"]:
                raise SystemExit(f"{case_id}: dual lower bound changed")
            if maximum != certificate["maximum_over_variable_bounds"]:
                raise SystemExit(f"{case_id}: dual maximum changed")
            if required - maximum != certificate["contradiction_margin"]:
                raise SystemExit(f"{case_id}: dual margin changed")
        elif status == "LP_FEASIBLE":
            values = {key: Fraction(0) for key in keys}
            for entry in certificate["nonzero_profile"]:
                key = (int(entry["inside"]), int(entry["outside"]))
                if key not in values or values[key] != 0:
                    raise SystemExit(f"{case_id}: invalid primal key")
                values[key] = Fraction(entry["value"])
            vector = [values[key] for key in keys]
            for value, upper in zip(vector, upper_bounds):
                if value < 0 or value > upper:
                    raise SystemExit(f"{case_id}: primal bound failed")
            for name, (coefficients, lower, upper) in rows.items():
                activity = sum(
                    value * coefficient
                    for value, coefficient in zip(vector, coefficients)
                )
                if lower is not None and activity < lower:
                    raise SystemExit(
                        f"{case_id}: lower row {name} failed"
                    )
                if upper is not None and activity > upper:
                    raise SystemExit(
                        f"{case_id}: upper row {name} failed"
                    )
        else:
            raise SystemExit(f"{case_id}: unknown certificate status")

    if counts != payload["status_counts"]:
        raise SystemExit("certificate status counts changed")
    print(
        json.dumps(
            {
                "case_count": len(cases),
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
