#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from audit_covering_cnf import read_dimacs


def weight(word: int) -> int:
    return bin(word).count("1")


def parent_units(case: dict[str, object], length: int) -> list[int]:
    ambient_size = 1 << length
    minimum_weight = int(case["minimum_weight"])
    first_word = int(case["first_word"])
    payload = case["second_descriptor"]
    threshold = (
        int(payload["weight"]),
        int(payload["intersection"]),
    )
    units = [
        -(word + 1)
        for word in range(1, ambient_size)
        if weight(word) < minimum_weight
    ]
    units.append(first_word + 1)
    units.extend(
        -(word + 1)
        for word in range(1, ambient_size)
        if word != first_word
        and weight(word) >= minimum_weight
        and (weight(word), weight(word & first_word)) < threshold
    )
    units.append(int(case["second_word"]) + 1)
    return units


def candidate_words(
    case: dict[str, object],
    descriptor: list[int],
    length: int,
) -> list[int]:
    first = int(case["first_word"])
    second = int(case["second_word"])
    ambient = (1 << length) - 1
    masks = [
        first & second,
        first & (ambient ^ second),
        second & (ambient ^ first),
        ambient ^ (first | second),
    ]
    payload = case["second_descriptor"]
    threshold = (
        int(payload["weight"]),
        int(payload["intersection"]),
    )
    words = []
    for word in range(1 << length):
        if word in {0, first, second}:
            continue
        if weight(word) < int(case["minimum_weight"]):
            continue
        if (weight(word), weight(word & first)) < threshold:
            continue
        if [weight(word & mask) for mask in masks] == descriptor:
            words.append(word)
    return words


def append_gated_at_most_one(
    clauses: list[tuple[int, ...]],
    *,
    gate: int,
    inputs: list[int],
    next_variable: int,
) -> tuple[int, int]:
    if len(inputs) <= 1:
        return next_variable, 0
    if len(inputs) == 2:
        clauses.append((-gate, -inputs[0], -inputs[1]))
        return next_variable, 1
    auxiliaries = list(
        range(next_variable + 1, next_variable + len(inputs))
    )
    clauses.append((-gate, -inputs[0], auxiliaries[0]))
    for index in range(1, len(inputs) - 1):
        clauses.append((-gate, -inputs[index], auxiliaries[index]))
        clauses.append(
            (-gate, -auxiliaries[index - 1], auxiliaries[index])
        )
        clauses.append(
            (-gate, -inputs[index], -auxiliaries[index - 1])
        )
    clauses.append((-gate, -inputs[-1], -auxiliaries[-1]))
    return auxiliaries[-1], 3 * len(inputs) - 4


