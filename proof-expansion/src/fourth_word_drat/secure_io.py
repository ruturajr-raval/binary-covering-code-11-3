from __future__ import annotations

from contextlib import contextmanager
import ctypes
from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import sys
import tempfile


class _DuplicateJsonKeyError(ValueError):
    pass


class _InvalidJsonConstantError(ValueError):
    pass


class PublicationCommittedError(RuntimeError):
    def __init__(
        self,
        destination: Path,
        destination_identity: tuple[int, int, int],
        *,
        directory: bool,
    ) -> None:
        super().__init__(
            f"publication committed but rollback failed: {destination}"
        )
        self.destination = destination
        self.destination_identity = destination_identity
        self.directory = directory


@dataclass(frozen=True)
class AuthenticatedFileVersion:
    sha256: str
    size: int
    identity: tuple[int, int, int]
    mode: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True)
class PrivateSnapshot:
    path: Path
    sha256: str
    size: int
    identity: tuple[int, int, int]
    mode: int
    mtime_ns: int
    ctime_ns: int


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _metadata_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IFMT(metadata.st_mode),
    )


def _snapshot_fingerprint(
    metadata: os.stat_result,
) -> tuple[
    tuple[int, int, int],
    int,
    int,
    int,
    int,
]:
    return (
        _metadata_identity(metadata),
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _require_same_regular_file(
    path: Path,
    description: str,
    *metadata: os.stat_result,
) -> None:
    if (
        not metadata
        or any(
            not stat.S_ISREG(record.st_mode)
            or record.st_nlink != 1
            for record in metadata
        )
        or len(
            {
                (
                    record.st_dev,
                    record.st_ino,
                    record.st_size,
                    record.st_mtime_ns,
                    record.st_ctime_ns,
                )
                for record in metadata
            }
        )
        != 1
    ):
        raise RuntimeError(
            f"{description} is not a stable single-link regular file: "
            f"{path}"
        )


def _require_same_directory(
    path: Path,
    description: str,
    *metadata: os.stat_result,
) -> None:
    if (
        not metadata
        or any(not stat.S_ISDIR(record.st_mode) for record in metadata)
        or len({_metadata_identity(record) for record in metadata}) != 1
    ):
        raise RuntimeError(
            f"{description} is not a stable directory: {path}"
        )


def _verify_directory_descriptor(
    path: Path,
    descriptor: int,
    expected_identity: tuple[int, int, int],
    description: str,
) -> None:
    try:
        descriptor_metadata = os.fstat(descriptor)
        path_metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(
            f"{description} identity cannot be verified: {path}"
        ) from error
    _require_same_directory(
        path,
        description,
        descriptor_metadata,
        path_metadata,
    )
    if _metadata_identity(descriptor_metadata) != expected_identity:
        raise RuntimeError(f"{description} identity changed: {path}")


@contextmanager
def _authenticated_directory_descriptor(
    path: Path,
    description: str,
):
    try:
        initial_path_metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(f"{description} is unavailable: {path}") from error
    _require_same_directory(path, description, initial_path_metadata)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RuntimeError(f"{description} cannot be opened: {path}") from error
    try:
        try:
            opened_metadata = os.fstat(descriptor)
            current_path_metadata = path.lstat()
            _require_same_directory(
                path,
                description,
                initial_path_metadata,
                opened_metadata,
                current_path_metadata,
            )
        except OSError as error:
            raise RuntimeError(
                f"{description} identity cannot be verified: {path}"
            ) from error
        yield descriptor, _metadata_identity(opened_metadata)
    finally:
        os.close(descriptor)


def _native_rename_noreplace(
    source_descriptor: int,
    source_name: str,
    destination_descriptor: int,
    destination_name: str,
) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function_name = "renameatx_np"
        no_replace_flag = 0x00000004
    elif sys.platform.startswith("linux"):
        function_name = "renameat2"
        no_replace_flag = 0x00000001
    else:
        raise RuntimeError(
            "atomic no-replace publication is unsupported on this platform"
        )
    try:
        rename = getattr(library, function_name)
    except AttributeError as error:
        raise RuntimeError(
            "atomic no-replace publication is unavailable"
        ) from error
    rename.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    rename.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = rename(
        source_descriptor,
        os.fsencode(source_name),
        destination_descriptor,
        os.fsencode(destination_name),
        no_replace_flag,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    error = OSError(error_number, os.strerror(error_number))
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error_number,
            "publication destination already exists",
            destination_name,
        ) from error
    raise error


def _file_version_at(
    parent_descriptor: int,
    name: str,
    description: str,
) -> AuthenticatedFileVersion:
    try:
        initial_path_metadata = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError as error:
        raise RuntimeError(f"{description} is unavailable: {name}") from error
    _require_same_regular_file(
        Path(name),
        description,
        initial_path_metadata,
    )
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(
            name,
            flags,
            dir_fd=parent_descriptor,
        )
    except OSError as error:
        raise RuntimeError(f"{description} cannot be opened: {name}") from error
    digest = hashlib.sha256()
    size = 0
    try:
        opened_metadata = os.fstat(descriptor)
        current_path_metadata = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        _require_same_regular_file(
            Path(name),
            description,
            initial_path_metadata,
            opened_metadata,
            current_path_metadata,
        )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            while True:
                payload = handle.read(1024 * 1024)
                if not payload:
                    break
                digest.update(payload)
                size += len(payload)
            final_opened_metadata = os.fstat(handle.fileno())
            final_path_metadata = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        _require_same_regular_file(
            Path(name),
            description,
            initial_path_metadata,
            opened_metadata,
            final_opened_metadata,
            final_path_metadata,
        )
    except OSError as error:
        raise RuntimeError(
            f"{description} identity cannot be verified: {name}"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if size != final_path_metadata.st_size:
        raise RuntimeError(f"{description} size changed: {name}")
    return AuthenticatedFileVersion(
        sha256=digest.hexdigest(),
        size=size,
        identity=_metadata_identity(final_path_metadata),
        mode=final_path_metadata.st_mode,
        mtime_ns=final_path_metadata.st_mtime_ns,
        ctime_ns=final_path_metadata.st_ctime_ns,
    )


def authenticated_file_version(
    path: Path,
    description: str,
) -> AuthenticatedFileVersion:
    path = Path(path)
    with _authenticated_directory_descriptor(
        path.parent,
        f"{description} parent",
    ) as (parent_descriptor, parent_identity):
        _verify_directory_descriptor(
            path.parent,
            parent_descriptor,
            parent_identity,
            f"{description} parent",
        )
        version = _file_version_at(
            parent_descriptor,
            path.name,
            description,
        )
        _verify_directory_descriptor(
            path.parent,
            parent_descriptor,
            parent_identity,
            f"{description} parent",
        )
    return version


def _require_file_version_at(
    parent_descriptor: int,
    name: str,
    expected: AuthenticatedFileVersion,
    description: str,
    *,
    after_rename: bool = False,
) -> None:
    observed = _file_version_at(
        parent_descriptor,
        name,
        description,
    )
    matches = (
        observed.sha256 == expected.sha256
        and observed.size == expected.size
        and observed.identity == expected.identity
        and observed.mode == expected.mode
        and observed.mtime_ns == expected.mtime_ns
        and (
            observed.ctime_ns >= expected.ctime_ns
            if after_rename
            else observed.ctime_ns == expected.ctime_ns
        )
    )
    if not matches:
        raise RuntimeError(f"{description} version changed: {name}")


def durable_publish_noreplace(
    source: Path,
    destination: Path,
    *,
    directory: bool,
    expected_source_identity: tuple[int, int, int] | None = None,
    expected_source_version: AuthenticatedFileVersion | None = None,
) -> tuple[int, int, int]:
    source = Path(source)
    destination = Path(destination)
    if (
        source == destination
        or source.name in {"", ".", ".."}
        or destination.name in {"", ".", ".."}
        or (directory and expected_source_version is not None)
    ):
        raise RuntimeError("publication paths are invalid")
    if (
        expected_source_version is not None
        and expected_source_identity is not None
        and expected_source_version.identity != expected_source_identity
    ):
        raise RuntimeError("publication source expectations conflict")
    with _authenticated_directory_descriptor(
        source.parent,
        "publication source parent",
    ) as (source_parent_descriptor, source_parent_identity):
        with _authenticated_directory_descriptor(
            destination.parent,
            "publication destination parent",
        ) as (
            destination_parent_descriptor,
            destination_parent_identity,
        ):
            _verify_directory_descriptor(
                source.parent,
                source_parent_descriptor,
                source_parent_identity,
                "publication source parent",
            )
            _verify_directory_descriptor(
                destination.parent,
                destination_parent_descriptor,
                destination_parent_identity,
                "publication destination parent",
            )
            try:
                source_metadata = os.stat(
                    source.name,
                    dir_fd=source_parent_descriptor,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise RuntimeError(
                    f"publication source is unavailable: {source}"
                ) from error
            expected_type = stat.S_IFDIR if directory else stat.S_IFREG
            source_identity = _metadata_identity(source_metadata)
            if (
                stat.S_IFMT(source_metadata.st_mode) != expected_type
                or (
                    not directory
                    and source_metadata.st_nlink != 1
                )
                or (
                    expected_source_identity is not None
                    and source_identity != expected_source_identity
                )
            ):
                raise RuntimeError(
                    f"publication source identity is invalid: {source}"
                )
            if expected_source_version is not None:
                _require_file_version_at(
                    source_parent_descriptor,
                    source.name,
                    expected_source_version,
                    "publication source",
                )
            try:
                _native_rename_noreplace(
                    source_parent_descriptor,
                    source.name,
                    destination_parent_descriptor,
                    destination.name,
                )
            except FileExistsError as error:
                raise RuntimeError(
                    f"publication destination already exists: {destination}"
                ) from error
            except OSError as error:
                raise RuntimeError(
                    f"publication failed: {source} -> {destination}"
                ) from error
            try:
                try:
                    destination_metadata = os.stat(
                        destination.name,
                        dir_fd=destination_parent_descriptor,
                        follow_symlinks=False,
                    )
                except OSError as error:
                    raise RuntimeError(
                        f"published artifact is unavailable: {destination}"
                    ) from error
                if (
                    _metadata_identity(destination_metadata)
                    != source_identity
                ):
                    raise RuntimeError(
                        f"published artifact identity changed: {destination}"
                    )
                if expected_source_version is not None:
                    _require_file_version_at(
                        destination_parent_descriptor,
                        destination.name,
                        expected_source_version,
                        "published artifact",
                        after_rename=True,
                    )
                try:
                    os.stat(
                        source.name,
                        dir_fd=source_parent_descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    pass
                except OSError as error:
                    raise RuntimeError(
                        "publication source removal cannot be verified: "
                        f"{source}"
                    ) from error
                else:
                    raise RuntimeError(
                        f"publication source still exists: {source}"
                    )
                os.fsync(destination_parent_descriptor)
                if source.parent != destination.parent:
                    os.fsync(source_parent_descriptor)
                _verify_directory_descriptor(
                    source.parent,
                    source_parent_descriptor,
                    source_parent_identity,
                    "publication source parent",
                )
                _verify_directory_descriptor(
                    destination.parent,
                    destination_parent_descriptor,
                    destination_parent_identity,
                    "publication destination parent",
                )
            except BaseException as error:
                try:
                    _native_rename_noreplace(
                        destination_parent_descriptor,
                        destination.name,
                        source_parent_descriptor,
                        source.name,
                    )
                    restored_metadata = os.stat(
                        source.name,
                        dir_fd=source_parent_descriptor,
                        follow_symlinks=False,
                    )
                    if (
                        _metadata_identity(restored_metadata)
                        != source_identity
                    ):
                        raise RuntimeError(
                            "rolled-back publication identity changed"
                        )
                    try:
                        os.stat(
                            destination.name,
                            dir_fd=destination_parent_descriptor,
                            follow_symlinks=False,
                        )
                    except FileNotFoundError:
                        pass
                    else:
                        raise RuntimeError(
                            "rolled-back publication destination remains"
                        )
                    os.fsync(source_parent_descriptor)
                    if source.parent != destination.parent:
                        os.fsync(destination_parent_descriptor)
                except BaseException as rollback_error:
                    raise PublicationCommittedError(
                        destination,
                        source_identity,
                        directory=directory,
                    ) from rollback_error
                raise RuntimeError(
                    "publication post-commit validation failed and was "
                    "rolled back"
                ) from error
    return source_identity


def load_authenticated_bytes(
    path: Path,
    description: str,
) -> tuple[bytes, str]:
    try:
        initial_path_metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(f"{description} is unavailable: {path}") from error
    _require_same_regular_file(
        path,
        description,
        initial_path_metadata,
    )
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RuntimeError(f"{description} cannot be opened: {path}") from error
    try:
        opened_metadata = os.fstat(descriptor)
        current_path_metadata = path.lstat()
        _require_same_regular_file(
            path,
            description,
            initial_path_metadata,
            opened_metadata,
            current_path_metadata,
        )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read()
            final_opened_metadata = os.fstat(handle.fileno())
            final_path_metadata = path.lstat()
        _require_same_regular_file(
            path,
            description,
            initial_path_metadata,
            opened_metadata,
            final_opened_metadata,
            final_path_metadata,
        )
    except OSError as error:
        raise RuntimeError(
            f"{description} identity cannot be verified: {path}"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return payload, hashlib.sha256(payload).hexdigest()


def authenticated_file_sha256(path: Path, description: str) -> str:
    _payload, digest = load_authenticated_bytes(path, description)
    return digest


def load_authenticated_json(
    path: Path,
    description: str,
) -> tuple[dict[str, object], str]:
    payload, digest = load_authenticated_bytes(path, description)

    def unique_object(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        record: dict[str, object] = {}
        for key, value in pairs:
            if key in record:
                raise _DuplicateJsonKeyError(key)
            record[key] = value
        return record

    def reject_constant(value: str) -> object:
        raise _InvalidJsonConstantError(value)

    try:
        record = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateJsonKeyError,
        _InvalidJsonConstantError,
    ) as error:
        raise RuntimeError(f"{description} is invalid") from error
    if not isinstance(record, dict):
        raise RuntimeError(f"{description} is invalid")
    return record, digest


def artifact_path_identity(
    path: Path,
    *,
    directory: bool,
) -> tuple[int, int, int]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(
            f"artifact path identity is unavailable: {path}"
        ) from error
    expected_type = stat.S_IFDIR if directory else stat.S_IFREG
    if stat.S_IFMT(metadata.st_mode) != expected_type:
        raise RuntimeError(f"artifact path type is invalid: {path}")
    return _metadata_identity(metadata)


def descriptor_artifact_identity(
    descriptor: int,
    *,
    directory: bool,
) -> tuple[int, int, int]:
    try:
        metadata = os.fstat(descriptor)
    except OSError as error:
        raise RuntimeError(
            "artifact descriptor identity is unavailable"
        ) from error
    expected_type = stat.S_IFDIR if directory else stat.S_IFREG
    if stat.S_IFMT(metadata.st_mode) != expected_type:
        raise RuntimeError("artifact descriptor type is invalid")
    return _metadata_identity(metadata)


def quarantine_owned_path(
    path: Path,
    identity: tuple[int, int, int] | None,
    *,
    directory: bool,
) -> bool:
    if identity is None:
        try:
            path.lstat()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return False
    quarantine_parent = Path(
        tempfile.mkdtemp(
            dir=path.parent,
            prefix=f"{path.name}.rollback.",
        )
    )
    quarantine_path = quarantine_parent / "artifact"
    try:
        try:
            os.rename(path, quarantine_path)
        except FileNotFoundError:
            quarantine_parent.rmdir()
            _fsync_directory(path.parent)
            return True
        except OSError:
            quarantine_parent.rmdir()
            _fsync_directory(path.parent)
            return False
        _fsync_directory(path.parent)
        _fsync_directory(quarantine_parent)
        metadata = quarantine_path.lstat()
    except OSError:
        return False
    if _metadata_identity(metadata) != identity:
        return False
    if directory:
        shutil.rmtree(quarantine_path)
        _fsync_directory(quarantine_parent)
    else:
        quarantine_path.unlink()
        _fsync_directory(quarantine_parent)
    quarantine_parent.rmdir()
    _fsync_directory(path.parent)
    return True


def _remove_directory_tree_at(
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int, int],
) -> bool:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        metadata = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or _metadata_identity(metadata) != expected_identity
        ):
            return False
        descriptor = os.open(
            name,
            flags,
            dir_fd=parent_descriptor,
        )
    except OSError:
        return False
    try:
        if _metadata_identity(os.fstat(descriptor)) != expected_identity:
            return False
        entries = os.listdir(descriptor)
        vault_name = None
        for _attempt in range(128):
            candidate = f".deletion-vault.{secrets.token_hex(16)}"
            try:
                os.mkdir(
                    candidate,
                    mode=0o700,
                    dir_fd=descriptor,
                )
            except FileExistsError:
                continue
            vault_name = candidate
            break
        if vault_name is None:
            return False
        vault_descriptor = -1
        vault_cleanup_succeeded = False
        try:
            vault_descriptor = os.open(
                vault_name,
                flags,
                dir_fd=descriptor,
            )
            vault_metadata = os.fstat(vault_descriptor)
            if not stat.S_ISDIR(vault_metadata.st_mode):
                return False
            current_vault_metadata = os.stat(
                vault_name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            if (
                _metadata_identity(current_vault_metadata)
                != _metadata_identity(vault_metadata)
            ):
                return False
            os.fchmod(vault_descriptor, 0o300)
            for entry in entries:
                try:
                    entry_metadata = os.stat(
                        entry,
                        dir_fd=descriptor,
                        follow_symlinks=False,
                    )
                except OSError:
                    return False
                deletion_name = secrets.token_hex(16)
                try:
                    _native_rename_noreplace(
                        descriptor,
                        entry,
                        vault_descriptor,
                        deletion_name,
                    )
                except OSError:
                    return False
                try:
                    quarantined_metadata = os.stat(
                        deletion_name,
                        dir_fd=vault_descriptor,
                        follow_symlinks=False,
                    )
                except OSError:
                    return False
                entry_identity = _metadata_identity(entry_metadata)
                if (
                    _metadata_identity(quarantined_metadata)
                    != entry_identity
                ):
                    return False
                if stat.S_ISDIR(entry_metadata.st_mode):
                    if not _remove_directory_tree_at(
                        vault_descriptor,
                        deletion_name,
                        entry_identity,
                    ):
                        return False
                else:
                    try:
                        current_metadata = os.stat(
                            deletion_name,
                            dir_fd=vault_descriptor,
                            follow_symlinks=False,
                        )
                        if (
                            _metadata_identity(current_metadata)
                            != entry_identity
                        ):
                            return False
                        os.unlink(
                            deletion_name,
                            dir_fd=vault_descriptor,
                        )
                    except OSError:
                        return False
            os.fsync(vault_descriptor)
            os.fsync(descriptor)
            vault_cleanup_succeeded = True
        finally:
            if vault_descriptor >= 0:
                try:
                    os.fchmod(vault_descriptor, 0o700)
                finally:
                    os.close(vault_descriptor)
        if not vault_cleanup_succeeded:
            return False
        try:
            os.rmdir(vault_name, dir_fd=descriptor)
        except OSError:
            return False
        if os.listdir(descriptor):
            return False
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.rmdir(name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
    except OSError:
        return False
    return True


def _quarantine_owned_directory_at(
    parent_descriptor: int,
    name: str,
    identity: tuple[int, int, int],
) -> bool:
    quarantine_name = f".{name}.rollback.{secrets.token_hex(8)}"
    try:
        _native_rename_noreplace(
            parent_descriptor,
            name,
            parent_descriptor,
            quarantine_name,
        )
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        metadata = os.stat(
            quarantine_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        return False
    if _metadata_identity(metadata) != identity:
        return False
    return _remove_directory_tree_at(
        parent_descriptor,
        quarantine_name,
        identity,
    )


def _quarantine_unverified_directory_at(
    parent_descriptor: int,
    name: str,
) -> bool:
    for _attempt in range(128):
        quarantine_name = (
            f".{name}.rollback-unverified.{secrets.token_hex(8)}"
        )
        try:
            _native_rename_noreplace(
                parent_descriptor,
                name,
                parent_descriptor,
                quarantine_name,
            )
        except FileExistsError:
            continue
        except FileNotFoundError:
            return True
        except OSError:
            return False
        os.fsync(parent_descriptor)
        return False
    return False


@contextmanager
def owned_temporary_directory(
    parent: Path,
    *,
    prefix: str,
):
    if not parent.is_dir() or parent.is_symlink():
        raise RuntimeError(f"temporary parent is invalid: {parent}")
    if (
        not prefix
        or Path(prefix).name != prefix
        or prefix in {".", ".."}
    ):
        raise RuntimeError("temporary directory prefix is invalid")
    with _authenticated_directory_descriptor(
        parent,
        "temporary parent",
    ) as (parent_descriptor, parent_identity):
        name = None
        identity = None
        temporary = None
        try:
            for _attempt in range(128):
                candidate = f"{prefix}{secrets.token_hex(8)}"
                try:
                    os.mkdir(
                        candidate,
                        mode=0o700,
                        dir_fd=parent_descriptor,
                    )
                except FileExistsError:
                    continue
                name = candidate
                break
            if name is None:
                raise RuntimeError(
                    "temporary directory name allocation failed"
                )
            flags = os.O_RDONLY
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            created_descriptor = -1
            try:
                created_descriptor = os.open(
                    name,
                    flags,
                    dir_fd=parent_descriptor,
                )
                created_metadata = os.fstat(created_descriptor)
                if not stat.S_ISDIR(created_metadata.st_mode):
                    raise RuntimeError(
                        "temporary directory type is invalid"
                    )
                identity = _metadata_identity(created_metadata)
                current_metadata = os.stat(
                    name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                _require_same_directory(
                    Path(name),
                    "temporary directory",
                    created_metadata,
                    current_metadata,
                )
            finally:
                if created_descriptor >= 0:
                    os.close(created_descriptor)
            _verify_directory_descriptor(
                parent,
                parent_descriptor,
                parent_identity,
                "temporary parent",
            )
            temporary = parent / name
            if (
                artifact_path_identity(temporary, directory=True)
                != identity
            ):
                raise RuntimeError(
                    f"temporary directory identity changed: {temporary}"
                )
            yield temporary
        finally:
            if name is None:
                cleanup_succeeded = True
            elif identity is None:
                cleanup_succeeded = _quarantine_unverified_directory_at(
                    parent_descriptor,
                    name,
                )
            else:
                cleanup_succeeded = _quarantine_owned_directory_at(
                    parent_descriptor,
                    name,
                    identity,
                )
            parent_error = None
            try:
                _verify_directory_descriptor(
                    parent,
                    parent_descriptor,
                    parent_identity,
                    "temporary parent",
                )
            except RuntimeError as error:
                parent_error = error
            if not cleanup_succeeded:
                raise RuntimeError(
                    "temporary directory changed during cleanup: "
                    f"{temporary or parent}"
                )
            if parent_error is not None:
                raise RuntimeError(
                    f"temporary parent changed during use: {parent}"
                ) from parent_error


def write_private_file(
    directory: Path,
    filename: str,
    payload: bytes,
    *,
    executable: bool = False,
) -> PrivateSnapshot:
    if (
        not filename
        or Path(filename).name != filename
        or filename in {".", ".."}
    ):
        raise RuntimeError("private snapshot filename is invalid")
    path = directory / filename
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    mode = 0o500 if executable else 0o400
    descriptor = os.open(path, flags, mode)
    final_metadata = None
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            final_metadata = os.fstat(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    _fsync_directory(directory)
    path_metadata = path.lstat()
    if final_metadata is None:
        raise RuntimeError(f"private snapshot was not written: {path}")
    _require_same_regular_file(
        path,
        "private snapshot",
        final_metadata,
        path_metadata,
    )
    snapshot = PrivateSnapshot(
        path=path,
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
        identity=_metadata_identity(path_metadata),
        mode=path_metadata.st_mode,
        mtime_ns=path_metadata.st_mtime_ns,
        ctime_ns=path_metadata.st_ctime_ns,
    )
    verify_private_snapshot(snapshot, "private snapshot")
    return snapshot


def verify_private_snapshot(
    snapshot: PrivateSnapshot,
    description: str,
) -> Path:
    try:
        initial_metadata = snapshot.path.lstat()
    except OSError as error:
        raise RuntimeError(
            f"{description} is unavailable: {snapshot.path}"
        ) from error
    expected_fingerprint = (
        snapshot.identity,
        snapshot.mode,
        snapshot.size,
        snapshot.mtime_ns,
        snapshot.ctime_ns,
    )
    if _snapshot_fingerprint(initial_metadata) != expected_fingerprint:
        raise RuntimeError(
            f"{description} identity changed: {snapshot.path}"
        )
    payload, digest = load_authenticated_bytes(
        snapshot.path,
        description,
    )
    final_metadata = snapshot.path.lstat()
    if (
        digest != snapshot.sha256
        or len(payload) != snapshot.size
        or _snapshot_fingerprint(final_metadata) != expected_fingerprint
    ):
        raise RuntimeError(
            f"{description} content changed: {snapshot.path}"
        )
    return snapshot.path


@contextmanager
def authenticated_snapshot(
    snapshot: PrivateSnapshot,
    description: str,
):
    path = verify_private_snapshot(snapshot, description)
    try:
        yield path
    finally:
        verify_private_snapshot(snapshot, description)


@contextmanager
def authenticated_snapshots(
    *snapshots: tuple[PrivateSnapshot, str],
):
    paths = tuple(
        verify_private_snapshot(snapshot, description)
        for snapshot, description in snapshots
    )
    try:
        yield paths
    finally:
        for snapshot, description in snapshots:
            verify_private_snapshot(snapshot, description)
