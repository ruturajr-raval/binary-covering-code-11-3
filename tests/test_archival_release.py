from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.build_archival_release import (
    CHECKSUM_NAME,
    EXPECTED_NAMES,
    PDF_NAME,
    SOURCE_NAME,
    build_release,
    parse_checksums,
    verify_release,
)


ROOT = Path(__file__).resolve().parents[1]


class ArchivalReleaseTests(unittest.TestCase):
    def test_release_set_is_deterministic_and_exact(self) -> None:
        (ROOT / "build").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=ROOT / "build",
            prefix="archival-release-test-",
        ) as directory:
            base = Path(directory)
            pdf = base / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.5\narchival release test\n%%EOF\n")
            first = base / "first"
            second = base / "second"
            build_release(pdf, first)
            build_release(pdf, second)

            self.assertEqual(
                {path.name for path in first.iterdir()},
                EXPECTED_NAMES,
            )
            for name in EXPECTED_NAMES:
                self.assertEqual(
                    (first / name).read_bytes(),
                    (second / name).read_bytes(),
                    name,
                )

    def test_checksum_manifest_binds_both_payloads(self) -> None:
        records = verify_release()
        checksums = parse_checksums(
            ROOT / "dist" / "release" / CHECKSUM_NAME
        )
        self.assertEqual(set(checksums), {PDF_NAME, SOURCE_NAME})
        for name, record in records.items():
            path = ROOT / "dist" / "release" / name
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                record["sha256"],
            )

    def test_release_json_matches_release_assets(self) -> None:
        records = verify_release(
            metadata_path=ROOT / "release.json",
        )
        metadata = json.loads(
            (ROOT / "release.json").read_text(encoding="ascii")
        )
        self.assertEqual(metadata["version"], "0.3.1")
        self.assertEqual(
            metadata["technical_report"]["release_version_doi"],
            "10.5281/zenodo.22647766",
        )
        self.assertEqual(len(records), 2)


if __name__ == "__main__":
    unittest.main()
