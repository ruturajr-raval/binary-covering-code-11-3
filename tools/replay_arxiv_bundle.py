"""Validate and replay the arXiv archive against trusted repository bytes."""

from __future__ import annotations

import argparse
import gzip
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from build_arxiv_bundle import _load_entries, _manifest  # noqa: E402


DEFAULT_BUNDLE = (
    PROJECT_ROOT / "dist/arxiv/binary-covering-code-11-3.tar.gz"
)
MAX_ARCHIVE_MEMBERS = 64
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_TAR_OVERHEAD_BYTES = 1024 * 1024
TAR_BLOCK_BYTES = 512
TAR_ZERO_BLOCK = bytes(TAR_BLOCK_BYTES)


def _safe_relative_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != name
        or "\\" in name
        or any(ord(character) < 32 or ord(character) > 126 for character in name)
    ):
        raise ValueError(f"unsafe archive path: {name}")
    return path


def _trusted_entries() -> dict[str, bytes]:
    entries = _load_entries(PROJECT_ROOT)
    entries["MANIFEST.sha256"] = _manifest(entries)
    return entries


def _parse_tar_octal(field: bytes, label: str) -> int:
    if field and field[0] & 0x80:
        raise ValueError(f"noncanonical base-256 tar {label}")
    stripped = field.rstrip(b"\0 ").lstrip(b" ")
    if not stripped:
        return 0
    if any(character not in b"01234567" for character in stripped):
        raise ValueError(f"invalid tar {label}")
    return int(stripped, 8)


def _read_exact(stream: gzip.GzipFile, size: int, label: str) -> bytes:
    payload = bytearray()
    while len(payload) < size:
        chunk = stream.read(size - len(payload))
        if not chunk:
            raise ValueError(f"truncated tar {label}")
        payload.extend(chunk)
    return bytes(payload)


def _discard_exact(stream: gzip.GzipFile, size: int, label: str) -> None:
    remaining = size
    while remaining:
        chunk = stream.read(min(remaining, 64 * 1024))
        if not chunk:
            raise ValueError(f"truncated tar {label}")
        remaining -= len(chunk)


def _preflight_ustar(
    bundle: Path,
    *,
    max_members: int,
    max_member_bytes: int,
    max_total_bytes: int,
) -> None:
    max_stream_bytes = max_total_bytes + MAX_TAR_OVERHEAD_BYTES
    member_count = 0
    total_payload_bytes = 0
    stream_bytes = 0
    zero_blocks = 0
    with gzip.open(bundle, "rb") as stream:
        while True:
            header = _read_exact(stream, TAR_BLOCK_BYTES, "header")
            stream_bytes += len(header)
            if stream_bytes > max_stream_bytes:
                raise ValueError("arXiv archive exceeds stream size limit")
            if header == TAR_ZERO_BLOCK:
                zero_blocks += 1
                if zero_blocks < 2:
                    continue
                while True:
                    trailing = stream.read(64 * 1024)
                    if not trailing:
                        return
                    stream_bytes += len(trailing)
                    if stream_bytes > max_stream_bytes:
                        raise ValueError(
                            "arXiv archive exceeds stream size limit"
                        )
                    if any(trailing):
                        raise ValueError(
                            "nonzero data follows tar end marker"
                        )
            if zero_blocks:
                raise ValueError("invalid tar end marker")
            if (
                header[257:263] != b"ustar\0"
                or header[263:265] != b"00"
            ):
                raise ValueError("arXiv archive is not canonical USTAR")
            expected_checksum = _parse_tar_octal(
                header[148:156],
                "checksum",
            )
            actual_checksum = (
                sum(header[:148])
                + 8 * ord(" ")
                + sum(header[156:])
            )
            if expected_checksum != actual_checksum:
                raise ValueError("invalid tar header checksum")
            member_type = header[156:157]
            if member_type in {
                tarfile.XHDTYPE,
                tarfile.XGLTYPE,
                tarfile.GNUTYPE_LONGNAME,
                tarfile.GNUTYPE_LONGLINK,
            }:
                raise ValueError("unsupported tar extension record")
            if member_type not in {
                tarfile.REGTYPE,
                tarfile.AREGTYPE,
            }:
                raise ValueError("unsafe arXiv archive member type")
            member_count += 1
            if member_count > max_members:
                raise ValueError("arXiv archive has too many members")
            member_size = _parse_tar_octal(header[124:136], "size")
            if member_size > max_member_bytes:
                raise ValueError(
                    "arXiv archive member exceeds size limit"
                )
            total_payload_bytes += member_size
            if total_payload_bytes > max_total_bytes:
                raise ValueError("arXiv archive exceeds total size limit")
            _discard_exact(stream, member_size, "member payload")
            stream_bytes += member_size
            padding_size = (-member_size) % TAR_BLOCK_BYTES
            if padding_size:
                padding = _read_exact(stream, padding_size, "padding")
                if any(padding):
                    raise ValueError("nonzero tar member padding")
                stream_bytes += padding_size
            if stream_bytes > max_stream_bytes:
                raise ValueError("arXiv archive exceeds stream size limit")


