#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from covering_code.cnf import CnfBuilder, dimacs_text, generate_covering_cnf


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--length", type=int, default=11)
    parser.add_argument("--radius", type=int, default=3)
    parser.add_argument("--size", type=int, default=15)
    parser.add_argument("--maximum-minimum-weight", type=int, default=6)
    args = parser.parse_args()

    base, selected = generate_covering_cnf(
        length=args.length,
        radius=args.radius,
        size=args.size,
        anchor_zero=True,
    )
    base_text = dimacs_text(base)
    base_sha256 = hashlib.sha256(base_text.encode("ascii")).hexdigest()
    args.output_directory.mkdir(parents=True, exist_ok=True)

    cases = []
    for weight in range(1, args.maximum_minimum_weight + 1):
        builder = CnfBuilder(
            variable_count=base.variable_count,
            clauses=list(base.clauses),
        )
        forbidden_words = [
            word
            for word in range(1, 1 << args.length)
            if bin(word).count("1") < weight
        ]
        for word in forbidden_words:
            builder.add(-selected[word])
        canonical_word = (1 << weight) - 1
        builder.add(selected[canonical_word])

        text = dimacs_text(builder)
        output = (
            args.output_directory /
            f"k2-{args.length}-{args.radius}-size{args.size}-minweight{weight}.cnf"
        )
        output.write_text(text, encoding="ascii")
        cases.append(
            {
                "minimum_weight": weight,
                "canonical_word": canonical_word,
                "forbidden_lower_weight_words": len(forbidden_words),
                "variables": builder.variable_count,
                "clauses": len(builder.clauses),
                "formula": str(output),
                "sha256": hashlib.sha256(
                    text.encode("ascii")
                ).hexdigest(),
            }
        )

    manifest = {
        "problem": {
            "q": 2,
            "length": args.length,
            "radius": args.radius,
            "size": args.size,
        },
        "anchor_zero": True,
        "case_rule": (
            "minimum nonzero weight equals w and one minimum-weight "
            "word is coordinate-permuted to 2^w-1"
        ),
        "maximum_minimum_weight": args.maximum_minimum_weight,
        "base_formula_sha256": base_sha256,
        "base_variables": base.variable_count,
        "base_clauses": len(base.clauses),
        "cases": cases,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
