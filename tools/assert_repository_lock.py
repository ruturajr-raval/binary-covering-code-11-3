#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from repository_lock import require_inherited_repository_lock


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    require_inherited_repository_lock(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
