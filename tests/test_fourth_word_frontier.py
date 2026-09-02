from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools/generate_fourth_word_frontier.py"
AUDITOR = ROOT / "tools/audit_fourth_word_frontier.py"
PARENTS = ROOT / "evidence/residual-two-word-cases.json"
THIRD = ROOT / "evidence/third-word-cases.json"
CHILD_FRONTIER = ROOT / "research/third-word-child-frontier.json"
RETAINED = ROOT / "research/fourth-word-hard-frontier.json"
ARTIFACTS = ROOT / ".research-artifacts"
HARD_CHILD_IDS = (
    "w4-weight5-intersection0::orbit-005",
    "w4-weight5-intersection0::orbit-007",
    "w4-weight5-intersection0::orbit-014",
    "w4-weight5-intersection0::orbit-015",
)


def environment() -> dict[str, str]:
    result = dict(os.environ)
    result["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "tools")]
    )
    return result


def generator_command(
    output: Path,
    child_ids: tuple[str, ...] = HARD_CHILD_IDS,
) -> list[str]:
    command = [
        sys.executable,
        str(GENERATOR),
        str(PARENTS),
        str(THIRD),
        str(CHILD_FRONTIER),
        str(output),
    ]
    for child_id in child_ids:
        command.extend(["--child-id", child_id])
    return command


def audit(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(AUDITOR),
            str(PARENTS),
            str(THIRD),
            str(CHILD_FRONTIER),
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=environment(),
    )


class FourthWordFrontierTests(unittest.TestCase):
    def test_retained_frontier_is_reproducible_and_audited(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            generated = Path(directory) / "frontier.json"
            result = subprocess.run(
                generator_command(generated),
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(generated.read_bytes(), RETAINED.read_bytes())
            audited = audit(generated)
            self.assertEqual(audited.returncode, 0, audited.stderr)
            self.assertIn('"valid": true', audited.stdout)

    def test_reordered_child_arguments_are_deterministic(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            generated = Path(directory) / "frontier.json"
            result = subprocess.run(
                generator_command(
                    generated,
                    tuple(reversed(HARD_CHILD_IDS)),
                ),
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(generated.read_bytes(), RETAINED.read_bytes())

    def test_auditor_rejects_corrupted_branch_semantics(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            corrupted = Path(directory) / "corrupted.json"
            manifest = json.loads(RETAINED.read_text(encoding="ascii"))
            manifest["children"][0]["branches"][0][
                "canonical_word"
            ] += 1
            corrupted.write_text(
                json.dumps(
                    manifest,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="ascii",
            )
            audited = audit(corrupted)
        self.assertNotEqual(audited.returncode, 0)
        self.assertIn(
            "does not match independent reconstruction",
            audited.stderr,
        )

    def test_retained_counts_match_the_exact_partition(self) -> None:
        manifest = json.loads(RETAINED.read_text(encoding="ascii"))
        self.assertEqual(
            manifest["counts"],
            {
                "candidate_word_count": 2967,
                "excluded_matching_count": 753,
                "fourth_orbit_count": 350,
                "selected_child_count": 4,
            },
        )
        for child in manifest["children"]:
            classification = child["classification"]
            self.assertEqual(
                sum(
                    count
                    for label, count in classification.items()
                    if label != "ambient_word_count"
                ),
                classification["ambient_word_count"],
            )
            self.assertGreater(
                child["fixed_word_uncovered_count"],
                0,
            )

    def test_generator_rejects_hard_link_output_alias(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            parent = directory_path / "parent.json"
            third = directory_path / "third.json"
            frontier = directory_path / "frontier.json"
            output = directory_path / "output.json"
            parent.write_text("{}\n", encoding="ascii")
            third.write_text("{}\n", encoding="ascii")
            frontier.write_text("{}\n", encoding="ascii")
            os.link(parent, output)
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    str(parent),
                    str(third),
                    str(frontier),
                    str(output),
                    "--child-id",
                    HARD_CHILD_IDS[0],
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "output path aliases a source manifest",
            result.stderr,
        )

    def test_generator_rejects_duplicate_source_files(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            source = Path(directory) / "source.json"
            frontier = Path(directory) / "frontier.json"
            output = Path(directory) / "output.json"
            source.write_text("{}\n", encoding="ascii")
            frontier.write_text("{}\n", encoding="ascii")
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    str(source),
                    str(source),
                    str(frontier),
                    str(output),
                    "--child-id",
                    HARD_CHILD_IDS[0],
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "source manifests must use distinct files",
            result.stderr,
        )

    def test_generator_rejects_hard_link_source_aliases(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            parent = directory_path / "parent.json"
            third = directory_path / "third.json"
            frontier = directory_path / "frontier.json"
            output = directory_path / "output.json"
            parent.write_text("{}\n", encoding="ascii")
            os.link(parent, third)
            frontier.write_text("{}\n", encoding="ascii")
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    str(parent),
                    str(third),
                    str(frontier),
                    str(output),
                    "--child-id",
                    HARD_CHILD_IDS[0],
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "source manifests alias the same file",
            result.stderr,
        )

    def test_generator_rejects_output_alias_to_source_code(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            output = Path(directory) / "generator-link.py"
            os.link(GENERATOR, output)
            result = subprocess.run(
                generator_command(
                    output,
                    (HARD_CHILD_IDS[0], HARD_CHILD_IDS[0]),
                ),
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "output path aliases repository source code",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
