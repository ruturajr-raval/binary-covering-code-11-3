from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "proof-expansion/cli/generate_plan.py"
AUDITOR = ROOT / "proof-expansion/cli/audit_plan.py"
PARENTS = ROOT / "evidence/residual-two-word-cases.json"
THIRD = ROOT / "evidence/third-word-cases.json"
CHILD_FRONTIER = ROOT / "research/third-word-child-frontier.json"
FOURTH_FRONTIER = ROOT / "research/fourth-word-hard-frontier.json"
CLASSIFICATION = ROOT / "evidence/fourth-word-up-classification.json"
RUP_INDEX = ROOT / "evidence/fourth-word-rup-proof-index-v1.json"
RUP_ATTESTATION = (
    ROOT / "evidence/fourth-word-rup-replay-attestation-v1.json"
)
RUP_BUNDLE = ROOT / "evidence/fourth-word-rup-bundle-v1.sha256"
RUP_REVISION = ROOT / "evidence/fourth-word-rup-revision-v1.json"
SCOUT = ROOT / "research/runs/2026-09-02-fourth-word-portfolio.json"
SCOUT_RUN = (
    ROOT / "research/runs/2026-09-02-fourth-word-portfolio-run.json"
)
LITERATURE_AUDIT = ROOT / "docs/LITERATURE_AUDIT.md"
PLAN = (
    ROOT
    / "proof-expansion/evidence/fourth-word-solver-drat-plan-v2.json"
)
ARTIFACTS = ROOT / ".research-artifacts"


def environment() -> dict[str, str]:
    result = dict(os.environ)
    result["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "tools")]
    )
    return result


def write_json(path: Path, record: dict[str, object]) -> None:
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )


def generate(
    output: Path,
    *,
    scout: Path = SCOUT,
    scout_run: Path = SCOUT_RUN,
    literature_audit: Path = LITERATURE_AUDIT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            str(GENERATOR),
            str(PARENTS),
            str(THIRD),
            str(CHILD_FRONTIER),
            str(FOURTH_FRONTIER),
            str(CLASSIFICATION),
            str(RUP_INDEX),
            str(RUP_ATTESTATION),
            str(RUP_BUNDLE),
            str(RUP_REVISION),
            str(scout),
            str(scout_run),
            str(literature_audit),
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=environment(),
    )


def audit(
    plan: Path,
    *,
    scout: Path = SCOUT,
    scout_run: Path = SCOUT_RUN,
    literature_audit: Path = LITERATURE_AUDIT,
    expected_plan_sha256: str | None = None,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        sys.executable,
        "-I",
        str(AUDITOR),
        str(PARENTS),
        str(THIRD),
        str(CHILD_FRONTIER),
        str(FOURTH_FRONTIER),
        str(CLASSIFICATION),
        str(RUP_INDEX),
        str(RUP_ATTESTATION),
        str(RUP_BUNDLE),
        str(RUP_REVISION),
        str(scout),
        str(scout_run),
        str(literature_audit),
        str(plan),
    ]
    if expected_plan_sha256 is not None:
        arguments.extend(
            ["--expected-plan-sha256", expected_plan_sha256]
        )
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=environment(),
    )


class FourthWordDratPlanPrerequisiteTests(unittest.TestCase):
    def test_retained_plan_is_available(self) -> None:
        self.assertTrue(PLAN.is_file())


