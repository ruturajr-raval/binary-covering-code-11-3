from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools/generate_third_word_child_frontier.py"
AUDITOR = ROOT / "tools/audit_third_word_child_frontier.py"
STAGE1 = ROOT / "evidence/residual-two-word-cases.json"
THIRD = ROOT / "evidence/third-word-cases.json"
MINIMUM_DISTANCE = ROOT / "evidence/min-distance-branches.json"
MAXIMUM_DEGREE = ROOT / "evidence/max-degree-reduction.json"
PROOFS = ROOT / "evidence/third-word-proof-index.json"
SUMMARY = ROOT / "evidence/case-reduction-summary.json"
FINAL = ROOT / "evidence/normalized-residual-two-word-cases.json"
RETAINED = ROOT / "research/third-word-child-frontier.json"
ARTIFACTS = ROOT / ".research-artifacts"


def environment() -> dict[str, str]:
    result = dict(os.environ)
    result["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "tools")]
    )
    return result


def arguments(program: Path, output: Path) -> list[str]:
    return [
        sys.executable,
        str(program),
        str(STAGE1),
        str(THIRD),
        str(MINIMUM_DISTANCE),
        str(MAXIMUM_DEGREE),
        str(PROOFS),
        str(SUMMARY),
        str(FINAL),
        str(output),
    ]


class ThirdWordChildFrontierTests(unittest.TestCase):
    def test_retained_manifest_is_reproducible_and_audited(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            generated = Path(directory) / "frontier.json"
            subprocess.run(
                arguments(GENERATOR, generated),
                check=True,
                capture_output=True,
                text=True,
                cwd=directory,
                env=environment(),
            )
            self.assertEqual(
                generated.read_bytes(),
                RETAINED.read_bytes(),
            )
        retained_before = RETAINED.read_bytes()
        result = subprocess.run(
            arguments(AUDITOR, RETAINED),
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=environment(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(RETAINED.read_bytes(), retained_before)
        self.assertIn('"active_parent_child_count": 2548', result.stdout)
        self.assertIn('"live_child_count": 2163', result.stdout)
        self.assertIn('"non_drat_child_count": 2815', result.stdout)

    def test_auditor_rejects_a_corrupted_child(self) -> None:
        frontier = json.loads(RETAINED.read_text(encoding="ascii"))
        frontier["parents"][0]["children"][0]["canonical_word"] += 1
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            corrupted = Path(directory) / "corrupted.json"
            corrupted.write_text(
                json.dumps(frontier, indent=2, sort_keys=True) + "\n",
                encoding="ascii",
            )
            result = subprocess.run(
                arguments(AUDITOR, corrupted),
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("child records are incorrect", result.stderr)

    def test_auditor_rejects_corrupted_semantic_metadata(self) -> None:
        frontier = json.loads(RETAINED.read_text(encoding="ascii"))
        frontier["descriptor_order"] = list(
            reversed(frontier["descriptor_order"])
        )
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            corrupted = Path(directory) / "corrupted-metadata.json"
            corrupted.write_text(
                json.dumps(frontier, indent=2, sort_keys=True) + "\n",
                encoding="ascii",
            )
            result = subprocess.run(
                arguments(AUDITOR, corrupted),
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("descriptor order is incorrect", result.stderr)


if __name__ == "__main__":
    unittest.main()
