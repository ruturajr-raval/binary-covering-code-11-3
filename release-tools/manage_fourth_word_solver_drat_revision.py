#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import copy
from datetime import date
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from manage_fourth_word_rup_revision import (  # noqa: E402
    atomic_write_bytes,
    canonical_json,
    executable_attestation,
    file_sha256,
    git_bytes,
    replay_git_command,
    require_clean_head,
    require_git_object_id,
    require_sha256,
    resolve_executable,
    resolve_revision,
    run_process,
    sanitized_environment,
    validate_toolchain_attestation,
    verify_repository_root,
)


SCHEMA_VERSION = 1
RECORD_TYPE = "fourth-word-solver-drat-certified-revision"
STATUS = "clean-checkout-replay-passed"
OUTPUT_COMMITMENT_SCOPE = "host-specific-self-attestation"
PYPI_INDEX = "https://pypi.org/simple"
CERTIFICATION_DATE = "2026-09-03"
REVISION_MANAGER_TEST_COUNT = 14

RECORD_PATH = Path(
    "proof-expansion/evidence/"
    "fourth-word-solver-drat-revision-v2.json"
)
PLAN_PATH = Path(
    "proof-expansion/evidence/"
    "fourth-word-solver-drat-plan-v2.json"
)
INDEX_PATH = Path(
    "proof-expansion/evidence/"
    "fourth-word-solver-drat-index-v2.json"
)
BUNDLE_MANIFEST_PATH = Path(
    "proof-expansion/evidence/"
    "fourth-word-solver-drat-bundle-v2.sha256"
)
PROOF_DIRECTORY = Path(
    "proof-expansion/evidence/proofs/"
    "fourth-word-solver-drat-v2"
)
MANAGER_PATH = Path(
    "release-tools/manage_fourth_word_solver_drat_revision.py"
)
RELEASE_MANIFEST_PATH = Path("release-manifest.sha256")
REPLAY_REQUIREMENTS = Path("requirements-replay.txt")
REPLAY_PARENT = Path(
    ".research-artifacts/solver-drat-clean-replays"
)

ROOT_RELEASE_FILES = (
    Path("README.md"),
    Path(".zenodo.json"),
    Path("CITATION.cff"),
    Path("PUBLICATION.md"),
    Path("LICENSE"),
    Path("release.json"),
    Path("requirements-proof.txt"),
    Path("requirements-replay.txt"),
    Path("requirements-sat.txt"),
    Path("evidence.json"),
    Path("evidence/fourth-word-up-classification.json"),
    Path("evidence/fourth-word-rup-proof-plan.json"),
    Path("evidence/fourth-word-rup-proof-index-v1.json"),
    Path("evidence/fourth-word-rup-replay-attestation-v1.json"),
    Path("evidence/fourth-word-rup-bundle-v1.sha256"),
    Path("evidence/fourth-word-rup-revision-v1.json"),
    Path("evidence/distance-distribution-bounds.json"),
    Path("evidence/overlap-bound.json"),
    Path("evidence/min-distance-proof-index.json"),
    Path("evidence/third-word-proof-index.json"),
    Path("evidence/case-reduction-summary.json"),
    Path("evidence/normalized-residual-two-word-cases.json"),
    Path("evidence/proof-bundle.sha256"),
)

FINALIZATION_ALLOWED_PATHS = (
    Path("evidence.json"),
    RECORD_PATH,
    Path("release-manifest.sha256"),
    Path("release.json"),
    Path("research/release-gate.json"),
)

FINALIZATION_REQUIRED_PATHS = (
    Path("evidence.json"),
    RECORD_PATH,
    Path("release-manifest.sha256"),
    Path("release.json"),
    Path("research/release-gate.json"),
)

REPLAY_COMMANDS = (
    "git clone --no-hardlinks --no-checkout <repository> <clean-replay>",
    "git checkout --detach <certified-revision>",
    "git rev-parse HEAD",
    "python -I -m venv .venv",
    (
        ".venv/bin/python -I -m pip install --isolated "
        "--disable-pip-version-check --no-input --no-cache-dir "
        "--require-hashes --only-binary=:all: --no-deps "
        "--index-url https://pypi.org/simple "
        "-r requirements-replay.txt"
    ),
    (
        ".venv/bin/python -m unittest discover "
        "-s release-tools/tests -v"
    ),
    "make -C proof-expansion test",
    "make prepare-fourth-word-proof-formulas PYTHON=.venv/bin/python",
    "make -C proof-expansion audit-plan",
    "make -C proof-expansion audit-bundle",
    (
        ".venv/bin/python tools/verify_checksum_manifest.py "
        "proof-expansion/evidence/"
        "fourth-word-solver-drat-bundle-v2.sha256 "
        "--path proof-expansion/evidence/"
        "fourth-word-solver-drat-plan-v2.json "
        "--path proof-expansion/evidence/"
        "fourth-word-solver-drat-index-v2.json "
        "--tree proof-expansion/evidence/proofs/"
        "fourth-word-solver-drat-v2"
    ),
    "make verify-release-manifest PYTHON=.venv/bin/python",
    "git diff --exit-code",
    "git status --porcelain --untracked-files=all",
)

EXPECTED_SUPPORTED_CLAIM = (
    "A 16-word binary length-11 code has covering radius 3, verified "
    "by two direct enumeration paths and a syndrome-space cross-check. "
    "For hypothetical 15-word covers, exact certificates prove minimum "
    "distance at most 5, total pair-ball overlap at least 1712, and "
    "total triple-ball overlap at least 280. A complete 150-branch "
    "normalized cover has 112 certified closures and 38 residual "
    "branches. Within four selected hard third-word children, checked "
    "RUP certificates close 184 of 350 exhaustive fourth-word branches "
    "and checked solver-generated DRAT certificates close 140 more. "
    "The combined certificates close 324 branches, leaving 26 branches "
    "and all four children open."
)

EXPECTED_LIMITATIONS = [
    "The exact value remains either 15 or 16.",
    "The retained 15-word near-cover leaves 28 words uncovered.",
    "Thirty-eight normalized residual branches remain unresolved.",
    (
        "The combined fourth-word proof bundles leave 26 branches "
        "unresolved and close no complete third-word child or "
        "normalized parent."
    ),
    (
        "Solver timeouts and unlogged statuses are not mathematical "
        "evidence of impossibility."
    ),
    (
        "Sharp witnesses for the retained overlap row system are not "
        "claimed to be realizable covers."
    ),
    (
        "Fresh replay requires network access to retrieve hash-locked "
        "Python wheels and the pinned checker source."
    ),
    (
        "Final certification verification requires a full Git clone "
        "containing the certified source revision; source archives and "
        "shallow checkouts cannot verify revision identity."
    ),
    (
        "Zenodo assigns a version-specific DOI only after a tagged "
        "release is archived; pre-release metadata uses the stable "
        "concept DOI."
    ),
    "No external mathematical review has occurred.",
]

