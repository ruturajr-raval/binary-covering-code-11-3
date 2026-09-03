from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "release-tools/manage_fourth_word_solver_drat_revision.py"
)
SPEC = importlib.util.spec_from_file_location(
    "manage_fourth_word_solver_drat_revision",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
revision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(revision)
ARTIFACTS = ROOT / ".research-artifacts"
ARTIFACTS.mkdir(exist_ok=True)


def valid_command_results(source: str) -> list[dict[str, object]]:
    outputs = [b"" for _ in revision.REPLAY_COMMANDS]
    outputs[2] = (source + "\n").encode("ascii")
    outputs[5] = (
        b"test_canonical_replay_root_rejects_symlink_parent ... ok\n"
        b"test_finalization_git_parent_paths_and_modes ... ok\n"
        b"test_retained_bundle_and_root_manifests_validate ... ok\n"
        b"test_retained_output_tampering_is_rejected ... ok\n"
        b"test_supported_python_record_is_strict ... ok\n"
        b"\nRan 14 tests in 0.100s\n\nOK\n"
    )
    outputs[6] = b"\nRan 80 tests in 1.000s\n\nOK\n"
    outputs[8] = (
        json.dumps(
            {
                "case_count": 140,
                "remaining_count": 26,
                "selected_set_sha256": (
                    "314c573765bc28fd8556db41fec2aa4f"
                    "7e6e7b5b1266c7a0906c1b23dcaec034"
                ),
                "valid": True,
            }
        ).encode("ascii")
        + b"\n"
    )
    outputs[9] = (
        json.dumps(
            {
                "case_count": 140,
                "proof_directory_sha256": (
                    "44504c6320ac22ad62507f70222c2e8b"
                    "9e6a51977f27ca3c936019c9f657f08f"
                ),
                "proof_index_sha256": (
                    "342c94b10eb182b18c369a526e3fc9d5"
                    "ac2b9fc9faa8943b687ea1a357ce3ca8"
                ),
                "proofs_replayed": True,
                "valid": True,
            }
        ).encode("ascii")
        + b"\n"
    )
    outputs[10] = (
        json.dumps(
            {
                "artifact_count": 422,
                "manifest": (
                    revision.BUNDLE_MANIFEST_PATH.as_posix()
                ),
                "valid": True,
            }
        ).encode("ascii")
        + b"\n"
    )
    outputs[11] = (
        json.dumps(
            {
                "artifact_count": 23,
                "manifest": (
                    revision.RELEASE_MANIFEST_PATH.as_posix()
                ),
                "valid": True,
            }
        ).encode("ascii")
        + b"\n"
    )
    return [
        revision.command_result(command, output)
        for command, output in zip(revision.REPLAY_COMMANDS, outputs)
    ]


class SolverDratRevisionTests(unittest.TestCase):
    def test_directory_digest_matches_bundle_definition(self) -> None:
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            root = Path(directory)
            (root / "b").write_bytes(b"second")
            (root / "a").write_bytes(b"first")
            payload = (
                "a:"
                + revision.sha256_bytes(b"first")
                + "\n"
                + "b:"
                + revision.sha256_bytes(b"second")
                + "\n"
            ).encode("ascii")
            self.assertEqual(
                revision.directory_sha256(root),
                revision.sha256_bytes(payload),
            )

    def test_checksum_manifest_rejects_duplicate_path(self) -> None:
        line = f"{'0' * 64}  a\n"
        with self.assertRaisesRegex(RuntimeError, "repeats path"):
            revision.parse_checksum_manifest(
                (line + line).encode("ascii")
            )

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "duplicate key"):
            revision.load_json_bytes(
                b'{"valid":true,"valid":false}\n',
                "test record",
            )

    def test_nested_json_result_is_not_accepted(self) -> None:
        output = (
            b'{"valid":false,"nested":\n'
            b'{\n'
            b'  "artifact_count":422,\n'
            b'  "manifest":"'
            + revision.BUNDLE_MANIFEST_PATH.as_posix().encode("ascii")
            + b'",\n'
            b'  "valid":true\n'
            b'}\n'
            b'}\n'
        )
        with self.assertRaisesRegex(RuntimeError, "final JSON"):
            revision.require_json_result(
                output,
                {
                    "artifact_count": 422,
                    "manifest": (
                        revision.BUNDLE_MANIFEST_PATH.as_posix()
                    ),
                    "valid": True,
                },
            )
        for prefix in (b"", b" ", b"log: "):
            with self.subTest(prefix=prefix):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "malformed top-level JSON",
                ):
                    revision.require_json_result(
                        prefix + output[:-2],
                        {
                            "artifact_count": 422,
                            "manifest": (
                                revision.BUNDLE_MANIFEST_PATH.as_posix()
                            ),
                            "valid": True,
                        },
                    )

    def test_command_results_require_clean_semantic_outputs(self) -> None:
        source = "1" * 40
        self.assertEqual(
            revision.REPLAY_COMMANDS[7],
            (
                "make prepare-fourth-word-proof-formulas "
                "PYTHON=.venv/bin/python"
            ),
        )
        self.assertEqual(
            revision.REPLAY_COMMANDS[9],
            "make -C proof-expansion audit-bundle",
        )
        results = valid_command_results(source)
        revision.validate_command_results(results, source)
        results[-1] = revision.command_result(
            revision.REPLAY_COMMANDS[-1],
            b"untracked\n",
        )
        with self.assertRaisesRegex(
            RuntimeError,
            "final repository output",
        ):
            revision.validate_command_results(results, source)

    def test_retained_output_tampering_is_rejected(self) -> None:
        source = "1" * 40
        results = valid_command_results(source)
        audit_index = revision.REPLAY_COMMANDS.index(
            "make -C proof-expansion audit-bundle"
        )
        results[audit_index]["output_base64"] = "e30K"
        with self.assertRaisesRegex(
            RuntimeError,
            "retained output differs",
        ):
            revision.validate_command_results(results, source)

    def test_finalization_path_policy_rejects_extra_file(self) -> None:
        changed = {
            path.as_posix()
            for path in revision.FINALIZATION_REQUIRED_PATHS
        }
        changed.add("proof-expansion/cli/audit_bundle.py")
        with self.assertRaisesRegex(RuntimeError, "extra="):
            revision.validate_finalization_paths(changed)

    def test_finalization_path_policy_rejects_missing_file(self) -> None:
        changed = {
            path.as_posix()
            for path in revision.FINALIZATION_REQUIRED_PATHS
        }
        changed.remove("release.json")
        with self.assertRaisesRegex(RuntimeError, "missing="):
            revision.validate_finalization_paths(changed)

    def test_supported_python_record_is_strict(self) -> None:
        self.assertEqual(
            revision.require_supported_python_record(
                {
                    "implementation": "CPython",
                    "major": 3,
                    "minor": 12,
                }
            )["minor"],
            12,
        )
        with self.assertRaisesRegex(
            RuntimeError,
            "CPython 3.9 through 3.12",
        ):
            revision.require_supported_python_record(
                {
                    "implementation": "CPython",
                    "major": 3,
                    "minor": 14,
                }
            )

    def test_canonical_replay_root_rejects_symlink_parent(self) -> None:
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            root = Path(directory) / "repository"
            outside = Path(directory) / "outside"
            root.mkdir()
            outside.mkdir()
            (root / ".research-artifacts").symlink_to(
                outside,
                target_is_directory=True,
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "contains a symlink",
            ):
                revision.canonical_replay_root(root, "1" * 40)

    def test_finalization_git_parent_paths_and_modes(self) -> None:
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            root = Path(directory) / "repository"
            root.mkdir()

            def git(*arguments: str) -> str:
                result = subprocess.run(
                    ["git", "-C", str(root), *arguments],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                return result.stdout.strip()

            git("init", "-q")
            git("config", "user.name", "Test Author")
            git("config", "user.email", "test@example.invalid")
            for relative in revision.FINALIZATION_REQUIRED_PATHS:
                if relative == revision.RECORD_PATH:
                    continue
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("source\n", encoding="ascii")
            git("add", ".")
            git("commit", "-qm", "source")
            source = git("rev-parse", "HEAD")

            for relative in revision.FINALIZATION_REQUIRED_PATHS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("release\n", encoding="ascii")
            git("add", ".")
            git("commit", "-qm", "release")
            release = git("rev-parse", "HEAD")

            revision.require_single_parent_release(
                root,
                source,
                release,
            )
            changed = revision.finalization_changed_paths(
                root,
                source,
                release,
            )
            revision.validate_finalization_paths(changed)
            for relative in changed:
                revision.require_regular_git_blob(
                    root,
                    release,
                    relative,
                )

            evidence = root / "evidence.json"
            evidence.unlink()
            evidence.symlink_to("release.json")
            git("add", "evidence.json")
            git("commit", "-qm", "replace with symlink")
            symlink_revision = git("rev-parse", "HEAD")
            with self.assertRaisesRegex(
                RuntimeError,
                "regular Git file",
            ):
                revision.require_regular_git_blob(
                    root,
                    symlink_revision,
                    "evidence.json",
                )

    def test_retained_bundle_and_root_manifests_validate(self) -> None:
        v2 = revision.validate_v2_bundle(ROOT)
        self.assertEqual(v2["artifact_count"], 422)
        self.assertEqual(v2["proof_artifact_count"], 420)
        self.assertEqual(
            v2["proof_directory_sha256"],
            "44504c6320ac22ad62507f70222c2e8b"
            "9e6a51977f27ca3c936019c9f657f08f",
        )
        self.assertEqual(
            revision.validate_root_release_manifest(ROOT),
            revision.file_sha256(
                ROOT / revision.RELEASE_MANIFEST_PATH
            ),
        )

    def test_record_schema_rejects_wrong_result_scope(self) -> None:
        source = "1" * 40
        results = valid_command_results(source)
        toolchain = {
            role: {
                "source": source_name,
                "sha256": "2" * 64,
            }
            for role, source_name in (
                ("git", "system-default-path"),
                ("make", "system-default-path"),
                ("python", "explicit-absolute-path"),
            )
        }
        record = {
            "schema_version": revision.SCHEMA_VERSION,
            "record_type": revision.RECORD_TYPE,
            "status": revision.STATUS,
            "certified_revision": source,
            "certified_tree": "3" * 40,
            "certified_release_manifest": {
                "path": revision.RELEASE_MANIFEST_PATH.as_posix(),
                "sha256": "4" * 64,
            },
            "revision_manager": {
                "path": revision.MANAGER_PATH.as_posix(),
                "sha256": "5" * 64,
            },
            "solver_drat_plan": {
                "path": revision.PLAN_PATH.as_posix(),
                "sha256": "6" * 64,
            },
            "solver_drat_index": {
                "path": revision.INDEX_PATH.as_posix(),
                "sha256": "7" * 64,
            },
            "solver_drat_bundle_manifest": {
                "path": revision.BUNDLE_MANIFEST_PATH.as_posix(),
                "sha256": "8" * 64,
            },
            "proof_directory": {
                "path": revision.PROOF_DIRECTORY.as_posix(),
                "artifact_count": 420,
                "sha256": "9" * 64,
            },
            "result": {
                "frontier_branch_count": 350,
                "prior_rup_certified_branch_count": 184,
                "newly_certified_branch_count": 140,
                "combined_certified_branch_count": 323,
                "remaining_branch_count": 27,
                "fully_closed_selected_child_count": 0,
                "fully_closed_normalized_parent_count": 0,
                "covering_number_status": "15 or 16",
            },
            "clean_checkout_replay": {
                "completed_on": "2026-09-03",
                "passed": True,
                "revision": source,
                "commands": list(revision.REPLAY_COMMANDS),
                "command_results": results,
                "command_results_sha256": (
                    revision.command_results_digest(results, source)
                ),
                "output_commitment_scope": (
                    revision.OUTPUT_COMMITMENT_SCOPE
                ),
                "toolchain": toolchain,
                "working_tree_clean": True,
                "proofs_replayed": True,
            },
            "finalization_policy": {
                "required_parent": source,
                "allowed_changed_paths": [
                    path.as_posix()
                    for path in revision.FINALIZATION_ALLOWED_PATHS
                ],
                "required_changed_paths": [
                    path.as_posix()
                    for path in revision.FINALIZATION_REQUIRED_PATHS
                ],
                "release_revision_rule": (
                    "current HEAD must be a clean single-parent child "
                    "of the certified revision"
                ),
            },
        }
        with self.assertRaisesRegex(RuntimeError, "result scope"):
            revision.validate_record_schema(record)

    def test_record_json_is_ascii_canonical(self) -> None:
        payload = revision.canonical_json({"b": 2, "a": 1})
        self.assertEqual(
            json.loads(payload.decode("ascii")),
            {"a": 1, "b": 2},
        )
        self.assertTrue(payload.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
