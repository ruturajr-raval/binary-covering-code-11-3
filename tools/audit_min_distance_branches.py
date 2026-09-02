#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from audit_covering_cnf import read_dimacs
from generate_min_distance_branches import minimum_distance_clauses


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    base_path = Path(manifest["base_formula"])
    base_variables, base_clauses, base_sha256 = read_dimacs(base_path)
    if base_sha256 != manifest["base_formula_sha256"]:
        raise SystemExit("base formula hash does not match the manifest")
    if base_variables != manifest["base_variables"]:
        raise SystemExit("base variable count does not match the manifest")
    if len(base_clauses) != manifest["base_clauses"]:
        raise SystemExit("base clause count does not match the manifest")

    distance_path = Path(manifest["distance_bounds"])
    distance_digest = hashlib.sha256(distance_path.read_bytes()).hexdigest()
    if distance_digest != manifest["distance_bounds_sha256"]:
        raise SystemExit("distance-bound evidence hash does not match")
    distance_bounds = json.loads(distance_path.read_text(encoding="ascii"))
    maximum_distance = int(
        distance_bounds["conclusions"]["minimum_pair_distance_at_most"]
    )
    if maximum_distance != manifest["maximum_minimum_distance"]:
        raise SystemExit("minimum-distance limit does not match the evidence")

    problem = manifest["problem"]
    length = int(problem["length"])
    expected_distances = list(range(1, maximum_distance + 1))
    actual_distances = [
        int(case["minimum_distance"]) for case in manifest["cases"]
    ]
    if actual_distances != expected_distances:
        raise SystemExit("branch distances are incomplete or out of order")

    audited_cases = []
    for case in manifest["cases"]:
        minimum_distance = int(case["minimum_distance"])
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

        expected_pairs = minimum_distance_clauses(
            length=length,
            minimum_distance=minimum_distance,
        )
        expected_count = (1 << (length - 1)) * sum(
            math.comb(length, distance)
            for distance in range(1, minimum_distance)
        )
        if len(expected_pairs) != expected_count:
            raise SystemExit(f"{path}: reconstructed pair count is wrong")
        canonical_word = (1 << minimum_distance) - 1
        expected_suffix = expected_pairs + [(canonical_word + 1,)]
        if clauses[len(base_clauses):] != expected_suffix:
            raise SystemExit(f"{path}: branch clauses are incorrect")
        if case["canonical_pair"] != [0, canonical_word]:
            raise SystemExit(f"{path}: canonical pair is incorrect")
        if case["forbidden_pair_clauses"] != expected_count:
            raise SystemExit(f"{path}: forbidden-pair count is incorrect")
        if case["clauses"] != len(clauses):
            raise SystemExit(f"{path}: clause count is inconsistent")
        audited_cases.append(
            {
                "minimum_distance": minimum_distance,
                "forbidden_pair_clauses": expected_count,
                "sha256": digest,
                "valid": True,
            }
        )

    report = {
        "manifest": str(args.manifest),
        "base_formula_sha256": base_sha256,
        "distance_bounds_sha256": distance_digest,
        "case_count": len(audited_cases),
        "minimum_distances": expected_distances,
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
