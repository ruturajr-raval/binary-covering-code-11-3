#!/usr/bin/env python3
"""Check internal source integrity and replay the compact evidence.

Authenticate the enclosing archive against its published SHA-256 before
executing this file.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent


def _safe_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise RuntimeError(f"invalid manifest path: {value}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_internal_manifest() -> None:
    manifest = ROOT / "MANIFEST.sha256"
    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="ascii").splitlines():
        try:
            digest, name = line.split("  ", maxsplit=1)
        except ValueError as error:
            raise RuntimeError(f"malformed manifest line: {line!r}") from error
        _safe_path(name)
        if (
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or name in entries
        ):
            raise RuntimeError(f"invalid manifest entry: {line!r}")
        entries[name] = digest
    expected = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and path != manifest
    }
    if set(entries) != expected:
        raise RuntimeError("source archive manifest membership differs")
    for name, expected_digest in entries.items():
        target = ROOT.joinpath(*PurePosixPath(name).parts)
        if target.is_symlink() or not target.is_file():
            raise RuntimeError(f"manifest target is invalid: {name}")
        if _sha256(target) != expected_digest:
            raise RuntimeError(f"manifest digest mismatch: {name}")


def main() -> int:
    _check_internal_manifest()
    subprocess.run(
        [
            sys.executable,
            "-B",
            "verify_technical_report.py",
            "--root",
            "anc",
        ],
        cwd=ROOT,
        check=True,
    )
    with tempfile.TemporaryDirectory(
        prefix="binary-covering-code-report-"
    ) as directory:
        work = Path(directory)
        distance = work / "distance-distribution-bounds.json"
        overlap = work / "overlap-bound.json"
        subprocess.run(
            [
                sys.executable,
                "-B",
                "verify_distance_distribution_bounds.py",
                str(distance),
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                sys.executable,
                "-B",
                "verify_overlap_bound.py",
                str(overlap),
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        if distance.read_bytes() != (
            ROOT / "anc/evidence/distance-distribution-bounds.json"
        ).read_bytes():
            raise RuntimeError("distance certificate replay differs")
        if overlap.read_bytes() != (
            ROOT / "anc/evidence/overlap-bound.json"
        ).read_bytes():
            raise RuntimeError("overlap certificate replay differs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
