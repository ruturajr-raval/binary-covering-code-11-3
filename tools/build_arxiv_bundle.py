"""Build the deterministic, allowlisted arXiv source archive."""

from __future__ import annotations

import argparse
import binascii
import hashlib
import io
from pathlib import Path
import struct
import tarfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "dist/arxiv/binary-covering-code-11-3.tar.gz"
)

SOURCE_MAP = (
    ("paper/main.tex", "main.tex"),
    ("paper/ARXIV_README.txt", "README.txt"),
    ("paper/RIGHTS.md", "RIGHTS.md"),
    ("paper/replay.py", "replay.py"),
    ("tools/verify_technical_report.py", "verify_technical_report.py"),
    (
        "tools/verify_distance_distribution_bounds.py",
        "verify_distance_distribution_bounds.py",
    ),
    ("tools/verify_overlap_bound.py", "verify_overlap_bound.py"),
    ("LICENSE", "LICENSE"),
    (
        "data/baseline/k2-11-3-linear-16.txt",
        "anc/data/baseline/k2-11-3-linear-16.txt",
    ),
    (
        "evidence/technical-report-summary-v1.json",
        "anc/evidence/technical-report-summary-v1.json",
    ),
    (
        "evidence/case-reduction-summary.json",
        "anc/evidence/case-reduction-summary.json",
    ),
    (
        "evidence/distance-distribution-bounds.json",
        "anc/evidence/distance-distribution-bounds.json",
    ),
    (
        "evidence/overlap-bound.json",
        "anc/evidence/overlap-bound.json",
    ),
    (
        "evidence/fourth-word-up-classification.json",
        "anc/evidence/fourth-word-up-classification.json",
    ),
    (
        "evidence/fourth-word-rup-proof-index-v1.json",
        "anc/evidence/fourth-word-rup-proof-index-v1.json",
    ),
    (
        "evidence/fourth-word-rup-revision-v1.json",
        "anc/evidence/fourth-word-rup-revision-v1.json",
    ),
    (
        "evidence/release-manifest-v0.2.0.sha256",
        "anc/evidence/release-manifest-v0.2.0.sha256",
    ),
    (
        "evidence/proof-bundle.sha256",
        "anc/evidence/proof-bundle.sha256",
    ),
    (
        "evidence/fourth-word-rup-bundle-v1.sha256",
        "anc/evidence/fourth-word-rup-bundle-v1.sha256",
    ),
    (
        "evidence/zenodo-v0.2.0-archive.json",
        "anc/evidence/zenodo-v0.2.0-archive.json",
    ),
    (
        "research/third-word-child-frontier.json",
        "anc/research/third-word-child-frontier.json",
    ),
    (
        "research/fourth-word-hard-frontier.json",
        "anc/research/fourth-word-hard-frontier.json",
    ),
    (
        "proof-expansion/evidence/fourth-word-solver-drat-index-v2.json",
        "anc/proof-expansion/evidence/"
        "fourth-word-solver-drat-index-v2.json",
    ),
    (
        "proof-expansion/evidence/fourth-word-solver-drat-revision-v2.json",
        "anc/proof-expansion/evidence/"
        "fourth-word-solver-drat-revision-v2.json",
    ),
    (
        "proof-expansion/evidence/fourth-word-solver-drat-bundle-v2.sha256",
        "anc/proof-expansion/evidence/"
        "fourth-word-solver-drat-bundle-v2.sha256",
    ),
)

DISALLOWED_PUBLICATION_BYTES = (
    b"/" + b"Users/",
    b"file" + b"://",
    bytes.fromhex("e28094"),
)


def _load_entries(root: Path) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    for source_name, archive_name in SOURCE_MAP:
        source = root / source_name
        if source.is_symlink() or not source.is_file():
            raise ValueError(
                f"arXiv source is missing or not a regular file: {source_name}"
            )
        payload = source.read_bytes()
        for disallowed in DISALLOWED_PUBLICATION_BYTES:
            if disallowed in payload:
                raise ValueError(
                    "arXiv source contains non-public or unsupported text: "
                    f"{source_name}"
                )
        if archive_name in entries:
            raise ValueError(f"duplicate arXiv archive path: {archive_name}")
        entries[archive_name] = payload
    return entries


def _manifest(entries: dict[str, bytes]) -> bytes:
    return (
        "\n".join(
            f"{hashlib.sha256(payload).hexdigest()}  {name}"
            for name, payload in sorted(entries.items())
        )
        + "\n"
    ).encode("ascii")


def _add_bytes(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    archive.addfile(info, io.BytesIO(payload))


def _deterministic_gzip(payload: bytes) -> bytes:
    """Encode gzip with uncompressed DEFLATE blocks and fixed metadata."""

    compressed = bytearray(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff")
    if not payload:
        compressed.extend(b"\x01\x00\x00\xff\xff")
    else:
        offset = 0
        while offset < len(payload):
            chunk = payload[offset : offset + 65535]
            offset += len(chunk)
            compressed.append(1 if offset == len(payload) else 0)
            length = len(chunk)
            compressed.extend(struct.pack("<HH", length, length ^ 0xFFFF))
            compressed.extend(chunk)
    compressed.extend(
        struct.pack(
            "<II",
            binascii.crc32(payload) & 0xFFFFFFFF,
            len(payload) & 0xFFFFFFFF,
        )
    )
    return bytes(compressed)


def build_arxiv_bundle(
    output: Path = DEFAULT_OUTPUT,
    root: Path = PROJECT_ROOT,
) -> Path:
    entries = _load_entries(root)
    entries["MANIFEST.sha256"] = _manifest(entries)
    output.parent.mkdir(parents=True, exist_ok=True)
    tar_payload = io.BytesIO()
    with tarfile.open(
        fileobj=tar_payload,
        mode="w",
        format=tarfile.USTAR_FORMAT,
    ) as archive:
        for name, payload in sorted(entries.items()):
            _add_bytes(archive, name, payload)
    output.write_bytes(_deterministic_gzip(tar_payload.getvalue()))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(build_arxiv_bundle(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
