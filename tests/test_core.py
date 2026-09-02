from __future__ import annotations

import unittest
from pathlib import Path

from covering_code.core import parse_code, verify_code


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data/baseline/k2-11-3-linear-16.txt"


class CoreTests(unittest.TestCase):
    def test_baseline_is_a_radius_three_cover(self) -> None:
        code = parse_code(BASELINE.read_text(encoding="ascii"), length=11)
        report = verify_code(code, length=11, radius=3)
        self.assertTrue(report.valid)
        self.assertEqual(report.code_size, 16)
        self.assertEqual(report.covering_radius, 3)
        self.assertEqual(
            report.distance_histogram,
            {0: 16, 1: 176, 2: 752, 3: 1104},
        )

    def test_single_deletion_breaks_the_baseline(self) -> None:
        code = parse_code(BASELINE.read_text(encoding="ascii"), length=11)
        for index in range(len(code)):
            report = verify_code(
                code[:index] + code[index + 1 :],
                length=11,
                radius=3,
            )
            self.assertFalse(report.valid, index)

    def test_parser_rejects_invalid_and_duplicate_words(self) -> None:
        with self.assertRaises(ValueError):
            parse_code("001\n", length=4)
        with self.assertRaises(ValueError):
            parse_code("0000\n0000\n", length=4)


if __name__ == "__main__":
    unittest.main()
