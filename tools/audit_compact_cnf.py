#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_covering_cnf import expected_ball_clause, read_dimacs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("formula", type=Path)
    parser.add_argument("metadata", type=Path)
    args = parser.parse_args()

    metadata = json.loads(args.metadata.read_text(encoding="ascii"))
    variables, clauses, digest = read_dimacs(args.formula)
    if digest != metadata["sha256"]:
        raise SystemExit("formula hash does not match metadata")
    if hashlib.sha256(args.formula.read_bytes()).hexdigest() != digest:
        raise SystemExit("formula byte hash is inconsistent")
    if variables != metadata["variables"]:
        raise SystemExit("variable count does not match metadata")
    if len(clauses) != metadata["clauses"]:
        raise SystemExit("clause count does not match metadata")

    length = metadata["length"]
    radius = metadata["radius"]
    ambient_size = 1 << length
    suffix_size = ambient_size + int(metadata["anchor_zero"])
    suffix = clauses[-suffix_size:]
    if metadata["anchor_zero"]:
        if suffix[0] != (1,):
            raise SystemExit("anchor clause is missing")
        coverage = suffix[1:]
    else:
        coverage = suffix
    for target, clause in enumerate(coverage):
        if clause != expected_ball_clause(
            target,
            length=length,
            radius=radius,
        ):
            raise SystemExit(
                f"coverage clause {target} does not match its Hamming ball"
            )

    cardinality_count = len(clauses) - suffix_size
    if cardinality_count != metadata["cardinality_clauses"]:
        raise SystemExit("cardinality clause count does not match metadata")

    report = {
        "formula": str(args.formula),
        "sha256": digest,
        "encoding": metadata["encoding"],
        "variables": variables,
        "clauses": len(clauses),
        "cardinality_clauses": cardinality_count,
        "coverage_clauses": len(coverage),
        "suffix_valid": True,
        "valid": True,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
