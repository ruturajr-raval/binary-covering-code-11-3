from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fourth_word_symmetry import fourth_orbits, orbit_manifest_digest
from run_fourth_word_portfolio import (
    atomic_write_text,
    statistics_delta,
    worker_failure_records,
)
from run_third_word_child_portfolio import default_code_output_path
from run_two_word_portfolio import case_units, unit_digest
from third_word_symmetry import third_orbits


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_fourth_word_portfolio.py"
PARENTS = ROOT / "evidence/residual-two-word-cases.json"
THIRD = ROOT / "evidence/third-word-cases.json"
CHILD_FRONTIER = ROOT / "research/third-word-child-frontier.json"
FOURTH_FRONTIER = ROOT / "research/fourth-word-hard-frontier.json"
BASE = ROOT / "build/min-distance/k2-11-3-atmost15-mindistance4.cnf"
ARTIFACTS = ROOT / ".research-artifacts"
HARD_CHILD = "w4-weight5-intersection0::orbit-005"


def environment() -> dict[str, str]:
    result = dict(os.environ)
    result["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "tools")]
    )
    return result


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, record: dict[str, object]) -> None:
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )


def branch_digest(branch: dict[str, object]) -> str:
    identity = {
        key: value
        for key, value in branch.items()
        if key != "branch_sha256"
    }
    payload = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def word_weight(word: int) -> int:
    return bin(word).count("1")


def synthetic_fixture(
    directory: Path,
) -> tuple[Path, Path, Path, Path, str]:
    parent_path = directory / "parents.json"
    third_path = directory / "third.json"
    child_frontier_path = directory / "child-frontier.json"
    fourth_frontier_path = directory / "fourth-frontier.json"
    base_formula = directory / "base.cnf"
    length = 3
    parent = {
        "case_id": "tiny",
        "minimum_weight": 1,
        "first_word": 1,
        "second_word": 2,
        "second_descriptor": {
            "weight": 1,
            "intersection": 0,
        },
    }
    units = case_units(parent, length)
    parent["unit_count"] = len(units)
    parent["unit_sha256"] = unit_digest(units)
    write_json(
        parent_path,
        {
            "length": length,
            "cases": [parent],
        },
    )

    orbit_records = third_orbits(parent, length=length)
    retained_orbits = []
    earlier_word_count = 0
    for descriptor, words in orbit_records:
        retained_orbits.append(
            {
                "canonical_word": min(words),
                "descriptor": list(descriptor),
                "earlier_word_count": earlier_word_count,
                "orbit_size": len(words),
            }
        )
        earlier_word_count += len(words)
    write_json(
        third_path,
        {
            "parents": [
                {
                    "parent_case_id": "tiny",
                    "orbits": retained_orbits,
                }
            ]
        },
    )

    descriptor, words = orbit_records[0]
    child_id = "tiny::orbit-000"
    child = {
        "branch_status": "live",
        "canonical_word": min(words),
        "child_id": child_id,
        "descriptor": list(descriptor),
        "earlier_word_count": 0,
        "live_child_index": 0,
        "orbit_size": len(words),
        "parent_orbit_index": 0,
        "parent_status": "active",
    }
    base_formula.write_text("p cnf 8 1\n1 0\n", encoding="ascii")
    child_frontier = {
        "sources": {
            "stage1_parent_manifest": {
                "sha256": file_sha256(parent_path),
            },
            "third_word_manifest": {
                "sha256": file_sha256(third_path),
            },
        },
        "parents": [
            {
                "constraint_profile": {
                    "minimum_distance": {
                        "formula": {
                            "path": str(base_formula.relative_to(ROOT)),
                            "sha256": file_sha256(base_formula),
                        }
                    }
                },
                "matching_eligible": False,
                "parent_case_id": "tiny",
                "status": "active",
                "children": [child],
            }
        ],
    }
    write_json(child_frontier_path, child_frontier)

    grouped, classification = fourth_orbits(
        parent,
        child,
        length=length,
        matching=False,
    )
    branches = []
    earlier_word_count = 0
    for orbit_index, (fourth_descriptor, fourth_words) in enumerate(
        grouped
    ):
        canonical_word = min(fourth_words)
        branch = {
            "branch_id": f"{child_id}::fourth-{orbit_index:03d}",
            "parent_child_id": child_id,
            "fourth_orbit_index": orbit_index,
            "descriptor": list(fourth_descriptor),
            "canonical_word": canonical_word,
            "orbit_size": len(fourth_words),
            "earlier_word_count": earlier_word_count,
            "constraint_units": {
                "selected_word_literal": canonical_word + 1,
                "excluded_earlier_word_count": earlier_word_count,
            },
            "fixed_word_distances": {
                "zero": word_weight(canonical_word),
                "first": word_weight(canonical_word ^ 1),
                "second": word_weight(canonical_word ^ 2),
                "third": word_weight(
                    canonical_word ^ int(child["canonical_word"])
                ),
            },
        }
        branch["branch_sha256"] = branch_digest(branch)
        branches.append(branch)
        earlier_word_count += len(fourth_words)
    fourth_frontier = {
        "sources": {
            "parent_manifest": {
                "sha256": file_sha256(parent_path),
            },
            "third_word_manifest": {
                "sha256": file_sha256(third_path),
            },
            "child_frontier": {
                "sha256": file_sha256(child_frontier_path),
            },
        },
        "children": [
            {
                "parent_child_id": child_id,
                "classification": classification,
                "fourth_orbit_count": len(branches),
                "fourth_orbit_sha256": orbit_manifest_digest(branches),
                "branches": branches,
            }
        ],
    }
    write_json(fourth_frontier_path, fourth_frontier)
    return (
        parent_path,
        third_path,
        child_frontier_path,
        fourth_frontier_path,
        child_id,
    )


