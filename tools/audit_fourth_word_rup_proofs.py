#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
from collections import Counter
from datetime import date
import gzip
import hashlib
import json
import os
from pathlib import Path

from repository_lock import acquire_repository_lock


DRAT_TRIM_COMMIT = "2e3b2dc0ecf938addbd779d42877b6ed69d9a985"
DRAT_TRIM_REPOSITORY = "https://github.com/marijnheule/drat-trim.git"
EXPECTED_CHILD_COUNTS = {
    "w4-weight5-intersection0::orbit-005": (85, 50, 35),
    "w4-weight5-intersection0::orbit-007": (76, 53, 23),
    "w4-weight5-intersection0::orbit-014": (73, 41, 32),
    "w4-weight5-intersection0::orbit-015": (116, 40, 76),
}
FORMULA_DIRECTORY = Path("build/proofs/fourth-word")
PROOF_DIRECTORY = Path("evidence/proofs/fourth-word-rup-v1")
PROOF_INDEX = Path("evidence/fourth-word-rup-proof-index-v1.json")
REPLAY_ATTESTATION = Path(
    "evidence/fourth-word-rup-replay-attestation-v1.json"
)
PIPELINE_FILES = {
    "bundle_certifier": Path(
        "tools/certify_fourth_word_rup_bundle.py"
    ),
    "certified_revision_manager": Path(
        "tools/manage_fourth_word_rup_revision.py"
    ),
    "lock_assertion": Path("tools/assert_repository_lock.py"),
    "checker_bootstrap": Path("tools/bootstrap_drat_trim.py"),
    "formula_generator": Path("tools/generate_fourth_word_formula.py"),
    "formula_auditor": Path("tools/audit_fourth_word_formula.py"),
    "index_auditor": Path("tools/audit_fourth_word_rup_proofs.py"),
    "manifest_verifier": Path("tools/verify_checksum_manifest.py"),
    "plan_auditor": Path("tools/audit_fourth_word_rup_plan.py"),
    "plan_generator": Path("tools/generate_fourth_word_rup_plan.py"),
    "proof_checker_driver": Path("tools/check_drat_proof.py"),
    "proof_orchestrator": Path("tools/prove_fourth_word_rup_cases.py"),
    "repository_lock": Path("tools/repository_lock.py"),
    "repository_lock_runner": Path(
        "tools/run_with_repository_lock.py"
    ),
    "makefile": Path("Makefile"),
    "proof_requirements": Path("requirements-proof.txt"),
    "replay_requirements": Path("requirements-replay.txt"),
    "sat_requirements": Path("requirements-sat.txt"),
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


def directory_sha256(directory: Path) -> str:
    if not directory.is_dir() or directory.is_symlink():
        raise SystemExit("proof artifact directory is invalid")
    payload = bytearray()
    for entry in sorted(directory.iterdir(), key=lambda path: path.name):
        require_regular_single_link(entry, "proof artifact")
        payload.extend(entry.name.encode("ascii"))
        payload.extend(b":")
        payload.extend(file_sha256(entry).encode("ascii"))
        payload.extend(b"\n")
    return hashlib.sha256(bytes(payload)).hexdigest()


def python_tree_record(root: Path) -> dict[str, object]:
    sources = []
    for relative_directory in (Path("src"), Path("tools")):
        directory = repository_path(relative_directory, root)
        if not directory.is_dir() or directory.is_symlink():
            raise SystemExit(
                f"Python source directory is invalid: {directory}"
            )
        for path in directory.rglob("*.py"):
            source = repository_path(path, root)
            require_regular_single_link(source, "Python source")
            sources.append(source)
    sources.sort()
    payload = "".join(
        f"{path.relative_to(root)}:{file_sha256(path)}\n"
        for path in sources
    )
    return {
        "roots": ["src", "tools"],
        "file_count": len(sources),
        "sha256": hashlib.sha256(payload.encode("ascii")).hexdigest(),
    }


def validate_pipeline_provenance(
    pipeline_files: object,
    pipeline_tree: object,
    *,
    root: Path,
) -> tuple[dict[Path, str], dict[str, object]]:
    if (
        not isinstance(pipeline_files, dict)
        or set(pipeline_files) != set(PIPELINE_FILES)
    ):
        raise SystemExit("proof-index pipeline file set is incorrect")
    pipeline_paths = {
        label: repository_path(relative_path, root)
        for label, relative_path in PIPELINE_FILES.items()
    }
    pipeline_hashes = {}
    for label, relative_path in PIPELINE_FILES.items():
        record = pipeline_files[label]
        pipeline_path = pipeline_paths[label]
        require_regular_single_link(
            pipeline_path,
            f"proof-index pipeline file {label}",
        )
        pipeline_hash = file_sha256(pipeline_path)
        pipeline_hashes[pipeline_path] = pipeline_hash
        expected_record = {
            "path": str(relative_path),
            "sha256": pipeline_hash,
        }
        if record != expected_record:
            raise SystemExit(
                f"proof-index pipeline record {label} does not match "
                "the current repository"
            )
    current_pipeline_tree = python_tree_record(root)
    if pipeline_tree != current_pipeline_tree:
        raise SystemExit(
            "proof-index Python source tree does not match "
            "the current repository"
        )
    return pipeline_hashes, current_pipeline_tree


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="ascii"))


