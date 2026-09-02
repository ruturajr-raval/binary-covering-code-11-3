#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
from pathlib import Path

from run_two_word_portfolio import case_units


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_formula", type=Path)
    parser.add_argument("case_manifest", type=Path)
    parser.add_argument("case_id")
    parser.add_argument("formula_output", type=Path)
    parser.add_argument("proof_output", type=Path)
    parser.add_argument("summary_output", type=Path)
    parser.add_argument("--solver", default="cadical300")
    parser.add_argument("--length", type=int, default=11)
    args = parser.parse_args()

    try:
        import pysat
        from pysat.formula import CNF
        from pysat.solvers import Solver
    except ImportError as exc:
        raise SystemExit(
            "python-sat is required; install requirements-sat.txt"
        ) from exc

    manifest = json.loads(
        args.case_manifest.read_text(encoding="ascii")
    )
    case = next(
        (
            candidate
            for candidate in manifest["cases"]
            if candidate["case_id"] == args.case_id
        ),
        None,
    )
    if case is None:
        raise SystemExit(f"unknown case: {args.case_id}")

    formula = CNF(from_file=str(args.base_formula))
    units = case_units(case, args.length)
    for literal in units:
        formula.append([literal])
    lines = [f"p cnf {formula.nv} {len(formula.clauses)}"]
    lines.extend(
        " ".join(str(literal) for literal in clause) + " 0"
        for clause in formula.clauses
    )
    formula_text = "\n".join(lines) + "\n"
    args.formula_output.parent.mkdir(parents=True, exist_ok=True)
    args.formula_output.write_text(formula_text, encoding="ascii")

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
        raise RuntimeError("case did not solve as UNSAT")
    if not proof:
        raise RuntimeError("solver did not return a proof trace")

    proof_text = "\n".join(proof) + "\n"
    proof_bytes = proof_text.encode("ascii")
    compressed = gzip.compress(proof_bytes, mtime=0)
    args.proof_output.parent.mkdir(parents=True, exist_ok=True)
    args.proof_output.write_bytes(compressed)

    summary = {
        "case_id": args.case_id,
        "base_formula": str(args.base_formula),
        "base_formula_sha256": hashlib.sha256(
            args.base_formula.read_bytes()
        ).hexdigest(),
        "case_formula": str(args.formula_output),
        "case_formula_sha256": hashlib.sha256(
            formula_text.encode("ascii")
        ).hexdigest(),
        "variables": formula.nv,
        "clauses": len(formula.clauses),
        "unit_count": len(units),
        "solver": args.solver,
        "python_sat_version": pysat.__version__,
        "solve_seconds": elapsed,
        "status": "UNSAT",
        "proof_format": "text DRAT",
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
