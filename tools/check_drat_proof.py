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


STABLE_REPLAY_FIELDS = (
    "case_id",
    "checker",
    "checker_commit",
    "formula_sha256",
    "proof_compressed_sha256",
    "proof_uncompressed_sha256",
    "return_code",
    "verified",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checker", type=Path)
    parser.add_argument("formula", type=Path)
    parser.add_argument("proof", type=Path)
    parser.add_argument("proof_summary", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--checker-commit", required=True)
    parser.add_argument("--verify-existing", action="store_true")
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
    output_lines = combined_output.splitlines()
    verified_statuses = [
        line for line in output_lines if line.strip() == "s VERIFIED"
    ]
    verified = result.returncode == 0 and len(verified_statuses) == 1
    if not verified:
        raise SystemExit(
            "drat-trim did not verify the retained proof:\n"
            + combined_output
        )

    retained_lines = []
    normalized_timing_lines = 0
    for line in output_lines:
        if not line.strip() or "WARNING:" in line:
            continue
        normalized_line, replacements = re.subn(
            r"^(c verification time:) [0-9.]+ seconds$",
            r"\1 <elapsed>",
            line,
        )
        normalized_timing_lines += replacements
        retained_lines.append(normalized_line)
    if normalized_timing_lines != 1:
        raise SystemExit(
            "drat-trim output must contain exactly one verification-time line"
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
        "checker_timing_normalized": normalized_timing_lines == 1,
        "checker_output": retained_lines,
    }
    report_bytes = (
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    ).encode("ascii")
    if args.verify_existing:
        try:
            retained_bytes = args.output.read_bytes()
        except FileNotFoundError as exc:
            raise SystemExit(
                f"retained proof check is missing: {args.output}"
            ) from exc
        try:
            retained_report = json.loads(
                retained_bytes.decode("ascii")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemExit(
                "retained proof check is not ASCII JSON"
            ) from exc
        changed_fields = [
            key
            for key in STABLE_REPLAY_FIELDS
            if retained_report.get(key) != report.get(key)
        ]
        if changed_fields:
            raise SystemExit(
                "retained proof check does not match replay; "
                f"changed_fields={changed_fields}"
            )
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(report_bytes)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
