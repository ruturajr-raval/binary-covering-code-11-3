#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
from concurrent.futures import as_completed, ThreadPoolExecutor
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
    artifact_path_identity,
    authenticated_file_sha256,
    branch_slug,
    case_filenames,
    CommandRegistry,
    coordinator_signal_handlers,
    directory_sha256,
    expected_bundle_members,
    file_sha256,
    generate_and_audit_formula,
    isolated_python_script_command,
    load_authenticated_json,
    load_json,
    owned_temporary_directory,
    PROOF_COMMAND_TIMEOUT_SECONDS,
    proof_resource_arguments,
    python_tree_record,
    quarantine_owned_path,
    require_free_space,
    require_path_separation,
    run_prerequisite_audits,
    solver_environment_record,
    validate_flat_case,
)
from fourth_word_drat.proof_core import (
    DEFAULT_MAX_CHECKER_OUTPUT_BYTES,
    DEFAULT_MAX_CHECKER_SECONDS,
    DEFAULT_MAX_MEMORY_BYTES,
    DEFAULT_MAX_RAW_PROOF_BYTES,
    DEFAULT_MAX_RETAINED_PROOF_BYTES,
    DEFAULT_MAX_SOLVE_SECONDS,
    display_path,
    materialized_retained_proof,
    repository_path,
    require_regular_single_link,
    validate_proof_summary_record,
)
from repository_lock import acquire_repository_lock