def append_matching(
    clauses: list[tuple[int, ...]],
    *,
    variable_count: int,
    case: dict[str, object],
    length: int,
) -> tuple[int, dict[str, int]]:
    units = parent_units(case, length)
    forbidden = {
        -literal - 1
        for literal in units
        if literal < 0
    }
    allowed = [
        word
        for word in range(1 << length)
        if word not in forbidden
    ]
    allowed_set = set(allowed)
    distance = int(case["minimum_weight"])
    offsets = [
        sum(1 << position for position in positions)
        for positions in itertools.combinations(range(length), distance)
    ]
    next_variable = variable_count
    gated_vertices = 0
    incidences = 0
    added_clauses = 0
    for vertex in allowed:
        neighbors = sorted(
            vertex ^ offset
            for offset in offsets
            if vertex ^ offset in allowed_set
        )
        if len(neighbors) <= 1:
            continue
        gated_vertices += 1
        incidences += len(neighbors)
        next_variable, added = append_gated_at_most_one(
            clauses,
            gate=vertex + 1,
            inputs=[word + 1 for word in neighbors],
            next_variable=next_variable,
        )
        added_clauses += added
    return next_variable, {
        "matching_allowed_vertices": len(allowed),
        "matching_gated_vertices": gated_vertices,
        "matching_neighbor_incidences": incidences,
        "matching_auxiliary_variables": next_variable - variable_count,
        "matching_clauses": added_clauses,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("formula", type=Path)
    parser.add_argument("metadata", type=Path)
    args = parser.parse_args()

    metadata = json.loads(args.metadata.read_text(encoding="ascii"))
    parent_manifest_path = Path(metadata["parent_manifest"])
    third_manifest_path = Path(metadata["third_manifest"])
    if hashlib.sha256(parent_manifest_path.read_bytes()).hexdigest() != (
        metadata["parent_manifest_sha256"]
    ):
        raise SystemExit("parent-manifest hash mismatch")
    if hashlib.sha256(third_manifest_path.read_bytes()).hexdigest() != (
        metadata["third_manifest_sha256"]
    ):
        raise SystemExit("third-manifest hash mismatch")
    parent_manifest = json.loads(
        parent_manifest_path.read_text(encoding="ascii")
    )
    third_manifest = json.loads(
        third_manifest_path.read_text(encoding="ascii")
    )
    case_id = metadata["parent_case_id"]
    case = next(
        item
        for item in parent_manifest["cases"]
        if item["case_id"] == case_id
    )
    third_parent = next(
        item
        for item in third_manifest["parents"]
        if item["parent_case_id"] == case_id
    )

    base_path = Path(metadata["base_formula"])
    base_variables, base_clauses, base_digest = read_dimacs(base_path)
    if base_digest != metadata["base_formula_sha256"]:
        raise SystemExit("base formula hash mismatch")
    variables, clauses, digest = read_dimacs(args.formula)
    if digest != metadata["formula_sha256"]:
        raise SystemExit("formula hash mismatch")
    if hashlib.sha256(args.formula.read_bytes()).hexdigest() != digest:
        raise SystemExit("formula byte hash mismatch")

    length = int(parent_manifest["length"])
    units = parent_units(case, length)
    expected = list(base_clauses)
    expected.extend((literal,) for literal in units)
    selectors = []
    earlier_words: list[int] = []
    for index, orbit in enumerate(third_parent["orbits"], start=1):
        words = candidate_words(case, orbit["descriptor"], length)
        if len(words) != orbit["orbit_size"]:
            raise SystemExit(f"{case_id}: orbit size mismatch")
        if len(earlier_words) != orbit["earlier_word_count"]:
            raise SystemExit(f"{case_id}: orbit prefix mismatch")
        canonical = int(orbit["canonical_word"])
        if canonical not in words:
            raise SystemExit(f"{case_id}: canonical word mismatch")
        selector = base_variables + index
        selectors.append(selector)
        expected.append((-selector, canonical + 1))
        expected.extend(
            (-selector, -(word + 1))
            for word in earlier_words
        )
        earlier_words.extend(words)
    expected.append(tuple(selectors))
    for index, left in enumerate(selectors):
        for right in selectors[index + 1:]:
            expected.append((-left, -right))

    expected_variables = base_variables + len(selectors)
    matching_metadata = {
        "matching_allowed_vertices": 0,
        "matching_gated_vertices": 0,
        "matching_neighbor_incidences": 0,
        "matching_auxiliary_variables": 0,
        "matching_clauses": 0,
    }
    if metadata.get("enforce_minimum_distance_matching", False):
        expected_variables, matching_metadata = append_matching(
            expected,
            variable_count=expected_variables,
            case=case,
            length=length,
        )
    if clauses != expected:
        raise SystemExit("formula clauses do not match reconstruction")
    if variables != expected_variables:
        raise SystemExit("formula variable count is incorrect")
    if variables != metadata["variables"]:
        raise SystemExit("metadata variable count is incorrect")
    if len(clauses) != metadata["clauses"]:
        raise SystemExit("metadata clause count is incorrect")
    for key, value in matching_metadata.items():
        if metadata.get(key, 0) != value:
            raise SystemExit(f"metadata {key} is incorrect")
    print(
        json.dumps(
            {
                "clauses": len(clauses),
                "formula_sha256": digest,
                "parent_case_id": case_id,
                "selectors": len(selectors),
                "valid": True,
                "variables": variables,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
