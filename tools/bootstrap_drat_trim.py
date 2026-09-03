#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

from repository_lock import (
    acquire_repository_lock,
    subprocess_lock_kwargs,
)


GENERATED_ARTIFACTS = {
    "compress",
    "decompress",
    "drat-trim",
    "gapless",
    "lrat-check",
}


def secure_git_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for key in list(environment):
        if key.startswith("GIT_"):
            del environment[key]
    environment["GIT_ATTR_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_COUNT"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_CONFIG_KEY_0"] = "core.hooksPath"
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_SYSTEM"] = os.devnull
    environment["GIT_CONFIG_VALUE_0"] = os.devnull
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment


def run(
    arguments: list[str],
    *,
    environment: dict[str, str] | None = None,
) -> str:
    result = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        **subprocess_lock_kwargs(environment),
    )
    if result.returncode != 0:
        raise RuntimeError(
            "command failed:\n"
            + " ".join(arguments)
            + "\n"
            + result.stdout
            + result.stderr
        )
    return result.stdout.strip()


def run_bytes(
    arguments: list[str],
    *,
    environment: dict[str, str] | None = None,
) -> bytes:
    result = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        env=environment,
        **subprocess_lock_kwargs(environment),
    )
    if result.returncode != 0:
        raise RuntimeError(
            "command failed:\n"
            + " ".join(arguments)
            + "\n"
            + result.stdout.decode("utf-8", errors="replace")
            + result.stderr.decode("utf-8", errors="replace")
        )
    return result.stdout


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


def git_status(checkout: Path) -> list[str]:
    status = run(
        [
            "git",
            "-C",
            str(checkout),
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        environment=secure_git_environment(),
    )
    return status.splitlines() if status else []


def validate_clean_checkout(checkout: Path) -> None:
    status = git_status(checkout)
    if status:
        raise RuntimeError(
            "drat-trim checkout is not clean:\n" + "\n".join(status)
        )


def git_bytes(checkout: Path, arguments: list[str]) -> bytes:
    return run_bytes(
        ["git", "-C", str(checkout), *arguments],
        environment=secure_git_environment(),
    )


def git_text(checkout: Path, arguments: list[str]) -> str:
    return git_bytes(checkout, arguments).decode("utf-8").strip()


def parse_tree(checkout: Path, commit: str) -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    payload = git_bytes(
        checkout,
        ["ls-tree", "-r", "-z", "--full-tree", commit],
    )
    for raw_entry in payload.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_name = raw_entry.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if object_type != "blob" or mode not in {"100644", "100755"}:
            raise RuntimeError(
                f"drat-trim commit contains unsupported entry: {name}"
            )
        if name in entries:
            raise RuntimeError(
                f"drat-trim commit contains duplicate path: {name}"
            )
        entries[name] = (mode, object_id)
    if not entries:
        raise RuntimeError("drat-trim commit tree is empty")
    return entries


def parse_index(checkout: Path) -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    payload = git_bytes(checkout, ["ls-files", "--stage", "-z"])
    for raw_entry in payload.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_name = raw_entry.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if stage != "0" or name in entries:
            raise RuntimeError("drat-trim index is not a simple stage-0 tree")
        entries[name] = (mode, object_id)
    return entries


def validate_index_flags(checkout: Path, expected: set[str]) -> None:
    observed: set[str] = set()
    payload = git_bytes(checkout, ["ls-files", "-v", "-z"])
    for raw_entry in payload.split(b"\0"):
        if not raw_entry:
            continue
        if len(raw_entry) < 3 or raw_entry[1:2] != b" ":
            raise RuntimeError("drat-trim index flag output is malformed")
        tag = raw_entry[:1].decode("ascii")
        name = raw_entry[2:].decode("utf-8")
        if tag != "H":
            raise RuntimeError(
                f"drat-trim index has hidden state for {name}: {tag}"
            )
        observed.add(name)
    if observed != expected:
        raise RuntimeError("drat-trim index flag paths do not match HEAD")


def validate_no_filters(checkout: Path, names: list[str]) -> None:
    payload = git_bytes(
        checkout,
        ["check-attr", "-z", "filter", "--", *names],
    )
    fields = payload.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) != 3 * len(names):
        raise RuntimeError("drat-trim filter attribute output is malformed")
    for index in range(0, len(fields), 3):
        name = fields[index].decode("utf-8")
        attribute = fields[index + 1].decode("ascii")
        value = fields[index + 2].decode("utf-8")
        if attribute != "filter" or value != "unspecified":
            raise RuntimeError(
                f"drat-trim source filter is configured for {name}"
            )


