#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def run(arguments: list[str]) -> str:
    result = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
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

    output = args.output
    if output.exists() and not (output / ".git").is_dir():
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
            ]
        )

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
        ]
    )
    run(
        [
            "git",
            "-C",
            str(output),
            "checkout",
            "--detach",
            args.commit,
        ]
    )
    checked_out = run(
        ["git", "-C", str(output), "rev-parse", "HEAD"]
    )
    if checked_out != args.commit:
        raise RuntimeError("drat-trim checkout does not match pinned commit")
    run(["make", "-C", str(output), "drat-trim"])
    binary = output / "drat-trim"
    if not binary.is_file():
        raise RuntimeError("drat-trim build did not produce the checker")

    print(
        json.dumps(
            {
                "binary": str(binary),
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
