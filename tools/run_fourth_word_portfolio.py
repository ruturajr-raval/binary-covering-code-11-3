#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

from covering_code.core import normalized_code_text, verify_code
from fourth_word_symmetry import fourth_orbits, orbit_manifest_digest
from generate_third_word_child_formula import (
    build_child_formula,
    display_path,
    ensure_repository_path,
    find_parent_and_child,
    resolve_repository_path,
)
from run_third_word_child_portfolio import (
    close_job,
    cleanup_jobs,
    current_git_commit,
    default_code_output_path,
    default_run_record_path,
    file_sha256,
    git_worktree_state,
    load_json_snapshot,
    optional_solver_statistics,
    utc_timestamp,
)
from third_word_symmetry import weight


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def executed_code_paths(root: Path) -> tuple[Path, ...]:
    return (
        root / "tools/run_fourth_word_portfolio.py",
        root / "tools/run_third_word_child_portfolio.py",
        root / "tools/generate_third_word_child_formula.py",
        root / "tools/fourth_word_symmetry.py",
        root / "tools/third_word_symmetry.py",
        root / "tools/matching_constraints.py",
        root / "tools/run_two_word_portfolio.py",
        root / "tools/audit_covering_cnf.py",
        root / "src/covering_code/__init__.py",
        root / "src/covering_code/core.py",
        root / "src/covering_code/cnf.py",
    )


def statistics_delta(
    before: dict[str, int] | None,
    after: dict[str, int] | None,
) -> dict[str, int] | None:
    if before is None or after is None:
        return None
    return {
        key: int(after.get(key, 0)) - int(before.get(key, 0))
        for key in sorted(set(before) | set(after))
    }


def branch_digest(branch: dict[str, object]) -> str:
    identity = {
        key: value
        for key, value in branch.items()
        if key != "branch_sha256"
    }
    payload = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def reconstruct_branches(
    parent_case: dict[str, object],
    child: dict[str, object],
    grouped: list[tuple[tuple[int, ...], list[int]]],
) -> list[dict[str, object]]:
    branches = []
    earlier_word_count = 0
    for orbit_index, (descriptor, words) in enumerate(grouped):
        canonical_word = min(words)
        branch = {
            "branch_id": (
                f"{child['child_id']}::fourth-{orbit_index:03d}"
            ),
            "parent_child_id": child["child_id"],
            "fourth_orbit_index": orbit_index,
            "descriptor": list(descriptor),
            "canonical_word": canonical_word,
            "orbit_size": len(words),
            "earlier_word_count": earlier_word_count,
            "constraint_units": {
                "selected_word_literal": canonical_word + 1,
                "excluded_earlier_word_count": earlier_word_count,
            },
            "fixed_word_distances": {
                "zero": weight(canonical_word),
                "first": weight(
                    canonical_word ^ int(parent_case["first_word"])
                ),
                "second": weight(
                    canonical_word ^ int(parent_case["second_word"])
                ),
                "third": weight(
                    canonical_word ^ int(child["canonical_word"])
                ),
            },
        }
        branch["branch_sha256"] = branch_digest(branch)
        branches.append(branch)
        earlier_word_count += len(words)
    return branches


def validate_fourth_child(
    parent_case: dict[str, object],
    frontier_parent: dict[str, object],
    child: dict[str, object],
    fourth_child: dict[str, object],
    *,
    length: int,
) -> tuple[
    list[tuple[tuple[int, ...], list[int]]],
    list[dict[str, object]],
]:
    grouped, classification = fourth_orbits(
        parent_case,
        child,
        length=length,
        matching=bool(frontier_parent["matching_eligible"]),
    )
    branches = reconstruct_branches(
        parent_case,
        child,
        grouped,
    )
    if fourth_child["parent_child_id"] != child["child_id"]:
        raise RuntimeError("fourth-word child identity mismatch")
    if fourth_child["classification"] != classification:
        raise RuntimeError("fourth-word classification mismatch")
    if int(fourth_child["fourth_orbit_count"]) != len(grouped):
        raise RuntimeError("fourth-word orbit count mismatch")
    if fourth_child["fourth_orbit_sha256"] != orbit_manifest_digest(
        branches
    ):
        raise RuntimeError("fourth-word orbit digest mismatch")
    if fourth_child["branches"] != branches:
        raise RuntimeError("fourth-word branch manifest mismatch")
    return grouped, branches


