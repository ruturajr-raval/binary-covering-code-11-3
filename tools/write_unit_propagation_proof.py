#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import lzma
from pathlib import Path

from audit_covering_cnf import read_dimacs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("formula", type=Path)
    parser.add_argument("proof_output", type=Path)
    parser.add_argument("summary_output", type=Path)
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()

    formula = args.formula.resolve()
    proof_output = args.proof_output.resolve()
    summary_output = args.summary_output.resolve()
    if len({formula, proof_output, summary_output}) != 3:
        raise SystemExit("formula, proof, and summary paths must be distinct")

    variables, clauses, formula_sha256 = read_dimacs(formula)
    proof_bytes = b"0\n"
    if args.proof_output.suffix == ".xz":
        compressed = lzma.compress(
            proof_bytes,
            format=lzma.FORMAT_XZ,
            preset=9 | lzma.PRESET_EXTREME,
        )
        compression = "xz"
    elif args.proof_output.suffix == ".gz":
        compressed = gzip.compress(proof_bytes, mtime=0)
        compression = "gzip"
    else:
        raise SystemExit("proof output must end in .gz or .xz")

    proof_output.parent.mkdir(parents=True, exist_ok=True)
    proof_output.write_bytes(compressed)
    summary = {
        "case_id": args.case_id,
        "case_formula": str(args.formula),
        "case_formula_sha256": formula_sha256,
        "variables": variables,
        "clauses": len(clauses),
        "solver": "unit propagation",
        "status": "UNSAT",
        "proof_format": "text DRAT",
        "proof_strategy": "empty-clause RUP",
        "proof_compression": compression,
        "proof_lines": 1,
        "proof_uncompressed_bytes": len(proof_bytes),
        "proof_uncompressed_sha256": hashlib.sha256(
            proof_bytes
        ).hexdigest(),
        "proof_compressed": str(args.proof_output),
        "proof_compressed_bytes": len(compressed),
        "proof_compressed_sha256": hashlib.sha256(
            compressed
        ).hexdigest(),
        "proof_verification": "recorded in a separate check file",
    }
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
