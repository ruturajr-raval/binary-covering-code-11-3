from __future__ import annotations

import json
import unittest
from pathlib import Path

from covering_code.core import parse_code
from covering_code.linear import (
    analyze_linear_cover,
    binary_rank,
    kernel_code,
)


ROOT = Path(__file__).resolve().parents[1]
PARITY = ROOT / "data/baseline/k2-11-3-parity-columns-16.json"
BASELINE = ROOT / "data/baseline/k2-11-3-linear-16.txt"


class LinearTests(unittest.TestCase):
    def test_baseline_parity_check_has_radius_three(self) -> None:
        payload = json.loads(PARITY.read_text(encoding="ascii"))
        analysis = analyze_linear_cover(
            payload["columns"],
            syndrome_bits=payload["syndrome_bits"],
            radius=3,
        )
        self.assertTrue(analysis["valid"])
        self.assertEqual(analysis["rank"], 7)
        self.assertEqual(analysis["dimension"], 4)
        self.assertEqual(analysis["code_size"], 16)
        self.assertEqual(analysis["syndrome_radius"], 3)
        self.assertEqual(analysis["reached_syndromes"], 128)
        self.assertTrue(analysis["full_syndrome_space"])
        self.assertEqual(
            analysis["syndrome_weight_histogram"],
            {0: 1, 1: 11, 2: 47, 3: 69},
        )
        expected = parse_code(
            BASELINE.read_text(encoding="ascii"),
            length=11,
        )
        self.assertEqual(kernel_code(payload["columns"]), expected)

    def test_binary_rank(self) -> None:
        self.assertEqual(binary_rank([1, 2, 4, 3]), 3)
        self.assertEqual(binary_rank([1, 1, 0]), 1)

    def test_incomplete_syndrome_space_is_rejected(self) -> None:
        analysis = analyze_linear_cover(
            [1],
            syndrome_bits=2,
            radius=1,
        )
        self.assertFalse(analysis["valid"])
        self.assertEqual(analysis["reached_syndromes"], 2)


if __name__ == "__main__":
    unittest.main()
