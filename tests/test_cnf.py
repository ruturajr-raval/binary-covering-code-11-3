from __future__ import annotations

import importlib.util
import itertools
import unittest

from covering_code.cnf import (
    CnfBuilder,
    add_exact_cardinality,
    add_gated_at_most_one,
    extend_primary_assignment,
    generate_covering_cnf,
)
from covering_code.core import verify_code


class CnfTests(unittest.TestCase):
    def test_gated_at_most_one_for_all_small_assignments(self) -> None:
        for input_count in range(5):
            builder = CnfBuilder(variable_count=input_count + 1)
            gate = 1
            inputs = list(range(2, input_count + 2))
            add_gated_at_most_one(
                builder,
                gate=gate,
                literals=inputs,
            )
            for mask in range(1 << (input_count + 1)):
                assignment = {
                    variable
                    for variable in range(1, input_count + 2)
                    if mask >> (variable - 1) & 1
                }
                encoded = extend_primary_assignment(
                    builder,
                    assignment,
                    primary_count=input_count + 1,
                )
                expected = (
                    gate not in assignment
                    or len(assignment.intersection(inputs)) <= 1
                )
                self.assertEqual(
                    encoded,
                    expected,
                    (input_count, mask),
                )

    def test_exact_cardinality_for_all_small_assignments(self) -> None:
        for variable_count in range(1, 6):
            variables = list(range(1, variable_count + 1))
            for target in range(variable_count + 1):
                builder = CnfBuilder(variable_count=variable_count)
                add_exact_cardinality(builder, variables, target)
                for mask in range(1 << variable_count):
                    assignment = {
                        variable
                        for variable in variables
                        if mask >> (variable - 1) & 1
                    }
                    encoded = extend_primary_assignment(
                        builder,
                        assignment,
                        primary_count=variable_count,
                    )
                    self.assertEqual(
                        encoded,
                        len(assignment) == target,
                        (variable_count, target, mask),
                    )

    def test_tiny_formula_matches_direct_verification(self) -> None:
        length = 3
        radius = 1
        size = 2
        builder, selected = generate_covering_cnf(
            length=length,
            radius=radius,
            size=size,
            anchor_zero=False,
        )
        for code_tuple in itertools.combinations(range(1 << length), size):
            direct = verify_code(
                code_tuple,
                length=length,
                radius=radius,
            ).valid
            assignment = {selected[word] for word in code_tuple}
            encoded = extend_primary_assignment(
                builder,
                assignment,
                primary_count=1 << length,
            )
            self.assertEqual(encoded, direct, code_tuple)

    def test_anchor_zero_preserves_existence_on_a_tiny_cube(self) -> None:
        builder, selected = generate_covering_cnf(
            length=3,
            radius=1,
            size=2,
            anchor_zero=True,
        )
        satisfying_codes = []
        for code_tuple in itertools.combinations(range(1 << 3), 2):
            assignment = {selected[word] for word in code_tuple}
            if extend_primary_assignment(
                builder,
                assignment,
                primary_count=1 << 3,
            ):
                satisfying_codes.append(code_tuple)
        self.assertTrue(satisfying_codes)
        self.assertTrue(all(0 in code for code in satisfying_codes))

    def test_translation_places_zero_in_every_nonempty_code(self) -> None:
        for size in range(1, 5):
            for code_tuple in itertools.combinations(range(8), size):
                pivot = code_tuple[-1]
                translated = {word ^ pivot for word in code_tuple}
                self.assertIn(0, translated)
                for left in range(8):
                    for right in code_tuple:
                        self.assertEqual(
                            bin(left ^ right).count("1"),
                            bin(
                                (left ^ pivot) ^ (right ^ pivot)
                            ).count("1"),
                        )

    def test_smaller_cover_can_be_padded_without_losing_coverage(self) -> None:
        code = {0, 7}
        self.assertTrue(verify_code(code, length=3, radius=1).valid)
        padded = code | {1, 2}
        self.assertTrue(verify_code(padded, length=3, radius=1).valid)

    def test_invalid_parameters_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_covering_cnf(
                length=0,
                radius=0,
                size=1,
                anchor_zero=False,
            )

    def test_full_formula_dimensions(self) -> None:
        builder, selected = generate_covering_cnf(
            length=11,
            radius=3,
            size=15,
            anchor_zero=True,
        )
        self.assertEqual(len(selected), 2048)
        self.assertEqual(builder.variable_count, 34816)
        self.assertEqual(len(builder.clauses), 131029)
        self.assertEqual(builder.clauses[-2049], (1,))
        self.assertTrue(
            all(len(clause) == 232 for clause in builder.clauses[-2048:])
        )

    def test_builder_rejects_unallocated_literals(self) -> None:
        builder = CnfBuilder(variable_count=2)
        with self.assertRaises(ValueError):
            builder.add(3)


@unittest.skipUnless(
    importlib.util.find_spec("pysat") is not None,
    "python-sat is not installed",
)
class IndependentCardinalityTests(unittest.TestCase):
    def test_matches_totalizer_encoding(self) -> None:
        from pysat.card import CardEnc, EncType
        from pysat.solvers import Solver

        for variable_count in range(2, 7):
            variables = list(range(1, variable_count + 1))
            for target in range(1, variable_count):
                ours = CnfBuilder(variable_count=variable_count)
                add_exact_cardinality(ours, variables, target)
                totalizer = CardEnc.equals(
                    lits=variables,
                    bound=target,
                    encoding=EncType.totalizer,
                )
                with Solver(
                    name="minisat22",
                    bootstrap_with=ours.clauses,
                ) as ours_solver, Solver(
                    name="minisat22",
                    bootstrap_with=totalizer.clauses,
                ) as totalizer_solver:
                    for mask in range(1 << variable_count):
                        assumptions = [
                            variable
                            if mask >> (variable - 1) & 1
                            else -variable
                            for variable in variables
                        ]
                        self.assertEqual(
                            ours_solver.solve(assumptions=assumptions),
                            totalizer_solver.solve(
                                assumptions=assumptions
                            ),
                            (variable_count, target, mask),
                        )


if __name__ == "__main__":
    unittest.main()
