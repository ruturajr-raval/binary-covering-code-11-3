from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "tools/write_unit_propagation_proof.py"
ARTIFACTS = ROOT / ".research-artifacts"


def environment() -> dict[str, str]:
    result = dict(os.environ)
    result["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "tools")]
    )
    return result


class UnitPropagationProofTests(unittest.TestCase):
    def test_writes_deterministic_empty_clause_proof(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "formula.cnf"
            proof = directory_path / "proof.drat.gz"
            summary = directory_path / "proof.json"
            formula.write_text(
                "p cnf 1 2\n1 0\n-1 0\n",
                encoding="ascii",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(WRITER),
                    str(formula),
                    str(proof),
                    str(summary),
                    "--case-id",
                    "tiny-unsat",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(summary.read_text(encoding="ascii"))
            compressed = proof.read_bytes()
            self.assertEqual(gzip.decompress(compressed), b"0\n")
            self.assertEqual(
                record["proof_compressed_sha256"],
                hashlib.sha256(compressed).hexdigest(),
            )
            self.assertEqual(
                record["proof_uncompressed_sha256"],
                hashlib.sha256(b"0\n").hexdigest(),
            )
            self.assertEqual(record["proof_strategy"], "empty-clause RUP")
            self.assertEqual(record["status"], "UNSAT")

    def test_rejects_aliasing_outputs(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            formula = Path(directory) / "formula.cnf"
            formula.write_text("p cnf 1 1\n1 0\n", encoding="ascii")
            result = subprocess.run(
                [
                    sys.executable,
                    str(WRITER),
                    str(formula),
                    str(formula),
                    str(Path(directory) / "proof.json"),
                    "--case-id",
                    "alias",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "formula, proof, and summary paths must be distinct",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
