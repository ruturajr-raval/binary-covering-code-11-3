#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import lzma
import re
import subprocess
import tempfile
from pathlib import Path

from repository_lock import subprocess_lock_kwargs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checker", type=Path)
    parser.add_argument("formula", type=Path)
    parser.add_argument("proof", type=Path)
    parser.add_argument("proof_summary", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--checker-commit", required=True)
    args = parser.parse_args()

    summary = json.loads(
        args.proof_summary.read_text(encoding="ascii")
    )
    formula_sha256 = hashlib.sha256(
        args.formula.read_bytes()
    ).hexdigest()
    proof_compressed = args.proof.read_bytes()
    proof_compressed_sha256 = hashlib.sha256(
        proof_compressed
    ).hexdigest()
    if args.proof.suffix == ".xz":
        proof_bytes = lzma.decompress(
            proof_compressed,
            format=lzma.FORMAT_XZ,
        )
    elif args.proof.suffix == ".gz":
        proof_bytes = gzip.decompress(proof_compressed)
    else:
        raise SystemExit("proof file must end in .gz or .xz")
    proof_sha256 = hashlib.sha256(proof_bytes).hexdigest()
    if formula_sha256 != summary["case_formula_sha256"]:
        raise SystemExit("formula hash does not match proof summary")
    if proof_compressed_sha256 != summary["proof_compressed_sha256"]:
        raise SystemExit("compressed proof hash does not match summary")
    if proof_sha256 != summary["proof_uncompressed_sha256"]:
        raise SystemExit("proof hash does not match summary")

    with tempfile.TemporaryDirectory() as directory:
        proof_path = Path(directory) / "proof.drat"
        proof_path.write_bytes(proof_bytes)
        result = subprocess.run(
            [
                str(args.checker.resolve()),
                str(args.formula.resolve()),
                str(proof_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            **subprocess_lock_kwargs(),
        )
    combined_output = result.stdout + result.stderr
    verified = result.returncode == 0 and "VERIFIED" in combined_output
    if not verified:
        raise SystemExit(
            "drat-trim did not verify the retained proof:\n"
            + combined_output
        )

    output_lines = combined_output.splitlines()
    retained_lines = []
    for line in output_lines:
        if not line.strip() or "WARNING:" in line:
            continue
        retained_lines.append(
            re.sub(
                r"^(c verification time:) [0-9.]+ seconds$",
                r"\1 <elapsed>",
                line,
            )
        )
    stable_output = "\n".join(retained_lines) + "\n"
    report = {
        "case_id": summary["case_id"],
        "checker": "drat-trim",
        "checker_commit": args.checker_commit,
        "formula_sha256": formula_sha256,
        "proof_compressed_sha256": proof_compressed_sha256,
        "proof_uncompressed_sha256": proof_sha256,
        "return_code": result.returncode,
        "verified": True,
        "checker_output_sha256": hashlib.sha256(
            stable_output.encode("utf-8")
        ).hexdigest(),
        "checker_output_line_count": len(output_lines),
        "checker_warning_count": sum(
            "WARNING:" in line for line in output_lines
        ),
        "checker_timing_normalized": True,
        "checker_output": retained_lines,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