def aliases_existing_file(
    path: Path,
    sources: set[Path],
) -> bool:
    return path.exists() and any(
        os.path.samefile(path, source)
        for source in sources
    )


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def worker_failure_records(
    job: dict[str, object],
    completed: set[int],
    child_id: str,
    error: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    worker_error = {
        "parent_child_id": child_id,
        "error": error,
    }
    task_errors = []
    for task in job["tasks"]:
        if int(task["task_index"]) in completed:
            continue
        task_errors.append(
            {
                "task_index": task["task_index"],
                "branch_id": task["branch"]["branch_id"],
                "parent_child_id": child_id,
                "fourth_orbit_index": task["branch"][
                    "fourth_orbit_index"
                ],
                "status": "ERROR",
                "timed_out": False,
                "error": error,
            }
        )
    return worker_error, task_errors


def solve_child_worker(
    base_formula: str,
    parent_case: dict[str, object],
    third_parent: dict[str, object],
    frontier_parent: dict[str, object],
    child: dict[str, object],
    fourth_child: dict[str, object],
    tasks: list[dict[str, object]],
    solver_name: str,
    branch_time_limit: float,
    length: int,
    connection: object,
) -> None:
    try:
        from pysat.solvers import Solver

        build_started = time.monotonic()
        variables, clauses, child_metadata = build_child_formula(
            Path(base_formula),
            parent_case,
            third_parent,
            frontier_parent,
            child,
            length=length,
        )
        grouped, expected_branches = validate_fourth_child(
            parent_case,
            frontier_parent,
            child,
            fourth_child,
            length=length,
        )
        build_seconds = time.monotonic() - build_started

        with Solver(
            name=solver_name,
            bootstrap_with=clauses,
        ) as solver:
            for task in tasks:
                branch = task["branch"]
                orbit_index = int(branch["fourth_orbit_index"])
                if orbit_index < 0 or orbit_index >= len(grouped):
                    raise RuntimeError(
                        f"{branch['branch_id']}: orbit index is outside "
                        "the child"
                    )
                if branch != expected_branches[orbit_index]:
                    raise RuntimeError(
                        f"{branch['branch_id']}: branch identity mismatch"
                    )
                descriptor, words = grouped[orbit_index]
                earlier_words = [
                    word
                    for _, orbit_words in grouped[:orbit_index]
                    for word in orbit_words
                ]
                canonical_word = min(words)
                for key, value in {
                    "descriptor": list(descriptor),
                    "canonical_word": canonical_word,
                    "orbit_size": len(words),
                    "earlier_word_count": len(earlier_words),
                }.items():
                    if branch[key] != value:
                        raise RuntimeError(
                            f"{branch['branch_id']}: {key} mismatch"
                        )
                assumptions = [canonical_word + 1]
                assumptions.extend(
                    -(word + 1) for word in earlier_words
                )
                before = optional_solver_statistics(solver)
                timer = threading.Timer(
                    branch_time_limit,
                    solver.interrupt,
                )
                solve_started = time.monotonic()
                timer.start()
                try:
                    result = solver.solve_limited(
                        assumptions=assumptions,
                        expect_interrupt=True,
                    )
                finally:
                    timer.cancel()
                    timer.join()
                    solver.clear_interrupt()
                solve_seconds = time.monotonic() - solve_started
                after = optional_solver_statistics(solver)
                selected = None
                if result is True:
                    model = solver.get_model()
                    positive = {
                        literal for literal in model if literal > 0
                    }
                    selected = [
                        word
                        for word in range(1 << length)
                        if word + 1 in positive
                    ]
                connection.send(
                    {
                        "kind": "result",
                        "task_index": task["task_index"],
                        "branch_id": branch["branch_id"],
                        "parent_child_id": child["child_id"],
                        "fourth_orbit_index": orbit_index,
                        "result": result,
                        "selected": selected,
                        "solve_seconds": solve_seconds,
                        "statistics": statistics_delta(before, after),
                        "assumption_count": len(assumptions),
                        "variables": variables,
                        "clauses": (
                            len(clauses) + len(assumptions)
                        ),
                        "child_build_seconds": build_seconds,
                        "matching_clauses": child_metadata[
                            "matching_clauses"
                        ],
                    }
                )
                if result is True:
                    break
        connection.send(
            {
                "kind": "done",
                "parent_child_id": child["child_id"],
            }
        )
    except BaseException as exc:
        try:
            connection.send(
                {
                    "kind": "error",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "parent_child_id": child["child_id"],
                }
            )
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()


def canonical_command(
    args: argparse.Namespace,
    *,
    root: Path,
    output_path: Path,
    run_record_path: Path,
    code_output_path: Path,
    run_id: str,
) -> list[str]:
    command = [
        "env",
        "PYTHONPATH=src:tools",
        "python",
        "tools/run_fourth_word_portfolio.py",
        display_path(args.parent_manifest, root),
        display_path(args.third_word_manifest, root),
        display_path(args.child_frontier, root),
        display_path(args.fourth_frontier, root),
        display_path(output_path, root),
        "--solver",
        args.solver,
        "--branch-time-limit",
        str(args.branch_time_limit),
        "--workers",
        str(args.workers),
        "--order",
        args.order,
        "--run-record",
        display_path(run_record_path, root),
        "--run-id",
        run_id,
        "--code-output",
        display_path(code_output_path, root),
    ]
    for child_id in sorted(args.parent_child_id or ()):
        command.extend(["--parent-child-id", child_id])
    if args.start_fourth_index is not None:
        command.extend(
            ["--start-fourth-index", str(args.start_fourth_index)]
        )
    if args.end_fourth_index is not None:
        command.extend(
            ["--end-fourth-index", str(args.end_fourth_index)]
        )
    if args.maximum_branches is not None:
        command.extend(
            ["--maximum-branches", str(args.maximum_branches)]
        )
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("child_frontier", type=Path)
    parser.add_argument("fourth_frontier", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--solver",
        choices=("glucose4", "glucose42"),
        default="glucose4",
    )
    parser.add_argument("--branch-time-limit", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--parent-child-id", action="append")
    parser.add_argument("--start-fourth-index", type=int)
    parser.add_argument("--end-fourth-index", type=int)
    parser.add_argument("--maximum-branches", type=int)
    parser.add_argument(
        "--order",
        choices=("manifest", "reverse-prefix"),
        default="reverse-prefix",
    )
    parser.add_argument("--run-record", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--code-output", type=Path)
    args = parser.parse_args()

    if args.branch_time_limit <= 0 or args.workers <= 0:
        raise SystemExit("time limit and worker count must be positive")
    if args.maximum_branches is not None and args.maximum_branches <= 0:
        raise SystemExit("maximum branches must be positive")
    try:
        import pysat
    except ImportError as exc:
        raise SystemExit(
            "python-sat is required; install requirements-sat.txt"
        ) from exc

    root = repository_root()
    started_at = utc_timestamp()
    started = time.monotonic()
    git_commit = current_git_commit(root)
    git_worktree = git_worktree_state(root)
    code_hashes = {
        path: file_sha256(path)
        for path in executed_code_paths(root)
    }
    parent_path = ensure_repository_path(args.parent_manifest, root)
    third_path = ensure_repository_path(args.third_word_manifest, root)
    child_frontier_path = ensure_repository_path(
        args.child_frontier,
        root,
    )
    fourth_frontier_path = ensure_repository_path(
        args.fourth_frontier,
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
    all_paths = {
        parent_path,
        third_path,
        child_frontier_path,
        fourth_frontier_path,
        output_path,
        run_record_path,
        code_output_path,
    }
    if len(all_paths) != 7:
        raise SystemExit("sources and outputs must use distinct paths")
    source_paths = {
        parent_path,
        third_path,
        child_frontier_path,
        fourth_frontier_path,
    }
    if not all(path.is_file() for path in source_paths):
        raise SystemExit("source paths must be regular files")
    source_list = list(source_paths)
    if any(
        os.path.samefile(left, right)
        for index, left in enumerate(source_list)
        for right in source_list[index + 1:]
    ):
        raise SystemExit("source paths alias the same file")
    if any(
        aliases_existing_file(output, source_paths)
        for output in (
            output_path,
            run_record_path,
            code_output_path,
        )
    ):
        raise SystemExit("an output path aliases a source file")
    output_paths = {
        output_path,
        run_record_path,
        code_output_path,
    }
    existing_outputs = [
        path for path in output_paths if path.exists()
    ]
    if any(not path.is_file() for path in existing_outputs):
        raise SystemExit("output paths must be regular files")
    if any(
        os.path.samefile(left, right)
        for index, left in enumerate(existing_outputs)
        for right in existing_outputs[index + 1:]
    ):
        raise SystemExit("output paths alias the same file")
    executed_sources = set(code_hashes)
    if (
        output_paths & executed_sources
        or any(
            aliases_existing_file(output, executed_sources)
            for output in output_paths
        )
    ):
        raise SystemExit("an output path aliases executed source code")

    parent_manifest, parent_sha256 = load_json_snapshot(parent_path)
    third_manifest, third_sha256 = load_json_snapshot(third_path)
    child_frontier, child_frontier_sha256 = load_json_snapshot(
        child_frontier_path
    )
    fourth_frontier, fourth_frontier_sha256 = load_json_snapshot(
        fourth_frontier_path
    )
    if parent_sha256 != child_frontier["sources"][
        "stage1_parent_manifest"
    ]["sha256"]:
        raise SystemExit("parent manifest does not match child frontier")
    if third_sha256 != child_frontier["sources"][
        "third_word_manifest"
    ]["sha256"]:
        raise SystemExit("third manifest does not match child frontier")
    expected_fourth_sources = {
        "parent_manifest": parent_sha256,
        "third_word_manifest": third_sha256,
        "child_frontier": child_frontier_sha256,
    }
    for label, digest in expected_fourth_sources.items():
        if fourth_frontier["sources"][label]["sha256"] != digest:
            raise SystemExit(
                f"{label} does not match fourth-word frontier"
            )

    selected_child_ids = (
        set(args.parent_child_id)
        if args.parent_child_id is not None
        else None
    )
    if (
        args.parent_child_id is not None
        and len(selected_child_ids) != len(args.parent_child_id)
    ):
        raise SystemExit("selected child identifiers must be unique")
    parents = {
        str(parent["case_id"]): parent
        for parent in parent_manifest["cases"]
    }
    third_parents = {
        str(parent["parent_case_id"]): parent
        for parent in third_manifest["parents"]
    }
    base_formula_hashes: dict[Path, str] = {}
    for frontier_parent in child_frontier["parents"]:
        formula_record = frontier_parent["constraint_profile"][
            "minimum_distance"
        ]["formula"]
        path = resolve_repository_path(formula_record["path"], root)
        digest = file_sha256(path)
        if digest != formula_record["sha256"]:
            raise SystemExit("retained base formula hash mismatch")
        base_formula_hashes[path] = digest
    protected_outputs = output_paths
    if protected_outputs & set(base_formula_hashes):
        raise SystemExit("an output path aliases a base formula")
    if any(
        aliases_existing_file(output, set(base_formula_hashes))
        for output in protected_outputs
    ):
        raise SystemExit("an output path aliases a base formula")

    tasks = []
    child_contexts = {}
    for fourth_child in fourth_frontier["children"]:
        child_id = str(fourth_child["parent_child_id"])
        if (
            selected_child_ids is not None
            and child_id not in selected_child_ids
        ):
            continue
        frontier_parent, child = find_parent_and_child(
            child_frontier,
            child_id,
        )
        case_id = str(frontier_parent["parent_case_id"])
        parent_case = parents[case_id]
        third_parent = third_parents[case_id]
        validate_fourth_child(
            parent_case,
            frontier_parent,
            child,
            fourth_child,
            length=int(parent_manifest["length"]),
        )
        base_formula = resolve_repository_path(
            frontier_parent["constraint_profile"][
                "minimum_distance"
            ]["formula"]["path"],
            root,
        )
        child_contexts[child_id] = {
            "base_formula": str(base_formula),
            "parent_case": parent_case,
            "third_parent": third_parent,
            "frontier_parent": frontier_parent,
            "child": child,
            "fourth_child": fourth_child,
        }
        for branch in fourth_child["branches"]:
            orbit_index = int(branch["fourth_orbit_index"])
            if (
                args.start_fourth_index is not None
                and orbit_index < args.start_fourth_index
            ):
                continue
            if (
                args.end_fourth_index is not None
                and orbit_index >= args.end_fourth_index
            ):
                continue
            tasks.append(
                {
                    "parent_child_id": child_id,
                    "live_child_index": child["live_child_index"],
                    "branch": branch,
                }
            )
    if selected_child_ids is not None:
        missing = selected_child_ids - set(child_contexts)
        if missing:
            raise SystemExit(
                "unknown fourth-frontier child ids: "
                + ", ".join(sorted(missing))
            )
    if not tasks:
        raise SystemExit("no fourth-word branches match the filters")
    if args.order == "manifest":
        tasks.sort(
            key=lambda task: (
                int(task["live_child_index"]),
                int(task["branch"]["fourth_orbit_index"]),
            )
        )
    else:
        tasks.sort(
            key=lambda task: (
                int(task["live_child_index"]),
                -int(task["branch"]["earlier_word_count"]),
                int(task["branch"]["fourth_orbit_index"]),
            )
        )
    if args.maximum_branches is not None:
        tasks = tasks[: args.maximum_branches]
    for task_index, task in enumerate(tasks):
        task["task_index"] = task_index

    grouped_tasks: dict[str, list[dict[str, object]]] = {}
    for task in tasks:
        grouped_tasks.setdefault(
            str(task["parent_child_id"]),
            [],
        ).append(task)
    pending = [
        {
            **child_contexts[child_id],
            "tasks": child_tasks,
        }
        for child_id, child_tasks in grouped_tasks.items()
    ]
    context = multiprocessing.get_context("spawn")
    active: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    worker_errors: list[dict[str, object]] = []
    completed_by_child: dict[str, set[int]] = {
        child_id: set() for child_id in grouped_tasks
    }
    sat_codes: dict[int, list[int]] = {}

    def launch(job: dict[str, object]) -> None:
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=solve_child_worker,
            args=(
                job["base_formula"],
                job["parent_case"],
                job["third_parent"],
                job["frontier_parent"],
                job["child"],
                job["fourth_child"],
                job["tasks"],
                args.solver,
                args.branch_time_limit,
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
                "job": job,
                "done": False,
            }
        )

    try:
        found_cover = False
        while (pending or active) and not found_cover:
            while pending and len(active) < args.workers:
                launch(pending.pop(0))
            made_progress = False
            for active_job in list(active):
                process = active_job["process"]
                receiver = active_job["receiver"]
                job = active_job["job"]
                child_id = str(job["child"]["child_id"])
                while receiver.poll():
                    try:
                        payload = receiver.recv()
                    except EOFError:
                        break
                    made_progress = True
                    if payload["kind"] == "result":
                        task_index = int(payload["task_index"])
                        completed_by_child[child_id].add(task_index)
                        status = (
                            "SAT"
                            if payload["result"] is True
                            else (
                                "UNSAT"
                                if payload["result"] is False
                                else "UNKNOWN"
                            )
                        )
                        record = {
                            key: value
                            for key, value in payload.items()
                            if key
                            not in {
                                "kind",
                                "result",
                                "selected",
                            }
                        }
                        record["status"] = status
                        record["timed_out"] = (
                            payload["result"] is None
                        )
                        if status == "SAT":
                            decoded = list(payload["selected"])
                            if len(decoded) > 15:
                                raise RuntimeError(
                                    "SAT model exceeds size bound"
                                )
                            selected = set(decoded)
                            padded = decoded + [
                                word
                                for word in range(
                                    1
                                    << int(parent_manifest["length"])
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
                                    "SAT branch decoded invalid cover"
                                )
                            record["model_code_size"] = len(decoded)
                            record["padded_code_size"] = len(padded)
                            record["codewords"] = padded
                            record["verification"] = (
                                verification.to_dict()
                            )
                            sat_codes[task_index] = padded
                            found_cover = True
                        results.append(record)
                    elif payload["kind"] == "done":
                        active_job["done"] = True
                    else:
                        error = (
                            f"{payload['error_type']}: "
                            f"{payload['error_message']}"
                        )
                        worker_error, task_errors = (
                            worker_failure_records(
                                job,
                                completed_by_child[child_id],
                                child_id,
                                error,
                            )
                        )
                        worker_errors.append(worker_error)
                        results.extend(task_errors)
                        active_job["done"] = True
                if active_job["done"] or not process.is_alive():
                    if not active_job["done"]:
                        worker_error, task_errors = (
                            worker_failure_records(
                                job,
                                completed_by_child[child_id],
                                child_id,
                                "worker exited without completion",
                            )
                        )
                        worker_errors.append(worker_error)
                        results.extend(task_errors)
                    close_job(active_job, terminate=False)
                    active.remove(active_job)
                    made_progress = True
            if active and not made_progress:
                time.sleep(0.02)
    finally:
        cleanup_jobs(active)

    results.sort(key=lambda record: int(record["task_index"]))
    found_code = (
        sat_codes[min(sat_codes)]
        if sat_codes
        else None
    )
    status_counts = Counter(
        str(record["status"]) for record in results
    )
    input_hashes = {
        parent_path: parent_sha256,
        third_path: third_sha256,
        child_frontier_path: child_frontier_sha256,
        fourth_frontier_path: fourth_frontier_sha256,
        **base_formula_hashes,
        **code_hashes,
    }
    for path, digest in input_hashes.items():
        if file_sha256(path) != digest:
            raise RuntimeError(
                f"input changed during run: {display_path(path, root)}"
            )
    if current_git_commit(root) != git_commit:
        raise RuntimeError("Git HEAD changed during run")

    elapsed_seconds = time.monotonic() - started
    finished_at = utc_timestamp()
    run_id = args.run_id or (
        started_at.replace("-", "").replace(":", "")
        + "-"
        + output_path.stem
    )
    report = {
        "record_type": "fourth-word-portfolio",
        "schema_version": 1,
        "run_id": run_id,
        "run_record": display_path(run_record_path, root),
        "sources": {
            "parent_manifest": {
                "path": display_path(parent_path, root),
                "sha256": parent_sha256,
            },
            "third_word_manifest": {
                "path": display_path(third_path, root),
                "sha256": third_sha256,
            },
            "child_frontier": {
                "path": display_path(child_frontier_path, root),
                "sha256": child_frontier_sha256,
            },
            "fourth_frontier": {
                "path": display_path(fourth_frontier_path, root),
                "sha256": fourth_frontier_sha256,
            },
        },
        "solver": args.solver,
        "python_sat_version": pysat.__version__,
        "branch_interrupt_after_seconds": args.branch_time_limit,
        "interrupt_enforcement": "solver-cooperative",
        "workers": args.workers,
        "order": args.order,
        "incremental_solver_reuse": True,
        "proof_traces_available": False,
        "scheduled_branch_count": len(tasks),
        "completed_branch_count": len(results),
        "status_counts": {
            status: status_counts[status]
            for status in sorted(status_counts)
        },
        "found_cover": found_code is not None,
        "elapsed_seconds": elapsed_seconds,
        "worker_errors": worker_errors,
        "results": results,
    }
    report_text = json.dumps(
        report,
        indent=2,
        sort_keys=True,
    ) + "\n"
    artifacts = [
        {
            "path": display_path(output_path, root),
            "sha256": hashlib.sha256(
                report_text.encode("ascii")
            ).hexdigest(),
        },
    ]
    cover_text = None
    if found_code is not None:
        cover_text = normalized_code_text(
            found_code,
            length=int(parent_manifest["length"]),
        )
        artifacts.append(
            {
                "path": display_path(code_output_path, root),
                "sha256": hashlib.sha256(
                    cover_text.encode("ascii")
                ).hexdigest(),
            }
        )
    if worker_errors or status_counts["ERROR"]:
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
        "command": canonical_command(
            args,
            root=root,
            output_path=output_path,
            run_record_path=run_record_path,
            code_output_path=code_output_path,
            run_id=run_id,
        ),
        "environment": {
            "git_worktree": git_worktree,
            "multiprocessing_start_method": "spawn",
            "python": sys.version.split()[0],
            "python_sat": pysat.__version__,
            "solver": args.solver,
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
            "completed_branch_count": len(results),
            "elapsed_seconds": elapsed_seconds,
            "found_cover": found_code is not None,
            "scheduled_branch_count": len(tasks),
            "unknown_branch_count": status_counts["UNKNOWN"],
            "unsat_branch_count": status_counts["UNSAT"],
            "worker_error_count": len(worker_errors),
        },
        "artifacts": artifacts,
        "notes": (
            "Solver statuses are exploratory. UNSAT results under "
            "assumptions have no retained proof trace. The per-branch "
            "threshold requests a cooperative solver interrupt and is not "
            "a strict wall-clock limit."
        ),
    }
    run_record_text = json.dumps(
        run_record,
        indent=2,
        sort_keys=True,
    ) + "\n"
    run_record_path.unlink(missing_ok=True)
    if cover_text is None:
        code_output_path.unlink(missing_ok=True)
    else:
        atomic_write_text(code_output_path, cover_text)
    atomic_write_text(output_path, report_text)
    atomic_write_text(run_record_path, run_record_text)
    print(
        json.dumps(
            {
                "completed_branch_count": len(results),
                "elapsed_seconds": elapsed_seconds,
                "found_cover": found_code is not None,
                "output": display_path(output_path, root),
                "run_record": display_path(run_record_path, root),
                "status_counts": report["status_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if worker_errors or status_counts["ERROR"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
