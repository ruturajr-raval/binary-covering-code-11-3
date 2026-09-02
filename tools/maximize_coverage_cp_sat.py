#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from covering_code.core import normalized_code_text, parse_code
from covering_code.search import maximize_coverage_with_cp_sat


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", type=Path)
    parser.add_argument("--length", type=int, required=True)
    parser.add_argument("--radius", type=int, required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--time-limit", type=float, default=300)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--anchor-zero", action="store_true")
    parser.add_argument("--initial-code", type=Path)
    parser.add_argument("--code-output", type=Path)
    args = parser.parse_args()

    initial_code = None
    if args.initial_code is not None:
        initial_code = parse_code(
            args.initial_code.read_text(encoding="ascii"),
            length=args.length,
        )
    summary, code = maximize_coverage_with_cp_sat(
        length=args.length,
        radius=args.radius,
        size=args.size,
        time_limit=args.time_limit,
        workers=args.workers,
        seed=args.seed,
        anchor_zero=args.anchor_zero,
        initial_code=initial_code,
    )
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    if code is not None and args.code_output is not None:
        args.code_output.parent.mkdir(parents=True, exist_ok=True)
        args.code_output.write_text(
            normalized_code_text(code, length=args.length),
            encoding="ascii",
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if code is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
