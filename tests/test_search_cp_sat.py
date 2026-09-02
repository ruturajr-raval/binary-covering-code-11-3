from __future__ import annotations

import importlib.util
import unittest

from covering_code.search import (
    maximize_coverage_with_cp_sat,
    repair_with_cp_sat,
    solve_with_cp_sat,
)


ORTOOLS_AVAILABLE = importlib.util.find_spec("ortools") is not None


@unittest.skipUnless(ORTOOLS_AVAILABLE, "OR-Tools is not installed")
class CpSatTests(unittest.TestCase):
    def test_finds_a_small_known_cover(self) -> None:
        summary, code = solve_with_cp_sat(
            length=3,
            radius=1,
            size=2,
            time_limit=5,
            workers=1,
            seed=1,
            anchor_zero=True,
        )
        self.assertIn(summary["status"], {"OPTIMAL", "FEASIBLE"})
        self.assertTrue(summary["valid"])
        self.assertIsNotNone(code)
        self.assertIn(0, code)

    def test_maximizes_coverage_on_a_small_cube(self) -> None:
        summary, code = maximize_coverage_with_cp_sat(
            length=3,
            radius=1,
            size=2,
            time_limit=5,
            workers=1,
            seed=1,
            anchor_zero=True,
            initial_code=[0, 1],
        )
        self.assertIsNotNone(code)
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["covered_words"], 8)

    def test_repairs_with_a_required_overlap(self) -> None:
        summary, code = repair_with_cp_sat(
            initial_code=[0, 7],
            minimum_overlap=2,
            length=3,
            radius=1,
            size=2,
            time_limit=5,
            workers=1,
            seed=1,
            anchor_zero=True,
        )
        self.assertIsNotNone(code)
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["actual_overlap"], 2)


if __name__ == "__main__":
    unittest.main()