def require_regular_single_link(path: Path, description: str) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_nlink != 1
    ):
        raise SystemExit(
            f"{description} is not a single-link regular file: {path}"
        )


def record_digest(records: list[dict[str, object]]) -> str:
    payload = "".join(
        f"{record['branch_id']}:{record['branch_sha256']}\n"
        for record in records
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def branch_slug(branch_id: str) -> str:
    slug = branch_id.replace("::", "--")
    if not slug or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
        for character in slug
    ):
        raise SystemExit(f"branch id is not path-safe: {branch_id}")
    return slug


def require_sha256(value: object, message: str) -> str:
    if not isinstance(value, str):
        raise SystemExit(message)
    digest = value
    if len(digest) != 64 or any(
        character not in "0123456789abcdef"
        for character in digest
    ):
        raise SystemExit(message)
    return digest


def require_exact_integer(value: object, message: str) -> int:
    if type(value) is not int:
        raise SystemExit(message)
    return value


def validate_attestation_environment(
    environment: object,
    *,
    expected_python_sat_version: object,
) -> None:
    environment_keys = {
        "python_implementation",
        "python_version",
        "python_executable_sha256",
        "python_executable_path",
        "python_sat_version",
        "python_sat_distribution_version",
        "python_sat_tree",
        "python_sat_native_modules",
        "platform_system",
        "platform_machine",
    }
    string_keys = environment_keys - {
        "python_executable_sha256",
        "python_executable_path",
        "python_sat_tree",
        "python_sat_native_modules",
    }
    if (
        not isinstance(environment, dict)
        or set(environment) != environment_keys
        or environment["python_sat_version"]
        != expected_python_sat_version
        or environment["python_sat_distribution_version"]
        != environment["python_sat_version"]
        or any(
            not isinstance(environment[key], str)
            or not environment[key]
            for key in string_keys
        )
    ):
        raise SystemExit("replay attestation environment is incorrect")
    require_sha256(
        environment["python_executable_sha256"],
        "replay attestation Python executable hash is invalid",
    )
    executable_path = environment["python_executable_path"]
    if (
        not isinstance(executable_path, dict)
        or set(executable_path) != {"scope", "value"}
        or executable_path["scope"]
        not in {"repository-relative", "absolute-path-sha256"}
        or not isinstance(executable_path["value"], str)
        or not executable_path["value"]
    ):
        raise SystemExit(
            "replay attestation Python executable path is incorrect"
        )
    if executable_path["scope"] == "absolute-path-sha256":
        require_sha256(
            executable_path["value"],
            "replay attestation Python executable path hash is invalid",
        )
    else:
        relative_path = Path(executable_path["value"])
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path.as_posix() != executable_path["value"]
        ):
            raise SystemExit(
                "replay attestation Python executable path is invalid"
            )
    python_sat_tree = environment["python_sat_tree"]
    if (
        not isinstance(python_sat_tree, dict)
        or set(python_sat_tree) != {"root", "file_count", "sha256"}
        or python_sat_tree["root"] != "pysat"
        or type(python_sat_tree["file_count"]) is not int
        or python_sat_tree["file_count"] <= 0
    ):
        raise SystemExit(
            "replay attestation python-sat tree is incorrect"
        )
    require_sha256(
        python_sat_tree["sha256"],
        "replay attestation python-sat tree hash is invalid",
    )
    native_modules = environment["python_sat_native_modules"]
    if (
        not isinstance(native_modules, dict)
        or set(native_modules) != {"pycard", "pyformula", "pysolvers"}
    ):
        raise SystemExit(
            "replay attestation python-sat native modules are incorrect"
        )
    for name, record in native_modules.items():
        if (
            not isinstance(record, dict)
            or set(record) != {"filename", "sha256"}
            or not isinstance(record["filename"], str)
            or not record["filename"]
        ):
            raise SystemExit(
                "replay attestation python-sat native module "
                f"is incorrect: {name}"
            )
        require_sha256(
            record["sha256"],
            "replay attestation python-sat native module "
            f"hash is invalid: {name}",
        )


