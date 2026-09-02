#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Protocol

from covering_code.core import normalized_code_text, verify_code
from generate_third_word_child_formula import (
    build_child_formula,
    display_path,
    ensure_repository_path,
    repository_root,
    resolve_repository_path,
)


class StatisticsSolver(Protocol):
    def accum_stats(self) -> dict[str, int]:
        ...


def optional_solver_statistics(
    solver: StatisticsSolver,
) -> dict[str, int] | None:
    try:
        return solver.accum_stats()
    except NotImplementedError:
        return None


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_snapshot(
    path: Path,
) -> tuple[dict[str, object], str]:
    payload = path.read_bytes()
    return (
        json.loads(payload.decode("ascii")),
        hashlib.sha256(payload).hexdigest(),
    )


def utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def current_git_commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        cwd=root,
    )
    commit = result.stdout.strip()
    if len(commit) != 40:
        raise RuntimeError("git did not return a full commit identifier")
    return commit


def git_worktree_state(root: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
        cwd=root,
    )
    return "dirty" if result.stdout else "clean"


def default_run_record_path(output: Path) -> Path:
    return output.with_name(f"{output.stem}-run.json")


def default_code_output_path(output: Path) -> Path:
    return output.with_name(f"{output.stem}-cover.txt")


def executed_code_paths(root: Path) -> tuple[Path, ...]:
    return (
        root / "tools/run_third_word_child_portfolio.py",
        root / "tools/generate_third_word_child_formula.py",
        root / "tools/audit_covering_cnf.py",
        root / "tools/matching_constraints.py",
        root / "tools/run_two_word_portfolio.py",
        root / "tools/third_word_symmetry.py",
        root / "src/covering_code/__init__.py",
        root / "src/covering_code/core.py",
        root / "src/covering_code/cnf.py",
    )


def close_job(job: dict[str, object], *, terminate: bool) -> None:
    process = job["process"]
    receiver = job["receiver"]
    if terminate and process.is_alive():
        process.terminate()
    process.join(timeout=1)
    if process.is_alive():
        process.terminate()
        process.join()
    try:
        receiver.close()
    except (OSError, ValueError):
        pass


def cleanup_jobs(jobs: list[dict[str, object]]) -> None:
    for job in list(jobs):
        close_job(job, terminate=True)
        jobs.remove(job)


def write_cover_artifact(
    path: Path,
    code: list[int],
    *,
    length: int,
    root: Path,
) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        normalized_code_text(code, length=length),
        encoding="ascii",
    )
    return {
        "path": display_path(path, root),
        "sha256": file_sha256(path),
    }


def solve_child_worker(
    base_formula: str,
    parent_case: dict[str, object],
    third_parent: dict[str, object],
    frontier_parent: dict[str, object],
    child: dict[str, object],
    solver_name: str,
    length: int,
    connection: object,
) -> None:
    try:
        from pysat.solvers import Solver

        build_started = time.monotonic()
        variables, clauses, metadata = build_child_formula(
            Path(base_formula),
            parent_case,
            third_parent,
            frontier_parent,
            child,
            length=length,
        )
        build_seconds = time.monotonic() - build_started
        solve_started = time.monotonic()
        with Solver(
            name=solver_name,
            bootstrap_with=clauses,
        ) as solver:
            result = solver.solve()
            model = solver.get_model() if result else None
            statistics = optional_solver_statistics(solver)
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
                "build_seconds": build_seconds,
                "clauses": len(clauses),
                "matching_clauses": metadata["matching_clauses"],
                "result": result,
                "selected": selected,
                "solve_seconds": time.monotonic() - solve_started,
                "statistics": statistics,
                "variables": variables,
            }
        )
    except BaseException as exc:
        connection.send(
            {
                "error_message": str(exc),
                "error_type": type(exc).__name__,
            }
        )
    finally:
        connection.close()