def validate_no_replacements(checkout: Path) -> None:
    replacements = git_text(
        checkout,
        ["for-each-ref", "--format=%(refname)", "refs/replace/"],
    )
    if replacements:
        raise RuntimeError("drat-trim checkout contains replacement refs")
    grafts = checkout / ".git/info/grafts"
    if grafts.exists() or grafts.is_symlink():
        raise RuntimeError("drat-trim checkout contains a grafts file")


def validate_checkout_control_plane(
    checkout: Path,
    *,
    expected_repository: str | None = None,
) -> None:
    config_path = checkout / ".git/config"
    metadata = config_path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise RuntimeError("drat-trim local Git config is invalid")
    entries: dict[str, list[str]] = {}
    payload = git_bytes(checkout, ["config", "--local", "--null", "--list"])
    for raw_entry in payload.split(b"\0"):
        if not raw_entry:
            continue
        raw_key, raw_value = raw_entry.split(b"\n", 1)
        key = raw_key.decode("utf-8").lower()
        value = raw_value.decode("utf-8")
        allowed = key in {
            "core.bare",
            "core.filemode",
            "core.ignorecase",
            "core.logallrefupdates",
            "core.precomposeunicode",
            "core.repositoryformatversion",
            "remote.origin.fetch",
            "remote.origin.partialclonefilter",
            "remote.origin.promisor",
            "remote.origin.url",
        } or (
            key.startswith("branch.")
            and key.endswith((".merge", ".remote"))
        )
        if not allowed:
            raise RuntimeError(
                f"drat-trim local Git config is not allowed: {key}"
            )
        entries.setdefault(key, []).append(value)
    if entries.get("core.bare") != ["false"]:
        raise RuntimeError("drat-trim checkout is unexpectedly bare")
    if expected_repository is not None and entries.get(
        "remote.origin.url"
    ) != [expected_repository]:
        raise RuntimeError("drat-trim origin URL is incorrect")
    info = checkout / ".git/info"
    for name in ("attributes", "grafts"):
        path = info / name
        if path.exists() or path.is_symlink():
            raise RuntimeError(
                f"drat-trim Git control file is not allowed: {name}"
            )


def worktree_files(checkout: Path) -> set[str]:
    files: set[str] = set()
    for directory, directory_names, file_names in os.walk(
        checkout,
        topdown=True,
        followlinks=False,
    ):
        directory_path = Path(directory)
        retained_directories = []
        for name in directory_names:
            path = directory_path / name
            if path == checkout / ".git":
                continue
            if path.is_symlink():
                raise RuntimeError(
                    f"drat-trim worktree contains a symlink: "
                    f"{path.relative_to(checkout)}"
                )
            retained_directories.append(name)
        directory_names[:] = retained_directories
        for name in file_names:
            path = directory_path / name
            relative = str(path.relative_to(checkout))
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError(
                    f"drat-trim worktree contains a non-regular file: "
                    f"{relative}"
                )
            if metadata.st_nlink != 1:
                raise RuntimeError(
                    f"drat-trim worktree file has multiple links: {relative}"
                )
            files.add(relative)
    return files


