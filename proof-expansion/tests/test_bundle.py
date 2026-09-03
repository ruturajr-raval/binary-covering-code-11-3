from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import py_compile
import signal
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

import fourth_word_drat.secure_io as secure_io
from fourth_word_drat.bundle import (
    artifact_path_identity,
    branch_slug,
    case_filenames,
    case_index_record,
    certification_resource_limits,
    clean_stale_bundle_staging,
    CommandRegistry,
    coordinator_signal_handlers,
    directory_sha256,
    expected_bundle_members,
    load_authenticated_json,
    PROOF_COMMAND_TIMEOUT_SECONDS,
    promotion_index_free_space_requirement,
    promotion_journal_record,
    promote_bundle,
    recover_promotion,
    require_free_space,
    require_certification_resource_limits,
    require_path_separation,
    run_case,
    solver_environment_record,
    stage_bundle,
    StagedBundle,
    validate_case_directory,
    workspace_free_space_requirement,
)
from fourth_word_drat.proof_core import atomic_write_json, file_sha256
from fourth_word_drat.secure_io import (
    authenticated_file_version,
    durable_publish_noreplace,
    owned_temporary_directory,
    PublicationCommittedError,
)


ROOT = Path(__file__).resolve().parents[2]
PLAN = (
    ROOT
    / "proof-expansion/evidence/fourth-word-solver-drat-plan-v2.json"
)
ARTIFACTS = ROOT / ".research-artifacts"


