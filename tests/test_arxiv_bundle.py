from __future__ import annotations

import gzip
import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from tools.build_arxiv_bundle import SOURCE_MAP, build_arxiv_bundle
from tools.replay_arxiv_bundle import replay_bundle
from tools.verify_technical_report import verify


ROOT = Path(__file__).resolve().parents[1]
COMMITTED_BUNDLE = ROOT / "dist/arxiv/binary-covering-code-11-3.tar.gz"


def read_archive(path: Path) -> list[tuple[str, bytes]]:
    with tarfile.open(path, "r:gz") as archive:
        entries: list[tuple[str, bytes]] = []
        for member in archive.getmembers():
            source = archive.extractfile(member)
            if source is None:
                raise AssertionError(
                    f"cannot read test archive member: {member.name}"
                )
            entries.append((member.name, source.read()))
        return entries


def write_archive(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with (
        path.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed,
        tarfile.open(
            fileobj=compressed,
            mode="w",
            format=tarfile.USTAR_FORMAT,
        ) as archive,
    ):
        for name, payload in entries:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))


def root_manifest(entries: list[tuple[str, bytes]]) -> bytes:
    return (
        "\n".join(
            f"{hashlib.sha256(payload).hexdigest()}  {name}"
            for name, payload in sorted(entries)
            if name != "MANIFEST.sha256"
        )
        + "\n"
    ).encode("ascii")


