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
import tempfile

from fourth_word_symmetry import fourth_orbits, orbit_manifest_digest
from generate_fourth_word_formula import reconstruct_branches
from generate_third_word_child_formula import (
    build_child_formula,
    display_path,
    find_parent_and_child,
    resolve_repository_path,
)
from repository_lock import acquire_repository_lock


PROOF_BYTES = b"0\n"
PROOF_COMPRESSED = bytes.fromhex(
    "1f8b08000000000002ff33e0020012cd4a7e02000000"
)
EXPECTED_CLOSED_SET_SHA256 = (
    "414d614aab49a3d01a604622d24b714c21e36ec1589afbe4a24b2980db7ef216"
)
EXPECTED_RESIDUAL_SET_SHA256 = (
    "f52df0cc136bd8d2854040ab3f869e84661d3a7261a751a99ec2f1cbe9273638"
)
TRANSACTION_DIRECTORY = Path(
    ".research-artifacts/fourth-word-rup-plan-transactions"
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bytes_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_snapshot(path: Path) -> tuple[dict[str, object], str]:
    payload = path.read_bytes()
    return (
        json.loads(payload.decode("ascii")),
        bytes_sha256(payload),
    )


def aliases_existing_file(
    path: Path,
    sources: set[Path],
) -> bool:
    return path.exists() and any(
        os.path.samefile(path, source)
        for source in sources
    )


def repository_python_sources(root: Path) -> set[Path]:
    return {
        path.resolve()
        for directory in (root / "src", root / "tools")
        for path in directory.rglob("*.py")
    }


def require_regular_single_link(path: Path, description: str) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_nlink != 1
    ):
        raise RuntimeError(
            f"{description} is not a single-link regular file: {path}"
        )


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_unlink(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    path.unlink()
    fsync_directory(path.parent)


def durable_replace(source: Path, destination: Path) -> None:
    os.replace(source, destination)
    fsync_directory(destination.parent)
    if source.parent != destination.parent:
        fsync_directory(source.parent)


def durable_remove_tree(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"transaction staging path is invalid: {path}")
    shutil.rmtree(path)
    fsync_directory(path.parent)


def durable_make_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_dir():
            raise RuntimeError(f"directory path is invalid: {path}")
        return
    parent = path.parent
    if parent == path:
        raise RuntimeError(f"directory has no existing ancestor: {path}")
    durable_make_directory(parent)
    path.mkdir()
    fsync_directory(parent)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    durable_make_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        durable_replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            durable_unlink(temporary)


def atomic_write_json(path: Path, record: dict[str, object]) -> None:
    atomic_write_bytes(
        path,
        (
            json.dumps(record, indent=2, sort_keys=True) + "\n"
        ).encode("ascii"),
    )


def plan_transaction_paths(
    classification_path: Path,
    plan_path: Path,
    *,
    root: Path,
) -> tuple[Path, Path]:
    identity = (
        f"{display_path(classification_path, root)}\n"
        f"{display_path(plan_path, root)}\n"
    )
    digest = hashlib.sha256(identity.encode("ascii")).hexdigest()
    directory = repository_path(TRANSACTION_DIRECTORY, root)
    return (
        directory / f"{digest}.json",
        directory / f"{digest}.staging",
    )


def transaction_record(
    state: str,
    *,
    classification_path: Path,
    plan_path: Path,
    staging_directory: Path,
    root: Path,
    classification_sha256: str | None = None,
    plan_sha256: str | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "record_type": "fourth-word-rup-plan-transaction",
        "schema_version": 1,
        "state": state,
        "classification_output": display_path(
            classification_path,
            root,
        ),
        "plan_output": display_path(plan_path, root),
        "staging_directory": display_path(staging_directory, root),
    }
    if state == "ready":
        if classification_sha256 is None or plan_sha256 is None:
            raise RuntimeError("ready transaction hashes are missing")
        record["classification_sha256"] = classification_sha256
        record["plan_sha256"] = plan_sha256
    elif state != "building":
        raise RuntimeError(f"unsupported transaction state: {state}")
    return record


def begin_plan_transaction(
    journal_path: Path,
    staging_directory: Path,
    *,
    classification_path: Path,
    plan_path: Path,
    root: Path,
) -> None:
    if journal_path.exists() or journal_path.is_symlink():
        raise RuntimeError("plan transaction journal already exists")
    if staging_directory.exists() or staging_directory.is_symlink():
        raise RuntimeError("plan transaction staging directory already exists")
    atomic_write_json(
        journal_path,
        transaction_record(
            "building",
            classification_path=classification_path,
            plan_path=plan_path,
            staging_directory=staging_directory,
            root=root,
        ),
    )
    staging_directory.mkdir()
    fsync_directory(staging_directory.parent)


def mark_plan_transaction_ready(
    journal_path: Path,
    staging_directory: Path,
    *,
    classification_path: Path,
    plan_path: Path,
    root: Path,
) -> None:
    staged_classification = staging_directory / "classification.json"
    staged_plan = staging_directory / "plan.json"
    require_regular_single_link(
        staged_classification,
        "staged classification",
    )
    require_regular_single_link(staged_plan, "staged proof plan")
    fsync_directory(staging_directory)
    atomic_write_json(
        journal_path,
        transaction_record(
            "ready",
            classification_path=classification_path,
            plan_path=plan_path,
            staging_directory=staging_directory,
            root=root,
            classification_sha256=file_sha256(staged_classification),
            plan_sha256=file_sha256(staged_plan),
        ),
    )


def recover_plan_transaction(
    journal_path: Path,
    staging_directory: Path,
    *,
    classification_path: Path,
    plan_path: Path,
    root: Path,
) -> str:
    if not journal_path.exists() and not journal_path.is_symlink():
        if staging_directory.exists() or staging_directory.is_symlink():
            durable_remove_tree(staging_directory)
            return "removed-orphan-staging"
        return "none"
    require_regular_single_link(journal_path, "plan transaction journal")
    try:
        record = json.loads(journal_path.read_text(encoding="ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("plan transaction journal is invalid") from exc
    expected_common = transaction_record(
        str(record.get("state")),
        classification_path=classification_path,
        plan_path=plan_path,
        staging_directory=staging_directory,
        root=root,
        classification_sha256=record.get("classification_sha256"),
        plan_sha256=record.get("plan_sha256"),
    )
    if record != expected_common:
        raise RuntimeError("plan transaction journal is invalid")
    state = str(record["state"])
    if state == "building":
        if (
            classification_path.exists()
            or classification_path.is_symlink()
            or plan_path.exists()
            or plan_path.is_symlink()
        ):
            raise RuntimeError(
                "building transaction conflicts with final outputs"
            )
        durable_remove_tree(staging_directory)
        durable_unlink(journal_path)
        return "cleaned-building"

    staging_exists = (
        staging_directory.exists() or staging_directory.is_symlink()
    )
    if staging_exists and (
        staging_directory.is_symlink()
        or not staging_directory.is_dir()
    ):
        raise RuntimeError(
            f"transaction staging path is invalid: {staging_directory}"
        )
    staged_paths = {
        classification_path: staging_directory / "classification.json",
        plan_path: staging_directory / "plan.json",
    }
    expected_hashes = {
        classification_path: str(record["classification_sha256"]),
        plan_path: str(record["plan_sha256"]),
    }
    for output, staged in staged_paths.items():
        expected_hash = expected_hashes[output]
        if output.exists() or output.is_symlink():
            require_regular_single_link(output, "transaction output")
            if file_sha256(output) != expected_hash:
                raise RuntimeError(
                    f"transaction output hash differs: "
                    f"{display_path(output, root)}"
                )
            if staging_exists and (
                staged.exists() or staged.is_symlink()
            ):
                require_regular_single_link(staged, "staged transaction output")
                if file_sha256(staged) != expected_hash:
                    raise RuntimeError(
                        "staged transaction output hash differs"
                    )
                durable_unlink(staged)
            continue
        if not staging_exists:
            raise RuntimeError(
                "transaction staging directory is missing before "
                "all outputs were promoted"
            )
        require_regular_single_link(staged, "staged transaction output")
        if file_sha256(staged) != expected_hash:
            raise RuntimeError("staged transaction output hash differs")
        durable_make_directory(output.parent)
        durable_replace(staged, output)
    if staging_exists:
        if any(staging_directory.iterdir()):
            raise RuntimeError("transaction staging directory is not empty")
        staging_directory.rmdir()
        fsync_directory(staging_directory.parent)
    durable_unlink(journal_path)
    return "completed-ready"


def write_plan_transaction(
    classification_path: Path,
    classification_payload: bytes,
    plan_path: Path,
    plan_payload: bytes,
    *,
    root: Path,
) -> str:
    journal_path, staging_directory = plan_transaction_paths(
        classification_path,
        plan_path,
        root=root,
    )
    begin_plan_transaction(
        journal_path,
        staging_directory,
        classification_path=classification_path,
        plan_path=plan_path,
        root=root,
    )
    atomic_write_bytes(
        staging_directory / "classification.json",
        classification_payload,
    )
    atomic_write_bytes(staging_directory / "plan.json", plan_payload)
    mark_plan_transaction_ready(
        journal_path,
        staging_directory,
        classification_path=classification_path,
        plan_path=plan_path,
        root=root,
    )
    return recover_plan_transaction(
        journal_path,
        staging_directory,
        classification_path=classification_path,
        plan_path=plan_path,
        root=root,
    )


def record_digest(records: list[dict[str, object]]) -> str:
    payload = "".join(
        f"{record['branch_id']}:{record['branch_sha256']}\n"
        for record in records
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def validate_fourth_child(
    parent: dict[str, object],
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
        parent,
        child,
        length=length,
        matching=bool(frontier_parent["matching_eligible"]),
    )
    branches = reconstruct_branches(parent, child, grouped)
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("child_frontier", type=Path)
    parser.add_argument("fourth_frontier", type=Path)
    parser.add_argument("classification_output", type=Path)
    parser.add_argument("plan_output", type=Path)
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()

    try:
        import pysat
        from pysat.solvers import Solver
    except ImportError as exc:
        raise SystemExit(
            "python-sat is required; install requirements-sat.txt"
        ) from exc

    root = repository_root()
    repository_lock = acquire_repository_lock(root)
    atexit.register(repository_lock.close)
    source_paths = {
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
    }
    classification_path = repository_path(
        args.classification_output,
        root,
    )
    plan_path = repository_path(args.plan_output, root)
    source_set = set(source_paths.values())
    if len(source_set) != 4:
        raise SystemExit("source manifests must use distinct paths")
    if not all(path.is_file() for path in source_set):
        raise SystemExit("source manifests must be regular files")
    source_list = list(source_set)
    if any(
        os.path.samefile(left, right)
        for index, left in enumerate(source_list)
        for right in source_list[index + 1:]
    ):
        raise SystemExit("source manifests alias the same file")
    output_paths = {classification_path, plan_path}
    if len(output_paths) != 2:
        raise SystemExit("classification and plan outputs must be distinct")
    if (
        classification_path.exists()
        and plan_path.exists()
        and os.path.samefile(classification_path, plan_path)
    ):
        raise SystemExit("classification and plan outputs alias the same file")
    for output in output_paths:
        if output.exists() or output.is_symlink():
            require_regular_single_link(output, "output")
        if output in source_set or aliases_existing_file(output, source_set):
            raise SystemExit("an output path aliases a source manifest")
    python_sources = repository_python_sources(root)
    if (
        output_paths & python_sources
        or any(
            aliases_existing_file(output, python_sources)
            for output in output_paths
        )
    ):
        raise SystemExit("an output path aliases repository source code")
    journal_path, staging_directory = plan_transaction_paths(
        classification_path,
        plan_path,
        root=root,
    )
    recovery_outcome = recover_plan_transaction(
        journal_path,
        staging_directory,
        classification_path=classification_path,
        plan_path=plan_path,
        root=root,
    )
    verify_existing = (
        args.verify_existing
        or recovery_outcome == "completed-ready"
    )
    if verify_existing:
        if not all(path.is_file() for path in output_paths):
            raise SystemExit("retained classification or plan is missing")
    elif any(path.exists() for path in output_paths):
        if all(path.is_file() for path in output_paths):
            verify_existing = True
            recovery_outcome = "recognized-committed-outputs"
        else:
            raise SystemExit(
                "classification or plan output is incomplete"
            )

    source_records: dict[str, dict[str, object]] = {}
    source_hashes: dict[str, str] = {}
    for label, path in source_paths.items():
        source_records[label], source_hashes[label] = load_snapshot(path)
    parent_manifest = source_records["parent_manifest"]
    third_manifest = source_records["third_word_manifest"]
    child_frontier = source_records["child_frontier"]
    fourth_frontier = source_records["fourth_frontier"]
    if source_hashes["parent_manifest"] != child_frontier["sources"][
        "stage1_parent_manifest"
    ]["sha256"]:
        raise SystemExit("parent manifest does not match child frontier")
    if source_hashes["third_word_manifest"] != child_frontier["sources"][
        "third_word_manifest"
    ]["sha256"]:
        raise SystemExit("third manifest does not match child frontier")
    for label in (
        "parent_manifest",
        "third_word_manifest",
        "child_frontier",
    ):
        if source_hashes[label] != fourth_frontier["sources"][label][
            "sha256"
        ]:
            raise SystemExit(
                f"{label} does not match fourth-word frontier"
            )

    length = int(parent_manifest["length"])
    parents = {
        str(parent["case_id"]): parent
        for parent in parent_manifest["cases"]
    }
    third_parents = {
        str(parent["parent_case_id"]): parent
        for parent in third_manifest["parents"]
    }
    base_hashes: dict[Path, str] = {}
    records = []
    per_child = []
    for fourth_child in fourth_frontier["children"]:
        child_id = str(fourth_child["parent_child_id"])
        frontier_parent, child = find_parent_and_child(
            child_frontier,
            child_id,
        )
        case_id = str(frontier_parent["parent_case_id"])
        parent = parents[case_id]
        third_parent = third_parents[case_id]
        grouped, branches = validate_fourth_child(
            parent,
            frontier_parent,
            child,
            fourth_child,
            length=length,
        )
        base_record = frontier_parent["constraint_profile"][
            "minimum_distance"
        ]["formula"]
        base_formula = resolve_repository_path(
            base_record["path"],
            root,
        )
        digest = file_sha256(base_formula)
        if digest != base_record["sha256"]:
            raise SystemExit("retained base formula hash mismatch")
        base_hashes[base_formula] = digest
        _, clauses, _ = build_child_formula(
            base_formula,
            parent,
            third_parent,
            frontier_parent,
            child,
            length=length,
        )
        child_records = []
        earlier_words: list[int] = []
        with Solver(
            name="glucose4",
            bootstrap_with=clauses,
        ) as primary_solver:
            with Solver(
                name="glucose42",
                bootstrap_with=clauses,
            ) as cross_check_solver:
                for branch, (_, words) in zip(branches, grouped):
                    canonical_word = min(words)
                    assumptions = [canonical_word + 1]
                    assumptions.extend(
                        -(word + 1) for word in earlier_words
                    )
                    primary_consistent, _ = primary_solver.propagate(
                        assumptions=assumptions
                    )
                    cross_check_consistent, _ = (
                        cross_check_solver.propagate(
                            assumptions=assumptions
                        )
                    )
                    if primary_consistent != cross_check_consistent:
                        raise RuntimeError(
                            f"{branch['branch_id']}: propagation "
                            "solvers disagree"
                        )
                    status = (
                        "rup-conflict"
                        if primary_consistent is False
                        else "not-rup-conflict"
                    )
                    record = {
                        "branch_id": branch["branch_id"],
                        "branch_sha256": branch["branch_sha256"],
                        "parent_child_id": child_id,
                        "fourth_orbit_index": branch[
                            "fourth_orbit_index"
                        ],
                        "assumption_count": len(assumptions),
                        "status": status,
                    }
                    records.append(record)
                    child_records.append(record)
                    earlier_words.extend(words)
        child_counts = Counter(
            str(record["status"]) for record in child_records
        )
        per_child.append(
            {
                "parent_child_id": child_id,
                "branch_count": len(child_records),
                "rup_conflict_count": child_counts["rup-conflict"],
                "not_rup_conflict_count": child_counts[
                    "not-rup-conflict"
                ],
            }
        )

    counts = Counter(str(record["status"]) for record in records)
    closed = [
        record
        for record in records
        if record["status"] == "rup-conflict"
    ]
    residual = [
        record
        for record in records
        if record["status"] == "not-rup-conflict"
    ]
    closed_digest = record_digest(closed)
    residual_digest = record_digest(residual)
    if closed_digest != EXPECTED_CLOSED_SET_SHA256:
        raise RuntimeError("unit-propagation closed set changed")
    if residual_digest != EXPECTED_RESIDUAL_SET_SHA256:
        raise RuntimeError("unit-propagation residual set changed")
    retained_sources = {
        label: {
            "path": display_path(path, root),
            "sha256": source_hashes[label],
        }
        for label, path in source_paths.items()
    }
    classification = {
        "record_type": "fourth-word-unit-propagation-classification",
        "schema_version": 1,
        "sources": retained_sources,
        "solver": "glucose4",
        "cross_check_solver": "glucose42",
        "solver_agreement": True,
        "python_sat_version": pysat.__version__,
        "method": "propagation under branch units without SAT search",
        "proof_claim": False,
        "branch_count": len(records),
        "rup_conflict_count": counts["rup-conflict"],
        "not_rup_conflict_count": counts["not-rup-conflict"],
        "closed_set_sha256": closed_digest,
        "residual_set_sha256": residual_digest,
        "per_child": per_child,
        "branches": records,
    }
    classification_text = (
        json.dumps(classification, indent=2, sort_keys=True) + "\n"
    )
    classification_sha256 = hashlib.sha256(
        classification_text.encode("ascii")
    ).hexdigest()
    cases = [
        {
            key: record[key]
            for key in (
                "branch_id",
                "branch_sha256",
                "parent_child_id",
                "fourth_orbit_index",
            )
        }
        for record in closed
    ]
    plan = {
        "record_type": "fourth-word-rup-proof-plan",
        "schema_version": 1,
        "sources": retained_sources,
        "classification": {
            "path": display_path(classification_path, root),
            "sha256": classification_sha256,
        },
        "proof_strategy": "empty-clause RUP",
        "proof_format": "text DRAT",
        "shared_proof": {
            "uncompressed_bytes": len(PROOF_BYTES),
            "uncompressed_sha256": bytes_sha256(PROOF_BYTES),
            "compressed_bytes": len(PROOF_COMPRESSED),
            "compressed_sha256": bytes_sha256(PROOF_COMPRESSED),
            "compression": "gzip",
        },
        "case_count": len(cases),
        "closed_set_sha256": closed_digest,
        "residual_set_sha256": residual_digest,
        "cases": cases,
    }

    input_hashes = {
        **{
            path: source_hashes[label]
            for label, path in source_paths.items()
        },
        **base_hashes,
    }
    for path, digest in input_hashes.items():
        if file_sha256(path) != digest:
            raise RuntimeError(
                f"input changed during classification: "
                f"{display_path(path, root)}"
            )
    plan_text = (
        json.dumps(plan, indent=2, sort_keys=True) + "\n"
    ).encode("ascii")
    if verify_existing:
        if classification_path.read_bytes() != classification_text.encode(
            "ascii"
        ):
            raise RuntimeError("retained classification changed")
        if plan_path.read_bytes() != plan_text:
            raise RuntimeError("retained proof plan changed")
    else:
        recovery_outcome = write_plan_transaction(
            classification_path,
            classification_text.encode("ascii"),
            plan_path,
            plan_text,
            root=root,
        )
    print(
        json.dumps(
            {
                "branch_count": len(records),
                "classification": display_path(
                    classification_path,
                    root,
                ),
                "not_rup_conflict_count": len(residual),
                "plan": display_path(plan_path, root),
                "transaction_recovery": recovery_outcome,
                "rup_conflict_count": len(closed),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
