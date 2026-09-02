#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="ascii"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("two_word_cases", type=Path)
    parser.add_argument("orbit_certificates", type=Path)
    parser.add_argument("integer_certificates", type=Path)
    parser.add_argument("distance_bounds", type=Path)
    parser.add_argument("residual_proof_check", type=Path)
    parser.add_argument("minimum_distance_proofs", type=Path)
    parser.add_argument("summary_output", type=Path)
    parser.add_argument("residual_output", type=Path)
    args = parser.parse_args()

    manifest = load_json(args.two_word_cases)
    cases = manifest["cases"]
    case_by_id = {case["case_id"]: case for case in cases}
    if len(case_by_id) != len(cases):
        raise SystemExit("two-word manifest contains duplicate case ids")
    all_case_ids = set(case_by_id)

    orbit = load_json(args.orbit_certificates)
    orbit_status = {
        item["case_id"]: item["status"]
        for item in orbit["certificates"]
    }
    if set(orbit_status) != all_case_ids:
        raise SystemExit("orbit certificates do not cover every case")
    if set(orbit_status.values()) != {"LP_FEASIBLE", "LP_INFEASIBLE"}:
        raise SystemExit("orbit certificates contain an unknown status")

    integer = load_json(args.integer_certificates)
    integer_status = {
        item["case_id"]: item["status"]
        for item in integer["certificates"]
    }
    lp_feasible = {
        case_id
        for case_id, status in orbit_status.items()
        if status == "LP_FEASIBLE"
    }
    if set(integer_status) != lp_feasible:
        raise SystemExit(
            "integer certificates do not exactly cover LP-feasible cases"
        )
    if set(integer_status.values()) != {
        "INTEGER_FEASIBLE",
        "INTEGER_INFEASIBLE",
    }:
        raise SystemExit("integer certificates contain an unknown status")

    distance = load_json(args.distance_bounds)
    maximum_minimum_distance = int(
        distance["conclusions"]["minimum_pair_distance_at_most"]
    )
    if maximum_minimum_distance != 5 or not distance["valid"]:
        raise SystemExit("distance evidence does not certify distance at most 5")

    residual_check = load_json(args.residual_proof_check)
    if not residual_check["verified"]:
        raise SystemExit("retained residual-case proof is not verified")
    original_drat_case = residual_check["case_id"]
    if original_drat_case not in all_case_ids:
        raise SystemExit("retained residual proof names an unknown case")

    proof_index = load_json(args.minimum_distance_proofs)
    if not proof_index["all_verified"]:
        raise SystemExit("minimum-distance proof index is not fully verified")
    proof_cases = {
        record["case_id"]: record
        for record in proof_index["cases"]
    }
    if len(proof_cases) != proof_index["case_count"]:
        raise SystemExit("minimum-distance proof index has duplicate cases")
    for case_id, record in proof_cases.items():
        case = case_by_id.get(case_id)
        if case is None:
            raise SystemExit(f"proof index contains unknown case {case_id}")
        if int(case["minimum_weight"]) != int(record["minimum_distance"]):
            raise SystemExit(f"{case_id}: proof branch has the wrong distance")
        proof = Path(record["proof"])
        summary = Path(record["proof_summary"])
        check = Path(record["proof_check"])
        if file_sha256(proof) != record["proof_sha256"]:
            raise SystemExit(f"{case_id}: proof hash mismatch")
        if file_sha256(summary) != record["proof_summary_sha256"]:
            raise SystemExit(f"{case_id}: proof-summary hash mismatch")
        if file_sha256(check) != record["proof_check_sha256"]:
            raise SystemExit(f"{case_id}: proof-check hash mismatch")
        if not load_json(check)["verified"]:
            raise SystemExit(f"{case_id}: proof-check file is not verified")

    classifications: dict[str, list[str]] = {
        "orbit_lp_infeasible": [],
        "integer_profile_infeasible": [],
        "standalone_drat": [],
        "minimum_distance_at_most_5": [],
        "closest_pair_drat": [],
        "open": [],
    }
    for case in cases:
        case_id = case["case_id"]
        minimum_weight = int(case["minimum_weight"])
        if orbit_status[case_id] == "LP_INFEASIBLE":
            reason = "orbit_lp_infeasible"
        elif integer_status[case_id] == "INTEGER_INFEASIBLE":
            reason = "integer_profile_infeasible"
        elif case_id == original_drat_case:
            reason = "standalone_drat"
        elif minimum_weight > maximum_minimum_distance:
            reason = "minimum_distance_at_most_5"
        elif case_id in proof_cases:
            reason = "closest_pair_drat"
        else:
            reason = "open"
        classifications[reason].append(case_id)

    counts = {
        reason: len(case_ids)
        for reason, case_ids in classifications.items()
    }
    expected_counts = {
        "orbit_lp_infeasible": 80,
        "integer_profile_infeasible": 2,
        "standalone_drat": 1,
        "minimum_distance_at_most_5": 4,
        "closest_pair_drat": 14,
        "open": 49,
    }
    if counts != expected_counts:
        raise SystemExit(
            f"case-reduction counts changed: {counts} != {expected_counts}"
        )
    if sum(counts.values()) != len(cases):
        raise SystemExit("case classification is incomplete")

    open_ids = set(classifications["open"])
    residual_cases = [
        case for case in cases if case["case_id"] in open_ids
    ]
    open_by_weight = Counter(
        int(case["minimum_weight"])
        for case in residual_cases
    )
    summary = {
        "problem": {
            "q": 2,
            "length": 11,
            "radius": 3,
            "target_size": 15,
        },
        "source_case_manifest": str(args.two_word_cases),
        "source_case_manifest_sha256": file_sha256(args.two_word_cases),
        "certificate_inputs": {
            "orbit_lp": {
                "path": str(args.orbit_certificates),
                "sha256": file_sha256(args.orbit_certificates),
            },
            "integer_profile": {
                "path": str(args.integer_certificates),
                "sha256": file_sha256(args.integer_certificates),
            },
            "distance_bounds": {
                "path": str(args.distance_bounds),
                "sha256": file_sha256(args.distance_bounds),
            },
            "standalone_drat_check": {
                "path": str(args.residual_proof_check),
                "sha256": file_sha256(args.residual_proof_check),
            },
            "minimum_distance_proofs": {
                "path": str(args.minimum_distance_proofs),
                "sha256": file_sha256(args.minimum_distance_proofs),
            },
        },
        "total_cases": len(cases),
        "classification_order": list(classifications),
        "counts": counts,
        "open_by_minimum_distance": {
            str(weight): open_by_weight[weight]
            for weight in sorted(open_by_weight)
        },
        "classifications": classifications,
        "proof_checker": proof_index["checker"],
        "proof_checker_commit": proof_index["checker_commit"],
        "all_accounted_for": True,
        "global_exact_value_resolved": False,
    }
    residual = {
        "length": manifest["length"],
        "maximum_minimum_weight": maximum_minimum_distance,
        "descriptor_order": manifest["descriptor_order"],
        "source_manifest": str(args.two_word_cases),
        "source_manifest_sha256": file_sha256(args.two_word_cases),
        "reduction_summary": str(args.summary_output),
        "case_count": len(residual_cases),
        "cases": residual_cases,
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    args.residual_output.parent.mkdir(parents=True, exist_ok=True)
    args.residual_output.write_text(
        json.dumps(residual, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(
        json.dumps(
            {
                "counts": counts,
                "open_by_minimum_distance": (
                    summary["open_by_minimum_distance"]
                ),
                "residual_output": str(args.residual_output),
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
