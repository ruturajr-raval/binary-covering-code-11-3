#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

from audit_fourth_word_rup_proofs import (
    python_tree_record,
    validate_pipeline_provenance,
)
from repository_lock import (
    LOCK_FD_ENV,
    acquire_repository_lock,
)


RECORD_PATH = Path("evidence/fourth-word-rup-revision-v1.json")
PROOF_INDEX = Path("evidence/fourth-word-rup-proof-index-v1.json")
BUNDLE_MANIFEST = Path("evidence/fourth-word-rup-bundle-v1.sha256")
REPLAY_ATTESTATION = Path(
    "evidence/fourth-word-rup-replay-attestation-v1.json"
)
RELEASE_MANIFEST = Path("release-manifest.sha256")
REPLAY_REQUIREMENTS = Path("requirements-replay.txt")
PYPI_INDEX = "https://pypi.org/simple"
SCHEMA_VERSION = 2
OUTPUT_COMMITMENT_SCOPE = "host-specific-self-attestation"
TOOLCHAIN_SOURCES = {
    "git": "system-default-path",
    "make": "system-default-path",
    "python": "explicit-absolute-path",
}
REPLAY_COMMANDS = [
    (
        "git clone --no-hardlinks --no-checkout "
        "<repository> <clean-replay>"
    ),
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
    "make test PYTHON=.venv/bin/python",
    "make audit-fourth-word-rup-proofs PYTHON=.venv/bin/python",
    (
        "make verify-release-manifest PYTHON=.venv/bin/python "
        "ALLOW_PENDING_REVISION=1"
    ),
    "git diff --exit-code",
    "git status --porcelain --untracked-files=all",
]


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


