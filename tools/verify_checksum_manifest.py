#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat

from repository_lock import acquire_repository_lock


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def normalize_relative(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or str(path) != value
    ):
        raise SystemExit(f"manifest path is not canonical: {value}")
    return value


def repository_path(value: str, root: Path) -> Path:
    relative = normalize_relative(value)
    path = root.joinpath(*PurePosixPath(relative).parts)
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise SystemExit(f"path contains a symbolic link: {relative}")
    return path


def require_regular_single_link(path: Path, description: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise SystemExit(f"{description} is missing: {path}") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise SystemExit(
            f"{description} is not a single-link regular file: {path}"
        )
    return metadata


def file_sha256(path: Path) -> str:
    before = require_regular_single_link(path, "manifest artifact")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    after = require_regular_single_link(path, "manifest artifact")
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after:
        raise SystemExit(f"manifest artifact changed while hashing: {path}")
    return digest


def load_manifest(path: Path, root: Path) -> dict[str, str]:
    require_regular_single_link(path, "checksum manifest")
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise SystemExit("checksum manifest is not ASCII") from exc
    if not lines:
        raise SystemExit("checksum manifest is empty")
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
            raise SystemExit(
                f"checksum manifest line {line_number} is malformed"
            )
        relative = normalize_relative(line[66:])
        if relative in entries:
            raise SystemExit(
                f"checksum manifest contains duplicate path: {relative}"
            )
        repository_path(relative, root)
        entries[relative] = line[:64]
    return entries


def tree_files(relative: str, root: Path) -> set[str]:
    directory = repository_path(relative, root)
    try:
        metadata = directory.lstat()
    except FileNotFoundError as exc:
        raise SystemExit(f"manifest tree is missing: {relative}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise SystemExit(f"manifest tree is not a directory: {relative}")
    files: set[str] = set()
    for current, directory_names, file_names in os.walk(
        directory,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current)
        retained_directories = []
        for name in directory_names:
            path = current_path / name
            if path.is_symlink():
                raise SystemExit(
                    "manifest tree contains a symbolic-link directory: "
                    + str(path.relative_to(root))
                )
            retained_directories.append(name)
        directory_names[:] = retained_directories
        for name in file_names:
            path = current_path / name
            require_regular_single_link(path, "manifest tree artifact")
            files.add(path.relative_to(root).as_posix())
    return files


def expected_membership(
    declared_paths: list[str],
    declared_trees: list[str],
    root: Path,
) -> set[str]:
    expected = {
        normalize_relative(relative)
        for relative in declared_paths
    }
    for relative in declared_trees:
        expected.update(tree_files(normalize_relative(relative), root))
    return expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--tree", action="append", default=[])
    args = parser.parse_args()

    if not args.path and not args.tree:
        raise SystemExit("at least one --path or --tree declaration is required")
    root = repository_root()
    repository_lock = acquire_repository_lock(root)
    atexit.register(repository_lock.close)
    manifest_path = repository_path(args.manifest, root)
    manifest_before = require_regular_single_link(
        manifest_path,
        "checksum manifest",
    )
    entries = load_manifest(manifest_path, root)
    expected = expected_membership(args.path, args.tree, root)
    if set(entries) != expected:
        missing = sorted(expected - set(entries))
        extra = sorted(set(entries) - expected)
        raise SystemExit(
            "checksum manifest membership is incorrect; "
            f"missing={missing}, extra={extra}"
        )
    observed = {}
    for relative, expected_digest in entries.items():
        observed_digest = file_sha256(repository_path(relative, root))
        if observed_digest != expected_digest:
            raise SystemExit(f"checksum mismatch: {relative}")
        observed[relative] = observed_digest
    final_expected = expected_membership(args.path, args.tree, root)
    if final_expected != expected:
        raise SystemExit(
            "checksum manifest membership changed during verification"
        )
    final_observed = {
        relative: file_sha256(repository_path(relative, root))
        for relative in entries
    }
    if final_observed != observed:
        raise SystemExit(
            "checksum manifest artifacts changed during verification"
        )
    manifest_after = require_regular_single_link(
        manifest_path,
        "checksum manifest",
    )
    if (
        manifest_before.st_dev,
        manifest_before.st_ino,
        manifest_before.st_size,
        manifest_before.st_mtime_ns,
    ) != (
        manifest_after.st_dev,
        manifest_after.st_ino,
        manifest_after.st_size,
        manifest_after.st_mtime_ns,
    ):
        raise SystemExit("checksum manifest changed during verification")
    print(
        json.dumps(
            {
                "artifact_count": len(entries),
                "manifest": args.manifest,
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