def _run_repository_verifiers(extracted: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(PROJECT_ROOT / "tools/verify_technical_report.py"),
            "--root",
            str(extracted / "anc"),
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )
    with tempfile.TemporaryDirectory(
        prefix="binary-covering-code-certificates-"
    ) as directory:
        work = Path(directory)
        distance = work / "distance-distribution-bounds.json"
        overlap = work / "overlap-bound.json"
        subprocess.run(
            [
                sys.executable,
                "-B",
                str(PROJECT_ROOT / "tools/verify_distance_distribution_bounds.py"),
                str(distance),
            ],
            cwd=PROJECT_ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                sys.executable,
                "-B",
                str(PROJECT_ROOT / "tools/verify_overlap_bound.py"),
                str(overlap),
            ],
            cwd=PROJECT_ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        if distance.read_bytes() != (
            extracted / "anc/evidence/distance-distribution-bounds.json"
        ).read_bytes():
            raise ValueError("distance certificate replay differs")
        if overlap.read_bytes() != (
            extracted / "anc/evidence/overlap-bound.json"
        ).read_bytes():
            raise ValueError("overlap certificate replay differs")


def replay_bundle(
    bundle: Path = DEFAULT_BUNDLE,
    *,
    max_members: int = MAX_ARCHIVE_MEMBERS,
    max_member_bytes: int = MAX_MEMBER_BYTES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> None:
    _preflight_ustar(
        bundle,
        max_members=max_members,
        max_member_bytes=max_member_bytes,
        max_total_bytes=max_total_bytes,
    )
    expected = _trusted_entries()
    with tempfile.TemporaryDirectory(
        prefix="binary-covering-code-arxiv-"
    ) as directory:
        root = Path(directory)
        seen: set[str] = set()
        total_bytes = 0
        with tarfile.open(bundle, "r|gz") as archive:
            if getattr(archive, "pax_headers", {}):
                raise ValueError("arXiv archive has global PAX headers")
            for member_count, member in enumerate(archive, start=1):
                if member_count > max_members:
                    raise ValueError("arXiv archive has too many members")
                path = _safe_relative_path(member.name)
                name = path.as_posix()
                if (
                    member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE}
                    or not member.isfile()
                    or member.pax_headers
                    or name in seen
                ):
                    raise ValueError(
                        f"unsafe arXiv archive member: {member.name}"
                    )
                if (
                    member.mode != 0o644
                    or member.mtime != 0
                    or member.uid != 0
                    or member.gid != 0
                    or member.uname
                    or member.gname
                ):
                    raise ValueError(
                        f"noncanonical arXiv archive metadata: {member.name}"
                    )
                if member.size < 0 or member.size > max_member_bytes:
                    raise ValueError(
                        f"arXiv archive member exceeds size limit: {member.name}"
                    )
                total_bytes += member.size
                if total_bytes > max_total_bytes:
                    raise ValueError("arXiv archive exceeds total size limit")
                expected_payload = expected.get(name)
                if expected_payload is None:
                    raise ValueError(f"unexpected arXiv archive member: {name}")
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(
                        f"cannot read arXiv archive member: {member.name}"
                    )
                payload = source.read(member.size + 1)
                if len(payload) != member.size:
                    raise ValueError(
                        f"arXiv archive member size differs: {member.name}"
                    )
                if payload != expected_payload:
                    raise ValueError(
                        f"arXiv archive member differs from trusted source: {name}"
                    )
                destination = root.joinpath(*path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)
                seen.add(name)
        if seen != set(expected):
            missing = sorted(set(expected) - seen)
            raise ValueError(f"arXiv archive is missing trusted members: {missing}")
        _run_repository_verifiers(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "bundle",
        type=Path,
        nargs="?",
        default=DEFAULT_BUNDLE,
        help="archive built from this repository revision",
    )
    args = parser.parse_args()
    replay_bundle(args.bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
