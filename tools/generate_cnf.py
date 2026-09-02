#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from covering_code.cnf import dimacs_text, generate_covering_cnf


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--length", type=int, required=True)
    parser.add_argument("--radius", type=int, required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--anchor-zero", action="store_true")
    args = parser.parse_args()

    builder, _ = generate_covering_cnf(
        length=args.length,
        radius=args.radius,
        size=args.size,
        anchor_zero=args.anchor_zero,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dimacs_text(builder), encoding="ascii")
    print(
        f"wrote {builder.variable_count} variables and "
        f"{len(builder.clauses)} clauses"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
