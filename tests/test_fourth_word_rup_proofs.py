from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from prove_fourth_word_rup_cases import (
    PROOF_BYTES,
    PROOF_COMPRESSED,
    begin_promotion_build,
    branch_slug,
    directory_sha256,
    interpreter_path_record,
    measure_interpreter,
    promote_bundle,
    recover_promotion,
    repository_path,
    validate_check,
)
from audit_fourth_word_rup_proofs import (
    validate_pipeline_provenance,
    validate_replay_attestation,
)


ROOT = Path(__file__).resolve().parents[1]
AUDITOR = ROOT / "tools/audit_fourth_word_rup_proofs.py"
PARENTS = ROOT / "evidence/residual-two-word-cases.json"
THIRD = ROOT / "evidence/third-word-cases.json"
CHILD_FRONTIER = ROOT / "research/third-word-child-frontier.json"
FOURTH_FRONTIER = ROOT / "research/fourth-word-hard-frontier.json"
CLASSIFICATION = ROOT / "evidence/fourth-word-up-classification.json"
PLAN = ROOT / "evidence/fourth-word-rup-proof-plan.json"
INDEX = ROOT / "evidence/fourth-word-rup-proof-index-v1.json"
PROOF_DIRECTORY = ROOT / "evidence/proofs/fourth-word-rup-v1"
ATTESTATION = (
    ROOT / "evidence/fourth-word-rup-replay-attestation-v1.json"
)
ARTIFACTS = ROOT / ".research-artifacts"
CERTIFIED_PIPELINE_REVISION = (
    "7f5a3b524d703985b5e6c36270173578598c8b3a"
)


