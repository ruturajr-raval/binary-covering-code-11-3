from __future__ import annotations

import itertools
import json
import math
import random
import unittest
from pathlib import Path


def choose(n: int, k: int) -> int:
    return math.comb(n, k) if 0 <= k <= n else 0


def krawtchouk(degree: int, distance: int) -> int:
    return sum(
        (-1) ** overlap
        * choose(distance, overlap)
        * choose(11 - distance, degree - overlap)
        for overlap in range(degree + 1)
    )


class DistanceDistributionTests(unittest.TestCase):
    def test_retained_certificate_conclusion(self) -> None:
        evidence = json.loads(
            Path("evidence/distance-distribution-bounds.json").read_text(
                encoding="ascii"
            )
        )
        self.assertTrue(evidence["valid"])
        self.assertEqual(
            evidence["conclusions"],
            {
                "pairs_at_distance_at_most_5": 11,
                "pairs_at_distance_at_most_6": 28,
                "minimum_pair_distance_at_most": 5,
            },
        )

    def test_retained_overlap_conclusion(self) -> None:
        evidence = json.loads(
            Path("evidence/overlap-bound.json").read_text(encoding="ascii")
        )
        self.assertTrue(evidence["valid"])
        self.assertEqual(
            evidence["modular_refinement"]["integral_lower_bound"],
            1712,
        )
        self.assertEqual(
            evidence["sharp_for_retained_row_system"]["witness_count"],
            3,
        )
        self.assertEqual(
            {
                witness["objective"]
                for witness in evidence[
                    "sharp_for_retained_row_system"
                ]["witnesses"]
            },
            {1712},
        )
        self.assertEqual(
            evidence["triple_overlap_consequence"]["lower_bound"],
            280,
        )

    def test_pair_ball_intersections(self) -> None:
        expected = [112, 112, 56, 56, 20, 20, 0, 0, 0, 0, 0]
        actual = []
        for distance in range(1, 12):
            other = (1 << distance) - 1
            actual.append(
                sum(
                    1
                    for word in range(1 << 11)
                    if bin(word).count("1") <= 3
                    and bin(word ^ other).count("1") <= 3
                )
            )
        self.assertEqual(actual, expected)

    def test_krawtchouk_identity_and_parity_refinement(self) -> None:
        code = random.Random(20260902).sample(range(1 << 11), 15)
        pair_distances = [
            bin(left ^ right).count("1")
            for left, right in itertools.combinations(code, 2)
        ]
        for degree in range(12):
            pair_formula = (
                15 * choose(11, degree)
                + 2
                * sum(
                    krawtchouk(degree, distance)
                    for distance in pair_distances
                )
            )
            fourier = 0
            for mask in range(1 << 11):
                if bin(mask).count("1") != degree:
                    continue
                character_sum = sum(
                    -1
                    if bin(mask & word).count("1") % 2
                    else 1
                    for word in code
                )
                fourier += character_sum * character_sum
            self.assertEqual(pair_formula, fourier)
            self.assertGreaterEqual(fourier, choose(11, degree))
            self.assertEqual(
                fourier % 8,
                choose(11, degree) % 8,
            )


if __name__ == "__main__":
    unittest.main()
