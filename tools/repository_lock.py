from __future__ import annotations

from collections.abc import Mapping
import fcntl
import os
from pathlib import Path
import stat


LOCK_PATH = Path(".research-artifacts/repository-integrity.lock")
LOCK_FD_ENV = "REPOSITORY_INTEGRITY_LOCK_FD"


class RepositoryLock:
    def __init__(
        self,
        handle,
        *,
        previous_descriptor: str | None,
    ) -> None:
        self._handle = handle
        self._previous_descriptor = previous_descriptor
        os.environ[LOCK_FD_ENV] = str(handle.fileno())

    def fileno(self) -> int:
        return self._handle.fileno()

    def close(self) -> None:
        if self._handle is None:
            return
        descriptor = self._handle.fileno()
        if os.environ.get(LOCK_FD_ENV) != str(descriptor):
            raise RuntimeError(
                "repository locks must close in last-in, first-out order"
            )
        self._handle.close()
        self._handle = None
        if self._previous_descriptor is None:
            os.environ.pop(LOCK_FD_ENV, None)
        else:
            os.environ[LOCK_FD_ENV] = self._previous_descriptor


def environment_lock_descriptor(
    environment: Mapping[str, str] | None = None,
) -> int | None:
    source = os.environ if environment is None else environment
    value = source.get(LOCK_FD_ENV)
    if value is None:
        return None
    if not value.isdecimal() or str(int(value)) != value:
        raise RuntimeError("repository lock descriptor is invalid")
    descriptor = int(value)
    if descriptor < 3:
        raise RuntimeError("repository lock descriptor is reserved")
    try:
        metadata = os.fstat(descriptor)
    except OSError as exc:
        raise RuntimeError(
            "repository lock descriptor is unavailable"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise RuntimeError(
            "repository lock descriptor is not a single-link regular file"
        )
    return descriptor


def subprocess_lock_kwargs(
    environment: Mapping[str, str] | None = None,
) -> dict[str, tuple[int, ...]]:
    descriptor = environment_lock_descriptor(environment)
    if descriptor is None:
        return {}
    return {"pass_fds": (descriptor,)}


def require_lock_path_matches_descriptor(
    lock_path: Path,
    descriptor: int,
) -> None:
    try:
        path_metadata = lock_path.lstat()
        descriptor_metadata = os.fstat(descriptor)
    except OSError as exc:
        raise RuntimeError("repository lock identity cannot be checked") from exc
    if (
        not stat.S_ISREG(path_metadata.st_mode)
        or path_metadata.st_nlink != 1
        or not stat.S_ISREG(descriptor_metadata.st_mode)
        or descriptor_metadata.st_nlink != 1
        or path_metadata.st_dev != descriptor_metadata.st_dev
        or path_metadata.st_ino != descriptor_metadata.st_ino
    ):
        raise RuntimeError("repository lock path and descriptor differ")


def require_inherited_repository_lock(root: Path) -> int:
    descriptor = environment_lock_descriptor()
    if descriptor is None:
        raise RuntimeError("an inherited repository lock is required")
    require_lock_path_matches_descriptor(root / LOCK_PATH, descriptor)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(
            "the inherited repository descriptor cannot acquire the lock"
        ) from exc
    return descriptor


def acquire_repository_lock(root: Path) -> RepositoryLock:
    lock_path = root / LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.parent.is_symlink():
        raise RuntimeError("repository lock directory is a symbolic link")
    previous_descriptor = os.environ.get(LOCK_FD_ENV)
    inherited_descriptor = environment_lock_descriptor()
    if inherited_descriptor is not None:
        require_lock_path_matches_descriptor(
            lock_path,
            inherited_descriptor,
        )
        duplicate = os.dup(inherited_descriptor)
        try:
            handle = os.fdopen(duplicate, "a+b", buffering=0)
        except BaseException:
            os.close(duplicate)
            raise
        try:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            handle.close()
            raise RuntimeError(
                "inherited repository lock is not held"
            ) from exc
        return RepositoryLock(
            handle,
            previous_descriptor=previous_descriptor,
        )

    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        require_lock_path_matches_descriptor(lock_path, descriptor)
        handle = os.fdopen(descriptor, "a+b", buffering=0)
    except BaseException:
        os.close(descriptor)
        raise
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return RepositoryLock(handle, previous_descriptor=None)
