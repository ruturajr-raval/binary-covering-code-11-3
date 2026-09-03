from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from generate_fourth_word_rup_plan import (
    atomic_write_bytes,
    begin_plan_transaction,
    durable_replace,
    fsync_directory,
    mark_plan_transaction_ready,
    plan_transaction_paths,
    recover_plan_transaction,
)


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools/generate_fourth_word_rup_plan.py"
AUDITOR = ROOT / "tools/audit_fourth_word_rup_plan.py"
PARENTS = ROOT / "evidence/residual-two-word-cases.json"
THIRD = ROOT / "evidence/third-word-cases.json"
CHILD_FRONTIER = ROOT / "research/third-word-child-frontier.json"
FOURTH_FRONTIER = ROOT / "research/fourth-word-hard-frontier.json"
CLASSIFICATION = ROOT / "evidence/fourth-word-up-classification.json"
PLAN = ROOT / "evidence/fourth-word-rup-proof-plan.json"
ARTIFACTS = ROOT / ".research-artifacts"


def environment() -> dict[str, str]:
    result = dict(os.environ)
    result["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "tools")]
    )
    return result


def record_digest(records: list[dict[str, object]]) -> str:
    payload = "".join(
        f"{record['branch_id']}:{record['branch_sha256']}\n"
        for record in records
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def write_json(path: Path, record: dict[str, object]) -> None:
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )


def audit(
    classification: Path,
    plan: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(AUDITOR),
            str(PARENTS),
            str(THIRD),
            str(CHILD_FRONTIER),
            str(FOURTH_FRONTIER),
            str(classification),
            str(plan),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=environment(),
    )


class FourthWordRupPlanPrerequisiteTests(unittest.TestCase):
    def test_retained_plan_is_available(self) -> None:
        self.assertTrue(CLASSIFICATION.is_file())
        self.assertTrue(PLAN.is_file())


