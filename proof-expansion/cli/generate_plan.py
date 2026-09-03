#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
from collections import Counter
import hashlib
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

from fourth_word_drat.bundle import (
    load_authenticated_bytes,
    load_authenticated_json,
)
from fourth_word_drat.secure_io import (
    authenticated_file_version,
    descriptor_artifact_identity,
    durable_publish_noreplace,
    PublicationCommittedError,
    quarantine_owned_path,
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


def atomic_write_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    ).encode("ascii")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    temporary_identity = descriptor_artifact_identity(
        descriptor,
        directory=False,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_version = authenticated_file_version(
            temporary,
            "atomic-write temporary",
        )
        try:
            durable_publish_noreplace(
                temporary,
                path,
                directory=False,
                expected_source_identity=temporary_identity,
                expected_source_version=temporary_version,
            )
        except PublicationCommittedError as error:
            if not quarantine_owned_path(
                path,
                error.destination_identity,
                directory=False,
            ):
                raise RuntimeError(
                    f"committed atomic write could not be removed: {path}"
                ) from error
            raise
    finally:
        if not quarantine_owned_path(
            temporary,
            temporary_identity,
            directory=False,
        ):
            raise RuntimeError(
                f"atomic-write temporary changed during cleanup: "
                f"{temporary}"
            )


def validate_scout_binding(
    scout_path: Path,
    scout_sha256: str,
    scout: dict[str, object],
    run_path: Path,
    run: dict[str, object],
    *,
    root: Path,
) -> None:
    if scout.get("run_record") != display_path(run_path, root):
        raise SystemExit("scout report does not identify its run record")
    artifacts = run.get("artifacts")
    expected_artifact = {
        "path": display_path(scout_path, root),
        "sha256": scout_sha256,
    }
    if artifacts != [expected_artifact]:
        raise SystemExit("scout run record does not authenticate the report")
    if run.get("run_id") != scout.get("run_id"):
        raise SystemExit("scout report and run identifier differ")
    if run.get("result") != "inconclusive":
        raise SystemExit("scout run result changed")


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
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify-existing", action="store_true")
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
    }
    output = repository_path(args.output, root)
    if len(set(paths.values())) != len(paths):
        raise SystemExit("DRAT plan inputs must use distinct files")
    if output in paths.values():
        raise SystemExit("DRAT plan output aliases an input")
    if not all(path.is_file() for path in paths.values()):
        raise SystemExit("DRAT plan inputs must be regular files")

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
    classification = records["rup_classification"]
    scout = records["scout_report"]
    run = records["scout_run_record"]

    validate_rup_certificate_binding(
        paths,
        records,
        hashes,
        classification,
        root=root,
    )

    validate_scout_binding(
        paths["scout_report"],
        hashes["scout_report"],
        scout,
        paths["scout_run_record"],
        run,
        root=root,
    )
    if scout.get("solver") != "glucose4":
        raise SystemExit("authenticated scout solver changed")
    if scout.get("proof_traces_available") is not False:
        raise SystemExit("scout report must not claim proof traces")
    if scout.get("found_cover") is not False:
        raise SystemExit("scout report unexpectedly contains a cover")
    if scout.get("status_counts") != {
        "UNKNOWN": 26,
        "UNSAT": 324,
    }:
        raise SystemExit("authenticated scout status counts changed")

    residual = [
        record
        for record in classification["branches"]
        if record["status"] == "not-rup-conflict"
    ]
    residual_by_id = {
        str(record["branch_id"]): record
        for record in residual
    }
    scout_results = scout["results"]
    scout_by_id = {
        str(record["branch_id"]): record
        for record in scout_results
    }
    if len(scout_by_id) != len(scout_results):
        raise SystemExit("scout report has duplicate branch identifiers")
    if set(scout_by_id) != {
        str(record["branch_id"])
        for record in classification["branches"]
    }:
        raise SystemExit("scout report does not cover the exact frontier")

    selected = []
    remaining = []
    for record in residual:
        branch_id = str(record["branch_id"])
        scout_record = scout_by_id[branch_id]
        identity = {
            "branch_id": branch_id,
            "branch_sha256": record["branch_sha256"],
            "parent_child_id": record["parent_child_id"],
            "fourth_orbit_index": record["fourth_orbit_index"],
            "scout_task_index": scout_record["task_index"],
        }
        status = scout_record["status"]
        if status == "UNSAT":
            if scout_record["timed_out"] is not False:
                raise SystemExit(
                    f"{branch_id}: UNSAT scout result timed out"
                )
            selected.append(identity)
        elif status == "UNKNOWN":
            if scout_record["timed_out"] is not True:
                raise SystemExit(
                    f"{branch_id}: UNKNOWN scout result did not time out"
                )
            remaining.append(
                {
                    key: identity[key]
                    for key in (
                        "branch_id",
                        "branch_sha256",
                        "parent_child_id",
                        "fourth_orbit_index",
                    )
                }
            )
        else:
            raise SystemExit(
                f"{branch_id}: unsupported scout status {status}"
            )

    selected_digest = record_digest(selected)
    remaining_digest = record_digest(remaining)
    if len(selected) != 140:
        raise SystemExit("selected DRAT case count changed")
    if len(remaining) != 26:
        raise SystemExit("remaining branch count changed")
    if selected_digest != EXPECTED_SELECTED_SET_SHA256:
        raise SystemExit("selected DRAT case set changed")
    if remaining_digest != EXPECTED_REMAINING_SET_SHA256:
        raise SystemExit("remaining branch set changed")

    selected_counts = Counter(
        str(record["parent_child_id"]) for record in selected
    )
    remaining_counts = Counter(
        str(record["parent_child_id"]) for record in remaining
    )
    per_child = []
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
        per_child.append(
            {
                "parent_child_id": child_id,
                "branch_count": observed[0],
                "rup_closed_count": observed[1],
                "drat_planned_count": observed[2],
                "remaining_count": observed[3],
            }
        )

    sources = {
        label: {
            "path": display_path(path, root),
            "sha256": hashes[label],
        }
        for label, path in paths.items()
    }
    plan = {
        "record_type": "fourth-word-drat-proof-plan",
        "schema_version": 2,
        "sources": sources,
        "selection": {
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
        },
        "proof_pipeline": {
            "solver": "glucose4",
            "solver_output": "text DRAT",
            "core_extractor": "drat-trim -l",
            "retained_proof": "trimmed text DRAT",
            "compression": "gzip with mtime zero",
            "checker": "drat-trim",
            "checker_commit": DRAT_TRIM_COMMIT,
        },
        "case_count": len(selected),
        "remaining_count": len(remaining),
        "selected_set_sha256": selected_digest,
        "remaining_set_sha256": remaining_digest,
        "per_child": per_child,
        "completion_implication": {
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
        },
        "cases": selected,
        "remaining_cases": remaining,
    }
    payload = (
        json.dumps(plan, indent=2, sort_keys=True) + "\n"
    ).encode("ascii")
    if args.verify_existing:
        try:
            retained_payload, _retained_digest = load_authenticated_bytes(
                output,
                "retained DRAT plan",
            )
        except RuntimeError as error:
            raise SystemExit("retained DRAT plan is missing") from error
        if retained_payload != payload:
            raise SystemExit("retained DRAT plan differs from regeneration")
    else:
        if output.exists() or output.is_symlink():
            raise SystemExit(
                "DRAT plan output already exists; use --verify-existing"
            )
        atomic_write_json(output, plan)

    for label, path in paths.items():
        if (
            load_authenticated_bytes(
                path,
                label.replace("_", " "),
            )[1]
            != hashes[label]
        ):
            raise RuntimeError(f"{label} changed during DRAT plan generation")
    print(
        json.dumps(
            {
                "case_count": len(selected),
                "output": display_path(output, root),
                "remaining_count": len(remaining),
                "selected_set_sha256": selected_digest,
                "verified_existing": args.verify_existing,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
