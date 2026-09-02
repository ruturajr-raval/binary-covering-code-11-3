#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_covering_cnf import read_dimacs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_formula", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    base_variables, base_clauses, base_sha256 = read_dimacs(
        args.base_formula
    )
    if base_sha256 != manifest["base_formula_sha256"]:
        raise SystemExit("base formula hash does not match the manifest")
    if base_variables != manifest["base_variables"]:
        raise SystemExit("base variable count does not match the manifest")
    if len(base_clauses) != manifest["base_clauses"]:
        raise SystemExit("base clause count does not match the manifest")

    length = manifest["problem"]["length"]
    expected_weights = list(
        range(1, manifest["maximum_minimum_weight"] + 1)
    )
    actual_weights = [
        case["minimum_weight"]
        for case in manifest["cases"]
    ]
    if actual_weights != expected_weights:
        raise SystemExit("case weights are incomplete or out of order")

    audited_cases = []
    for case in manifest["cases"]:
        path = Path(case["formula"])
        variables, clauses, digest = read_dimacs(path)
        if variables != base_variables:
            raise SystemExit(f"{path}: variable count changed")
        if clauses[: len(base_clauses)] != base_clauses:
            raise SystemExit(f"{path}: base formula prefix changed")
        if digest != case["sha256"]:
            raise SystemExit(f"{path}: formula hash mismatch")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise SystemExit(f"{path}: byte hash mismatch")

        weight = case["minimum_weight"]
        forbidden = [
            word
            for word in range(1, 1 << length)
            if bin(word).count("1") < weight
        ]
        canonical = (1 << weight) - 1
        expected_suffix = [
            (-(word + 1),)
            for word in forbidden
        ] + [(canonical + 1,)]
        if clauses[len(base_clauses):] != expected_suffix:
            raise SystemExit(f"{path}: case unit clauses are incorrect")
        if case["canonical_word"] != canonical:
            raise SystemExit(f"{path}: canonical word is incorrect")
        if case["forbidden_lower_weight_words"] != len(forbidden):
            raise SystemExit(f"{path}: forbidden-word count is incorrect")
        audited_cases.append(
            {
                "minimum_weight": weight,
                "sha256": digest,
                "valid": True,
            }
        )

    report = {
        "base_formula_sha256": base_sha256,
        "case_count": len(audited_cases),
        "weights": expected_weights,
        "cases": audited_cases,
        "valid": True,
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="ascii")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
