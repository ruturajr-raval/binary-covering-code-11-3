#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def isolate_python_bytecode() -> None:
    if sys.flags.isolated != 1:
        raise RuntimeError(
            "certification CLI requires Python isolated mode (-I)"
        )
    root = Path(__file__).resolve().parents[2]
    work = root / "proof-expansion/work"
    if work.is_symlink():
        raise RuntimeError("proof-expansion work path is a symbolic link")
    work.mkdir(parents=True, exist_ok=True)
    cache_parent = work / "python-bytecode"
    if cache_parent.is_symlink():
        raise RuntimeError("Python bytecode cache path is a symbolic link")
    cache_parent.mkdir(exist_ok=True)
    cache = Path(
        tempfile.mkdtemp(dir=cache_parent, prefix=".run.")
    )
    os.environ["PYTHONPYCACHEPREFIX"] = str(cache)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.pycache_prefix = str(cache)
    sys.dont_write_bytecode = True
    sys.path[:0] = [
        str(root / "proof-expansion/src"),
        str(root / "src"),
        str(root / "tools"),
    ]
    atexit.register(shutil.rmtree, cache, ignore_errors=True)


isolate_python_bytecode()

from fourth_word_drat.proof_core import (
    DEFAULT_MAX_MEMORY_BYTES,
    DEFAULT_MAX_RAW_PROOF_BYTES,
    DEFAULT_MAX_RETAINED_PROOF_BYTES,
    DEFAULT_MAX_SOLVE_SECONDS,
    build_proof,
    verify_existing,
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("formula", type=Path)
    parser.add_argument("proof_output", type=Path)
    parser.add_argument("summary_output", type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--solver", default="glucose4")
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--checker-commit", required=True)
    parser.add_argument("--scratch-directory", type=Path)
    parser.add_argument(
        "--max-solve-seconds",
        type=int,
        default=DEFAULT_MAX_SOLVE_SECONDS,
    )
    parser.add_argument(
        "--max-raw-proof-bytes",
        type=int,
        default=DEFAULT_MAX_RAW_PROOF_BYTES,
    )
    parser.add_argument(
        "--max-retained-proof-bytes",
        type=int,
        default=DEFAULT_MAX_RETAINED_PROOF_BYTES,
    )
    parser.add_argument(
        "--max-memory-bytes",
        type=int,
        default=DEFAULT_MAX_MEMORY_BYTES,
    )
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()

    root = repository_root()
    if args.verify_existing:
        if args.scratch_directory is None:
            raise SystemExit(
                "--scratch-directory is required with --verify-existing"
            )
        report = verify_existing(
            args.formula,
            args.proof_output,
            args.summary_output,
            case_id=args.case_id,
            checker_path=args.checker,
            checker_commit=args.checker_commit,
            root=root,
            scratch_directory=args.scratch_directory,
            max_solve_seconds=args.max_solve_seconds,
            max_raw_proof_bytes=args.max_raw_proof_bytes,
            max_retained_proof_bytes=args.max_retained_proof_bytes,
            max_memory_bytes=args.max_memory_bytes,
        )
    else:
        if args.scratch_directory is not None:
            raise SystemExit(
                "--scratch-directory requires --verify-existing"
            )
        report = build_proof(
            args.formula,
            args.proof_output,
            args.summary_output,
            case_id=args.case_id,
            solver_name=args.solver,
            checker_path=args.checker,
            checker_commit=args.checker_commit,
            root=root,
            max_solve_seconds=args.max_solve_seconds,
            max_raw_proof_bytes=args.max_raw_proof_bytes,
            max_retained_proof_bytes=args.max_retained_proof_bytes,
            max_memory_bytes=args.max_memory_bytes,
        )
    print(
        json.dumps(
            {
                "case_id": args.case_id,
                "formula_sha256": report.get(
                    "case_formula_sha256",
                    report.get("formula_sha256"),
                ),
                "verified": (
                    report.get("verified") is True
                    or report.get("retained_replay", {}).get("verified")
                    is True
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
