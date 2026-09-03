from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import bootstrap_drat_trim as bootstrap
from bootstrap_drat_trim import (
    repository_path,
    validate_clean_checkout,
    validate_pinned_checkout,
    validate_tracked_sources,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".research-artifacts"


def run(*arguments: str, cwd: Path) -> None:
    subprocess.run(
        list(arguments),
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def output(*arguments: str, cwd: Path) -> str:
    return subprocess.run(
        list(arguments),
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    ).stdout.strip()


def create_checkout(directory: Path) -> tuple[Path, str]:
    checkout = directory / "checkout"
    checkout.mkdir()
    run("git", "init", cwd=checkout)
    source = checkout / "checker.c"
    source.write_text("int main(void) { return 0; }\n")
    run("git", "add", "checker.c", cwd=checkout)
    run(
        "git",
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "initial",
        cwd=checkout,
    )
    return checkout, output("git", "rev-parse", "HEAD", cwd=checkout)


class BootstrapDratTrimTests(unittest.TestCase):
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
                repository_path(link / "checkout", ROOT)

    def test_dirty_tracked_checkout_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            checkout = Path(directory)
            run("git", "init", cwd=checkout)
            source = checkout / "checker.c"
            source.write_text("int main(void) { return 0; }\n")
            run("git", "add", "checker.c", cwd=checkout)
            run(
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-m",
                "initial",
                cwd=checkout,
            )
            source.write_text("int main(void) { return 1; }\n")
            with self.assertRaisesRegex(
                RuntimeError,
                "checkout is not clean",
            ):
                validate_clean_checkout(checkout)

    def test_hard_linked_tracked_source_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            checkout, _ = create_checkout(Path(directory))
            source = checkout / "checker.c"
            alias = checkout / "checker-alias.c"
            os.link(source, alias)
            with self.assertRaisesRegex(
                RuntimeError,
                "multiple links",
            ):
                validate_tracked_sources(checkout)

    def test_assume_unchanged_index_flag_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            checkout, commit = create_checkout(Path(directory))
            run(
                "git",
                "update-index",
                "--assume-unchanged",
                "checker.c",
                cwd=checkout,
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "hidden state",
            ):
                validate_pinned_checkout(checkout, commit)

    def test_modified_tracked_source_bytes_are_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            checkout, commit = create_checkout(Path(directory))
            source = checkout / "checker.c"
            source.write_text("int main(void) { return 2; }\n")
            with self.assertRaisesRegex(
                RuntimeError,
                "source bytes changed",
            ):
                validate_pinned_checkout(checkout, commit)

    def test_skip_worktree_index_flag_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            checkout, commit = create_checkout(Path(directory))
            run(
                "git",
                "update-index",
                "--skip-worktree",
                "checker.c",
                cwd=checkout,
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "hidden state",
            ):
                validate_pinned_checkout(checkout, commit)

    def test_filter_attribute_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            checkout, commit = create_checkout(Path(directory))
            attributes = checkout / ".git/info/attributes"
            attributes.write_text("checker.c filter=untrusted\n")
            with self.assertRaisesRegex(
                RuntimeError,
                "control file is not allowed",
            ):
                validate_pinned_checkout(checkout, commit)

    def test_checkout_hooks_are_disabled(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            checkout, first_commit = create_checkout(Path(directory))
            source = checkout / "checker.c"
            source.write_text("int main(void) { return 3; }\n")
            run("git", "add", "checker.c", cwd=checkout)
            run(
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-m",
                "second",
                cwd=checkout,
            )
            marker = checkout / "hook-ran"
            hook = checkout / ".git/hooks/post-checkout"
            hook.write_text(
                "#!/bin/sh\n"
                f"printf invoked > {marker}\n",
                encoding="ascii",
            )
            hook.chmod(0o755)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(checkout),
                    "checkout",
                    "--detach",
                    first_commit,
                ],
                check=True,
                capture_output=True,
                text=True,
                env=bootstrap.secure_git_environment(),
            )
            self.assertFalse(marker.exists())

    def test_replacement_ref_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            checkout, first_commit = create_checkout(Path(directory))
            source = checkout / "checker.c"
            source.write_text("int main(void) { return 1; }\n")
            run("git", "add", "checker.c", cwd=checkout)
            run(
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-m",
                "second",
                cwd=checkout,
            )
            second_commit = output(
                "git",
                "rev-parse",
                "HEAD",
                cwd=checkout,
            )
            run(
                "git",
                "replace",
                first_commit,
                second_commit,
                cwd=checkout,
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "replacement refs",
            ):
                validate_pinned_checkout(checkout, second_commit)

    def test_unexpected_ignored_file_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            checkout, commit = create_checkout(Path(directory))
            (checkout / ".gitignore").write_text("hidden.h\n")
            run("git", "add", ".gitignore", cwd=checkout)
            run(
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-m",
                "ignore generated header",
                cwd=checkout,
            )
            commit = output("git", "rev-parse", "HEAD", cwd=checkout)
            (checkout / "hidden.h").write_text("#define VALUE 1\n")
            with self.assertRaisesRegex(
                RuntimeError,
                "worktree file set is incorrect",
            ):
                validate_pinned_checkout(checkout, commit)


if __name__ == "__main__":
    unittest.main()