EXPECTED_PER_CHILD = {
    "orbit-005": {
        "rup_certified": 50,
        "solver_drat_certified": 29,
        "unresolved": 6,
        "total": 85,
    },
    "orbit-007": {
        "rup_certified": 53,
        "solver_drat_certified": 15,
        "unresolved": 8,
        "total": 76,
    },
    "orbit-014": {
        "rup_certified": 41,
        "solver_drat_certified": 28,
        "unresolved": 4,
        "total": 73,
    },
    "orbit-015": {
        "rup_certified": 40,
        "solver_drat_certified": 68,
        "unresolved": 8,
        "total": 116,
    },
}

EXPECTED_GATE_VALUES = {
    "significant_original_result": False,
    "prior_art_refreshed": True,
    "complete_orbit_manifest": True,
    "independent_manifest_audit_passes": True,
    "fourth_word_rup_classification_audited": True,
    "fourth_word_rup_proofs_replay": True,
    "fourth_word_solver_drat_plan_audited": True,
    "fourth_word_solver_drat_proofs_replay": True,
    "fourth_word_solver_drat_bundle_manifest_valid": True,
    "fourth_word_solver_drat_revision_attested": True,
    "finalization_path_policy_passes": True,
    "all_selected_fourth_word_branches_closed": False,
    "closed_third_word_child_from_fourth_word_bundle": False,
    "closed_normalized_parent_from_fourth_word_bundle": False,
    "complete_child_formula_manifest": False,
    "independent_child_formula_audit_passes": True,
    "construction_verified_twice": True,
    "all_required_proofs_replay": True,
    "clean_checkout_replay_passes": True,
    "claim_scope_audited": True,
    "limitations_documented": True,
    "manuscript_ready": False,
    "external_review_addressed": False,
}


def repository_path(relative: Path, root: Path = ROOT) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"repository path is invalid: {relative}")
    path = root / relative
    lexical = Path(os.path.abspath(str(path)))
    try:
        lexical.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            f"repository path escapes the root: {relative}"
        ) from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(
                f"repository path contains a symlink: {relative}"
            )
    return lexical


def require_regular_single_link(path: Path, description: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"{description} is missing: {path}") from exc
    if (
        not path.is_file()
        or path.is_symlink()
        or metadata.st_nlink != 1
    ):
        raise RuntimeError(
            f"{description} is not a single-link regular file: {path}"
        )