DEFAULT_PLAN = Path(
    "proof-expansion/evidence/fourth-word-solver-drat-plan-v2.json"
)
DEFAULT_PROOF_DIRECTORY = Path(
    "proof-expansion/evidence/proofs/fourth-word-solver-drat-v2"
)
DEFAULT_INDEX = Path(
    "proof-expansion/evidence/fourth-word-solver-drat-index-v2.json"
)
DEFAULT_REPLAY_WORKSPACE = Path(
    "proof-expansion/work/fourth-word-solver-drat-replay-v2"
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


def expected_index_case(
    planned: dict[str, object],
    case_record: dict[str, object],
    *,
    proof_directory: Path,
    root: Path,
) -> dict[str, object]:
    names = case_filenames(str(planned["branch_id"]))
    return {
        **planned,
        "formula": case_record["formula"],
        "proof": {
            "path": display_path(proof_directory / names["proof"], root),
            "sha256": case_record["proof"]["sha256"],
        },
        "proof_summary": {
            "path": display_path(
                proof_directory / names["summary"],
                root,
            ),
            "sha256": case_record["proof_summary"]["sha256"],
        },
        "case_record": {
            "path": display_path(
                proof_directory / names["case"],
                root,
            ),
            "sha256": authenticated_file_sha256(
                proof_directory / names["case"],
                "case record",
            ),
        },
        "verified": True,
    }


def audit_structure(
    plan: dict[str, object],
    plan_path: Path,
    plan_sha256: str,
    index: dict[str, object],
    proof_directory: Path,
    checker: Path,
    checker_commit: str,
    solver_environment: dict[str, object],
    replay_workspace: Path,
    *,
    root: Path,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if (
        plan.get("record_type") != "fourth-word-drat-proof-plan"
        or plan.get("schema_version") != 2
        or plan.get("case_count") != 140
        or plan.get("remaining_count") != 26
    ):
        raise RuntimeError("proof plan identity is incorrect")
    if set(index) != {
        "record_type",
        "schema_version",
        "certification_date",
        "plan",
        "proof_directory",
        "solver",
        "solver_environment",
        "checker",
        "pipeline_files",
        "pipeline_python_tree",
        "resource_limits",
        "prior_rup_certificate",
        "result",
        "case_count",
        "per_child",
        "cases",
    }:
        raise RuntimeError("proof index schema is incorrect")
    if (
        index["record_type"]
        != "fourth-word-solver-drat-proof-index"
        or index["schema_version"] != 2
        or index["certification_date"] != "2026-09-03"
        or index["plan"]
        != {
            "path": display_path(plan_path, root),
            "sha256": plan_sha256,
        }
        or index["proof_directory"]
        != display_path(proof_directory, root)
        or index["solver"] != "glucose4"
        or index["solver_environment"] != solver_environment
        or index["case_count"] != 140
        or len(index["cases"]) != 140
    ):
        raise RuntimeError("proof index identity is incorrect")
    checker_record = index["checker"]
    if (
        checker_record
        != {
            "name": "drat-trim",
            "commit": checker_commit,
            "binary_sha256": authenticated_file_sha256(
                checker,
                "proof checker",
            ),
        }
    ):
        raise RuntimeError("proof index checker identity changed")
    pipeline_files = index["pipeline_files"]
    expected_pipeline_files = {
        display_path(path, root): authenticated_file_sha256(
            root / path,
            "pipeline file",
        )
        for path in PIPELINE_FILES
    }
    if pipeline_files != expected_pipeline_files:
        raise RuntimeError("proof index pipeline files changed")
    for relative in pipeline_files:
        require_regular_single_link(
            repository_path(Path(relative), root),
            "pipeline file",
        )
    if index["pipeline_python_tree"] != python_tree_record(root):
        raise RuntimeError("proof index Python source tree changed")
    resource_limits = index["resource_limits"]
    if (
        not isinstance(resource_limits, dict)
        or set(resource_limits)
        != {
            "workers",
            "minimum_free_bytes",
            "solve_seconds_per_case",
            "raw_proof_bytes_per_case",
            "retained_proof_bytes_per_case",
            "memory_watchdog_bytes_per_case",
            "checker_seconds_per_run",
            "checker_output_bytes_per_run",
            "proof_command_seconds",
        }
        or resource_limits["workers"] not in {1, 2}
        or resource_limits["minimum_free_bytes"]
        != 8 * 1024 * 1024 * 1024
        or resource_limits["solve_seconds_per_case"]
        != DEFAULT_MAX_SOLVE_SECONDS
        or resource_limits["raw_proof_bytes_per_case"]
        != DEFAULT_MAX_RAW_PROOF_BYTES
        or resource_limits["retained_proof_bytes_per_case"]
        != DEFAULT_MAX_RETAINED_PROOF_BYTES
        or resource_limits["memory_watchdog_bytes_per_case"]
        != DEFAULT_MAX_MEMORY_BYTES
        or resource_limits["checker_seconds_per_run"]
        != DEFAULT_MAX_CHECKER_SECONDS
        or resource_limits["checker_output_bytes_per_run"]
        != DEFAULT_MAX_CHECKER_OUTPUT_BYTES
        or resource_limits["proof_command_seconds"]
        != PROOF_COMMAND_TIMEOUT_SECONDS
    ):
        raise RuntimeError("proof index resource limits changed")
    expected_prior = {
        "certified_branch_count": 184,
        "proof_index": plan["sources"]["rup_proof_index"],
        "replay_attestation": plan["sources"][
            "rup_replay_attestation"
        ],
        "bundle_manifest": plan["sources"]["rup_bundle_manifest"],
        "certified_revision": plan["sources"][
            "rup_certified_revision"
        ],
    }
    if index["prior_rup_certificate"] != expected_prior:
        raise RuntimeError("prior RUP certificate binding changed")
    if index["result"] != {
        "newly_certified_branch_count": 140,
        "combined_certified_branch_count": 324,
        "frontier_branch_count": 350,
        "remaining_branch_count": 26,
        "fully_closed_selected_child_count": 0,
        "fully_closed_normalized_parent_count": 0,
        "covering_number_status": "15 or 16",
        "lower_bound_15": plan["completion_implication"][
            "lower_bound_15"
        ],
    }:
        raise RuntimeError("proof index result boundary changed")

    observed_members = {
        entry.name for entry in proof_directory.iterdir()
    }
    expected_members = expected_bundle_members(plan["cases"])
    if observed_members != expected_members:
        raise RuntimeError("proof bundle membership is incorrect")
    for entry in proof_directory.iterdir():
        require_regular_single_link(entry, "proof bundle artifact")

    case_records = []
    expected_cases = []
    checker_sha256 = authenticated_file_sha256(
        checker,
        "proof checker",
    )
    for planned in plan["cases"]:
        case_record = validate_flat_case(proof_directory, planned)
        names = case_filenames(str(planned["branch_id"]))
        retained, _compressed_metrics = validate_proof_summary_record(
            load_json(proof_directory / names["summary"]),
            case_id=str(planned["branch_id"]),
            formula_sha256=str(case_record["formula"]["sha256"]),
            variables=int(case_record["formula"]["variables"]),
            clauses=int(case_record["formula"]["clauses"]),
            proof_path=proof_directory / names["proof"],
            checker_commit=checker_commit,
            checker_sha256=checker_sha256,
            python_sat_version=str(
                solver_environment["python_sat_version"]
            ),
            max_solve_seconds=int(
                resource_limits["solve_seconds_per_case"]
            ),
            max_raw_proof_bytes=int(
                resource_limits["raw_proof_bytes_per_case"]
            ),
            max_retained_proof_bytes=int(
                resource_limits["retained_proof_bytes_per_case"]
            ),
            max_memory_bytes=int(
                resource_limits["memory_watchdog_bytes_per_case"]
            ),
        )
        with materialized_retained_proof(
            proof_directory / names["proof"],
            retained,
            scratch_directory=replay_workspace,
            max_bytes=int(
                resource_limits["retained_proof_bytes_per_case"]
            ),
        ):
            pass
        case_records.append(case_record)
        expected_cases.append(
            expected_index_case(
                planned,
                case_record,
                proof_directory=proof_directory,
                root=root,
            )
        )
    if index["cases"] != expected_cases:
        raise RuntimeError("proof index cases are not canonical")
    expected_per_child = [
        {
            "parent_child_id": record["parent_child_id"],
            "proof_count": record["drat_planned_count"],
        }
        for record in plan["per_child"]
    ]
    if index["per_child"] != expected_per_child:
        raise RuntimeError("proof index child counts are incorrect")
    return case_records, resource_limits


def replay_case(
    planned: dict[str, object],
    case_record: dict[str, object],
    *,
    root: Path,
    proof_directory: Path,
    replay_workspace: Path,
    python_command: str,
    checker: Path,
    checker_commit: str,
    environment: dict[str, str],
    commands: CommandRegistry,
    resource_limits: dict[str, object],
) -> dict[str, object]:
    branch_id = str(planned["branch_id"])
    slug = branch_slug(branch_id)
    replay_workspace.mkdir(parents=True, exist_ok=True)
    require_free_space(
        replay_workspace,
        int(resource_limits["minimum_free_bytes"]),
    )
    with owned_temporary_directory(
        replay_workspace,
        prefix=f".{slug}.",
    ) as temporary:
        formula, _metadata_path, formula_record = (
            generate_and_audit_formula(
                planned,
                directory=temporary,
                root=root,
                python_command=python_command,
                environment=environment,
                commands=commands,
            )
        )
        scratch = temporary / "proof-replay"
        scratch.mkdir()
        if (
            formula_record["formula_sha256"]
            != case_record["formula"]["sha256"]
            or formula_record["variables"]
            != case_record["formula"]["variables"]
            or formula_record["clauses"]
            != case_record["formula"]["clauses"]
        ):
            raise RuntimeError(f"{branch_id}: formula identity changed")
        names = case_filenames(branch_id)
        commands.run(
            isolated_python_script_command(
                python_command,
                "proof-expansion/cli/prove_formula.py",
                display_path(formula, root),
                display_path(
                    proof_directory / names["proof"],
                    root,
                ),
                display_path(
                    proof_directory / names["summary"],
                    root,
                ),
                "--case-id",
                branch_id,
                "--solver",
                "glucose4",
                "--checker",
                display_path(checker, root),
                "--checker-commit",
                checker_commit,
                "--scratch-directory",
                display_path(scratch, root),
                *proof_resource_arguments(
                    max_solve_seconds=int(
                        resource_limits[
                            "solve_seconds_per_case"
                        ]
                    ),
                    max_raw_proof_bytes=int(
                        resource_limits[
                            "raw_proof_bytes_per_case"
                        ]
                    ),
                    max_retained_proof_bytes=int(
                        resource_limits[
                            "retained_proof_bytes_per_case"
                        ]
                    ),
                    max_memory_bytes=int(
                        resource_limits[
                            "memory_watchdog_bytes_per_case"
                        ]
                    ),
                ),
                "--verify-existing",
            ),
            environment=environment,
            root=root,
            timeout_seconds=PROOF_COMMAND_TIMEOUT_SECONDS,
        )
    return {
        "branch_id": branch_id,
        "verified": True,
    }


def replay_cases(
    planned_cases: list[dict[str, object]],
    case_records: list[dict[str, object]],
    *,
    root: Path,
    proof_directory: Path,
    replay_workspace: Path,
    python_command: str,
    checker: Path,
    checker_commit: str,
    environment: dict[str, str],
    workers: int,
    resource_limits: dict[str, object],
) -> None:
    commands = CommandRegistry()
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = {}
    with coordinator_signal_handlers(commands):
        try:
            futures = {
                executor.submit(
                    replay_case,
                    planned,
                    case_record,
                    root=root,
                    proof_directory=proof_directory,
                    replay_workspace=replay_workspace,
                    python_command=python_command,
                    checker=checker,
                    checker_commit=checker_commit,
                    environment=environment,
                    commands=commands,
                    resource_limits=resource_limits,
                ): planned
                for planned, case_record in zip(
                    planned_cases,
                    case_records,
                )
            }
            completed = 0
            for future in as_completed(futures):
                planned = futures[future]
                future.result()
                completed += 1
                print(
                    f"[{completed}/{len(futures)}] replayed "
                    f"{planned['branch_id']}",
                    flush=True,
                )
        except BaseException:
            commands.cancel()
            for future in futures:
                future.cancel()
            try:
                commands.terminate_all()
            finally:
                executor.shutdown(wait=True, cancel_futures=True)
            raise
    executor.shutdown(wait=True)


def clean_replay_workspace(
    replay_workspace: Path,
    planned_cases: list[dict[str, object]],
) -> None:
    if not replay_workspace.exists() and not replay_workspace.is_symlink():
        return
    if (
        replay_workspace.is_symlink()
        or not replay_workspace.is_dir()
    ):
        raise RuntimeError("replay workspace is invalid")
    workspace_identity = artifact_path_identity(
        replay_workspace,
        directory=True,
    )
    prefixes = {
        f".{branch_slug(str(case['branch_id']))}."
        for case in planned_cases
    }
    for entry in replay_workspace.iterdir():
        if (
            entry.is_symlink()
            or not entry.is_dir()
            or not any(
                entry.name.startswith(prefix) for prefix in prefixes
            )
        ):
            raise RuntimeError(
                f"unexpected replay workspace entry: {entry}"
            )
        identity = artifact_path_identity(entry, directory=True)
        if not quarantine_owned_path(
            entry,
            identity,
            directory=True,
        ):
            raise RuntimeError(
                f"replay workspace entry changed during cleanup: {entry}"
            )
    if not quarantine_owned_path(
        replay_workspace,
        workspace_identity,
        directory=True,
    ):
        raise RuntimeError("replay workspace changed during cleanup")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument(
        "--proof-directory",
        type=Path,
        default=DEFAULT_PROOF_DIRECTORY,
    )
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--replay-workspace",
        type=Path,
        default=DEFAULT_REPLAY_WORKSPACE,
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--checker",
        type=Path,
        default=Path("build/drat-trim-src/drat-trim"),
    )
    parser.add_argument("--checker-commit", default=CHECKER_COMMIT)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--structure-only", action="store_true")
    args = parser.parse_args()

    if args.workers < 1 or args.workers > 2:
        raise SystemExit("workers must be between 1 and 2")
    root = repository_root()
    plan_path = repository_path(args.plan, root)
    proof_directory = repository_path(args.proof_directory, root)
    index_path = repository_path(args.index, root)
    replay_workspace = repository_path(args.replay_workspace, root)
    checker = repository_path(args.checker, root)
    require_path_separation(
        {
            "plan": plan_path,
            "proof_directory": proof_directory,
            "index": index_path,
            "replay_workspace": replay_workspace,
            "checker": checker,
        }
    )
    repository_lock = acquire_repository_lock(root)
    atexit.register(repository_lock.close)
    for path, description in (
        (plan_path, "proof plan"),
        (index_path, "proof index"),
        (checker, "proof checker"),
    ):
        require_regular_single_link(path, description)
    if not proof_directory.is_dir() or proof_directory.is_symlink():
        raise SystemExit("proof directory is invalid")
    if args.checker_commit != CHECKER_COMMIT:
        raise SystemExit("checker commit is not pinned")
    validate_pinned_checkout(
        checker.parent,
        args.checker_commit,
        allowed_untracked={"drat-trim"},
    )

    plan, before_plan_hash = load_authenticated_json(
        plan_path,
        "proof plan",
    )
    index, before_index_hash = load_authenticated_json(
        index_path,
        "proof index",
    )
    environment = dict(os.environ)
    required_python_path = os.pathsep.join(
        ["proof-expansion/src", "src", "tools"]
    )
    environment["PYTHONPATH"] = required_python_path
    run_prerequisite_audits(
        root=root,
        plan_path=plan_path,
        expected_plan_sha256=before_plan_hash,
        python_command=args.python,
        environment=environment,
    )
    solver_environment = solver_environment_record(
        args.python,
        environment=environment,
        root=root,
    )
    clean_replay_workspace(
        replay_workspace,
        list(plan["cases"]),
    )
    replay_workspace.mkdir(parents=True, exist_ok=True)
    replay_workspace_identity = artifact_path_identity(
        replay_workspace,
        directory=True,
    )
    require_free_space(
        replay_workspace,
        8 * 1024 * 1024 * 1024
        + args.workers * DEFAULT_MAX_RETAINED_PROOF_BYTES,
    )
    before_directory_hash = directory_sha256(proof_directory)
    before_python_tree = python_tree_record(root)

    case_records, resource_limits = audit_structure(
        plan,
        plan_path,
        before_plan_hash,
        index,
        proof_directory,
        checker,
        args.checker_commit,
        solver_environment,
        replay_workspace,
        root=root,
    )
    authenticated_inputs = {
        plan_path: before_plan_hash,
        index_path: before_index_hash,
        checker: authenticated_file_sha256(checker, "proof checker"),
    }
    for source in plan["sources"].values():
        source_path = repository_path(Path(source["path"]), root)
        require_regular_single_link(source_path, "plan source")
        if (
            authenticated_file_sha256(source_path, "plan source")
            != source["sha256"]
        ):
            raise RuntimeError(f"plan source changed: {source['path']}")
        authenticated_inputs[source_path] = str(source["sha256"])
    for relative, digest in index["pipeline_files"].items():
        pipeline_path = repository_path(Path(relative), root)
        authenticated_inputs[pipeline_path] = str(digest)
    if not args.structure_only:
        replay_cases(
            list(plan["cases"]),
            case_records,
            root=root,
            proof_directory=proof_directory,
            replay_workspace=replay_workspace,
            python_command=args.python,
            checker=checker,
            checker_commit=args.checker_commit,
            environment=environment,
            workers=args.workers,
            resource_limits=resource_limits,
        )
    if (
        directory_sha256(proof_directory) != before_directory_hash
        or authenticated_file_sha256(index_path, "proof index")
        != before_index_hash
        or python_tree_record(root) != before_python_tree
        or solver_environment_record(
            args.python,
            environment=environment,
            root=root,
        )
        != solver_environment
        or any(
            authenticated_file_sha256(path, "authenticated input")
            != digest
            for path, digest in authenticated_inputs.items()
        )
    ):
        raise RuntimeError("audit inputs changed during verification")
    if replay_workspace.exists():
        entries = list(replay_workspace.iterdir())
        if entries:
            raise RuntimeError("replay workspace contains stale entries")
        if not quarantine_owned_path(
            replay_workspace,
            replay_workspace_identity,
            directory=True,
        ):
            raise RuntimeError(
                "replay workspace changed before final cleanup"
            )
    print(
        json.dumps(
            {
                "case_count": len(case_records),
                "proof_directory_sha256": before_directory_hash,
                "proof_index_sha256": before_index_hash,
                "proofs_replayed": not args.structure_only,
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
