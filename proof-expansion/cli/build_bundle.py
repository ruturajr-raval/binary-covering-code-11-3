#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def isolate_python_bytecode() -> None:
    if sys.flags.isolated != 1:
        raise RuntimeError(
            "certification CLI requires Python isolated mode (-I)"
        )
    root = Path(__file__).resolve().parents[2]
    work = root / "proof-expansion/work"
    if work.is_symlink():
        raise RuntimeError("proof-expansion work path is a symbolic link")
    work.mkdir(parents=True, exist_ok=True)
    cache_parent = work / "python-bytecode"
    if cache_parent.is_symlink():
        raise RuntimeError("Python bytecode cache path is a symbolic link")
    cache_parent.mkdir(exist_ok=True)
    cache = Path(
        tempfile.mkdtemp(dir=cache_parent, prefix=".run.")
    )
    os.environ["PYTHONPYCACHEPREFIX"] = str(cache)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.pycache_prefix = str(cache)
    sys.dont_write_bytecode = True
    sys.path[:0] = [
        str(root / "proof-expansion/src"),
        str(root / "src"),
        str(root / "tools"),
    ]
    atexit.register(shutil.rmtree, cache, ignore_errors=True)


isolate_python_bytecode()

from bootstrap_drat_trim import validate_pinned_checkout
from fourth_word_drat.bundle import (
    authenticated_file_sha256,
    build_cases,
    clean_stale_bundle_staging,
    DEFAULT_MIN_FREE_BYTES,
    directory_sha256,
    file_sha256,
    load_authenticated_json,
    python_tree_record,
    promote_bundle,
    recover_promotion,
    require_free_space,
    require_path_separation,
    run_prerequisite_audits,
    solver_environment_record,
    stage_bundle,
    workspace_free_space_requirement,
)
from fourth_word_drat.proof_core import (
    DEFAULT_MAX_CHECKER_OUTPUT_BYTES,
    DEFAULT_MAX_CHECKER_SECONDS,
    DEFAULT_MAX_MEMORY_BYTES,
    DEFAULT_MAX_RAW_PROOF_BYTES,
    DEFAULT_MAX_RETAINED_PROOF_BYTES,
    DEFAULT_MAX_SOLVE_SECONDS,
    display_path,
    repository_path,
    require_regular_single_link,
)
from repository_lock import acquire_repository_lock