class BundleUtilityTests(unittest.TestCase):
    def write_fake_case(
        self,
        directory: Path,
        planned: dict[str, object],
    ) -> dict[str, object]:
        names = case_filenames(str(planned["branch_id"]))
        proof = directory / names["proof"]
        summary = directory / names["summary"]
        case = directory / names["case"]
        proof.write_bytes(b"proof")
        atomic_write_json(
            summary,
            {
                "case_id": planned["branch_id"],
                "case_formula_sha256": "1" * 64,
                "retained_proof": {
                    "filename": names["proof"],
                    "compressed_sha256": file_sha256(proof),
                },
                "retained_replay": {"verified": True},
            },
        )
        record = {
            "record_type": "fourth-word-solver-drat-case",
            "schema_version": 2,
            "plan_case": planned,
            "formula": {
                "sha256": "1" * 64,
                "variables": 1,
                "clauses": 1,
            },
            "proof": {
                "filename": names["proof"],
                "sha256": file_sha256(proof),
            },
            "proof_summary": {
                "filename": names["summary"],
                "sha256": file_sha256(summary),
            },
            "verified": True,
        }
        atomic_write_json(case, record)
        return record

    def test_branch_slug_is_canonical(self) -> None:
        branch_id = (
            "w4-weight5-intersection0::orbit-005::fourth-030"
        )
        self.assertEqual(
            branch_slug(branch_id),
            "w4-weight5-intersection0--orbit-005--fourth-030",
        )

    def test_branch_slug_rejects_path_characters(self) -> None:
        with self.assertRaises(ValueError):
            branch_slug("../branch")

    def test_overlapping_repository_paths_are_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            require_path_separation(
                {
                    "proof_directory": ROOT / "proof-expansion/evidence",
                    "index": (
                        ROOT
                        / "proof-expansion/evidence/index.json"
                    ),
                }
            )

    def test_case_insensitive_path_aliases_are_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            require_path_separation(
                {
                    "index": ROOT / "proof-expansion/evidence/index.json",
                    "journal": ROOT / "proof-expansion/evidence/INDEX.json",
                }
            )

    def test_bundle_members_are_exact_and_collision_free(self) -> None:
        plan = json.loads(PLAN.read_text(encoding="ascii"))
        members = expected_bundle_members(plan["cases"])
        self.assertEqual(len(members), 420)

    def test_directory_digest_is_order_independent(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as first_dir:
            with tempfile.TemporaryDirectory(dir=ARTIFACTS) as second_dir:
                first = Path(first_dir)
                second = Path(second_dir)
                (first / "a").write_bytes(b"a")
                (first / "b").write_bytes(b"b")
                (second / "b").write_bytes(b"b")
                (second / "a").write_bytes(b"a")
                self.assertEqual(
                    directory_sha256(first),
                    directory_sha256(second),
                )

    def test_authenticated_json_hashes_parsed_bytes(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            path = Path(directory) / "record.json"
            payload = b'{"value": 7}\n'
            path.write_bytes(payload)
            record, digest = load_authenticated_json(
                path,
                "test record",
            )
            self.assertEqual(record, {"value": 7})
            self.assertEqual(
                digest,
                hashlib.sha256(payload).hexdigest(),
            )

    def test_authenticated_json_rejects_duplicate_keys(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            path = Path(directory) / "record.json"
            path.write_bytes(b'{"value": 7, "value": 8}\n')
            with self.assertRaisesRegex(RuntimeError, "is invalid"):
                load_authenticated_json(path, "test record")

    def test_authenticated_json_rejects_symlinks(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            target = directory_path / "target.json"
            link = directory_path / "record.json"
            target.write_bytes(b'{"value": 7}\n')
            link.symlink_to(target)
            with self.assertRaisesRegex(
                RuntimeError,
                "cannot be opened|stable single-link",
            ):
                load_authenticated_json(link, "test record")

    def test_authenticated_json_rejects_fifo_without_opening(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            path = Path(directory) / "record.json"
            os.mkfifo(path)
            started = time.monotonic()
            with self.assertRaisesRegex(
                RuntimeError,
                "stable single-link",
            ):
                load_authenticated_json(path, "test record")
            self.assertLess(time.monotonic() - started, 1)

    def test_authenticated_reader_rejects_fifo_swap(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            path = Path(directory) / "record.json"
            path.write_bytes(b'{"value": 7}\n')
            real_open = os.open

            def replace_with_fifo(
                target: Path,
                flags: int,
            ) -> int:
                self.assertTrue(flags & os.O_NONBLOCK)
                path.unlink()
                os.mkfifo(path)
                return real_open(target, flags)

            started = time.monotonic()
            with mock.patch(
                "fourth_word_drat.secure_io.os.open",
                side_effect=replace_with_fifo,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "stable single-link",
                ):
                    load_authenticated_json(path, "test record")
            self.assertLess(time.monotonic() - started, 1)

    def test_authenticated_reader_closes_descriptor_on_error(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            path = Path(directory) / "record.json"
            path.write_bytes(b'{"value": 7}\n')
            real_close = os.close
            with mock.patch(
                "fourth_word_drat.secure_io.os.fdopen",
                side_effect=RuntimeError("injected fdopen failure"),
            ):
                with mock.patch(
                    "fourth_word_drat.secure_io.os.close",
                    wraps=real_close,
                ) as close:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "injected fdopen failure",
                    ):
                        load_authenticated_json(path, "test record")
            close.assert_called_once()

    def test_atomic_publication_preserves_racing_destination(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            destination = directory_path / "record.json"
            foreign_payload = b'{"foreign": true}\n'
            real_rename = secure_io._native_rename_noreplace

            def inject_destination(
                source_descriptor: int,
                source_name: str,
                destination_descriptor: int,
                destination_name: str,
            ) -> None:
                descriptor = os.open(
                    destination_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=destination_descriptor,
                )
                try:
                    os.write(descriptor, foreign_payload)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                real_rename(
                    source_descriptor,
                    source_name,
                    destination_descriptor,
                    destination_name,
                )

            with mock.patch(
                "fourth_word_drat.secure_io._native_rename_noreplace",
                side_effect=inject_destination,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "destination already exists",
                ):
                    atomic_write_json(destination, {"ours": True})
            self.assertEqual(destination.read_bytes(), foreign_payload)
            self.assertEqual(
                list(directory_path.glob(".record.json.*.tmp")),
                [],
            )

    def test_directory_publication_preserves_existing_destination(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            source = directory_path / "source"
            destination = directory_path / "destination"
            source.mkdir()
            destination.mkdir()
            (source / "owned").write_bytes(b"owned")
            (destination / "foreign").write_bytes(b"foreign")
            source_identity = artifact_path_identity(
                source,
                directory=True,
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "destination already exists",
            ):
                durable_publish_noreplace(
                    source,
                    destination,
                    directory=True,
                    expected_source_identity=source_identity,
                )
            self.assertEqual(
                (destination / "foreign").read_bytes(),
                b"foreign",
            )
            self.assertEqual((source / "owned").read_bytes(), b"owned")

    def test_file_publication_rolls_back_source_version_drift(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            source = directory_path / "source"
            destination = directory_path / "destination"
            source.write_bytes(b"original")
            source_version = authenticated_file_version(
                source,
                "publication source",
            )
            real_rename = secure_io._native_rename_noreplace

            def mutate_before_rename(
                source_descriptor: int,
                source_name: str,
                destination_descriptor: int,
                destination_name: str,
            ) -> None:
                if (
                    source_name == source.name
                    and destination_name == destination.name
                ):
                    descriptor = os.open(
                        source_name,
                        os.O_WRONLY | os.O_TRUNC,
                        dir_fd=source_descriptor,
                    )
                    try:
                        os.write(descriptor, b"mutated")
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                real_rename(
                    source_descriptor,
                    source_name,
                    destination_descriptor,
                    destination_name,
                )

            with mock.patch(
                "fourth_word_drat.secure_io._native_rename_noreplace",
                side_effect=mutate_before_rename,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "post-commit validation failed",
                ):
                    durable_publish_noreplace(
                        source,
                        destination,
                        directory=False,
                        expected_source_identity=source_version.identity,
                        expected_source_version=source_version,
                    )
            self.assertEqual(source.read_bytes(), b"mutated")
            self.assertFalse(destination.exists())

    def test_file_publication_rolls_back_verification_failure(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            source = directory_path / "source"
            destination = directory_path / "destination"
            source.write_bytes(b"payload")
            source_version = authenticated_file_version(
                source,
                "publication source",
            )
            real_require = secure_io._require_file_version_at

            def fail_destination(
                parent_descriptor: int,
                name: str,
                expected,
                description: str,
                *,
                after_rename: bool = False,
            ) -> None:
                if name == destination.name:
                    raise RuntimeError(
                        "injected destination verification failure"
                    )
                real_require(
                    parent_descriptor,
                    name,
                    expected,
                    description,
                    after_rename=after_rename,
                )

            with mock.patch(
                "fourth_word_drat.secure_io._require_file_version_at",
                side_effect=fail_destination,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "post-commit validation failed",
                ):
                    durable_publish_noreplace(
                        source,
                        destination,
                        directory=False,
                        expected_source_identity=source_version.identity,
                        expected_source_version=source_version,
                    )
            self.assertEqual(source.read_bytes(), b"payload")
            self.assertFalse(destination.exists())

    def test_file_publication_rolls_back_fsync_failure(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            source = directory_path / "source"
            destination = directory_path / "destination"
            source.write_bytes(b"payload")
            source_version = authenticated_file_version(
                source,
                "publication source",
            )
            real_fsync = secure_io.os.fsync
            fsync_calls = 0

            def fail_once(descriptor: int) -> None:
                nonlocal fsync_calls
                fsync_calls += 1
                if fsync_calls == 1:
                    raise OSError("injected fsync failure")
                real_fsync(descriptor)

            with mock.patch(
                "fourth_word_drat.secure_io.os.fsync",
                side_effect=fail_once,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "post-commit validation failed",
                ):
                    durable_publish_noreplace(
                        source,
                        destination,
                        directory=False,
                        expected_source_identity=source_version.identity,
                        expected_source_version=source_version,
                    )
            self.assertGreaterEqual(fsync_calls, 2)
            self.assertEqual(source.read_bytes(), b"payload")
            self.assertFalse(destination.exists())

    def test_file_publication_reports_reverse_fsync_failure(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            source = directory_path / "source"
            destination = directory_path / "destination"
            source.write_bytes(b"payload")
            source_version = authenticated_file_version(
                source,
                "publication source",
            )
            fsync_calls = 0

            def fail_all(descriptor: int) -> None:
                nonlocal fsync_calls
                fsync_calls += 1
                raise OSError("injected fsync failure")

            with mock.patch(
                "fourth_word_drat.secure_io.os.fsync",
                side_effect=fail_all,
            ):
                with self.assertRaises(PublicationCommittedError):
                    durable_publish_noreplace(
                        source,
                        destination,
                        directory=False,
                        expected_source_identity=source_version.identity,
                        expected_source_version=source_version,
                    )
            self.assertGreaterEqual(fsync_calls, 2)
            self.assertEqual(source.read_bytes(), b"payload")
            self.assertFalse(destination.exists())

    def test_atomic_write_removes_committed_destination_after_failed_rollback(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            destination = directory_path / "record.json"
            real_rename = secure_io._native_rename_noreplace
            real_require = secure_io._require_file_version_at
            rename_calls = 0

            def fail_destination_verification(
                parent_descriptor: int,
                name: str,
                expected,
                description: str,
                *,
                after_rename: bool = False,
            ) -> None:
                if description == "published artifact":
                    raise RuntimeError(
                        "injected destination verification failure"
                    )
                real_require(
                    parent_descriptor,
                    name,
                    expected,
                    description,
                    after_rename=after_rename,
                )

            def fail_reverse_rename(
                source_descriptor: int,
                source_name: str,
                destination_descriptor: int,
                destination_name: str,
            ) -> None:
                nonlocal rename_calls
                rename_calls += 1
                if rename_calls == 2:
                    raise OSError("injected reverse rename failure")
                real_rename(
                    source_descriptor,
                    source_name,
                    destination_descriptor,
                    destination_name,
                )

            with mock.patch(
                "fourth_word_drat.secure_io._require_file_version_at",
                side_effect=fail_destination_verification,
            ):
                with mock.patch(
                    "fourth_word_drat.secure_io._native_rename_noreplace",
                    side_effect=fail_reverse_rename,
                ):
                    with self.assertRaises(PublicationCommittedError):
                        atomic_write_json(
                            destination,
                            {"value": 7},
                        )
            self.assertEqual(rename_calls, 2)
            self.assertFalse(destination.exists())
            self.assertEqual(
                list(directory_path.glob(".record.json.*.tmp")),
                [],
            )

    def test_owned_temporary_directory_detects_parent_replacement(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            parent = directory_path / "scratch"
            moved_parent = directory_path / "scratch-moved"
            parent.mkdir()
            real_mkdir = secure_io.os.mkdir

            def replace_parent(
                path,
                mode=0o777,
                *,
                dir_fd=None,
            ) -> None:
                real_mkdir(path, mode=mode, dir_fd=dir_fd)
                if dir_fd is not None and str(path).startswith(".test."):
                    parent.rename(moved_parent)
                    real_mkdir(parent)

            with mock.patch(
                "fourth_word_drat.secure_io.os.mkdir",
                side_effect=replace_parent,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "temporary parent changed during use",
                ):
                    with owned_temporary_directory(
                        parent,
                        prefix=".test.",
                    ):
                        pass
            self.assertEqual(list(moved_parent.iterdir()), [])
            self.assertEqual(list(parent.iterdir()), [])

    def test_owned_temporary_directory_cleans_moved_parent(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            parent = directory_path / "scratch"
            moved_parent = directory_path / "scratch-moved"
            parent.mkdir()
            with self.assertRaisesRegex(
                RuntimeError,
                "temporary parent changed during use",
            ):
                with owned_temporary_directory(
                    parent,
                    prefix=".test.",
                ) as temporary:
                    (temporary / "nested").mkdir()
                    (temporary / "nested" / "member").write_bytes(
                        b"owned"
                    )
                    parent.rename(moved_parent)
                    parent.mkdir()
            self.assertEqual(list(moved_parent.iterdir()), [])
            self.assertEqual(list(parent.iterdir()), [])

    def test_owned_temporary_directory_cleans_after_identity_capture_failure(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory) / "scratch"
            parent.mkdir()
            real_open = secure_io.os.open

            def fail_created_directory_open(
                path,
                flags,
                mode=0o777,
                *,
                dir_fd=None,
            ):
                if dir_fd is not None and str(path).startswith(".test."):
                    raise OSError("injected directory-open failure")
                return real_open(
                    path,
                    flags,
                    mode,
                    dir_fd=dir_fd,
                )

            with mock.patch(
                "fourth_word_drat.secure_io.os.open",
                side_effect=fail_created_directory_open,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "temporary directory changed during cleanup",
                ):
                    with owned_temporary_directory(
                        parent,
                        prefix=".test.",
                    ):
                        pass
            quarantined = list(
                parent.glob(".*.rollback-unverified.*")
            )
            self.assertEqual(len(quarantined), 1)
            self.assertTrue(quarantined[0].is_dir())

    def test_unverified_scratch_replacement_is_quarantined_not_deleted(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory) / "scratch"
            parent.mkdir()
            real_open = secure_io.os.open
            real_mkdir = secure_io.os.mkdir

            def replace_before_identity_capture(
                path,
                flags,
                mode=0o777,
                *,
                dir_fd=None,
            ):
                if dir_fd is not None and str(path).startswith(".test."):
                    os.rename(
                        path,
                        "owned-original",
                        src_dir_fd=dir_fd,
                        dst_dir_fd=dir_fd,
                    )
                    real_mkdir(path, mode=0o700, dir_fd=dir_fd)
                    foreign_descriptor = real_open(
                        f"{path}/foreign",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=dir_fd,
                    )
                    try:
                        os.write(foreign_descriptor, b"foreign")
                    finally:
                        os.close(foreign_descriptor)
                    raise OSError("injected directory substitution")
                return real_open(
                    path,
                    flags,
                    mode,
                    dir_fd=dir_fd,
                )

            with mock.patch(
                "fourth_word_drat.secure_io.os.open",
                side_effect=replace_before_identity_capture,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "temporary directory changed during cleanup",
                ):
                    with owned_temporary_directory(
                        parent,
                        prefix=".test.",
                    ):
                        pass
            quarantined_files = [
                path
                for path in parent.rglob("*")
                if path.is_file()
            ]
            self.assertEqual(len(quarantined_files), 1)
            self.assertEqual(
                quarantined_files[0].read_bytes(),
                b"foreign",
            )
            self.assertTrue((parent / "owned-original").is_dir())

    def test_owned_temporary_directory_quarantines_child_replacement(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            parent = directory_path / "scratch"
            replacement = directory_path / "replacement"
            parent.mkdir()
            replacement.write_bytes(b"foreign")
            real_rename = secure_io._native_rename_noreplace
            substituted = False

            def replace_child_before_quarantine(
                source_descriptor: int,
                source_name: str,
                destination_descriptor: int,
                destination_name: str,
            ) -> None:
                nonlocal substituted
                if source_name == "member" and not substituted:
                    substituted = True
                    os.replace(
                        replacement,
                        source_name,
                        dst_dir_fd=source_descriptor,
                    )
                real_rename(
                    source_descriptor,
                    source_name,
                    destination_descriptor,
                    destination_name,
                )

            with mock.patch(
                "fourth_word_drat.secure_io._native_rename_noreplace",
                side_effect=replace_child_before_quarantine,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "temporary directory changed during cleanup",
                ):
                    with owned_temporary_directory(
                        parent,
                        prefix=".test.",
                    ) as temporary:
                        (temporary / "member").write_bytes(b"owned")
            quarantined = [
                path
                for path in parent.rglob("*")
                if path.is_file()
            ]
            self.assertTrue(substituted)
            self.assertEqual(len(quarantined), 1)
            self.assertEqual(quarantined[0].read_bytes(), b"foreign")

    def test_case_membership_mutation_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        plan = json.loads(PLAN.read_text(encoding="ascii"))
        planned = plan["cases"][0]
        names = case_filenames(planned["branch_id"])
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            self.write_fake_case(directory_path, planned)
            (directory_path / "unexpected").write_text(
                "x",
                encoding="ascii",
            )
            with self.assertRaises(RuntimeError):
                validate_case_directory(directory_path, planned)

    def test_case_index_authenticates_case_record(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        plan = json.loads(PLAN.read_text(encoding="ascii"))
        planned = plan["cases"][0]
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            artifact_directory = Path(directory)
            record = self.write_fake_case(
                artifact_directory,
                planned,
            )
            proof_directory = ROOT / "proof-expansion/evidence/proofs/test"
            indexed = case_index_record(
                record,
                proof_directory=proof_directory,
                artifact_directory=artifact_directory,
                root=ROOT,
            )
            case_name = case_filenames(
                str(planned["branch_id"])
            )["case"]
            self.assertEqual(
                indexed["case_record"]["sha256"],
                file_sha256(artifact_directory / case_name),
            )
            self.assertEqual(indexed["branch_id"], planned["branch_id"])

    def test_stale_staging_cleanup_is_strict(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            stale_proofs = parent / ".proofs.0123456789abcdef"
            stale_index = parent / ".index.json.fedcba9876543210"
            unrelated = parent / ".proofs.not-a-token"
            stale_proofs.mkdir()
            stale_index.write_text("{}\n", encoding="ascii")
            unrelated.mkdir()
            removed = clean_stale_bundle_staging(
                proof_directory,
                output,
            )
            self.assertEqual(set(removed), {stale_proofs, stale_index})
            self.assertFalse(stale_proofs.exists())
            self.assertFalse(stale_index.exists())
            self.assertTrue(unrelated.exists())

    def test_stale_cleanup_quarantines_replacement(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            stale_index = parent / ".index.json.0123456789abcdef"
            replacement_source = parent / "replacement"
            replacement = b"unowned stale replacement\n"
            stale_index.write_text("{}\n", encoding="ascii")
            replacement_source.write_bytes(replacement)
            real_rename = os.rename
            substituted = False

            def substitute_before_quarantine(
                source: Path,
                destination: Path,
            ) -> None:
                nonlocal substituted
                if Path(source) == stale_index and not substituted:
                    substituted = True
                    os.replace(replacement_source, stale_index)
                real_rename(source, destination)

            with mock.patch(
                "fourth_word_drat.secure_io.os.rename",
                side_effect=substitute_before_quarantine,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "stale staging changed during cleanup",
                ):
                    clean_stale_bundle_staging(
                        proof_directory,
                        output,
                    )
            quarantined = list(
                parent.glob(
                    ".index.json.0123456789abcdef.rollback.*/artifact"
                )
            )
            self.assertTrue(substituted)
            self.assertEqual(len(quarantined), 1)
            self.assertEqual(quarantined[0].read_bytes(), replacement)
            self.assertFalse(stale_index.exists())

    def test_self_authenticating_fake_case_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        plan = json.loads(PLAN.read_text(encoding="ascii"))
        planned = plan["cases"][0]
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            directory_path = Path(directory)
            self.write_fake_case(directory_path, planned)
            with self.assertRaises(RuntimeError):
                validate_case_directory(directory_path, planned)

    def test_ready_promotion_is_rolled_back(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            staging = parent / ".proofs.0123456789abcdef"
            staged_index = parent / ".index.json.0123456789abcdef"
            journal = parent / ".promotion.json"
            staging.mkdir()
            (staging / "proof").write_bytes(b"proof")
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            atomic_write_json(
                journal,
                promotion_journal_record(
                    token="0123456789abcdef",
                    root=ROOT,
                    proof_directory=proof_directory,
                    output_path=output,
                    staging_directory=staging,
                    staged_index=staged_index,
                    proof_directory_sha256=directory_sha256(staging),
                    output_sha256=file_sha256(staged_index),
                ),
            )
            outcome = recover_promotion(
                root=ROOT,
                proof_directory=proof_directory,
                output_path=output,
                journal_path=journal,
            )
            self.assertEqual(outcome, "ready-rolled-back")
            self.assertFalse(proof_directory.exists())
            self.assertFalse(output.exists())
            self.assertFalse(staging.exists())
            self.assertFalse(staged_index.exists())
            self.assertFalse(journal.exists())

    def test_partial_promotion_is_rolled_back(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            staging = parent / ".proofs.0123456789abcdef"
            staged_index = parent / ".index.json.0123456789abcdef"
            journal = parent / ".promotion.json"
            staging.mkdir()
            (staging / "proof").write_bytes(b"proof")
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            atomic_write_json(
                journal,
                promotion_journal_record(
                    token="0123456789abcdef",
                    root=ROOT,
                    proof_directory=proof_directory,
                    output_path=output,
                    staging_directory=staging,
                    staged_index=staged_index,
                    proof_directory_sha256=directory_sha256(staging),
                    output_sha256=file_sha256(staged_index),
                ),
            )
            staging.rename(proof_directory)
            output.write_bytes(staged_index.read_bytes())
            outcome = recover_promotion(
                root=ROOT,
                proof_directory=proof_directory,
                output_path=output,
                journal_path=journal,
            )
            self.assertEqual(outcome, "ready-rolled-back")
            self.assertFalse(proof_directory.exists())
            self.assertFalse(output.exists())
            self.assertFalse(staged_index.exists())
            self.assertFalse(journal.exists())

    def test_recovery_quarantines_replacement(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            staging = parent / ".proofs.0123456789abcdef"
            staged_index = parent / ".index.json.0123456789abcdef"
            journal = parent / ".promotion.json"
            replacement_source = parent / "replacement"
            replacement = b"unowned recovery replacement\n"
            staging.mkdir()
            (staging / "proof").write_bytes(b"proof")
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            index_digest = file_sha256(staged_index)
            atomic_write_json(
                journal,
                promotion_journal_record(
                    token="0123456789abcdef",
                    root=ROOT,
                    proof_directory=proof_directory,
                    output_path=output,
                    staging_directory=staging,
                    staged_index=staged_index,
                    proof_directory_sha256=directory_sha256(staging),
                    output_sha256=index_digest,
                ),
            )
            staging.rename(proof_directory)
            output.write_bytes(staged_index.read_bytes())
            replacement_source.write_bytes(replacement)
            real_rename = os.rename
            substituted = False

            def substitute_before_quarantine(
                source: Path,
                destination: Path,
            ) -> None:
                nonlocal substituted
                if Path(source) == output and not substituted:
                    substituted = True
                    os.replace(replacement_source, output)
                real_rename(source, destination)

            with mock.patch(
                "fourth_word_drat.secure_io.os.rename",
                side_effect=substitute_before_quarantine,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "recovery could not safely remove",
                ):
                    recover_promotion(
                        root=ROOT,
                        proof_directory=proof_directory,
                        output_path=output,
                        journal_path=journal,
                    )
            quarantined = list(
                parent.glob("index.json.rollback.*/artifact")
            )
            self.assertTrue(substituted)
            self.assertEqual(len(quarantined), 1)
            self.assertEqual(quarantined[0].read_bytes(), replacement)
            self.assertFalse(proof_directory.exists())
            self.assertFalse(output.exists())
            self.assertFalse(staged_index.exists())
            self.assertTrue(journal.is_file())

    def test_post_promotion_input_failure_rolls_back(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            staging = parent / ".proofs.0123456789abcdef"
            staged_index = parent / ".index.json.0123456789abcdef"
            journal = parent / ".promotion.json"
            staging.mkdir()
            (staging / "proof").write_bytes(b"proof")
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            directory_digest = directory_sha256(staging)
            index_digest = file_sha256(staged_index)
            calls = 0

            def validate_inputs() -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("injected input drift")

            with self.assertRaisesRegex(
                RuntimeError,
                "injected input drift",
            ):
                promote_bundle(
                    staging,
                    staged_index,
                    root=ROOT,
                    proof_directory=proof_directory,
                    output_path=output,
                    journal_path=journal,
                    token="0123456789abcdef",
                    expected_directory_hash=directory_digest,
                    expected_index_hash=index_digest,
                    validate_inputs=validate_inputs,
                )
            self.assertEqual(calls, 2)
            self.assertFalse(proof_directory.exists())
            self.assertFalse(output.exists())
            self.assertFalse(staging.exists())
            self.assertFalse(staged_index.exists())
            self.assertFalse(journal.exists())

    def test_proof_directory_publication_collision_preserves_foreign(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            staging = parent / ".proofs.0123456789abcdef"
            staged_index = parent / ".index.json.0123456789abcdef"
            journal = parent / ".promotion.json"
            staging.mkdir()
            (staging / "proof").write_bytes(b"proof")
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            directory_digest = directory_sha256(staging)
            index_digest = file_sha256(staged_index)
            real_rename = secure_io._native_rename_noreplace

            def inject_directory(
                source_descriptor: int,
                source_name: str,
                destination_descriptor: int,
                destination_name: str,
            ) -> None:
                if destination_name == proof_directory.name:
                    os.mkdir(
                        destination_name,
                        mode=0o700,
                        dir_fd=destination_descriptor,
                    )
                    (proof_directory / "foreign").write_bytes(b"foreign")
                real_rename(
                    source_descriptor,
                    source_name,
                    destination_descriptor,
                    destination_name,
                )

            with mock.patch(
                "fourth_word_drat.secure_io._native_rename_noreplace",
                side_effect=inject_directory,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "destination already exists",
                ):
                    promote_bundle(
                        staging,
                        staged_index,
                        root=ROOT,
                        proof_directory=proof_directory,
                        output_path=output,
                        journal_path=journal,
                        token="0123456789abcdef",
                        expected_directory_hash=directory_digest,
                        expected_index_hash=index_digest,
                    )
            self.assertEqual(
                (proof_directory / "foreign").read_bytes(),
                b"foreign",
            )
            self.assertFalse(output.exists())
            self.assertFalse(staging.exists())
            self.assertFalse(staged_index.exists())
            self.assertFalse(journal.exists())

    def test_index_publication_collision_preserves_foreign(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            staging = parent / ".proofs.0123456789abcdef"
            staged_index = parent / ".index.json.0123456789abcdef"
            journal = parent / ".promotion.json"
            foreign_payload = b'{"foreign": true}\n'
            staging.mkdir()
            (staging / "proof").write_bytes(b"proof")
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            directory_digest = directory_sha256(staging)
            index_digest = file_sha256(staged_index)
            real_rename = secure_io._native_rename_noreplace

            def inject_index(
                source_descriptor: int,
                source_name: str,
                destination_descriptor: int,
                destination_name: str,
            ) -> None:
                if destination_name == output.name:
                    descriptor = os.open(
                        destination_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=destination_descriptor,
                    )
                    try:
                        os.write(descriptor, foreign_payload)
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                real_rename(
                    source_descriptor,
                    source_name,
                    destination_descriptor,
                    destination_name,
                )

            with mock.patch(
                "fourth_word_drat.secure_io._native_rename_noreplace",
                side_effect=inject_index,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "destination already exists",
                ):
                    promote_bundle(
                        staging,
                        staged_index,
                        root=ROOT,
                        proof_directory=proof_directory,
                        output_path=output,
                        journal_path=journal,
                        token="0123456789abcdef",
                        expected_directory_hash=directory_digest,
                        expected_index_hash=index_digest,
                    )
            self.assertEqual(output.read_bytes(), foreign_payload)
            self.assertFalse(proof_directory.exists())
            self.assertFalse(staging.exists())
            self.assertFalse(staged_index.exists())
            self.assertFalse(journal.exists())

    def test_promotion_rolls_back_committed_directory_exception(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            staging = parent / ".proofs.0123456789abcdef"
            staged_index = parent / ".index.json.0123456789abcdef"
            journal = parent / ".promotion.json"
            staging.mkdir()
            (staging / "proof").write_bytes(b"proof")
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            directory_digest = directory_sha256(staging)
            index_digest = file_sha256(staged_index)

            def commit_then_fail(
                source: Path,
                destination: Path,
                *,
                directory: bool,
                expected_source_identity=None,
                expected_source_version=None,
            ):
                self.assertTrue(directory)
                os.rename(source, destination)
                raise PublicationCommittedError(
                    destination,
                    expected_source_identity,
                    directory=True,
                )

            with mock.patch(
                "fourth_word_drat.bundle.durable_publish_noreplace",
                side_effect=commit_then_fail,
            ):
                with self.assertRaises(PublicationCommittedError):
                    promote_bundle(
                        staging,
                        staged_index,
                        root=ROOT,
                        proof_directory=proof_directory,
                        output_path=output,
                        journal_path=journal,
                        token="0123456789abcdef",
                        expected_directory_hash=directory_digest,
                        expected_index_hash=index_digest,
                    )
            self.assertFalse(proof_directory.exists())
            self.assertFalse(output.exists())
            self.assertFalse(staging.exists())
            self.assertFalse(staged_index.exists())
            self.assertFalse(journal.exists())

    def test_case_cleanup_checks_both_uncertain_publication_locations(
        self,
    ) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        plan = json.loads(PLAN.read_text(encoding="ascii"))
        planned = plan["cases"][0]
        branch_id = str(planned["branch_id"])
        names = case_filenames(branch_id)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            workspace = parent / "workspace"
            checker = parent / "checker"
            checker.write_bytes(b"checker")

            class FakeCommands:
                def __init__(self) -> None:
                    self.calls = 0

                def run(self, _command, **_kwargs) -> str:
                    self.calls += 1
                    if self.calls == 1:
                        case_root = workspace / "cases"
                        staging = next(
                            case_root.glob(
                                f".{branch_slug(branch_id)}.*"
                            )
                        )
                        (staging / names["proof"]).write_bytes(b"proof")
                        atomic_write_json(
                            staging / names["summary"],
                            {
                                "case_formula_sha256": "1" * 64,
                            },
                        )
                    return ""

            def generate_formula(
                _planned,
                *,
                directory: Path,
                **_kwargs,
            ):
                formula = directory / "formula.cnf"
                metadata_path = directory / "formula.json"
                formula.write_bytes(b"p cnf 0 0\n")
                metadata = {
                    "formula_sha256": "1" * 64,
                    "variables": 0,
                    "clauses": 0,
                }
                atomic_write_json(metadata_path, metadata)
                return formula, metadata_path, metadata

            def restored_but_uncertain(
                _source: Path,
                destination: Path,
                *,
                directory: bool,
                expected_source_identity=None,
                expected_source_version=None,
            ):
                self.assertTrue(directory)
                raise PublicationCommittedError(
                    destination,
                    expected_source_identity,
                    directory=True,
                )

            commands = FakeCommands()
            with mock.patch(
                "fourth_word_drat.bundle.generate_and_audit_formula",
                side_effect=generate_formula,
            ):
                with mock.patch(
                    "fourth_word_drat.bundle.durable_publish_noreplace",
                    side_effect=restored_but_uncertain,
                ):
                    with self.assertRaises(PublicationCommittedError):
                        run_case(
                            planned,
                            root=ROOT,
                            workspace=workspace,
                            python_command=str(ROOT / ".venv/bin/python"),
                            checker=checker,
                            checker_commit="2" * 40,
                            environment={},
                            commands=commands,
                            minimum_free_bytes=1,
                            max_solve_seconds=1,
                            max_raw_proof_bytes=1024,
                            max_retained_proof_bytes=1024,
                            max_memory_bytes=1024,
                        )
            self.assertEqual(commands.calls, 2)
            self.assertEqual(list((workspace / "cases").iterdir()), [])

    def test_pre_journal_failure_quarantines_replacement(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            staging = parent / ".proofs.0123456789abcdef"
            staged_index = parent / ".index.json.0123456789abcdef"
            journal = parent / ".promotion.json"
            replacement_source = parent / "replacement"
            replacement = b"unowned pre-journal replacement\n"
            staging.mkdir()
            (staging / "proof").write_bytes(b"proof")
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            replacement_source.write_bytes(replacement)
            directory_digest = directory_sha256(staging)
            index_digest = file_sha256(staged_index)
            staging_identity = artifact_path_identity(
                staging,
                directory=True,
            )
            staged_index_identity = artifact_path_identity(
                staged_index,
                directory=False,
            )

            def substitute_and_fail() -> None:
                os.replace(replacement_source, staged_index)
                raise RuntimeError("injected pre-journal failure")

            with self.assertRaisesRegex(
                RuntimeError,
                "rollback could not safely remove",
            ):
                promote_bundle(
                    staging,
                    staged_index,
                    root=ROOT,
                    proof_directory=proof_directory,
                    output_path=output,
                    journal_path=journal,
                    token="0123456789abcdef",
                    expected_directory_hash=directory_digest,
                    expected_index_hash=index_digest,
                    expected_staging_identity=staging_identity,
                    expected_staged_index_identity=(
                        staged_index_identity
                    ),
                    validate_inputs=substitute_and_fail,
                )
            quarantined = list(
                parent.glob(
                    ".index.json.0123456789abcdef.rollback.*/artifact"
                )
            )
            self.assertEqual(len(quarantined), 1)
            self.assertEqual(quarantined[0].read_bytes(), replacement)
            self.assertFalse(staging.exists())
            self.assertFalse(staged_index.exists())
            self.assertFalse(journal.exists())

    def test_post_promotion_corruption_rolls_back(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            staging = parent / ".proofs.0123456789abcdef"
            staged_index = parent / ".index.json.0123456789abcdef"
            journal = parent / ".promotion.json"
            staging.mkdir()
            (staging / "proof").write_bytes(b"proof")
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            directory_digest = directory_sha256(staging)
            index_digest = file_sha256(staged_index)
            calls = 0

            def corrupt_after_promotion() -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    output.write_text("{}\n", encoding="ascii")

            with self.assertRaisesRegex(
                RuntimeError,
                "changed during input validation",
            ):
                promote_bundle(
                    staging,
                    staged_index,
                    root=ROOT,
                    proof_directory=proof_directory,
                    output_path=output,
                    journal_path=journal,
                    token="0123456789abcdef",
                    expected_directory_hash=directory_digest,
                    expected_index_hash=index_digest,
                    validate_inputs=corrupt_after_promotion,
                )
            self.assertEqual(calls, 2)
            self.assertFalse(proof_directory.exists())
            self.assertFalse(output.exists())
            self.assertFalse(staging.exists())
            self.assertFalse(staged_index.exists())
            self.assertFalse(journal.exists())

    def test_success_cleanup_quarantines_replacement(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            staging = parent / ".proofs.0123456789abcdef"
            staged_index = parent / ".index.json.0123456789abcdef"
            journal = parent / ".promotion.json"
            staging.mkdir()
            (staging / "proof").write_bytes(b"proof")
            staged_index.write_text('{"valid": true}\n', encoding="ascii")
            directory_digest = directory_sha256(staging)
            index_digest = file_sha256(staged_index)
            real_rename = os.rename
            replacement = b"unowned replacement\n"
            replacement_source = parent / "replacement"
            replacement_source.write_bytes(replacement)
            substituted = False

            def substitute_before_quarantine(
                source: Path,
                destination: Path,
            ) -> None:
                nonlocal substituted
                if Path(source) == staged_index and not substituted:
                    substituted = True
                    os.replace(replacement_source, staged_index)
                real_rename(source, destination)

            with mock.patch(
                "fourth_word_drat.secure_io.os.rename",
                side_effect=substitute_before_quarantine,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "cleanup could not safely remove",
                ):
                    promote_bundle(
                        staging,
                        staged_index,
                        root=ROOT,
                        proof_directory=proof_directory,
                        output_path=output,
                        journal_path=journal,
                        token="0123456789abcdef",
                        expected_directory_hash=directory_digest,
                        expected_index_hash=index_digest,
                    )
            quarantined = list(
                parent.glob(
                    ".index.json.0123456789abcdef.rollback.*/artifact"
                )
            )
            self.assertTrue(substituted)
            self.assertEqual(len(quarantined), 1)
            self.assertEqual(quarantined[0].read_bytes(), replacement)
            self.assertTrue(proof_directory.is_dir())
            self.assertTrue(output.is_file())
            self.assertFalse(staged_index.exists())
            self.assertFalse(journal.exists())

    def test_noncanonical_promotion_journal_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            proof_directory = parent / "proofs"
            output = parent / "index.json"
            staging = parent / ".proofs.0123456789abcdef"
            staged_index = parent / ".index.json.0123456789abcdef"
            journal = parent / ".promotion.json"
            staging.mkdir()
            (staging / "proof").write_bytes(b"proof")
            staged_index.write_text("{}\n", encoding="ascii")
            record = promotion_journal_record(
                token="0123456789abcdef",
                root=ROOT,
                proof_directory=proof_directory,
                output_path=output,
                staging_directory=staging,
                staged_index=staged_index,
                proof_directory_sha256=directory_sha256(staging),
                output_sha256=file_sha256(staged_index),
            )
            record["staging_directory"] = str(
                (parent / "unrelated").relative_to(ROOT)
            )
            atomic_write_json(journal, record)
            with self.assertRaises(RuntimeError):
                recover_promotion(
                    root=ROOT,
                    proof_directory=proof_directory,
                    output_path=output,
                    journal_path=journal,
                )

    def test_command_timeout_terminates_process_group(self) -> None:
        registry = CommandRegistry()
        started = time.monotonic()
        with self.assertRaises(RuntimeError):
            registry.run(
                [
                    str(ROOT / ".venv/bin/python"),
                    "-c",
                    "import time; time.sleep(10)",
                ],
                environment={},
                root=ROOT,
                timeout_seconds=1,
            )
        self.assertLess(time.monotonic() - started, 7)

    def test_command_cancellation_rejects_new_launch(self) -> None:
        registry = CommandRegistry()
        registry.cancel()
        with self.assertRaises(RuntimeError):
            registry.run(
                [
                    str(ROOT / ".venv/bin/python"),
                    "-c",
                    "print('unexpected')",
                ],
                environment={},
                root=ROOT,
                timeout_seconds=1,
            )

    def test_command_output_limit_terminates_process_group(self) -> None:
        registry = CommandRegistry()
        with self.assertRaisesRegex(
            RuntimeError,
            "command output exceeds size limit",
        ):
            registry.run(
                [
                    str(ROOT / ".venv/bin/python"),
                    "-c",
                    (
                        "import sys; "
                        "sys.stdout.buffer.write(b'x' * (2 * 1024 * 1024)); "
                        "sys.stdout.flush()"
                    ),
                ],
                environment={},
                root=ROOT,
                timeout_seconds=5,
            )

    def test_impossible_free_space_requirement_is_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            require_free_space(ROOT, 1 << 100)

    def test_workspace_reserve_accounts_for_workers(self) -> None:
        self.assertEqual(
            workspace_free_space_requirement(
                minimum_bytes=100,
                workers=2,
                raw_proof_bytes=10,
                retained_proof_bytes=5,
            ),
            140,
        )

    def test_promotion_reserve_accounts_for_index_copy(self) -> None:
        self.assertEqual(
            promotion_index_free_space_requirement(
                minimum_bytes=100,
                index_bytes=25,
            ),
            125,
        )

    def test_staged_bundle_fields_drive_real_promotion(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        plan = json.loads(PLAN.read_text(encoding="ascii"))
        case_records = [
            {"plan_case": planned} for planned in plan["cases"]
        ]
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            parent = Path(directory)
            workspace = parent / "workspace"
            for planned in plan["cases"]:
                names = case_filenames(str(planned["branch_id"]))
                source = workspace / "cases" / branch_slug(
                    str(planned["branch_id"])
                )
                source.mkdir(parents=True)
                for filename in names.values():
                    (source / filename).write_bytes(
                        f"{filename}\n".encode("ascii")
                    )

            def fake_validate(
                _directory: Path,
                planned: dict[str, object],
            ) -> dict[str, object]:
                return {"plan_case": planned}

            def fake_index(
                record: dict[str, object],
                **_kwargs,
            ) -> dict[str, object]:
                planned = record["plan_case"]
                return {
                    "branch_id": planned["branch_id"],
                    "branch_sha256": planned["branch_sha256"],
                    "parent_child_id": planned["parent_child_id"],
                    "fourth_orbit_index": planned[
                        "fourth_orbit_index"
                    ],
                }

            proof_directory = parent / "proofs"
            output = parent / "index.json"
            journal = parent / ".promotion.json"
            with mock.patch(
                "fourth_word_drat.bundle.validate_case_directory",
                side_effect=fake_validate,
            ):
                with mock.patch(
                    "fourth_word_drat.bundle.validate_flat_case",
                    side_effect=fake_validate,
                ):
                    with mock.patch(
                        "fourth_word_drat.bundle.case_index_record",
                        side_effect=fake_index,
                    ):
                        with mock.patch(
                            "fourth_word_drat.bundle.require_free_space",
                        ):
                            staged = stage_bundle(
                                case_records,
                                root=ROOT,
                                workspace=workspace,
                                plan=plan,
                                plan_path=PLAN,
                                plan_sha256=file_sha256(PLAN),
                                proof_directory=proof_directory,
                                output_path=output,
                                checker_commit="2" * 40,
                                checker_sha256="3" * 64,
                                pipeline_files={},
                                pipeline_python_tree={},
                                solver_environment={},
                                resource_limits=(
                                    certification_resource_limits(1)
                                ),
                            )
            self.assertIsInstance(staged, StagedBundle)
            staged_index = json.loads(
                staged.index_path.read_text(encoding="ascii")
            )
            self.assertEqual(staged_index["case_count"], 140)
            self.assertEqual(len(staged_index["cases"]), 140)
            self.assertEqual(
                staged_index["resource_limits"],
                certification_resource_limits(1),
            )
            self.assertEqual(
                len(list(staged.proof_directory.iterdir())),
                420,
            )
            self.assertEqual(
                staged.proof_directory_sha256,
                directory_sha256(staged.proof_directory),
            )
            self.assertEqual(
                staged.index_sha256,
                file_sha256(staged.index_path),
            )
            self.assertEqual(
                staged.proof_directory_identity,
                artifact_path_identity(
                    staged.proof_directory,
                    directory=True,
                ),
            )
            self.assertEqual(
                staged.index_identity,
                artifact_path_identity(
                    staged.index_path,
                    directory=False,
                ),
            )
            promote_bundle(
                staged.proof_directory,
                staged.index_path,
                root=ROOT,
                proof_directory=proof_directory,
                output_path=output,
                journal_path=journal,
                token=staged.token,
                expected_directory_hash=(
                    staged.proof_directory_sha256
                ),
                expected_index_hash=staged.index_sha256,
                expected_staging_identity=(
                    staged.proof_directory_identity
                ),
                expected_staged_index_identity=staged.index_identity,
            )
            self.assertEqual(
                directory_sha256(proof_directory),
                staged.proof_directory_sha256,
            )
            self.assertEqual(file_sha256(output), staged.index_sha256)
            self.assertFalse(staged.proof_directory.exists())
            self.assertFalse(staged.index_path.exists())
            self.assertFalse(journal.exists())

    def test_proof_command_timeout_covers_inner_limits(self) -> None:
        self.assertEqual(PROOF_COMMAND_TIMEOUT_SECONDS, 2400)

    def test_certification_resource_limits_are_complete(self) -> None:
        self.assertEqual(
            certification_resource_limits(1),
            {
                "workers": 1,
                "minimum_free_bytes": 8 * 1024 * 1024 * 1024,
                "solve_seconds_per_case": 300,
                "raw_proof_bytes_per_case": 1024 * 1024 * 1024,
                "retained_proof_bytes_per_case": 256 * 1024 * 1024,
                "memory_watchdog_bytes_per_case": 12 * 1024 * 1024 * 1024,
                "checker_seconds_per_run": 900,
                "checker_output_bytes_per_run": 4 * 1024 * 1024,
                "proof_command_seconds": 2400,
            },
        )

    def test_certification_resource_limits_reject_bad_workers(self) -> None:
        for workers in (True, 0, 3):
            with self.subTest(workers=workers):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "worker count is invalid",
                ):
                    certification_resource_limits(workers)

    def test_certification_resource_limit_schema_is_required(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "certification resource limits are invalid",
        ):
            require_certification_resource_limits(
                {
                    "workers": 1,
                    "minimum_free_bytes": 8 * 1024 * 1024 * 1024,
                }
            )

    def test_solver_probe_ignores_unchecked_package_bytecode(self) -> None:
        spec = importlib.util.find_spec("pysat")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.origin)
        source = Path(str(spec.origin))
        cache = Path(importlib.util.cache_from_source(str(source)))
        cache.parent.mkdir(exist_ok=True)
        original = cache.read_bytes() if cache.exists() else None
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            fake_source = Path(directory) / "malicious.py"
            fake_source.write_text(
                "raise RuntimeError('unchecked solver bytecode executed')\n",
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
                record = solver_environment_record(
                    str(ROOT / ".venv/bin/python"),
                    environment=dict(os.environ),
                    root=ROOT,
                )
            finally:
                if original is None:
                    cache.unlink(missing_ok=True)
                else:
                    cache.write_bytes(original)
        self.assertEqual(
            record["python_sat_version"],
            record["python_sat_distribution_version"],
        )

    def test_repeated_signal_is_suppressed_during_cleanup(self) -> None:
        registry = CommandRegistry()
        with coordinator_signal_handlers(registry):
            with self.assertRaises(KeyboardInterrupt):
                os.kill(os.getpid(), signal.SIGINT)
            os.kill(os.getpid(), signal.SIGINT)

    def test_timeout_terminates_descendants_after_leader_exit(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            pid_path = Path(directory) / "child.pid"
            script = (
                "import subprocess,sys\n"
                "from pathlib import Path\n"
                "child=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(30)'])\n"
                "Path(sys.argv[1]).write_text(str(child.pid),"
                "encoding='ascii')\n"
            )
            registry = CommandRegistry()
            with self.assertRaises(RuntimeError):
                registry.run(
                    [
                        str(ROOT / ".venv/bin/python"),
                        "-c",
                        script,
                        str(pid_path),
                    ],
                    environment={},
                    root=ROOT,
                    timeout_seconds=1,
                )
            child_pid = int(pid_path.read_text(encoding="ascii"))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            else:
                self.fail("descendant process survived group cleanup")

    def test_active_command_is_terminated(self) -> None:
        registry = CommandRegistry()
        outcome = []

        def run_command() -> None:
            try:
                registry.run(
                    [
                        str(ROOT / ".venv/bin/python"),
                        "-c",
                        "import time; time.sleep(30)",
                    ],
                    environment={},
                    root=ROOT,
                    timeout_seconds=60,
                )
            except RuntimeError:
                outcome.append("terminated")

        worker = threading.Thread(target=run_command)
        worker.start()
        time.sleep(0.2)
        registry.terminate_all()
        worker.join(timeout=7)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcome, ["terminated"])


if __name__ == "__main__":
    unittest.main()