class TechnicalReportTests(unittest.TestCase):
    def test_compact_evidence_verifies(self) -> None:
        result = verify()
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["exact_value_resolved"])
        self.assertEqual(result["residual_normalized_branches"], 38)
        self.assertEqual(result["residual_selected_fourth_word_branches"], 26)

    def test_bundle_is_deterministic_and_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.tar.gz"
            second = Path(directory) / "second.tar.gz"
            build_arxiv_bundle(first)
            build_arxiv_bundle(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first, "r:gz") as archive:
                self.assertEqual(
                    archive.getnames(),
                    sorted(
                        [archive_name for _, archive_name in SOURCE_MAP]
                        + ["MANIFEST.sha256"]
                    ),
                )
                self.assertTrue(all(member.isfile() for member in archive))

    def test_committed_bundle_matches_fresh_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rebuilt = Path(directory) / "rebuilt.tar.gz"
            build_arxiv_bundle(rebuilt)
            self.assertEqual(COMMITTED_BUNDLE.read_bytes(), rebuilt.read_bytes())

    def test_archive_manifest_covers_every_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle.tar.gz"
            build_arxiv_bundle(output)
            with tarfile.open(output, "r:gz") as archive:
                manifest = archive.extractfile("MANIFEST.sha256")
                self.assertIsNotNone(manifest)
                expected: dict[str, str] = {}
                for line in manifest.read().decode("ascii").splitlines():
                    digest, name = line.split("  ", maxsplit=1)
                    expected[name] = digest
                self.assertEqual(
                    set(expected),
                    set(archive.getnames()) - {"MANIFEST.sha256"},
                )
                for name, digest in expected.items():
                    source = archive.extractfile(name)
                    self.assertIsNotNone(source)
                    self.assertEqual(
                        hashlib.sha256(source.read()).hexdigest(),
                        digest,
                        name,
                    )

    def test_bundle_replays_from_clean_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle.tar.gz"
            build_arxiv_bundle(output)
            replay_bundle(output)

    def test_replay_rejects_self_consistent_malicious_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.tar.gz"
            malicious = Path(directory) / "malicious.tar.gz"
            build_arxiv_bundle(original)
            entries = [
                (name, b"raise SystemExit('malicious replay executed')\n")
                if name == "replay.py"
                else (name, payload)
                for name, payload in read_archive(original)
            ]
            manifest = root_manifest(entries)
            entries = [
                (name, manifest)
                if name == "MANIFEST.sha256"
                else (name, payload)
                for name, payload in entries
            ]
            write_archive(malicious, entries)
            with self.assertRaisesRegex(ValueError, "trusted source"):
                replay_bundle(malicious)

    def test_replay_rejects_duplicate_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.tar.gz"
            duplicated = Path(directory) / "duplicated.tar.gz"
            build_arxiv_bundle(original)
            entries = read_archive(original)
            readme = next(
                payload for name, payload in entries if name == "README.txt"
            )
            write_archive(duplicated, entries + [("README.txt", readme)])
            with self.assertRaisesRegex(ValueError, "unsafe arXiv archive member"):
                replay_bundle(duplicated)

    def test_replay_rejects_unsafe_paths_and_member_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            traversal = Path(directory) / "traversal.tar.gz"
            write_archive(traversal, [("../outside", b"x")])
            with self.assertRaisesRegex(ValueError, "unsafe archive path"):
                replay_bundle(traversal)

            backslash = Path(directory) / "backslash.tar.gz"
            write_archive(backslash, [("bad\\path", b"x")])
            with self.assertRaisesRegex(ValueError, "unsafe archive path"):
                replay_bundle(backslash)

            symlink = Path(directory) / "symlink.tar.gz"
            with (
                symlink.open("wb") as raw,
                gzip.GzipFile(
                    fileobj=raw,
                    mode="wb",
                    filename="",
                    mtime=0,
                ) as compressed,
                tarfile.open(
                    fileobj=compressed,
                    mode="w",
                    format=tarfile.USTAR_FORMAT,
                ) as archive,
            ):
                info = tarfile.TarInfo("README.txt")
                info.type = tarfile.SYMTYPE
                info.linkname = "replay.py"
                info.mode = 0o644
                info.mtime = 0
                archive.addfile(info)
            with self.assertRaisesRegex(ValueError, "unsafe arXiv archive member"):
                replay_bundle(symlink)

    def test_replay_rejects_pax_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pax.tar.gz"
            with (
                path.open("wb") as raw,
                gzip.GzipFile(
                    fileobj=raw,
                    mode="wb",
                    filename="",
                    mtime=0,
                ) as compressed,
                tarfile.open(
                    fileobj=compressed,
                    mode="w",
                    format=tarfile.PAX_FORMAT,
                ) as archive,
            ):
                payload = b"x"
                info = tarfile.TarInfo("README.txt")
                info.size = len(payload)
                info.mode = 0o644
                info.mtime = 0
                info.pax_headers = {"comment": "not canonical"}
                archive.addfile(info, io.BytesIO(payload))
            with self.assertRaisesRegex(
                ValueError,
                "unsupported tar extension",
            ):
                replay_bundle(path)

    def test_replay_rejects_extensions_before_declared_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for member_type in (
                tarfile.XHDTYPE,
                tarfile.XGLTYPE,
                tarfile.GNUTYPE_LONGNAME,
                tarfile.GNUTYPE_LONGLINK,
            ):
                with self.subTest(member_type=member_type):
                    info = tarfile.TarInfo("extension")
                    info.type = member_type
                    info.size = 1 << 30
                    info.mode = 0o644
                    info.mtime = 0
                    raw_tar = (
                        info.tobuf(format=tarfile.USTAR_FORMAT)
                        + bytes(1024)
                    )
                    path = Path(directory) / (
                        f"extension-{member_type.hex()}.tar.gz"
                    )
                    path.write_bytes(gzip.compress(raw_tar, mtime=0))
                    with self.assertRaisesRegex(
                        ValueError,
                        "unsupported tar extension",
                    ):
                        replay_bundle(path)

    def test_replay_enforces_resource_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle.tar.gz"
            build_arxiv_bundle(output)
            with self.assertRaisesRegex(ValueError, "too many members"):
                replay_bundle(output, max_members=1)
            with self.assertRaisesRegex(ValueError, "member exceeds size limit"):
                replay_bundle(output, max_member_bytes=1)
            with self.assertRaisesRegex(ValueError, "total size limit"):
                replay_bundle(output, max_total_bytes=1)


if __name__ == "__main__":
    unittest.main()