def require_regular_single_link(path: Path, description: str) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_nlink != 1
    ):
        raise RuntimeError(
            f"{description} is not a single-link regular file: {path}"
        )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def require_sha256(value: object, description: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RuntimeError(f"{description} is not a SHA-256 digest")
    return value


def require_git_object_id(value: object, description: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RuntimeError(f"{description} is not a Git object id")
    return value


def validate_toolchain_attestation(
    value: object,
) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict) or set(value) != set(
        TOOLCHAIN_SOURCES
    ):
        raise RuntimeError("clean-replay toolchain attestation is invalid")
    validated = {}
    for role, source in TOOLCHAIN_SOURCES.items():
        record = value[role]
        if (
            not isinstance(record, dict)
            or set(record) != {"source", "sha256"}
            or record["source"] != source
        ):
            raise RuntimeError(
                f"clean-replay {role} attestation is invalid"
            )
        validated[role] = {
            "source": source,
            "sha256": require_sha256(
                record["sha256"],
                f"clean-replay {role} executable hash",
            ),
        }
    return validated


def parse_date(value: object, description: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"{description} is not an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError(f"{description} is not an ISO date") from exc
    if parsed.isoformat() != value:
        raise RuntimeError(f"{description} is not canonical")
    return value


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
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
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()
            fsync_directory(temporary.parent)


def canonical_json(record: object) -> bytes:
    return (
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    ).encode("ascii")


def command_result(
    command: str,
    output: bytes,
) -> dict[str, object]:
    return {
        "command": command,
        "return_code": 0,
        "output_bytes": len(output),
        "output_sha256": sha256_bytes(output),
    }


def validate_command_results(
    value: object,
    *,
    revision: Optional[str] = None,
) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) != len(REPLAY_COMMANDS):
        raise RuntimeError("clean-replay command results are invalid")
    validated = []
    for expected_command, result in zip(REPLAY_COMMANDS, value):
        if (
            not isinstance(result, dict)
            or set(result)
            != {
                "command",
                "return_code",
                "output_bytes",
                "output_sha256",
            }
            or result["command"] != expected_command
            or type(result["return_code"]) is not int
            or result["return_code"] != 0
            or type(result["output_bytes"]) is not int
            or result["output_bytes"] < 0
        ):
            raise RuntimeError("clean-replay command result is invalid")
        validated.append(
            {
                "command": expected_command,
                "return_code": 0,
                "output_bytes": result["output_bytes"],
                "output_sha256": require_sha256(
                    result["output_sha256"],
                    "clean-replay command output hash",
                ),
            }
        )
    if revision is not None:
        semantic_expectations = {
            2: (revision + "\n").encode("ascii"),
            8: b"",
            9: b"",
        }
        for index, expected_output in semantic_expectations.items():
            if validated[index] != command_result(
                REPLAY_COMMANDS[index],
                expected_output,
            ):
                raise RuntimeError(
                    "clean-replay command result has invalid semantics"
                )
    return validated


def command_results_digest(results: object) -> str:
    return sha256_bytes(canonical_json(validate_command_results(results)))


def artifact_reference(path: Path, *, root: Path) -> dict[str, str]:
    resolved = repository_path(path, root)
    require_regular_single_link(resolved, str(path))
    return {
        "path": str(resolved.relative_to(root)),
        "sha256": file_sha256(resolved),
    }


def validate_reference(
    reference: object,
    *,
    expected_path: Path,
    description: str,
) -> dict[str, str]:
    if (
        not isinstance(reference, dict)
        or set(reference) != {"path", "sha256"}
        or reference["path"] != str(expected_path)
    ):
        raise RuntimeError(f"{description} reference is invalid")
    return {
        "path": str(expected_path),
        "sha256": require_sha256(
            reference["sha256"],
            f"{description} hash",
        ),
    }


def pending_record(
    *,
    proof_index: dict[str, str],
    bundle_manifest: dict[str, str],
    replay_attestation: dict[str, str],
) -> dict[str, object]:
    return {
        "record_type": "fourth-word-rup-certified-revision",
        "schema_version": SCHEMA_VERSION,
        "status": "pending-clean-checkout-replay",
        "proof_index": proof_index,
        "bundle_manifest": bundle_manifest,
        "replay_attestation": replay_attestation,
        "certified_revision": None,
        "certified_tree": None,
        "certified_release_manifest": None,
        "clean_checkout_replay": {
            "passed": False,
            "revision": None,
            "completed_on": None,
            "working_tree_clean": False,
            "commands": REPLAY_COMMANDS,
            "output_commitment_scope": OUTPUT_COMMITMENT_SCOPE,
            "command_results": None,
            "command_results_sha256": None,
            "toolchain": None,
        },
    }


def finalized_record(
    pending: dict[str, object],
    *,
    revision: str,
    tree: str,
    release_manifest: dict[str, str],
    completed_on: str,
    command_results: list[dict[str, object]],
    toolchain: dict[str, dict[str, str]],
) -> dict[str, object]:
    validated_results = validate_command_results(
        command_results,
        revision=revision,
    )
    return {
        **pending,
        "status": "clean-checkout-replay-passed",
        "certified_revision": revision,
        "certified_tree": tree,
        "certified_release_manifest": release_manifest,
        "clean_checkout_replay": {
            "passed": True,
            "revision": revision,
            "completed_on": completed_on,
            "working_tree_clean": True,
            "commands": REPLAY_COMMANDS,
            "output_commitment_scope": OUTPUT_COMMITMENT_SCOPE,
            "command_results": validated_results,
            "command_results_sha256": command_results_digest(
                validated_results
            ),
            "toolchain": toolchain,
        },
    }


def validate_record_schema(
    record: object,
    *,
    allow_pending: bool,
) -> str:
    expected_keys = {
        "record_type",
        "schema_version",
        "status",
        "proof_index",
        "bundle_manifest",
        "replay_attestation",
        "certified_revision",
        "certified_tree",
        "certified_release_manifest",
        "clean_checkout_replay",
    }
    if not isinstance(record, dict) or set(record) != expected_keys:
        raise RuntimeError("revision record schema is invalid")
    if record["record_type"] != "fourth-word-rup-certified-revision":
        raise RuntimeError("revision record type is invalid")
    if type(record["schema_version"]) is not int or record[
        "schema_version"
    ] != SCHEMA_VERSION:
        raise RuntimeError("revision record schema version is invalid")
    validate_reference(
        record["proof_index"],
        expected_path=PROOF_INDEX,
        description="proof index",
    )
    validate_reference(
        record["bundle_manifest"],
        expected_path=BUNDLE_MANIFEST,
        description="bundle manifest",
    )
    validate_reference(
        record["replay_attestation"],
        expected_path=REPLAY_ATTESTATION,
        description="replay attestation",
    )
    replay = record["clean_checkout_replay"]
    if (
        not isinstance(replay, dict)
        or set(replay)
        != {
            "passed",
            "revision",
            "completed_on",
            "working_tree_clean",
            "commands",
            "output_commitment_scope",
            "command_results",
            "command_results_sha256",
            "toolchain",
        }
        or replay["commands"] != REPLAY_COMMANDS
        or replay["output_commitment_scope"] != OUTPUT_COMMITMENT_SCOPE
    ):
        raise RuntimeError("clean-checkout replay record is invalid")
    status = record["status"]
    if status == "pending-clean-checkout-replay":
        if not allow_pending:
            raise RuntimeError("clean-checkout replay is still pending")
        if (
            record["certified_revision"] is not None
            or record["certified_tree"] is not None
            or record["certified_release_manifest"] is not None
            or replay["passed"] is not False
            or replay["revision"] is not None
            or replay["completed_on"] is not None
            or replay["working_tree_clean"] is not False
            or replay["command_results"] is not None
            or replay["command_results_sha256"] is not None
            or replay["toolchain"] is not None
        ):
            raise RuntimeError("pending revision record is inconsistent")
        return status
    if status != "clean-checkout-replay-passed":
        raise RuntimeError("revision record status is invalid")
    revision = require_git_object_id(
        record["certified_revision"],
        "certified revision",
    )
    require_git_object_id(record["certified_tree"], "certified tree")
    validate_reference(
        record["certified_release_manifest"],
        expected_path=RELEASE_MANIFEST,
        description="certified release manifest",
    )
    if (
        replay["passed"] is not True
        or replay["revision"] != revision
        or replay["working_tree_clean"] is not True
    ):
        raise RuntimeError("completed replay record is inconsistent")
    parse_date(replay["completed_on"], "replay completion date")
    command_results = validate_command_results(
        replay["command_results"],
        revision=revision,
    )
    command_results_sha256 = require_sha256(
        replay["command_results_sha256"],
        "clean-replay command-results hash",
    )
    if command_results_sha256 != command_results_digest(command_results):
        raise RuntimeError(
            "clean-replay command-results hash does not match"
        )
    validate_toolchain_attestation(replay["toolchain"])
    return status


def sanitized_environment(
    *,
    remove_repository_lock: bool = False,
) -> dict[str, str]:
    environment = {
        "PATH": os.defpath,
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    if not remove_repository_lock and LOCK_FD_ENV in os.environ:
        environment[LOCK_FD_ENV] = os.environ[LOCK_FD_ENV]
    if remove_repository_lock:
        environment.update(
            {
                "PIP_CONFIG_FILE": os.devnull,
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_KEYRING_PROVIDER": "disabled",
                "PIP_NO_INPUT": "1",
            }
        )
    return environment


def resolve_executable(
    name: str,
    *,
    environment: dict[str, str],
) -> str:
    resolved = shutil.which(name, path=environment.get("PATH"))
    if resolved is None:
        raise RuntimeError(f"required executable was not found: {name}")
    return resolved


def executable_attestation(
    *,
    git_executable: Path,
    make_executable: Path,
    python_executable: Path,
) -> dict[str, dict[str, str]]:
    paths = {
        "git": git_executable,
        "make": make_executable,
        "python": python_executable,
    }
    attestation = {}
    for role, path in paths.items():
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(
                f"clean-replay {role} executable is invalid"
            )
        attestation[role] = {
            "source": TOOLCHAIN_SOURCES[role],
            "sha256": file_sha256(path),
        }
    return validate_toolchain_attestation(attestation)


def replay_git_command(
    git_executable: str,
    hooks_directory: Path,
    arguments: list[str],
) -> list[str]:
    return [
        git_executable,
        "--no-replace-objects",
        "-c",
        f"core.hooksPath={hooks_directory}",
        "-c",
        f"core.attributesFile={os.devnull}",
        "-c",
        "core.fsmonitor=false",
        *arguments,
    ]


def git_bytes(root: Path, arguments: list[str]) -> bytes:
    environment = sanitized_environment()
    git_executable = resolve_executable(
        "git",
        environment=environment,
    )
    result = subprocess.run(
        [
            git_executable,
            "--no-replace-objects",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(root),
            *arguments,
        ],
        check=False,
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "git command failed: "
            + " ".join(arguments)
            + "\n"
            + result.stderr.decode("utf-8", errors="replace")
        )
    return result.stdout


def verify_repository_root(root: Path) -> None:
    observed = git_bytes(
        root,
        ["rev-parse", "--show-toplevel"],
    ).decode("utf-8").strip()
    if Path(observed).resolve() != root:
        raise RuntimeError("Git repository root differs")


def resolve_revision(root: Path, revision: str) -> tuple[str, str]:
    revision = require_git_object_id(
        revision,
        "revision argument",
    )
    commit = git_bytes(
        root,
        [
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{revision}^{{commit}}",
        ],
    ).decode("ascii").strip()
    tree = git_bytes(
        root,
        ["rev-parse", "--verify", f"{commit}^{{tree}}"],
    ).decode("ascii").strip()
    return (
        require_git_object_id(commit, "resolved revision"),
        require_git_object_id(tree, "resolved tree"),
    )


def require_clean_head(root: Path, revision: str) -> None:
    head = git_bytes(
        root,
        ["rev-parse", "--verify", "HEAD"],
    ).decode("ascii").strip()
    if head != revision:
        raise RuntimeError(
            "current HEAD is not the certified revision"
        )
    status = git_bytes(
        root,
        [
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
    )
    if status:
        raise RuntimeError(
            "current worktree is not clean before finalization"
        )


def run_process(
    arguments: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    description: str,
    print_output: bool = True,
) -> bytes:
    result = subprocess.run(
        arguments,
        check=False,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if print_output and result.stdout:
        print(
            result.stdout.decode("utf-8", errors="replace"),
            end="",
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"clean-replay command failed: {description}"
        )
    return result.stdout


def run_clean_checkout_replay(
    *,
    root: Path,
    revision: str,
    python_command: str,
) -> dict[str, object]:
    replay_directory = repository_path(
        Path(".research-artifacts")
        / f"clean-replay-{revision}",
        root,
    )
    runtime_directory = repository_path(
        Path(".research-artifacts")
        / f".clean-replay-runtime-{revision}",
        root,
    )
    if replay_directory.exists() or replay_directory.is_symlink():
        if replay_directory.is_symlink() or not replay_directory.is_dir():
            raise RuntimeError("clean-replay path is invalid")
        shutil.rmtree(replay_directory)
    if runtime_directory.exists() or runtime_directory.is_symlink():
        if runtime_directory.is_symlink() or not runtime_directory.is_dir():
            raise RuntimeError("clean-replay runtime path is invalid")
        shutil.rmtree(runtime_directory)
    replay_directory.parent.mkdir(parents=True, exist_ok=True)
    runtime_directory.mkdir()
    hooks_directory = runtime_directory / "hooks"
    template_directory = runtime_directory / "template"
    home_directory = runtime_directory / "home"
    config_directory = runtime_directory / "config"
    cache_directory = runtime_directory / "cache"
    temporary_directory = runtime_directory / "tmp"
    for directory in (
        hooks_directory,
        template_directory,
        home_directory,
        config_directory,
        cache_directory,
        temporary_directory,
    ):
        directory.mkdir()
    try:
        environment = sanitized_environment(remove_repository_lock=True)
        git_executable = resolve_executable(
            "git",
            environment=environment,
        )
        make_executable = resolve_executable(
            "make",
            environment=environment,
        )
        source_python = Path(python_command)
        if not source_python.is_absolute():
            raise RuntimeError(
                "clean-replay source interpreter must be absolute"
            )
        source_python = Path(os.path.abspath(str(source_python)))
        toolchain = executable_attestation(
            git_executable=Path(git_executable),
            make_executable=Path(make_executable),
            python_executable=source_python,
        )
        environment.update(
            {
                "HOME": str(home_directory),
                "TMPDIR": str(temporary_directory),
                "XDG_CACHE_HOME": str(cache_directory),
                "XDG_CONFIG_HOME": str(config_directory),
            }
        )
        results = []

        commands = [
            (
                replay_git_command(
                    git_executable,
                    hooks_directory,
                    [
                        "clone",
                        "--no-hardlinks",
                        "--no-checkout",
                        "--quiet",
                        f"--template={template_directory}",
                        str(root),
                        str(replay_directory),
                    ],
                ),
                root,
                REPLAY_COMMANDS[0],
            ),
            (
                replay_git_command(
                    git_executable,
                    hooks_directory,
                    [
                        "-C",
                        str(replay_directory),
                        "checkout",
                        "--detach",
                        "--quiet",
                        revision,
                    ],
                ),
                root,
                REPLAY_COMMANDS[1],
            ),
        ]
        for arguments, cwd, description in commands:
            output = run_process(
                arguments,
                cwd=cwd,
                environment=environment,
                description=description,
            )
            results.append(command_result(description, output))

        revision_output = run_process(
            replay_git_command(
                git_executable,
                hooks_directory,
                [
                    "-C",
                    str(replay_directory),
                    "rev-parse",
                    "HEAD",
                ],
            ),
            cwd=root,
            environment=environment,
            description=REPLAY_COMMANDS[2],
            print_output=False,
        )
        observed_revision = revision_output.decode("ascii").strip()
        if observed_revision != revision:
            raise RuntimeError(
                "clean-replay checkout is not the certified revision"
            )
        results.append(
            command_result(REPLAY_COMMANDS[2], revision_output)
        )

        replay_python = replay_directory / ".venv/bin/python"
        replay_commands = [
            (
                [
                    str(source_python),
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
                    str(REPLAY_REQUIREMENTS),
                ],
                REPLAY_COMMANDS[4],
            ),
            (
                [
                    make_executable,
                    "test",
                    "PYTHON=.venv/bin/python",
                ],
                REPLAY_COMMANDS[5],
            ),
            (
                [
                    make_executable,
                    "audit-fourth-word-rup-proofs",
                    "PYTHON=.venv/bin/python",
                ],
                REPLAY_COMMANDS[6],
            ),
            (
                [
                    make_executable,
                    "verify-release-manifest",
                    "PYTHON=.venv/bin/python",
                    "ALLOW_PENDING_REVISION=1",
                ],
                REPLAY_COMMANDS[7],
            ),
            (
                replay_git_command(
                    git_executable,
                    hooks_directory,
                    [
                        "diff",
                        "--no-ext-diff",
                        "--exit-code",
                    ],
                ),
                REPLAY_COMMANDS[8],
            ),
        ]
        for arguments, description in replay_commands:
            output = run_process(
                arguments,
                cwd=replay_directory,
                environment=environment,
                description=description,
            )
            results.append(command_result(description, output))

        status = run_process(
            replay_git_command(
                git_executable,
                hooks_directory,
                [
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=all",
                ],
            ),
            cwd=replay_directory,
            environment=environment,
            description=REPLAY_COMMANDS[9],
            print_output=False,
        )
        if status:
            raise RuntimeError(
                "clean-replay worktree is not clean after verification"
            )
        results.append(command_result(REPLAY_COMMANDS[9], status))
        if executable_attestation(
            git_executable=Path(git_executable),
            make_executable=Path(make_executable),
            python_executable=source_python,
        ) != toolchain:
            raise RuntimeError(
                "clean-replay toolchain changed during verification"
            )
        return {
            "command_results": results,
            "command_results_sha256": command_results_digest(results),
            "toolchain": toolchain,
        }
    finally:
        if runtime_directory.exists():
            shutil.rmtree(runtime_directory)


def git_file(root: Path, revision: str, path: Path) -> bytes:
    return git_bytes(root, ["show", f"{revision}:{path}"])


def revision_reference(
    root: Path,
    revision: str,
    path: Path,
) -> dict[str, str]:
    return {
        "path": str(path),
        "sha256": sha256_bytes(git_file(root, revision, path)),
    }


def revision_python_tree(
    root: Path,
    revision: str,
) -> dict[str, object]:
    names = git_bytes(
        root,
        [
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            revision,
            "--",
            "src",
            "tools",
        ],
    ).split(b"\0")
    paths = sorted(
        Path(name.decode("utf-8"))
        for name in names
        if name and name.endswith(b".py")
    )
    payload = "".join(
        f"{path}:{sha256_bytes(git_file(root, revision, path))}\n"
        for path in paths
    )
    return {
        "roots": ["src", "tools"],
        "file_count": len(paths),
        "sha256": sha256_bytes(payload.encode("ascii")),
    }


def validate_frozen_sources(
    *,
    root: Path,
    revision: str,
    index: dict[str, object],
) -> None:
    pipeline_files = index["pipeline_files"]
    pipeline_tree = index["pipeline_python_tree"]
    validate_pipeline_provenance(
        pipeline_files,
        pipeline_tree,
        root=root,
    )
    if not isinstance(pipeline_files, dict):
        raise RuntimeError("proof-index pipeline files are invalid")
    for record in pipeline_files.values():
        path = Path(str(record["path"]))
        revision_digest = sha256_bytes(git_file(root, revision, path))
        if revision_digest != record["sha256"]:
            raise RuntimeError(
                f"certified revision pipeline hash differs: {path}"
            )
    if revision_python_tree(root, revision) != pipeline_tree:
        raise RuntimeError(
            "certified revision Python source tree differs"
        )
    if python_tree_record(root) != pipeline_tree:
        raise RuntimeError("current Python source tree is not frozen")


def load_record(path: Path) -> dict[str, object]:
    try:
        record = json.loads(path.read_text(encoding="ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("revision record is invalid JSON") from exc
    if not isinstance(record, dict):
        raise RuntimeError("revision record is not an object")
    return record


def write_pending(path: Path, *, root: Path) -> dict[str, object]:
    index_path = repository_path(PROOF_INDEX, root)
    require_regular_single_link(index_path, "proof index")
    index = json.loads(index_path.read_text(encoding="ascii"))
    validate_pipeline_provenance(
        index["pipeline_files"],
        index["pipeline_python_tree"],
        root=root,
    )
    record = pending_record(
        proof_index=artifact_reference(PROOF_INDEX, root=root),
        bundle_manifest=artifact_reference(BUNDLE_MANIFEST, root=root),
        replay_attestation=artifact_reference(
            REPLAY_ATTESTATION,
            root=root,
        ),
    )
    validate_record_schema(record, allow_pending=True)
    payload = canonical_json(record)
    if path.exists() or path.is_symlink():
        require_regular_single_link(path, "revision record")
        if path.read_bytes() != payload:
            raise RuntimeError("existing revision record differs")
    else:
        atomic_write_bytes(path, payload)
    return record


def validate_artifact_references(
    record: dict[str, object],
    *,
    root: Path,
) -> None:
    expected = {
        "proof_index": artifact_reference(PROOF_INDEX, root=root),
        "bundle_manifest": artifact_reference(
            BUNDLE_MANIFEST,
            root=root,
        ),
        "replay_attestation": artifact_reference(
            REPLAY_ATTESTATION,
            root=root,
        ),
    }
    for label, reference in expected.items():
        if record[label] != reference:
            raise RuntimeError(
                f"revision record {label} does not match current bytes"
            )


def validate_final_record(
    record: dict[str, object],
    *,
    root: Path,
) -> None:
    validate_record_schema(record, allow_pending=False)
    revision = str(record["certified_revision"])
    commit, tree = resolve_revision(root, revision)
    if commit != revision or tree != record["certified_tree"]:
        raise RuntimeError("certified Git revision identity differs")
    validate_artifact_references(record, root=root)
    for label, path in (
        ("proof_index", PROOF_INDEX),
        ("bundle_manifest", BUNDLE_MANIFEST),
        ("replay_attestation", REPLAY_ATTESTATION),
    ):
        if revision_reference(root, revision, path) != record[label]:
            raise RuntimeError(
                f"certified revision {label} bytes differ"
            )
    expected_release_manifest = revision_reference(
        root,
        revision,
        RELEASE_MANIFEST,
    )
    if record["certified_release_manifest"] != expected_release_manifest:
        raise RuntimeError(
            "certified revision release manifest differs"
        )
    index = json.loads((root / PROOF_INDEX).read_text(encoding="ascii"))
    validate_frozen_sources(
        root=root,
        revision=revision,
        index=index,
    )


def finalize_record(
    path: Path,
    *,
    root: Path,
    revision_argument: str,
    completed_on: str,
    python_command: str,
) -> dict[str, object]:
    parse_date(completed_on, "replay completion date")
    require_regular_single_link(path, "pending revision record")
    current = load_record(path)
    if current.get("status") == "clean-checkout-replay-passed":
        validate_final_record(current, root=root)
        if (
            current["certified_revision"]
            != resolve_revision(root, revision_argument)[0]
            or current["clean_checkout_replay"]["completed_on"]
            != completed_on
        ):
            raise RuntimeError(
                "existing finalized revision record differs"
            )
        return current
    validate_record_schema(current, allow_pending=True)
    validate_artifact_references(current, root=root)
    revision, tree = resolve_revision(root, revision_argument)
    require_clean_head(root, revision)
    for label, artifact_path in (
        ("proof_index", PROOF_INDEX),
        ("bundle_manifest", BUNDLE_MANIFEST),
        ("replay_attestation", REPLAY_ATTESTATION),
    ):
        if revision_reference(root, revision, artifact_path) != current[label]:
            raise RuntimeError(
                f"certified revision {label} bytes differ"
            )
    index = json.loads((root / PROOF_INDEX).read_text(encoding="ascii"))
    validate_frozen_sources(
        root=root,
        revision=revision,
        index=index,
    )
    replay_result = run_clean_checkout_replay(
        root=root,
        revision=revision,
        python_command=python_command,
    )
    command_results = validate_command_results(
        replay_result.get("command_results"),
        revision=revision,
    )
    command_results_sha256 = require_sha256(
        replay_result.get("command_results_sha256"),
        "clean-replay command-results hash",
    )
    if command_results_sha256 != command_results_digest(command_results):
        raise RuntimeError(
            "clean-replay command-results hash does not match"
        )
    toolchain = validate_toolchain_attestation(
        replay_result.get("toolchain")
    )
    require_clean_head(root, revision)
    record = finalized_record(
        current,
        revision=revision,
        tree=tree,
        release_manifest=revision_reference(
            root,
            revision,
            RELEASE_MANIFEST,
        ),
        completed_on=completed_on,
        command_results=command_results,
        toolchain=toolchain,
    )
    validate_record_schema(record, allow_pending=False)
    validate_final_record(record, root=root)
    require_clean_head(root, revision)
    atomic_write_bytes(path, canonical_json(record))
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write-pending", action="store_true")
    action.add_argument("--finalize", action="store_true")
    action.add_argument("--verify", action="store_true")
    parser.add_argument("--revision")
    parser.add_argument("--completed-on")
    parser.add_argument("--python")
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args()

    root = repository_root()
    repository_lock = acquire_repository_lock(root)
    atexit.register(repository_lock.close)
    verify_repository_root(root)
    record_path = repository_path(args.record, root)
    if record_path != root / RECORD_PATH:
        raise SystemExit("revision record path is not canonical")
    if args.write_pending:
        if (
            args.revision
            or args.completed_on
            or args.python
            or args.allow_pending
        ):
            raise SystemExit("pending-record arguments are inconsistent")
        record = write_pending(record_path, root=root)
    elif args.finalize:
        if (
            not args.revision
            or not args.completed_on
            or args.allow_pending
        ):
            raise SystemExit("finalization arguments are incomplete")
        record = finalize_record(
            record_path,
            root=root,
            revision_argument=args.revision,
            completed_on=args.completed_on,
            python_command=args.python or sys.executable,
        )
    else:
        if args.revision or args.completed_on or args.python:
            raise SystemExit("verification does not accept revision arguments")
        require_regular_single_link(record_path, "revision record")
        record = load_record(record_path)
        status = validate_record_schema(
            record,
            allow_pending=args.allow_pending,
        )
        validate_artifact_references(record, root=root)
        if status == "clean-checkout-replay-passed":
            validate_final_record(record, root=root)
    print(
        json.dumps(
            {
                "record": str(RECORD_PATH),
                "status": record["status"],
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
