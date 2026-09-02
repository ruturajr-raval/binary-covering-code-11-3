from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from run_third_word_child_portfolio import (
    cleanup_jobs,
    default_code_output_path,
    optional_solver_statistics,
    priority_key,
    write_cover_artifact,
)
from third_word_symmetry import third_orbits


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_third_word_child_portfolio.py"
PARENTS = ROOT / "evidence/residual-two-word-cases.json"
THIRD = ROOT / "evidence/third-word-cases.json"
FRONTIER = ROOT / "research/third-word-child-frontier.json"
BASE = ROOT / "build/min-distance/k2-11-3-atmost15-mindistance4.cnf"
ARTIFACTS = ROOT / ".research-artifacts"


def environment() -> dict[str, str]:
    result = dict(os.environ)
    result["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "tools")]
    )
    return result


def temporary_artifact(suffix: str) -> Path:
    handle, name = tempfile.mkstemp(
        dir=ARTIFACTS,
        prefix="portfolio-test-",
        suffix=suffix,
    )
    os.close(handle)
    return Path(name)


class SolverWithStatistics:
    def accum_stats(self) -> dict[str, int]:
        return {"conflicts": 7}


class SolverWithoutStatistics:
    def accum_stats(self) -> dict[str, int]:
        raise NotImplementedError


class FakeProcess:
    def __init__(self) -> None:
        self.alive = True
        self.terminated = 0

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated += 1
        self.alive = False

    def join(self, timeout: int | None = None) -> None:
        del timeout