def parse_iso_date(value: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError("completion date is not an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError("completion date is not an ISO date") from exc
    if parsed.isoformat() != value:
        raise RuntimeError("completion date is not canonical")
    return value


def require_supported_python_record(
    record: object,
) -> dict[str, object]:
    if (
        not isinstance(record, dict)
        or set(record) != {"implementation", "major", "minor"}
        or record.get("implementation") != "CPython"
        or record.get("major") != 3
        or type(record.get("minor")) is not int
        or not 9 <= record["minor"] <= 12
    ):
        raise RuntimeError(
            "clean replay requires CPython 3.9 through 3.12"
        )
    return record


def validate_python_interpreter(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise RuntimeError("clean-replay Python interpreter is invalid")
    environment = sanitized_environment(remove_repository_lock=True)
    result = subprocess.run(
        [
            str(resolved),
            "-I",
            "-c",
            (
                "import json, platform, sys; "
                "print(json.dumps({"
                "'implementation': platform.python_implementation(), "
                "'major': sys.version_info.major, "
                "'minor': sys.version_info.minor"
                "}, sort_keys=True))"
            ),
        ],
        check=False,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError("clean-replay Python probe failed")
    try:
        record = json.loads(result.stdout.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "clean-replay Python probe output is invalid"
        ) from exc
    require_supported_python_record(record)
    return resolved


def canonical_replay_root(root: Path, revision: str) -> Path:
    revision = require_git_object_id(revision, "replay revision")
    artifacts = repository_path(Path(".research-artifacts"), root)
    if artifacts.exists() or artifacts.is_symlink():
        if artifacts.is_symlink() or not artifacts.is_dir():
            raise RuntimeError(
                ".research-artifacts is not a regular directory"
            )
    else:
        artifacts.mkdir()
    parent = repository_path(REPLAY_PARENT, root)
    if parent.exists() or parent.is_symlink():
        if parent.is_symlink() or not parent.is_dir():
            raise RuntimeError(
                "clean-replay parent is not a regular directory"
            )
    else:
        parent.mkdir()
    parent = repository_path(REPLAY_PARENT, root)
    replay_root = parent / revision
    if replay_root.exists() or replay_root.is_symlink():
        raise RuntimeError(
            f"clean-replay directory already exists: {replay_root}"
        )
    return replay_root


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def unique_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    record: dict[str, object] = {}
    for key, value in pairs:
        if key in record:
            raise RuntimeError(f"JSON contains duplicate key: {key}")
        record[key] = value
    return record


def load_json_bytes(
    payload: bytes,
    description: str,
) -> object:
    try:
        return json.loads(
            payload.decode("ascii"),
            object_pairs_hook=unique_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{description} is invalid JSON") from exc


def normalize_manifest_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or str(path) != value
    ):
        raise RuntimeError(f"manifest path is not canonical: {value}")
    return value


def parse_checksum_manifest(payload: bytes) -> dict[str, str]:
    try:
        lines = payload.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise RuntimeError("checksum manifest is not ASCII") from exc
    if not lines:
        raise RuntimeError("checksum manifest is empty")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        if (
            len(line) < 67
            or line[64:66] != "  "
            or any(
                character not in "0123456789abcdef"
                for character in line[:64]
            )
        ):
            raise RuntimeError(
                f"checksum manifest line {line_number} is malformed"
            )
        relative = normalize_manifest_path(line[66:])
        if relative in entries:
            raise RuntimeError(
                f"checksum manifest repeats path: {relative}"
            )
        entries[relative] = line[:64]
    return entries


def directory_sha256(directory: Path) -> str:
    if not directory.is_dir() or directory.is_symlink():
        raise RuntimeError(f"proof directory is invalid: {directory}")
    payload = bytearray()
    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    for entry in entries:
        require_regular_single_link(entry, "proof artifact")
        payload.extend(entry.name.encode("ascii"))
        payload.extend(b":")
        payload.extend(file_sha256(entry).encode("ascii"))
        payload.extend(b"\n")
    return sha256_bytes(bytes(payload))


def expected_v2_paths(root: Path) -> set[str]:
    proof_directory = repository_path(PROOF_DIRECTORY, root)
    if not proof_directory.is_dir() or proof_directory.is_symlink():
        raise RuntimeError("v2 proof directory is invalid")
    proof_paths = set()
    for entry in proof_directory.iterdir():
        require_regular_single_link(entry, "v2 proof artifact")
        proof_paths.add(entry.relative_to(root).as_posix())
    return {
        PLAN_PATH.as_posix(),
        INDEX_PATH.as_posix(),
        *proof_paths,
    }


def validate_v2_bundle(root: Path) -> dict[str, object]:
    manifest_path = repository_path(BUNDLE_MANIFEST_PATH, root)
    require_regular_single_link(manifest_path, "v2 bundle manifest")
    entries = parse_checksum_manifest(manifest_path.read_bytes())
    expected = expected_v2_paths(root)
    if set(entries) != expected:
        raise RuntimeError("v2 bundle manifest membership differs")
    for relative, digest in entries.items():
        path = repository_path(Path(relative), root)
        require_regular_single_link(path, "v2 manifest artifact")
        if file_sha256(path) != digest:
            raise RuntimeError(
                f"v2 bundle manifest hash differs: {relative}"
            )
    if len(entries) != 422:
        raise RuntimeError("v2 bundle manifest must contain 422 entries")
    proof_directory = repository_path(PROOF_DIRECTORY, root)
    proof_count = len(list(proof_directory.iterdir()))
    if proof_count != 420:
        raise RuntimeError("v2 proof directory must contain 420 files")
    return {
        "artifact_count": len(entries),
        "manifest_sha256": file_sha256(manifest_path),
        "proof_artifact_count": proof_count,
        "proof_directory_sha256": directory_sha256(proof_directory),
    }


def validate_root_release_manifest(root: Path) -> str:
    manifest_path = repository_path(RELEASE_MANIFEST_PATH, root)
    require_regular_single_link(manifest_path, "root release manifest")
    entries = parse_checksum_manifest(manifest_path.read_bytes())
    expected = {path.as_posix() for path in ROOT_RELEASE_FILES}
    if set(entries) != expected:
        raise RuntimeError("root release manifest membership differs")
    for relative, digest in entries.items():
        path = repository_path(Path(relative), root)
        require_regular_single_link(path, "root release artifact")
        if file_sha256(path) != digest:
            raise RuntimeError(
                f"root release manifest hash differs: {relative}"
            )
    return file_sha256(manifest_path)


def artifact_reference(relative: Path, root: Path) -> dict[str, str]:
    path = repository_path(relative, root)
    require_regular_single_link(path, str(relative))
    return {
        "path": relative.as_posix(),
        "sha256": file_sha256(path),
    }


def git_file(root: Path, revision: str, relative: Path) -> bytes:
    return git_bytes(
        root,
        ["show", f"{revision}:{relative.as_posix()}"],
    )


def revision_reference(
    root: Path,
    revision: str,
    relative: Path,
) -> dict[str, str]:
    return {
        "path": relative.as_posix(),
        "sha256": sha256_bytes(git_file(root, revision, relative)),
    }


def revision_tree_files(
    root: Path,
    revision: str,
    directory: Path,
) -> dict[str, bytes]:
    output = git_bytes(
        root,
        [
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            revision,
            "--",
            directory.as_posix(),
        ],
    )
    records: dict[str, bytes] = {}
    for raw_entry in output.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split()
        relative = raw_path.decode("utf-8")
        if mode != "100644" or object_type != "blob":
            raise RuntimeError(
                f"revision proof artifact has invalid mode: {relative}"
            )
        path = PurePosixPath(relative)
        if path.parent.as_posix() != directory.as_posix():
            raise RuntimeError(
                f"revision proof tree is not flat: {relative}"
            )
        payload = git_bytes(root, ["cat-file", "blob", object_id])
        records[path.name] = payload
    return records


def revision_directory_sha256(
    root: Path,
    revision: str,
    directory: Path,
) -> tuple[int, str]:
    records = revision_tree_files(root, revision, directory)
    payload = bytearray()
    for name in sorted(records):
        payload.extend(name.encode("ascii"))
        payload.extend(b":")
        payload.extend(sha256_bytes(records[name]).encode("ascii"))
        payload.extend(b"\n")
    return len(records), sha256_bytes(bytes(payload))


def validate_revision_v2_bundle(root: Path, revision: str) -> None:
    entries = parse_checksum_manifest(
        git_file(root, revision, BUNDLE_MANIFEST_PATH)
    )
    proof_records = revision_tree_files(
        root,
        revision,
        PROOF_DIRECTORY,
    )
    expected = {
        PLAN_PATH.as_posix(),
        INDEX_PATH.as_posix(),
        *(
            (PROOF_DIRECTORY / name).as_posix()
            for name in proof_records
        ),
    }
    if set(entries) != expected or len(entries) != 422:
        raise RuntimeError(
            "certified revision v2 manifest membership differs"
        )
    for relative, digest in entries.items():
        if relative == PLAN_PATH.as_posix():
            payload = git_file(root, revision, PLAN_PATH)
        elif relative == INDEX_PATH.as_posix():
            payload = git_file(root, revision, INDEX_PATH)
        else:
            name = PurePosixPath(relative).name
            payload = proof_records[name]
        if sha256_bytes(payload) != digest:
            raise RuntimeError(
                f"certified revision v2 hash differs: {relative}"
            )


def validate_revision_root_manifest(root: Path, revision: str) -> None:
    entries = parse_checksum_manifest(
        git_file(root, revision, RELEASE_MANIFEST_PATH)
    )
    expected = {path.as_posix() for path in ROOT_RELEASE_FILES}
    if set(entries) != expected:
        raise RuntimeError(
            "certified revision root manifest membership differs"
        )
    for relative, digest in entries.items():
        if sha256_bytes(
            git_file(root, revision, Path(relative))
        ) != digest:
            raise RuntimeError(
                f"certified revision root hash differs: {relative}"
            )


def command_result(
    command: str,
    output: bytes,
) -> dict[str, object]:
    return {
        "command": command,
        "return_code": 0,
        "output_bytes": len(output),
        "output_sha256": sha256_bytes(output),
        "output_base64": base64.b64encode(output).decode("ascii"),
    }


def decode_command_output(result: dict[str, object]) -> bytes:
    encoded = result.get("output_base64")
    if not isinstance(encoded, str):
        raise RuntimeError("clean-replay output encoding is invalid")
    try:
        output = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "clean-replay output encoding is invalid"
        ) from exc
    if (
        len(output) != result.get("output_bytes")
        or sha256_bytes(output) != result.get("output_sha256")
    ):
        raise RuntimeError("clean-replay retained output differs")
    return output


def top_level_json_objects(
    output: bytes,
) -> list[dict[str, object]]:
    text = output.decode("utf-8", errors="strict")
    decoder = json.JSONDecoder(object_pairs_hook=unique_json_object)
    records: list[dict[str, object]] = []
    cursor = 0
    while cursor < len(text):
        index = text.find("{", cursor)
        if index < 0:
            break
        try:
            value, consumed = decoder.raw_decode(text[index:])
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "clean-replay output contains malformed top-level JSON"
            ) from exc
        if isinstance(value, dict):
            records.append(value)
        cursor = index + consumed
    return records


def require_json_result(
    output: bytes,
    expected: dict[str, object],
) -> None:
    records = top_level_json_objects(output)
    if not records or records[-1] != expected:
        raise RuntimeError(
            f"clean-replay final JSON result differs: {expected}"
        )


def validate_command_output_semantics(
    index: int,
    output: bytes,
    revision: str,
) -> None:
    if index == 2:
        if output != (revision + "\n").encode("ascii"):
            raise RuntimeError(
                "clean-replay revision output is invalid"
            )
    elif index == 5:
        text = output.decode("utf-8", errors="strict")
        required_tests = (
            "test_canonical_replay_root_rejects_symlink_parent",
            "test_finalization_git_parent_paths_and_modes",
            "test_retained_bundle_and_root_manifests_validate",
            "test_retained_output_tampering_is_rejected",
            "test_supported_python_record_is_strict",
        )
        if any(name not in text for name in required_tests) or (
            f"Ran {REVISION_MANAGER_TEST_COUNT} tests in " not in text
            or "\nOK\n" not in text
        ):
            raise RuntimeError(
                "revision-manager test output is invalid"
            )
    elif index == 6:
        text = output.decode("utf-8", errors="strict")
        if "Ran 80 tests in " not in text or "\nOK\n" not in text:
            raise RuntimeError(
                "proof-expansion test output is invalid"
            )
    elif index == 8:
        require_json_result(
            output,
            {
                "case_count": 140,
                "remaining_count": 26,
                "selected_set_sha256": (
                    "314c573765bc28fd8556db41fec2aa4f"
                    "7e6e7b5b1266c7a0906c1b23dcaec034"
                ),
                "valid": True,
            },
        )
    elif index == 9:
        require_json_result(
            output,
            {
                "case_count": 140,
                "proof_directory_sha256": (
                    "44504c6320ac22ad62507f70222c2e8b"
                    "9e6a51977f27ca3c936019c9f657f08f"
                ),
                "proof_index_sha256": (
                    "342c94b10eb182b18c369a526e3fc9d5"
                    "ac2b9fc9faa8943b687ea1a357ce3ca8"
                ),
                "proofs_replayed": True,
                "valid": True,
            },
        )
    elif index == 10:
        require_json_result(
            output,
            {
                "artifact_count": 422,
                "manifest": BUNDLE_MANIFEST_PATH.as_posix(),
                "valid": True,
            },
        )
    elif index == 11:
        require_json_result(
            output,
            {
                "artifact_count": 23,
                "manifest": RELEASE_MANIFEST_PATH.as_posix(),
                "valid": True,
            },
        )
    elif index in {12, 13} and output:
        raise RuntimeError(
            "clean-replay final repository output is not empty"
        )


def validate_command_results(
    value: object,
    revision: str,
) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) != len(REPLAY_COMMANDS):
        raise RuntimeError("clean-replay command results are invalid")
    validated = []
    for expected, result in zip(REPLAY_COMMANDS, value):
        if (
            not isinstance(result, dict)
            or set(result)
            != {
                "command",
                "return_code",
                "output_bytes",
                "output_sha256",
                "output_base64",
            }
            or result["command"] != expected
            or type(result["return_code"]) is not int
            or result["return_code"] != 0
            or type(result["output_bytes"]) is not int
            or result["output_bytes"] < 0
        ):
            raise RuntimeError("clean-replay command result is invalid")
        validated.append(
            {
                "command": expected,
                "return_code": 0,
                "output_bytes": result["output_bytes"],
                "output_sha256": require_sha256(
                    result["output_sha256"],
                    "clean-replay command output hash",
                ),
                "output_base64": result["output_base64"],
            }
        )
    for index, result in enumerate(validated):
        output = decode_command_output(result)
        validate_command_output_semantics(index, output, revision)
    return validated


def command_results_digest(results: object, revision: str) -> str:
    validated = validate_command_results(results, revision)
    return sha256_bytes(canonical_json(validated))


def reference_schema(
    value: object,
    expected_path: Path,
    description: str,
) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"path", "sha256"}
        or value.get("path") != expected_path.as_posix()
    ):
        raise RuntimeError(f"{description} reference is invalid")
    return {
        "path": expected_path.as_posix(),
        "sha256": require_sha256(
            value.get("sha256"),
            f"{description} hash",
        ),
    }


