#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from covering_code.linear import analyze_linear_cover


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parity_columns", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--radius", type=int, default=3)
    args = parser.parse_args()

    source = json.loads(
        args.parity_columns.read_text(encoding="ascii")
    )
    analysis = analyze_linear_cover(
        source["columns"],
        syndrome_bits=source["syndrome_bits"],
        radius=args.radius,
    )
    text = json.dumps(analysis, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="ascii")
    return 0 if analysis["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
