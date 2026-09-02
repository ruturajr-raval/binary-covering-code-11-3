#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_covering_cnf import read_dimacs
from matching_constraints import append_matching_constraints
from run_two_word_portfolio import case_units, unit_digest
from third_word_symmetry import third_orbits


def dimacs_text(variable_count: int, clauses: list[tuple[int, ...]]) -> str:
    lines = [f"p cnf {variable_count} {len(clauses)}"]
    lines.extend(
        " ".join(str(literal) for literal in clause) + " 0"
        for clause in clauses
    )
    return "\n".join(lines) + "\n"


def build_formula(
    base_formula: Path,
    parent_case: dict[str, object],
    third_parent: dict[str, object],
    *,
    length: int,
    enforce_matching: bool = False,
) -> tuple[int, list[tuple[int, ...]], dict[str, object]]:
    variables, base_clauses, base_sha256 = read_dimacs(base_formula)
    units = case_units(parent_case, length)
    if len(units) != parent_case["unit_count"]:
        raise RuntimeError("parent unit count does not match its manifest")
    if unit_digest(units) != parent_case["unit_sha256"]:
        raise RuntimeError("parent unit hash does not match its manifest")
    clauses = list(base_clauses)
    clauses.extend((literal,) for literal in units)

    reconstructed_orbits = third_orbits(parent_case, length=length)
    orbit_records = third_parent["orbits"]
    if len(reconstructed_orbits) != len(orbit_records):
        raise RuntimeError("third-orbit count does not match its manifest")

    selectors = []
    earlier_words: list[int] = []
    selector_implication_clauses = 0
    for index, ((descriptor, words), orbit) in enumerate(
        zip(reconstructed_orbits, orbit_records),
        start=1,
    ):
        if list(descriptor) != orbit["descriptor"]:
            raise RuntimeError("third-orbit descriptor mismatch")
        if len(words) != orbit["orbit_size"]:
            raise RuntimeError("third-orbit size mismatch")
        if len(earlier_words) != orbit["earlier_word_count"]:
            raise RuntimeError("third-orbit prefix mismatch")
        canonical = int(orbit["canonical_word"])
        if canonical not in words:
            raise RuntimeError("third-orbit representative mismatch")
        selector = variables + index
        selectors.append(selector)
        clauses.append((-selector, canonical + 1))
        selector_implication_clauses += 1
        clauses.extend(
            (-selector, -(word + 1))
            for word in earlier_words
        )
        selector_implication_clauses += len(earlier_words)
        earlier_words.extend(words)

    clauses.append(tuple(selectors))
    at_most_one_clauses = 0
    for index, left in enumerate(selectors):
        for right in selectors[index + 1:]:
            clauses.append((-left, -right))
            at_most_one_clauses += 1
    final_variables = variables + len(selectors)
    matching_metadata = {
        "matching_allowed_vertices": 0,
        "matching_gated_vertices": 0,
        "matching_neighbor_incidences": 0,
        "matching_auxiliary_variables": 0,
        "matching_clauses": 0,
    }
    if enforce_matching:
        final_variables, matching_metadata = append_matching_constraints(
            final_variables,
            clauses,
            parent_case,
            length=length,
        )

    metadata = {
        "parent_case_id": parent_case["case_id"],
        "minimum_distance": parent_case["minimum_weight"],
        "base_formula": str(base_formula),
        "base_formula_sha256": base_sha256,
        "base_variables": variables,
        "base_clauses": len(base_clauses),
        "parent_unit_count": len(units),
        "parent_unit_sha256": unit_digest(units),
        "selector_count": len(selectors),
        "selector_first_variable": selectors[0],
        "selector_last_variable": selectors[-1],
        "selector_implication_clauses": selector_implication_clauses,
        "selector_at_least_one_clauses": 1,
        "selector_at_most_one_clauses": at_most_one_clauses,
        "enforce_minimum_distance_matching": enforce_matching,
        "variables": final_variables,
        "clauses": len(clauses),
        **matching_metadata,
    }
    return final_variables, clauses, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_formula", type=Path)
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_manifest", type=Path)
    parser.add_argument("parent_case_id")
    parser.add_argument("formula_output", type=Path)
    parser.add_argument("metadata_output", type=Path)
    parser.add_argument("--matching", action="store_true")
    args = parser.parse_args()

    parent_manifest = json.loads(
        args.parent_manifest.read_text(encoding="ascii")
    )
    third_manifest = json.loads(
        args.third_manifest.read_text(encoding="ascii")
    )
    parent_case = next(
        (
            case
            for case in parent_manifest["cases"]
            if case["case_id"] == args.parent_case_id
        ),
        None,
    )
    third_parent = next(
        (
            parent
            for parent in third_manifest["parents"]
            if parent["parent_case_id"] == args.parent_case_id
        ),
        None,
    )
    if parent_case is None or third_parent is None:
        raise SystemExit(f"unknown parent case: {args.parent_case_id}")
    variables, clauses, metadata = build_formula(
        args.base_formula,
        parent_case,
        third_parent,
        length=int(parent_manifest["length"]),
        enforce_matching=args.matching,
    )
    text = dimacs_text(variables, clauses)
    args.formula_output.parent.mkdir(parents=True, exist_ok=True)
    args.formula_output.write_text(text, encoding="ascii")
    metadata.update(
        {
            "formula": str(args.formula_output),
            "formula_sha256": hashlib.sha256(
                text.encode("ascii")
            ).hexdigest(),
            "parent_manifest": str(args.parent_manifest),
            "parent_manifest_sha256": hashlib.sha256(
                args.parent_manifest.read_bytes()
            ).hexdigest(),
            "third_manifest": str(args.third_manifest),
            "third_manifest_sha256": hashlib.sha256(
                args.third_manifest.read_bytes()
            ).hexdigest(),
        }
    )
    args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_output.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