def validate_record_schema(record: object) -> dict[str, object]:
    if not isinstance(record, dict) or set(record) != {
        "schema_version",
        "record_type",
        "status",
        "certified_revision",
        "certified_tree",
        "certified_release_manifest",
        "revision_manager",
        "solver_drat_plan",
        "solver_drat_index",
        "solver_drat_bundle_manifest",
        "proof_directory",
        "result",
        "clean_checkout_replay",
        "finalization_policy",
    }:
        raise RuntimeError("v2 revision record schema is invalid")
    if (
        record["schema_version"] != SCHEMA_VERSION
        or record["record_type"] != RECORD_TYPE
        or record["status"] != STATUS
    ):
        raise RuntimeError("v2 revision record identity is invalid")
    revision = require_git_object_id(
        record["certified_revision"],
        "certified revision",
    )
    require_git_object_id(record["certified_tree"], "certified tree")
    reference_schema(
        record["certified_release_manifest"],
        RELEASE_MANIFEST_PATH,
        "certified release manifest",
    )
    reference_schema(
        record["revision_manager"],
        MANAGER_PATH,
        "revision manager",
    )
    reference_schema(
        record["solver_drat_plan"],
        PLAN_PATH,
        "solver DRAT plan",
    )
    reference_schema(
        record["solver_drat_index"],
        INDEX_PATH,
        "solver DRAT index",
    )
    reference_schema(
        record["solver_drat_bundle_manifest"],
        BUNDLE_MANIFEST_PATH,
        "solver DRAT bundle manifest",
    )
    proof_directory = record["proof_directory"]
    if (
        not isinstance(proof_directory, dict)
        or set(proof_directory)
        != {"path", "artifact_count", "sha256"}
        or proof_directory["path"] != PROOF_DIRECTORY.as_posix()
        or proof_directory["artifact_count"] != 420
    ):
        raise RuntimeError("v2 proof-directory record is invalid")
    require_sha256(
        proof_directory["sha256"],
        "v2 proof-directory hash",
    )
    if record["result"] != {
        "frontier_branch_count": 350,
        "prior_rup_certified_branch_count": 184,
        "newly_certified_branch_count": 140,
        "combined_certified_branch_count": 324,
        "remaining_branch_count": 26,
        "fully_closed_selected_child_count": 0,
        "fully_closed_normalized_parent_count": 0,
        "covering_number_status": "15 or 16",
    }:
        raise RuntimeError("v2 revision result scope is invalid")
    replay = record["clean_checkout_replay"]
    if (
        not isinstance(replay, dict)
        or set(replay)
        != {
            "completed_on",
            "passed",
            "revision",
            "commands",
            "command_results",
            "command_results_sha256",
            "output_commitment_scope",
            "toolchain",
            "working_tree_clean",
            "proofs_replayed",
        }
        or replay["passed"] is not True
        or replay["revision"] != revision
        or replay["commands"] != list(REPLAY_COMMANDS)
        or replay["output_commitment_scope"]
        != OUTPUT_COMMITMENT_SCOPE
        or replay["working_tree_clean"] is not True
        or replay["proofs_replayed"] is not True
    ):
        raise RuntimeError("v2 clean-replay record is invalid")
    if (
        parse_iso_date(replay["completed_on"])
        != CERTIFICATION_DATE
    ):
        raise RuntimeError(
            "v2 clean-replay completion date differs"
        )
    results = validate_command_results(
        replay["command_results"],
        revision,
    )
    if replay["command_results_sha256"] != command_results_digest(
        results,
        revision,
    ):
        raise RuntimeError(
            "v2 clean-replay command-results hash differs"
        )
    validate_toolchain_attestation(replay["toolchain"])
    policy = record["finalization_policy"]
    if (
        not isinstance(policy, dict)
        or set(policy)
        != {
            "required_parent",
            "allowed_changed_paths",
            "required_changed_paths",
            "release_revision_rule",
        }
        or policy["required_parent"] != revision
        or policy["allowed_changed_paths"]
        != [path.as_posix() for path in FINALIZATION_ALLOWED_PATHS]
        or policy["required_changed_paths"]
        != [path.as_posix() for path in FINALIZATION_REQUIRED_PATHS]
        or policy["release_revision_rule"]
        != "current HEAD must be a clean single-parent child of the certified revision"
    ):
        raise RuntimeError("v2 finalization policy is invalid")
    return record