class FakeReceiver:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class ThirdWordChildPortfolioTests(unittest.TestCase):
    def test_available_statistics_are_retained(self) -> None:
        self.assertEqual(
            optional_solver_statistics(SolverWithStatistics()),
            {"conflicts": 7},
        )

    def test_unavailable_statistics_do_not_discard_result(self) -> None:
        self.assertIsNone(
            optional_solver_statistics(SolverWithoutStatistics())
        )

    def test_priority_order_is_stable(self) -> None:
        def task(
            *,
            case_id: str,
            distance: int,
            matching: bool,
            earlier: int,
        ) -> dict[str, object]:
            return {
                "parent_case": {
                    "case_id": case_id,
                    "minimum_weight": distance,
                    "second_descriptor": {"weight": distance + 1},
                },
                "frontier_parent": {
                    "matching_eligible": matching,
                    "live_child_count": 40,
                },
                "child": {
                    "earlier_word_count": earlier,
                    "parent_orbit_index": 0,
                },
            }

        tasks = [
            task(
                case_id="nonmatching",
                distance=5,
                matching=False,
                earlier=100,
            ),
            task(
                case_id="matching-low",
                distance=3,
                matching=True,
                earlier=100,
            ),
            task(
                case_id="matching-high",
                distance=4,
                matching=True,
                earlier=50,
            ),
        ]
        tasks.sort(key=priority_key)
        self.assertEqual(
            [
                record["parent_case"]["case_id"]
                for record in tasks
            ],
            ["matching-high", "matching-low", "nonmatching"],
        )

    def test_cleanup_terminates_all_jobs(self) -> None:
        processes = [FakeProcess(), FakeProcess()]
        receivers = [FakeReceiver(), FakeReceiver()]
        jobs = [
            {
                "process": process,
                "receiver": receiver,
            }
            for process, receiver in zip(processes, receivers)
        ]
        cleanup_jobs(jobs)
        self.assertEqual(jobs, [])
        self.assertTrue(
            all(process.terminated == 1 for process in processes)
        )
        self.assertTrue(all(receiver.closed for receiver in receivers))

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
                    str(FRONTIER),
                    str(output),
                    "--code-output",
                    str(output),
                    "--maximum-children",
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
            "manifests and all output paths must be distinct",
            result.stderr,
        )

    def test_default_cover_path_and_writer_retain_codewords(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            output = Path(directory) / "portfolio.json"
            cover = default_code_output_path(output)
            artifact = write_cover_artifact(
                cover,
                [0, 3],
                length=2,
                root=ROOT,
            )
            self.assertEqual(
                cover.name,
                "portfolio-cover.txt",
            )
            self.assertEqual(
                cover.read_text(encoding="ascii").splitlines(),
                ["00", "11"],
            )
            self.assertEqual(
                artifact["sha256"],
                hashlib.sha256(cover.read_bytes()).hexdigest(),
            )

    def test_rejects_alias_to_filtered_parent_base_formula(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        frontier_record = json.loads(
            FRONTIER.read_text(encoding="ascii")
        )
        decoy_handle, decoy_name = tempfile.mkstemp(
            dir=ARTIFACTS,
            prefix="portfolio-base-alias-",
            suffix=".cnf",
        )
        os.close(decoy_handle)
        frontier_handle, frontier_name = tempfile.mkstemp(
            dir=ARTIFACTS,
            prefix="portfolio-frontier-",
            suffix=".json",
        )
        os.close(frontier_handle)
        decoy = Path(decoy_name)
        altered_frontier = Path(frontier_name)
        try:
            decoy.write_text("p cnf 1 0\n", encoding="ascii")
            formula_record = frontier_record["parents"][0][
                "constraint_profile"
            ]["minimum_distance"]["formula"]
            formula_record["path"] = str(decoy.relative_to(ROOT))
            formula_record["sha256"] = hashlib.sha256(
                decoy.read_bytes()
            ).hexdigest()
            altered_frontier.write_text(
                json.dumps(
                    frontier_record,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="ascii",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(PARENTS),
                    str(THIRD),
                    str(altered_frontier),
                    str(decoy),
                    "--parent-case-id",
                    "w4-weight5-intersection0",
                    "--maximum-children",
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
                "output path aliases a retained base formula",
                result.stderr,
            )
        finally:
            decoy.unlink(missing_ok=True)
            altered_frontier.unlink(missing_ok=True)


@unittest.skipUnless(
    BASE.is_file(),
    "minimum-distance formulas have not been generated",
)
class ThirdWordChildPortfolioIntegrationTests(unittest.TestCase):
    def test_easy_child_produces_ordered_report_and_run_record(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            output = directory_path / "portfolio.json"
            run_record = directory_path / "run.json"
            stale_cover = default_code_output_path(output)
            stale_cover.write_text("stale\n", encoding="ascii")
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(PARENTS),
                    str(THIRD),
                    str(FRONTIER),
                    str(output),
                    "--solver",
                    "cadical300",
                    "--child-time-limit",
                    "5",
                    "--workers",
                    "1",
                    "--parent-case-id",
                    "w4-weight5-intersection0",
                    "--start-live-index",
                    "2030",
                    "--end-live-index",
                    "2031",
                    "--order",
                    "live-index",
                    "--run-record",
                    str(run_record),
                    "--run-id",
                    "portfolio-integration-test",
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
            self.assertEqual(
                report["status_counts"],
                {"UNSAT": 1},
            )
            self.assertEqual(
                [record["task_index"] for record in report["results"]],
                [0],
            )
            self.assertEqual(
                provenance["run_id"],
                "portfolio-integration-test",
            )
            self.assertEqual(provenance["result"], "completed")
            self.assertFalse(stale_cover.exists())
            self.assertEqual(
                provenance["command"][:3],
                ["env", "PYTHONPATH=src:tools", "python"],
            )
            self.assertIn(
                provenance["environment"]["git_worktree"],
                {"clean", "dirty"},
            )
            self.assertEqual(
                provenance["artifacts"][0]["sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )
            self.assertTrue(
                any(
                    artifact["path"]
                    == "tools/run_third_word_child_portfolio.py"
                    for artifact in provenance["inputs"]
                )
            )
            self.assertTrue(
                all(
                    not Path(artifact["path"]).is_absolute()
                    for artifact in provenance["inputs"]
                )
            )

    def test_synthetic_sat_run_retains_default_cover(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        paths = [
            temporary_artifact(".parents.json"),
            temporary_artifact(".third.json"),
            temporary_artifact(".frontier.json"),
            temporary_artifact(".cnf"),
            temporary_artifact(".output.json"),
        ]
        (
            parent_path,
            third_path,
            frontier_path,
            base_formula,
            output,
        ) = paths
        output.unlink()
        run_record = output.with_name(
            f"{output.stem}-run.json"
        )
        cover = default_code_output_path(output)
        try:
            parent = {
                "case_id": "tiny",
                "minimum_weight": 1,
                "first_word": 1,
                "second_word": 2,
                "second_descriptor": {
                    "weight": 1,
                    "intersection": 0,
                },
                "unit_count": 2,
                "unit_sha256": hashlib.sha256(
                    b"2\n3\n"
                ).hexdigest(),
            }
            parent_manifest = {
                "length": 3,
                "cases": [parent],
            }
            parent_path.write_text(
                json.dumps(
                    parent_manifest,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="ascii",
            )
            orbit_records = third_orbits(parent, length=3)
            descriptor, words = orbit_records[0]
            canonical_word = min(words)
            third_manifest = {
                "parents": [
                    {
                        "parent_case_id": "tiny",
                        "orbits": [
                            {
                                "canonical_word": min(orbit_words),
                                "descriptor": list(orbit_descriptor),
                                "earlier_word_count": sum(
                                    len(previous_words)
                                    for _, previous_words
                                    in orbit_records[:orbit_index]
                                ),
                                "orbit_size": len(orbit_words),
                            }
                            for orbit_index, (
                                orbit_descriptor,
                                orbit_words,
                            ) in enumerate(orbit_records)
                        ],
                    }
                ]
            }
            third_path.write_text(
                json.dumps(
                    third_manifest,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="ascii",
            )
            base_formula.write_text(
                "p cnf 8 0\n",
                encoding="ascii",
            )
            frontier = {
                "sources": {
                    "stage1_parent_manifest": {
                        "sha256": hashlib.sha256(
                            parent_path.read_bytes()
                        ).hexdigest(),
                    },
                    "third_word_manifest": {
                        "sha256": hashlib.sha256(
                            third_path.read_bytes()
                        ).hexdigest(),
                    },
                },
                "parents": [
                    {
                        "constraint_profile": {
                            "minimum_distance": {
                                "formula": {
                                    "path": str(
                                        base_formula.relative_to(ROOT)
                                    ),
                                    "sha256": hashlib.sha256(
                                        base_formula.read_bytes()
                                    ).hexdigest(),
                                }
                            }
                        },
                        "live_child_count": 1,
                        "matching_eligible": False,
                        "parent_case_id": "tiny",
                        "status": "active",
                        "children": [
                            {
                                "branch_status": "live",
                                "canonical_word": canonical_word,
                                "child_id": "tiny::orbit-000",
                                "descriptor": list(descriptor),
                                "earlier_word_count": 0,
                                "live_child_index": 0,
                                "orbit_size": len(words),
                                "parent_orbit_index": 0,
                                "parent_status": "active",
                            }
                        ],
                    }
                ],
            }
            frontier_path.write_text(
                json.dumps(
                    frontier,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="ascii",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    str(parent_path),
                    str(third_path),
                    str(frontier_path),
                    str(output),
                    "--solver",
                    "cadical300",
                    "--child-time-limit",
                    "5",
                    "--workers",
                    "1",
                    "--order",
                    "live-index",
                    "--run-id",
                    "portfolio-synthetic-sat-test",
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
            self.assertTrue(report["found_cover"])
            self.assertEqual(report["status_counts"], {"SAT": 1})
            codewords = report["results"][0]["codewords"]
            self.assertTrue({1, 2, canonical_word} <= set(codewords))
            self.assertEqual(
                cover.read_text(encoding="ascii").splitlines(),
                [f"{word:03b}" for word in sorted(codewords)],
            )
            self.assertEqual(len(provenance["artifacts"]), 2)
            self.assertEqual(
                provenance["artifacts"][1]["path"],
                str(cover.relative_to(ROOT)),
            )
            self.assertEqual(
                provenance["artifacts"][1]["sha256"],
                hashlib.sha256(cover.read_bytes()).hexdigest(),
            )
        finally:
            for path in [
                *paths,
                run_record,
                cover,
            ]:
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
