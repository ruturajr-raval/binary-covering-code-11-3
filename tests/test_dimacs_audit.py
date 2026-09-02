from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools/generate_cnf.py"
AUDITOR = ROOT / "tools/audit_covering_cnf.py"


class DimacsAuditTests(unittest.TestCase):
    def generate(self, output: Path) -> None:
        subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                str(output),
                "--length",
                "3",
                "--radius",
                "1",
                "--size",
                "2",
                "--anchor-zero",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(ROOT / "src")},
        )

    def audit(self, path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(AUDITOR),
                str(path),
                "--length",
                "3",
                "--radius",
                "1",
                "--size",
                "2",
                "--anchor-zero",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_accepts_generated_formula(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            formula = Path(directory) / "formula.cnf"
            self.generate(formula)
            result = self.audit(formula)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"valid": true', result.stdout)

    def test_rejects_corrupted_coverage_clause(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            formula = Path(directory) / "formula.cnf"
            self.generate(formula)
            lines = formula.read_text(encoding="ascii").splitlines()
            final_clause = lines[-1].split()
            lines[-1] = " ".join(final_clause[1:])
            formula.write_text("\n".join(lines) + "\n", encoding="ascii")
            result = self.audit(formula)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match its Hamming ball", result.stderr)


if __name__ == "__main__":
    unittest.main()
