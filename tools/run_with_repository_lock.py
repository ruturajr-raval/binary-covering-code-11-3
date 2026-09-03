#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

from repository_lock import (
    acquire_repository_lock,
    subprocess_lock_kwargs,
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise SystemExit("a command is required after --")
    root = repository_root()
    lock = acquire_repository_lock(root)
    try:
        return subprocess.run(
            command,
            check=False,
            cwd=root,
            **subprocess_lock_kwargs(),
        ).returncode
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
