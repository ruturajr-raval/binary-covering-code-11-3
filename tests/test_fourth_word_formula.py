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
GENERATOR = ROOT / "tools/generate_fourth_word_formula.py"
AUDITOR = ROOT / "tools/audit_fourth_word_formula.py"
PARENTS = ROOT / "evidence/residual-two-word-cases.json"
THIRD = ROOT / "evidence/third-word-cases.json"
CHILD_FRONTIER = ROOT / "research/third-word-child-frontier.json"
FOURTH_FRONTIER = ROOT / "research/fourth-word-hard-frontier.json"
BASE = ROOT / "build/min-distance/k2-11-3-atmost15-mindistance4.cnf"
ARTIFACTS = ROOT / ".research-artifacts"


def environment() -> dict[str, str]:
    result = dict(os.environ)
    result["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "tools")]
    )
    return result


class FourthWordFormulaPrerequisiteTests(unittest.TestCase):
    def test_minimum_distance_formula_is_available(self) -> None:
        self.assertTrue(
            BASE.is_file(),
            "run `make min-distance-branches` before formula tests",
        )


@unittest.skipUnless(
    BASE.is_file(),
    "minimum-distance formulas have not been generated",
)
class FourthWordFormulaTests(unittest.TestCase):
    def generate(
        self,
        directory: Path,
        branch_id: str,
    ) -> tuple[Path, Path, subprocess.CompletedProcess[str]]:
        formula = directory / "formula.cnf"
        metadata = directory / "metadata.json"
        result = subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                str(PARENTS),
                str(THIRD),
                str(CHILD_FRONTIER),
                str(FOURTH_FRONTIER),
                branch_id,
                str(formula),
                str(metadata),
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
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

    def test_zero_and_nonzero_prefix_branches_are_audited(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        branch_ids = (
            "w4-weight5-intersection0::orbit-005::fourth-000",
            "w4-weight5-intersection0::orbit-005::fourth-001",
        )
        for branch_id in branch_ids:
            with self.subTest(branch_id=branch_id):
                with tempfile.TemporaryDirectory(
                    dir=ARTIFACTS
                ) as directory:
                    formula, metadata, generated = self.generate(
                        Path(directory),
                        branch_id,
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

    def test_semantic_clause_corruption_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            formula, metadata, generated = self.generate(
                Path(directory),
                "w4-weight5-intersection0::orbit-005::fourth-001",
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            record = json.loads(metadata.read_text(encoding="ascii"))
            lines = formula.read_text(encoding="ascii").splitlines()
            selected_line = 1 + int(
                record["child_formula"]["clauses"]
            )
            lines[selected_line] = (
                f"-{record['selected_fourth_word_literal']} 0"
            )
            formula.write_text(
                "\n".join(lines) + "\n",
                encoding="ascii",
            )
            record["formula_sha256"] = hashlib.sha256(
                formula.read_bytes()
            ).hexdigest()
            metadata.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="ascii",
            )
            audited = self.audit(formula, metadata)
        self.assertNotEqual(audited.returncode, 0)
        self.assertIn(
            "fourth-word formula clauses are incorrect",
            audited.stderr,
        )

    def test_relabelled_frontier_branch_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula, metadata, generated = self.generate(
                directory_path,
                "w4-weight5-intersection0::orbit-005::fourth-001",
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            altered_frontier = directory_path / "frontier.json"
            frontier = json.loads(
                FOURTH_FRONTIER.read_text(encoding="ascii")
            )
            renamed = (
                "w4-weight5-intersection0::orbit-005"
                "::fourth-renamed"
            )
            frontier["children"][0]["branches"][1][
                "branch_id"
            ] = renamed
            altered_frontier.write_text(
                json.dumps(frontier, indent=2, sort_keys=True) + "\n",
                encoding="ascii",
            )
            record = json.loads(metadata.read_text(encoding="ascii"))
            record["branch_id"] = renamed
            record["fourth_frontier"] = str(
                altered_frontier.relative_to(ROOT)
            )
            record["fourth_frontier_sha256"] = hashlib.sha256(
                altered_frontier.read_bytes()
            ).hexdigest()
            metadata.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="ascii",
            )
            audited = self.audit(formula, metadata)
        self.assertNotEqual(audited.returncode, 0)
        self.assertIn(
            "fourth-word branch manifest is incorrect",
            audited.stderr,
        )

    def test_unknown_branch_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            _, _, generated = self.generate(
                Path(directory),
                "w4-weight5-intersection0::orbit-005::fourth-999",
            )
        self.assertNotEqual(generated.returncode, 0)
        self.assertIn("unknown or duplicate branch id", generated.stderr)

    def test_output_paths_must_be_distinct(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            output = Path(directory) / "shared"
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    str(PARENTS),
                    str(THIRD),
                    str(CHILD_FRONTIER),
                    str(FOURTH_FRONTIER),
                    (
                        "w4-weight5-intersection0::orbit-005"
                        "::fourth-000"
                    ),
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

    def test_hard_linked_outputs_are_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "formula.cnf"
            metadata = directory_path / "metadata.json"
            formula.write_text("placeholder\n", encoding="ascii")
            os.link(formula, metadata)
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    str(PARENTS),
                    str(THIRD),
                    str(CHILD_FRONTIER),
                    str(FOURTH_FRONTIER),
                    (
                        "w4-weight5-intersection0::orbit-005"
                        "::fourth-999"
                    ),
                    str(formula),
                    str(metadata),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "formula and metadata outputs alias the same file",
            result.stderr,
        )

    def test_output_alias_to_source_code_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            formula = directory_path / "generator-link.py"
            metadata = directory_path / "metadata.json"
            os.link(GENERATOR, formula)
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    str(PARENTS),
                    str(THIRD),
                    str(CHILD_FRONTIER),
                    str(FOURTH_FRONTIER),
                    (
                        "w4-weight5-intersection0::orbit-005"
                        "::fourth-999"
                    ),
                    str(formula),
                    str(metadata),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "an output path aliases repository source code",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
