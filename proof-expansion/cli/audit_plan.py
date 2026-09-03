#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
from collections import Counter
import hashlib
import json
import math
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

from fourth_word_drat.bundle import (
    load_authenticated_bytes,
    load_authenticated_json,
)
from manage_fourth_word_rup_revision import validate_record_schema
from repository_lock import acquire_repository_lock


DRAT_TRIM_COMMIT = "2e3b2dc0ecf938addbd779d42877b6ed69d9a985"
EXPECTED_SELECTED_SET_SHA256 = (
    "314c573765bc28fd8556db41fec2aa4f7e6e7b5b1266c7a0906c1b23dcaec034"
)
EXPECTED_REMAINING_SET_SHA256 = (
    "f692db28c5e59d1515fabe1b0c89005890c316e8e8b8c3384f7638de35e73d32"
)
EXPECTED_CHILD_COUNTS = {
    "w4-weight5-intersection0::orbit-005": (85, 50, 29, 6),
    "w4-weight5-intersection0::orbit-007": (76, 53, 15, 8),
    "w4-weight5-intersection0::orbit-014": (73, 41, 28, 4),
    "w4-weight5-intersection0::orbit-015": (116, 40, 68, 8),
}
EXPECTED_RUP_CERTIFIED_REVISION = (
    "06ecaa7bc28503efd871faf4450005f43e625124"
)
EXPECTED_RUP_CERTIFIED_TREE = (
    "4888ad6c5305b5d30d6c4ca3e8435b9c872307b1"
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def repository_path(path: Path, root: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    lexical = Path(os.path.abspath(str(candidate)))
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        raise SystemExit(f"path is outside the repository: {path}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SystemExit(f"path contains a symbolic link: {path}")
    return lexical


def display_path(path: Path, root: Path) -> str:
    return str(repository_path(path, root).relative_to(root))


def validate_literature_audit(payload: bytes) -> None:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SystemExit("literature audit is not valid UTF-8") from error
    required = (
        "Audit date: 2026-09-03",
        "15 <= K_2(11,3) <= 16.",
        "The table update log dated 2006-01-17 records the lower bound 15",
        "No stable paper or retained proof certificate for this computation",
    )
    if any(fragment not in text for fragment in required):
        raise SystemExit("literature audit does not support the inherited bound")


def record_digest(records: list[dict[str, object]]) -> str:
    payload = "".join(
        f"{record['branch_id']}:{record['branch_sha256']}\n"
        for record in records
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def require_finite_nonnegative(value: object, description: str) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise SystemExit(f"{description} is invalid")


def validate_rup_certificate_binding(
    paths: dict[str, Path],
    records: dict[str, dict[str, object]],
    hashes: dict[str, str],
    classification: dict[str, object],
    *,
    root: Path,
) -> None:
    index = records["rup_proof_index"]
    attestation = records["rup_replay_attestation"]
    revision = records["rup_certified_revision"]
    expected_cases = [
        {
            key: branch[key]
            for key in (
                "branch_id",
                "branch_sha256",
                "parent_child_id",
                "fourth_orbit_index",
            )
        }
        for branch in classification["branches"]
        if branch["status"] == "rup-conflict"
    ]
    observed_cases = [
        {
            key: case[key]
            for key in (
                "branch_id",
                "branch_sha256",
                "parent_child_id",
                "fourth_orbit_index",
            )
        }
        for case in index.get("cases", [])
    ]
    if (
        index.get("record_type") != "fourth-word-rup-proof-index"
        or index.get("schema_version") != 3
        or index.get("case_count") != 184
        or index.get("all_verified") is not True
        or observed_cases != expected_cases
    ):
        raise SystemExit("certified RUP proof index is inconsistent")
    index_reference = {
        "path": display_path(paths["rup_proof_index"], root),
        "sha256": hashes["rup_proof_index"],
    }
    attestation_reference = {
        "path": display_path(paths["rup_replay_attestation"], root),
        "sha256": hashes["rup_replay_attestation"],
    }
    bundle_reference = {
        "path": display_path(paths["rup_bundle_manifest"], root),
        "sha256": hashes["rup_bundle_manifest"],
    }
    if (
        attestation.get("record_type")
        != "fourth-word-rup-replay-attestation"
        or attestation.get("schema_version") != 3
        or attestation.get("proof_index") != index_reference
        or attestation.get("case_count") != 184
        or attestation.get("all_verified") is not True
        or attestation.get("replay_date") != "2026-09-03"
    ):
        raise SystemExit("certified RUP replay attestation is inconsistent")
    try:
        status = validate_record_schema(
            revision,
            allow_pending=False,
        )
    except RuntimeError as exc:
        raise SystemExit(
            "certified RUP revision record is invalid"
        ) from exc
    if (
        status != "clean-checkout-replay-passed"
        or revision.get("proof_index") != index_reference
        or revision.get("replay_attestation")
        != attestation_reference
        or revision.get("bundle_manifest") != bundle_reference
        or revision.get("certified_revision")
        != EXPECTED_RUP_CERTIFIED_REVISION
        or revision.get("certified_tree")
        != EXPECTED_RUP_CERTIFIED_TREE
        or revision.get("clean_checkout_replay", {}).get(
            "completed_on"
        )
        != "2026-09-03"
    ):
        raise SystemExit("certified RUP revision binding changed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("child_frontier", type=Path)
    parser.add_argument("fourth_frontier", type=Path)
    parser.add_argument("rup_classification", type=Path)
    parser.add_argument("rup_proof_index", type=Path)
    parser.add_argument("rup_replay_attestation", type=Path)
    parser.add_argument("rup_bundle_manifest", type=Path)
    parser.add_argument("rup_certified_revision", type=Path)
    parser.add_argument("scout_report", type=Path)
    parser.add_argument("scout_run_record", type=Path)
    parser.add_argument("literature_audit", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--expected-plan-sha256")
    args = parser.parse_args()

    root = repository_root()
    repository_lock = acquire_repository_lock(root)
    atexit.register(repository_lock.close)
    paths = {
        "parent_manifest": repository_path(
            args.parent_manifest,
            root,
        ),
        "third_word_manifest": repository_path(
            args.third_word_manifest,
            root,
        ),
        "child_frontier": repository_path(
            args.child_frontier,
            root,
        ),
        "fourth_frontier": repository_path(
            args.fourth_frontier,
            root,
        ),
        "rup_classification": repository_path(
            args.rup_classification,
            root,
        ),
        "rup_proof_index": repository_path(
            args.rup_proof_index,
            root,
        ),
        "rup_replay_attestation": repository_path(
            args.rup_replay_attestation,
            root,
        ),
        "rup_bundle_manifest": repository_path(
            args.rup_bundle_manifest,
            root,
        ),
        "rup_certified_revision": repository_path(
            args.rup_certified_revision,
            root,
        ),
        "scout_report": repository_path(args.scout_report, root),
        "scout_run_record": repository_path(
            args.scout_run_record,
            root,
        ),
        "literature_audit": repository_path(
            args.literature_audit,
            root,
        ),
        "plan": repository_path(args.plan, root),
    }
    if len(set(paths.values())) != len(paths):
        raise SystemExit("DRAT plan audit inputs must use distinct files")
    if not all(path.is_file() for path in paths.values()):
        raise SystemExit("DRAT plan audit inputs must be regular files")
    path_list = list(paths.values())
    if any(
        os.path.samefile(left, right)
        for index, left in enumerate(path_list)
        for right in path_list[index + 1:]
    ):
        raise SystemExit("DRAT plan audit inputs alias the same file")

    records: dict[str, dict[str, object]] = {}
    hashes: dict[str, str] = {}
    literature_payload = b""
    for label, path in paths.items():
        if label in {"rup_bundle_manifest", "literature_audit"}:
            payload, hashes[label] = load_authenticated_bytes(
                path,
                label.replace("_", " "),
            )
            if label == "literature_audit":
                literature_payload = payload
        else:
            records[label], hashes[label] = load_authenticated_json(
                path,
                label.replace("_", " "),
            )
    validate_literature_audit(literature_payload)
    if (
        args.expected_plan_sha256 is not None
        and hashes["plan"] != args.expected_plan_sha256
    ):
        raise SystemExit("proof plan digest differs from caller snapshot")
    child_frontier = records["child_frontier"]
    fourth_frontier = records["fourth_frontier"]
    classification = records["rup_classification"]
    scout = records["scout_report"]
    run = records["scout_run_record"]
    plan = records["plan"]

    validate_rup_certificate_binding(
        paths,
        records,
        hashes,
        classification,
        root=root,
    )

    expected_sources = {
        label: {
            "path": display_path(paths[label], root),
            "sha256": hashes[label],
        }
        for label in (
            "parent_manifest",
            "third_word_manifest",
            "child_frontier",
            "fourth_frontier",
            "rup_classification",
            "rup_proof_index",
            "rup_replay_attestation",
            "rup_bundle_manifest",
            "rup_certified_revision",
            "scout_report",
            "scout_run_record",
            "literature_audit",
        )
    }
    if hashes["parent_manifest"] != child_frontier["sources"][
        "stage1_parent_manifest"
    ]["sha256"]:
        raise SystemExit("parent manifest does not match child frontier")
    if hashes["third_word_manifest"] != child_frontier["sources"][
        "third_word_manifest"
    ]["sha256"]:
        raise SystemExit("third-word manifest does not match child frontier")
    for label in (
        "parent_manifest",
        "third_word_manifest",
        "child_frontier",
    ):
        if hashes[label] != fourth_frontier["sources"][label]["sha256"]:
            raise SystemExit(
                f"{label} does not match fourth-word frontier"
            )

    frontier_branches = [
        branch
        for child in fourth_frontier["children"]
        for branch in child["branches"]
    ]
    frontier_by_id = {
        str(branch["branch_id"]): branch
        for branch in frontier_branches
    }
    if len(frontier_by_id) != 350:
        raise SystemExit("fourth-word frontier identities changed")

    classification_branches = classification["branches"]
    if len(classification_branches) != 350:
        raise SystemExit("RUP classification branch count changed")
    for observed, frontier in zip(
        classification_branches,
        frontier_branches,
    ):
        expected_identity = {
            "branch_id": frontier["branch_id"],
            "branch_sha256": frontier["branch_sha256"],
            "parent_child_id": frontier["parent_child_id"],
            "fourth_orbit_index": frontier["fourth_orbit_index"],
        }
        if {
            key: observed[key]
            for key in expected_identity
        } != expected_identity:
            raise SystemExit("RUP classification identity changed")
        if observed["status"] not in {
            "rup-conflict",
            "not-rup-conflict",
        }:
            raise SystemExit("RUP classification status is invalid")
    residual = [
        record
        for record in classification_branches
        if record["status"] == "not-rup-conflict"
    ]
    if len(residual) != 166:
        raise SystemExit("RUP residual count changed")

    expected_scout_keys = {
        "record_type",
        "schema_version",
        "run_id",
        "run_record",
        "sources",
        "solver",
        "python_sat_version",
        "branch_interrupt_after_seconds",
        "interrupt_enforcement",
        "workers",
        "order",
        "incremental_solver_reuse",
        "proof_traces_available",
        "scheduled_branch_count",
        "completed_branch_count",
        "status_counts",
        "found_cover",
        "elapsed_seconds",
        "worker_errors",
        "results",
    }
    if set(scout) != expected_scout_keys:
        raise SystemExit("scout report schema changed")
    if (
        scout["record_type"] != "fourth-word-portfolio"
        or scout["schema_version"] != 1
        or scout["solver"] != "glucose4"
        or scout["python_sat_version"] != "1.9.dev15"
        or scout["branch_interrupt_after_seconds"] != 5.0
        or scout["interrupt_enforcement"] != "solver-cooperative"
        or scout["workers"] != 4
        or scout["order"] != "reverse-prefix"
        or scout["incremental_solver_reuse"] is not True
        or scout["proof_traces_available"] is not False
        or scout["scheduled_branch_count"] != 350
        or scout["completed_branch_count"] != 350
        or scout["status_counts"] != {"UNKNOWN": 26, "UNSAT": 324}
        or scout["found_cover"] is not False
        or scout["worker_errors"] != []
    ):
        raise SystemExit("authenticated scout metadata changed")
    require_finite_nonnegative(
        scout["elapsed_seconds"],
        "scout elapsed time",
    )
    expected_scout_sources = {
        label: {
            "path": display_path(paths[label], root),
            "sha256": hashes[label],
        }
        for label in (
            "parent_manifest",
            "third_word_manifest",
            "child_frontier",
            "fourth_frontier",
        )
    }
    if scout["sources"] != expected_scout_sources:
        raise SystemExit("scout report sources changed")

    scout_results = scout["results"]
    if len(scout_results) != 350:
        raise SystemExit("scout result count changed")
    scout_by_id: dict[str, dict[str, object]] = {}
    for result in scout_results:
        branch_id = str(result["branch_id"])
        if branch_id in scout_by_id:
            raise SystemExit("scout branch identifiers are not unique")
        branch = frontier_by_id.get(branch_id)
        if branch is None:
            raise SystemExit("scout contains an unknown branch")
        expected_identity = {
            "branch_id": branch_id,
            "parent_child_id": branch["parent_child_id"],
            "fourth_orbit_index": branch["fourth_orbit_index"],
            "assumption_count": int(branch["earlier_word_count"]) + 1,
        }
        if {
            key: result[key]
            for key in expected_identity
        } != expected_identity:
            raise SystemExit(f"{branch_id}: scout identity changed")
        if result["status"] not in {"UNSAT", "UNKNOWN"}:
            raise SystemExit(f"{branch_id}: scout status is invalid")
        expected_timeout = result["status"] == "UNKNOWN"
        if result["timed_out"] is not expected_timeout:
            raise SystemExit(f"{branch_id}: scout timeout is inconsistent")
        require_finite_nonnegative(
            result["solve_seconds"],
            f"{branch_id}: solve time",
        )
        scout_by_id[branch_id] = result
    if set(scout_by_id) != set(frontier_by_id):
        raise SystemExit("scout does not cover the exact frontier")
    scout_counts = Counter(
        str(result["status"]) for result in scout_results
    )
    if scout_counts != Counter({"UNSAT": 324, "UNKNOWN": 26}):
        raise SystemExit("scout result counts changed")

    if set(run) != {
        "schema_version",
        "run_id",
        "started_at",
        "finished_at",
        "git_commit",
        "command",
        "environment",
        "inputs",
        "result",
        "metrics",
        "artifacts",
        "notes",
    }:
        raise SystemExit("scout run-record schema changed")
    if (
        run["schema_version"] != 1
        or run["run_id"] != scout["run_id"]
        or run["git_commit"]
        != "f968cc79e9c17f93f79dcd135eb6dbecaa3feb55"
        or run["result"] != "inconclusive"
        or scout["run_record"] != display_path(
            paths["scout_run_record"],
            root,
        )
        or run["artifacts"]
        != [
            {
                "path": display_path(paths["scout_report"], root),
                "sha256": hashes["scout_report"],
            }
        ]
    ):
        raise SystemExit("scout run-record authentication failed")
    expected_metrics = {
        "completed_branch_count": 350,
        "elapsed_seconds": scout["elapsed_seconds"],
        "found_cover": False,
        "scheduled_branch_count": 350,
        "unknown_branch_count": 26,
        "unsat_branch_count": 324,
        "worker_error_count": 0,
    }
    if run["metrics"] != expected_metrics:
        raise SystemExit("scout run-record metrics changed")

    selected = []
    remaining = []
    for record in residual:
        branch_id = str(record["branch_id"])
        result = scout_by_id[branch_id]
        common = {
            "branch_id": branch_id,
            "branch_sha256": record["branch_sha256"],
            "parent_child_id": record["parent_child_id"],
            "fourth_orbit_index": record["fourth_orbit_index"],
        }
        if result["status"] == "UNSAT":
            selected.append(
                {
                    **common,
                    "scout_task_index": result["task_index"],
                }
            )
        else:
            remaining.append(common)

    selected_digest = record_digest(selected)
    remaining_digest = record_digest(remaining)
    if (
        len(selected) != 140
        or selected_digest != EXPECTED_SELECTED_SET_SHA256
    ):
        raise SystemExit("selected DRAT case set changed")
    if (
        len(remaining) != 26
        or remaining_digest != EXPECTED_REMAINING_SET_SHA256
    ):
        raise SystemExit("remaining branch set changed")

    selected_counts = Counter(
        str(record["parent_child_id"]) for record in selected
    )
    remaining_counts = Counter(
        str(record["parent_child_id"]) for record in remaining
    )
    expected_per_child = []
    for record in classification["per_child"]:
        child_id = str(record["parent_child_id"])
        observed = (
            int(record["branch_count"]),
            int(record["rup_conflict_count"]),
            selected_counts[child_id],
            remaining_counts[child_id],
        )
        if observed != EXPECTED_CHILD_COUNTS.get(child_id):
            raise SystemExit(f"{child_id}: DRAT plan counts changed")
        expected_per_child.append(
            {
                "parent_child_id": child_id,
                "branch_count": observed[0],
                "rup_closed_count": observed[1],
                "drat_planned_count": observed[2],
                "remaining_count": observed[3],
            }
        )

    if set(plan) != {
        "record_type",
        "schema_version",
        "sources",
        "selection",
        "proof_pipeline",
        "case_count",
        "remaining_count",
        "selected_set_sha256",
        "remaining_set_sha256",
        "per_child",
        "completion_implication",
        "cases",
        "remaining_cases",
    }:
        raise SystemExit("DRAT proof-plan schema is incorrect")
    if (
        plan["record_type"] != "fourth-word-drat-proof-plan"
        or plan["schema_version"] != 2
        or plan["sources"] != expected_sources
        or plan["selection"]
        != {
            "basis": (
                "non-RUP branches reported UNSAT by the authenticated "
                "exploratory scout"
            ),
            "claim_basis": (
                "only independently checked retained DRAT proofs may "
                "certify branch closure"
            ),
            "scout_solver": "glucose4",
            "scout_status": "UNSAT",
            "scout_proof_claim": False,
        }
        or plan["proof_pipeline"]
        != {
            "solver": "glucose4",
            "solver_output": "text DRAT",
            "core_extractor": "drat-trim -l",
            "retained_proof": "trimmed text DRAT",
            "compression": "gzip with mtime zero",
            "checker": "drat-trim",
            "checker_commit": DRAT_TRIM_COMMIT,
        }
        or plan["case_count"] != 140
        or plan["remaining_count"] != 26
        or plan["selected_set_sha256"] != selected_digest
        or plan["remaining_set_sha256"] != remaining_digest
        or plan["per_child"] != expected_per_child
        or plan["completion_implication"]
        != {
            "conditional_on_all_planned_proofs_verifying": True,
            "frontier_branch_count": 350,
            "previously_certified_branch_count": 184,
            "planned_new_certificate_count": 140,
            "combined_certified_branch_count": 324,
            "remaining_branch_count": 26,
            "fully_closed_selected_child_count": 0,
            "fully_closed_normalized_parent_count": 0,
            "covering_number_status": "15 or 16",
            "lower_bound_15": {
                "basis": "inherited historical computational result",
                "independently_reconstructed_here": False,
                "literature_source": "literature_audit",
                "table_update_date": "2006-01-17",
            },
        }
        or plan["cases"] != selected
        or plan["remaining_cases"] != remaining
    ):
        raise SystemExit("DRAT proof plan does not match reconstruction")

    for label, path in paths.items():
        if (
            load_authenticated_bytes(
                path,
                label.replace("_", " "),
            )[1]
            != hashes[label]
        ):
            raise RuntimeError(f"{label} changed during DRAT plan audit")
    print(
        json.dumps(
            {
                "case_count": len(selected),
                "remaining_count": len(remaining),
                "selected_set_sha256": selected_digest,
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