DEFAULT_PLAN = Path(
    "proof-expansion/evidence/fourth-word-solver-drat-plan-v2.json"
)
DEFAULT_WORKSPACE = Path(
    "proof-expansion/work/fourth-word-solver-drat-v2"
)
DEFAULT_PROOF_DIRECTORY = Path(
    "proof-expansion/evidence/proofs/fourth-word-solver-drat-v2"
)
DEFAULT_INDEX = Path(
    "proof-expansion/evidence/fourth-word-solver-drat-index-v2.json"
)
DEFAULT_JOURNAL = Path(
    "proof-expansion/evidence/.fourth-word-solver-drat-promotion-v2.json"
)
CHECKER_COMMIT = "2e3b2dc0ecf938addbd779d42877b6ed69d9a985"
PIPELINE_FILES = (
    Path("proof-expansion/Makefile"),
    Path("proof-expansion/cli/bootstrap_checker.py"),
    Path("proof-expansion/cli/audit_plan.py"),
    Path("proof-expansion/cli/audit_bundle.py"),
    Path("proof-expansion/cli/build_bundle.py"),
    Path("proof-expansion/cli/generate_plan.py"),
    Path("proof-expansion/cli/prove_formula.py"),
    Path("proof-expansion/src/fourth_word_drat/__init__.py"),
    Path("proof-expansion/src/fourth_word_drat/bundle.py"),
    Path("proof-expansion/src/fourth_word_drat/proof_core.py"),
    Path("proof-expansion/src/fourth_word_drat/secure_io.py"),
    Path("Makefile"),
    Path("requirements-proof.txt"),
    Path("requirements-replay.txt"),
    Path("requirements-sat.txt"),
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_WORKSPACE,
    )
    parser.add_argument(
        "--proof-directory",
        type=Path,
        default=DEFAULT_PROOF_DIRECTORY,
    )
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--checker",
        type=Path,
        default=Path("build/drat-trim-src/drat-trim"),
    )
    parser.add_argument("--checker-commit", default=CHECKER_COMMIT)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--workspace-only", action="store_true")
    args = parser.parse_args()

    if args.workers < 1 or args.workers > 2:
        raise SystemExit("workers must be between 1 and 2")
    if args.case_id and not args.workspace_only:
        raise SystemExit("--case-id requires --workspace-only")

    root = repository_root()
    plan_path = repository_path(args.plan, root)
    workspace = repository_path(args.workspace, root)
    proof_directory = repository_path(args.proof_directory, root)
    output_path = repository_path(args.index, root)
    journal_path = repository_path(args.journal, root)
    checker = repository_path(args.checker, root)
    require_path_separation(
        {
            "plan": plan_path,
            "workspace": workspace,
            "proof_directory": proof_directory,
            "index": output_path,
            "journal": journal_path,
            "checker": checker,
        }
    )
    repository_lock = acquire_repository_lock(root)
    atexit.register(repository_lock.close)
    require_regular_single_link(plan_path, "DRAT proof plan")
    require_regular_single_link(checker, "proof checker")
    if args.checker_commit != CHECKER_COMMIT:
        raise SystemExit("checker commit is not pinned")
    validate_pinned_checkout(
        checker.parent,
        args.checker_commit,
        allowed_untracked={"drat-trim"},
    )
    checker_sha256 = authenticated_file_sha256(
        checker,
        "proof checker",
    )
    plan, plan_sha256 = load_authenticated_json(
        plan_path,
        "DRAT proof plan",
    )
    if (
        plan.get("record_type") != "fourth-word-drat-proof-plan"
        or plan.get("schema_version") != 2
        or plan.get("case_count") != 140
    ):
        raise SystemExit("DRAT proof plan is invalid")

    all_cases = list(plan["cases"])
    if args.case_id:
        requested = set(args.case_id)
        cases = [
            case
            for case in all_cases
            if case["branch_id"] in requested
        ]
        if {case["branch_id"] for case in cases} != requested:
            raise SystemExit("one or more requested case identifiers are unknown")
    else:
        cases = all_cases

    environment = dict(os.environ)
    required_python_path = os.pathsep.join(
        ["proof-expansion/src", "src", "tools"]
    )
    environment["PYTHONPATH"] = required_python_path
    run_prerequisite_audits(
        root=root,
        plan_path=plan_path,
        expected_plan_sha256=plan_sha256,
        python_command=args.python,
        environment=environment,
    )
    pipeline_hashes = {
        display_path(path, root): authenticated_file_sha256(
            root / path,
            "pipeline file",
        )
        for path in PIPELINE_FILES
    }
    input_hashes = {
        plan_path: plan_sha256,
        checker: checker_sha256,
        **{
            root / path: digest
            for path, digest in pipeline_hashes.items()
        },
    }
    initial_python_tree = python_tree_record(root)
    solver_environment = solver_environment_record(
        args.python,
        environment=environment,
        root=root,
    )
    for source in plan["sources"].values():
        source_path = repository_path(Path(source["path"]), root)
        if (
            authenticated_file_sha256(source_path, "plan source")
            != source["sha256"]
        ):
            raise SystemExit(
                f"plan source changed: {source['path']}"
            )
        input_hashes[source_path] = source["sha256"]

    recovery = recover_promotion(
        root=root,
        proof_directory=proof_directory,
        output_path=output_path,
        journal_path=journal_path,
    )
    clean_stale_bundle_staging(proof_directory, output_path)
    if proof_directory.exists() or output_path.exists():
        raise SystemExit(
            "final bundle already exists; use the bundle auditor"
        )
    workspace.mkdir(parents=True, exist_ok=True)
    require_free_space(
        workspace,
        workspace_free_space_requirement(
            minimum_bytes=DEFAULT_MIN_FREE_BYTES,
            workers=args.workers,
            raw_proof_bytes=DEFAULT_MAX_RAW_PROOF_BYTES,
            retained_proof_bytes=DEFAULT_MAX_RETAINED_PROOF_BYTES,
        ),
    )

    def progress(
        completed: int,
        total: int,
        case: dict[str, object],
        _record: dict[str, object],
    ) -> None:
        print(
            f"[{completed}/{total}] verified {case['branch_id']}",
            flush=True,
        )

    case_records = build_cases(
        cases,
        root=root,
        workspace=workspace,
        python_command=args.python,
        checker=checker,
        checker_commit=args.checker_commit,
        environment=environment,
        workers=args.workers,
        minimum_free_bytes=DEFAULT_MIN_FREE_BYTES,
        max_solve_seconds=DEFAULT_MAX_SOLVE_SECONDS,
        max_raw_proof_bytes=DEFAULT_MAX_RAW_PROOF_BYTES,
        max_retained_proof_bytes=(
            DEFAULT_MAX_RETAINED_PROOF_BYTES
        ),
        max_memory_bytes=DEFAULT_MAX_MEMORY_BYTES,
        progress=progress,
    )

    def require_inputs_unchanged() -> None:
        for path, expected_hash in input_hashes.items():
            if (
                authenticated_file_sha256(path, "bundle input")
                != expected_hash
            ):
                raise RuntimeError(
                    f"input changed during bundle build: "
                    f"{display_path(path, root)}"
                )
        if python_tree_record(root) != initial_python_tree:
            raise RuntimeError(
                "root Python source tree changed during build"
            )
        if solver_environment_record(
            args.python,
            environment=environment,
            root=root,
        ) != solver_environment:
            raise RuntimeError(
                "solver environment changed during build"
            )

    require_inputs_unchanged()

    if args.workspace_only:
        print(
            json.dumps(
                {
                    "built_case_count": len(case_records),
                    "promoted": False,
                    "workspace": display_path(workspace, root),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if len(case_records) != 140:
        raise RuntimeError("complete promotion requires all 140 cases")

    resource_limits = {
        "workers": args.workers,
        "minimum_free_bytes": DEFAULT_MIN_FREE_BYTES,
        "solve_seconds_per_case": DEFAULT_MAX_SOLVE_SECONDS,
        "raw_proof_bytes_per_case": DEFAULT_MAX_RAW_PROOF_BYTES,
        "retained_proof_bytes_per_case": (
            DEFAULT_MAX_RETAINED_PROOF_BYTES
        ),
        "memory_watchdog_bytes_per_case": DEFAULT_MAX_MEMORY_BYTES,
        "checker_seconds_per_run": DEFAULT_MAX_CHECKER_SECONDS,
        "checker_output_bytes_per_run": (
            DEFAULT_MAX_CHECKER_OUTPUT_BYTES
        ),
        "proof_command_seconds": PROOF_COMMAND_TIMEOUT_SECONDS,
    }
    staged = stage_bundle(
        case_records,
        root=root,
        workspace=workspace,
        plan=plan,
        plan_path=plan_path,
        plan_sha256=plan_sha256,
        proof_directory=proof_directory,
        output_path=output_path,
        checker_commit=args.checker_commit,
        checker_sha256=checker_sha256,
        pipeline_files=pipeline_hashes,
        pipeline_python_tree=initial_python_tree,
        solver_environment=solver_environment,
        resource_limits=resource_limits,
    )
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    promote_bundle(
        staged.proof_directory,
        staged.index_path,
        root=root,
        proof_directory=proof_directory,
        output_path=output_path,
        journal_path=journal_path,
        token=staged.token,
        expected_directory_hash=staged.proof_directory_sha256,
        expected_index_hash=staged.index_sha256,
        expected_staging_identity=staged.proof_directory_identity,
        expected_staged_index_identity=staged.index_identity,
        validate_inputs=require_inputs_unchanged,
    )
    print(
        json.dumps(
            {
                "case_count": len(case_records),
                "index": display_path(output_path, root),
                "proof_directory": display_path(
                    proof_directory,
                    root,
                ),
                "proof_directory_sha256": directory_sha256(
                    proof_directory
                ),
                "promoted": True,
                "promotion_recovery": recovery,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
