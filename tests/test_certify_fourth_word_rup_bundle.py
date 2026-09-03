from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from certify_fourth_word_rup_bundle import (
    CHECKER_PATH,
    PROOF_DIRECTORY,
    PROOF_INDEX,
    REPLAY_ATTESTATION,
    audit_command,
    certify_bundle,
    certification_actions,
    proof_command,
    run_command,
    validate_retained_arguments,
)
from repository_lock import acquire_repository_lock


class CertifyFourthWordRupBundleTests(unittest.TestCase):
    def create_checker(self, root: Path) -> Path:
        checker = root / CHECKER_PATH
        checker.parent.mkdir(parents=True, exist_ok=True)
        checker.write_bytes(b"checker")
        return checker

    def write_retained_argument_records(
        self,
        *,
        root: Path,
        checker: Path,
        checker_commit: str,
        attestation_date: str,
    ) -> None:
        digest = hashlib.sha256(checker.read_bytes()).hexdigest()
        (root / PROOF_INDEX).parent.mkdir(parents=True, exist_ok=True)
        (root / PROOF_INDEX).write_text(
            json.dumps({"checker_commit": checker_commit}),
            encoding="ascii",
        )
        (root / REPLAY_ATTESTATION).write_text(
            json.dumps(
                {
                    "checker": {
                        "commit": checker_commit,
                        "binary_sha256": digest,
                    },
                    "replay_date": attestation_date,
                }
            ),
            encoding="ascii",
        )

    def test_empty_state_creates_attests_and_audits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                certification_actions(
                    proof_directory=root / "proofs",
                    proof_index=root / "index.json",
                    attestation=root / "attestation.json",
                    promotion_journal=root / "journal.json",
                ),
                ["create", "attest", "audit"],
            )

    def test_promoted_bundle_resumes_at_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "proofs").mkdir()
            (root / "index.json").write_text("{}", encoding="ascii")
            self.assertEqual(
                certification_actions(
                    proof_directory=root / "proofs",
                    proof_index=root / "index.json",
                    attestation=root / "attestation.json",
                    promotion_journal=root / "journal.json",
                ),
                ["attest", "audit"],
            )

    def test_completed_bundle_resumes_at_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "proofs").mkdir()
            (root / "index.json").write_text("{}", encoding="ascii")
            (root / "attestation.json").write_text("{}", encoding="ascii")
            self.assertEqual(
                certification_actions(
                    proof_directory=root / "proofs",
                    proof_index=root / "index.json",
                    attestation=root / "attestation.json",
                    promotion_journal=root / "journal.json",
                ),
                ["audit"],
            )

    def test_promotion_journal_reenters_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "journal.json").write_text("{}", encoding="ascii")
            self.assertEqual(
                certification_actions(
                    proof_directory=root / "proofs",
                    proof_index=root / "index.json",
                    attestation=root / "attestation.json",
                    promotion_journal=root / "journal.json",
                ),
                ["create", "attest", "audit"],
            )

    def test_inconsistent_unjournaled_bundle_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "proofs").mkdir()
            with self.assertRaises(RuntimeError):
                certification_actions(
                    proof_directory=root / "proofs",
                    proof_index=root / "index.json",
                    attestation=root / "attestation.json",
                    promotion_journal=root / "journal.json",
                )

    def test_retained_arguments_bind_checker_and_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker = self.create_checker(root)
            self.write_retained_argument_records(
                root=root,
                checker=checker,
                checker_commit="a" * 40,
                attestation_date="2026-09-03",
            )
            validate_retained_arguments(
                root=root,
                checker=str(checker),
                checker_commit="a" * 40,
                attestation_date="2026-09-03",
            )
            with self.assertRaises(RuntimeError):
                validate_retained_arguments(
                    root=root,
                    checker=str(checker),
                    checker_commit="a" * 40,
                    attestation_date="2026-09-02",
                )
            with self.assertRaises(RuntimeError):
                validate_retained_arguments(
                    root=root,
                    checker=str(checker),
                    checker_commit="b" * 40,
                    attestation_date="2026-09-03",
                )

            checker.write_bytes(b"modified checker")
            with self.assertRaises(RuntimeError):
                validate_retained_arguments(
                    root=root,
                    checker=str(checker),
                    checker_commit="a" * 40,
                    attestation_date="2026-09-03",
                )

            checker.write_bytes(b"checker")
            attestation_path = root / REPLAY_ATTESTATION
            attestation = json.loads(
                attestation_path.read_text(encoding="ascii")
            )
            attestation["checker"]["binary_sha256"] = "0" * 64
            attestation_path.write_text(
                json.dumps(attestation),
                encoding="ascii",
            )
            with self.assertRaises(RuntimeError):
                validate_retained_arguments(
                    root=root,
                    checker=str(checker),
                    checker_commit="a" * 40,
                    attestation_date="2026-09-03",
                )

    def test_retained_checker_path_is_repository_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker = self.create_checker(root)
            self.write_retained_argument_records(
                root=root,
                checker=checker,
                checker_commit="a" * 40,
                attestation_date="2026-09-03",
            )
            other_checker = root / "other-checker"
            other_checker.write_bytes(checker.read_bytes())
            with self.assertRaises(RuntimeError):
                validate_retained_arguments(
                    root=root,
                    checker=str(other_checker),
                    checker_commit="a" * 40,
                    attestation_date="2026-09-03",
                )

    def test_retained_checker_rejects_symlinked_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actual = root / "actual"
            checker = actual / "drat-trim-src/drat-trim"
            checker.parent.mkdir(parents=True)
            checker.write_bytes(b"checker")
            try:
                (root / "build").symlink_to(
                    actual,
                    target_is_directory=True,
                )
            except OSError:
                self.skipTest("symbolic links are unavailable")
            canonical_checker = root / CHECKER_PATH
            self.write_retained_argument_records(
                root=root,
                checker=canonical_checker,
                checker_commit="a" * 40,
                attestation_date="2026-09-03",
            )
            with self.assertRaises(RuntimeError):
                validate_retained_arguments(
                    root=root,
                    checker=str(canonical_checker),
                    checker_commit="a" * 40,
                    attestation_date="2026-09-03",
                )

    def test_certifier_runs_create_attest_audit_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker = self.create_checker(root)
            calls = []

            def runner(arguments, *, environment, root):
                calls.append(arguments)
                if "--verify-existing" not in arguments and (
                    "prove_fourth_word_rup_cases.py" in arguments[1]
                ):
                    (root / PROOF_DIRECTORY).mkdir(parents=True)
                    (root / PROOF_INDEX).write_text(
                        json.dumps({"checker_commit": "a" * 40}),
                        encoding="ascii",
                    )
                elif "--attestation-output" in arguments:
                    self.write_retained_argument_records(
                        root=root,
                        checker=checker,
                        checker_commit="a" * 40,
                        attestation_date="2026-09-03",
                    )

            actions = certify_bundle(
                root=root,
                python_command="python",
                checker=str(checker),
                checker_commit="a" * 40,
                attestation_date="2026-09-03",
                environment={},
                runner=runner,
            )
            self.assertEqual(actions, ["create", "attest", "audit"])
            self.assertEqual(
                calls[0],
                proof_command(
                    python_command="python",
                    checker=str(checker),
                    checker_commit="a" * 40,
                ),
            )
            self.assertEqual(
                calls[1][-5:],
                [
                    "--verify-existing",
                    "--attestation-output",
                    str(REPLAY_ATTESTATION),
                    "--attestation-date",
                    "2026-09-03",
                ],
            )
            self.assertEqual(
                calls[2],
                audit_command(python_command="python"),
            )

    def test_certifier_stops_after_command_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def runner(arguments, *, environment, root):
                calls.append(arguments)
                raise RuntimeError("failed")

            with self.assertRaises(RuntimeError):
                certify_bundle(
                    root=Path(directory),
                    python_command="python",
                    checker="checker",
                    checker_commit="a" * 40,
                    attestation_date="2026-09-03",
                    environment={},
                    runner=runner,
                )
            self.assertEqual(len(calls), 1)

    def test_run_command_propagates_inherited_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = acquire_repository_lock(root)
            try:
                environment = dict(os.environ)
                with patch(
                    "certify_fourth_word_rup_bundle.subprocess.run",
                    return_value=SimpleNamespace(returncode=0),
                ) as run:
                    run_command(
                        ["command"],
                        environment=environment,
                        root=root,
                    )
                self.assertEqual(
                    run.call_args.kwargs["pass_fds"],
                    (lock.fileno(),),
                )
            finally:
                lock.close()


if __name__ == "__main__":
    unittest.main()
