from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools/generate_third_word_child_formula.py"
AUDITOR = ROOT / "tools/audit_third_word_child_formula.py"
PARENTS = ROOT / "evidence/residual-two-word-cases.json"
THIRD = ROOT / "evidence/third-word-cases.json"
FRONTIER = ROOT / "research/third-word-child-frontier.json"
BASE = ROOT / "build/min-distance/k2-11-3-atmost15-mindistance1.cnf"
ARTIFACTS = ROOT / ".research-artifacts"


def environment() -> dict[str, str]:
    result = dict(os.environ)
    result["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "tools")]
    )
    return result


class ThirdWordChildFormulaPrerequisiteTests(unittest.TestCase):
    def test_minimum_distance_formula_is_available(self) -> None:
        self.assertTrue(
            BASE.is_file(),
            "run `make min-distance-branches` before the formula tests",
        )


@unittest.skipUnless(
    BASE.is_file(),
    "minimum-distance formulas have not been generated",
)
class ThirdWordChildFormulaTests(unittest.TestCase):
    def generate(
        self,
        directory: Path,
        child_id: str,
    ) -> tuple[Path, Path, subprocess.CompletedProcess[str]]:
        formula = directory / "formula.cnf"
        metadata = directory / "metadata.json"
        result = subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                str(PARENTS),
                str(THIRD),
                str(FRONTIER),
                child_id,
                str(formula),
                str(metadata),
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=directory,
            env=environment(),
        )
        return formula, metadata, result

    def audit(
        self,
        formula: Path,
        metadata: Path,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(AUDITOR),
                str(formula),
                str(metadata),
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=environment(),
        )

    def test_nonmatching_and_matching_children_are_audited(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        child_ids = (
            "w1-weight1-intersection0::orbit-000",
            "w1-weight2-intersection0::orbit-001",
            "w2-weight2-intersection0::orbit-001",
        )
        for child_id in child_ids:
            with self.subTest(child_id=child_id):
                with tempfile.TemporaryDirectory(
                    dir=ARTIFACTS
                ) as directory:
                    formula, metadata, generated = self.generate(
                        Path(directory),
                        child_id,
                    )
                    self.assertEqual(
                        generated.returncode,
                        0,
                        generated.stderr,
                    )
                    audited = self.audit(formula, metadata)
                    self.assertEqual(
                        audited.returncode,
                        0,
                        audited.stderr,
                    )
                    self.assertIn('"valid": true', audited.stdout)

    def test_excluded_child_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            _, _, result = self.generate(
                Path(directory),
                "w2-weight2-intersection0::orbit-013",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "child is excluded by a retained constraint",
            result.stderr,
        )

    def test_corrupted_formula_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            formula, metadata, generated = self.generate(
                Path(directory),
                "w2-weight2-intersection0::orbit-001",
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            lines = formula.read_text(encoding="ascii").splitlines()
            metadata_record = json.loads(
                metadata.read_text(encoding="ascii")
            )
            selected_line = (
                1
                + int(metadata_record["base_clauses"])
                + int(metadata_record["parent_unit_count"])
            )
            lines[selected_line] = (
                f"-{metadata_record['selected_word_literal']} 0"
            )
            formula.write_text(
                "\n".join(lines) + "\n",
                encoding="ascii",
            )
            metadata_record["formula_sha256"] = hashlib.sha256(
                formula.read_bytes()
            ).hexdigest()
            metadata.write_text(
                json.dumps(
                    metadata_record,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="ascii",
            )
            audited = self.audit(formula, metadata)
        self.assertNotEqual(audited.returncode, 0)
        self.assertIn("child formula clauses are incorrect", audited.stderr)

    def test_base_formula_path_is_bound_to_the_frontier(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula, metadata, generated = self.generate(
                directory_path,
                "w1-weight1-intersection0::orbit-000",
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            alternate_base = directory_path / "alternate-base.cnf"
            alternate_base.write_bytes(BASE.read_bytes())
            metadata_record = json.loads(
                metadata.read_text(encoding="ascii")
            )
            metadata_record["base_formula"] = str(
                alternate_base.relative_to(ROOT)
            )
            metadata.write_text(
                json.dumps(
                    metadata_record,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="ascii",
            )
            audited = self.audit(formula, metadata)
        self.assertNotEqual(audited.returncode, 0)
        self.assertIn(
            "base formula is not the frontier formula",
            audited.stderr,
        )

    def test_matching_eligibility_is_reconstructed(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula, metadata, generated = self.generate(
                directory_path,
                "w1-weight1-intersection0::orbit-000",
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            frontier_record = json.loads(
                FRONTIER.read_text(encoding="ascii")
            )
            parent = next(
                record
                for record in frontier_record["parents"]
                if record["parent_case_id"]
                == "w1-weight1-intersection0"
            )
            parent["matching_eligible"] = True
            alternate_frontier = (
                directory_path / "altered-frontier.json"
            )
            alternate_frontier.write_text(
                json.dumps(
                    frontier_record,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="ascii",
            )
            metadata_record = json.loads(
                metadata.read_text(encoding="ascii")
            )
            metadata_record["frontier_manifest"] = str(
                alternate_frontier.relative_to(ROOT)
            )
            metadata_record["frontier_manifest_sha256"] = (
                hashlib.sha256(
                    alternate_frontier.read_bytes()
                ).hexdigest()
            )
            metadata.write_text(
                json.dumps(
                    metadata_record,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="ascii",
            )
            audited = self.audit(formula, metadata)
        self.assertNotEqual(audited.returncode, 0)
        self.assertIn(
            "frontier matching eligibility is incorrect",
            audited.stderr,
        )

    def test_output_paths_must_be_distinct(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            output = Path(directory) / "shared-output"
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    str(PARENTS),
                    str(THIRD),
                    str(FRONTIER),
                    "w1-weight1-intersection0::orbit-000",
                    str(output),
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "formula and metadata outputs must be distinct",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