def validate_replay_attestation(
    attestation: object,
    *,
    expected_index: dict[str, object],
    expected_pipeline_files: object,
    expected_pipeline_python_tree: object,
    expected_python_sat_version: object,
    expected_case_count: int,
    expected_case_outcomes_sha256: str,
    expected_closed_set_sha256: str,
    expected_residual_set_sha256: str,
) -> None:
    expected_keys = {
        "record_type",
        "schema_version",
        "provenance",
        "replay_date",
        "proof_index",
        "checker",
        "pipeline_files",
        "pipeline_python_tree",
        "environment",
        "case_count",
        "case_outcomes_sha256",
        "closed_set_sha256",
        "residual_set_sha256",
        "all_verified",
    }
    if not isinstance(attestation, dict) or set(attestation) != expected_keys:
        raise SystemExit("replay attestation schema is incorrect")
    if attestation["record_type"] != (
        "fourth-word-rup-replay-attestation"
    ):
        raise SystemExit("replay attestation type is incorrect")
    if (
        require_exact_integer(
            attestation["schema_version"],
            "replay attestation schema changed",
        )
        != 3
    ):
        raise SystemExit("replay attestation schema changed")
    if attestation["provenance"] != {
        "scope": "local self-attestation",
        "externally_signed": False,
    }:
        raise SystemExit("replay attestation provenance is incorrect")
    replay_date_value = attestation["replay_date"]
    if not isinstance(replay_date_value, str):
        raise SystemExit("replay attestation date is invalid")
    try:
        replay_date = date.fromisoformat(replay_date_value)
    except ValueError as exc:
        raise SystemExit("replay attestation date is invalid") from exc
    if replay_date.isoformat() != replay_date_value:
        raise SystemExit("replay attestation date is not canonical")
    if attestation["proof_index"] != expected_index:
        raise SystemExit("replay attestation index is incorrect")
    checker = attestation["checker"]
    if (
        not isinstance(checker, dict)
        or set(checker)
        != {"name", "repository", "commit", "binary_sha256"}
        or checker["name"] != "drat-trim"
        or checker["repository"] != DRAT_TRIM_REPOSITORY
        or checker["commit"] != DRAT_TRIM_COMMIT
    ):
        raise SystemExit("replay attestation checker is incorrect")
    require_sha256(
        checker["binary_sha256"],
        "replay attestation checker hash is invalid",
    )
    if attestation["pipeline_files"] != expected_pipeline_files:
        raise SystemExit(
            "replay attestation pipeline files are incorrect"
        )
    if (
        attestation["pipeline_python_tree"]
        != expected_pipeline_python_tree
    ):
        raise SystemExit("replay attestation Python tree is incorrect")
    validate_attestation_environment(
        attestation["environment"],
        expected_python_sat_version=expected_python_sat_version,
    )
    if (
        require_exact_integer(
            attestation["case_count"],
            "replay attestation case count is incorrect",
        )
        != expected_case_count
        or attestation["case_outcomes_sha256"]
        != expected_case_outcomes_sha256
        or attestation["closed_set_sha256"]
        != expected_closed_set_sha256
        or attestation["residual_set_sha256"]
        != expected_residual_set_sha256
        or attestation["all_verified"] is not True
    ):
        raise SystemExit("replay attestation result is incorrect")