def materialize_certified_pipeline(destination: Path) -> Path:
    index = json.loads(INDEX.read_text(encoding="ascii"))
    paths = {
        record["path"]
        for record in index["pipeline_files"].values()
    }
    listing = subprocess.run(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            CERTIFIED_PIPELINE_REVISION,
            "--",
            "src",
            "tools",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths.update(
        path
        for path in listing.stdout.splitlines()
        if path.endswith(".py")
    )
    for path in sorted(paths):
        payload = subprocess.run(
            [
                "git",
                "show",
                f"{CERTIFIED_PIPELINE_REVISION}:{path}",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        output = destination / path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    return destination


def environment() -> dict[str, str]:
    result = dict(os.environ)
    result["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "tools")]
    )
    return result


def valid_check() -> dict[str, object]:
    output = [
        "c UNSAT via unit propagation on the input instance",
        "s VERIFIED",
        "c verification time: <elapsed>",
    ]
    stable_output = "\n".join(output) + "\n"
    return {
        "case_id": "case",
        "checker": "drat-trim",
        "checker_commit": (
            "2e3b2dc0ecf938addbd779d42877b6ed69d9a985"
        ),
        "formula_sha256": "a" * 64,
        "proof_compressed_sha256": hashlib.sha256(
            PROOF_COMPRESSED
        ).hexdigest(),
        "proof_uncompressed_sha256": hashlib.sha256(
            PROOF_BYTES
        ).hexdigest(),
        "return_code": 0,
        "verified": True,
        "checker_output_sha256": hashlib.sha256(
            stable_output.encode("utf-8")
        ).hexdigest(),
        "checker_output_line_count": len(output),
        "checker_warning_count": 0,
        "checker_timing_normalized": True,
        "checker_output": output,
    }


def valid_attestation() -> tuple[
    dict[str, object],
    dict[str, object],
]:
    digest = "a" * 64
    index = {
        "path": "evidence/fourth-word-rup-proof-index-v1.json",
        "sha256": digest,
    }
    pipeline_files = {
        "proof_orchestrator": {
            "path": "tools/prove_fourth_word_rup_cases.py",
            "sha256": digest,
        }
    }
    pipeline_tree = {
        "roots": ["src", "tools"],
        "file_count": 1,
        "sha256": digest,
    }
    native_modules = {
        name: {
            "filename": f"{name}.so",
            "sha256": digest,
        }
        for name in ("pycard", "pyformula", "pysolvers")
    }
    record = {
        "record_type": "fourth-word-rup-replay-attestation",
        "schema_version": 3,
        "provenance": {
            "scope": "local self-attestation",
            "externally_signed": False,
        },
        "replay_date": "2026-09-03",
        "proof_index": index,
        "checker": {
            "name": "drat-trim",
            "repository": "https://github.com/marijnheule/drat-trim.git",
            "commit": "2e3b2dc0ecf938addbd779d42877b6ed69d9a985",
            "binary_sha256": digest,
        },
        "pipeline_files": pipeline_files,
        "pipeline_python_tree": pipeline_tree,
        "environment": {
            "python_implementation": "CPython",
            "python_version": "3.12.11",
            "python_executable_sha256": digest,
            "python_executable_path": {
                "scope": "repository-relative",
                "value": ".venv/bin/python",
            },
            "python_sat_version": "1.9.dev15",
            "python_sat_distribution_version": "1.9.dev15",
            "python_sat_tree": {
                "root": "pysat",
                "file_count": 28,
                "sha256": digest,
            },
            "python_sat_native_modules": native_modules,
            "platform_system": "Linux",
            "platform_machine": "x86_64",
        },
        "case_count": 184,
        "case_outcomes_sha256": digest,
        "closed_set_sha256": "b" * 64,
        "residual_set_sha256": "c" * 64,
        "all_verified": True,
    }
    expected = {
        "expected_index": index,
        "expected_pipeline_files": pipeline_files,
        "expected_pipeline_python_tree": pipeline_tree,
        "expected_python_sat_version": "1.9.dev15",
        "expected_case_count": 184,
        "expected_case_outcomes_sha256": digest,
        "expected_closed_set_sha256": "b" * 64,
        "expected_residual_set_sha256": "c" * 64,
    }
    return record, expected


class ReplayAttestationSchemaTests(unittest.TestCase):
    def test_valid_record_passes(self) -> None:
        record, expected = valid_attestation()
        validate_replay_attestation(record, **expected)

    def test_non_integer_counts_are_rejected(self) -> None:
        for value in (True, "184", 184.0, 184.9):
            with self.subTest(value=value):
                record, expected = valid_attestation()
                record["case_count"] = value
                with self.assertRaises(SystemExit):
                    validate_replay_attestation(record, **expected)
        for value in (True, "28", 28.0, 28.9):
            with self.subTest(value=value):
                record, expected = valid_attestation()
                record["environment"]["python_sat_tree"][
                    "file_count"
                ] = value
                with self.assertRaises(SystemExit):
                    validate_replay_attestation(record, **expected)

    def test_non_integer_schema_versions_are_rejected(self) -> None:
        for value in (True, "3", 3.0):
            with self.subTest(value=value):
                record, expected = valid_attestation()
                record["schema_version"] = value
                with self.assertRaises(SystemExit):
                    validate_replay_attestation(record, **expected)

    def test_provenance_and_extra_keys_are_rejected(self) -> None:
        record, expected = valid_attestation()
        record["provenance"]["externally_signed"] = True
        with self.assertRaises(SystemExit):
            validate_replay_attestation(record, **expected)
        record, expected = valid_attestation()
        record["unexpected"] = True
        with self.assertRaises(SystemExit):
            validate_replay_attestation(record, **expected)

    def test_native_module_records_are_required(self) -> None:
        record, expected = valid_attestation()
        del record["environment"]["python_sat_native_modules"]["pysolvers"]
        with self.assertRaises(SystemExit):
            validate_replay_attestation(record, **expected)


class FourthWordRupProofPrerequisiteTests(unittest.TestCase):
    def test_retained_proof_bundle_is_available(self) -> None:
        self.assertTrue(CLASSIFICATION.is_file())
        self.assertTrue(PLAN.is_file())
        self.assertTrue(INDEX.is_file())
        self.assertTrue(PROOF_DIRECTORY.is_dir())
        self.assertTrue(ATTESTATION.is_file())


class FourthWordRupProofUnitTests(unittest.TestCase):
    def test_proof_blob_and_slug_are_canonical(self) -> None:
        self.assertEqual(PROOF_BYTES, b"0\n")
        self.assertEqual(
            hashlib.sha256(PROOF_COMPRESSED).hexdigest(),
            "89ed3b723e0e40d8957a2df55fcb04d57b6d95fa665c5fe67b098df7f29694ae",
        )
        self.assertEqual(
            branch_slug(
                "w4-weight5-intersection0"
                "::orbit-005::fourth-084"
            ),
            "w4-weight5-intersection0--orbit-005--fourth-084",
        )

    def test_check_validation_requires_unit_propagation(self) -> None:
        check = valid_check()
        validate_check(
            check,
            branch_id="case",
            formula_sha256="a" * 64,
            checker_commit=check["checker_commit"],
        )
        check["checker_output"] = ["s VERIFIED"]
        check["checker_output_sha256"] = hashlib.sha256(
            b"s VERIFIED\n"
        ).hexdigest()
        with self.assertRaisesRegex(
            RuntimeError,
            "did not verify by unit propagation",
        ):
            validate_check(
                check,
                branch_id="case",
                formula_sha256="a" * 64,
                checker_commit=check["checker_commit"],
            )

    def test_repository_path_rejects_symbolic_link_components(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            target = directory_path / "target"
            target.mkdir()
            link = directory_path / "link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(
                SystemExit,
                "contains a symbolic link",
            ):
                repository_path(link / "artifact.json", ROOT)

    def test_interrupted_bundle_promotion_is_recovered(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            staging = directory_path / ".proofs.test"
            staging.mkdir()
            (staging / "proof").write_text("proof\n", encoding="ascii")
            proof_directory = directory_path / "proofs"
            index = directory_path / "index.json"
            staged_index = directory_path / ".index.json.staged"
            staged_index.write_text(
                '{"all_verified": true}\n',
                encoding="ascii",
            )
            journal = directory_path / "promotion.json"
            journal.write_text(
                json.dumps(
                    {
                        "record_type": "fourth-word-rup-promotion",
                        "schema_version": 2,
                        "phase": "ready",
                        "proof_directory": str(
                            proof_directory.relative_to(ROOT)
                        ),
                        "proof_directory_sha256": directory_sha256(
                            staging
                        ),
                        "output": str(index.relative_to(ROOT)),
                        "output_sha256": hashlib.sha256(
                            staged_index.read_bytes()
                        ).hexdigest(),
                        "staging_directory": str(
                            staging.relative_to(ROOT)
                        ),
                        "staged_index": str(
                            staged_index.relative_to(ROOT)
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="ascii",
            )
            os.replace(staging, proof_directory)
            recovered = recover_promotion(
                root=ROOT,
                proof_directory=proof_directory,
                output_path=index,
                journal_path=journal,
            )
            self.assertEqual(recovered, "ready-completed")
            self.assertTrue(proof_directory.is_dir())
            self.assertEqual(index.read_bytes(), b'{"all_verified": true}\n')
            self.assertFalse(staged_index.exists())
            self.assertFalse(journal.exists())

    def test_building_journal_cleans_partial_staging(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            staging = directory_path / ".proofs.test"
            proof_directory = directory_path / "proofs"
            index = directory_path / "index.json"
            staged_index = directory_path / ".index.json.staged"
            journal = directory_path / "promotion.json"
            begin_promotion_build(
                root=ROOT,
                proof_directory=proof_directory,
                output_path=index,
                staging_directory=staging,
                staged_index=staged_index,
                journal_path=journal,
            )
            staging.mkdir()
            (staging / "partial").write_text("partial\n", encoding="ascii")
            outcome = recover_promotion(
                root=ROOT,
                proof_directory=proof_directory,
                output_path=index,
                journal_path=journal,
            )
            self.assertEqual(outcome, "building-cleared")
            self.assertFalse(staging.exists())
            self.assertFalse(journal.exists())

    def test_promotion_rejects_mutation_after_audit(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            staging = directory_path / ".proofs.test"
            staging.mkdir()
            proof = staging / "proof"
            proof.write_text("proof\n", encoding="ascii")
            proof_directory = directory_path / "proofs"
            index = directory_path / "index.json"
            staged_index = directory_path / ".index.json.staged"
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            journal = directory_path / "promotion.json"
            begin_promotion_build(
                root=ROOT,
                proof_directory=proof_directory,
                output_path=index,
                staging_directory=staging,
                staged_index=staged_index,
                journal_path=journal,
            )
            audited_directory = directory_sha256(staging)
            audited_index = hashlib.sha256(
                staged_index.read_bytes()
            ).hexdigest()
            proof.write_text("changed\n", encoding="ascii")
            with self.assertRaisesRegex(
                RuntimeError,
                "changed after audit",
            ):
                promote_bundle(
                    staging,
                    proof_directory,
                    staged_index,
                    index,
                    journal,
                    audited_directory,
                    audited_index,
                    root=ROOT,
                )
            self.assertFalse(proof_directory.exists())
            self.assertFalse(index.exists())

    def test_ready_journal_follows_staging_parent_fsync(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            staging = directory_path / ".proofs.test"
            staging.mkdir()
            (staging / "proof").write_text("proof\n", encoding="ascii")
            proof_directory = directory_path / "proofs"
            index = directory_path / "index.json"
            staged_index = directory_path / ".index.json.staged"
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            journal = directory_path / "promotion.json"
            events = []

            def record_fsync(path: Path) -> None:
                events.append(("fsync", path))

            def record_journal(
                path: Path,
                record: dict[str, object],
            ) -> None:
                events.append(("journal", path))

            with patch(
                "prove_fourth_word_rup_cases.fsync_directory",
                side_effect=record_fsync,
            ):
                with patch(
                    "prove_fourth_word_rup_cases.atomic_write_json",
                    side_effect=record_journal,
                ):
                    with patch(
                        "prove_fourth_word_rup_cases.recover_promotion",
                        return_value="ready-completed",
                    ):
                        promote_bundle(
                            staging,
                            proof_directory,
                            staged_index,
                            index,
                            journal,
                            directory_sha256(staging),
                            hashlib.sha256(
                                staged_index.read_bytes()
                            ).hexdigest(),
                            root=ROOT,
                        )
            parent_fsync = events.index(("fsync", staging.parent))
            journal_write = events.index(("journal", journal))
            self.assertLess(parent_fsync, journal_write)

    def test_child_interpreter_must_match_parent(self) -> None:
        with patch(
            "prove_fourth_word_rup_cases.os.path.samefile",
            return_value=False,
        ):
            with self.assertRaisesRegex(
                SystemExit,
                "interpreter running this process",
            ):
                measure_interpreter(
                    sys.executable,
                    environment=environment(),
                    root=ROOT,
                )

    def test_child_interpreter_path_must_match_parent_lexically(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            alternate = Path(directory) / "python"
            alternate.symlink_to(sys.executable)
            with self.assertRaisesRegex(
                SystemExit,
                "interpreter running this process",
            ):
                measure_interpreter(
                    str(alternate),
                    environment=environment(),
                    root=ROOT,
                )

    def test_interpreter_record_binds_python_sat_tree(self) -> None:
        record = measure_interpreter(
            sys.executable,
            environment=environment(),
            root=ROOT,
        )
        self.assertEqual(
            record["python_sat_distribution_version"],
            record["python_sat_version"],
        )
        self.assertEqual(
            record["python_executable_path"],
            interpreter_path_record(sys.executable, root=ROOT),
        )
        self.assertEqual(record["python_sat_tree"]["root"], "pysat")
        self.assertGreater(record["python_sat_tree"]["file_count"], 0)
        self.assertEqual(len(record["python_sat_tree"]["sha256"]), 64)

    def test_interpreter_path_record_is_privacy_safe(self) -> None:
        repository_interpreter = ROOT / ".venv/bin/python"
        self.assertEqual(
            interpreter_path_record(
                str(repository_interpreter),
                root=ROOT,
            ),
            {
                "scope": "repository-relative",
                "value": ".venv/bin/python",
            },
        )
        external_interpreter = (
            "/opt/hostedtoolcache/Python/3.12.11/x64/bin/python"
        )
        self.assertEqual(
            interpreter_path_record(external_interpreter, root=ROOT),
            {
                "scope": "absolute-path-sha256",
                "value": hashlib.sha256(
                    external_interpreter.encode("utf-8")
                ).hexdigest(),
            },
        )


@unittest.skipUnless(
    INDEX.is_file() and PROOF_DIRECTORY.is_dir(),
    "retained fourth-word RUP proof bundle is missing",
)
class FourthWordRupProofIntegrationTests(unittest.TestCase):
    def test_pipeline_provenance_matches_certified_sources(self) -> None:
        index = json.loads(INDEX.read_text(encoding="ascii"))
        with tempfile.TemporaryDirectory() as directory:
            pipeline_root = materialize_certified_pipeline(
                Path(directory)
            )
            validate_pipeline_provenance(
                index["pipeline_files"],
                index["pipeline_python_tree"],
                root=pipeline_root,
            )
            changed = json.loads(json.dumps(index["pipeline_files"]))
            changed["index_auditor"]["sha256"] = "0" * 64
            with self.assertRaises(SystemExit):
                validate_pipeline_provenance(
                    changed,
                    index["pipeline_python_tree"],
                    root=pipeline_root,
                )
            changed_tree = dict(index["pipeline_python_tree"])
            changed_tree["sha256"] = "0" * 64
            with self.assertRaises(SystemExit):
                validate_pipeline_provenance(
                    index["pipeline_files"],
                    changed_tree,
                    root=pipeline_root,
                )

    def test_retained_index_passes_structural_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pipeline_root = materialize_certified_pipeline(
                Path(directory)
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(AUDITOR),
                    str(PARENTS),
                    str(THIRD),
                    str(CHILD_FRONTIER),
                    str(FOURTH_FRONTIER),
                    str(CLASSIFICATION),
                    str(PLAN),
                    str(INDEX),
                    str(PROOF_DIRECTORY),
                    "--pipeline-root",
                    str(pipeline_root),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=environment(),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"case_count": 184', result.stdout)
        self.assertIn('"proofs_replayed": false', result.stdout)
        self.assertIn(
            '"replay_attestation_valid": true',
            result.stdout,
        )
        self.assertIn('"structurally_valid": true', result.stdout)

    def test_index_states_the_exact_claim_boundary(self) -> None:
        index = json.loads(INDEX.read_text(encoding="ascii"))
        self.assertEqual(
            index["certification_scope"],
            {
                "selected_third_word_children": 4,
                "fourth_word_branches": 350,
                "rup_unsat_branches": 184,
                "unresolved_fourth_word_branches": 166,
                "closed_third_word_children": 0,
                "closed_normalized_parents": 0,
            },
        )

    def test_replay_attestation_binds_the_retained_index(self) -> None:
        attestation = json.loads(
            ATTESTATION.read_text(encoding="ascii")
        )
        self.assertEqual(attestation["case_count"], 184)
        self.assertIs(attestation["all_verified"], True)
        self.assertEqual(attestation["schema_version"], 3)
        self.assertEqual(
            len(attestation["environment"]["python_executable_sha256"]),
            64,
        )
        self.assertGreater(
            attestation["environment"]["python_sat_tree"]["file_count"],
            0,
        )
        self.assertEqual(
            len(
                attestation["environment"]["python_sat_tree"]["sha256"]
            ),
            64,
        )
        self.assertEqual(
            set(attestation["environment"]["python_sat_native_modules"]),
            {"pycard", "pyformula", "pysolvers"},
        )
        self.assertEqual(
            attestation["proof_index"]["sha256"],
            hashlib.sha256(INDEX.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