def load_record(path: Path) -> dict[str, object]:
    require_regular_single_link(path, "v2 revision record")
    value = load_json_bytes(
        path.read_bytes(),
        "v2 revision record",
    )
    return validate_record_schema(value)


def validate_source_record(
    record: dict[str, object],
    root: Path,
) -> None:
    validate_record_schema(record)
    revision = str(record["certified_revision"])
    commit, tree = resolve_revision(root, revision)
    if commit != revision or tree != record["certified_tree"]:
        raise RuntimeError("certified revision identity differs")
    expected_references = {
        "certified_release_manifest": revision_reference(
            root,
            revision,
            RELEASE_MANIFEST_PATH,
        ),
        "revision_manager": revision_reference(
            root,
            revision,
            MANAGER_PATH,
        ),
        "solver_drat_plan": revision_reference(
            root,
            revision,
            PLAN_PATH,
        ),
        "solver_drat_index": revision_reference(
            root,
            revision,
            INDEX_PATH,
        ),
        "solver_drat_bundle_manifest": revision_reference(
            root,
            revision,
            BUNDLE_MANIFEST_PATH,
        ),
    }
    for label, expected in expected_references.items():
        if record[label] != expected:
            raise RuntimeError(
                f"certified revision {label} differs"
            )
    proof_count, proof_digest = revision_directory_sha256(
        root,
        revision,
        PROOF_DIRECTORY,
    )
    if record["proof_directory"] != {
        "path": PROOF_DIRECTORY.as_posix(),
        "artifact_count": proof_count,
        "sha256": proof_digest,
    }:
        raise RuntimeError(
            "certified revision proof directory differs"
        )
    validate_revision_v2_bundle(root, revision)
    validate_revision_root_manifest(root, revision)


def write_log(log_directory: Path, index: int, output: bytes) -> None:
    path = log_directory / f"{index:02d}.log"
    path.write_bytes(output)


