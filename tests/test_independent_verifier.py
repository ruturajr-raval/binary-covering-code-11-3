from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "tools/verify_code_independent.py"
BASELINE = ROOT / "data/baseline/k2-11-3-linear-16.txt"


class IndependentVerifierTests(unittest.TestCase):
    def run_verifier(self, code: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                str(code),
                "--length",
                "11",
                "--radius",
                "3",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_accepts_the_baseline(self) -> None:
        result = self.run_verifier(BASELINE)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["valid"])
        self.assertEqual(report["covering_radius"], 3)
        self.assertEqual(
            report["normalized_sha256"],
            "6f056ff8fb88c423155514f959d6f211bcffb2653c85ff6399731fde3827e691",
        )

    def test_rejects_a_deleted_codeword(self) -> None:
        lines = BASELINE.read_text(encoding="ascii").splitlines()
        with tempfile.TemporaryDirectory() as directory:
            damaged = Path(directory) / "damaged.txt"
            damaged.write_text(
                "\n".join(lines[1:]) + "\n",
                encoding="ascii",
            )
            result = self.run_verifier(damaged)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["valid"])
        self.assertTrue(report["uncovered_words"])


if __name__ == "__main__":
    unittest.main()
