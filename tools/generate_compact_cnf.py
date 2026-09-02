#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--length", type=int, required=True)
    parser.add_argument("--radius", type=int, required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument(
        "--encoding",
        choices=["kmtotalizer", "cardnetwrk"],
        required=True,
    )
    parser.add_argument("--anchor-zero", action="store_true")
    args = parser.parse_args()

    try:
        import pysat
        from pysat.card import CardEnc, EncType
    except ImportError as exc:
        raise SystemExit(
            "python-sat is required; install requirements-sat.txt"
        ) from exc

    if args.length <= 0:
        raise SystemExit("length must be positive")
    if args.radius < 0 or args.radius > args.length:
        raise SystemExit("radius is outside the valid range")
    ambient_size = 1 << args.length
    if args.size <= 0 or args.size >= ambient_size:
        raise SystemExit("size must be between 1 and the ambient size")

    encoding = {
        "kmtotalizer": EncType.kmtotalizer,
        "cardnetwrk": EncType.cardnetwrk,
    }[args.encoding]
    selected = list(range(1, ambient_size + 1))
    cardinality = CardEnc.atmost(
        lits=selected,
        bound=args.size,
        top_id=ambient_size,
        encoding=encoding,
    )
    clauses = [tuple(clause) for clause in cardinality.clauses]
    cardinality_clause_count = len(clauses)
    if args.anchor_zero:
        clauses.append((1,))
    for target in range(ambient_size):
        clauses.append(
            tuple(
                center + 1
                for center in range(ambient_size)
                if bin(center ^ target).count("1") <= args.radius
            )
        )

    lines = [f"p cnf {cardinality.nv} {len(clauses)}"]
    lines.extend(
        " ".join(str(literal) for literal in clause) + " 0"
        for clause in clauses
    )
    text = "\n".join(lines) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="ascii")

    metadata = {
        "formula": str(args.output),
        "sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
        "python_sat_version": pysat.__version__,
        "encoding": args.encoding,
        "semantics": "at most size selected codewords",
        "padding_equivalence": True,
        "length": args.length,
        "radius": args.radius,
        "size": args.size,
        "anchor_zero": args.anchor_zero,
        "variables": cardinality.nv,
        "auxiliary_variables": cardinality.nv - ambient_size,
        "cardinality_clauses": cardinality_clause_count,
        "coverage_clauses": ambient_size,
        "clauses": len(clauses),
    }
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
