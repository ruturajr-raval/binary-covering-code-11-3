#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from audit_covering_cnf import read_dimacs
from run_two_word_portfolio import case_units, unit_digest


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dimacs_text(
    variable_count: int,
    clauses: list[tuple[int, ...]],
) -> str:
    lines = [f"p cnf {variable_count} {len(clauses)}"]
    lines.extend(
        " ".join(str(literal) for literal in clause) + " 0"
        for clause in clauses
    )
    return "\n".join(lines) + "\n"


def run_command(arguments: list[str], *, environment: dict[str, str]) -> None:
    result = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "proof command failed:\n"
            + " ".join(arguments)
            + "\n"
            + result.stdout
            + result.stderr
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("formula_directory", type=Path)
    parser.add_argument("proof_directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--checker-commit", required=True)
    parser.add_argument("--solver", default="cadical300")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="ascii"))
    branch_manifest_path = Path(plan["branch_manifest"])
    case_manifest_path = Path(plan["case_manifest"])
    branch_manifest = json.loads(
        branch_manifest_path.read_text(encoding="ascii")
    )
    case_manifest = json.loads(
        case_manifest_path.read_text(encoding="ascii")
    )
    branches = {
        int(case["minimum_distance"]): Path(case["formula"])
        for case in branch_manifest["cases"]
    }
    two_word_cases = {
        case["case_id"]: case
        for case in case_manifest["cases"]
    }
    case_ids = [case["case_id"] for case in plan["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise SystemExit("proof plan contains duplicate case identifiers")

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
        minimum_distance = int(planned["minimum_distance"])
        solver = planned.get("solver", args.solver)
        case = two_word_cases.get(case_id)
        if case is None:
            raise SystemExit(f"proof plan contains unknown case {case_id}")
        if int(case["minimum_weight"]) != minimum_distance:
            raise SystemExit(
                f"{case_id}: branch distance and case weight differ"
            )
        base_formula = branches.get(minimum_distance)
        if base_formula is None:
            raise SystemExit(
                f"{case_id}: no formula for distance {minimum_distance}"
            )

        formula = args.formula_directory / f"{case_id}.cnf"
        proof = args.proof_directory / f"{case_id}.drat.gz"
        summary = args.proof_directory / f"{case_id}-proof.json"
        check = args.proof_directory / f"{case_id}-check.json"
        if args.verify_existing:
            base_variables, base_clauses, _ = read_dimacs(base_formula)
            units = case_units(case, int(case_manifest["length"]))
            expected_clauses = list(base_clauses)
            expected_clauses.extend((literal,) for literal in units)
            formula.parent.mkdir(parents=True, exist_ok=True)
            formula.write_text(
                dimacs_text(base_variables, expected_clauses),
                encoding="ascii",
            )
        else:
            run_command(
                [
                    args.python,
                    "tools/prove_two_word_case.py",
                    str(base_formula),
                    str(case_manifest_path),
                    case_id,
                    str(formula),
                    str(proof),
                    str(summary),
                    "--solver",
                    solver,
                ],
                environment=environment,
            )

        base_variables, base_clauses, base_sha256 = read_dimacs(
            base_formula
        )
        formula_variables, formula_clauses, formula_sha256 = read_dimacs(
            formula
        )
        units = case_units(case, int(case_manifest["length"]))
        if len(units) != case["unit_count"]:
            raise RuntimeError(f"{case_id}: unit count mismatch")
        if unit_digest(units) != case["unit_sha256"]:
            raise RuntimeError(f"{case_id}: unit hash mismatch")
        expected_clauses = list(base_clauses)
        expected_clauses.extend((literal,) for literal in units)
        if formula_variables != base_variables:
            raise RuntimeError(f"{case_id}: formula variable count changed")
        if formula_clauses != expected_clauses:
            raise RuntimeError(f"{case_id}: formula reconstruction failed")

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
            environment=environment,
        )

        proof_summary = json.loads(summary.read_text(encoding="ascii"))
        check_report = json.loads(check.read_text(encoding="ascii"))
        if proof_summary["solver"] != solver:
            raise RuntimeError(f"{case_id}: solver does not match the plan")
        if proof_summary["base_formula_sha256"] != base_sha256:
            raise RuntimeError(f"{case_id}: base formula hash mismatch")
        if proof_summary["case_formula_sha256"] != formula_sha256:
            raise RuntimeError(f"{case_id}: case formula hash mismatch")
        if proof_summary["proof_compressed_sha256"] != file_sha256(proof):
            raise RuntimeError(f"{case_id}: proof hash mismatch")
        if not check_report["verified"]:
            raise RuntimeError(f"{case_id}: proof check is not verified")
        records.append(
            {
                "case_id": case_id,
                "minimum_distance": minimum_distance,
                "solver": solver,
                "base_formula_sha256": base_sha256,
                "formula": str(formula),
                "case_formula_sha256": formula_sha256,
                "proof": str(proof),
                "proof_sha256": file_sha256(proof),
                "proof_summary": str(summary),
                "proof_summary_sha256": file_sha256(summary),
                "proof_check": str(check),
                "proof_check_sha256": file_sha256(check),
                "proof_lines": proof_summary["proof_lines"],
                "proof_compressed_bytes": proof_summary[
                    "proof_compressed_bytes"
                ],
                "solve_seconds": proof_summary["solve_seconds"],
                "verified": True,
            }
        )
        print(f"[{index}/{len(plan['cases'])}] verified {case_id}")

    report = {
        "proof_plan": str(args.plan),
        "proof_plan_sha256": file_sha256(args.plan),
        "branch_manifest": str(branch_manifest_path),
        "branch_manifest_sha256": file_sha256(branch_manifest_path),
        "case_manifest": str(case_manifest_path),
        "case_manifest_sha256": file_sha256(case_manifest_path),
        "solver": args.solver,
        "checker": "drat-trim",
        "checker_commit": args.checker_commit,
        "proofs_regenerated": not args.verify_existing,
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
