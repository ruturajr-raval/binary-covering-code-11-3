from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from verify_advanced_case_reduction import (
    verify_third_word_proof_index,
)


class AdvancedCaseReductionTests(unittest.TestCase):
    def test_missing_proof_check_is_rejected(self) -> None:
        index = json.loads(
            Path("evidence/third-word-proof-index.json").read_text(
                encoding="ascii"
            )
        )
        broken = copy.deepcopy(index)
        broken["cases"][0]["proof_check"] = "missing-proof-check.json"
        with self.assertRaisesRegex(
            SystemExit,
            "proof-check file is missing",
        ):
            verify_third_word_proof_index(
                broken,
                Path("evidence/residual-two-word-cases.json"),
            )


if __name__ == "__main__":
    unittest.main()
