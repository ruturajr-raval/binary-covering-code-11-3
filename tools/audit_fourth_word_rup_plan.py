#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

from repository_lock import acquire_repository_lock


EXPECTED_CHILD_COUNTS = {
    "w4-weight5-intersection0::orbit-005": (85, 50, 35),
    "w4-weight5-intersection0::orbit-007": (76, 53, 23),
    "w4-weight5-intersection0::orbit-014": (73, 41, 32),
    "w4-weight5-intersection0::orbit-015": (116, 40, 76),
}
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


def display_path(path: Path, root: Path) -> str:
    return str(repository_path(path, root).relative_to(root))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_snapshot(path: Path) -> tuple[dict[str, object], str]:
    payload = path.read_bytes()
    return (
        json.loads(payload.decode("ascii")),
        hashlib.sha256(payload).hexdigest(),
    )


def record_digest(records: list[dict[str, object]]) -> str:
    payload = "".join(
        f"{record['branch_id']}:{record['branch_sha256']}\n"
        for record in records
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("child_frontier", type=Path)
    parser.add_argument("fourth_frontier", type=Path)
    parser.add_argument("classification", type=Path)
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()

    root = repository_root()
    repository_lock = acquire_repository_lock(root)
    atexit.register(repository_lock.close)
    paths = {
        "parent_manifest": repository_path(args.parent_manifest, root),
        "third_word_manifest": repository_path(
            args.third_word_manifest,
            root,
        ),
        "child_frontier": repository_path(args.child_frontier, root),
        "fourth_frontier": repository_path(
            args.fourth_frontier,
            root,
        ),
        "classification": repository_path(
            args.classification,
            root,
        ),
        "plan": repository_path(args.plan, root),
    }
    if len(set(paths.values())) != len(paths):
        raise SystemExit("RUP plan audit inputs must use distinct files")
    if not all(path.is_file() for path in paths.values()):
        raise SystemExit("RUP plan audit inputs must be regular files")
    path_list = list(paths.values())
    if any(
        os.path.samefile(left, right)
        for index, left in enumerate(path_list)
        for right in path_list[index + 1:]
    ):
        raise SystemExit("RUP plan audit inputs alias the same file")

    records: dict[str, dict[str, object]] = {}
    hashes: dict[str, str] = {}
    for label, path in paths.items():
        records[label], hashes[label] = load_snapshot(path)
    child_frontier = records["child_frontier"]
    fourth_frontier = records["fourth_frontier"]
    classification = records["classification"]
    plan = records["plan"]

    expected_classification_keys = {
        "record_type",
        "schema_version",
        "sources",
        "solver",
        "cross_check_solver",
        "solver_agreement",
        "python_sat_version",
        "method",
        "proof_claim",
        "branch_count",
        "rup_conflict_count",
        "not_rup_conflict_count",
        "closed_set_sha256",
        "residual_set_sha256",
        "per_child",
        "branches",
    }
    if set(classification) != expected_classification_keys:
        raise SystemExit("classification schema is incorrect")
    expected_plan_keys = {
        "record_type",
        "schema_version",
        "sources",
        "classification",
        "proof_strategy",
        "proof_format",
        "shared_proof",
        "case_count",
        "closed_set_sha256",
        "residual_set_sha256",
        "cases",
    }
    if set(plan) != expected_plan_keys:
        raise SystemExit("RUP proof-plan schema is incorrect")

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
        )
    }
    if hashes["parent_manifest"] != child_frontier["sources"][
        "stage1_parent_manifest"
    ]["sha256"]:
        raise SystemExit("parent manifest does not match child frontier")
    if hashes["third_word_manifest"] != child_frontier["sources"][
        "third_word_manifest"
    ]["sha256"]:
        raise SystemExit("third manifest does not match child frontier")
    for label in (
        "parent_manifest",
        "third_word_manifest",
        "child_frontier",
    ):
        if hashes[label] != fourth_frontier["sources"][label]["sha256"]:
            raise SystemExit(
                f"{label} does not match fourth-word frontier"
            )

    if classification["record_type"] != (
        "fourth-word-unit-propagation-classification"
    ):
        raise SystemExit("unexpected classification record type")
    if classification["schema_version"] != 1:
        raise SystemExit("unsupported classification schema")
    if classification["sources"] != expected_sources:
        raise SystemExit("classification source authentication failed")
    if classification["solver"] != "glucose4":
        raise SystemExit("classification solver changed")
    if classification["cross_check_solver"] != "glucose42":
        raise SystemExit("classification cross-check solver changed")
    if classification["solver_agreement"] is not True:
        raise SystemExit("classification solvers did not agree")
    if classification["python_sat_version"] != "1.9.dev15":
        raise SystemExit("classification python-sat version changed")
    if classification["method"] != (
        "propagation under branch units without SAT search"
    ):
        raise SystemExit("classification method changed")
    if classification["proof_claim"] is not False:
        raise SystemExit("classification must not make a proof claim")

    expected_identities = []
    expected_child_order = []
    for child in fourth_frontier["children"]:
        child_id = str(child["parent_child_id"])
        expected_child_order.append(child_id)
        for branch in child["branches"]:
            expected_identities.append(
                {
                    "branch_id": branch["branch_id"],
                    "branch_sha256": branch["branch_sha256"],
                    "parent_child_id": child_id,
                    "fourth_orbit_index": branch[
                        "fourth_orbit_index"
                    ],
                    "assumption_count": (
                        int(branch["earlier_word_count"]) + 1
                    ),
                }
            )
    branches = classification["branches"]
    if len(branches) != len(expected_identities):
        raise SystemExit("classification branch count is incorrect")
    if len({record["branch_id"] for record in branches}) != len(branches):
        raise SystemExit("classification branch identifiers are not unique")
    for expected, observed in zip(expected_identities, branches):
        if set(observed) != {
            "branch_id",
            "branch_sha256",
            "parent_child_id",
            "fourth_orbit_index",
            "assumption_count",
            "status",
        }:
            raise SystemExit("classification branch schema is incorrect")
        identity = {
            key: observed[key]
            for key in expected
        }
        if identity != expected:
            raise SystemExit("classification branch identity is incorrect")
        if observed["status"] not in {
            "rup-conflict",
            "not-rup-conflict",
        }:
            raise SystemExit("classification branch status is invalid")

    counts = Counter(str(record["status"]) for record in branches)
    if (
        int(classification["branch_count"]) != len(branches)
        or int(classification["rup_conflict_count"])
        != counts["rup-conflict"]
        or int(classification["not_rup_conflict_count"])
        != counts["not-rup-conflict"]
    ):
        raise SystemExit("classification aggregate counts are incorrect")
    if (
        len(branches),
        counts["rup-conflict"],
        counts["not-rup-conflict"],
    ) != (350, 184, 166):
        raise SystemExit("classification exact counts changed")

    per_child = classification["per_child"]
    if [
        str(record["parent_child_id"]) for record in per_child
    ] != expected_child_order:
        raise SystemExit("classification child order is incorrect")
    for record in per_child:
        if set(record) != {
            "parent_child_id",
            "branch_count",
            "rup_conflict_count",
            "not_rup_conflict_count",
        }:
            raise SystemExit("classification child schema is incorrect")
        child_id = str(record["parent_child_id"])
        expected = EXPECTED_CHILD_COUNTS.get(child_id)
        observed = (
            int(record["branch_count"]),
            int(record["rup_conflict_count"]),
            int(record["not_rup_conflict_count"]),
        )
        if expected is None or observed != expected:
            raise SystemExit(
                f"{child_id}: classification counts are incorrect"
            )

    closed = [
        record
        for record in branches
        if record["status"] == "rup-conflict"
    ]
    residual = [
        record
        for record in branches
        if record["status"] == "not-rup-conflict"
    ]
    closed_digest = record_digest(closed)
    residual_digest = record_digest(residual)
    if closed_digest != EXPECTED_CLOSED_SET_SHA256:
        raise SystemExit("classification closed set changed")
    if residual_digest != EXPECTED_RESIDUAL_SET_SHA256:
        raise SystemExit("classification residual set changed")
    if classification["closed_set_sha256"] != closed_digest:
        raise SystemExit("classification closed-set digest is incorrect")
    if classification["residual_set_sha256"] != residual_digest:
        raise SystemExit("classification residual-set digest is incorrect")

    if plan["record_type"] != "fourth-word-rup-proof-plan":
        raise SystemExit("unexpected RUP proof-plan record type")
    if plan["schema_version"] != 1:
        raise SystemExit("unsupported RUP proof-plan schema")
    if plan["sources"] != expected_sources:
        raise SystemExit("RUP proof-plan sources are incorrect")
    if plan["classification"] != {
        "path": display_path(paths["classification"], root),
        "sha256": hashes["classification"],
    }:
        raise SystemExit("RUP proof-plan classification is incorrect")
    expected_proof = {
        "uncompressed_bytes": len(PROOF_BYTES),
        "uncompressed_sha256": hashlib.sha256(
            PROOF_BYTES
        ).hexdigest(),
        "compressed_bytes": len(PROOF_COMPRESSED),
        "compressed_sha256": hashlib.sha256(
            PROOF_COMPRESSED
        ).hexdigest(),
        "compression": "gzip",
    }
    if plan["proof_strategy"] != "empty-clause RUP":
        raise SystemExit("RUP proof strategy changed")
    if plan["proof_format"] != "text DRAT":
        raise SystemExit("RUP proof format changed")
    if plan["shared_proof"] != expected_proof:
        raise SystemExit("shared RUP proof identity is incorrect")
    expected_cases = [
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
    if plan["cases"] != expected_cases:
        raise SystemExit("RUP proof-plan cases are incorrect")
    if int(plan["case_count"]) != len(expected_cases):
        raise SystemExit("RUP proof-plan case count is incorrect")
    if plan["closed_set_sha256"] != closed_digest:
        raise SystemExit("RUP proof-plan closed-set digest is incorrect")
    if plan["residual_set_sha256"] != residual_digest:
        raise SystemExit("RUP proof-plan residual-set digest is incorrect")

    for label, path in paths.items():
        if file_sha256(path) != hashes[label]:
            raise RuntimeError(f"{label} changed during RUP plan audit")
    print(
        json.dumps(
            {
                "branch_count": len(branches),
                "not_rup_conflict_count": len(residual),
                "rup_conflict_count": len(closed),
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
