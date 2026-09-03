#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import subprocess

from repository_lock import (
    acquire_repository_lock,
    subprocess_lock_kwargs,
)


PROOF_DIRECTORY = Path("evidence/proofs/fourth-word-rup-v1")
PROOF_INDEX = Path("evidence/fourth-word-rup-proof-index-v1.json")
REPLAY_ATTESTATION = Path(
    "evidence/fourth-word-rup-replay-attestation-v1.json"
)
PROMOTION_JOURNAL = Path(
    "evidence/.fourth-word-rup-promotion-v1.json"
)
CHECKER_PATH = Path("build/drat-trim-src/drat-trim")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def repository_path(path: Path, root: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    lexical = Path(os.path.abspath(str(candidate)))
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        raise RuntimeError(f"path is outside the repository: {path}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"path contains a symbolic link: {path}")
    return lexical


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_regular_single_link(path: Path, description: str) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_nlink != 1
    ):
        raise RuntimeError(
            f"{description} is not a single-link regular file: {path}"
        )


def validate_retained_arguments(
    *,
    root: Path,
    checker: str,
    checker_commit: str,
    attestation_date: str,
) -> None:
    try:
        parsed_date = date.fromisoformat(attestation_date)
    except ValueError as exc:
        raise RuntimeError("attestation date is invalid") from exc
    if parsed_date.isoformat() != attestation_date:
        raise RuntimeError("attestation date is not canonical")
    if (
        len(checker_commit) != 40
        or any(
            character not in "0123456789abcdef"
            for character in checker_commit
        )
    ):
        raise RuntimeError("checker commit is invalid")
    index_path = repository_path(PROOF_INDEX, root)
    attestation_path = repository_path(REPLAY_ATTESTATION, root)
    checker_path = repository_path(Path(checker), root)
    if checker_path != root / CHECKER_PATH:
        raise RuntimeError("proof checker path is not canonical")
    require_regular_single_link(index_path, "proof index")
    require_regular_single_link(
        attestation_path,
        "replay attestation",
    )
    require_regular_single_link(checker_path, "proof checker")
    index = json.loads(index_path.read_text(encoding="ascii"))
    attestation = json.loads(
        attestation_path.read_text(encoding="ascii")
    )
    if (
        index.get("checker_commit") != checker_commit
        or attestation.get("checker", {}).get("commit")
        != checker_commit
    ):
        raise RuntimeError("retained checker commit differs")
    if attestation.get("replay_date") != attestation_date:
        raise RuntimeError("retained attestation date differs")
    if (
        attestation.get("checker", {}).get("binary_sha256")
        != file_sha256(checker_path)
    ):
        raise RuntimeError("retained checker binary differs")


def certification_actions(
    *,
    proof_directory: Path,
    proof_index: Path,
    attestation: Path,
    promotion_journal: Path,
) -> list[str]:
    proof_exists = path_exists(proof_directory)
    index_exists = path_exists(proof_index)
    attestation_exists = path_exists(attestation)
    journal_exists = path_exists(promotion_journal)
    if attestation_exists and not (proof_exists and index_exists):
        raise RuntimeError(
            "replay attestation exists without a complete proof bundle"
        )
    if proof_exists != index_exists and not journal_exists:
        raise RuntimeError(
            "proof directory and proof index are inconsistent"
        )
    actions = []
    if journal_exists or not (proof_exists and index_exists):
        actions.append("create")
    if not attestation_exists:
        actions.append("attest")
    actions.append("audit")
    return actions


def run_command(
    arguments: list[str],
    *,
    environment: dict[str, str],
    root: Path,
) -> None:
    result = subprocess.run(
        arguments,
        check=False,
        cwd=root,
        env=environment,
        **subprocess_lock_kwargs(environment),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed with status {result.returncode}: "
            + " ".join(arguments)
        )


def proof_command(
    *,
    python_command: str,
    checker: str,
    checker_commit: str,
) -> list[str]:
    return [
        python_command,
        "tools/prove_fourth_word_rup_cases.py",
        "evidence/residual-two-word-cases.json",
        "evidence/third-word-cases.json",
        "research/third-word-child-frontier.json",
        "research/fourth-word-hard-frontier.json",
        "evidence/fourth-word-up-classification.json",
        "evidence/fourth-word-rup-proof-plan.json",
        "build/proofs/fourth-word",
        str(PROOF_DIRECTORY),
        str(PROOF_INDEX),
        "--checker",
        checker,
        "--checker-commit",
        checker_commit,
        "--python",
        python_command,
    ]


def audit_command(*, python_command: str) -> list[str]:
    return [
        python_command,
        "tools/audit_fourth_word_rup_proofs.py",
        "evidence/residual-two-word-cases.json",
        "evidence/third-word-cases.json",
        "research/third-word-child-frontier.json",
        "research/fourth-word-hard-frontier.json",
        "evidence/fourth-word-up-classification.json",
        "evidence/fourth-word-rup-proof-plan.json",
        str(PROOF_INDEX),
        str(PROOF_DIRECTORY),
    ]


def certify_bundle(
    *,
    root: Path,
    python_command: str,
    checker: str,
    checker_commit: str,
    attestation_date: str,
    environment: dict[str, str],
    runner=run_command,
) -> list[str]:
    proof_directory = root / PROOF_DIRECTORY
    proof_index = root / PROOF_INDEX
    attestation = root / REPLAY_ATTESTATION
    promotion_journal = root / PROMOTION_JOURNAL
    actions = certification_actions(
        proof_directory=proof_directory,
        proof_index=proof_index,
        attestation=attestation,
        promotion_journal=promotion_journal,
    )
    base_command = proof_command(
        python_command=python_command,
        checker=checker,
        checker_commit=checker_commit,
    )
    if "create" in actions:
        runner(base_command, environment=environment, root=root)
    if not (
        proof_directory.is_dir()
        and not proof_directory.is_symlink()
        and proof_index.is_file()
        and not proof_index.is_symlink()
    ):
        raise RuntimeError("proof bundle creation did not complete")
    if "attest" in actions:
        runner(
            [
                *base_command,
                "--verify-existing",
                "--attestation-output",
                str(REPLAY_ATTESTATION),
                "--attestation-date",
                attestation_date,
            ],
            environment=environment,
            root=root,
        )
    if not attestation.is_file() or attestation.is_symlink():
        raise RuntimeError("proof replay attestation is missing")
    validate_retained_arguments(
        root=root,
        checker=checker,
        checker_commit=checker_commit,
        attestation_date=attestation_date,
    )
    runner(
        audit_command(python_command=python_command),
        environment=environment,
        root=root,
    )
    return actions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    parser.add_argument("--checker", required=True)
    parser.add_argument("--checker-commit", required=True)
    parser.add_argument("--attestation-date", required=True)
    args = parser.parse_args()

    root = repository_root()
    repository_lock = acquire_repository_lock(root)
    atexit.register(repository_lock.close)
    certify_bundle(
        root=root,
        python_command=args.python,
        checker=args.checker,
        checker_commit=args.checker_commit,
        attestation_date=args.attestation_date,
        environment=dict(os.environ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
