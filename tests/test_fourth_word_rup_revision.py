from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manage_fourth_word_rup_revision import (
    BUNDLE_MANIFEST,
    OUTPUT_COMMITMENT_SCOPE,
    PROOF_INDEX,
    REPLAY_COMMANDS,
    REPLAY_REQUIREMENTS,
    RELEASE_MANIFEST,
    REPLAY_ATTESTATION,
    PYPI_INDEX,
    TOOLCHAIN_SOURCES,
    canonical_json,
    command_result,
    command_results_digest,
    finalize_record,
    finalized_record,
    git_bytes,
    pending_record,
    replay_git_command,
    require_clean_head,
    resolve_executable,
    run_clean_checkout_replay,
    sanitized_environment,
    validate_record_schema,
)


DIGEST = "a" * 64
REVISION = "b" * 40
TREE = "c" * 40
TOOLCHAIN = {
    role: {
        "source": source,
        "sha256": DIGEST,
    }
    for role, source in TOOLCHAIN_SOURCES.items()
}


def reference(path) -> dict[str, str]:
    return {"path": str(path), "sha256": DIGEST}


def valid_pending() -> dict[str, object]:
    return pending_record(
        proof_index=reference(PROOF_INDEX),
        bundle_manifest=reference(BUNDLE_MANIFEST),
        replay_attestation=reference(REPLAY_ATTESTATION),
    )


def replay_command_results() -> list[dict[str, object]]:
    outputs = [
        b"",
        b"",
        (REVISION + "\n").encode("ascii"),
        *([b""] * 7),
    ]
    return [
        command_result(command, output)
        for command, output in zip(REPLAY_COMMANDS, outputs)
    ]


