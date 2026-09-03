from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECK_PROOF = ROOT / "tools/check_drat_proof.py"
PROVE_TWO_WORD = ROOT / "tools/prove_two_word_case.py"
ARTIFACTS = ROOT / ".research-artifacts"
PYSAT_AVAILABLE = importlib.util.find_spec("pysat") is not None


def canonical_json(record: dict[str, object]) -> bytes:
    return (
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    ).encode("ascii")


def write_fake_checker(
    path: Path,
    *,
    include_timing: bool,
    host_variant: bool = False,
) -> None:
    lines = [
        (
            "c parsing input formula with 99 variables and 88 clauses\n"
            if host_variant
            else "c parsing input formula with 1 variables and 2 clauses\n"
        ),
        "c finished parsing\r",
        "WARNING: ignored deletion\r",
        "s VERIFIED\n",
    ]
    if host_variant:
        lines.append("WARNING: host-specific diagnostic\r")
    if include_timing:
        lines.append("c verification time: 0.001 seconds\n")
    script = (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"sys.stdout.write({''.join(lines)!r})\n"
    )
    path.write_text(script, encoding="ascii")
    path.chmod(0o755)


def run_check(
    checker: Path,
    formula: Path,
    proof: Path,
    summary: Path,
    output: Path,
    *,
    verify_existing: bool = False,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        sys.executable,
        str(CHECK_PROOF),
        str(checker),
        str(formula),
        str(proof),
        str(summary),
        str(output),
        "--checker-commit",
        "a" * 40,
    ]
    if verify_existing:
        arguments.append("--verify-existing")
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


class DratProofReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)

    def prepare_case(
        self,
        directory: Path,
    ) -> tuple[Path, Path, Path]:
        formula = directory / "formula.cnf"
        proof = directory / "proof.drat.gz"
        summary = directory / "proof.json"
        formula.write_text(
            "p cnf 1 2\n1 0\n-1 0\n",
            encoding="ascii",
        )
        proof_bytes = b"0\n"
        compressed = gzip.compress(proof_bytes, mtime=0)
        proof.write_bytes(compressed)
        summary.write_bytes(
            canonical_json(
                {
                    "case_formula_sha256": hashlib.sha256(
                        formula.read_bytes()
                    ).hexdigest(),
                    "case_id": "tiny-unsat",
                    "proof_compressed_sha256": hashlib.sha256(
                        compressed
                    ).hexdigest(),
                    "proof_uncompressed_sha256": hashlib.sha256(
                        proof_bytes
                    ).hexdigest(),
                }
            )
        )
        return formula, proof, summary

    def test_verify_existing_preserves_retained_check_bytes(self) -> None:
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            checker = base / "checker.py"
            output = base / "check.json"
            write_fake_checker(checker, include_timing=True)
            formula, proof, summary = self.prepare_case(base)

            created = run_check(
                checker,
                formula,
                proof,
                summary,
                output,
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            record = json.loads(output.read_text(encoding="ascii"))
            self.assertTrue(record["checker_timing_normalized"])
            self.assertEqual(record["checker_warning_count"], 1)

            retained = output.read_bytes()
            replayed = run_check(
                checker,
                formula,
                proof,
                summary,
                output,
                verify_existing=True,
            )
            self.assertEqual(replayed.returncode, 0, replayed.stderr)
            self.assertEqual(output.read_bytes(), retained)

            write_fake_checker(
                checker,
                include_timing=True,
                host_variant=True,
            )
            portable = run_check(
                checker,
                formula,
                proof,
                summary,
                output,
                verify_existing=True,
            )
            self.assertEqual(portable.returncode, 0, portable.stderr)
            self.assertEqual(output.read_bytes(), retained)

            changed = dict(record)
            changed["return_code"] = 1
            output.write_bytes(canonical_json(changed))
            mismatched = output.read_bytes()
            rejected = run_check(
                checker,
                formula,
                proof,
                summary,
                output,
                verify_existing=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("changed_fields=['return_code']", rejected.stderr)
            self.assertEqual(output.read_bytes(), mismatched)

    def test_missing_timing_line_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            checker = base / "checker.py"
            output = base / "check.json"
            write_fake_checker(checker, include_timing=False)
            formula, proof, summary = self.prepare_case(base)
            result = run_check(
                checker,
                formula,
                proof,
                summary,
                output,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "exactly one verification-time line",
                result.stderr,
            )
            self.assertFalse(output.exists())


@unittest.skipUnless(PYSAT_AVAILABLE, "python-sat is not installed")
class TwoWordProofReplayTests(unittest.TestCase):
    def test_verify_existing_reconstructs_only_the_formula(self) -> None:
        import pysat

        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            base_formula = base / "base.cnf"
            case_manifest = base / "cases.json"
            formula = base / "case.cnf"
            proof = base / "proof.drat.gz"
            summary = base / "proof.json"
            base_formula.write_text(
                "p cnf 3 1\n-2 -3 0\n",
                encoding="ascii",
            )
            case_manifest.write_bytes(
                canonical_json(
                    {
                        "cases": [
                            {
                                "case_id": "tiny-case",
                                "first_word": 1,
                                "minimum_weight": 1,
                                "second_descriptor": {
                                    "intersection": 0,
                                    "weight": 1,
                                },
                                "second_word": 2,
                            }
                        ]
                    }
                )
            )
            expected_formula = (
                b"p cnf 3 3\n-2 -3 0\n2 0\n3 0\n"
            )
            proof_bytes = b"0\n"
            compressed = gzip.compress(proof_bytes, mtime=0)
            proof.write_bytes(compressed)
            summary_record = {
                "base_formula": str(base_formula),
                "base_formula_sha256": hashlib.sha256(
                    base_formula.read_bytes()
                ).hexdigest(),
                "case_formula": str(formula),
                "case_formula_sha256": hashlib.sha256(
                    expected_formula
                ).hexdigest(),
                "case_id": "tiny-case",
                "clauses": 3,
                "proof_compressed": str(proof),
                "proof_compressed_bytes": len(compressed),
                "proof_compressed_sha256": hashlib.sha256(
                    compressed
                ).hexdigest(),
                "proof_format": "text DRAT",
                "proof_lines": 1,
                "proof_uncompressed_bytes": len(proof_bytes),
                "proof_uncompressed_sha256": hashlib.sha256(
                    proof_bytes
                ).hexdigest(),
                "proof_verification": (
                    "recorded in a separate check file"
                ),
                "python_sat_version": pysat.__version__,
                "solve_seconds": 1.0,
                "solver": "cadical300",
                "solver_statistics": {},
                "status": "UNSAT",
                "unit_count": 2,
                "variables": 3,
            }
            summary.write_bytes(canonical_json(summary_record))
            proof_before = proof.read_bytes()
            summary_before = summary.read_bytes()

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROVE_TWO_WORD),
                    str(base_formula),
                    str(case_manifest),
                    "tiny-case",
                    str(formula),
                    str(proof),
                    str(summary),
                    "--length",
                    "2",
                    "--verify-existing",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env={
                    **os.environ,
                    "PYTHONPATH": os.pathsep.join(
                        [str(ROOT / "src"), str(ROOT / "tools")]
                    ),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(formula.read_bytes(), expected_formula)
            self.assertEqual(proof.read_bytes(), proof_before)
            self.assertEqual(summary.read_bytes(), summary_before)


if __name__ == "__main__":
    unittest.main()
