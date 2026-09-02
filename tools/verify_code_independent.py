#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def read_words(path: Path, length: int) -> list[int]:
    words: list[int] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="ascii").splitlines(),
        start=1,
    ):
        token = raw_line.strip()
        if not token or token.startswith("#"):
            continue
        if len(token) != length or set(token) - {"0", "1"}:
            raise ValueError(
                f"line {line_number} is not a {length}-bit binary word"
            )
        words.append(int(token, 2))
    if not words:
        raise ValueError("code is empty")
    if len(words) != len(set(words)):
        raise ValueError("code contains duplicate words")
    return words


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("code", type=Path)
    parser.add_argument("--length", type=int, required=True)
    parser.add_argument("--radius", type=int, required=True)
    parser.add_argument("--expected-size", type=int)
    args = parser.parse_args()

    if args.length <= 0:
        raise SystemExit("length must be positive")
    if args.radius < 0 or args.radius > args.length:
        raise SystemExit("radius is outside the valid range")

    words = read_words(args.code, args.length)
    if args.expected_size is not None and len(words) != args.expected_size:
        raise SystemExit(
            f"expected {args.expected_size} codewords, found {len(words)}"
        )

    distance_histogram: dict[int, int] = {}
    uncovered: list[int] = []
    for target in range(1 << args.length):
        minimum = min(
            bin(target ^ codeword).count("1")
            for codeword in words
        )
        distance_histogram[minimum] = (
            distance_histogram.get(minimum, 0) + 1
        )
        if minimum > args.radius:
            uncovered.append(target)

    normalized = "".join(
        f"{word:0{args.length}b}\n"
        for word in sorted(words)
    )
    report = {
        "length": args.length,
        "radius": args.radius,
        "code_size": len(words),
        "ambient_size": 1 << args.length,
        "valid": not uncovered,
        "covering_radius": max(distance_histogram),
        "distance_histogram": distance_histogram,
        "uncovered_words": uncovered,
        "normalized_sha256": hashlib.sha256(
            normalized.encode("ascii")
        ).hexdigest(),
        "implementation": "standalone-direct-distance",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
