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


def require_file(
    record: dict[str, object],
    key: str,
    case_id: str,
) -> Path:
    path = Path(record[key])
    if not path.is_file():
        label = key.replace("_", "-")
        raise SystemExit(f"{case_id}: {label} file is missing")
    return path


def verify_third_word_proof_index(
    proof_index: dict[str, object],
    parent_manifest: Path,
) -> tuple[set[str], set[str]]:
    if not proof_index["all_verified"]:
        raise SystemExit("third-word proofs are not fully verified")
    if proof_index["checker"] != "drat-trim":
        raise SystemExit("third-word proof checker changed")
    if proof_index["parent_manifest_sha256"] != file_sha256(
        parent_manifest
    ):
        raise SystemExit("third-word proof source hash mismatch")

    for path_key, hash_key in (
        ("proof_plan", "proof_plan_sha256"),
        ("branch_manifest", "branch_manifest_sha256"),
        ("parent_manifest", "parent_manifest_sha256"),
        ("third_manifest", "third_manifest_sha256"),
    ):
        path = Path(proof_index[path_key])
        if not path.is_file():
            raise SystemExit(f"third-word {path_key} file is missing")
        if file_sha256(path) != proof_index[hash_key]:
            raise SystemExit(f"third-word {path_key} hash mismatch")

    records = proof_index["cases"]
    if len(records) != proof_index["case_count"]:
        raise SystemExit("third-word proof count is inconsistent")
    proof_ids = {record["case_id"] for record in records}
    if len(proof_ids) != len(records):
        raise SystemExit("third-word proof index has duplicate cases")

    matching_proof_ids = set()
    for record in records:
        case_id = record["case_id"]
        formula = require_file(record, "formula", case_id)
        metadata_path = require_file(record, "formula_metadata", case_id)
        proof = require_file(record, "proof", case_id)
        summary_path = require_file(record, "proof_summary", case_id)
        check_path = require_file(record, "proof_check", case_id)

        expected_hashes = (
            (formula, record["formula_sha256"], "formula"),
            (
                metadata_path,
                record["formula_metadata_sha256"],
                "formula metadata",
            ),
            (proof, record["proof_sha256"], "proof"),
            (
                summary_path,
                record["proof_summary_sha256"],
                "proof summary",
            ),
            (
                check_path,
                record["proof_check_sha256"],
                "proof check",
            ),
        )
        for path, expected, label in expected_hashes:
            if file_sha256(path) != expected:
                raise SystemExit(f"{case_id}: {label} hash mismatch")

        metadata = load_json(metadata_path)
        summary = load_json(summary_path)
        check = load_json(check_path)
        matching = bool(
            record.get("enforce_minimum_distance_matching", False)
        )
        if metadata["parent_case_id"] != case_id:
            raise SystemExit(f"{case_id}: formula metadata case mismatch")
        if metadata["formula_sha256"] != record["formula_sha256"]:
            raise SystemExit(f"{case_id}: metadata formula hash mismatch")
        if (
            metadata.get("enforce_minimum_distance_matching", False)
            != matching
        ):
            raise SystemExit(f"{case_id}: matching assumption mismatch")
        if int(metadata["minimum_distance"]) != int(
            record["minimum_distance"]
        ):
            raise SystemExit(f"{case_id}: minimum-distance mismatch")

        if summary["case_id"] != case_id:
            raise SystemExit(f"{case_id}: proof summary case mismatch")
        if summary["case_formula_sha256"] != record["formula_sha256"]:
            raise SystemExit(f"{case_id}: proof formula hash mismatch")
        if summary["proof_compressed_sha256"] != record["proof_sha256"]:
            raise SystemExit(f"{case_id}: compressed proof hash mismatch")
        if summary["solver"] != record["solver"]:
            raise SystemExit(f"{case_id}: proof solver mismatch")
        if (
            summary.get("proof_compression", "gzip")
            != record["proof_compression"]
        ):
            raise SystemExit(f"{case_id}: proof compression mismatch")

        if check["case_id"] != case_id or not check["verified"]:
            raise SystemExit(f"{case_id}: proof check is not verified")
        if check["checker"] != proof_index["checker"]:
            raise SystemExit(f"{case_id}: checker name mismatch")
        if check["checker_commit"] != proof_index["checker_commit"]:
            raise SystemExit(f"{case_id}: checker commit mismatch")
        if check["formula_sha256"] != record["formula_sha256"]:
            raise SystemExit(f"{case_id}: checked formula hash mismatch")
        if check["proof_compressed_sha256"] != record["proof_sha256"]:
            raise SystemExit(f"{case_id}: checked proof hash mismatch")
        if not check.get("checker_timing_normalized", False):
            raise SystemExit(f"{case_id}: proof check is not deterministic")
        if not record["verified"]:
            raise SystemExit(f"{case_id}: proof index record is not verified")
        if matching:
            matching_proof_ids.add(case_id)

    return proof_ids, matching_proof_ids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage1_summary", type=Path)
    parser.add_argument("stage1_residual", type=Path)
    parser.add_argument("maximum_degree", type=Path)
    parser.add_argument("third_word_proofs", type=Path)
    parser.add_argument("summary_output", type=Path)
    parser.add_argument("residual_output", type=Path)
    args = parser.parse_args()

    stage1 = load_json(args.stage1_summary)
    residual = load_json(args.stage1_residual)
    maximum_degree = load_json(args.maximum_degree)
    third_proofs = load_json(args.third_word_proofs)
    if residual["case_count"] != 49:
        raise SystemExit("stage-1 residual does not contain 49 cases")
    if maximum_degree["source_residual_manifest_sha256"] != file_sha256(
        args.stage1_residual
    ):
        raise SystemExit("maximum-degree source hash mismatch")
    if not maximum_degree["valid"]:
        raise SystemExit("maximum-degree reduction is not valid")
    proof_ids, matching_proof_ids = verify_third_word_proof_index(
        third_proofs,
        args.stage1_residual,
    )

    cases = residual["cases"]
    all_ids = {case["case_id"] for case in cases}
    maximum_degree_ids = set(
        maximum_degree["maximum_degree_contradiction_cases"]
    )
    matching_case_ids = set(maximum_degree["matching_cases"])
    if len(all_ids) != len(cases):
        raise SystemExit("stage-1 residual contains duplicate cases")
    if not maximum_degree_ids <= all_ids or not proof_ids <= all_ids:
        raise SystemExit("advanced reduction names an unknown case")
    if maximum_degree_ids & proof_ids:
        raise SystemExit("advanced reductions overlap")
    if not matching_proof_ids <= matching_case_ids:
        raise SystemExit("a matching-constrained proof is outside its scope")
    expected_proof_ids = {
        "w1-weight7-intersection0",
        "w4-weight6-intersection0",
        "w4-weight6-intersection1",
        "w4-weight6-intersection2",
        "w5-weight5-intersection1",
        "w5-weight5-intersection2",
    }
    if proof_ids != expected_proof_ids:
        raise SystemExit("advanced proof cases changed")
    if len(maximum_degree_ids) != 5 or len(proof_ids) != 6:
        raise SystemExit("advanced reduction counts changed")

    open_cases = [
        case
        for case in cases
        if case["case_id"] not in maximum_degree_ids | proof_ids
    ]
    if len(open_cases) != 38:
        raise SystemExit("advanced residual count changed")
    by_weight = Counter(
        int(case["minimum_weight"])
        for case in open_cases
    )
    expected_by_weight = {1: 10, 2: 12, 3: 10, 4: 6}
    if dict(sorted(by_weight.items())) != expected_by_weight:
        raise SystemExit("advanced residual weight counts changed")

    final_counts = dict(stage1["counts"])
    final_counts.update(
        {
            "maximum_degree_normalization": len(maximum_degree_ids),
            "third_word_drat": len(proof_ids),
            "open": len(open_cases),
        }
    )
    final_counts["stage1_open"] = stage1["counts"]["open"]
    summary = {
        "problem": stage1["problem"],
        "total_cases": stage1["total_cases"],
        "stage1_summary": str(args.stage1_summary),
        "stage1_summary_sha256": file_sha256(args.stage1_summary),
        "stage1_residual": str(args.stage1_residual),
        "stage1_residual_sha256": file_sha256(args.stage1_residual),
        "advanced_inputs": {
            "maximum_degree": {
                "path": str(args.maximum_degree),
                "sha256": file_sha256(args.maximum_degree),
            },
            "third_word_proofs": {
                "path": str(args.third_word_proofs),
                "sha256": file_sha256(args.third_word_proofs),
            },
        },
        "stage1_counts": stage1["counts"],
        "advanced_counts": {
            "maximum_degree_normalization": len(maximum_degree_ids),
            "third_word_drat": len(proof_ids),
            "open": len(open_cases),
        },
        "third_word_proof_details": {
            "matching_constrained": len(matching_proof_ids),
            "unconstrained": len(proof_ids - matching_proof_ids),
        },
        "open_by_minimum_distance": {
            str(weight): count
            for weight, count in sorted(by_weight.items())
        },
        "maximum_degree_normalization_cases": sorted(maximum_degree_ids),
        "third_word_drat_cases": sorted(proof_ids),
        "matching_constrained_third_word_drat_cases": sorted(
            matching_proof_ids
        ),
        "open_cases": [case["case_id"] for case in open_cases],
        "proof_checker": third_proofs["checker"],
        "proof_checker_commit": third_proofs["checker_commit"],
        "all_accounted_for": True,
        "global_exact_value_resolved": False,
    }
    final_residual = {
        "length": residual["length"],
        "maximum_minimum_weight": 4,
        "descriptor_order": residual["descriptor_order"],
        "source_manifest": str(args.stage1_residual),
        "source_manifest_sha256": file_sha256(args.stage1_residual),
        "reduction_summary": str(args.summary_output),
        "case_count": len(open_cases),
        "cases": open_cases,
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    args.residual_output.parent.mkdir(parents=True, exist_ok=True)
    args.residual_output.write_text(
        json.dumps(final_residual, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(
        json.dumps(
            {
                "advanced_counts": summary["advanced_counts"],
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
