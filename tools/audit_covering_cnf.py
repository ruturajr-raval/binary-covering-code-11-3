#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def read_dimacs(path: Path) -> tuple[int, list[tuple[int, ...]], str]:
    raw = path.read_bytes()
    variable_count: int | None = None
    declared_clause_count: int | None = None
    clauses: list[tuple[int, ...]] = []

    for line_number, raw_line in enumerate(
        raw.decode("ascii").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("c"):
            continue
        if line.startswith("p "):
            if variable_count is not None:
                raise ValueError("multiple DIMACS headers")
            fields = line.split()
            if len(fields) != 4 or fields[:2] != ["p", "cnf"]:
                raise ValueError(f"invalid header on line {line_number}")
            variable_count = int(fields[2])
            declared_clause_count = int(fields[3])
            continue
        if variable_count is None:
            raise ValueError("clause appears before the DIMACS header")

        fields = [int(field) for field in line.split()]
        if not fields or fields[-1] != 0 or 0 in fields[:-1]:
            raise ValueError(
                f"clause on line {line_number} is not zero-terminated"
            )
        clause = tuple(fields[:-1])
        if not clause:
            raise ValueError(f"empty clause on line {line_number}")
        if any(abs(literal) > variable_count for literal in clause):
            raise ValueError(
                f"literal outside declared range on line {line_number}"
            )
        clauses.append(clause)

    if variable_count is None or declared_clause_count is None:
        raise ValueError("missing DIMACS header")
    if len(clauses) != declared_clause_count:
        raise ValueError(
            "declared clause count does not match parsed clause count"
        )
    return variable_count, clauses, hashlib.sha256(raw).hexdigest()


def expected_cardinality_prefix(
    primary_count: int,
    target: int,
) -> tuple[int, list[tuple[int, ...]]]:
    if target <= 0 or target >= primary_count:
        raise ValueError("auditor expects an interior cardinality target")

    width = target + 1
    total_variables = primary_count + primary_count * width

    def counter(position: int, threshold: int) -> int:
        return primary_count + position * width + threshold

    clauses: list[tuple[int, ...]] = []
    first = 1
    clauses.append((-counter(0, 1), first))
    clauses.append((counter(0, 1), -first))
    for threshold in range(2, width + 1):
        clauses.append((-counter(0, threshold),))

    for position in range(1, primary_count):
        literal = position + 1
        for threshold in range(1, width + 1):
            current = counter(position, threshold)
            previous = counter(position - 1, threshold)
            clauses.append((-previous, current))
            if threshold == 1:
                clauses.append((-literal, current))
                clauses.append((-current, previous, literal))
                continue

            previous_lower = counter(position - 1, threshold - 1)
            clauses.append((-literal, -previous_lower, current))
            clauses.append((-current, previous, literal))
            clauses.append((-current, previous, previous_lower))

    clauses.append((counter(primary_count - 1, target),))
    clauses.append((-counter(primary_count - 1, target + 1),))
    return total_variables, clauses


def expected_ball_clause(
    target: int,
    *,
    length: int,
    radius: int,
) -> tuple[int, ...]:
    return tuple(
        center + 1
        for center in range(1 << length)
        if bin(center ^ target).count("1") <= radius
    )


def audit(
    path: Path,
    *,
    length: int,
    radius: int,
    size: int,
    anchor_zero: bool,
) -> dict[str, object]:
    if length <= 0:
        raise ValueError("length must be positive")
    if radius < 0 or radius > length:
        raise ValueError("radius is outside the valid range")

    ambient_size = 1 << length
    variable_count, clauses, digest = read_dimacs(path)
    expected_variables, cardinality = expected_cardinality_prefix(
        ambient_size,
        size,
    )
    if variable_count != expected_variables:
        raise ValueError("variable count does not match the encoding")
    if clauses[: len(cardinality)] != cardinality:
        raise ValueError("cardinality prefix does not match the encoding")

    offset = len(cardinality)
    if anchor_zero:
        if clauses[offset : offset + 1] != [(1,)]:
            raise ValueError("zero-word anchor clause is missing or misplaced")
        offset += 1

    coverage = clauses[offset:]
    if len(coverage) != ambient_size:
        raise ValueError("coverage clause count does not match the cube")
    for target, clause in enumerate(coverage):
        if clause != expected_ball_clause(
            target,
            length=length,
            radius=radius,
        ):
            raise ValueError(
                f"coverage clause {target} does not match its Hamming ball"
            )

    ball_size = sum(math.comb(length, weight) for weight in range(radius + 1))
    return {
        "path": str(path),
        "sha256": digest,
        "length": length,
        "radius": radius,
        "size": size,
        "anchor_zero": anchor_zero,
        "ambient_size": ambient_size,
        "ball_size": ball_size,
        "variables": variable_count,
        "clauses": len(clauses),
        "cardinality_clauses": len(cardinality),
        "coverage_clauses": len(coverage),
        "valid": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cnf", type=Path)
    parser.add_argument("--length", type=int, required=True)
    parser.add_argument("--radius", type=int, required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--anchor-zero", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = audit(
        args.cnf,
        length=args.length,
        radius=args.radius,
        size=args.size,
        anchor_zero=args.anchor_zero,
    )
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="ascii")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
