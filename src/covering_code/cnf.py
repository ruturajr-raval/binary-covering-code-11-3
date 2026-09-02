from __future__ import annotations

from dataclasses import dataclass, field

from .core import hamming_distance


@dataclass
class CnfBuilder:
    variable_count: int
    clauses: list[tuple[int, ...]] = field(default_factory=list)

    def new_variables(self, count: int) -> list[int]:
        if count < 0:
            raise ValueError("variable count must be nonnegative")
        start = self.variable_count + 1
        self.variable_count += count
        return list(range(start, self.variable_count + 1))

    def add(self, *literals: int) -> None:
        if not literals:
            raise ValueError("empty clauses are not supported")
        if any(literal == 0 for literal in literals):
            raise ValueError("zero is not a DIMACS literal")
        if any(abs(literal) > self.variable_count for literal in literals):
            raise ValueError("literal exceeds the allocated variable range")
        self.clauses.append(tuple(literals))


def add_exact_cardinality(
    builder: CnfBuilder,
    literals: list[int],
    target: int,
) -> None:
    if not literals:
        raise ValueError("cardinality requires at least one literal")
    if target < 0 or target > len(literals):
        raise ValueError("cardinality target is outside the literal range")
    if target == 0:
        for literal in literals:
            builder.add(-literal)
        return
    if target == len(literals):
        for literal in literals:
            builder.add(literal)
        return

    width = target + 1
    counters = builder.new_variables(len(literals) * width)

    def counter(position: int, threshold: int) -> int:
        return counters[position * width + threshold - 1]

    first = literals[0]
    builder.add(-counter(0, 1), first)
    builder.add(counter(0, 1), -first)
    for threshold in range(2, width + 1):
        builder.add(-counter(0, threshold))

    for position, literal in enumerate(literals[1:], start=1):
        for threshold in range(1, width + 1):
            current = counter(position, threshold)
            previous = counter(position - 1, threshold)
            builder.add(-previous, current)
            if threshold == 1:
                builder.add(-literal, current)
                builder.add(-current, previous, literal)
                continue

            previous_lower = counter(position - 1, threshold - 1)
            builder.add(-literal, -previous_lower, current)
            builder.add(-current, previous, literal)
            builder.add(-current, previous, previous_lower)

    builder.add(counter(len(literals) - 1, target))
    builder.add(-counter(len(literals) - 1, target + 1))


def add_gated_at_most_one(
    builder: CnfBuilder,
    *,
    gate: int,
    literals: list[int],
) -> None:
    if gate <= 0 or gate > builder.variable_count:
        raise ValueError("gate is outside the allocated variable range")
    if any(
        literal <= 0 or literal > builder.variable_count
        for literal in literals
    ):
        raise ValueError("input is outside the allocated variable range")
    if len(set(literals)) != len(literals):
        raise ValueError("inputs must be distinct")
    if len(literals) <= 1:
        return
    if len(literals) == 2:
        builder.add(-gate, -literals[0], -literals[1])
        return

    auxiliaries = builder.new_variables(len(literals) - 1)
    builder.add(-gate, -literals[0], auxiliaries[0])
    for index in range(1, len(literals) - 1):
        builder.add(-gate, -literals[index], auxiliaries[index])
        builder.add(
            -gate,
            -auxiliaries[index - 1],
            auxiliaries[index],
        )
        builder.add(
            -gate,
            -literals[index],
            -auxiliaries[index - 1],
        )
    builder.add(-gate, -literals[-1], -auxiliaries[-1])


def generate_covering_cnf(
    *,
    length: int,
    radius: int,
    size: int,
    anchor_zero: bool,
) -> tuple[CnfBuilder, list[int]]:
    if length <= 0:
        raise ValueError("length must be positive")
    if radius < 0 or radius > length:
        raise ValueError("radius is outside the valid range")
    ambient_size = 1 << length
    if size <= 0 or size > ambient_size:
        raise ValueError("size is outside the valid range")

    builder = CnfBuilder(variable_count=ambient_size)
    selected = list(range(1, ambient_size + 1))
    add_exact_cardinality(builder, selected, size)

    if anchor_zero:
        builder.add(selected[0])

    for target in range(ambient_size):
        builder.add(
            *[
                selected[center]
                for center in range(ambient_size)
                if hamming_distance(center, target) <= radius
            ]
        )
    return builder, selected


def dimacs_text(builder: CnfBuilder) -> str:
    lines = [
        f"p cnf {builder.variable_count} {len(builder.clauses)}"
    ]
    lines.extend(
        " ".join(str(literal) for literal in clause) + " 0"
        for clause in builder.clauses
    )
    return "\n".join(lines) + "\n"


def assignment_satisfies(
    builder: CnfBuilder,
    assignment: set[int],
) -> bool:
    for clause in builder.clauses:
        if not any(
            (literal > 0 and literal in assignment)
            or (literal < 0 and -literal not in assignment)
            for literal in clause
        ):
            return False
    return True


def extend_primary_assignment(
    builder: CnfBuilder,
    primary_assignment: set[int],
    primary_count: int,
) -> bool:
    if primary_count < 0 or primary_count > builder.variable_count:
        raise ValueError("primary variable count is outside the formula")
    if any(
        variable <= 0 or variable > primary_count
        for variable in primary_assignment
    ):
        raise ValueError("primary assignment contains a non-primary variable")

    fixed = {
        variable: variable in primary_assignment
        for variable in range(1, primary_count + 1)
    }

    def propagate(assignment: dict[int, bool]) -> bool:
        while True:
            unit_literal: int | None = None
            for clause in builder.clauses:
                undecided: list[int] = []
                for literal in clause:
                    value = assignment.get(abs(literal))
                    if value is None:
                        undecided.append(literal)
                    elif value == (literal > 0):
                        break
                else:
                    if not undecided:
                        return False
                    if len(undecided) == 1:
                        unit_literal = undecided[0]
                        break

            if unit_literal is None:
                return True

            variable = abs(unit_literal)
            value = unit_literal > 0
            previous = assignment.get(variable)
            if previous is not None and previous != value:
                return False
            assignment[variable] = value

    def solve(assignment: dict[int, bool]) -> bool:
        if not propagate(assignment):
            return False

        variable = next(
            (
                candidate
                for candidate in range(primary_count + 1, builder.variable_count + 1)
                if candidate not in assignment
            ),
            None,
        )
        if variable is None:
            return True

        for value in (False, True):
            branch = dict(assignment)
            branch[variable] = value
            if solve(branch):
                return True
        return False

    return solve(fixed)
