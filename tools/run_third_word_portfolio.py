#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import multiprocessing
import time
from pathlib import Path

from covering_code.core import normalized_code_text, verify_code
from generate_third_word_formula import build_formula


def solve_parent_worker(
    base_formula: str,
    parent_case: dict[str, object],
    third_parent: dict[str, object],
    solver_name: str,
    length: int,
    enforce_matching: bool,
    connection: object,
) -> None:
    try:
        from pysat.solvers import Solver

        build_started = time.monotonic()
        variables, clauses, metadata = build_formula(
            Path(base_formula),
            parent_case,
            third_parent,
            length=length,
            enforce_matching=enforce_matching,
        )
        build_seconds = time.monotonic() - build_started
        solve_started = time.monotonic()
        with Solver(
            name=solver_name,
            bootstrap_with=clauses,
        ) as solver:
            result = solver.solve()
            model = solver.get_model() if result else None
            statistics = solver.accum_stats()
        selected = None
        if model is not None:
            positive = {literal for literal in model if literal > 0}
            selected = [
                word
                for word in range(1 << length)
                if word + 1 in positive
            ]
        connection.send(
            {
                "result": result,
                "build_seconds": build_seconds,
                "solve_seconds": time.monotonic() - solve_started,
                "variables": variables,
                "clauses": len(clauses),
                "selectors": metadata["selector_count"],
                "matching_clauses": metadata["matching_clauses"],
                "matching_auxiliary_variables": metadata[
                    "matching_auxiliary_variables"
                ],
                "statistics": statistics,
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
    parser.add_argument("branch_manifest", type=Path)
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--solver", default="cadical300")
    parser.add_argument("--parent-time-limit", type=float, default=30)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--length", type=int, default=11)
    parser.add_argument("--radius", type=int, default=3)
    parser.add_argument("--code-output", type=Path)
    parser.add_argument("--maximum-degree-manifest", type=Path)
    args = parser.parse_args()

    if args.parent_time_limit <= 0 or args.workers <= 0:
        raise SystemExit("time limit and worker count must be positive")
    try:
        import pysat
    except ImportError as exc:
        raise SystemExit(
            "python-sat is required; install requirements-sat.txt"
        ) from exc

    branches = json.loads(
        args.branch_manifest.read_text(encoding="ascii")
    )
    parent_manifest = json.loads(
        args.parent_manifest.read_text(encoding="ascii")
    )
    third_manifest = json.loads(
        args.third_manifest.read_text(encoding="ascii")
    )
    branch_formulas = {
        int(case["minimum_distance"]): case["formula"]
        for case in branches["cases"]
    }
    third_by_id = {
        parent["parent_case_id"]: parent
        for parent in third_manifest["parents"]
    }
    matching_cases: set[str] = set()
    if args.maximum_degree_manifest is not None:
        maximum_degree = json.loads(
            args.maximum_degree_manifest.read_text(encoding="ascii")
        )
        matching_cases = set(maximum_degree["matching_cases"])
    pending = list(parent_manifest["cases"])
    context = multiprocessing.get_context("spawn")
    active: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    found_code: list[int] | None = None
    started = time.monotonic()

    def launch(parent_case: dict[str, object]) -> None:
        case_id = parent_case["case_id"]
        third_parent = third_by_id.get(case_id)
        if third_parent is None:
            raise RuntimeError(f"missing third-word data for {case_id}")
        distance = int(parent_case["minimum_weight"])
        enforce_matching = case_id in matching_cases
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=solve_parent_worker,
            args=(
                branch_formulas[distance],
                parent_case,
                third_parent,
                args.solver,
                args.length,
                enforce_matching,
                sender,
            ),
        )
        process.start()
        sender.close()
        active.append(
            {
                "case": parent_case,
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
            elif elapsed >= args.parent_time_limit:
                if process.is_alive():
                    process.terminate()
                process.join()
                receiver.close()
                results.append(
                    {
                        "case_id": case["case_id"],
                        "minimum_distance": case["minimum_weight"],
                        "status": "UNKNOWN",
                        "timed_out": True,
                        "seconds": args.parent_time_limit,
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
                        "minimum_distance": case["minimum_weight"],
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
                        "minimum_distance": case["minimum_weight"],
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
                report = verify_code(
                    code,
                    length=args.length,
                    radius=args.radius,
                )
                if not report.valid:
                    raise RuntimeError("SAT model decoded to an invalid cover")
                found_code = code
                results.append(
                    {
                        "case_id": case["case_id"],
                        "minimum_distance": case["minimum_weight"],
                        "status": "SAT",
                        "timed_out": False,
                        "build_seconds": payload["build_seconds"],
                        "solve_seconds": payload["solve_seconds"],
                        "variables": payload["variables"],
                        "clauses": payload["clauses"],
                        "selectors": payload["selectors"],
                        "matching_clauses": payload["matching_clauses"],
                        "matching_auxiliary_variables": payload[
                            "matching_auxiliary_variables"
                        ],
                        "statistics": payload["statistics"],
                        "verification": report.to_dict(),
                    }
                )
            else:
                results.append(
                    {
                        "case_id": case["case_id"],
                        "minimum_distance": case["minimum_weight"],
                        "status": "UNSAT",
                        "timed_out": False,
                        "build_seconds": payload["build_seconds"],
                        "solve_seconds": payload["solve_seconds"],
                        "variables": payload["variables"],
                        "clauses": payload["clauses"],
                        "selectors": payload["selectors"],
                        "matching_clauses": payload["matching_clauses"],
                        "matching_auxiliary_variables": payload[
                            "matching_auxiliary_variables"
                        ],
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
        "branch_manifest": str(args.branch_manifest),
        "parent_manifest": str(args.parent_manifest),
        "third_manifest": str(args.third_manifest),
        "maximum_degree_manifest": (
            None
            if args.maximum_degree_manifest is None
            else str(args.maximum_degree_manifest)
        ),
        "parent_case_count": len(parent_manifest["cases"]),
        "solver": args.solver,
        "python_sat_version": pysat.__version__,
        "parent_time_limit_seconds": args.parent_time_limit,
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
