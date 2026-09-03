#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import time
from pathlib import Path

from run_two_word_portfolio import case_units


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_equal(
    record: dict[str, object],
    expected: dict[str, object],
) -> None:
    mismatches = sorted(
        key for key, value in expected.items() if record.get(key) != value
    )
    if mismatches:
        raise RuntimeError(
            "retained proof summary does not match reconstructed case; "
            f"fields={mismatches}"
        )


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
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()

    try:
        import pysat
        from pysat.formula import CNF
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
    args.formula_output.write_bytes(formula_text.encode("ascii"))

    if args.verify_existing:
        summary = json.loads(
            args.summary_output.read_text(encoding="ascii")
        )
        compressed = args.proof_output.read_bytes()
        proof_bytes = gzip.decompress(compressed)
        require_equal(
            summary,
            {
                "case_id": args.case_id,
                "base_formula": str(args.base_formula),
                "base_formula_sha256": file_sha256(args.base_formula),
                "case_formula": str(args.formula_output),
                "case_formula_sha256": hashlib.sha256(
                    formula_text.encode("ascii")
                ).hexdigest(),
                "variables": formula.nv,
                "clauses": len(formula.clauses),
                "unit_count": len(units),
                "solver": args.solver,
                "python_sat_version": pysat.__version__,
                "status": "UNSAT",
                "proof_format": "text DRAT",
                "proof_lines": len(proof_bytes.splitlines()),
                "proof_uncompressed_bytes": len(proof_bytes),
                "proof_uncompressed_sha256": hashlib.sha256(
                    proof_bytes
                ).hexdigest(),
                "proof_compressed": str(args.proof_output),
                "proof_compressed_bytes": len(compressed),
                "proof_compressed_sha256": hashlib.sha256(
                    compressed
                ).hexdigest(),
                "proof_verification": (
                    "recorded in a separate check file"
                ),
            },
        )
        solve_seconds = summary.get("solve_seconds")
        if (
            not isinstance(solve_seconds, (int, float))
            or isinstance(solve_seconds, bool)
            or not math.isfinite(solve_seconds)
            or solve_seconds < 0
        ):
            raise RuntimeError(
                "retained proof summary has invalid solve_seconds"
            )
        if not isinstance(summary.get("solver_statistics"), dict):
            raise RuntimeError(
                "retained proof summary has invalid solver statistics"
            )
        print(
            json.dumps(
                {
                    "case_formula_sha256": summary[
                        "case_formula_sha256"
                    ],
                    "case_id": args.case_id,
                    "proof_compressed_sha256": summary[
                        "proof_compressed_sha256"
                    ],
                    "verified_existing": True,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    try:
        from pysat.solvers import Solver
    except ImportError as exc:
        raise SystemExit(
            "python-sat solvers are required; install requirements-sat.txt"
        ) from exc

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
