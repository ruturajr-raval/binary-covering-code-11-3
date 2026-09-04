from __future__ import annotations

import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fourth_word_drat.proof_core import (
    deterministic_gzip,
    file_metrics,
    materialized_retained_proof,
    run_checker,
)
from fourth_word_drat.secure_io import (
    authenticated_snapshot,
    write_private_file,
)


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "proof-expansion/cli/prove_formula.py"
CHECKER = ROOT / "build/drat-trim-src/drat-trim"
CHECKER_COMMIT = "2e3b2dc0ecf938addbd779d42877b6ed69d9a985"
ARTIFACTS = ROOT / ".research-artifacts"


def environment() -> dict[str, str]:
    result = dict(os.environ)
    result["PYTHONPATH"] = os.pathsep.join(
        [
            str(ROOT / "proof-expansion/src"),
            str(ROOT / "src"),
            str(ROOT / "tools"),
        ]
    )
    return result


def run_cli(
    formula: Path,
    proof: Path,
    summary: Path,
    *,
    verify_existing: bool = False,
    checker: Path = CHECKER,
    production_checker_sha256: str | None = None,
    production_python_sat_version: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-I",
        str(CLI),
        str(formula),
        str(proof),
        str(summary),
        "--case-id",
        "synthetic-xor",
        "--solver",
        "glucose4",
        "--checker",
        str(checker),
        "--checker-commit",
        CHECKER_COMMIT,
    ]
    if verify_existing:
        scratch = Path(
            tempfile.mkdtemp(
                dir=ARTIFACTS,
                prefix="proof-replay-scratch-",
            )
        )
        command.extend(
            [
                "--scratch-directory",
                str(scratch),
                "--verify-existing",
            ]
        )
        if production_checker_sha256 is not None:
            command.extend(
                [
                    "--production-checker-sha256",
                    production_checker_sha256,
                ]
            )
        if production_python_sat_version is not None:
            command.extend(
                [
                    "--production-python-sat-version",
                    production_python_sat_version,
                ]
            )
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=environment(),
        )
    finally:
        if verify_existing:
            shutil.rmtree(scratch)


def write_xor_formula(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "p cnf 2 4",
                "1 2 0",
                "1 -2 0",
                "-1 2 0",
                "-1 -2 0",
                "",
            ]
        ),
        encoding="ascii",
    )


