#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_command(arguments: list[str], environment: dict[str, str]) -> None:
    result = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode != 0:
        output = result.stdout + result.stderr
        raise RuntimeError(
            "command failed:\n"
            + " ".join(arguments)
            + "\n"
            + output[-8000:]
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("formula_directory", type=Path)
    parser.add_argument("proof_directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--checker-commit", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="ascii"))
    branch_manifest_path = Path(plan["branch_manifest"])
    parent_manifest_path = Path(plan["parent_manifest"])
    third_manifest_path = Path(plan["third_manifest"])
    branch_manifest = json.loads(
        branch_manifest_path.read_text(encoding="ascii")
    )
    parent_manifest = json.loads(
        parent_manifest_path.read_text(encoding="ascii")
    )
    branches = {
        int(case["minimum_distance"]): Path(case["formula"])
        for case in branch_manifest["cases"]
    }
    parent_cases = {
        case["case_id"]: case
        for case in parent_manifest["cases"]
    }
    case_ids = [case["case_id"] for case in plan["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise SystemExit("proof plan contains duplicate cases")

    args.formula_directory.mkdir(parents=True, exist_ok=True)
    args.proof_directory.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    python_path = environment.get("PYTHONPATH")
    required_path = os.pathsep.join(["src", "tools"])
    environment["PYTHONPATH"] = (
        required_path
        if not python_path
        else required_path + os.pathsep + python_path
    )

    records = []
    for index, planned in enumerate(plan["cases"], start=1):
        case_id = planned["case_id"]
        parent = parent_cases.get(case_id)
        if parent is None:
            raise SystemExit(f"proof plan contains unknown case {case_id}")
        distance = int(parent["minimum_weight"])
        solver = planned["solver"]
        compression = planned["compression"]
        matching = planned.get("matching", False)
        if not isinstance(matching, bool):
            raise SystemExit(f"{case_id}: matching must be Boolean")
        if compression not in {"gzip", "xz"}:
            raise SystemExit(f"{case_id}: unknown proof compression")
        suffix = ".drat.gz" if compression == "gzip" else ".drat.xz"
        formula = args.formula_directory / f"{case_id}.cnf"
        formula_metadata = (
            args.proof_directory / f"{case_id}-formula.json"
        )
        proof = args.proof_directory / f"{case_id}{suffix}"
        summary = args.proof_directory / f"{case_id}-proof.json"
        check = args.proof_directory / f"{case_id}-check.json"

        if not args.verify_existing:
            generate_arguments = [
                args.python,
                "tools/generate_third_word_formula.py",
                str(branches[distance]),
                str(parent_manifest_path),
                str(third_manifest_path),
                case_id,
                str(formula),
                str(formula_metadata),
            ]
            if matching:
                generate_arguments.append("--matching")
            run_command(
                generate_arguments,
                environment,
            )
        run_command(
            [
                args.python,
                "tools/audit_third_word_formula.py",
                str(formula),
                str(formula_metadata),
            ],
            environment,
        )
        if not args.verify_existing:
            run_command(
                [
                    args.python,
                    "tools/prove_cnf.py",
                    str(formula),
                    str(proof),
                    str(summary),
                    "--case-id",
                    case_id,
                    "--solver",
                    solver,
                ],
                environment,
            )
        run_command(
            [
                args.python,
                "tools/check_drat_proof.py",
                str(args.checker),
                str(formula),
                str(proof),
                str(summary),
                str(check),
                "--checker-commit",
                args.checker_commit,
            ],
            environment,
        )

        formula_record = json.loads(
            formula_metadata.read_text(encoding="ascii")
        )
        proof_record = json.loads(summary.read_text(encoding="ascii"))
        check_record = json.loads(check.read_text(encoding="ascii"))
        if proof_record["solver"] != solver:
            raise RuntimeError(f"{case_id}: solver does not match the plan")
        if (
            formula_record.get(
                "enforce_minimum_distance_matching",
                False,
            )
            != matching
        ):
            raise RuntimeError(
                f"{case_id}: matching assumption does not match the plan"
            )
        if proof_record.get("proof_compression", "gzip") != compression:
            raise RuntimeError(
                f"{case_id}: compression does not match the plan"
            )
        if proof_record["case_formula_sha256"] != file_sha256(formula):
            raise RuntimeError(f"{case_id}: formula hash mismatch")
        if proof_record["proof_compressed_sha256"] != file_sha256(proof):
            raise RuntimeError(f"{case_id}: proof hash mismatch")
        if not check_record["verified"]:
            raise RuntimeError(f"{case_id}: proof check is not verified")
        records.append(
            {
                "case_id": case_id,
                "minimum_distance": distance,
                "solver": solver,
                "proof_compression": compression,
                "enforce_minimum_distance_matching": matching,
                "formula": str(formula),
                "formula_sha256": file_sha256(formula),
                "formula_metadata": str(formula_metadata),
                "formula_metadata_sha256": file_sha256(formula_metadata),
                "proof": str(proof),
                "proof_sha256": file_sha256(proof),
                "proof_summary": str(summary),
                "proof_summary_sha256": file_sha256(summary),
                "proof_check": str(check),
                "proof_check_sha256": file_sha256(check),
                "variables": formula_record["variables"],
                "clauses": formula_record["clauses"],
                "selectors": formula_record["selector_count"],
                "proof_compressed_bytes": proof_record[
                    "proof_compressed_bytes"
                ],
                "verified": True,
            }
        )
        print(f"[{index}/{len(plan['cases'])}] verified {case_id}")

    report = {
        "proof_plan": str(args.plan),
        "proof_plan_sha256": file_sha256(args.plan),
        "branch_manifest": str(branch_manifest_path),
        "branch_manifest_sha256": file_sha256(branch_manifest_path),
        "parent_manifest": str(parent_manifest_path),
        "parent_manifest_sha256": file_sha256(parent_manifest_path),
        "third_manifest": str(third_manifest_path),
        "third_manifest_sha256": file_sha256(third_manifest_path),
        "checker": "drat-trim",
        "checker_commit": args.checker_commit,
        "case_count": len(records),
        "all_verified": all(record["verified"] for record in records),
        "cases": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(
        json.dumps(
            {
                "all_verified": report["all_verified"],
                "case_count": report["case_count"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