def normalize_output(
    output: bytes,
    replacements: list[tuple[bytes, bytes]],
) -> bytes:
    normalized = output
    for original, replacement in sorted(
        replacements,
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if original:
            normalized = normalized.replace(original, replacement)
    return normalized


def replay_process(
    arguments: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    description: str,
    log_directory: Path,
    result_index: int,
    replacements: list[tuple[bytes, bytes]],
    print_output: bool = True,
) -> dict[str, object]:
    print(f"[{result_index + 1}/{len(REPLAY_COMMANDS)}] {description}")
    output = run_process(
        arguments,
        cwd=cwd,
        environment=environment,
        description=description,
        print_output=print_output,
    )
    normalized = normalize_output(output, replacements)
    write_log(log_directory, result_index, normalized)
    print(f"[{result_index + 1}/{len(REPLAY_COMMANDS)}] passed")
    return command_result(description, normalized)


def run_clean_checkout(
    *,
    root: Path,
    revision: str,
    python_executable: Path,
    replay_root: Path,
) -> tuple[Path, list[dict[str, object]], dict[str, object]]:
    expected_parent = repository_path(REPLAY_PARENT, root)
    if replay_root.parent != expected_parent:
        raise RuntimeError("clean-replay directory is not canonical")
    if replay_root.exists() or replay_root.is_symlink():
        raise RuntimeError(
            f"clean-replay directory already exists: {replay_root}"
        )
    replay_root.mkdir(parents=True)
    checkout = replay_root / "checkout"
    logs = replay_root / "logs"
    runtime = replay_root / "runtime"
    logs.mkdir()
    runtime.mkdir()
    hooks = runtime / "hooks"
    template = runtime / "template"
    home = runtime / "home"
    cache = runtime / "cache"
    config = runtime / "config"
    temporary = runtime / "tmp"
    for directory in (
        hooks,
        template,
        home,
        cache,
        config,
        temporary,
    ):
        directory.mkdir()

    environment = sanitized_environment(remove_repository_lock=True)
    git_executable = resolve_executable(
        "git",
        environment=environment,
    )
    make_executable = resolve_executable(
        "make",
        environment=environment,
    )
    python_executable = validate_python_interpreter(python_executable)
    toolchain = executable_attestation(
        git_executable=Path(git_executable),
        make_executable=Path(make_executable),
        python_executable=python_executable,
    )
    environment.update(
        {
            "HOME": str(home),
            "TMPDIR": str(temporary),
            "XDG_CACHE_HOME": str(cache),
            "XDG_CONFIG_HOME": str(config),
        }
    )
    replacements = [
        (
            str(checkout).encode("utf-8"),
            b"<clean-replay>",
        ),
        (
            str(replay_root).encode("utf-8"),
            b"<replay-root>",
        ),
        (
            str(root).encode("utf-8"),
            b"<repository>",
        ),
        (
            str(python_executable).encode("utf-8"),
            b"<python>",
        ),
        (
            str(runtime).encode("utf-8"),
            b"<runtime>",
        ),
    ]

    results: list[dict[str, object]] = []
    clone_command = replay_git_command(
        git_executable,
        hooks,
        [
            "clone",
            "--no-hardlinks",
            "--no-checkout",
            "--quiet",
            f"--template={template}",
            str(root),
            str(checkout),
        ],
    )
    results.append(
        replay_process(
            clone_command,
            cwd=root,
            environment=environment,
            description=REPLAY_COMMANDS[0],
            log_directory=logs,
            result_index=0,
            replacements=replacements,
        )
    )
    checkout_command = replay_git_command(
        git_executable,
        hooks,
        [
            "-C",
            str(checkout),
            "checkout",
            "--detach",
            "--quiet",
            revision,
        ],
    )
    results.append(
        replay_process(
            checkout_command,
            cwd=root,
            environment=environment,
            description=REPLAY_COMMANDS[1],
            log_directory=logs,
            result_index=1,
            replacements=replacements,
        )
    )
    revision_output = run_process(
        replay_git_command(
            git_executable,
            hooks,
            [
                "-C",
                str(checkout),
                "rev-parse",
                "HEAD",
            ],
        ),
        cwd=root,
        environment=environment,
        description=REPLAY_COMMANDS[2],
        print_output=False,
    )
    revision_output = normalize_output(revision_output, replacements)
    write_log(logs, 2, revision_output)
    if revision_output != (revision + "\n").encode("ascii"):
        raise RuntimeError("clean checkout has the wrong revision")
    results.append(command_result(REPLAY_COMMANDS[2], revision_output))
    print(f"[3/{len(REPLAY_COMMANDS)}] {REPLAY_COMMANDS[2]} passed")

    replay_python = checkout / ".venv/bin/python"
    commands = (
        (
            [
                str(python_executable),
                "-I",
                "-m",
                "venv",
                ".venv",
            ],
            REPLAY_COMMANDS[3],
        ),
        (
            [
                str(replay_python),
                "-I",
                "-m",
                "pip",
                "install",
                "--isolated",
                "--disable-pip-version-check",
                "--no-input",
                "--no-cache-dir",
                "--require-hashes",
                "--only-binary=:all:",
                "--no-deps",
                "--index-url",
                PYPI_INDEX,
                "-r",
                REPLAY_REQUIREMENTS.as_posix(),
            ],
            REPLAY_COMMANDS[4],
        ),
        (
            [
                str(replay_python),
                "-m",
                "unittest",
                "discover",
                "-s",
                "release-tools/tests",
                "-v",
            ],
            REPLAY_COMMANDS[5],
        ),
        (
            [make_executable, "-C", "proof-expansion", "test"],
            REPLAY_COMMANDS[6],
        ),
        (
            [
                make_executable,
                "prepare-fourth-word-proof-formulas",
                "PYTHON=.venv/bin/python",
            ],
            REPLAY_COMMANDS[7],
        ),
        (
            [make_executable, "-C", "proof-expansion", "audit-plan"],
            REPLAY_COMMANDS[8],
        ),
        (
            [make_executable, "-C", "proof-expansion", "audit-bundle"],
            REPLAY_COMMANDS[9],
        ),
        (
            [
                str(replay_python),
                "tools/verify_checksum_manifest.py",
                BUNDLE_MANIFEST_PATH.as_posix(),
                "--path",
                PLAN_PATH.as_posix(),
                "--path",
                INDEX_PATH.as_posix(),
                "--tree",
                PROOF_DIRECTORY.as_posix(),
            ],
            REPLAY_COMMANDS[10],
        ),
        (
            [
                make_executable,
                "verify-release-manifest",
                "PYTHON=.venv/bin/python",
            ],
            REPLAY_COMMANDS[11],
        ),
        (
            replay_git_command(
                git_executable,
                hooks,
                [
                    "diff",
                    "--no-ext-diff",
                    "--exit-code",
                ],
            ),
            REPLAY_COMMANDS[12],
        ),
    )
    for result_index, (arguments, description) in enumerate(
        commands,
        start=3,
    ):
        results.append(
            replay_process(
                arguments,
                cwd=checkout,
                environment=environment,
                description=description,
                log_directory=logs,
                result_index=result_index,
                replacements=replacements,
            )
        )

    status_index = len(REPLAY_COMMANDS) - 1
    status = run_process(
        replay_git_command(
            git_executable,
            hooks,
            [
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
        ),
        cwd=checkout,
        environment=environment,
        description=REPLAY_COMMANDS[status_index],
        print_output=False,
    )
    status = normalize_output(status, replacements)
    write_log(logs, status_index, status)
    if status:
        raise RuntimeError(
            "clean-replay worktree is not clean after verification"
        )
    results.append(
        command_result(REPLAY_COMMANDS[status_index], status)
    )
    print(
        f"[{len(REPLAY_COMMANDS)}/{len(REPLAY_COMMANDS)}] "
        f"{REPLAY_COMMANDS[status_index]} passed"
    )

    if executable_attestation(
        git_executable=Path(git_executable),
        make_executable=Path(make_executable),
        python_executable=python_executable,
    ) != toolchain:
        raise RuntimeError("clean-replay toolchain changed")
    validate_command_results(results, revision)
    return checkout, results, toolchain


def build_record(
    *,
    checkout: Path,
    revision: str,
    tree: str,
    completed_on: str,
    results: list[dict[str, object]],
    toolchain: dict[str, object],
) -> dict[str, object]:
    v2 = validate_v2_bundle(checkout)
    validate_root_release_manifest(checkout)
    record: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_TYPE,
        "status": STATUS,
        "certified_revision": revision,
        "certified_tree": tree,
        "certified_release_manifest": artifact_reference(
            RELEASE_MANIFEST_PATH,
            checkout,
        ),
        "revision_manager": artifact_reference(
            MANAGER_PATH,
            checkout,
        ),
        "solver_drat_plan": artifact_reference(
            PLAN_PATH,
            checkout,
        ),
        "solver_drat_index": artifact_reference(
            INDEX_PATH,
            checkout,
        ),
        "solver_drat_bundle_manifest": artifact_reference(
            BUNDLE_MANIFEST_PATH,
            checkout,
        ),
        "proof_directory": {
            "path": PROOF_DIRECTORY.as_posix(),
            "artifact_count": v2["proof_artifact_count"],
            "sha256": v2["proof_directory_sha256"],
        },
        "result": {
            "frontier_branch_count": 350,
            "prior_rup_certified_branch_count": 184,
            "newly_certified_branch_count": 140,
            "combined_certified_branch_count": 324,
            "remaining_branch_count": 26,
            "fully_closed_selected_child_count": 0,
            "fully_closed_normalized_parent_count": 0,
            "covering_number_status": "15 or 16",
        },
        "clean_checkout_replay": {
            "completed_on": completed_on,
            "passed": True,
            "revision": revision,
            "commands": list(REPLAY_COMMANDS),
            "command_results": results,
            "command_results_sha256": command_results_digest(
                results,
                revision,
            ),
            "output_commitment_scope": OUTPUT_COMMITMENT_SCOPE,
            "toolchain": toolchain,
            "working_tree_clean": True,
            "proofs_replayed": True,
        },
        "finalization_policy": {
            "required_parent": revision,
            "allowed_changed_paths": [
                path.as_posix()
                for path in FINALIZATION_ALLOWED_PATHS
            ],
            "required_changed_paths": [
                path.as_posix()
                for path in FINALIZATION_REQUIRED_PATHS
            ],
            "release_revision_rule": (
                "current HEAD must be a clean single-parent child "
                "of the certified revision"
            ),
        },
    }
    return validate_record_schema(record)


def finalization_changed_paths(
    root: Path,
    source_revision: str,
    release_revision: str,
) -> set[str]:
    raw = git_bytes(
        root,
        [
            "diff",
            "--name-status",
            "--no-renames",
            source_revision,
            release_revision,
        ],
    ).decode("utf-8")
    changed: set[str] = set()
    for line in raw.splitlines():
        status, relative = line.split("\t", 1)
        if status not in {"A", "M"}:
            raise RuntimeError(
                f"finalization contains disallowed status {status}: "
                f"{relative}"
            )
        changed.add(normalize_manifest_path(relative))
    return changed


def require_regular_git_blob(
    root: Path,
    revision: str,
    relative: str,
) -> None:
    output = git_bytes(
        root,
        [
            "ls-tree",
            "-z",
            "--full-tree",
            revision,
            "--",
            relative,
        ],
    )
    entries = [entry for entry in output.split(b"\0") if entry]
    if len(entries) != 1:
        raise RuntimeError(
            f"finalization path is not a unique Git entry: {relative}"
        )
    metadata, raw_path = entries[0].split(b"\t", 1)
    mode, object_type, _ = metadata.decode("ascii").split()
    if (
        raw_path.decode("utf-8") != relative
        or mode != "100644"
        or object_type != "blob"
    ):
        raise RuntimeError(
            f"finalization path is not a regular Git file: {relative}"
        )


def validate_finalization_paths(changed: set[str]) -> None:
    allowed = {
        path.as_posix() for path in FINALIZATION_ALLOWED_PATHS
    }
    required = {
        path.as_posix() for path in FINALIZATION_REQUIRED_PATHS
    }
    extra = sorted(changed - allowed)
    missing = sorted(required - changed)
    if extra or missing:
        raise RuntimeError(
            "finalization path policy failed; "
            f"extra={extra}, missing={missing}"
        )


def require_single_parent_release(
    root: Path,
    source_revision: str,
    release_revision: str,
) -> None:
    parents = git_bytes(
        root,
        ["rev-list", "--parents", "-n", "1", release_revision],
    ).decode("ascii").strip().split()
    if parents != [release_revision, source_revision]:
        raise RuntimeError(
            "release revision is not a single-parent child "
            "of the certified revision"
        )


def load_repository_json(
    root: Path,
    relative: Path,
    description: str,
) -> dict[str, object]:
    path = repository_path(relative, root)
    require_regular_single_link(path, description)
    value = load_json_bytes(path.read_bytes(), description)
    if not isinstance(value, dict):
        raise RuntimeError(f"{description} is not an object")
    return value


def load_revision_json(
    root: Path,
    revision: str,
    relative: Path,
    description: str,
) -> dict[str, object]:
    value = load_json_bytes(
        git_file(root, revision, relative),
        description,
    )
    if not isinstance(value, dict):
        raise RuntimeError(f"{description} is not an object")
    return value


def verify_metadata_bindings(
    root: Path,
    record: dict[str, object],
) -> None:
    source_revision = str(record["certified_revision"])
    record_reference = artifact_reference(RECORD_PATH, root)
    manager_reference = artifact_reference(MANAGER_PATH, root)
    plan_reference = artifact_reference(PLAN_PATH, root)
    index_reference = artifact_reference(INDEX_PATH, root)
    manifest_reference = artifact_reference(
        BUNDLE_MANIFEST_PATH,
        root,
    )
    release = load_repository_json(
        root,
        Path("release.json"),
        "release metadata",
    )
    source_release = load_revision_json(
        root,
        source_revision,
        Path("release.json"),
        "certified release metadata",
    )
    expected_verification = {
        "status": "clean_checkout_replay_passed",
        "solver_drat_plan": plan_reference,
        "solver_drat_index": index_reference,
        "solver_drat_bundle_manifest": {
            **manifest_reference,
            "artifact_count": 422,
        },
        "solver_drat_proof_directory": {
            "path": PROOF_DIRECTORY.as_posix(),
            "artifact_count": 420,
            "digest": (
                "44504c6320ac22ad62507f70222c2e8b"
                "9e6a51977f27ca3c936019c9f657f08f"
            ),
        },
        "revision_manager": manager_reference,
        "certified_revision_record": record_reference,
        "certified_source_revision": record["certified_revision"],
        "certified_source_tree": record["certified_tree"],
        "certified_release_manifest": (
            record["certified_release_manifest"]
        ),
        "clean_checkout_completed_on": CERTIFICATION_DATE,
        "finalization_policy": "strict-single-parent-allowlist",
    }
    expected_research_records = {
        "claim": artifact_reference(
            Path("research/claim.yaml"),
            root,
        ),
        "release_gate": artifact_reference(
            Path("research/release-gate.json"),
            root,
        ),
    }
    source_research_records = {
        "claim": revision_reference(
            root,
            source_revision,
            Path("research/claim.yaml"),
        ),
        "release_gate": revision_reference(
            root,
            source_revision,
            Path("research/release-gate.json"),
        ),
    }
    expected_source_verification = {
        "status": "pending_clean_checkout_replay",
        "pending_requirement": (
            "Replay the committed v2 proof bundle and release checks "
            "from an independent clean checkout, then retain a "
            "revision-bound attestation."
        ),
        "solver_drat_plan": plan_reference,
        "solver_drat_index": index_reference,
        "solver_drat_bundle_manifest": {
            **manifest_reference,
            "artifact_count": 422,
        },
        "solver_drat_proof_directory": {
            "path": PROOF_DIRECTORY.as_posix(),
            "artifact_count": 420,
            "digest": (
                "44504c6320ac22ad62507f70222c2e8b"
                "9e6a51977f27ca3c936019c9f657f08f"
            ),
        },
        "revision_manager": record["revision_manager"],
        "certified_revision_record": None,
    }
    pending_limitation = (
        "The v2 artifact remains a release candidate until its "
        "committed revision passes an independent clean-checkout replay."
    )
    expected_source_limitations = [
        *EXPECTED_LIMITATIONS[:-1],
        pending_limitation,
        EXPECTED_LIMITATIONS[-1],
    ]
    if (
        source_release.get("version") != "0.2.0"
        or source_release.get("release_status") != "candidate"
        or source_release.get("artifact_release_status")
        != "verification_pending_clean_checkout"
        or source_release.get("theorem_release_status") != "hold"
        or source_release.get("release_date") is not None
        or source_release.get("supported_claim")
        != EXPECTED_SUPPORTED_CLAIM
        or source_release.get("artifact_reproducibility_ready")
        is not False
        or source_release.get("artifact_release_ready") is not False
        or source_release.get("theorem_announcement_ready") is not False
        or source_release.get("artifact_verification")
        != expected_source_verification
        or source_release.get("research_records")
        != source_research_records
        or source_release.get("limitations")
        != expected_source_limitations
    ):
        raise RuntimeError(
            "certified release metadata is not the pending source"
        )
    expected_release = copy.deepcopy(source_release)
    expected_release["artifact_release_status"] = (
        "clean_checkout_replay_passed"
    )
    expected_release["artifact_reproducibility_ready"] = True
    expected_release["artifact_release_ready"] = True
    expected_release["artifact_verification"] = expected_verification
    expected_release["research_records"] = expected_research_records
    expected_release["limitations"] = EXPECTED_LIMITATIONS
    if release != expected_release:
        raise RuntimeError("release metadata finalization differs")

    evidence = load_repository_json(
        root,
        Path("evidence.json"),
        "evidence metadata",
    )
    source_evidence = load_revision_json(
        root,
        source_revision,
        Path("evidence.json"),
        "certified evidence metadata",
    )
    expected_branch = {
        "classification": "evidence/fourth-word-up-classification.json",
        "rup_proof_plan": "evidence/fourth-word-rup-proof-plan.json",
        "rup_proof_index": (
            "evidence/fourth-word-rup-proof-index-v1.json"
        ),
        "rup_replay_attestation": (
            "evidence/fourth-word-rup-replay-attestation-v1.json"
        ),
        "rup_bundle_manifest": (
            "evidence/fourth-word-rup-bundle-v1.sha256"
        ),
        "rup_certified_revision_record": (
            "evidence/fourth-word-rup-revision-v1.json"
        ),
        "rup_proof_directory": (
            "evidence/proofs/fourth-word-rup-v1"
        ),
        "solver_drat_plan": PLAN_PATH.as_posix(),
        "solver_drat_plan_sha256": plan_reference["sha256"],
        "solver_drat_index": INDEX_PATH.as_posix(),
        "solver_drat_index_sha256": index_reference["sha256"],
        "solver_drat_bundle_manifest": (
            BUNDLE_MANIFEST_PATH.as_posix()
        ),
        "solver_drat_bundle_manifest_sha256": (
            manifest_reference["sha256"]
        ),
        "solver_drat_bundle_artifact_count": 422,
        "solver_drat_certified_revision_record": record_reference,
        "solver_drat_revision_manager": manager_reference,
        "solver_drat_proof_directory": PROOF_DIRECTORY.as_posix(),
        "solver_drat_proof_artifact_count": 420,
        "solver_drat_proof_directory_digest": (
            "44504c6320ac22ad62507f70222c2e8b"
            "9e6a51977f27ca3c936019c9f657f08f"
        ),
        "replay_date": "2026-09-03",
        "selected_third_word_children": 4,
        "total_branches": 350,
        "rup_unsat_branches": 184,
        "solver_drat_unsat_branches": 140,
        "combined_certified_branches": 324,
        "unresolved_branches": 26,
        "per_child": EXPECTED_PER_CHILD,
        "closed_third_word_children": 0,
        "closed_normalized_branches": 0,
        "proof_checker": "drat-trim",
        "proof_checker_commit": (
            "2e3b2dc0ecf938addbd779d42877b6ed69d9a985"
        ),
        "all_retained_proofs_checked": True,
    }
    source_expected_branch = copy.deepcopy(expected_branch)
    source_expected_branch[
        "solver_drat_certified_revision_record"
    ] = None
    if (
        source_evidence.get("fourth_word_branch_reduction")
        != source_expected_branch
    ):
        raise RuntimeError(
            "certified evidence metadata is not the pending source"
        )
    expected_size_15_result = {
        "status": "open",
        "certificate": None,
        "proof_trace": None,
        "new_claim": None,
        "normalized_branches_closed": 112,
        "normalized_branches_remaining": 38,
        "fourth_word_rup_branches_closed": 184,
        "fourth_word_solver_drat_branches_closed": 140,
        "fourth_word_certified_branches_closed": 324,
        "fourth_word_branches_remaining": 26,
        "newly_closed_normalized_branches": 0,
    }
    if source_evidence.get("size_15_result") != expected_size_15_result:
        raise RuntimeError(
            "certified size-15 result metadata is invalid"
        )
    expected_evidence = copy.deepcopy(source_evidence)
    expected_evidence["fourth_word_branch_reduction"] = expected_branch
    if evidence != expected_evidence:
        raise RuntimeError("size-15 result metadata is invalid")
    gate = load_repository_json(
        root,
        Path("research/release-gate.json"),
        "release gate",
    )
    expected_gate = {
        "schema_version": 1,
        "project": "binary-covering-code-11-3",
        "evaluated_at": CERTIFICATION_DATE,
        "candidate_claim": None,
        "gates": EXPECTED_GATE_VALUES,
        "artifact_decision": "ready",
        "decision_scope": "theorem_announcement",
        "decision": "hold",
        "reason": (
            "The fourth-word evidence contains 184 checked RUP "
            "closures and 140 clean-checkout-replayed solver-generated "
            "DRAT closures, for 324 certified closures out of 350. "
            "Artifact release is ready under the retained revision "
            "attestation. A theorem announcement remains on hold "
            "because 26 fourth-word branches, every selected child, "
            "and all 38 residual parents remain open."
        ),
    }
    if gate != expected_gate:
        raise RuntimeError("release gate is not finalized")


def verify_finalized_release(
    *,
    root: Path,
    record_path: Path,
    release_argument: str,
) -> dict[str, object]:
    record = load_record(record_path)
    source_revision = str(record["certified_revision"])
    release_revision, _ = resolve_revision(root, release_argument)
    require_clean_head(root, release_revision)
    require_single_parent_release(
        root,
        source_revision,
        release_revision,
    )
    changed = finalization_changed_paths(
        root,
        source_revision,
        release_revision,
    )
    validate_finalization_paths(changed)
    for relative in changed:
        require_regular_git_blob(root, release_revision, relative)
    validate_source_record(record, root)
    validate_v2_bundle(root)
    validate_root_release_manifest(root)
    verify_metadata_bindings(root, record)
    if artifact_reference(MANAGER_PATH, root) != record["revision_manager"]:
        raise RuntimeError("current revision manager differs")
    return {
        "certified_revision": source_revision,
        "changed_paths": sorted(changed),
        "record": RECORD_PATH.as_posix(),
        "release_revision": release_revision,
        "valid": True,
    }


def run_and_record(
    *,
    root: Path,
    revision_argument: str,
    completed_on: str,
    python_executable: Path,
) -> dict[str, object]:
    completed_on = parse_iso_date(completed_on)
    if completed_on != CERTIFICATION_DATE:
        raise RuntimeError(
            "clean replay must use the certification date"
        )
    revision, tree = resolve_revision(root, revision_argument)
    require_clean_head(root, revision)
    record_path = repository_path(RECORD_PATH, root)
    if record_path.exists() or record_path.is_symlink():
        raise RuntimeError("v2 revision record already exists")
    python_executable = validate_python_interpreter(python_executable)
    replay_root = canonical_replay_root(root, revision)
    validate_v2_bundle(root)
    validate_root_release_manifest(root)
    if artifact_reference(MANAGER_PATH, root) != revision_reference(
        root,
        revision,
        MANAGER_PATH,
    ):
        raise RuntimeError(
            "current revision manager differs from certified revision"
        )
    checkout, results, toolchain = run_clean_checkout(
        root=root,
        revision=revision,
        python_executable=python_executable,
        replay_root=replay_root,
    )
    record = build_record(
        checkout=checkout,
        revision=revision,
        tree=tree,
        completed_on=completed_on,
        results=results,
        toolchain=toolchain,
    )
    validate_source_record(record, root)
    atomic_write_bytes(record_path, canonical_json(record))
    return {
        "certified_revision": revision,
        "record": RECORD_PATH.as_posix(),
        "replay_root": str(replay_root.relative_to(root)),
        "valid": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--run-clean-replay", action="store_true")
    action.add_argument("--verify", action="store_true")
    parser.add_argument("--revision")
    parser.add_argument("--release-revision", default="HEAD")
    parser.add_argument("--completed-on")
    parser.add_argument("--python", type=Path)
    args = parser.parse_args()

    root = ROOT.resolve()
    verify_repository_root(root)
    if args.run_clean_replay:
        if (
            args.revision is None
            or args.completed_on is None
            or args.python is None
        ):
            parser.error(
                "--run-clean-replay requires --revision "
                "--completed-on, and --python"
            )
        revision = require_git_object_id(
            args.revision,
            "revision argument",
        )
        result = run_and_record(
            root=root,
            revision_argument=revision,
            completed_on=args.completed_on,
            python_executable=args.python,
        )
    else:
        result = verify_finalized_release(
            root=root,
            record_path=repository_path(RECORD_PATH, root),
            release_argument=args.release_revision,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