@unittest.skipUnless(
    CLASSIFICATION.is_file() and PLAN.is_file(),
    "retained fourth-word RUP plan is missing",
)
class FourthWordRupPlanTests(unittest.TestCase):
    def test_building_transaction_is_cleaned_for_retry(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            classification = directory_path / "classification.json"
            plan = directory_path / "plan.json"
            journal, staging = plan_transaction_paths(
                classification,
                plan,
                root=ROOT,
            )
            begin_plan_transaction(
                journal,
                staging,
                classification_path=classification,
                plan_path=plan,
                root=ROOT,
            )
            atomic_write_bytes(
                staging / "classification.json",
                b'{"partial": true}\n',
            )
            outcome = recover_plan_transaction(
                journal,
                staging,
                classification_path=classification,
                plan_path=plan,
                root=ROOT,
            )
            self.assertEqual(outcome, "cleaned-building")
            self.assertFalse(journal.exists())
            self.assertFalse(staging.exists())
            self.assertFalse(classification.exists())
            self.assertFalse(plan.exists())

    def test_ready_transaction_completes_partial_promotion(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            classification = directory_path / "classification.json"
            plan = directory_path / "plan.json"
            classification_payload = b'{"classification": true}\n'
            plan_payload = b'{"plan": true}\n'
            journal, staging = plan_transaction_paths(
                classification,
                plan,
                root=ROOT,
            )
            begin_plan_transaction(
                journal,
                staging,
                classification_path=classification,
                plan_path=plan,
                root=ROOT,
            )
            atomic_write_bytes(
                staging / "classification.json",
                classification_payload,
            )
            atomic_write_bytes(staging / "plan.json", plan_payload)
            mark_plan_transaction_ready(
                journal,
                staging,
                classification_path=classification,
                plan_path=plan,
                root=ROOT,
            )
            durable_replace(
                staging / "classification.json",
                classification,
            )

            outcome = recover_plan_transaction(
                journal,
                staging,
                classification_path=classification,
                plan_path=plan,
                root=ROOT,
            )
            self.assertEqual(outcome, "completed-ready")
            self.assertEqual(
                classification.read_bytes(),
                classification_payload,
            )
            self.assertEqual(plan.read_bytes(), plan_payload)
            self.assertFalse(journal.exists())
            self.assertFalse(staging.exists())

    def test_ready_transaction_finishes_after_staging_removal(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            classification = directory_path / "classification.json"
            plan = directory_path / "plan.json"
            journal, staging = plan_transaction_paths(
                classification,
                plan,
                root=ROOT,
            )
            begin_plan_transaction(
                journal,
                staging,
                classification_path=classification,
                plan_path=plan,
                root=ROOT,
            )
            atomic_write_bytes(
                staging / "classification.json",
                b'{"classification": true}\n',
            )
            atomic_write_bytes(
                staging / "plan.json",
                b'{"plan": true}\n',
            )
            mark_plan_transaction_ready(
                journal,
                staging,
                classification_path=classification,
                plan_path=plan,
                root=ROOT,
            )
            durable_replace(
                staging / "classification.json",
                classification,
            )
            durable_replace(staging / "plan.json", plan)
            staging.rmdir()
            fsync_directory(staging.parent)

            outcome = recover_plan_transaction(
                journal,
                staging,
                classification_path=classification,
                plan_path=plan,
                root=ROOT,
            )
            self.assertEqual(outcome, "completed-ready")
            self.assertFalse(journal.exists())

    def test_ready_transaction_rejects_symlinked_staging(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            classification = directory_path / "classification.json"
            plan = directory_path / "plan.json"
            journal, staging = plan_transaction_paths(
                classification,
                plan,
                root=ROOT,
            )
            real_staging = staging.with_name(f"{staging.name}.real")
            begin_plan_transaction(
                journal,
                staging,
                classification_path=classification,
                plan_path=plan,
                root=ROOT,
            )
            atomic_write_bytes(
                staging / "classification.json",
                b'{"classification": true}\n',
            )
            atomic_write_bytes(
                staging / "plan.json",
                b'{"plan": true}\n',
            )
            mark_plan_transaction_ready(
                journal,
                staging,
                classification_path=classification,
                plan_path=plan,
                root=ROOT,
            )
            staging.rename(real_staging)
            staging.symlink_to(real_staging, target_is_directory=True)
            try:
                with self.assertRaises(RuntimeError):
                    recover_plan_transaction(
                        journal,
                        staging,
                        classification_path=classification,
                        plan_path=plan,
                        root=ROOT,
                    )
            finally:
                staging.unlink(missing_ok=True)
                if real_staging.exists():
                    for path in real_staging.iterdir():
                        path.unlink()
                    real_staging.rmdir()
                journal.unlink(missing_ok=True)

    def test_retained_plan_is_reproducible_and_audited(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            classification = directory_path / "classification.json"
            plan = directory_path / "plan.json"
            generated = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    str(PARENTS),
                    str(THIRD),
                    str(CHILD_FRONTIER),
                    str(FOURTH_FRONTIER),
                    str(classification),
                    str(plan),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
            self.assertEqual(
                generated.returncode,
                0,
                generated.stderr,
            )
            self.assertEqual(
                classification.read_bytes(),
                CLASSIFICATION.read_bytes(),
            )
            generated_plan = json.loads(
                plan.read_text(encoding="ascii")
            )
            retained_plan = json.loads(
                PLAN.read_text(encoding="ascii")
            )
            generated_plan["classification"]["path"] = str(
                CLASSIFICATION.relative_to(ROOT)
            )
            self.assertEqual(generated_plan, retained_plan)
            audited = audit(classification, plan)
            self.assertEqual(audited.returncode, 0, audited.stderr)
            self.assertIn('"valid": true', audited.stdout)

    def test_exact_existing_outputs_resume_without_flag(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            classification = directory_path / "classification.json"
            plan = directory_path / "plan.json"
            command = [
                sys.executable,
                str(GENERATOR),
                str(PARENTS),
                str(THIRD),
                str(CHILD_FRONTIER),
                str(FOURTH_FRONTIER),
                str(classification),
                str(plan),
            ]
            first = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            second = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn(
                '"transaction_recovery": '
                '"recognized-committed-outputs"',
                second.stdout,
            )

    def test_exact_counts_and_cross_check_are_retained(self) -> None:
        classification = json.loads(
            CLASSIFICATION.read_text(encoding="ascii")
        )
        self.assertEqual(classification["branch_count"], 350)
        self.assertEqual(classification["rup_conflict_count"], 184)
        self.assertEqual(
            classification["not_rup_conflict_count"],
            166,
        )
        self.assertEqual(classification["solver"], "glucose4")
        self.assertEqual(
            classification["cross_check_solver"],
            "glucose42",
        )
        self.assertIs(classification["solver_agreement"], True)

    def test_status_permutation_with_same_counts_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            classification_path = (
                directory_path / "classification.json"
            )
            plan_path = directory_path / "plan.json"
            classification = json.loads(
                CLASSIFICATION.read_text(encoding="ascii")
            )
            first_closed = next(
                record
                for record in classification["branches"]
                if record["status"] == "rup-conflict"
            )
            first_residual = next(
                record
                for record in classification["branches"]
                if (
                    record["status"] == "not-rup-conflict"
                    and record["parent_child_id"]
                    == first_closed["parent_child_id"]
                )
            )
            first_closed["status"] = "not-rup-conflict"
            first_residual["status"] = "rup-conflict"
            closed = [
                record
                for record in classification["branches"]
                if record["status"] == "rup-conflict"
            ]
            residual = [
                record
                for record in classification["branches"]
                if record["status"] == "not-rup-conflict"
            ]
            classification["closed_set_sha256"] = record_digest(closed)
            classification["residual_set_sha256"] = record_digest(
                residual
            )
            write_json(classification_path, classification)

            plan = json.loads(PLAN.read_text(encoding="ascii"))
            plan["classification"] = {
                "path": str(classification_path.relative_to(ROOT)),
                "sha256": hashlib.sha256(
                    classification_path.read_bytes()
                ).hexdigest(),
            }
            plan["closed_set_sha256"] = record_digest(closed)
            plan["residual_set_sha256"] = record_digest(residual)
            plan["cases"] = [
                {
                    key: record[key]
                    for key in (
                        "branch_id",
                        "branch_sha256",
                        "parent_child_id",
                        "fourth_orbit_index",
                    )
                }
                for record in closed
            ]
            write_json(plan_path, plan)
            audited = audit(classification_path, plan_path)
        self.assertNotEqual(audited.returncode, 0)
        self.assertIn("classification closed set changed", audited.stderr)


if __name__ == "__main__":
    unittest.main()