def validate_check(
    check: dict[str, object],
    *,
    branch_id: str,
    formula_sha256: str,
) -> None:
    expected_keys = {
        "case_id",
        "checker",
        "checker_commit",
        "formula_sha256",
        "proof_compressed_sha256",
        "proof_uncompressed_sha256",
        "return_code",
        "verified",
        "checker_output_sha256",
        "checker_output_line_count",
        "checker_warning_count",
        "checker_timing_normalized",
        "checker_output",
    }
    if set(check) != expected_keys:
        raise SystemExit(f"{branch_id}: proof-check schema is incorrect")
    expected = {
        "case_id": branch_id,
        "checker": "drat-trim",
        "checker_commit": DRAT_TRIM_COMMIT,
        "formula_sha256": formula_sha256,
        "proof_compressed_sha256": hashlib.sha256(
            PROOF_COMPRESSED
        ).hexdigest(),
        "proof_uncompressed_sha256": hashlib.sha256(
            PROOF_BYTES
        ).hexdigest(),
        "return_code": 0,
        "verified": True,
        "checker_timing_normalized": True,
        "checker_warning_count": 0,
    }
    for key, value in expected.items():
        if check[key] != value:
            raise SystemExit(
                f"{branch_id}: proof-check field {key} is incorrect"
            )
    output = check["checker_output"]
    if not isinstance(output, list) or "s VERIFIED" not in output:
        raise SystemExit(f"{branch_id}: checker output is not verified")
    if not any(
        marker in str(line)
        for line in output
        for marker in (
            "UNSAT via unit propagation",
            "detected empty clause",
        )
    ):
        raise SystemExit(
            f"{branch_id}: checker did not verify by unit propagation"
        )
    stable_output = "\n".join(str(line) for line in output) + "\n"
    if check["checker_output_sha256"] != hashlib.sha256(
        stable_output.encode("utf-8")
    ).hexdigest():
        raise SystemExit(
            f"{branch_id}: checker output digest is incorrect"
        )
    if int(check["checker_output_line_count"]) < len(output):
        raise SystemExit(
            f"{branch_id}: checker output line count is incorrect"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("child_frontier", type=Path)
    parser.add_argument("fourth_frontier", type=Path)
    parser.add_argument("classification", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("index", type=Path)
    parser.add_argument("proof_directory", type=Path)
    parser.add_argument("--staged", action="store_true")
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
        "index": repository_path(args.index, root),
    }
    proof_directory = repository_path(args.proof_directory, root)
    if args.staged:
        if (
            paths["index"].parent != (root / PROOF_INDEX).parent
            or not paths["index"].name.startswith(
                f".{PROOF_INDEX.name}."
            )
            or proof_directory.parent
            != (root / PROOF_DIRECTORY).parent
            or not proof_directory.name.startswith(
                f".{PROOF_DIRECTORY.name}."
            )
        ):
            raise SystemExit("staged proof paths are not canonical")
    else:
        if paths["index"] != root / PROOF_INDEX:
            raise SystemExit("fourth-word proof index is not canonical")
        if proof_directory != root / PROOF_DIRECTORY:
            raise SystemExit("fourth-word proof directory is not canonical")
    if len(set(paths.values())) != len(paths):
        raise SystemExit("RUP proof audit inputs must use distinct files")
    for path in paths.values():
        require_regular_single_link(path, "RUP proof audit input")
    if not proof_directory.is_dir() or proof_directory.is_symlink():
        raise SystemExit("RUP proof directory is missing")
    path_list = list(paths.values())
    if any(
        os.path.samefile(left, right)
        for index, left in enumerate(path_list)
        for right in path_list[index + 1:]
    ):
        raise SystemExit("RUP proof audit inputs alias the same file")

    hashes = {
        label: file_sha256(path)
        for label, path in paths.items()
    }
    parent_manifest = load_json(paths["parent_manifest"])
    child_frontier = load_json(paths["child_frontier"])
    fourth_frontier = load_json(paths["fourth_frontier"])
    classification = load_json(paths["classification"])
    plan = load_json(paths["plan"])
    index = load_json(paths["index"])
    if set(classification) != {
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
    }:
        raise SystemExit("classification schema is incorrect")
    if set(plan) != {
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
    }:
        raise SystemExit("RUP proof-plan schema is incorrect")
    retained_sources = {
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
    if classification["sources"] != retained_sources:
        raise SystemExit("classification sources are incorrect")
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
    for fourth_child in fourth_frontier["children"]:
        child_id = str(fourth_child["parent_child_id"])
        expected_child_order.append(child_id)
        for branch in fourth_child["branches"]:
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
        if {
            key: observed[key]
            for key in expected
        } != expected:
            raise SystemExit("classification branch identity is incorrect")
        if observed["status"] not in {
            "rup-conflict",
            "not-rup-conflict",
        }:
            raise SystemExit("classification branch status is invalid")
    counts = Counter(str(record["status"]) for record in branches)
    if (
        int(classification["branch_count"]),
        int(classification["rup_conflict_count"]),
        int(classification["not_rup_conflict_count"]),
    ) != (350, 184, 166):
        raise SystemExit("classification exact counts changed")
    if (
        counts["rup-conflict"],
        counts["not-rup-conflict"],
    ) != (184, 166):
        raise SystemExit("classification status counts are incorrect")
    if [
        str(record["parent_child_id"])
        for record in classification["per_child"]
    ] != expected_child_order:
        raise SystemExit("classification child order is incorrect")
    for record in classification["per_child"]:
        if set(record) != {
            "parent_child_id",
            "branch_count",
            "rup_conflict_count",
            "not_rup_conflict_count",
        }:
            raise SystemExit("classification child schema is incorrect")
        child_id = str(record["parent_child_id"])
        observed = (
            int(record["branch_count"]),
            int(record["rup_conflict_count"]),
            int(record["not_rup_conflict_count"]),
        )
        if EXPECTED_CHILD_COUNTS.get(child_id) != observed:
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
    if plan["sources"] != retained_sources:
        raise SystemExit("proof-plan sources are incorrect")
    if plan["classification"] != {
        "path": display_path(paths["classification"], root),
        "sha256": hashes["classification"],
    }:
        raise SystemExit("proof plan does not match classification")
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
        raise SystemExit("proof strategy changed")
    if plan["proof_format"] != "text DRAT":
        raise SystemExit("proof format changed")
    if plan["shared_proof"] != expected_proof:
        raise SystemExit("shared proof identity is incorrect")
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
    if (
        int(plan["case_count"]) != 184
        or plan["cases"] != expected_cases
    ):
        raise SystemExit("proof plan does not contain the exact cases")
    if plan["closed_set_sha256"] != closed_digest:
        raise SystemExit("proof-plan closed-set digest is incorrect")
    if plan["residual_set_sha256"] != residual_digest:
        raise SystemExit("proof-plan residual-set digest is incorrect")

    expected_index_keys = {
        "record_type",
        "schema_version",
        "sources",
        "classification",
        "proof_plan",
        "pipeline_files",
        "pipeline_python_tree",
        "formula_directory",
        "formula_files_retained",
        "proof_directory",
        "checker",
        "checker_repository",
        "checker_commit",
        "checker_source_validation",
        "certification_scope",
        "shared_proof",
        "case_count",
        "closed_set_sha256",
        "residual_set_sha256",
        "all_verified",
        "cases",
    }
    if set(index) != expected_index_keys:
        raise SystemExit("fourth-word proof-index schema is incorrect")
    if index["record_type"] != "fourth-word-rup-proof-index":
        raise SystemExit("unexpected fourth-word proof-index record type")
    if index["schema_version"] != 3:
        raise SystemExit("unsupported fourth-word proof-index schema")
    if index["sources"] != retained_sources:
        raise SystemExit("proof-index sources are incorrect")
    if index["classification"] != plan["classification"]:
        raise SystemExit("proof-index classification is incorrect")
    if index["proof_plan"] != {
        "path": display_path(paths["plan"], root),
        "sha256": hashes["plan"],
    }:
        raise SystemExit("proof-index plan is incorrect")
    pipeline_hashes, current_pipeline_tree = (
        validate_pipeline_provenance(
            index["pipeline_files"],
            index["pipeline_python_tree"],
            root=root,
        )
    )
    formula_directory = repository_path(FORMULA_DIRECTORY, root)
    if index["formula_directory"] != str(FORMULA_DIRECTORY):
        raise SystemExit("proof-index formula directory is incorrect")
    if index["formula_files_retained"] is not False:
        raise SystemExit("proof-index formula retention flag is incorrect")
    if index["proof_directory"] != str(PROOF_DIRECTORY):
        raise SystemExit("proof-index proof directory is incorrect")
    if index["checker"] != "drat-trim":
        raise SystemExit("proof-index checker changed")
    if index["checker_repository"] != DRAT_TRIM_REPOSITORY:
        raise SystemExit("proof-index checker repository changed")
    if index["checker_commit"] != DRAT_TRIM_COMMIT:
        raise SystemExit("proof-index checker commit changed")
    if index["checker_source_validation"] != (
        "tracked modes and raw bytes matched the pinned Git tree"
    ):
        raise SystemExit("proof-index checker source validation changed")
    if index["certification_scope"] != {
        "selected_third_word_children": 4,
        "fourth_word_branches": 350,
        "rup_unsat_branches": 184,
        "unresolved_fourth_word_branches": 166,
        "closed_third_word_children": 0,
        "closed_normalized_parents": 0,
    }:
        raise SystemExit("proof-index certification scope is incorrect")
    if index["all_verified"] is not True:
        raise SystemExit("proof index is not fully verified")
    if index["closed_set_sha256"] != closed_digest:
        raise SystemExit("proof-index closed-set digest is incorrect")
    if index["residual_set_sha256"] != residual_digest:
        raise SystemExit("proof-index residual-set digest is incorrect")

    retained_proof_directory = root / PROOF_DIRECTORY
    shared_proof = proof_directory / "empty-clause-rup.drat.gz"
    shared_summary_path = proof_directory / "empty-clause-rup.json"
    retained_shared_proof = (
        retained_proof_directory / "empty-clause-rup.drat.gz"
    )
    retained_shared_summary = (
        retained_proof_directory / "empty-clause-rup.json"
    )
    require_regular_single_link(shared_proof, "shared RUP proof")
    require_regular_single_link(
        shared_summary_path,
        "shared RUP proof summary",
    )
    if shared_proof.read_bytes() != PROOF_COMPRESSED:
        raise SystemExit("shared RUP proof bytes are incorrect")
    if gzip.decompress(shared_proof.read_bytes()) != PROOF_BYTES:
        raise SystemExit("shared RUP proof does not contain the empty clause")
    expected_shared_summary = {
        "record_type": "shared-empty-clause-rup-proof",
        "schema_version": 1,
        "proof": display_path(retained_shared_proof, root),
        "proof_format": "text DRAT",
        "proof_strategy": "empty-clause RUP",
        "proof_compression": "gzip",
        "proof_lines": 1,
        "proof_uncompressed_bytes": len(PROOF_BYTES),
        "proof_uncompressed_sha256": hashlib.sha256(
            PROOF_BYTES
        ).hexdigest(),
        "proof_compressed_bytes": len(PROOF_COMPRESSED),
        "proof_compressed_sha256": hashlib.sha256(
            PROOF_COMPRESSED
        ).hexdigest(),
    }
    if load_json(shared_summary_path) != expected_shared_summary:
        raise SystemExit("shared RUP proof summary is incorrect")
    expected_shared_index = {
        "path": display_path(retained_shared_proof, root),
        "sha256": file_sha256(shared_proof),
        "summary": display_path(retained_shared_summary, root),
        "summary_sha256": file_sha256(shared_summary_path),
    }
    if index["shared_proof"] != expected_shared_index:
        raise SystemExit("proof-index shared proof is incorrect")

    index_cases = index["cases"]
    if (
        int(index["case_count"]) != 184
        or len(index_cases) != 184
    ):
        raise SystemExit("fourth-word RUP proof count is incorrect")
    if len({case["branch_id"] for case in index_cases}) != 184:
        raise SystemExit("proof-index branch identifiers are not unique")

    parent_by_id = {
        str(parent["case_id"]): parent
        for parent in parent_manifest["cases"]
    }
    child_sources = {}
    for frontier_parent in child_frontier["parents"]:
        for child in frontier_parent["children"]:
            child_sources[str(child["child_id"])] = (
                frontier_parent,
                child,
            )

    expected_names = {
        "empty-clause-rup.drat.gz",
        "empty-clause-rup.json",
    }
    artifact_hashes = {
        shared_proof: file_sha256(shared_proof),
        shared_summary_path: file_sha256(shared_summary_path),
    }
    expected_metadata_keys = {
        "schema_version",
        "branch_id",
        "branch_sha256",
        "parent_child_id",
        "parent_case_id",
        "live_child_index",
        "minimum_distance",
        "child_formula",
        "fourth_orbit_index",
        "fourth_orbit_count",
        "fourth_candidate_word_count",
        "selected_fourth_word",
        "selected_fourth_word_literal",
        "earlier_fourth_word_count",
        "earlier_fourth_word_unit_sha256",
        "variables",
        "clauses",
        "base_formula",
        "formula",
        "formula_sha256",
        "parent_manifest",
        "parent_manifest_sha256",
        "third_word_manifest",
        "third_word_manifest_sha256",
        "child_frontier",
        "child_frontier_sha256",
        "fourth_frontier",
        "fourth_frontier_sha256",
    }
    expected_child_metadata_keys = {
        "schema_version",
        "child_id",
        "live_child_index",
        "parent_case_id",
        "parent_orbit_index",
        "minimum_distance",
        "base_formula_sha256",
        "base_variables",
        "base_clauses",
        "parent_unit_count",
        "parent_unit_sha256",
        "selected_word",
        "selected_word_literal",
        "earlier_word_count",
        "earlier_word_unit_sha256",
        "enforce_minimum_distance_matching",
        "variables",
        "clauses",
        "matching_allowed_vertices",
        "matching_gated_vertices",
        "matching_neighbor_incidences",
        "matching_auxiliary_variables",
        "matching_clauses",
    }
    for planned, record in zip(expected_cases, index_cases):
        branch_id = str(planned["branch_id"])
        slug = branch_slug(branch_id)
        formula = formula_directory / f"{slug}.cnf"
        metadata_path = proof_directory / f"{slug}-formula.json"
        summary_path = proof_directory / f"{slug}-proof.json"
        check_path = proof_directory / f"{slug}-check.json"
        retained_metadata_path = (
            retained_proof_directory / f"{slug}-formula.json"
        )
        retained_summary_path = (
            retained_proof_directory / f"{slug}-proof.json"
        )
        retained_check_path = (
            retained_proof_directory / f"{slug}-check.json"
        )
        expected_names.update(
            {
                metadata_path.name,
                summary_path.name,
                check_path.name,
            }
        )
        for path in (metadata_path, summary_path, check_path):
            require_regular_single_link(
                path,
                f"{branch_id}: proof artifact",
            )
            artifact_hashes[path] = file_sha256(path)
        if formula.exists() or formula.is_symlink():
            raise SystemExit(
                f"{branch_id}: transient formula was unexpectedly retained"
            )

        metadata = load_json(metadata_path)
        summary = load_json(summary_path)
        check = load_json(check_path)
        if set(metadata) != expected_metadata_keys:
            raise SystemExit(
                f"{branch_id}: formula metadata schema is incorrect"
            )
        if set(metadata["child_formula"]) != {
            "variables",
            "clauses",
            "sha256",
            "metadata",
        }:
            raise SystemExit(
                f"{branch_id}: child formula schema is incorrect"
            )
        if (
            set(metadata["child_formula"]["metadata"])
            != expected_child_metadata_keys
        ):
            raise SystemExit(
                f"{branch_id}: child metadata schema is incorrect"
            )
        if metadata["schema_version"] != 1:
            raise SystemExit(
                f"{branch_id}: formula metadata schema changed"
            )
        if metadata["branch_id"] != branch_id:
            raise SystemExit(
                f"{branch_id}: formula metadata identity changed"
            )
        if metadata["branch_sha256"] != planned["branch_sha256"]:
            raise SystemExit(f"{branch_id}: formula branch digest changed")
        if (
            metadata["parent_child_id"] != planned["parent_child_id"]
            or metadata["fourth_orbit_index"]
            != planned["fourth_orbit_index"]
        ):
            raise SystemExit(
                f"{branch_id}: formula metadata branch changed"
            )
        if metadata["formula"] != display_path(formula, root):
            raise SystemExit(f"{branch_id}: formula path is incorrect")
        formula_sha256 = require_sha256(
            metadata["formula_sha256"],
            f"{branch_id}: formula hash is invalid",
        )
        for label in (
            "parent_manifest",
            "third_word_manifest",
            "child_frontier",
            "fourth_frontier",
        ):
            if metadata[label] != retained_sources[label]["path"]:
                raise SystemExit(
                    f"{branch_id}: formula source path is incorrect"
                )
            if metadata[f"{label}_sha256"] != hashes[label]:
                raise SystemExit(
                    f"{branch_id}: formula source hash is incorrect"
                )
        frontier_parent, child = child_sources[
            str(planned["parent_child_id"])
        ]
        if child["branch_status"] != "live":
            raise SystemExit(f"{branch_id}: parent child is not live")
        case_id = str(frontier_parent["parent_case_id"])
        if metadata["parent_case_id"] != case_id:
            raise SystemExit(f"{branch_id}: parent case is incorrect")
        if case_id not in parent_by_id:
            raise SystemExit(f"{branch_id}: parent case is missing")
        base_record = frontier_parent["constraint_profile"][
            "minimum_distance"
        ]["formula"]
        if (
            metadata["base_formula"] != base_record["path"]
            or metadata["child_formula"]["metadata"][
                "base_formula_sha256"
            ]
            != base_record["sha256"]
        ):
            raise SystemExit(f"{branch_id}: base formula is incorrect")
        if int(metadata["variables"]) <= 0 or int(metadata["clauses"]) <= 0:
            raise SystemExit(f"{branch_id}: formula size is invalid")

        expected_summary = {
            "case_id": branch_id,
            "case_formula": display_path(formula, root),
            "case_formula_sha256": formula_sha256,
            "variables": metadata["variables"],
            "clauses": metadata["clauses"],
            "solver": "unit propagation",
            "status": "UNSAT",
            "proof_format": "text DRAT",
            "proof_strategy": "empty-clause RUP",
            "proof_compression": "gzip",
            "proof_lines": 1,
            "proof_uncompressed_bytes": len(PROOF_BYTES),
            "proof_uncompressed_sha256": hashlib.sha256(
                PROOF_BYTES
            ).hexdigest(),
            "proof_compressed": display_path(retained_shared_proof, root),
            "proof_compressed_bytes": len(PROOF_COMPRESSED),
            "proof_compressed_sha256": file_sha256(shared_proof),
            "proof_verification": "recorded in a separate check file",
        }
        if summary != expected_summary:
            raise SystemExit(f"{branch_id}: proof summary is incorrect")
        validate_check(
            check,
            branch_id=branch_id,
            formula_sha256=formula_sha256,
        )

        expected_record = {
            "branch_id": branch_id,
            "branch_sha256": planned["branch_sha256"],
            "parent_child_id": planned["parent_child_id"],
            "fourth_orbit_index": planned["fourth_orbit_index"],
            "formula": display_path(formula, root),
            "formula_sha256": formula_sha256,
            "formula_metadata": display_path(retained_metadata_path, root),
            "formula_metadata_sha256": file_sha256(metadata_path),
            "variables": metadata["variables"],
            "clauses": metadata["clauses"],
            "proof": display_path(retained_shared_proof, root),
            "proof_sha256": file_sha256(shared_proof),
            "proof_summary": display_path(retained_summary_path, root),
            "proof_summary_sha256": file_sha256(summary_path),
            "proof_check": display_path(retained_check_path, root),
            "proof_check_sha256": file_sha256(check_path),
            "verified": True,
        }
        if record != expected_record:
            raise SystemExit(f"{branch_id}: proof-index record is incorrect")

    attestation_path = repository_path(REPLAY_ATTESTATION, root)
    attestation_valid = False
    if not args.staged:
        if not (
            attestation_path.exists() or attestation_path.is_symlink()
        ):
            raise SystemExit(
                "fourth-word replay attestation is missing"
            )
        require_regular_single_link(
            attestation_path,
            "fourth-word replay attestation",
        )
        attestation = load_json(attestation_path)
        outcome_payload = "".join(
            (
                f"{record['branch_id']}:"
                f"{record['formula_sha256']}:"
                f"{record['proof_check_sha256']}\n"
            )
            for record in index_cases
        ).encode("ascii")
        validate_replay_attestation(
            attestation,
            expected_index={
                "path": display_path(paths["index"], root),
                "sha256": hashes["index"],
            },
            expected_pipeline_files=index["pipeline_files"],
            expected_pipeline_python_tree=index["pipeline_python_tree"],
            expected_python_sat_version=classification[
                "python_sat_version"
            ],
            expected_case_count=184,
            expected_case_outcomes_sha256=hashlib.sha256(
                outcome_payload
            ).hexdigest(),
            expected_closed_set_sha256=closed_digest,
            expected_residual_set_sha256=residual_digest,
        )
        artifact_hashes[attestation_path] = file_sha256(
            attestation_path
        )
        attestation_valid = True

    entries = list(proof_directory.iterdir())
    if any(
        not entry.is_file()
        or entry.is_symlink()
        or entry.stat().st_nlink != 1
        for entry in entries
    ):
        raise SystemExit("proof directory contains a non-regular artifact")
    if {entry.name for entry in entries} != expected_names:
        raise SystemExit("fourth-word proof artifact set is incorrect")
    for label, path in paths.items():
        if file_sha256(path) != hashes[label]:
            raise RuntimeError(
                f"{label} changed during fourth-word proof audit"
            )
    for path, digest in artifact_hashes.items():
        if file_sha256(path) != digest:
            raise RuntimeError(
                "a fourth-word proof artifact changed during audit"
            )
    for path, digest in pipeline_hashes.items():
        if file_sha256(path) != digest:
            raise RuntimeError(
                "a fourth-word proof pipeline file changed during audit"
            )
    if python_tree_record(root) != current_pipeline_tree:
        raise RuntimeError(
            "the repository Python source tree changed during audit"
        )
    print(
        json.dumps(
            {
                "case_count": len(index_cases),
                "not_rup_conflict_count": len(residual),
                "proofs_replayed": False,
                "proof_directory_sha256": directory_sha256(
                    proof_directory
                ),
                "proof_index_sha256": hashes["index"],
                "replay_attestation_valid": attestation_valid,
                "retained_check_records": len(index_cases),
                "structurally_valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