class FourthWordPortfolioTests(unittest.TestCase):
    def test_statistics_delta_tracks_added_and_removed_keys(self) -> None:
        self.assertEqual(
            statistics_delta(
                {"conflicts": 4, "decisions": 3},
                {"conflicts": 9, "propagations": 11},
            ),
            {
                "conflicts": 5,
                "decisions": -3,
                "propagations": 11,
            },
        )
        self.assertIsNone(statistics_delta(None, {"conflicts": 1}))

    def test_atomic_write_replaces_complete_file(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            path = Path(directory) / "record.json"
            path.write_text("old\n", encoding="ascii")
            atomic_write_text(path, "new\n")
            self.assertEqual(path.read_text(encoding="ascii"), "new\n")
            self.assertEqual(
                list(path.parent.glob(f".{path.name}.*.tmp")),
                [],
            )

    def test_worker_failure_is_retained_after_all_tasks_finish(
        self,
    ) -> None:
        job = {
            "tasks": [
                {
                    "task_index": 0,
                    "branch": {
                        "branch_id": "branch-000",
                        "fourth_orbit_index": 0,
                    },
                }
            ]
        }
        worker_error, task_errors = worker_failure_records(
            job,
            {0},
            "child",
            "worker exited without completion",
        )
        self.assertEqual(task_errors, [])
        self.assertEqual(
            worker_error,
            {
                "parent_child_id": "child",
                "error": "worker exited without completion",
            },
        )

    def test_rejects_aliasing_output_paths(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            output = Path(directory) / "shared.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(PARENTS),
                    str(THIRD),
                    str(CHILD_FRONTIER),
                    str(FOURTH_FRONTIER),
                    str(output),
                    "--run-record",
                    str(output),
                    "--maximum-branches",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "sources and outputs must use distinct paths",
            result.stderr,
        )

    def test_rejects_output_hard_link_to_source_manifest(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            output = Path(directory) / "parents-link.json"
            os.link(PARENTS, output)
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(PARENTS),
                    str(THIRD),
                    str(CHILD_FRONTIER),
                    str(FOURTH_FRONTIER),
                    str(output),
                    "--parent-child-id",
                    "unknown-child",
                    "--maximum-branches",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "an output path aliases a source file",
            result.stderr,
        )

    def test_rejects_output_hard_link_to_executed_source(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            output = directory_path / "portfolio.json"
            code_output = directory_path / "runner-link.py"
            os.link(RUNNER, code_output)
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(PARENTS),
                    str(THIRD),
                    str(CHILD_FRONTIER),
                    str(FOURTH_FRONTIER),
                    str(output),
                    "--code-output",
                    str(code_output),
                    "--parent-child-id",
                    "unknown-child",
                    "--maximum-branches",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "an output path aliases executed source code",
            result.stderr,
        )

    def test_rejects_hard_linked_output_paths(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            output = directory_path / "portfolio.json"
            run_record = directory_path / "run.json"
            output.write_text("{}\n", encoding="ascii")
            os.link(output, run_record)
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(PARENTS),
                    str(THIRD),
                    str(CHILD_FRONTIER),
                    str(FOURTH_FRONTIER),
                    str(output),
                    "--run-record",
                    str(run_record),
                    "--parent-child-id",
                    "unknown-child",
                    "--maximum-branches",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "output paths alias the same file",
            result.stderr,
        )

    def test_rejects_malformed_branch_manifest(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            (
                parents,
                third,
                child_frontier,
                fourth_frontier,
                _,
            ) = synthetic_fixture(directory_path)
            record = json.loads(
                fourth_frontier.read_text(encoding="ascii")
            )
            record["children"][0]["branches"][-1][
                "fourth_orbit_index"
            ] = -1
            write_json(fourth_frontier, record)
            output = directory_path / "portfolio.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(parents),
                    str(third),
                    str(child_frontier),
                    str(fourth_frontier),
                    str(output),
                    "--maximum-branches",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "fourth-word branch manifest mismatch",
            result.stderr,
        )


@unittest.skipUnless(
    BASE.is_file(),
    "minimum-distance formulas have not been generated",
)
class FourthWordPortfolioIntegrationTests(unittest.TestCase):
    def run_portfolio(
        self,
        directory: Path,
        *options: str,
    ) -> tuple[
        subprocess.CompletedProcess[str],
        Path,
        Path,
    ]:
        output = directory / "portfolio.json"
        run_record = directory / "run.json"
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                str(PARENTS),
                str(THIRD),
                str(CHILD_FRONTIER),
                str(FOURTH_FRONTIER),
                str(output),
                "--solver",
                "glucose4",
                "--workers",
                "1",
                "--parent-child-id",
                HARD_CHILD,
                "--run-record",
                str(run_record),
                "--run-id",
                "fourth-word-portfolio-test",
                *options,
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=environment(),
        )
        return result, output, run_record

    def test_easy_branch_produces_report_and_run_record(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            stale_cover = directory_path / "portfolio-cover.txt"
            stale_cover.write_text("stale\n", encoding="ascii")
            result, output, run_record = self.run_portfolio(
                directory_path,
                "--branch-time-limit",
                "5",
                "--order",
                "reverse-prefix",
                "--maximum-branches",
                "1",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="ascii"))
            provenance = json.loads(
                run_record.read_text(encoding="ascii")
            )
            self.assertEqual(report["status_counts"], {"UNSAT": 1})
            self.assertEqual(
                report["results"][0]["branch_id"],
                f"{HARD_CHILD}::fourth-084",
            )
            self.assertEqual(report["completed_branch_count"], 1)
            self.assertEqual(report["worker_errors"], [])
            self.assertEqual(provenance["result"], "completed")
            self.assertEqual(
                provenance["metrics"]["worker_error_count"],
                0,
            )
            self.assertFalse(stale_cover.exists())
            self.assertEqual(
                provenance["artifacts"][0]["sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )
            self.assertTrue(
                any(
                    artifact["path"]
                    == "tools/run_fourth_word_portfolio.py"
                    for artifact in provenance["inputs"]
                )
            )
            self.assertTrue(
                all(
                    not Path(artifact["path"]).is_absolute()
                    for artifact in provenance["inputs"]
                )
            )

    def test_bounded_incremental_solver_handles_two_branches(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            result, output, run_record = self.run_portfolio(
                Path(directory),
                "--branch-time-limit",
                "0.001",
                "--order",
                "manifest",
                "--maximum-branches",
                "2",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="ascii"))
            provenance = json.loads(
                run_record.read_text(encoding="ascii")
            )
            self.assertEqual(
                [
                    record["fourth_orbit_index"]
                    for record in report["results"]
                ],
                [0, 1],
            )
            self.assertTrue(
                all(
                    record["status"] in {"UNKNOWN", "UNSAT"}
                    for record in report["results"]
                )
            )
            self.assertEqual(report["worker_errors"], [])
            self.assertIn(
                provenance["result"],
                {"completed", "inconclusive"},
            )

    def test_synthetic_sat_run_retains_verified_cover(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            (
                parents,
                third,
                child_frontier,
                fourth_frontier,
                child_id,
            ) = synthetic_fixture(directory_path)
            output = directory_path / "portfolio.json"
            run_record = directory_path / "run.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(parents),
                    str(third),
                    str(child_frontier),
                    str(fourth_frontier),
                    str(output),
                    "--solver",
                    "glucose4",
                    "--branch-time-limit",
                    "5",
                    "--workers",
                    "1",
                    "--parent-child-id",
                    child_id,
                    "--order",
                    "manifest",
                    "--maximum-branches",
                    "2",
                    "--run-record",
                    str(run_record),
                    "--run-id",
                    "fourth-word-synthetic-sat-test",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="ascii"))
            provenance = json.loads(
                run_record.read_text(encoding="ascii")
            )
            cover = default_code_output_path(output)
            self.assertTrue(report["found_cover"])
            self.assertEqual(report["status_counts"], {"SAT": 1})
            self.assertEqual(report["scheduled_branch_count"], 2)
            self.assertEqual(report["completed_branch_count"], 1)
            self.assertEqual(report["worker_errors"], [])
            self.assertTrue(
                {0, 1, 2, 3, 4}
                <= set(report["results"][0]["codewords"])
            )
            self.assertTrue(
                report["results"][0]["verification"]["valid"]
            )
            self.assertTrue(cover.is_file())
            self.assertEqual(provenance["result"], "completed")
            self.assertEqual(len(provenance["artifacts"]), 2)
            self.assertEqual(
                provenance["artifacts"][1]["sha256"],
                hashlib.sha256(cover.read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
