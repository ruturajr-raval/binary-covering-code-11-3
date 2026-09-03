from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/verify_checksum_manifest.py"
ARTIFACTS = ROOT / ".research-artifacts"


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def write_manifest(manifest: Path, paths: list[Path]) -> None:
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative(path)}"
        for path in paths
    ]
    manifest.write_text("\n".join(lines) + "\n", encoding="ascii")


def run_verifier(
    manifest: Path,
    *,
    paths: list[Path] | None = None,
    trees: list[Path] | None = None,
) -> subprocess.CompletedProcess[str]:
    arguments = [sys.executable, str(TOOL), relative(manifest)]
    for path in paths or []:
        arguments.extend(["--path", relative(path)])
    for tree in trees or []:
        arguments.extend(["--tree", relative(tree)])
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


class VerifyChecksumManifestTests(unittest.TestCase):
    def test_exact_tree_and_path_membership_passes(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            tree = base / "tree"
            tree.mkdir()
            first = tree / "first.txt"
            second = tree / "second.txt"
            outside = base / "outside.txt"
            first.write_text("first\n", encoding="ascii")
            second.write_text("second\n", encoding="ascii")
            outside.write_text("outside\n", encoding="ascii")
            manifest = base / "manifest.sha256"
            write_manifest(manifest, [first, outside, second])
            result = run_verifier(
                manifest,
                paths=[outside],
                trees=[tree],
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"artifact_count": 3', result.stdout)

    def test_missing_tree_entry_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            tree = base / "tree"
            tree.mkdir()
            first = tree / "first.txt"
            second = tree / "second.txt"
            first.write_text("first\n", encoding="ascii")
            second.write_text("second\n", encoding="ascii")
            manifest = base / "manifest.sha256"
            write_manifest(manifest, [first])
            result = run_verifier(manifest, trees=[tree])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("membership is incorrect", result.stderr)

    def test_duplicate_manifest_path_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            artifact = base / "artifact.txt"
            artifact.write_text("artifact\n", encoding="ascii")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            line = f"{digest}  {relative(artifact)}\n"
            manifest = base / "manifest.sha256"
            manifest.write_text(line + line, encoding="ascii")
            result = run_verifier(manifest, paths=[artifact])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate path", result.stderr)

    def test_undeclared_manifest_entry_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            declared = base / "declared.txt"
            extra = base / "extra.txt"
            declared.write_text("declared\n", encoding="ascii")
            extra.write_text("extra\n", encoding="ascii")
            manifest = base / "manifest.sha256"
            write_manifest(manifest, [declared, extra])
            result = run_verifier(manifest, paths=[declared])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("membership is incorrect", result.stderr)

    def test_parent_traversal_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            artifact = base / "artifact.txt"
            artifact.write_text("artifact\n", encoding="ascii")
            manifest = base / "manifest.sha256"
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            manifest.write_text(
                f"{digest}  ../artifact.txt\n",
                encoding="ascii",
            )
            result = run_verifier(manifest, paths=[artifact])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not canonical", result.stderr)

    def test_symbolic_link_artifact_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            target = base / "target.txt"
            target.write_text("target\n", encoding="ascii")
            link = base / "link.txt"
            link.symlink_to(target)
            manifest = base / "manifest.sha256"
            write_manifest(manifest, [target])
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            manifest.write_text(
                f"{digest}  {relative(link)}\n",
                encoding="ascii",
            )
            result = run_verifier(manifest, paths=[link])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symbolic link", result.stderr)

    def test_hard_linked_artifact_is_rejected(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            artifact = base / "artifact.txt"
            alias = base / "alias.txt"
            artifact.write_text("artifact\n", encoding="ascii")
            os.link(artifact, alias)
            manifest = base / "manifest.sha256"
            write_manifest(manifest, [artifact])
            result = run_verifier(manifest, paths=[artifact])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("single-link regular file", result.stderr)


if __name__ == "__main__":
    unittest.main()
