#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import time
from pathlib import Path

from covering_code.core import normalized_code_text, verify_code


def solve_worker(
    cnf_path: str,
    solver_name: str,
    connection: object,
) -> None:
    try:
        from pysat.formula import CNF
        from pysat.solvers import Solver

        parse_started = time.monotonic()
        formula = CNF(from_file=cnf_path)
        parse_seconds = time.monotonic() - parse_started
        connection.send(
            (
                "parsed",
                {
                    "parse_seconds": parse_seconds,
                    "variables": formula.nv,
                    "clauses": len(formula.clauses),
                },
            )
        )

        solve_started = time.monotonic()
        with Solver(
            name=solver_name,
            bootstrap_with=formula.clauses,
        ) as solver:
            result = solver.solve()
            connection.send(
                (
                    "result",
                    {
                        "result": result,
                        "solve_seconds": time.monotonic() - solve_started,
                        "statistics": solver.accum_stats(),
                        "model": solver.get_model() if result else None,
                    },
                )
            )
    except BaseException as exc:
        connection.send(
            (
                "error",
                {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            )
        )
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cnf", type=Path)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--solver", default="cadical300")
    parser.add_argument("--time-limit", type=float, default=300)
    parser.add_argument("--length", type=int, required=True)
    parser.add_argument("--radius", type=int, required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--code-output", type=Path)
    args = parser.parse_args()

    if args.time_limit <= 0:
        raise SystemExit("time limit must be positive")

    try:
        import pysat
    except ImportError as exc:
        raise SystemExit(
            "python-sat is required; install requirements-sat.txt"
        ) from exc

    raw_formula = args.cnf.read_bytes()
    formula_sha256 = hashlib.sha256(raw_formula).hexdigest()
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=solve_worker,
        args=(str(args.cnf), args.solver, sender),
    )
    process.start()
    sender.close()

    parse_payload: dict[str, object] = {}
    result_payload: dict[str, object] | None = None
    error_payload: dict[str, object] | None = None
    deadline = time.monotonic() + args.time_limit
    while time.monotonic() < deadline and result_payload is None:
        remaining = deadline - time.monotonic()
        if receiver.poll(min(0.1, max(remaining, 0.0))):
            kind, payload = receiver.recv()
            if kind == "parsed":
                parse_payload = payload
            elif kind == "result":
                result_payload = payload
            elif kind == "error":
                error_payload = payload
                break
        elif not process.is_alive():
            break

    timed_out = result_payload is None and error_payload is None
    if process.is_alive():
        process.terminate()
    process.join()
    receiver.close()

    if error_payload is not None:
        raise RuntimeError(
            f"{error_payload['type']}: {error_payload['message']}"
        )

    if result_payload is None:
        status = "UNKNOWN"
        solve_seconds = args.time_limit
        stats: dict[str, object] = {}
        model = None
    else:
        result = result_payload["result"]
        status = "SAT" if result is True else "UNSAT"
        solve_seconds = result_payload["solve_seconds"]
        stats = result_payload["statistics"]
        model = result_payload["model"]

    summary: dict[str, object] = {
        "formula": str(args.cnf),
        "formula_sha256": formula_sha256,
        "variables": parse_payload.get("variables"),
        "clauses": parse_payload.get("clauses"),
        "solver": args.solver,
        "python_sat_version": pysat.__version__,
        "time_limit_seconds": args.time_limit,
        "parse_seconds": parse_payload.get("parse_seconds"),
        "solve_seconds": solve_seconds,
        "status": status,
        "process_timeout_enforced": True,
        "timed_out": timed_out,
        "solver_statistics": stats,
        "proof_trace_available": False,
    }

    if model is not None:
        positive = {literal for literal in model if literal > 0}
        code = [
            word
            for word in range(1 << args.length)
            if word + 1 in positive
        ]
        if len(code) > args.size:
            raise RuntimeError("SAT model exceeds the requested code size")
        model_code_size = len(code)
        if len(code) < args.size:
            selected = set(code)
            code.extend(
                word
                for word in range(1 << args.length)
                if word not in selected
            )
            code = code[: args.size]
        report = verify_code(
            code,
            length=args.length,
            radius=args.radius,
        )
        if not report.valid:
            raise RuntimeError("SAT model decoded to an invalid code")
        summary["model_code_size"] = model_code_size
        summary["padded_code_size"] = len(code)
        summary["verification"] = report.to_dict()
        if args.code_output is not None:
            args.code_output.parent.mkdir(parents=True, exist_ok=True)
            args.code_output.write_text(
                normalized_code_text(code, length=args.length),
                encoding="ascii",
            )

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if status in {"SAT", "UNSAT"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