def priority_key(task: dict[str, object]) -> tuple[object, ...]:
    parent_case = task["parent_case"]
    frontier_parent = task["frontier_parent"]
    child = task["child"]
    return (
        0 if frontier_parent["matching_eligible"] else 1,
        -int(parent_case["minimum_weight"]),
        -int(parent_case["second_descriptor"]["weight"]),
        int(frontier_parent["live_child_count"]),
        str(parent_case["case_id"]),
        -int(child["earlier_word_count"]),
        int(child["parent_orbit_index"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("frontier_manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--solver", default="cadical300")
    parser.add_argument("--child-time-limit", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--minimum-distance",
        type=int,
        action="append",
    )
    parser.add_argument(
        "--parent-case-id",
        action="append",
    )
    parser.add_argument("--start-live-index", type=int)
    parser.add_argument("--end-live-index", type=int)
    parser.add_argument("--maximum-children", type=int)
    parser.add_argument(
        "--order",
        choices=("priority", "live-index"),
        default="priority",
    )
    parser.add_argument("--code-output", type=Path)
    parser.add_argument("--run-record", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args()

    if args.child_time_limit <= 0 or args.workers <= 0:
        raise SystemExit("time limit and worker count must be positive")
    if args.maximum_children is not None and args.maximum_children <= 0:
        raise SystemExit("maximum children must be positive")
    try:
        import pysat
    except ImportError as exc:
        raise SystemExit(
            "python-sat is required; install requirements-sat.txt"
        ) from exc

    root = repository_root(args.frontier_manifest)
    started_at = utc_timestamp()
    started = time.monotonic()
    git_commit = current_git_commit(root)
    git_worktree = git_worktree_state(root)
    code_hashes = {
        path: file_sha256(path)
        for path in executed_code_paths(root)
    }
    parent_manifest_path = ensure_repository_path(
        args.parent_manifest,
        root,
    )
    third_manifest_path = ensure_repository_path(
        args.third_word_manifest,
        root,
    )
    frontier_manifest_path = ensure_repository_path(
        args.frontier_manifest,
        root,
    )
    output_path = ensure_repository_path(args.output, root)
    run_record_path = ensure_repository_path(
        (
            args.run_record
            if args.run_record is not None
            else default_run_record_path(args.output)
        ),
        root,
    )
    code_output_path = ensure_repository_path(
        (
            args.code_output
            if args.code_output is not None
            else default_code_output_path(args.output)
        ),
        root,
    )
    protected_paths = {
        parent_manifest_path,
        third_manifest_path,
        frontier_manifest_path,
        output_path,
        run_record_path,
        code_output_path,
    }
    if len(protected_paths) != 6:
        raise SystemExit(
            "manifests and all output paths must be distinct"
        )
    if (
        {output_path, run_record_path, code_output_path}
        & set(code_hashes)
    ):
        raise SystemExit("an output path aliases executed source code")

    parent_manifest, parent_manifest_sha256 = load_json_snapshot(
        parent_manifest_path
    )
    third_manifest, third_manifest_sha256 = load_json_snapshot(
        third_manifest_path
    )
    frontier, frontier_manifest_sha256 = load_json_snapshot(
        frontier_manifest_path
    )
    if parent_manifest_sha256 != frontier["sources"][
        "stage1_parent_manifest"
    ]["sha256"]:
        raise SystemExit("parent manifest hash does not match the frontier")
    if third_manifest_sha256 != frontier["sources"][
        "third_word_manifest"
    ]["sha256"]:
        raise SystemExit("third-word manifest hash does not match the frontier")

    parents = {
        str(parent["case_id"]): parent
        for parent in parent_manifest["cases"]
    }
    third_parents = {
        str(parent["parent_case_id"]): parent
        for parent in third_manifest["parents"]
    }
    selected_parent_ids = (
        set(args.parent_case_id)
        if args.parent_case_id is not None
        else None
    )
    selected_distances = (
        set(args.minimum_distance)
        if args.minimum_distance is not None
        else None
    )
    tasks = []
    base_formula_hashes: dict[Path, str] = {}
    for frontier_parent in frontier["parents"]:
        formula_record = frontier_parent["constraint_profile"][
            "minimum_distance"
        ]["formula"]
        base_formula = resolve_repository_path(
            formula_record["path"],
            root,
        )
        if not base_formula.is_file():
            raise SystemExit(
                "a retained minimum-distance formula is missing"
            )
        actual_base_sha256 = file_sha256(base_formula)
        if actual_base_sha256 != formula_record["sha256"]:
            raise SystemExit(
                "a retained minimum-distance formula hash changed"
            )
        base_formula_hashes[base_formula] = actual_base_sha256
        if base_formula in protected_paths:
            raise SystemExit(
                "an output path aliases a retained base formula"
            )
    for frontier_parent in frontier["parents"]:
        if frontier_parent["status"] != "active":
            continue
        case_id = str(frontier_parent["parent_case_id"])
        parent_case = parents[case_id]
        if (
            selected_parent_ids is not None
            and case_id not in selected_parent_ids
        ):
            continue
        if (
            selected_distances is not None
            and int(parent_case["minimum_weight"])
            not in selected_distances
        ):
            continue
        base_formula = resolve_repository_path(
            frontier_parent["constraint_profile"]["minimum_distance"][
                "formula"
            ]["path"],
            root,
        )
        for child in frontier_parent["children"]:
            if child["branch_status"] != "live":
                continue
            live_index = int(child["live_child_index"])
            if (
                args.start_live_index is not None
                and live_index < args.start_live_index
            ):
                continue
            if (
                args.end_live_index is not None
                and live_index >= args.end_live_index
            ):
                continue
            tasks.append(
                {
                    "base_formula": str(base_formula),
                    "child": child,
                    "frontier_parent": frontier_parent,
                    "parent_case": parent_case,
                    "third_parent": third_parents[case_id],
                }
            )
    if not tasks:
        raise SystemExit("no live children match the requested filters")
    if args.order == "priority":
        tasks.sort(key=priority_key)
    else:
        tasks.sort(key=lambda task: int(task["child"]["live_child_index"]))
    if args.maximum_children is not None:
        tasks = tasks[: args.maximum_children]
    for task_index, task in enumerate(tasks):
        task["task_index"] = task_index

    context = multiprocessing.get_context("spawn")
    pending = list(tasks)
    active: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    sat_codes: dict[int, list[int]] = {}
    stop_launching = False

    def launch(task: dict[str, object]) -> None:
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=solve_child_worker,
            args=(
                task["base_formula"],
                task["parent_case"],
                task["third_parent"],
                task["frontier_parent"],
                task["child"],
                args.solver,
                int(parent_manifest["length"]),
                sender,
            ),
        )
        process.start()
        sender.close()
        active.append(
            {
                "process": process,
                "receiver": receiver,
                "started": time.monotonic(),
                "task": task,
            }
        )

    try:
        while pending or active:
            while (
                not stop_launching
                and pending
                and len(active) < args.workers
            ):
                launch(pending.pop(0))
            made_progress = False
            for job in list(active):
                process = job["process"]
                receiver = job["receiver"]
                task = job["task"]
                child = task["child"]
                parent_case = task["parent_case"]
                task_index = int(task["task_index"])
                elapsed = time.monotonic() - job["started"]
                payload = None
                if receiver.poll():
                    try:
                        payload = receiver.recv()
                    except EOFError:
                        payload = {
                            "error_message": (
                                "worker closed its result pipe"
                            ),
                            "error_type": "EOFError",
                        }
                elif elapsed >= args.child_time_limit:
                    close_job(job, terminate=True)
                    results.append(
                        {
                            "task_index": task_index,
                            "child_id": child["child_id"],
                            "live_child_index": child[
                                "live_child_index"
                            ],
                            "minimum_distance": parent_case[
                                "minimum_weight"
                            ],
                            "parent_case_id": parent_case["case_id"],
                            "seconds": args.child_time_limit,
                            "status": "UNKNOWN",
                            "timed_out": True,
                        }
                    )
                    active.remove(job)
                    made_progress = True
                    continue
                elif not process.is_alive():
                    close_job(job, terminate=False)
                    results.append(
                        {
                            "task_index": task_index,
                            "child_id": child["child_id"],
                            "live_child_index": child[
                                "live_child_index"
                            ],
                            "minimum_distance": parent_case[
                                "minimum_weight"
                            ],
                            "parent_case_id": parent_case["case_id"],
                            "seconds": elapsed,
                            "status": "ERROR",
                            "timed_out": False,
                            "error": "worker exited without a result",
                        }
                    )
                    active.remove(job)
                    made_progress = True
                    continue
                if payload is None:
                    continue

                close_job(job, terminate=False)
                active.remove(job)
                made_progress = True
                base_record = {
                    "task_index": task_index,
                    "child_id": child["child_id"],
                    "live_child_index": child["live_child_index"],
                    "minimum_distance": parent_case["minimum_weight"],
                    "parent_case_id": parent_case["case_id"],
                    "timed_out": False,
                }
                if "error_type" in payload:
                    results.append(
                        {
                            **base_record,
                            "status": "ERROR",
                            "seconds": elapsed,
                            "error": (
                                f"{payload['error_type']}: "
                                f"{payload['error_message']}"
                            ),
                        }
                    )
                    continue
                if payload["result"] is True:
                    decoded = list(payload["selected"])
                    if len(decoded) > 15:
                        raise RuntimeError(
                            "SAT model exceeds the size bound"
                        )
                    model_code_size = len(decoded)
                    selected = set(decoded)
                    padded = decoded + [
                        word
                        for word in range(
                            1 << int(parent_manifest["length"])
                        )
                        if word not in selected
                    ]
                    padded = padded[:15]
                    verification = verify_code(
                        padded,
                        length=int(parent_manifest["length"]),
                        radius=3,
                    )
                    if not verification.valid:
                        raise RuntimeError(
                            "SAT child decoded to an invalid cover"
                        )
                    sat_codes[task_index] = padded
                    stop_launching = True
                    pending.clear()
                    results.append(
                        {
                            **base_record,
                            "build_seconds": payload[
                                "build_seconds"
                            ],
                            "clauses": payload["clauses"],
                            "matching_clauses": payload[
                                "matching_clauses"
                            ],
                            "model_code_size": model_code_size,
                            "padded_code_size": len(padded),
                            "codewords": padded,
                            "solve_seconds": payload[
                                "solve_seconds"
                            ],
                            "solver_statistics": payload[
                                "statistics"
                            ],
                            "status": "SAT",
                            "variables": payload["variables"],
                            "verification": verification.to_dict(),
                        }
                    )
                    continue
                results.append(
                    {
                        **base_record,
                        "build_seconds": payload["build_seconds"],
                        "clauses": payload["clauses"],
                        "matching_clauses": payload[
                            "matching_clauses"
                        ],
                        "solve_seconds": payload["solve_seconds"],
                        "solver_statistics": payload["statistics"],
                        "status": "UNSAT",
                        "variables": payload["variables"],
                    }
                )
            if active and not made_progress:
                time.sleep(0.01)
    finally:
        cleanup_jobs(active)

    results.sort(key=lambda record: int(record["task_index"]))
    found_code = (
        sat_codes[min(sat_codes)]
        if sat_codes
        else None
    )
    status_counts = Counter(
        str(record["status"])
        for record in results
    )
    input_hashes = {
        parent_manifest_path: parent_manifest_sha256,
        third_manifest_path: third_manifest_sha256,
        frontier_manifest_path: frontier_manifest_sha256,
        **base_formula_hashes,
        **code_hashes,
    }
    for path, expected_sha256 in input_hashes.items():
        if file_sha256(path) != expected_sha256:
            raise RuntimeError(
                f"input changed during the run: {display_path(path, root)}"
            )
    if current_git_commit(root) != git_commit:
        raise RuntimeError("Git HEAD changed during the run")

    elapsed_seconds = time.monotonic() - started
    finished_at = utc_timestamp()
    run_id = args.run_id or (
        started_at.replace("-", "").replace(":", "")
        + "-"
        + output_path.stem
    )
    report = {
        "record_type": "third-word-child-portfolio",
        "schema_version": 1,
        "run_id": run_id,
        "run_record": display_path(run_record_path, root),
        "sources": {
            "parent_manifest": {
                "path": display_path(parent_manifest_path, root),
                "sha256": parent_manifest_sha256,
            },
            "third_word_manifest": {
                "path": display_path(third_manifest_path, root),
                "sha256": third_manifest_sha256,
            },
            "frontier_manifest": {
                "path": display_path(frontier_manifest_path, root),
                "sha256": frontier_manifest_sha256,
            },
            "base_formulas": [
                {
                    "path": display_path(path, root),
                    "sha256": digest,
                }
                for path, digest in sorted(
                    base_formula_hashes.items(),
                    key=lambda item: display_path(item[0], root),
                )
            ],
            "executed_code": [
                {
                    "path": display_path(path, root),
                    "sha256": input_hashes[path],
                }
                for path in executed_code_paths(root)
            ],
        },
        "solver": args.solver,
        "python_sat_version": pysat.__version__,
        "child_time_limit_seconds": args.child_time_limit,
        "workers": args.workers,
        "order": args.order,
        "filters": {
            "end_live_index": args.end_live_index,
            "maximum_children": args.maximum_children,
            "minimum_distances": (
                sorted(selected_distances)
                if selected_distances is not None
                else None
            ),
            "parent_case_ids": (
                sorted(selected_parent_ids)
                if selected_parent_ids is not None
                else None
            ),
            "start_live_index": args.start_live_index,
        },
        "scheduled_child_count": len(tasks),
        "completed_child_count": len(results),
        "status_counts": {
            status: status_counts[status]
            for status in sorted(status_counts)
        },
        "found_cover": found_code is not None,
        "proof_traces_available": False,
        "process_timeout_enforced": True,
        "stopped_launching_after_cover": stop_launching,
        "elapsed_seconds": elapsed_seconds,
        "results": results,
    }
    artifacts = []
    if found_code is not None:
        artifacts.append(
            write_cover_artifact(
                code_output_path,
                found_code,
                length=int(parent_manifest["length"]),
                root=root,
            )
        )
    elif code_output_path.exists():
        if not code_output_path.is_file():
            raise RuntimeError("cover output exists and is not a file")
        code_output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    artifacts.insert(
        0,
        {
            "path": display_path(output_path, root),
            "sha256": file_sha256(output_path),
        },
    )
    canonical_command = [
        "env",
        "PYTHONPATH=src:tools",
        "python",
        "tools/run_third_word_child_portfolio.py",
        display_path(parent_manifest_path, root),
        display_path(third_manifest_path, root),
        display_path(frontier_manifest_path, root),
        display_path(output_path, root),
        "--solver",
        args.solver,
        "--child-time-limit",
        str(args.child_time_limit),
        "--workers",
        str(args.workers),
        "--order",
        args.order,
        "--run-record",
        display_path(run_record_path, root),
        "--run-id",
        run_id,
    ]
    for distance in sorted(selected_distances or ()):
        canonical_command.extend(
            ["--minimum-distance", str(distance)]
        )
    for case_id in sorted(selected_parent_ids or ()):
        canonical_command.extend(["--parent-case-id", case_id])
    if args.start_live_index is not None:
        canonical_command.extend(
            ["--start-live-index", str(args.start_live_index)]
        )
    if args.end_live_index is not None:
        canonical_command.extend(
            ["--end-live-index", str(args.end_live_index)]
        )
    if args.maximum_children is not None:
        canonical_command.extend(
            ["--maximum-children", str(args.maximum_children)]
        )
    canonical_command.extend(
        ["--code-output", display_path(code_output_path, root)]
    )
    if status_counts["ERROR"]:
        run_result = "failed"
    elif status_counts["UNKNOWN"] and found_code is None:
        run_result = "inconclusive"
    else:
        run_result = "completed"
    run_record = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "git_commit": git_commit,
        "command": canonical_command,
        "environment": {
            "multiprocessing_start_method": "spawn",
            "python": sys.version.split()[0],
            "python_sat": pysat.__version__,
            "solver": args.solver,
            "git_worktree": git_worktree,
        },
        "inputs": [
            {
                "path": display_path(path, root),
                "sha256": digest,
            }
            for path, digest in sorted(
                input_hashes.items(),
                key=lambda item: display_path(item[0], root),
            )
        ],
        "result": run_result,
        "metrics": {
            "completed_child_count": len(results),
            "elapsed_seconds": elapsed_seconds,
            "found_cover": found_code is not None,
            "scheduled_child_count": len(tasks),
            "unknown_child_count": status_counts["UNKNOWN"],
            "unsat_child_count": status_counts["UNSAT"],
        },
        "artifacts": artifacts,
        "notes": (
            "Solver statuses are exploratory. UNSAT results have no "
            "retained proof trace and are not mathematical closures."
        ),
    }
    run_record_path.parent.mkdir(parents=True, exist_ok=True)
    run_record_path.write_text(
        json.dumps(run_record, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(
        json.dumps(
            {
                "completed_child_count": len(results),
                "elapsed_seconds": elapsed_seconds,
                "found_cover": report["found_cover"],
                "output": display_path(output_path, root),
                "run_record": display_path(run_record_path, root),
                "status_counts": report["status_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    if status_counts["ERROR"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
