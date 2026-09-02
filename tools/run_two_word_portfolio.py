#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import time
from pathlib import Path

from covering_code.core import normalized_code_text, verify_code


def weight(word: int) -> int:
    return bin(word).count("1")


def case_units(case: dict[str, object], length: int) -> list[int]:
    ambient_size = 1 << length
    minimum_weight = int(case["minimum_weight"])
    first_word = int(case["first_word"])
    descriptor_payload = case["second_descriptor"]
    descriptor = (
        int(descriptor_payload["weight"]),
        int(descriptor_payload["intersection"]),
    )
    units = [
        -(word + 1)
        for word in range(1, ambient_size)
        if weight(word) < minimum_weight
    ]
    units.append(first_word + 1)
    units.extend(
        -(word + 1)
        for word in range(1, ambient_size)
        if word != first_word
        and weight(word) >= minimum_weight
        and (
            weight(word),
            weight(word & first_word),
        ) < descriptor
    )
    units.append(int(case["second_word"]) + 1)
    return units


def unit_digest(units: list[int]) -> str:
    text = "".join(f"{literal}\n" for literal in units)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def solve_case_worker(
    base_formula: str,
    solver_name: str,
    units: list[int],
    primary_count: int,
    connection: object,
) -> None:
    try:
        from pysat.formula import CNF
        from pysat.solvers import Solver

        formula = CNF(from_file=base_formula)
        for literal in units:
            formula.append([literal])
        started = time.monotonic()
        with Solver(
            name=solver_name,
            bootstrap_with=formula.clauses,
        ) as solver:
            result = solver.solve()
            model = solver.get_model() if result else None
            selected = None
            if model is not None:
                positive = {literal for literal in model if literal > 0}
                selected = [
                    word
                    for word in range(primary_count)
                    if word + 1 in positive
                ]
            connection.send(
                {
                    "result": result,
                    "seconds": time.monotonic() - started,
                    "statistics": solver.accum_stats(),
                    "selected": selected,
                }
            )
    except BaseException as exc:
        connection.send(
            {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_formula", type=Path)
    parser.add_argument("case_manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--solver", default="cadical300")
    parser.add_argument("--case-time-limit", type=float, default=10)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--length", type=int, default=11)
    parser.add_argument("--radius", type=int, default=3)
    parser.add_argument("--size", type=int, default=15)
    parser.add_argument("--minimum-weight", type=int)
    parser.add_argument("--code-output", type=Path)
    args = parser.parse_args()

    if args.case_time_limit <= 0 or args.workers <= 0:
        raise SystemExit("time limit and worker count must be positive")

    try:
        import pysat
    except ImportError as exc:
        raise SystemExit(
            "python-sat is required; install requirements-sat.txt"
        ) from exc

    manifest = json.loads(
        args.case_manifest.read_text(encoding="ascii")
    )
    cases = manifest["cases"]
    if args.minimum_weight is not None:
        cases = [
            case
            for case in cases
            if case["minimum_weight"] == args.minimum_weight
        ]
        if not cases:
            raise SystemExit(
                "no manifest cases match the requested minimum weight"
            )
    context = multiprocessing.get_context("spawn")
    pending = list(cases)
    active: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    found_code: list[int] | None = None
    started = time.monotonic()

    def launch(case: dict[str, object]) -> None:
        units = case_units(case, args.length)
        if len(units) != case["unit_count"]:
            raise RuntimeError(f"{case['case_id']}: unit count mismatch")
        if unit_digest(units) != case["unit_sha256"]:
            raise RuntimeError(f"{case['case_id']}: unit hash mismatch")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=solve_case_worker,
            args=(
                str(args.base_formula),
                args.solver,
                units,
                1 << args.length,
                sender,
            ),
        )
        process.start()
        sender.close()
        active.append(
            {
                "case": case,
                "process": process,
                "receiver": receiver,
                "started": time.monotonic(),
            }
        )

    while (pending or active) and found_code is None:
        while pending and len(active) < args.workers:
            launch(pending.pop(0))

        for job in list(active):
            process = job["process"]
            receiver = job["receiver"]
            case = job["case"]
            elapsed = time.monotonic() - job["started"]
            payload = None
            if receiver.poll():
                payload = receiver.recv()
            elif elapsed >= args.case_time_limit:
                if process.is_alive():
                    process.terminate()
                process.join()
                receiver.close()
                results.append(
                    {
                        "case_id": case["case_id"],
                        "status": "UNKNOWN",
                        "timed_out": True,
                        "seconds": args.case_time_limit,
                    }
                )
                active.remove(job)
                continue
            elif not process.is_alive():
                process.join()
                receiver.close()
                results.append(
                    {
                        "case_id": case["case_id"],
                        "status": "ERROR",
                        "timed_out": False,
                        "seconds": elapsed,
                        "error": "worker exited without a result",
                    }
                )
                active.remove(job)
                continue

            if payload is None:
                continue
            process.join()
            receiver.close()
            if "error_type" in payload:
                results.append(
                    {
                        "case_id": case["case_id"],
                        "status": "ERROR",
                        "timed_out": False,
                        "seconds": elapsed,
                        "error": (
                            f"{payload['error_type']}: "
                            f"{payload['error_message']}"
                        ),
                    }
                )
            elif payload["result"] is True:
                code = payload["selected"]
                if len(code) > args.size:
                    raise RuntimeError("SAT case exceeds the size bound")
                model_code_size = len(code)
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
                    raise RuntimeError("SAT case decoded to an invalid cover")
                found_code = code
                results.append(
                    {
                        "case_id": case["case_id"],
                        "status": "SAT",
                        "timed_out": False,
                        "seconds": payload["seconds"],
                        "model_code_size": model_code_size,
                        "padded_code_size": len(code),
                        "statistics": payload["statistics"],
                        "verification": report.to_dict(),
                    }
                )
            else:
                results.append(
                    {
                        "case_id": case["case_id"],
                        "status": "UNSAT",
                        "timed_out": False,
                        "seconds": payload["seconds"],
                        "statistics": payload["statistics"],
                        "proof_trace_available": False,
                    }
                )
            active.remove(job)

        if found_code is None:
            time.sleep(0.01)

    if found_code is not None:
        for job in active:
            process = job["process"]
            receiver = job["receiver"]
            if process.is_alive():
                process.terminate()
            process.join()
            receiver.close()

    status_counts: dict[str, int] = {}
    for result in results:
        status = result["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    summary = {
        "base_formula": str(args.base_formula),
        "base_formula_sha256": hashlib.sha256(
            args.base_formula.read_bytes()
        ).hexdigest(),
        "case_manifest": str(args.case_manifest),
        "case_count": len(cases),
        "minimum_weight_filter": args.minimum_weight,
        "solver": args.solver,
        "python_sat_version": pysat.__version__,
        "case_time_limit_seconds": args.case_time_limit,
        "workers": args.workers,
        "elapsed_seconds": time.monotonic() - started,
        "status_counts": status_counts,
        "found_cover": found_code is not None,
        "proof_traces_available": False,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    if found_code is not None and args.code_output is not None:
        args.code_output.parent.mkdir(parents=True, exist_ok=True)
        args.code_output.write_text(
            normalized_code_text(found_code, length=args.length),
            encoding="ascii",
        )
    print(
        json.dumps(
            {
                "elapsed_seconds": summary["elapsed_seconds"],
                "found_cover": summary["found_cover"],
                "status_counts": status_counts,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if found_code is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