@unittest.skipUnless(
    CHECKER.is_file(),
    "pinned drat-trim checker is missing",
)
class ProofCoreTests(unittest.TestCase):
    def test_build_and_read_only_replay(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "formula.cnf"
            proof = directory_path / "proof.drat.gz"
            summary = directory_path / "proof.json"
            write_xor_formula(formula)
            built = run_cli(formula, proof, summary)
            self.assertEqual(built.returncode, 0, built.stderr)
            completion = json.loads(built.stdout)
            self.assertEqual(
                set(completion),
                {"case_id", "formula_sha256", "verified"},
            )
            self.assertTrue(completion["verified"])
            before_proof = proof.read_bytes()
            before_summary = summary.read_bytes()
            replayed = run_cli(
                formula,
                proof,
                summary,
                verify_existing=True,
            )
            self.assertEqual(replayed.returncode, 0, replayed.stderr)
            completion = json.loads(replayed.stdout)
            self.assertEqual(
                completion["production_checker_sha256"],
                completion["replay_checker_sha256"],
            )
            self.assertEqual(
                completion["production_python_sat_version"],
                completion["replay_python_sat_version"],
            )
            self.assertEqual(proof.read_bytes(), before_proof)
            self.assertEqual(summary.read_bytes(), before_summary)
            report = json.loads(summary.read_text(encoding="ascii"))
            self.assertEqual(
                report["record_type"],
                "solver-generated-drat-core-proof",
            )
            self.assertTrue(report["retained_replay"]["verified"])
            self.assertEqual(
                gzip.decompress(proof.read_bytes())[-2:],
                b"0\n",
            )

    def test_corrupt_proof_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "formula.cnf"
            proof = directory_path / "proof.drat.gz"
            summary = directory_path / "proof.json"
            write_xor_formula(formula)
            built = run_cli(formula, proof, summary)
            self.assertEqual(built.returncode, 0, built.stderr)
            payload = bytearray(proof.read_bytes())
            payload[-1] ^= 1
            proof.write_bytes(payload)
            replayed = run_cli(
                formula,
                proof,
                summary,
                verify_existing=True,
            )
        self.assertNotEqual(replayed.returncode, 0)

    def test_cross_platform_replay_uses_retained_provenance(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "formula.cnf"
            proof = directory_path / "proof.drat.gz"
            summary = directory_path / "proof.json"
            write_xor_formula(formula)
            built = run_cli(formula, proof, summary)
            self.assertEqual(built.returncode, 0, built.stderr)
            record = json.loads(summary.read_text(encoding="ascii"))
            production_checker_sha256 = "a" * 64
            production_python_sat_version = "retained-version"
            record["production"]["checker_binary_sha256"] = (
                production_checker_sha256
            )
            record["production"]["python_sat_version"] = (
                production_python_sat_version
            )
            record["retained_replay"]["checker_binary_sha256"] = (
                production_checker_sha256
            )
            summary.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="ascii",
            )
            before_proof = proof.read_bytes()
            before_summary = summary.read_bytes()
            replayed = run_cli(
                formula,
                proof,
                summary,
                verify_existing=True,
                production_checker_sha256=(
                    production_checker_sha256
                ),
                production_python_sat_version=(
                    production_python_sat_version
                ),
            )
            self.assertEqual(replayed.returncode, 0, replayed.stderr)
            completion = json.loads(replayed.stdout)
            self.assertEqual(
                completion["production_checker_sha256"],
                production_checker_sha256,
            )
            self.assertEqual(
                completion["production_python_sat_version"],
                production_python_sat_version,
            )
            self.assertNotEqual(
                completion["replay_checker_sha256"],
                production_checker_sha256,
            )
            self.assertNotEqual(
                completion["replay_python_sat_version"],
                production_python_sat_version,
            )
            self.assertEqual(proof.read_bytes(), before_proof)
            self.assertEqual(summary.read_bytes(), before_summary)

    def test_cross_platform_replay_rejects_wrong_provenance(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "formula.cnf"
            proof = directory_path / "proof.drat.gz"
            summary = directory_path / "proof.json"
            write_xor_formula(formula)
            built = run_cli(formula, proof, summary)
            self.assertEqual(built.returncode, 0, built.stderr)
            replayed = run_cli(
                formula,
                proof,
                summary,
                verify_existing=True,
                production_checker_sha256="b" * 64,
                production_python_sat_version="retained-version",
            )
        self.assertNotEqual(replayed.returncode, 0)
        self.assertIn(
            "production metadata changed",
            replayed.stderr,
        )

    def test_checker_substitution_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "formula.cnf"
            proof = directory_path / "proof.drat.gz"
            summary = directory_path / "proof.json"
            fake_checker = directory_path / "drat-trim"
            fake_checker.write_bytes(CHECKER.read_bytes())
            fake_checker.chmod(0o755)
            write_xor_formula(formula)
            result = run_cli(
                formula,
                proof,
                summary,
                checker=fake_checker,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checker must be", result.stderr)

    def test_deterministic_streaming_gzip(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            source = directory_path / "proof.drat"
            first = directory_path / "first.gz"
            second = directory_path / "second.gz"
            source.write_bytes(b"1 0\n0\n")
            deterministic_gzip(source, first)
            deterministic_gzip(source, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_checker_output_limit_is_enforced(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            checker = directory_path / "checker"
            checker.write_text(
                (
                    f"#!{sys.executable}\n"
                    "import sys\n"
                    "sys.stdout.write('x' * 4096)\n"
                ),
                encoding="ascii",
            )
            checker.chmod(0o755)
            with self.assertRaisesRegex(
                RuntimeError,
                "checker output exceeds size limit",
            ):
                run_checker(
                    checker,
                    directory_path / "formula.cnf",
                    directory_path / "proof.drat",
                    timeout_seconds=5,
                    max_output_bytes=128,
                )

    def test_malformed_retained_gzip_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            retained_directory = directory_path / "retained"
            scratch = directory_path / "scratch"
            retained_directory.mkdir()
            scratch.mkdir()
            proof = retained_directory / "proof.drat.gz"
            proof.write_bytes(b"not a gzip stream")
            retained = {
                "uncompressed_bytes": 1,
                "uncompressed_lines": 1,
                "uncompressed_sha256": "0" * 64,
                "compressed_bytes": file_metrics(proof)["bytes"],
                "compressed_sha256": file_metrics(proof)["sha256"],
            }
            with self.assertRaisesRegex(
                RuntimeError,
                "gzip stream is invalid",
            ):
                with materialized_retained_proof(
                    proof,
                    retained,
                    scratch_directory=scratch,
                    max_bytes=1024,
                ):
                    pass

    def test_nested_replay_scratch_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            retained_directory = Path(directory) / "retained"
            scratch = retained_directory / "scratch"
            retained_directory.mkdir()
            scratch.mkdir()
            proof = retained_directory / "proof.drat.gz"
            proof.write_bytes(b"unused")
            with self.assertRaisesRegex(
                RuntimeError,
                "outside retained artifacts",
            ):
                with materialized_retained_proof(
                    proof,
                    {},
                    scratch_directory=scratch,
                    max_bytes=1024,
                ):
                    pass

    def test_existing_outputs_are_not_overwritten(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "formula.cnf"
            proof = directory_path / "proof.drat.gz"
            summary = directory_path / "proof.json"
            write_xor_formula(formula)
            proof.write_bytes(b"occupied")
            result = run_cli(formula, proof, summary)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("proof outputs already exist", result.stderr)

    def test_fresh_equivalent_proofs_are_byte_identical(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            outputs = []
            for name in ("first", "second"):
                target = directory_path / name
                target.mkdir()
                formula = target / "formula.cnf"
                proof = target / "proof.drat.gz"
                summary = target / "proof.json"
                write_xor_formula(formula)
                result = run_cli(formula, proof, summary)
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append((proof.read_bytes(), summary.read_bytes()))
            self.assertEqual(outputs[0], outputs[1])
            record = json.loads(outputs[0][1].decode("ascii"))
            self.assertNotIn("solve_seconds", record)
            self.assertNotIn("solver_statistics", record)

    def test_solver_provenance_mutation_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "formula.cnf"
            proof = directory_path / "proof.drat.gz"
            summary = directory_path / "proof.json"
            write_xor_formula(formula)
            built = run_cli(formula, proof, summary)
            self.assertEqual(built.returncode, 0, built.stderr)
            record = json.loads(summary.read_text(encoding="ascii"))
            record["production"]["solver"] = "other"
            summary.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="ascii",
            )
            replayed = run_cli(
                formula,
                proof,
                summary,
                verify_existing=True,
            )
        self.assertNotEqual(replayed.returncode, 0)
        self.assertIn("production metadata changed", replayed.stderr)

    def test_nested_resource_limit_mutation_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "formula.cnf"
            proof = directory_path / "proof.drat.gz"
            summary = directory_path / "proof.json"
            write_xor_formula(formula)
            built = run_cli(formula, proof, summary)
            self.assertEqual(built.returncode, 0, built.stderr)
            record = json.loads(summary.read_text(encoding="ascii"))
            record["resource_limits"]["checker_seconds"] += 1
            summary.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="ascii",
            )
            replayed = run_cli(
                formula,
                proof,
                summary,
                verify_existing=True,
            )
        self.assertNotEqual(replayed.returncode, 0)
        self.assertIn("resource limits changed", replayed.stderr)

    def test_nested_replay_mutation_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "formula.cnf"
            proof = directory_path / "proof.drat.gz"
            summary = directory_path / "proof.json"
            write_xor_formula(formula)
            built = run_cli(formula, proof, summary)
            self.assertEqual(built.returncode, 0, built.stderr)
            record = json.loads(summary.read_text(encoding="ascii"))
            record["retained_replay"]["verified_marker_count"] = 2
            summary.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="ascii",
            )
            replayed = run_cli(
                formula,
                proof,
                summary,
                verify_existing=True,
            )
        self.assertNotEqual(replayed.returncode, 0)
        self.assertIn("replay result is invalid", replayed.stderr)

    def test_private_snapshot_mutation_after_use_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            snapshot = write_private_file(
                directory_path,
                "formula.cnf",
                b"p cnf 0 0\n",
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "identity changed|content changed",
            ):
                with authenticated_snapshot(
                    snapshot,
                    "case formula snapshot",
                ) as snapshot_path:
                    snapshot_path.chmod(0o600)
                    snapshot_path.write_bytes(b"p cnf 1 0\n")

    def test_private_snapshot_replacement_before_use_is_rejected(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            snapshot = write_private_file(
                directory_path,
                "formula.cnf",
                b"p cnf 0 0\n",
            )
            replacement = directory_path / "replacement"
            replacement.write_bytes(b"p cnf 1 0\n")
            os.replace(replacement, snapshot.path)
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                with authenticated_snapshot(
                    snapshot,
                    "case formula snapshot",
                ):
                    pass


if __name__ == "__main__":
    unittest.main()
