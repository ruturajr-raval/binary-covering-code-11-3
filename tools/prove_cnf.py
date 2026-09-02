#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import lzma
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("formula", type=Path)
    parser.add_argument("proof_output", type=Path)
    parser.add_argument("summary_output", type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--solver", default="cadical300")
    args = parser.parse_args()

    try:
        import pysat
        from pysat.formula import CNF
        from pysat.solvers import Solver
    except ImportError as exc:
        raise SystemExit(
            "python-sat is required; install requirements-sat.txt"
        ) from exc

    formula = CNF(from_file=str(args.formula))
    started = time.monotonic()
    with Solver(
        name=args.solver,
        bootstrap_with=formula.clauses,
        with_proof=True,
    ) as solver:
        result = solver.solve()
        elapsed = time.monotonic() - started
        proof = solver.get_proof()
        statistics = solver.accum_stats()
    if result is not False:
        raise RuntimeError("formula did not solve as UNSAT")
    if not proof:
        raise RuntimeError("solver did not return a proof trace")

    proof_text = "\n".join(proof) + "\n"
    proof_bytes = proof_text.encode("ascii")
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
    args.proof_output.parent.mkdir(parents=True, exist_ok=True)
    args.proof_output.write_bytes(compressed)
    formula_sha256 = hashlib.sha256(args.formula.read_bytes()).hexdigest()
    summary = {
        "case_id": args.case_id,
        "case_formula": str(args.formula),
        "case_formula_sha256": formula_sha256,
        "variables": formula.nv,
        "clauses": len(formula.clauses),
        "solver": args.solver,
        "python_sat_version": pysat.__version__,
        "solve_seconds": elapsed,
        "status": "UNSAT",
        "proof_format": "text DRAT",
        "proof_compression": compression,
        "proof_lines": len(proof),
        "proof_uncompressed_bytes": len(proof_bytes),
        "proof_uncompressed_sha256": hashlib.sha256(
            proof_bytes
        ).hexdigest(),
        "proof_compressed": str(args.proof_output),
        "proof_compressed_bytes": len(compressed),
        "proof_compressed_sha256": hashlib.sha256(
            compressed
        ).hexdigest(),
        "solver_statistics": statistics,
        "proof_verification": "recorded in a separate check file",
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
