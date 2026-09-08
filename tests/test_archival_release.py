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

    def test_published_release_state_is_exact_and_claim_safe(self) -> None:
        metadata = json.loads(
            (ROOT / "release.json").read_text(encoding="ascii")
        )
        readme = (ROOT / "README.md").read_text(encoding="ascii")
        publication = (ROOT / "PUBLICATION.md").read_text(encoding="ascii")
        report = metadata["technical_report"]
        workflows = report["release_workflows"]
        record = report["zenodo_record"]
        verification = metadata["artifact_verification"]

        self.assertEqual(metadata["release_status"], "published")
        self.assertEqual(
            metadata["artifact_release_status"],
            "paper_inclusive_archival_patch_published_and_verified",
        )
        self.assertEqual(
            metadata["technical_report_release_status"],
            "published",
        )
        self.assertEqual(
            report["release_commit"],
            "3543518d89d35f57753caa25a8ce73b004c4561b",
        )
        self.assertEqual(
            report["release_tag_object"],
            "b59bc8f2b10113eee23d35397a47900804632b2e",
        )
        self.assertEqual(report["github_release_id"], 384349074)
        self.assertIn(
            "audited release commit is\n"
            "`3543518d89d35f57753caa25a8ce73b004c4561b`",
            readme,
        )
        self.assertIn(
            "| Audited release commit | "
            "`3543518d89d35f57753caa25a8ce73b004c4561b` |",
            publication,
        )
        self.assertEqual(
            {
                key: value["run_id"]
                for key, value in workflows.items()
            },
            {
                "public_main_ci": 34159901270,
                "public_main_full_proof_replay": 34159901314,
                "public_tag_ci": 34163740426,
                "public_tag_full_proof_replay": 34163740483,
            },
        )
        self.assertTrue(
            all(value["status"] == "success" for value in workflows.values())
        )
        expected_workflow_bindings = {
            "public_main_ci": (
                "CI",
                ".github/workflows/ci.yml",
                "main",
            ),
            "public_main_full_proof_replay": (
                "Full Proof Replay",
                ".github/workflows/proof-replay.yml",
                "main",
            ),
            "public_tag_ci": (
                "CI",
                ".github/workflows/ci.yml",
                "v0.3.1",
            ),
            "public_tag_full_proof_replay": (
                "Full Proof Replay",
                ".github/workflows/proof-replay.yml",
                "v0.3.1",
            ),
        }
        for key, (name, path, ref) in expected_workflow_bindings.items():
            workflow = workflows[key]
            self.assertEqual(workflow["name"], name)
            self.assertEqual(workflow["workflow_path"], path)
            self.assertEqual(workflow["event"], "push")
            self.assertEqual(workflow["ref"], ref)
            self.assertEqual(
                workflow["head_sha"],
                "3543518d89d35f57753caa25a8ce73b004c4561b",
            )
        self.assertEqual(record["record_id"], 22647766)
        self.assertEqual(record["status"], "published")
        self.assertEqual(record["publication_date"], "2026-09-07")
        self.assertTrue(record["public_files_verified"])
        self.assertTrue(
            all(
                verification[key]
                for key in (
                    "public_main_ci_passes",
                    "public_main_full_proof_replay_passes",
                    "public_tag_ci_passes",
                    "public_tag_full_proof_replay_passes",
                    "github_release_created",
                    "github_release_assets_downloaded_and_verified",
                    "zenodo_record_published",
                    "zenodo_assets_downloaded_and_verified",
                )
            )
        )

    def test_release_asset_md5_values_match(self) -> None:
        metadata = json.loads(
            (ROOT / "release.json").read_text(encoding="ascii")
        )
        assets = metadata["technical_report"]["release_assets"]
        for record in assets.values():
            path = ROOT / "dist" / "release" / record["name"]
            self.assertEqual(
                hashlib.md5(path.read_bytes()).hexdigest(),
                record["md5"],
                record["name"],
            )

    def test_release_gate_preserves_theorem_hold(self) -> None:
        gate = json.loads(
            (ROOT / "research" / "release-gate.json").read_text(
                encoding="ascii"
            )
        )
        self.assertEqual(gate["schema_version"], 1)
        self.assertEqual(
            {
                gate["artifact_decision"],
                gate["technical_report_decision"],
                gate["archival_patch_decision"],
            },
            {"published"},
        )
        self.assertEqual(gate["artifact_decision"], "published")
        self.assertEqual(gate["technical_report_decision"], "published")
        self.assertEqual(gate["archival_patch_decision"], "published")
        self.assertEqual(gate["decision"], "hold")
        for key in (
            "archival_patch_hosted_ci_passes",
            "public_release_created",
            "zenodo_version_doi_assigned",
            "zenodo_record_updated_with_paper",
            "public_release_assets_downloaded_and_verified",
            "public_zenodo_assets_downloaded_and_verified",
        ):
            self.assertTrue(gate["gates"][key], key)
        self.assertFalse(gate["gates"]["complete_exact_value_result"])
        self.assertFalse(
            gate["gates"]["all_selected_fourth_word_branches_closed"]
        )
        self.assertFalse(
            gate["gates"]["closed_third_word_child_from_fourth_word_bundle"]
        )
        self.assertFalse(
            gate["gates"]["closed_normalized_parent_from_fourth_word_bundle"]
        )
        self.assertFalse(gate["gates"]["external_review_addressed"])


if __name__ == "__main__":
    unittest.main()