@unittest.skipUnless(
    PLAN.is_file(),
    "retained fourth-word DRAT plan is missing",
)
class FourthWordDratPlanTests(unittest.TestCase):
    def test_retained_plan_audits(self) -> None:
        result = audit(PLAN)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"case_count": 140', result.stdout)
        self.assertIn('"remaining_count": 26', result.stdout)
        self.assertIn('"valid": true', result.stdout)

    def test_caller_plan_digest_mismatch_is_rejected(self) -> None:
        result = audit(
            PLAN,
            expected_plan_sha256="0" * 64,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "proof plan digest differs from caller snapshot",
            result.stderr,
        )

    def test_retained_plan_is_reproducible(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            generated_plan = Path(directory) / "plan.json"
            result = generate(generated_plan)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                generated_plan.read_bytes(),
                PLAN.read_bytes(),
            )

    def test_case_identity_mutation_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            altered = Path(directory) / "plan.json"
            record = json.loads(PLAN.read_text(encoding="ascii"))
            record["cases"][0]["branch_sha256"] = "0" * 64
            write_json(altered, record)
            result = audit(altered)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "DRAT proof plan does not match reconstruction",
            result.stderr,
        )

    def test_scout_artifact_hash_mutation_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            altered_run = directory_path / "run.json"
            run = json.loads(SCOUT_RUN.read_text(encoding="ascii"))
            run["artifacts"][0]["sha256"] = "0" * 64
            write_json(altered_run, run)
            altered_plan = directory_path / "plan.json"
            plan = json.loads(PLAN.read_text(encoding="ascii"))
            plan["sources"]["scout_run_record"] = {
                "path": str(altered_run.relative_to(ROOT)),
                "sha256": hashlib.sha256(
                    altered_run.read_bytes()
                ).hexdigest(),
            }
            write_json(altered_plan, plan)
            result = audit(
                altered_plan,
                scout_run=altered_run,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "scout run-record authentication failed",
            result.stderr,
        )

    def test_coordinated_scout_status_swap_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            altered_scout = directory_path / "scout.json"
            altered_run = directory_path / "run.json"
            scout = json.loads(SCOUT.read_text(encoding="ascii"))
            selected = next(
                result
                for result in scout["results"]
                if result["branch_id"]
                == (
                    "w4-weight5-intersection0::orbit-005"
                    "::fourth-030"
                )
            )
            remaining = next(
                result
                for result in scout["results"]
                if result["branch_id"]
                == (
                    "w4-weight5-intersection0::orbit-005"
                    "::fourth-012"
                )
            )
            selected["status"] = "UNKNOWN"
            selected["timed_out"] = True
            remaining["status"] = "UNSAT"
            remaining["timed_out"] = False
            scout["run_record"] = str(altered_run.relative_to(ROOT))
            write_json(altered_scout, scout)

            run = json.loads(SCOUT_RUN.read_text(encoding="ascii"))
            run["artifacts"] = [
                {
                    "path": str(altered_scout.relative_to(ROOT)),
                    "sha256": hashlib.sha256(
                        altered_scout.read_bytes()
                    ).hexdigest(),
                }
            ]
            write_json(altered_run, run)
            output = directory_path / "plan.json"
            result = generate(
                output,
                scout=altered_scout,
                scout_run=altered_run,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("selected DRAT case set changed", result.stderr)

    def test_incomplete_literature_audit_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            literature = directory_path / "literature.md"
            literature.write_text(
                "Audit date: 2026-09-03\n",
                encoding="ascii",
            )
            output = directory_path / "plan.json"
            result = generate(
                output,
                literature_audit=literature,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "literature audit does not support the inherited bound",
            result.stderr,
        )

    def test_unchecked_local_bytecode_is_ignored(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        source = ROOT / "tools/manage_fourth_word_rup_revision.py"
        cache = Path(importlib.util.cache_from_source(str(source)))
        cache.parent.mkdir(exist_ok=True)
        original = cache.read_bytes() if cache.exists() else None
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            fake_source = Path(directory) / "malicious.py"
            fake_source.write_text(
                "raise RuntimeError('unchecked bytecode executed')\n",
                encoding="ascii",
            )
            try:
                py_compile.compile(
                    str(fake_source),
                    cfile=str(cache),
                    doraise=True,
                    invalidation_mode=(
                        py_compile.PycInvalidationMode.UNCHECKED_HASH
                    ),
                )
                result = audit(PLAN)
            finally:
                if original is None:
                    cache.unlink(missing_ok=True)
                else:
                    cache.write_bytes(original)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_output_requires_verify_mode(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            output = Path(directory) / "plan.json"
            output.write_text("{}\n", encoding="ascii")
            result = generate(output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("output already exists", result.stderr)


if __name__ == "__main__":
    unittest.main()
