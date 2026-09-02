#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
from pathlib import Path


def weight(word: int) -> int:
    return bin(word).count("1")


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
        inside_count = (
            math.comb(center_inside, inside_overlap)
            * math.comb(
                first_size - center_inside,
                target_inside - inside_overlap,
            )
        )
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
                    inside_count
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
    list[dict[str, object]],
]:
    first_size = int(case["minimum_weight"])
    outside_size = length - first_size
    descriptor_payload = case["second_descriptor"]
    second_descriptor = (
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

    rows: list[dict[str, object]] = []

    def add_row(
        name: str,
        coefficients: list[int],
        lower: int | None,
        upper: int | None,
    ) -> None:
        rows.append(
            {
                "name": name,
                "coefficients": coefficients,
                "lower": lower,
                "upper": upper,
            }
        )

    add_row("size", [1] * len(keys), size, size)
    add_row(
        "zero",
        [int(key == (0, 0)) for key in keys],
        1,
        1,
    )
    add_row(
        "first",
        [int(key == (first_size, 0)) for key in keys],
        1,
        1,
    )
    for index, key in enumerate(keys):
        descriptor = (sum(key), key[0])
        if key in {(0, 0), (first_size, 0)}:
            continue
        if sum(key) < first_size or descriptor < second_descriptor:
            coefficients = [0] * len(keys)
            coefficients[index] = 1
            add_row(
                f"forbid_{key[0]}_{key[1]}",
                coefficients,
                0,
                0,
            )

    second_key = (
        second_descriptor[1],
        second_descriptor[0] - second_descriptor[1],
    )
    add_row(
        "second",
        [int(key == second_key) for key in keys],
        1,
        None,
    )

    for target_inside in range(first_size + 1):
        for target_outside in range(outside_size + 1):
            coefficients = [
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
            ]
            orbit_size = (
                math.comb(first_size, target_inside)
                * math.comb(outside_size, target_outside)
            )
            add_row(
                f"cover_{target_inside}_{target_outside}",
                coefficients,
                orbit_size,
                None,
            )
    return keys, upper_bounds, rows


def rationalize(value: float) -> Fraction:
    result = Fraction(value).limit_denominator(1000000)
    if abs(float(result) - value) > 1e-8:
        raise RuntimeError(f"failed to rationalize {value}")
    return result


def normalize_ray(values: list[float]) -> list[int]:
    fractions = [rationalize(value) for value in values]
    scale = 1
    for value in fractions:
        scale = math.lcm(scale, value.denominator)
    integers = [
        value.numerator * (scale // value.denominator)
        for value in fractions
    ]
    divisor = 0
    for value in integers:
        divisor = math.gcd(divisor, abs(value))
    if divisor:
        integers = [value // divisor for value in integers]
    return integers


def verify_dual(
    upper_bounds: list[int],
    rows: list[dict[str, object]],
    multipliers: list[int],
) -> tuple[int, int]:
    combined = [0] * len(upper_bounds)
    required = 0
    for row, multiplier in zip(rows, multipliers):
        if multiplier == 0:
            continue
        if multiplier > 0:
            bound = row["lower"]
        else:
            bound = row["upper"]
        if bound is None:
            raise RuntimeError("dual multiplier uses an infinite row bound")
        required += multiplier * int(bound)
        for index, coefficient in enumerate(row["coefficients"]):
            combined[index] += multiplier * int(coefficient)
    maximum = sum(
        coefficient * upper
        for coefficient, upper in zip(combined, upper_bounds)
        if coefficient > 0
    )
    if maximum >= required:
        raise RuntimeError("dual ray does not give a strict contradiction")
    return required, maximum


def verify_primal(
    upper_bounds: list[int],
    rows: list[dict[str, object]],
    values: list[Fraction],
) -> None:
    for value, upper in zip(values, upper_bounds):
        if value < 0 or value > upper:
            raise RuntimeError("primal witness violates a variable bound")
    for row in rows:
        activity = sum(
            value * int(coefficient)
            for value, coefficient in zip(
                values,
                row["coefficients"],
            )
        )
        lower = row["lower"]
        upper = row["upper"]
        if lower is not None and activity < int(lower):
            raise RuntimeError("primal witness violates a lower row bound")
        if upper is not None and activity > int(upper):
            raise RuntimeError("primal witness violates an upper row bound")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--length", type=int, default=11)
    parser.add_argument("--radius", type=int, default=3)
    parser.add_argument("--size", type=int, default=15)
    args = parser.parse_args()

    try:
        import highspy
    except ImportError as exc:
        raise SystemExit(
            "highspy is required; install requirements-proof.txt"
        ) from exc

    manifest = json.loads(
        args.case_manifest.read_text(encoding="ascii")
    )
    certificates = []
    for case in manifest["cases"]:
        keys, upper_bounds, rows = build_profile(
            case,
            length=args.length,
            radius=args.radius,
            size=args.size,
        )
        solver = highspy.Highs()
        solver.setOptionValue("output_flag", False)
        solver.setOptionValue("presolve", "off")
        variables = [
            solver.addVariable(
                lb=0,
                ub=upper,
                name=f"x_{inside}_{outside}",
            )
            for (inside, outside), upper in zip(keys, upper_bounds)
        ]
        for row in rows:
            expression = solver.qsum(
                variable * int(coefficient)
                for variable, coefficient in zip(
                    variables,
                    row["coefficients"],
                )
            )
            lower = row["lower"]
            upper = row["upper"]
            if lower is not None and upper is not None and lower == upper:
                solver.addConstr(expression == int(lower), name=row["name"])
            elif lower is not None and upper is None:
                solver.addConstr(expression >= int(lower), name=row["name"])
            elif lower is None and upper is not None:
                solver.addConstr(expression <= int(upper), name=row["name"])
            else:
                raise RuntimeError("unsupported row bounds")

        solver.run()
        status = solver.getModelStatus()
        if status == highspy.HighsModelStatus.kInfeasible:
            ray_status, exists, ray = solver.getDualRay()
            if ray_status != highspy.HighsStatus.kOk or not exists:
                raise RuntimeError("HiGHS did not return a dual ray")
            multipliers = normalize_ray(ray.tolist())
            try:
                required, maximum = verify_dual(
                    upper_bounds,
                    rows,
                    multipliers,
                )
            except RuntimeError:
                multipliers = [-value for value in multipliers]
                required, maximum = verify_dual(
                    upper_bounds,
                    rows,
                    multipliers,
                )
            certificates.append(
                {
                    "case_id": case["case_id"],
                    "status": "LP_INFEASIBLE",
                    "multipliers": [
                        {
                            "row": row["name"],
                            "value": multiplier,
                        }
                        for row, multiplier in zip(rows, multipliers)
                        if multiplier != 0
                    ],
                    "required_lower_bound": required,
                    "maximum_over_variable_bounds": maximum,
                    "contradiction_margin": required - maximum,
                }
            )
        elif status == highspy.HighsModelStatus.kOptimal:
            solution = solver.getSolution()
            values = [
                rationalize(float(value))
                for value in solution.col_value
            ]
            verify_primal(upper_bounds, rows, values)
            certificates.append(
                {
                    "case_id": case["case_id"],
                    "status": "LP_FEASIBLE",
                    "nonzero_profile": [
                        {
                            "inside": key[0],
                            "outside": key[1],
                            "value": str(value),
                        }
                        for key, value in zip(keys, values)
                        if value != 0
                    ],
                }
            )
        else:
            raise RuntimeError(
                f"{case['case_id']}: unexpected status "
                f"{solver.modelStatusToString(status)}"
            )

    counts: dict[str, int] = {}
    for certificate in certificates:
        status = certificate["status"]
        counts[status] = counts.get(status, 0) + 1
    output = {
        "problem": {
            "length": args.length,
            "radius": args.radius,
            "size": args.size,
        },
        "case_manifest": str(args.case_manifest),
        "highs_version": highspy.Highs().version(),
        "arithmetic": "exact rational replay after numerical ray extraction",
        "status_counts": counts,
        "certificates": certificates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(json.dumps(counts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
