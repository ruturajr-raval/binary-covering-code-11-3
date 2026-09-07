#!/usr/bin/env python3
"""Build and verify the deterministic paper-inclusive release asset set."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat

try:
    from .build_arxiv_bundle import build_arxiv_bundle
except ImportError:
    from build_arxiv_bundle import build_arxiv_bundle


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.3.1"
RELEASE_DIR = ROOT / "dist" / "release"
PDF_NAME = f"binary-covering-code-11-3-v{VERSION}-paper.pdf"
SOURCE_NAME = (
    f"binary-covering-code-11-3-v{VERSION}-paper-source.tar.gz"
)
CHECKSUM_NAME = "SHA256SUMS"
EXPECTED_NAMES = {PDF_NAME, SOURCE_NAME, CHECKSUM_NAME}


def require_regular(path: Path, description: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{description} is missing: {path}") from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError(
            f"{description} is not a single-link regular file: {path}"
        )


def sha256_file(path: Path) -> str:
    require_regular(path, "release asset")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def release_records(directory: Path) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for name in (PDF_NAME, SOURCE_NAME):
        path = directory / name
        require_regular(path, "release asset")
        records[name] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    return records


def checksum_payload(records: dict[str, dict[str, object]]) -> str:
    return "".join(
        f"{records[name]['sha256']}  {name}\n" for name in sorted(records)
    )


def build_release(
    pdf_input: Path = ROOT / "build" / "paper" / "main.pdf",
    output_dir: Path = RELEASE_DIR,
) -> dict[str, dict[str, object]]:
    require_regular(pdf_input, "compiled paper")
    pdf_payload = pdf_input.read_bytes()
    if not pdf_payload.startswith(b"%PDF-"):
        raise ValueError(f"compiled paper is not a PDF: {pdf_input}")

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_output = output_dir / PDF_NAME
    source_output = output_dir / SOURCE_NAME
    pdf_output.write_bytes(pdf_payload)
    build_arxiv_bundle(source_output, root=ROOT)

    records = release_records(output_dir)
    (output_dir / CHECKSUM_NAME).write_text(
        checksum_payload(records),
        encoding="ascii",
    )
    verify_release(output_dir)
    return records


def parse_checksums(path: Path) -> dict[str, str]:
    require_regular(path, "release checksum manifest")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="ascii").splitlines(),
        start=1,
    ):
        if len(line) < 67 or line[64:66] != "  ":
            raise ValueError(
                f"malformed checksum line {line_number}: {path}"
            )
        digest = line[:64]
        name = line[66:]
        if (
            any(character not in "0123456789abcdef" for character in digest)
            or "/" in name
            or name in entries
        ):
            raise ValueError(
                f"invalid checksum line {line_number}: {path}"
            )
        entries[name] = digest
    return entries


def verify_release(
    directory: Path = RELEASE_DIR,
    metadata_path: Path | None = None,
) -> dict[str, dict[str, object]]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(f"release directory is invalid: {directory}")
    observed_names = {path.name for path in directory.iterdir()}
    if observed_names != EXPECTED_NAMES:
        raise ValueError(
            "release asset membership differs: "
            f"expected={sorted(EXPECTED_NAMES)}, "
            f"observed={sorted(observed_names)}"
        )

    records = release_records(directory)
    checksums = parse_checksums(directory / CHECKSUM_NAME)
    expected_checksums = {
        name: str(record["sha256"]) for name, record in records.items()
    }
    if checksums != expected_checksums:
        raise ValueError("release asset checksums differ")

    if metadata_path is not None:
        metadata = json.loads(metadata_path.read_text(encoding="ascii"))
        assets = metadata["technical_report"]["release_assets"]
        expected = {
            assets["pdf"]["name"]: {
                "bytes": assets["pdf"]["size"],
                "sha256": assets["pdf"]["sha256"],
            },
            assets["source"]["name"]: {
                "bytes": assets["source"]["size"],
                "sha256": assets["source"]["sha256"],
            },
        }
        if records != expected:
            raise ValueError("release.json asset metadata differs")
        checksum = assets["checksums"]
        checksum_path = directory / checksum["name"]
        if (
            checksum_path.stat().st_size != checksum["size"]
            or sha256_file(checksum_path) != checksum["sha256"]
        ):
            raise ValueError("release.json checksum metadata differs")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        type=Path,
        default=ROOT / "build" / "paper" / "main.pdf",
    )
    parser.add_argument("--output-dir", type=Path, default=RELEASE_DIR)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        records = verify_release(args.output_dir, ROOT / "release.json")
    else:
        records = build_release(args.pdf, args.output_dir)
    print(json.dumps(records, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