class FourthWordRupRevisionTests(unittest.TestCase):
    def test_pending_record_requires_explicit_allowance(self) -> None:
        record = valid_pending()
        self.assertEqual(
            validate_record_schema(record, allow_pending=True),
            "pending-clean-checkout-replay",
        )
        with self.assertRaises(RuntimeError):
            validate_record_schema(record, allow_pending=False)

    def test_final_record_has_strict_revision_binding(self) -> None:
        record = finalized_record(
            valid_pending(),
            revision=REVISION,
            tree=TREE,
            release_manifest=reference(RELEASE_MANIFEST),
            completed_on="2026-09-03",
            command_results=replay_command_results(),
            toolchain=TOOLCHAIN,
        )
        self.assertEqual(
            validate_record_schema(record, allow_pending=False),
            "clean-checkout-replay-passed",
        )

    def test_final_record_has_strict_toolchain_attestation(self) -> None:
        record = finalized_record(
            valid_pending(),
            revision=REVISION,
            tree=TREE,
            release_manifest=reference(RELEASE_MANIFEST),
            completed_on="2026-09-03",
            command_results=replay_command_results(),
            toolchain=TOOLCHAIN,
        )
        for mutation in ("missing-role", "wrong-source", "bad-hash"):
            with self.subTest(mutation=mutation):
                changed = json.loads(json.dumps(record))
                if mutation == "missing-role":
                    del changed["clean_checkout_replay"]["toolchain"]["git"]
                elif mutation == "wrong-source":
                    changed["clean_checkout_replay"]["toolchain"]["git"][
                        "source"
                    ] = "ambient-path"
                else:
                    changed["clean_checkout_replay"]["toolchain"]["git"][
                        "sha256"
                    ] = "not-a-hash"
                with self.assertRaises(RuntimeError):
                    validate_record_schema(
                        changed,
                        allow_pending=False,
                    )

    def test_final_record_has_strict_command_results(self) -> None:
        record = finalized_record(
            valid_pending(),
            revision=REVISION,
            tree=TREE,
            release_manifest=reference(RELEASE_MANIFEST),
            completed_on="2026-09-03",
            command_results=replay_command_results(),
            toolchain=TOOLCHAIN,
        )
        for mutation in (
            "wrong-command",
            "nonzero-return",
            "wrong-byte-count",
            "bad-output-hash",
            "bad-results-digest",
            "missing-result",
        ):
            with self.subTest(mutation=mutation):
                changed = json.loads(json.dumps(record))
                replay = changed["clean_checkout_replay"]
                if mutation == "wrong-command":
                    replay["command_results"][0][
                        "command"
                    ] = "different command"
                elif mutation == "nonzero-return":
                    replay["command_results"][0]["return_code"] = 1
                elif mutation == "wrong-byte-count":
                    replay["command_results"][0]["output_bytes"] = -1
                elif mutation == "bad-output-hash":
                    replay["command_results"][0][
                        "output_sha256"
                    ] = "not-a-hash"
                elif mutation == "bad-results-digest":
                    replay["command_results_sha256"] = "f" * 64
                else:
                    replay["command_results"].pop()
                with self.assertRaises(RuntimeError):
                    validate_record_schema(
                        changed,
                        allow_pending=False,
                    )

    def test_command_result_semantics_reject_coordinated_mutation(
        self,
    ) -> None:
        record = finalized_record(
            valid_pending(),
            revision=REVISION,
            tree=TREE,
            release_manifest=reference(RELEASE_MANIFEST),
            completed_on="2026-09-03",
            command_results=replay_command_results(),
            toolchain=TOOLCHAIN,
        )
        mutations = (
            (2, b""),
            (8, b"unexpected diff output\n"),
            (9, b"?? unexpected-file\n"),
        )
        for index, output in mutations:
            with self.subTest(index=index):
                changed = json.loads(json.dumps(record))
                replay = changed["clean_checkout_replay"]
                replay["command_results"][index] = command_result(
                    REPLAY_COMMANDS[index],
                    output,
                )
                replay["command_results_sha256"] = command_results_digest(
                    replay["command_results"]
                )
                with self.assertRaises(RuntimeError):
                    validate_record_schema(
                        changed,
                        allow_pending=False,
                    )

    def test_output_commitment_scope_is_fixed(self) -> None:
        pending = valid_pending()
        self.assertEqual(
            pending["clean_checkout_replay"]["output_commitment_scope"],
            OUTPUT_COMMITMENT_SCOPE,
        )
        pending["clean_checkout_replay"][
            "output_commitment_scope"
        ] = "portable-output-identity"
        with self.assertRaises(RuntimeError):
            validate_record_schema(pending, allow_pending=True)

    def test_non_integer_schema_version_is_rejected(self) -> None:
        for value in (True, "1", 1.0):
            with self.subTest(value=value):
                record = valid_pending()
                record["schema_version"] = value
                with self.assertRaises(RuntimeError):
                    validate_record_schema(record, allow_pending=True)

    def test_artifact_path_changes_are_rejected(self) -> None:
        record = valid_pending()
        record["proof_index"]["path"] = "evidence/other.json"
        with self.assertRaises(RuntimeError):
            validate_record_schema(record, allow_pending=True)

    def test_finalization_requires_clean_matching_head(self) -> None:
        with patch(
            "manage_fourth_word_rup_revision.git_bytes",
            side_effect=[
                (REVISION + "\n").encode("ascii"),
                b" M evidence.json\n",
            ],
        ):
            with self.assertRaises(RuntimeError):
                require_clean_head(Path("/tmp/repository"), REVISION)

    def test_clean_replay_rejects_dirty_result(self) -> None:
        def fake_run_process(*args, **kwargs):
            description = kwargs["description"]
            if description == REPLAY_COMMANDS[2]:
                return (REVISION + "\n").encode("ascii")
            if description == REPLAY_COMMANDS[-1]:
                return b"?? unexpected.txt\n"
            return b""

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "manage_fourth_word_rup_revision.run_process",
                    side_effect=fake_run_process,
                ),
                patch(
                    "manage_fourth_word_rup_revision.resolve_executable",
                    return_value=sys.executable,
                ),
            ):
                with self.assertRaises(RuntimeError):
                    run_clean_checkout_replay(
                        root=Path(directory),
                        revision=REVISION,
                        python_command=sys.executable,
                    )

    def test_clean_replay_runs_exact_authenticated_sequence(self) -> None:
        calls = []

        def fake_run_process(*args, **kwargs):
            calls.append((args[0], kwargs))
            if kwargs["description"] == REPLAY_COMMANDS[2]:
                return (REVISION + "\n").encode("ascii")
            return b""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch(
                    "manage_fourth_word_rup_revision.run_process",
                    side_effect=fake_run_process,
                ),
                patch(
                    "manage_fourth_word_rup_revision.resolve_executable",
                    return_value=sys.executable,
                ),
            ):
                replay_result = run_clean_checkout_replay(
                    root=root,
                    revision=REVISION,
                    python_command=sys.executable,
                )
            replay_directory = (
                root / ".research-artifacts" / f"clean-replay-{REVISION}"
            )
            runtime_directory = (
                root
                / ".research-artifacts"
                / f".clean-replay-runtime-{REVISION}"
            )
            hooks_directory = runtime_directory / "hooks"
            expected_arguments = [
                replay_git_command(
                    sys.executable,
                    hooks_directory,
                    [
                        "clone",
                        "--no-hardlinks",
                        "--no-checkout",
                        "--quiet",
                        f"--template={runtime_directory / 'template'}",
                        str(root),
                        str(replay_directory),
                    ],
                ),
                replay_git_command(
                    sys.executable,
                    hooks_directory,
                    [
                        "-C",
                        str(replay_directory),
                        "checkout",
                        "--detach",
                        "--quiet",
                        REVISION,
                    ],
                ),
                replay_git_command(
                    sys.executable,
                    hooks_directory,
                    [
                        "-C",
                        str(replay_directory),
                        "rev-parse",
                        "HEAD",
                    ],
                ),
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "venv",
                    ".venv",
                ],
                [
                    str(replay_directory / ".venv/bin/python"),
                    "-I",
                    "-m",
                    "pip",
                    "install",
                    "--isolated",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--no-cache-dir",
                    "--require-hashes",
                    "--only-binary=:all:",
                    "--no-deps",
                    "--index-url",
                    PYPI_INDEX,
                    "-r",
                    str(REPLAY_REQUIREMENTS),
                ],
                [
                    sys.executable,
                    "test",
                    "PYTHON=.venv/bin/python",
                ],
                [
                    sys.executable,
                    "audit-fourth-word-rup-proofs",
                    "PYTHON=.venv/bin/python",
                ],
                [
                    sys.executable,
                    "verify-release-manifest",
                    "PYTHON=.venv/bin/python",
                    "ALLOW_PENDING_REVISION=1",
                ],
                replay_git_command(
                    sys.executable,
                    hooks_directory,
                    ["diff", "--no-ext-diff", "--exit-code"],
                ),
                replay_git_command(
                    sys.executable,
                    hooks_directory,
                    [
                        "status",
                        "--porcelain=v1",
                        "--untracked-files=all",
                    ],
                ),
            ]
            self.assertEqual(
                [arguments for arguments, _ in calls],
                expected_arguments,
            )
            self.assertEqual(
                [call["description"] for _, call in calls],
                REPLAY_COMMANDS,
            )
            self.assertEqual(
                [call["cwd"] for _, call in calls],
                [root, root, root] + [replay_directory] * 7,
            )
            environments = [call["environment"] for _, call in calls]
            self.assertTrue(
                all(environment == environments[0] for environment in environments)
            )
            self.assertEqual(
                environments[0]["HOME"],
                str(runtime_directory / "home"),
            )
            self.assertEqual(
                environments[0]["PIP_CONFIG_FILE"],
                os.devnull,
            )
            self.assertFalse(runtime_directory.exists())
        self.assertEqual(
            replay_result["command_results"],
            replay_command_results(),
        )
        self.assertEqual(
            replay_result["command_results_sha256"],
            command_results_digest(replay_command_results()),
        )
        executable_digest = hashlib.sha256(
            Path(sys.executable).read_bytes()
        ).hexdigest()
        self.assertEqual(
            replay_result["toolchain"],
            {
                role: {
                    "source": source,
                    "sha256": executable_digest,
                }
                for role, source in TOOLCHAIN_SOURCES.items()
            },
        )

    def test_git_environment_redirects_are_removed(self) -> None:
        redirected = {
            "GIT_DIR": "/tmp/other.git",
            "GIT_WORK_TREE": "/tmp/other",
            "GIT_OBJECT_DIRECTORY": "/tmp/objects",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/tmp/alternate",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.worktree",
            "GIT_CONFIG_VALUE_0": "/tmp/other",
            "MAKEFLAGS": "-i",
            "GNUMAKEFLAGS": "-k",
            "MAKEFILES": "/tmp/injected.mk",
            "MFLAGS": "-s",
            "PIP_INDEX_URL": "https://example.invalid/simple",
            "CC": "/tmp/compiler",
        }
        with patch.dict("os.environ", redirected, clear=False):
            environment = sanitized_environment(
                remove_repository_lock=True
            )
        for key in redirected:
            self.assertNotIn(key, environment)
        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertEqual(environment["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(environment["GIT_CONFIG_SYSTEM"], os.devnull)
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(environment["GIT_ATTR_NOSYSTEM"], "1")
        self.assertEqual(environment["PIP_CONFIG_FILE"], os.devnull)
        self.assertEqual(environment["PATH"], os.defpath)

    def test_clean_replay_requires_absolute_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "manage_fourth_word_rup_revision.run_process",
                ) as run_process,
                patch(
                    "manage_fourth_word_rup_revision.resolve_executable",
                    return_value=sys.executable,
                ) as resolver,
            ):
                with self.assertRaises(RuntimeError):
                    run_clean_checkout_replay(
                        root=Path(directory),
                        revision=REVISION,
                        python_command="python3",
                    )
        self.assertEqual(
            [call.args[0] for call in resolver.call_args_list],
            ["git", "make"],
        )
        run_process.assert_not_called()

    def test_make_finalization_uses_running_interpreter(self) -> None:
        root = Path(__file__).resolve().parents[1]
        make = resolve_executable(
            "make",
            environment=sanitized_environment(),
        )
        for python_assignment in ("PYTHON=python3", "PYTHON=python"):
            with self.subTest(python_assignment=python_assignment):
                result = subprocess.run(
                    [
                        make,
                        "-n",
                        "finalize-fourth-word-rup-revision",
                        python_assignment,
                        f"CERTIFIED_REVISION={REVISION}",
                        "CERTIFIED_REVISION_DATE=2026-09-03",
                    ],
                    check=True,
                    cwd=root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.assertIn(
                    "tools/manage_fourth_word_rup_revision.py",
                    result.stdout,
                )
                self.assertNotIn("--python", result.stdout)

    def test_clean_replay_ignores_ambient_path_executables(self) -> None:
        calls = []

        def fake_run_process(*args, **kwargs):
            calls.append((args[0], kwargs["description"]))
            if kwargs["description"] == REPLAY_COMMANDS[2]:
                return (REVISION + "\n").encode("ascii")
            return b""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            marker = root / "ambient-tool-ran"
            for name in ("git", "make"):
                executable = fake_bin / name
                executable.write_text(
                    f"#!/bin/sh\nprintf ran > {marker}\nexit 1\n",
                    encoding="ascii",
                )
                executable.chmod(0o755)
            fixed_environment = sanitized_environment(
                remove_repository_lock=True
            )
            fixed_git = resolve_executable(
                "git",
                environment=fixed_environment,
            )
            fixed_make = resolve_executable(
                "make",
                environment=fixed_environment,
            )
            with (
                patch.dict(
                    os.environ,
                    {"PATH": str(fake_bin)},
                    clear=False,
                ),
                patch(
                    "manage_fourth_word_rup_revision.run_process",
                    side_effect=fake_run_process,
                ),
            ):
                run_clean_checkout_replay(
                    root=root,
                    revision=REVISION,
                    python_command=sys.executable,
                )
            self.assertEqual(calls[0][0][0], fixed_git)
            for arguments, description in calls:
                if description in REPLAY_COMMANDS[5:8]:
                    self.assertEqual(arguments[0], fixed_make)
            self.assertFalse(marker.exists())

    def test_isolated_python_ignores_repository_shadow_modules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv_marker = root / "venv-shadow-ran"
            pip_marker = root / "pip-shadow-ran"
            (root / "venv.py").write_text(
                (
                    "from pathlib import Path\n"
                    f"Path({str(venv_marker)!r}).write_text('ran')\n"
                    "raise RuntimeError('shadowed venv')\n"
                ),
                encoding="ascii",
            )
            (root / "pip.py").write_text(
                (
                    "from pathlib import Path\n"
                    f"Path({str(pip_marker)!r}).write_text('ran')\n"
                    "raise RuntimeError('shadowed pip')\n"
                ),
                encoding="ascii",
            )
            isolated_venv = root / "isolated-venv"
            subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "venv",
                    str(isolated_venv),
                ],
                check=True,
                cwd=root,
            )
            subprocess.run(
                [
                    str(isolated_venv / "bin/python"),
                    "-I",
                    "-m",
                    "pip",
                    "--version",
                ],
                check=True,
                cwd=root,
                stdout=subprocess.PIPE,
            )
            self.assertFalse(venv_marker.exists())
            self.assertFalse(pip_marker.exists())

    def test_git_replay_ignores_global_hooks_and_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            clone = root / "clone"
            ambient_home = root / "ambient-home"
            ambient_hooks = root / "ambient-hooks"
            runtime = root / "runtime"
            for path in (
                source,
                ambient_home,
                ambient_hooks,
                runtime / "hooks",
                runtime / "template",
                runtime / "home",
                runtime / "config",
                runtime / "cache",
                runtime / "tmp",
            ):
                path.mkdir(parents=True, exist_ok=True)
            git = resolve_executable(
                "git",
                environment=sanitized_environment(),
            )
            setup_environment = {
                "PATH": os.defpath,
                "HOME": str(ambient_home),
                "LANG": "C",
                "LC_ALL": "C",
            }
            subprocess.run(
                [git, "init", "--quiet", str(source)],
                check=True,
                env=setup_environment,
            )
            (source / ".gitattributes").write_text(
                "payload.txt filter=poison\n",
                encoding="ascii",
            )
            (source / "payload.txt").write_text(
                "payload\n",
                encoding="ascii",
            )
            subprocess.run(
                [
                    git,
                    "-C",
                    str(source),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "add",
                    ".",
                ],
                check=True,
                env=setup_environment,
            )
            subprocess.run(
                [
                    git,
                    "-C",
                    str(source),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "fixture",
                ],
                check=True,
                env=setup_environment,
            )
            hook_marker = root / "hook-marker"
            filter_marker = root / "filter-marker"
            hook = ambient_hooks / "post-checkout"
            hook.write_text(
                f"#!/bin/sh\nprintf hook > {hook_marker}\n",
                encoding="ascii",
            )
            hook.chmod(0o755)
            filter_script = root / "smudge"
            filter_script.write_text(
                (
                    "#!/bin/sh\n"
                    f"printf filter > {filter_marker}\n"
                    "cat\n"
                ),
                encoding="ascii",
            )
            filter_script.chmod(0o755)
            subprocess.run(
                [
                    git,
                    "config",
                    "--global",
                    "core.hooksPath",
                    str(ambient_hooks),
                ],
                check=True,
                env=setup_environment,
            )
            subprocess.run(
                [
                    git,
                    "config",
                    "--global",
                    "filter.poison.smudge",
                    str(filter_script),
                ],
                check=True,
                env=setup_environment,
            )
            subprocess.run(
                [
                    git,
                    "config",
                    "--global",
                    "filter.poison.required",
                    "true",
                ],
                check=True,
                env=setup_environment,
            )
            with patch.dict(
                os.environ,
                {
                    "HOME": str(ambient_home),
                    "GIT_CONFIG_GLOBAL": str(
                        ambient_home / ".gitconfig"
                    ),
                },
                clear=False,
            ):
                environment = sanitized_environment(
                    remove_repository_lock=True
                )
            environment.update(
                {
                    "HOME": str(runtime / "home"),
                    "TMPDIR": str(runtime / "tmp"),
                    "XDG_CACHE_HOME": str(runtime / "cache"),
                    "XDG_CONFIG_HOME": str(runtime / "config"),
                }
            )
            subprocess.run(
                replay_git_command(
                    git,
                    runtime / "hooks",
                    [
                        "clone",
                        "--no-hardlinks",
                        "--no-checkout",
                        "--quiet",
                        f"--template={runtime / 'template'}",
                        str(source),
                        str(clone),
                    ],
                ),
                check=True,
                env=environment,
            )
            subprocess.run(
                replay_git_command(
                    git,
                    runtime / "hooks",
                    [
                        "-C",
                        str(clone),
                        "checkout",
                        "--detach",
                        "--quiet",
                        "HEAD",
                    ],
                ),
                check=True,
                env=environment,
            )
            self.assertEqual(
                (clone / "payload.txt").read_text(encoding="ascii"),
                "payload\n",
            )
            self.assertFalse(hook_marker.exists())
            self.assertFalse(filter_marker.exists())

    def test_git_bytes_disables_local_fsmonitor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git = resolve_executable(
                "git",
                environment=dict(os.environ),
            )
            environment = dict(os.environ)
            subprocess.run(
                [git, "init", "--quiet", str(root)],
                check=True,
                env=environment,
            )
            (root / "tracked.txt").write_text(
                "tracked\n",
                encoding="ascii",
            )
            subprocess.run(
                [
                    git,
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "add",
                    "tracked.txt",
                ],
                check=True,
                env=environment,
            )
            subprocess.run(
                [
                    git,
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "fixture",
                ],
                check=True,
                env=environment,
            )
            marker = root / "fsmonitor-ran"
            monitor = root / "fsmonitor"
            monitor.write_text(
                f"#!/bin/sh\nprintf monitor > {marker}\n",
                encoding="ascii",
            )
            monitor.chmod(0o755)
            subprocess.run(
                [
                    git,
                    "-C",
                    str(root),
                    "config",
                    "core.fsmonitor",
                    str(monitor),
                ],
                check=True,
                env=environment,
            )
            subprocess.run(
                [
                    git,
                    "-C",
                    str(root),
                    "status",
                    "--porcelain=v1",
                ],
                check=True,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertTrue(marker.is_file())
            marker.unlink()
            git_bytes(
                root,
                ["status", "--porcelain=v1"],
            )
            self.assertFalse(marker.exists())

    def test_replay_failure_leaves_pending_record_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_path = root / "revision.json"
            (root / PROOF_INDEX).parent.mkdir(parents=True)
            (root / PROOF_INDEX).write_text("{}", encoding="ascii")
            original = canonical_json(valid_pending())
            record_path.write_bytes(original)
            references = {
                PROOF_INDEX: reference(PROOF_INDEX),
                BUNDLE_MANIFEST: reference(BUNDLE_MANIFEST),
                REPLAY_ATTESTATION: reference(REPLAY_ATTESTATION),
                RELEASE_MANIFEST: reference(RELEASE_MANIFEST),
            }
            with (
                patch(
                    "manage_fourth_word_rup_revision.validate_artifact_references"
                ),
                patch(
                    "manage_fourth_word_rup_revision.resolve_revision",
                    return_value=(REVISION, TREE),
                ),
                patch(
                    "manage_fourth_word_rup_revision.require_clean_head"
                ),
                patch(
                    "manage_fourth_word_rup_revision.revision_reference",
                    side_effect=lambda _root, _revision, path: references[path],
                ),
                patch(
                    "manage_fourth_word_rup_revision.validate_frozen_sources"
                ),
                patch(
                    "manage_fourth_word_rup_revision.run_clean_checkout_replay",
                    side_effect=RuntimeError("replay failed"),
                ),
            ):
                with self.assertRaises(RuntimeError):
                    finalize_record(
                        record_path,
                        root=root,
                        revision_argument=REVISION,
                        completed_on="2026-09-03",
                        python_command=sys.executable,
                    )
            self.assertEqual(record_path.read_bytes(), original)

    def test_mid_replay_checkout_change_leaves_pending_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_path = root / "revision.json"
            (root / PROOF_INDEX).parent.mkdir(parents=True)
            (root / PROOF_INDEX).write_text("{}", encoding="ascii")
            original = canonical_json(valid_pending())
            record_path.write_bytes(original)
            references = {
                PROOF_INDEX: reference(PROOF_INDEX),
                BUNDLE_MANIFEST: reference(BUNDLE_MANIFEST),
                REPLAY_ATTESTATION: reference(REPLAY_ATTESTATION),
                RELEASE_MANIFEST: reference(RELEASE_MANIFEST),
            }
            with (
                patch(
                    "manage_fourth_word_rup_revision.validate_artifact_references"
                ),
                patch(
                    "manage_fourth_word_rup_revision.resolve_revision",
                    return_value=(REVISION, TREE),
                ),
                patch(
                    "manage_fourth_word_rup_revision.require_clean_head",
                    side_effect=[
                        None,
                        RuntimeError("checkout changed"),
                    ],
                ) as clean_head,
                patch(
                    "manage_fourth_word_rup_revision.revision_reference",
                    side_effect=lambda _root, _revision, path: references[path],
                ),
                patch(
                    "manage_fourth_word_rup_revision.validate_frozen_sources"
                ),
                patch(
                    "manage_fourth_word_rup_revision.run_clean_checkout_replay",
                    return_value={
                        "command_results": replay_command_results(),
                        "command_results_sha256": (
                            command_results_digest(
                                replay_command_results()
                            )
                        ),
                        "toolchain": TOOLCHAIN,
                    },
                ),
            ):
                with self.assertRaises(RuntimeError):
                    finalize_record(
                        record_path,
                        root=root,
                        revision_argument=REVISION,
                        completed_on="2026-09-03",
                        python_command=sys.executable,
                    )
            self.assertEqual(clean_head.call_count, 2)
            self.assertEqual(record_path.read_bytes(), original)

    def test_successful_replay_stores_returned_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_path = root / "revision.json"
            (root / PROOF_INDEX).parent.mkdir(parents=True)
            (root / PROOF_INDEX).write_text("{}", encoding="ascii")
            record_path.write_bytes(canonical_json(valid_pending()))
            replay_results = replay_command_results()
            replay_digest = command_results_digest(replay_results)
            references = {
                PROOF_INDEX: reference(PROOF_INDEX),
                BUNDLE_MANIFEST: reference(BUNDLE_MANIFEST),
                REPLAY_ATTESTATION: reference(REPLAY_ATTESTATION),
                RELEASE_MANIFEST: reference(RELEASE_MANIFEST),
            }
            with (
                patch(
                    "manage_fourth_word_rup_revision.validate_artifact_references"
                ),
                patch(
                    "manage_fourth_word_rup_revision.resolve_revision",
                    return_value=(REVISION, TREE),
                ),
                patch(
                    "manage_fourth_word_rup_revision.require_clean_head"
                ) as clean_head,
                patch(
                    "manage_fourth_word_rup_revision.revision_reference",
                    side_effect=lambda _root, _revision, path: references[path],
                ),
                patch(
                    "manage_fourth_word_rup_revision.validate_frozen_sources"
                ),
                patch(
                    "manage_fourth_word_rup_revision.run_clean_checkout_replay",
                    return_value={
                        "command_results": replay_results,
                        "command_results_sha256": replay_digest,
                        "toolchain": TOOLCHAIN,
                    },
                ),
                patch(
                    "manage_fourth_word_rup_revision.validate_final_record"
                ),
            ):
                result = finalize_record(
                    record_path,
                    root=root,
                    revision_argument=REVISION,
                    completed_on="2026-09-03",
                    python_command=sys.executable,
                )
            self.assertEqual(
                result["clean_checkout_replay"][
                    "command_results_sha256"
                ],
                replay_digest,
            )
            self.assertEqual(
                result["clean_checkout_replay"]["command_results"],
                replay_results,
            )
            self.assertEqual(
                result["clean_checkout_replay"]["toolchain"],
                TOOLCHAIN,
            )
            self.assertEqual(clean_head.call_count, 3)
            retained = json.loads(record_path.read_text(encoding="ascii"))
            self.assertEqual(retained, result)

    def test_matching_finalized_record_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            record_path = Path(directory) / "revision.json"
            record = finalized_record(
                valid_pending(),
                revision=REVISION,
                tree=TREE,
                release_manifest=reference(RELEASE_MANIFEST),
                completed_on="2026-09-03",
                command_results=replay_command_results(),
                toolchain=TOOLCHAIN,
            )
            record_path.write_bytes(canonical_json(record))
            with (
                patch(
                    "manage_fourth_word_rup_revision.validate_final_record"
                ) as validate,
                patch(
                    "manage_fourth_word_rup_revision.resolve_revision",
                    return_value=(REVISION, TREE),
                ),
                patch(
                    "manage_fourth_word_rup_revision.run_clean_checkout_replay"
                ) as replay,
            ):
                result = finalize_record(
                    record_path,
                    root=Path(directory),
                    revision_argument=REVISION,
                    completed_on="2026-09-03",
                    python_command=sys.executable,
                )
            self.assertEqual(result, record)
            validate.assert_called_once()
            replay.assert_not_called()

    def test_finalized_record_rejects_mismatched_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_path = root / "revision.json"
            record = finalized_record(
                valid_pending(),
                revision=REVISION,
                tree=TREE,
                release_manifest=reference(RELEASE_MANIFEST),
                completed_on="2026-09-03",
                command_results=replay_command_results(),
                toolchain=TOOLCHAIN,
            )
            record_path.write_bytes(canonical_json(record))
            with (
                patch(
                    "manage_fourth_word_rup_revision.validate_final_record"
                ),
                patch(
                    "manage_fourth_word_rup_revision.resolve_revision",
                    return_value=("e" * 40, TREE),
                ),
            ):
                with self.assertRaises(RuntimeError):
                    finalize_record(
                        record_path,
                        root=root,
                        revision_argument="e" * 40,
                        completed_on="2026-09-03",
                        python_command=sys.executable,
                    )
            with (
                patch(
                    "manage_fourth_word_rup_revision.validate_final_record"
                ),
                patch(
                    "manage_fourth_word_rup_revision.resolve_revision",
                    return_value=(REVISION, TREE),
                ),
            ):
                with self.assertRaises(RuntimeError):
                    finalize_record(
                        record_path,
                        root=root,
                        revision_argument=REVISION,
                        completed_on="2026-09-02",
                        python_command=sys.executable,
                    )


if __name__ == "__main__":
    unittest.main()
