from __future__ import annotations

import itertools

from covering_code.cnf import CnfBuilder, add_gated_at_most_one
from run_two_word_portfolio import case_units


def append_matching_constraints(
    variable_count: int,
    clauses: list[tuple[int, ...]],
    parent_case: dict[str, object],
    *,
    length: int,
) -> tuple[int, dict[str, int]]:
    minimum_distance = int(parent_case["minimum_weight"])
    forbidden = {
        -literal - 1
        for literal in case_units(parent_case, length)
        if literal < 0
    }
    allowed = [
        word
        for word in range(1 << length)
        if word not in forbidden
    ]
    offsets = [
        sum(1 << position for position in positions)
        for positions in itertools.combinations(
            range(length),
            minimum_distance,
        )
    ]
    allowed_set = set(allowed)
    builder = CnfBuilder(
        variable_count=variable_count,
        clauses=clauses,
    )
    gated_vertices = 0
    matching_clauses = 0
    neighbor_incidence_count = 0
    for vertex in allowed:
        neighbors = sorted(
            vertex ^ offset
            for offset in offsets
            if vertex ^ offset in allowed_set
        )
        if len(neighbors) <= 1:
            continue
        gated_vertices += 1
        neighbor_incidence_count += len(neighbors)
        before = len(builder.clauses)
        add_gated_at_most_one(
            builder,
            gate=vertex + 1,
            literals=[word + 1 for word in neighbors],
        )
        matching_clauses += len(builder.clauses) - before
    return builder.variable_count, {
        "matching_allowed_vertices": len(allowed),
        "matching_gated_vertices": gated_vertices,
        "matching_neighbor_incidences": neighbor_incidence_count,
        "matching_auxiliary_variables": (
            builder.variable_count - variable_count
        ),
        "matching_clauses": matching_clauses,
    }