def validate_pinned_checkout(
    checkout: Path,
    commit: str,
    *,
    allowed_untracked: set[str] | None = None,
) -> None:
    allowed = set() if allowed_untracked is None else set(allowed_untracked)
    git_directory = checkout / ".git"
    if (
        not checkout.is_dir()
        or checkout.is_symlink()
        or not git_directory.is_dir()
        or git_directory.is_symlink()
    ):
        raise RuntimeError("drat-trim checkout structure is invalid")
    top_level = Path(
        git_text(checkout, ["rev-parse", "--show-toplevel"])
    ).resolve()
    if top_level != checkout.resolve():
        raise RuntimeError("drat-trim checkout top level is incorrect")
    validate_checkout_control_plane(checkout)
    validate_no_replacements(checkout)
    head = git_text(checkout, ["rev-parse", "--verify", "HEAD^{commit}"])
    if head != commit:
        raise RuntimeError("drat-trim checkout does not match pinned commit")
    tree = parse_tree(checkout, commit)
    index = parse_index(checkout)
    if index != tree:
        raise RuntimeError("drat-trim index does not match pinned commit")
    validate_index_flags(checkout, set(tree))
    validate_no_filters(checkout, sorted(tree))
    actual_files = worktree_files(checkout)
    for name, (mode, object_id) in tree.items():
        path = checkout / name
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(
                f"drat-trim tracked source is not a regular file: {name}"
            )
        if metadata.st_nlink != 1:
            raise RuntimeError(
                f"drat-trim tracked source has multiple links: {name}"
            )
        expected_executable = mode == "100755"
        observed_executable = bool(metadata.st_mode & stat.S_IXUSR)
        if observed_executable != expected_executable:
            raise RuntimeError(
                f"drat-trim tracked source mode changed: {name}"
            )
        expected_bytes = git_bytes(
            checkout,
            ["cat-file", "blob", object_id],
        )
        if path.read_bytes() != expected_bytes:
            raise RuntimeError(
                f"drat-trim tracked source bytes changed: {name}"
            )
    expected_files = set(tree) | allowed
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        extra = sorted(actual_files - expected_files)
        raise RuntimeError(
            "drat-trim worktree file set is incorrect; "
            f"missing={missing}, extra={extra}"
        )


def validate_tracked_sources(checkout: Path) -> None:
    commit = git_text(
        checkout,
        ["rev-parse", "--verify", "HEAD^{commit}"],
    )
    validate_pinned_checkout(checkout, commit)


def remove_generated_artifacts(checkout: Path) -> None:
    for name in sorted(GENERATED_ARTIFACTS):
        path = checkout / name
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_dir() and not path.is_symlink():
            raise RuntimeError(
                f"drat-trim generated path is a directory: {name}"
            )
        path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository",
        default="https://github.com/marijnheule/drat-trim.git",
    )
    parser.add_argument(
        "--commit",
        default="2e3b2dc0ecf938addbd779d42877b6ed69d9a985",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/drat-trim-src"),
    )
    args = parser.parse_args()

    root = repository_root()
    repository_lock = acquire_repository_lock(root)
    atexit.register(repository_lock.close)
    output = repository_path(args.output, root)
    git_directory = output / ".git"
    if output.exists() and (
        not output.is_dir()
        or output.is_symlink()
        or not git_directory.is_dir()
        or git_directory.is_symlink()
    ):
        raise SystemExit(f"{output} exists but is not a Git checkout")
    if not output.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                args.repository,
                str(output),
            ],
            environment=secure_git_environment(),
        )

    validate_checkout_control_plane(
        output,
        expected_repository=args.repository,
    )
    validate_no_replacements(output)
    run(
        [
            "git",
            "-C",
            str(output),
            "fetch",
            "--depth",
            "1",
            "origin",
            args.commit,
        ],
        environment=secure_git_environment(),
    )
    validate_checkout_control_plane(
        output,
        expected_repository=args.repository,
    )
    validate_no_replacements(output)
    run(
        [
            "git",
            "-C",
            str(output),
            "checkout",
            "--detach",
            args.commit,
        ],
        environment=secure_git_environment(),
    )
    checked_out = git_text(
        output,
        ["rev-parse", "--verify", "HEAD^{commit}"],
    )
    if checked_out != args.commit:
        raise RuntimeError("drat-trim checkout does not match pinned commit")
    remove_generated_artifacts(output)
    validate_pinned_checkout(output, args.commit)
    binary = output / "drat-trim"
    run(["make", "-C", str(output), "drat-trim"])
    if (
        not binary.is_file()
        or binary.is_symlink()
        or binary.stat().st_nlink != 1
    ):
        raise RuntimeError("drat-trim build did not produce the checker")
    validate_pinned_checkout(
        output,
        args.commit,
        allowed_untracked={"drat-trim"},
    )
    binary_sha256 = hashlib.sha256(binary.read_bytes()).hexdigest()

    print(
        json.dumps(
            {
                "binary": str(binary),
                "binary_sha256": binary_sha256,
                "commit": checked_out,
                "repository": args.repository,
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
