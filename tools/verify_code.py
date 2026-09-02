#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from covering_code.core import parse_code, verify_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("code", type=Path)
    parser.add_argument("--length", type=int, required=True)
    parser.add_argument("--radius", type=int, required=True)
    parser.add_argument("--expected-size", type=int)
    args = parser.parse_args()

    code = parse_code(args.code.read_text(encoding="ascii"), length=args.length)
    if args.expected_size is not None and len(code) != args.expected_size:
        raise SystemExit(
            f"expected {args.expected_size} codewords, found {len(code)}"
        )
    report = verify_code(code, length=args.length, radius=args.radius)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
