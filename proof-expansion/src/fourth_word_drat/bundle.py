from __future__ import annotations

from collections.abc import Callable
from collections import Counter
from concurrent.futures import as_completed, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Iterable

from repository_lock import subprocess_lock_kwargs

from fourth_word_drat.proof_core import (
    BUFFER_SIZE,
    DEFAULT_MAX_CHECKER_OUTPUT_BYTES,
    DEFAULT_MAX_CHECKER_SECONDS,
    DEFAULT_MAX_MEMORY_BYTES,
    DEFAULT_MAX_RAW_PROOF_BYTES,
    DEFAULT_MAX_RETAINED_PROOF_BYTES,
    DEFAULT_MAX_SOLVE_SECONDS,
    atomic_write_json,
    display_path,
    file_sha256,
    fsync_directory,
    paths_overlap,
    repository_path,
    require_regular_single_link,
    require_sha256,
)
from fourth_word_drat.secure_io import (
    artifact_path_identity,
    authenticated_file_sha256,
    authenticated_file_version,
    descriptor_artifact_identity,
    durable_publish_noreplace,
    load_authenticated_bytes,
    load_authenticated_json,
    owned_temporary_directory,
    PublicationCommittedError,
    quarantine_owned_path,
)


CASE_RECORD_SUFFIX = "-case.json"
PROOF_SUMMARY_SUFFIX = "-proof.json"
PROOF_SUFFIX = ".drat.gz"
STAGING_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{16}$")
FORMULA_COMMAND_TIMEOUT_SECONDS = 600
PROOF_COMMAND_TIMEOUT_SECONDS = (
    DEFAULT_MAX_SOLVE_SECONDS + 2 * DEFAULT_MAX_CHECKER_SECONDS + 300
)
PREFLIGHT_COMMAND_TIMEOUT_SECONDS = 600
DEFAULT_MIN_FREE_BYTES = 8 * 1024 * 1024 * 1024
MAX_CAPTURED_OUTPUT_BYTES = 1024 * 1024
ISOLATED_REPOSITORY_RUNNER = "\n".join(
    (
        "import atexit,os,runpy,shutil,sys,tempfile",
        "from pathlib import Path",
        "root=Path.cwd().resolve()",
        "work=root/'proof-expansion/work'",
        "if work.is_symlink():",
        " raise RuntimeError('work path is a symbolic link')",
        "work.mkdir(parents=True,exist_ok=True)",
        "cache_parent=work/'python-bytecode'",
        "if cache_parent.is_symlink():",
        " raise RuntimeError('cache path is a symbolic link')",
        "cache_parent.mkdir(exist_ok=True)",
        "cache=Path(tempfile.mkdtemp(dir=cache_parent,prefix='.run.'))",
        "os.environ['PYTHONPYCACHEPREFIX']=str(cache)",
        "os.environ['PYTHONDONTWRITEBYTECODE']='1'",
        "sys.pycache_prefix=str(cache)",
        "sys.dont_write_bytecode=True",
        "sys.path[:0]=[str(root/'proof-expansion/src'),"
        "str(root/'src'),str(root/'tools')]",
        "relative=Path(sys.argv[1])",
        "if relative.is_absolute() or '..' in relative.parts:",
        " raise RuntimeError('script path is outside the repository')",
        "current=root",
        "for part in relative.parts:",
        " current=current/part",
        " if current.is_symlink():",
        "  raise RuntimeError('script path contains a symbolic link')",
        "if not current.is_file():",
        " raise RuntimeError('repository script is missing')",
        "sys.argv=sys.argv[1:]",
        "atexit.register(shutil.rmtree,cache,ignore_errors=True)",
        "runpy.run_path(str(current),run_name='__main__')",
    )
)


@dataclass(frozen=True)
class StagedBundle:
    proof_directory: Path
    index_path: Path
    token: str
    index_record: dict[str, object]
    proof_directory_sha256: str
    index_sha256: str
    proof_directory_identity: tuple[int, int, int]
    index_identity: tuple[int, int, int]


def load_json(path: Path) -> dict[str, object]:
    record, _digest = load_authenticated_json(path, "JSON document")
    return record


def isolated_python_script_command(
    python_command: str,
    script: str,
    *arguments: str,
) -> list[str]:
    return [
        python_command,
        "-I",
        "-c",
        ISOLATED_REPOSITORY_RUNNER,
        script,
        *arguments,
    ]


def require_path_separation(paths: dict[str, Path]) -> None:
    items = list(paths.items())
    for index, (left_name, left) in enumerate(items):
        for right_name, right in items[index + 1 :]:
            if paths_overlap(left, right):
                raise RuntimeError(
                    f"repository paths overlap: "
                    f"{left_name}, {right_name}"
                )


def branch_slug(branch_id: str) -> str:
    slug = branch_id.replace("::", "--")
    if not slug or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
        for character in slug
    ):
        raise ValueError(f"branch id is not path-safe: {branch_id}")
    return slug


def directory_sha256(directory: Path) -> str:
    if not directory.is_dir() or directory.is_symlink():
        raise RuntimeError(f"artifact directory is invalid: {directory}")
    payload = bytearray()
    for entry in sorted(directory.iterdir(), key=lambda path: path.name):
        require_regular_single_link(entry, "bundle artifact")
        payload.extend(entry.name.encode("ascii"))
        payload.extend(b":")
        payload.extend(
            authenticated_file_sha256(
                entry,
                "bundle artifact",
            ).encode("ascii")
        )
        payload.extend(b"\n")
    return hashlib.sha256(bytes(payload)).hexdigest()


def atomic_write_bytes(
    path: Path,
    payload: bytes,
) -> tuple[int, int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    temporary_identity = descriptor_artifact_identity(
        descriptor,
        directory=False,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_version = authenticated_file_version(
            temporary,
            "atomic-write temporary",
        )
        try:
            return durable_publish_noreplace(
                temporary,
                path,
                directory=False,
                expected_source_identity=temporary_identity,
                expected_source_version=temporary_version,
            )
        except PublicationCommittedError as error:
            if not quarantine_owned_path(
                path,
                error.destination_identity,
                directory=False,
            ):
                raise RuntimeError(
                    f"committed atomic write could not be removed: {path}"
                ) from error
            raise
    finally:
        if not quarantine_owned_path(
            temporary,
            temporary_identity,
            directory=False,
        ):
            raise RuntimeError(
                f"atomic-write temporary changed during cleanup: "
                f"{temporary}"
            )


def fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def durable_unlink(path: Path) -> None:
    path.unlink(missing_ok=True)
    fsync_directory(path.parent)


def require_free_space(path: Path, minimum_bytes: int) -> None:
    if type(minimum_bytes) is not int or minimum_bytes <= 0:
        raise RuntimeError("minimum free-space requirement is invalid")
    if shutil.disk_usage(path).free < minimum_bytes:
        raise RuntimeError(
            f"free space is below {minimum_bytes} bytes at {path}"
        )


def workspace_free_space_requirement(
    *,
    minimum_bytes: int,
    workers: int,
    raw_proof_bytes: int,
    retained_proof_bytes: int,
) -> int:
    if (
        type(workers) is not int
        or workers < 1
        or workers > 2
        or type(raw_proof_bytes) is not int
        or raw_proof_bytes <= 0
        or type(retained_proof_bytes) is not int
        or retained_proof_bytes <= 0
    ):
        raise RuntimeError("workspace reserve parameters are invalid")
    return minimum_bytes + workers * (
        raw_proof_bytes + 2 * retained_proof_bytes
    )


def certification_resource_limits(
    workers: int,
) -> dict[str, int]:
    if type(workers) is not int or workers < 1 or workers > 2:
        raise RuntimeError("worker count is invalid")
    return {
        "workers": workers,
        "minimum_free_bytes": DEFAULT_MIN_FREE_BYTES,
        "solve_seconds_per_case": DEFAULT_MAX_SOLVE_SECONDS,
        "raw_proof_bytes_per_case": DEFAULT_MAX_RAW_PROOF_BYTES,
        "retained_proof_bytes_per_case": (
            DEFAULT_MAX_RETAINED_PROOF_BYTES
        ),
        "memory_watchdog_bytes_per_case": DEFAULT_MAX_MEMORY_BYTES,
        "checker_seconds_per_run": DEFAULT_MAX_CHECKER_SECONDS,
        "checker_output_bytes_per_run": (
            DEFAULT_MAX_CHECKER_OUTPUT_BYTES
        ),
        "proof_command_seconds": PROOF_COMMAND_TIMEOUT_SECONDS,
    }


def require_certification_resource_limits(
    resource_limits: dict[str, object],
) -> None:
    if not isinstance(resource_limits, dict):
        raise RuntimeError("certification resource limits are invalid")
    workers = resource_limits.get("workers")
    if (
        type(workers) is not int
        or resource_limits != certification_resource_limits(workers)
    ):
        raise RuntimeError("certification resource limits are invalid")


def promotion_index_free_space_requirement(
    *,
    minimum_bytes: int,
    index_bytes: int,
) -> int:
    if (
        type(minimum_bytes) is not int
        or minimum_bytes <= 0
        or type(index_bytes) is not int
        or index_bytes <= 0
    ):
        raise RuntimeError("promotion reserve parameters are invalid")
    return minimum_bytes + index_bytes


def python_tree_record(root: Path) -> dict[str, object]:
    sources = []
    for relative_directory in (Path("src"), Path("tools")):
        directory = repository_path(relative_directory, root)
        if not directory.is_dir() or directory.is_symlink():
            raise RuntimeError(
                f"Python source directory is invalid: {directory}"
            )
        for path in directory.rglob("*.py"):
            source = repository_path(path, root)
            require_regular_single_link(source, "Python source")
            sources.append(source)
    sources.sort()
    payload = "".join(
        f"{path.relative_to(root)}:"
        f"{authenticated_file_sha256(path, 'Python source')}\n"
        for path in sources
    )
    return {
        "roots": ["src", "tools"],
        "file_count": len(sources),
        "sha256": hashlib.sha256(
            payload.encode("ascii")
        ).hexdigest(),
    }


def validate_solver_environment_record(
    record: object,
) -> dict[str, object]:
    expected_keys = {
        "python_implementation",
        "python_version",
        "python_executable_sha256",
        "python_executable_path",
        "python_sat_version",
        "python_sat_distribution_version",
        "python_sat_tree",
        "python_sat_native_modules",
        "platform_system",
        "platform_machine",
    }
    string_keys = {
        "python_implementation",
        "python_version",
        "python_sat_version",
        "python_sat_distribution_version",
        "platform_system",
        "platform_machine",
    }
    if (
        not isinstance(record, dict)
        or set(record) != expected_keys
        or any(
            not isinstance(record[key], str) or not record[key]
            for key in string_keys
        )
        or record["python_implementation"] != "CPython"
        or record["python_sat_distribution_version"]
        != record["python_sat_version"]
    ):
        raise RuntimeError("Python interpreter probe schema is invalid")
    require_sha256(
        record["python_executable_sha256"],
        "Python executable digest",
    )
    executable_path = record["python_executable_path"]
    if (
        not isinstance(executable_path, dict)
        or executable_path
        != {
            "scope": "repository-relative",
            "value": ".venv/bin/python",
        }
    ):
        raise RuntimeError("Python executable path record is invalid")
    tree = record["python_sat_tree"]
    if (
        not isinstance(tree, dict)
        or set(tree) != {"root", "file_count", "sha256"}
        or tree["root"] != "pysat"
        or type(tree["file_count"]) is not int
        or tree["file_count"] <= 0
    ):
        raise RuntimeError("python-sat tree record is invalid")
    require_sha256(tree["sha256"], "python-sat tree digest")
    native = record["python_sat_native_modules"]
    if (
        not isinstance(native, dict)
        or set(native) != {"pycard", "pyformula", "pysolvers"}
    ):
        raise RuntimeError("python-sat native modules are invalid")
    for name, module in native.items():
        if (
            not isinstance(module, dict)
            or set(module) != {"filename", "sha256"}
            or not isinstance(module["filename"], str)
            or not module["filename"]
        ):
            raise RuntimeError(
                f"python-sat native module is invalid: {name}"
            )
        require_sha256(
            module["sha256"],
            f"python-sat native module digest: {name}",
        )
    return record


def solver_environment_sha256(record: object) -> str:
    validated = validate_solver_environment_record(record)
    payload = json.dumps(
        validated,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def solver_environment_record(
    python_command: str,
    *,
    environment: dict[str, str],
    root: Path,
) -> dict[str, object]:
    candidate = Path(python_command)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = Path(os.path.abspath(str(candidate)))
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            "Python interpreter is outside the repository"
        ) from exc
    if not candidate.is_file() or not os.path.samefile(
        candidate,
        sys.executable,
    ):
        raise RuntimeError(
            "--python must identify the running repository interpreter"
        )
    probe = (
        "import atexit,hashlib,importlib.metadata,json,os,platform,"
        "shutil,stat,sys,tempfile\n"
        "from pathlib import Path\n"
        "repository=Path.cwd().resolve()\n"
        "work=repository/'proof-expansion/work'\n"
        "if work.is_symlink():\n"
        " raise RuntimeError('work path is a symbolic link')\n"
        "work.mkdir(parents=True,exist_ok=True)\n"
        "cache_parent=work/'python-bytecode'\n"
        "if cache_parent.is_symlink():\n"
        " raise RuntimeError('cache path is a symbolic link')\n"
        "cache_parent.mkdir(exist_ok=True)\n"
        "cache=Path(tempfile.mkdtemp(dir=cache_parent,prefix='.probe.'))\n"
        "os.environ['PYTHONPYCACHEPREFIX']=str(cache)\n"
        "os.environ['PYTHONDONTWRITEBYTECODE']='1'\n"
        "sys.pycache_prefix=str(cache)\n"
        "sys.dont_write_bytecode=True\n"
        "atexit.register(shutil.rmtree,cache,ignore_errors=True)\n"
        "import pycard,pyformula,pysat,pysolvers\n"
        "root=Path(pysat.__file__).parent\n"
        "entries=[]\n"
        "for path in sorted(root.rglob('*')):\n"
        " rel=path.relative_to(root)\n"
        " if '__pycache__' in rel.parts or path.suffix in "
        "{'.pyc','.pyo'}:\n"
        "  continue\n"
        " meta=path.lstat()\n"
        " if stat.S_ISLNK(meta.st_mode):\n"
        "  raise RuntimeError('python-sat contains a symlink')\n"
        " if stat.S_ISDIR(meta.st_mode):\n"
        "  continue\n"
        " if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:\n"
        "  raise RuntimeError('python-sat file is invalid')\n"
        " entries.append((rel.as_posix(),hashlib.sha256("
        "path.read_bytes()).hexdigest()))\n"
        "payload=''.join(f'{name}:{digest}\\n' for name,digest "
        "in entries).encode('ascii')\n"
        "native={}\n"
        "for module in (pycard,pyformula,pysolvers):\n"
        " path=Path(module.__file__)\n"
        " meta=path.lstat()\n"
        " if path.parent != root.parent or stat.S_ISLNK(meta.st_mode) "
        "or not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:\n"
        "  raise RuntimeError('python-sat native module is invalid')\n"
        " native[module.__name__]={'filename':path.name,'sha256':"
        "hashlib.sha256(path.read_bytes()).hexdigest()}\n"
        "record={"
        "'python_implementation':platform.python_implementation(),"
        "'python_version':platform.python_version(),"
        "'python_executable_sha256':hashlib.sha256("
        "Path(sys.executable).read_bytes()).hexdigest(),"
        "'python_sat_version':pysat.__version__,"
        "'python_sat_distribution_version':"
        "importlib.metadata.version('python-sat'),"
        "'python_sat_tree':{'root':'pysat','file_count':len(entries),"
        "'sha256':hashlib.sha256(payload).hexdigest()},"
        "'python_sat_native_modules':native,"
        "'platform_system':platform.system(),"
        "'platform_machine':platform.machine()"
        "}\n"
        "print(json.dumps(record,sort_keys=True))\n"
    )
    commands = CommandRegistry()
    with coordinator_signal_handlers(commands):
        try:
            output = commands.run(
                [str(candidate), "-I", "-c", probe],
                environment=environment,
                root=root,
                timeout_seconds=PREFLIGHT_COMMAND_TIMEOUT_SECONDS,
            )
        except BaseException:
            commands.terminate_all()
            raise
    try:
        record = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Python interpreter probe returned invalid JSON"
        ) from exc
    record["python_executable_path"] = {
        "scope": "repository-relative",
        "value": relative.as_posix(),
    }
    return validate_solver_environment_record(record)


def run_prerequisite_audits(
    *,
    root: Path,
    plan_path: Path,
    expected_plan_sha256: str,
    python_command: str,
    environment: dict[str, str],
) -> None:
    require_sha256(expected_plan_sha256, "expected proof-plan digest")
    commands = CommandRegistry()
    plan_arguments = isolated_python_script_command(
        python_command,
        "proof-expansion/cli/audit_plan.py",
        "evidence/residual-two-word-cases.json",
        "evidence/third-word-cases.json",
        "research/third-word-child-frontier.json",
        "research/fourth-word-hard-frontier.json",
        "evidence/fourth-word-up-classification.json",
        "evidence/fourth-word-rup-proof-index-v1.json",
        "evidence/fourth-word-rup-replay-attestation-v1.json",
        "evidence/fourth-word-rup-bundle-v1.sha256",
        "evidence/fourth-word-rup-revision-v1.json",
        "research/runs/2026-09-02-fourth-word-portfolio.json",
        "research/runs/2026-09-02-fourth-word-portfolio-run.json",
        "docs/LITERATURE_AUDIT.md",
        display_path(plan_path, root),
        "--expected-plan-sha256",
        expected_plan_sha256,
    )
    rup_arguments = isolated_python_script_command(
        python_command,
        "tools/audit_fourth_word_rup_proofs.py",
        "evidence/residual-two-word-cases.json",
        "evidence/third-word-cases.json",
        "research/third-word-child-frontier.json",
        "research/fourth-word-hard-frontier.json",
        "evidence/fourth-word-up-classification.json",
        "evidence/fourth-word-rup-proof-plan.json",
        "evidence/fourth-word-rup-proof-index-v1.json",
        "evidence/proofs/fourth-word-rup-v1",
    )
    manifest_arguments = isolated_python_script_command(
        python_command,
        "tools/verify_checksum_manifest.py",
        "evidence/fourth-word-rup-bundle-v1.sha256",
        "--path",
        "evidence/fourth-word-up-classification.json",
        "--path",
        "evidence/fourth-word-rup-proof-plan.json",
        "--path",
        "evidence/fourth-word-rup-proof-index-v1.json",
        "--path",
        "evidence/fourth-word-rup-replay-attestation-v1.json",
        "--tree",
        "evidence/proofs/fourth-word-rup-v1",
    )
    with coordinator_signal_handlers(commands):
        try:
            for arguments in (
                plan_arguments,
                rup_arguments,
                manifest_arguments,
            ):
                commands.run(
                    arguments,
                    environment=environment,
                    root=root,
                    timeout_seconds=PREFLIGHT_COMMAND_TIMEOUT_SECONDS,
                )
        except BaseException:
            commands.terminate_all()
            raise


class CommandRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen[bytes]] = set()
        self._cancelled = False

    @staticmethod
    def _process_group_exists(
        process: subprocess.Popen[bytes],
    ) -> bool:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _signal_processes(
        processes: list[subprocess.Popen[bytes]],
        signal_number: int,
    ) -> None:
        for process in processes:
            try:
                os.killpg(process.pid, signal_number)
            except ProcessLookupError:
                continue

    @staticmethod
    def _wait_for_exit(
        processes: list[subprocess.Popen[bytes]],
        timeout_seconds: float,
    ) -> list[subprocess.Popen[bytes]]:
        deadline = time.monotonic() + timeout_seconds
        remaining = [
            process
            for process in processes
            if CommandRegistry._process_group_exists(process)
        ]
        while remaining and time.monotonic() < deadline:
            time.sleep(0.05)
            remaining = [
                process
                for process in remaining
                if CommandRegistry._process_group_exists(process)
            ]
        return remaining

    @classmethod
    def _terminate_processes(
        cls,
        processes: list[subprocess.Popen[bytes]],
    ) -> None:
        cls._signal_processes(processes, signal.SIGTERM)
        remaining = cls._wait_for_exit(processes, 5)
        cls._signal_processes(remaining, signal.SIGKILL)
        remaining = cls._wait_for_exit(remaining, 5)
        if remaining:
            raise RuntimeError("command process group did not terminate")

    def run(
        self,
        arguments: list[str],
        *,
        environment: dict[str, str],
        root: Path,
        timeout_seconds: int,
    ) -> str:
        if type(timeout_seconds) is not int or timeout_seconds <= 0:
            raise RuntimeError("command timeout is invalid")
        previous_mask = None
        if (
            threading.current_thread() is threading.main_thread()
            and hasattr(signal, "pthread_sigmask")
        ):
            previous_mask = signal.pthread_sigmask(
                signal.SIG_BLOCK,
                {signal.SIGINT, signal.SIGTERM},
            )
        process = None
        try:
            try:
                with self._lock:
                    if self._cancelled:
                        raise RuntimeError(
                            "command execution is cancelled"
                        )
                    process = subprocess.Popen(
                        arguments,
                        cwd=root,
                        env=environment,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=True,
                        **subprocess_lock_kwargs(environment),
                    )
                    self._processes.add(process)
            finally:
                if previous_mask is not None:
                    signal.pthread_sigmask(
                        signal.SIG_SETMASK,
                        previous_mask,
                    )
            if process.stdout is None or process.stderr is None:
                raise RuntimeError("command output pipes are unavailable")
            selector = selectors.DefaultSelector()
            selector.register(
                process.stdout,
                selectors.EVENT_READ,
                "stdout",
            )
            selector.register(
                process.stderr,
                selectors.EVENT_READ,
                "stderr",
            )
            outputs = {
                "stdout": bytearray(),
                "stderr": bytearray(),
            }
            deadline = time.monotonic() + timeout_seconds
            try:
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError(
                            "command timed out:\n"
                            + " ".join(arguments)
                        )
                    for key, _events in selector.select(
                        timeout=min(0.1, remaining)
                    ):
                        payload = os.read(key.fd, BUFFER_SIZE)
                        if not payload:
                            selector.unregister(key.fileobj)
                            continue
                        total = sum(
                            len(value) for value in outputs.values()
                        )
                        if (
                            total + len(payload)
                            > MAX_CAPTURED_OUTPUT_BYTES
                        ):
                            raise RuntimeError(
                                "command output exceeds size limit:\n"
                                + " ".join(arguments)
                            )
                        outputs[str(key.data)].extend(payload)
                process.wait(timeout=5)
            finally:
                selector.close()
                process.stdout.close()
                process.stderr.close()
            if self._process_group_exists(process):
                self._terminate_processes([process])
                raise RuntimeError(
                    "command left descendant processes running:\n"
                    + " ".join(arguments)
                )
            stdout = outputs["stdout"].decode(
                "utf-8",
                errors="replace",
            )
            stderr = outputs["stderr"].decode(
                "utf-8",
                errors="replace",
            )
            if process.returncode != 0:
                raise RuntimeError(
                    "command failed:\n"
                    + " ".join(arguments)
                    + "\n"
                    + (stdout + stderr)[-12000:]
                )
            return stdout
        except BaseException as exc:
            if process is not None:
                try:
                    self._terminate_processes([process])
                except RuntimeError as cleanup_error:
                    raise cleanup_error from exc
            raise
        finally:
            if process is not None:
                with self._lock:
                    self._processes.discard(process)

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True

    def terminate_all(self) -> None:
        with self._lock:
            self._cancelled = True
            processes = list(self._processes)
        self._terminate_processes(processes)


@contextmanager
def coordinator_signal_handlers(commands: CommandRegistry):
    previous = {}
    interrupted = False

    def handle_signal(signal_number, _frame) -> None:
        nonlocal interrupted
        if interrupted:
            return
        interrupted = True
        raise KeyboardInterrupt(
            f"received signal {signal_number}"
        )

    for signal_number in (signal.SIGINT, signal.SIGTERM):
        previous[signal_number] = signal.getsignal(signal_number)
        signal.signal(signal_number, handle_signal)
    try:
        yield
    finally:
        for signal_number, handler in previous.items():
            signal.signal(signal_number, handler)


def case_filenames(branch_id: str) -> dict[str, str]:
    slug = branch_slug(branch_id)
    return {
        "case": f"{slug}{CASE_RECORD_SUFFIX}",
        "proof": f"{slug}{PROOF_SUFFIX}",
        "summary": f"{slug}{PROOF_SUMMARY_SUFFIX}",
    }


def expected_case_members(branch_id: str) -> set[str]:
    return set(case_filenames(branch_id).values())


def validate_case_directory(
    directory: Path,
    planned: dict[str, object],
) -> dict[str, object]:
    if not directory.is_dir() or directory.is_symlink():
        raise RuntimeError(f"case directory is invalid: {directory}")
    expected = expected_case_members(str(planned["branch_id"]))
    observed = {entry.name for entry in directory.iterdir()}
    if observed != expected:
        raise RuntimeError(
            f"{planned['branch_id']}: case artifact membership changed"
        )
    for entry in directory.iterdir():
        require_regular_single_link(entry, "case artifact")
    return validate_flat_case(directory, planned)


def validate_flat_case(
    directory: Path,
    planned: dict[str, object],
) -> dict[str, object]:
    names = case_filenames(str(planned["branch_id"]))
    case_path = directory / names["case"]
    proof_path = directory / names["proof"]
    summary_path = directory / names["summary"]
    for path in (case_path, proof_path, summary_path):
        require_regular_single_link(path, "case artifact")
    case_record, _case_record_sha256 = load_authenticated_json(
        case_path,
        "case record",
    )
    proof_sha256 = authenticated_file_sha256(
        proof_path,
        "retained proof",
    )
    proof_summary, proof_summary_sha256 = load_authenticated_json(
        summary_path,
        "proof summary",
    )
    expected_case_keys = {
        "record_type",
        "schema_version",
        "plan_case",
        "formula",
        "proof",
        "proof_summary",
        "verified",
    }
    if (
        set(case_record) != expected_case_keys
        or
        case_record.get("record_type")
        != "fourth-word-solver-drat-case"
        or case_record.get("schema_version") != 2
        or case_record.get("plan_case") != planned
        or case_record.get("verified") is not True
    ):
        raise RuntimeError(
            f"{planned['branch_id']}: case checkpoint is invalid"
        )
    formula = case_record.get("formula")
    proof = case_record.get("proof")
    summary = case_record.get("proof_summary")
    if (
        not isinstance(formula, dict)
        or set(formula) != {"sha256", "variables", "clauses"}
        or type(formula["variables"]) is not int
        or formula["variables"] <= 0
        or type(formula["clauses"]) is not int
        or formula["clauses"] <= 0
        or not isinstance(proof, dict)
        or not isinstance(summary, dict)
        or proof
        != {
            "filename": names["proof"],
            "sha256": proof_sha256,
        }
        or summary
        != {
            "filename": names["summary"],
            "sha256": proof_summary_sha256,
        }
    ):
        raise RuntimeError(
            f"{planned['branch_id']}: case artifact hashes changed"
        )
    require_sha256(formula["sha256"], "case formula digest")
    expected_summary_keys = {
        "record_type",
        "schema_version",
        "case_id",
        "status",
        "case_formula_sha256",
        "variables",
        "clauses",
        "production",
        "resource_limits",
        "raw_solver_proof",
        "core_extraction_check",
        "retained_proof",
        "retained_replay",
    }
    retained = proof_summary.get("retained_proof")
    if (
        set(proof_summary) != expected_summary_keys
        or proof_summary.get("record_type")
        != "solver-generated-drat-core-proof"
        or proof_summary.get("schema_version") != 2
        or proof_summary.get("case_id") != planned["branch_id"]
        or proof_summary.get("status") != "UNSAT"
        or proof_summary.get("case_formula_sha256")
        != formula.get("sha256")
        or proof_summary.get("variables") != formula["variables"]
        or proof_summary.get("clauses") != formula["clauses"]
        or proof_summary.get("production", {}).get("solver")
        != "glucose4"
        or not isinstance(retained, dict)
        or retained.get("filename") != names["proof"]
        or retained.get("compressed_sha256") != proof_sha256
        or proof_summary.get("retained_replay", {}).get("verified")
        is not True
    ):
        raise RuntimeError(
            f"{planned['branch_id']}: proof summary is inconsistent"
        )
    return case_record


def clean_case_staging(case_root: Path, slug: str) -> None:
    for path in case_root.glob(f".{slug}.*"):
        if path.is_symlink() or not path.is_dir():
            raise RuntimeError(f"case staging path is invalid: {path}")
        identity = artifact_path_identity(path, directory=True)
        if not quarantine_owned_path(
            path,
            identity,
            directory=True,
        ):
            raise RuntimeError(
                f"case staging path changed during cleanup: {path}"
            )


def proof_resource_arguments(
    *,
    max_solve_seconds: int,
    max_raw_proof_bytes: int,
    max_retained_proof_bytes: int,
    max_memory_bytes: int,
) -> list[str]:
    return [
        "--max-solve-seconds",
        str(max_solve_seconds),
        "--max-raw-proof-bytes",
        str(max_raw_proof_bytes),
        "--max-retained-proof-bytes",
        str(max_retained_proof_bytes),
        "--max-memory-bytes",
        str(max_memory_bytes),
    ]


def generate_and_audit_formula(
    planned: dict[str, object],
    *,
    directory: Path,
    root: Path,
    python_command: str,
    environment: dict[str, str],
    commands: CommandRegistry,
) -> tuple[Path, Path, dict[str, object]]:
    branch_id = str(planned["branch_id"])
    formula = directory / "formula.cnf"
    metadata_path = directory / "formula.json"
    commands.run(
        isolated_python_script_command(
            python_command,
            "tools/generate_fourth_word_formula.py",
            "evidence/residual-two-word-cases.json",
            "evidence/third-word-cases.json",
            "research/third-word-child-frontier.json",
            "research/fourth-word-hard-frontier.json",
            branch_id,
            display_path(formula, root),
            display_path(metadata_path, root),
        ),
        environment=environment,
        root=root,
        timeout_seconds=FORMULA_COMMAND_TIMEOUT_SECONDS,
    )
    commands.run(
        isolated_python_script_command(
            python_command,
            "tools/audit_fourth_word_formula.py",
            display_path(formula, root),
            display_path(metadata_path, root),
        ),
        environment=environment,
        root=root,
        timeout_seconds=FORMULA_COMMAND_TIMEOUT_SECONDS,
    )
    metadata, _metadata_sha256 = load_authenticated_json(
        metadata_path,
        "formula metadata",
    )
    formula_sha256 = authenticated_file_sha256(
        formula,
        "generated formula",
    )
    if (
        metadata.get("branch_id") != branch_id
        or metadata.get("branch_sha256")
        != planned["branch_sha256"]
        or metadata.get("parent_child_id")
        != planned["parent_child_id"]
        or metadata.get("fourth_orbit_index")
        != planned["fourth_orbit_index"]
        or metadata.get("formula_sha256") != formula_sha256
    ):
        raise RuntimeError(f"{branch_id}: generated identity changed")
    return formula, metadata_path, metadata


def replay_checkpoint(
    directory: Path,
    planned: dict[str, object],
    *,
    root: Path,
    case_root: Path,
    python_command: str,
    checker: Path,
    checker_commit: str,
    environment: dict[str, str],
    commands: CommandRegistry,
    max_solve_seconds: int,
    max_raw_proof_bytes: int,
    max_retained_proof_bytes: int,
    max_memory_bytes: int,
) -> dict[str, object]:
    record = validate_case_directory(directory, planned)
    branch_id = str(planned["branch_id"])
    slug = branch_slug(branch_id)
    names = case_filenames(branch_id)
    with owned_temporary_directory(
        case_root,
        prefix=f".{slug}.replay.",
    ) as temporary:
        formula, _metadata_path, metadata = (
            generate_and_audit_formula(
                planned,
                directory=temporary,
                root=root,
                python_command=python_command,
                environment=environment,
                commands=commands,
            )
        )
        scratch = temporary / "proof-replay"
        scratch.mkdir()
        if record["formula"] != {
            "sha256": metadata["formula_sha256"],
            "variables": metadata["variables"],
            "clauses": metadata["clauses"],
        }:
            raise RuntimeError(
                f"{branch_id}: checkpoint formula identity changed"
            )
        commands.run(
            isolated_python_script_command(
                python_command,
                "proof-expansion/cli/prove_formula.py",
                display_path(formula, root),
                display_path(directory / names["proof"], root),
                display_path(directory / names["summary"], root),
                "--case-id",
                branch_id,
                "--solver",
                "glucose4",
                "--checker",
                display_path(checker, root),
                "--checker-commit",
                checker_commit,
                "--scratch-directory",
                display_path(scratch, root),
                *proof_resource_arguments(
                    max_solve_seconds=max_solve_seconds,
                    max_raw_proof_bytes=max_raw_proof_bytes,
                    max_retained_proof_bytes=(
                        max_retained_proof_bytes
                    ),
                    max_memory_bytes=max_memory_bytes,
                ),
                "--verify-existing",
            ),
            environment=environment,
            root=root,
            timeout_seconds=PROOF_COMMAND_TIMEOUT_SECONDS,
        )
    return validate_case_directory(directory, planned)


def run_case(
    planned: dict[str, object],
    *,
    root: Path,
    workspace: Path,
    python_command: str,
    checker: Path,
    checker_commit: str,
    environment: dict[str, str],
    commands: CommandRegistry,
    minimum_free_bytes: int,
    max_solve_seconds: int,
    max_raw_proof_bytes: int,
    max_retained_proof_bytes: int,
    max_memory_bytes: int,
) -> dict[str, object]:
    branch_id = str(planned["branch_id"])
    slug = branch_slug(branch_id)
    case_root = workspace / "cases"
    case_root.mkdir(parents=True, exist_ok=True)
    require_free_space(case_root, minimum_free_bytes)
    final_directory = case_root / slug
    if final_directory.exists() or final_directory.is_symlink():
        clean_case_staging(case_root, slug)
        return replay_checkpoint(
            final_directory,
            planned,
            root=root,
            case_root=case_root,
            python_command=python_command,
            checker=checker,
            checker_commit=checker_commit,
            environment=environment,
            commands=commands,
            max_solve_seconds=max_solve_seconds,
            max_raw_proof_bytes=max_raw_proof_bytes,
            max_retained_proof_bytes=max_retained_proof_bytes,
            max_memory_bytes=max_memory_bytes,
        )
    clean_case_staging(case_root, slug)
    staging = case_root / f".{slug}.{secrets.token_hex(8)}"
    staging.mkdir()
    staging_identity = artifact_path_identity(
        staging,
        directory=True,
    )
    staging_moved = False
    publication_state_uncertain = False
    names = case_filenames(branch_id)
    proof = staging / names["proof"]
    proof_summary = staging / names["summary"]
    case_record_path = staging / names["case"]
    try:
        formula, formula_metadata, metadata = (
            generate_and_audit_formula(
                planned,
                directory=staging,
                root=root,
                python_command=python_command,
                environment=environment,
                commands=commands,
            )
        )
        commands.run(
            isolated_python_script_command(
                python_command,
                "proof-expansion/cli/prove_formula.py",
                display_path(formula, root),
                display_path(proof, root),
                display_path(proof_summary, root),
                "--case-id",
                branch_id,
                "--solver",
                "glucose4",
                "--checker",
                display_path(checker, root),
                "--checker-commit",
                checker_commit,
                *proof_resource_arguments(
                    max_solve_seconds=max_solve_seconds,
                    max_raw_proof_bytes=max_raw_proof_bytes,
                    max_retained_proof_bytes=(
                        max_retained_proof_bytes
                    ),
                    max_memory_bytes=max_memory_bytes,
                ),
            ),
            environment=environment,
            root=root,
            timeout_seconds=PROOF_COMMAND_TIMEOUT_SECONDS,
        )
        with owned_temporary_directory(
            case_root,
            prefix=f".{slug}.proof-replay.",
        ) as scratch_directory:
            commands.run(
                isolated_python_script_command(
                    python_command,
                    "proof-expansion/cli/prove_formula.py",
                    display_path(formula, root),
                    display_path(proof, root),
                    display_path(proof_summary, root),
                    "--case-id",
                    branch_id,
                    "--solver",
                    "glucose4",
                    "--checker",
                    display_path(checker, root),
                    "--checker-commit",
                    checker_commit,
                    "--scratch-directory",
                    display_path(scratch_directory, root),
                    *proof_resource_arguments(
                        max_solve_seconds=max_solve_seconds,
                        max_raw_proof_bytes=max_raw_proof_bytes,
                        max_retained_proof_bytes=(
                            max_retained_proof_bytes
                        ),
                        max_memory_bytes=max_memory_bytes,
                    ),
                    "--verify-existing",
                ),
                environment=environment,
                root=root,
                timeout_seconds=PROOF_COMMAND_TIMEOUT_SECONDS,
            )
        summary = load_json(proof_summary)
        if (
            summary.get("case_formula_sha256")
            != metadata.get("formula_sha256")
        ):
            raise RuntimeError(f"{branch_id}: generated identity changed")
        case_record = {
            "record_type": "fourth-word-solver-drat-case",
            "schema_version": 2,
            "plan_case": planned,
            "formula": {
                "sha256": metadata["formula_sha256"],
                "variables": metadata["variables"],
                "clauses": metadata["clauses"],
            },
            "proof": {
                "filename": names["proof"],
                "sha256": file_sha256(proof),
            },
            "proof_summary": {
                "filename": names["summary"],
                "sha256": file_sha256(proof_summary),
            },
            "verified": True,
        }
        atomic_write_json(case_record_path, case_record)
        for path, description in (
            (formula, "generated formula"),
            (formula_metadata, "formula metadata"),
        ):
            identity = artifact_path_identity(
                path,
                directory=False,
            )
            if not quarantine_owned_path(
                path,
                identity,
                directory=False,
            ):
                raise RuntimeError(
                    f"{description} changed during cleanup"
                )
        fsync_directory(staging)
        try:
            durable_publish_noreplace(
                staging,
                final_directory,
                directory=True,
                expected_source_identity=staging_identity,
            )
        except PublicationCommittedError:
            staging_moved = True
            publication_state_uncertain = True
            raise
        staging_moved = True
        return validate_case_directory(final_directory, planned)
    except BaseException as error:
        if publication_state_uncertain:
            cleanup_succeeded = all(
                (
                    quarantine_owned_path(
                        final_directory,
                        staging_identity,
                        directory=True,
                    ),
                    quarantine_owned_path(
                        staging,
                        staging_identity,
                        directory=True,
                    ),
                )
            )
        else:
            cleanup_target = (
                final_directory if staging_moved else staging
            )
            cleanup_succeeded = quarantine_owned_path(
                cleanup_target,
                staging_identity,
                directory=True,
            )
        if not cleanup_succeeded:
            raise RuntimeError(
                f"{branch_id}: case staging cleanup was unsafe"
            ) from error
        raise


def build_cases(
    cases: list[dict[str, object]],
    *,
    root: Path,
    workspace: Path,
    python_command: str,
    checker: Path,
    checker_commit: str,
    environment: dict[str, str],
    workers: int,
    minimum_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
    max_solve_seconds: int = DEFAULT_MAX_SOLVE_SECONDS,
    max_raw_proof_bytes: int = DEFAULT_MAX_RAW_PROOF_BYTES,
    max_retained_proof_bytes: int = DEFAULT_MAX_RETAINED_PROOF_BYTES,
    max_memory_bytes: int = DEFAULT_MAX_MEMORY_BYTES,
    progress=None,
) -> list[dict[str, object]]:
    commands = CommandRegistry()
    records: dict[str, dict[str, object]] = {}
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = {}
    with coordinator_signal_handlers(commands):
        try:
            futures = {
                executor.submit(
                    run_case,
                    case,
                    root=root,
                    workspace=workspace,
                    python_command=python_command,
                    checker=checker,
                    checker_commit=checker_commit,
                    environment=environment,
                    commands=commands,
                    minimum_free_bytes=minimum_free_bytes,
                    max_solve_seconds=max_solve_seconds,
                    max_raw_proof_bytes=max_raw_proof_bytes,
                    max_retained_proof_bytes=(
                        max_retained_proof_bytes
                    ),
                    max_memory_bytes=max_memory_bytes,
                ): case
                for case in cases
            }
            completed = 0
            for future in as_completed(futures):
                case = futures[future]
                record = future.result()
                records[str(case["branch_id"])] = record
                completed += 1
                if progress is not None:
                    progress(completed, len(cases), case, record)
        except BaseException:
            commands.cancel()
            for future in futures:
                future.cancel()
            try:
                commands.terminate_all()
            finally:
                executor.shutdown(wait=True, cancel_futures=True)
            raise
    executor.shutdown(wait=True)
    return [records[str(case["branch_id"])] for case in cases]


def case_index_record(
    case_record: dict[str, object],
    *,
    proof_directory: Path,
    artifact_directory: Path,
    root: Path,
) -> dict[str, object]:
    planned = case_record["plan_case"]
    branch_id = str(planned["branch_id"])
    names = case_filenames(branch_id)
    proof_summary = case_record["proof_summary"]
    return {
        **planned,
        "formula": case_record["formula"],
        "proof": {
            "path": display_path(proof_directory / names["proof"], root),
            "sha256": case_record["proof"]["sha256"],
        },
        "proof_summary": {
            "path": display_path(
                proof_directory / names["summary"],
                root,
            ),
            "sha256": proof_summary["sha256"],
        },
        "case_record": {
            "path": display_path(
                proof_directory / names["case"],
                root,
            ),
            "sha256": file_sha256(
                artifact_directory / names["case"]
            ),
        },
        "verified": True,
    }


def expected_bundle_members(cases: Iterable[dict[str, object]]) -> set[str]:
    names: set[str] = set()
    for case in cases:
        branch_id = str(case["branch_id"])
        case_names = expected_case_members(branch_id)
        if names & case_names:
            raise RuntimeError("case artifact filenames collide")
        names.update(case_names)
    return names


def clean_stale_bundle_staging(
    proof_directory: Path,
    output_path: Path,
) -> list[Path]:
    removed = []
    targets = (
        (proof_directory.parent, f".{proof_directory.name}.", True),
        (output_path.parent, f".{output_path.name}.", False),
    )
    for parent, prefix, expect_directory in targets:
        if not parent.exists():
            continue
        if not parent.is_dir() or parent.is_symlink():
            raise RuntimeError(f"staging parent is invalid: {parent}")
        for path in parent.iterdir():
            if not path.name.startswith(prefix):
                continue
            token = path.name[len(prefix) :]
            if STAGING_TOKEN_PATTERN.fullmatch(token) is None:
                continue
            if path.is_symlink():
                raise RuntimeError(f"stale staging path is invalid: {path}")
            if expect_directory:
                if not path.is_dir():
                    raise RuntimeError(
                        f"stale proof staging is invalid: {path}"
                    )
                identity = artifact_path_identity(
                    path,
                    directory=True,
                )
            else:
                require_regular_single_link(path, "stale index staging")
                identity = artifact_path_identity(
                    path,
                    directory=False,
                )
            if not quarantine_owned_path(
                path,
                identity,
                directory=expect_directory,
            ):
                raise RuntimeError(
                    f"stale staging changed during cleanup: {path}"
                )
            removed.append(path)
        if removed:
            fsync_directory(parent)
    return removed


def stage_bundle(
    case_records: list[dict[str, object]],
    *,
    root: Path,
    workspace: Path,
    plan: dict[str, object],
    plan_path: Path,
    plan_sha256: str,
    proof_directory: Path,
    output_path: Path,
    checker_commit: str,
    checker_sha256: str,
    pipeline_files: dict[str, str],
    pipeline_python_tree: dict[str, object],
    solver_environment: dict[str, object],
    resource_limits: dict[str, object],
) -> StagedBundle:
    require_certification_resource_limits(resource_limits)
    planned_cases = plan.get("cases")
    if (
        plan.get("case_count") != 140
        or not isinstance(planned_cases, list)
        or len(planned_cases) != 140
        or [
            record.get("plan_case")
            if isinstance(record, dict)
            else None
            for record in case_records
        ]
        != planned_cases
    ):
        raise RuntimeError(
            "bundle staging requires the complete ordered plan"
        )
    token = secrets.token_hex(8)
    staging_directory = proof_directory.parent / (
        f".{proof_directory.name}.{token}"
    )
    staged_index = output_path.parent / f".{output_path.name}.{token}"
    if (
        staging_directory.exists()
        or staging_directory.is_symlink()
        or staged_index.exists()
        or staged_index.is_symlink()
    ):
        raise RuntimeError("bundle staging paths already exist")
    case_root = workspace / "cases"
    bundle_bytes = 0
    for case_record in case_records:
        planned = case_record["plan_case"]
        source_directory = case_root / branch_slug(
            str(planned["branch_id"])
        )
        validated = validate_case_directory(source_directory, planned)
        if validated != case_record:
            raise RuntimeError("source case changed before staging")
        for filename in expected_case_members(str(planned["branch_id"])):
            bundle_bytes += (source_directory / filename).stat().st_size
    proof_directory.parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    require_free_space(
        proof_directory.parent,
        int(resource_limits["minimum_free_bytes"]) + bundle_bytes,
    )
    require_free_space(
        output_path.parent,
        int(resource_limits["minimum_free_bytes"]),
    )
    staging_directory.mkdir()
    staging_identity = artifact_path_identity(
        staging_directory,
        directory=True,
    )
    staged_index_identity = None
    fsync_directory(staging_directory.parent)
    try:
        for case_record in case_records:
            planned = case_record["plan_case"]
            branch_id = str(planned["branch_id"])
            source_directory = case_root / branch_slug(branch_id)
            for filename in sorted(expected_case_members(branch_id)):
                source = source_directory / filename
                destination = staging_directory / filename
                shutil.copyfile(source, destination)
                fsync_file(destination)
        fsync_directory(staging_directory)
        observed = {
            entry.name for entry in staging_directory.iterdir()
        }
        expected = expected_bundle_members(
            [record["plan_case"] for record in case_records]
        )
        if observed != expected:
            raise RuntimeError("staged bundle membership is incorrect")

        staged_records = [
            validate_flat_case(
                staging_directory,
                record["plan_case"],
            )
            for record in case_records
        ]
        if staged_records != case_records:
            raise RuntimeError("staged case records changed during copying")
        index_cases = [
            case_index_record(
                record,
                proof_directory=proof_directory,
                artifact_directory=staging_directory,
                root=root,
            )
            for record in staged_records
        ]
        child_counts = Counter(
            str(case["parent_child_id"]) for case in index_cases
        )
        index = {
            "record_type": "fourth-word-solver-drat-proof-index",
            "schema_version": 2,
            "certification_date": "2026-09-03",
            "plan": {
                "path": display_path(plan_path, root),
                "sha256": plan_sha256,
            },
            "proof_directory": display_path(proof_directory, root),
            "solver": "glucose4",
            "solver_environment": solver_environment,
            "checker": {
                "name": "drat-trim",
                "commit": checker_commit,
                "binary_sha256": checker_sha256,
            },
            "pipeline_files": pipeline_files,
            "pipeline_python_tree": pipeline_python_tree,
            "resource_limits": resource_limits,
            "prior_rup_certificate": {
                "certified_branch_count": 184,
                "proof_index": plan["sources"]["rup_proof_index"],
                "replay_attestation": plan["sources"][
                    "rup_replay_attestation"
                ],
                "bundle_manifest": plan["sources"][
                    "rup_bundle_manifest"
                ],
                "certified_revision": plan["sources"][
                    "rup_certified_revision"
                ],
            },
            "result": {
                "newly_certified_branch_count": len(index_cases),
                "combined_certified_branch_count": (
                    184 + len(index_cases)
                ),
                "frontier_branch_count": 350,
                "remaining_branch_count": 26,
                "fully_closed_selected_child_count": 0,
                "fully_closed_normalized_parent_count": 0,
                "covering_number_status": "15 or 16",
                "lower_bound_15": plan["completion_implication"][
                    "lower_bound_15"
                ],
            },
            "case_count": len(index_cases),
            "per_child": [
                {
                    "parent_child_id": child_id,
                    "proof_count": child_counts[child_id],
                }
                for child_id in (
                    "w4-weight5-intersection0::orbit-005",
                    "w4-weight5-intersection0::orbit-007",
                    "w4-weight5-intersection0::orbit-014",
                    "w4-weight5-intersection0::orbit-015",
                )
            ],
            "cases": index_cases,
        }
        staged_index_identity = atomic_write_json(
            staged_index,
            index,
        )
        require_free_space(
            output_path.parent,
            promotion_index_free_space_requirement(
                minimum_bytes=int(
                    resource_limits["minimum_free_bytes"]
                ),
                index_bytes=staged_index.stat().st_size,
            ),
        )
        return StagedBundle(
            proof_directory=staging_directory,
            index_path=staged_index,
            token=token,
            index_record=index,
            proof_directory_sha256=directory_sha256(
                staging_directory
            ),
            index_sha256=authenticated_file_sha256(
                staged_index,
                "staged proof index",
            ),
            proof_directory_identity=staging_identity,
            index_identity=staged_index_identity,
        )
    except BaseException as error:
        cleanup_succeeded = all(
            (
                quarantine_owned_path(
                    staged_index,
                    staged_index_identity,
                    directory=False,
                ),
                quarantine_owned_path(
                    staging_directory,
                    staging_identity,
                    directory=True,
                ),
            )
        )
        if not cleanup_succeeded:
            raise RuntimeError(
                "bundle staging cleanup could not safely remove outputs"
            ) from error
        raise


def promotion_journal_record(
    *,
    token: str,
    root: Path,
    proof_directory: Path,
    output_path: Path,
    staging_directory: Path,
    staged_index: Path,
    proof_directory_sha256: str,
    output_sha256: str,
) -> dict[str, object]:
    if STAGING_TOKEN_PATTERN.fullmatch(token) is None:
        raise RuntimeError("promotion token is invalid")
    expected_staging = proof_directory.parent / (
        f".{proof_directory.name}.{token}"
    )
    expected_index = output_path.parent / (
        f".{output_path.name}.{token}"
    )
    if (
        staging_directory != expected_staging
        or staged_index != expected_index
    ):
        raise RuntimeError("promotion staging paths are not canonical")
    return {
        "record_type": "fourth-word-solver-drat-promotion",
        "schema_version": 2,
        "phase": "ready",
        "token": token,
        "proof_directory": display_path(proof_directory, root),
        "output": display_path(output_path, root),
        "staging_directory": display_path(staging_directory, root),
        "staged_index": display_path(staged_index, root),
        "proof_directory_sha256": proof_directory_sha256,
        "output_sha256": output_sha256,
    }


def recover_promotion(
    *,
    root: Path,
    proof_directory: Path,
    output_path: Path,
    journal_path: Path,
) -> str:
    if not journal_path.exists() and not journal_path.is_symlink():
        return "none"
    require_regular_single_link(journal_path, "promotion journal")
    journal_identity = artifact_path_identity(
        journal_path,
        directory=False,
    )
    record = load_json(journal_path)
    if (
        artifact_path_identity(
            journal_path,
            directory=False,
        )
        != journal_identity
    ):
        raise RuntimeError("promotion journal identity changed")
    if (
        record.get("record_type")
        != "fourth-word-solver-drat-promotion"
        or record.get("schema_version") != 2
        or record.get("phase") != "ready"
    ):
        raise RuntimeError("promotion journal is invalid")
    token = str(record.get("token"))
    if STAGING_TOKEN_PATTERN.fullmatch(token) is None:
        raise RuntimeError("promotion journal token is invalid")
    staging_directory = proof_directory.parent / (
        f".{proof_directory.name}.{token}"
    )
    staged_index = output_path.parent / (
        f".{output_path.name}.{token}"
    )
    expected_common = promotion_journal_record(
        token=token,
        root=root,
        proof_directory=proof_directory,
        output_path=output_path,
        staging_directory=staging_directory,
        staged_index=staged_index,
        proof_directory_sha256=str(
            record.get("proof_directory_sha256")
        ),
        output_sha256=str(record.get("output_sha256")),
    )
    if record != expected_common:
        raise RuntimeError("promotion journal fields are invalid")
    expected_directory_hash = str(record["proof_directory_sha256"])
    expected_index_hash = str(record["output_sha256"])
    directory_identities: dict[
        Path,
        tuple[int, int, int] | None,
    ] = {}
    for directory, description in (
        (staging_directory, "staged proof directory"),
        (proof_directory, "promoted proof directory"),
    ):
        if not directory.exists() and not directory.is_symlink():
            directory_identities[directory] = None
            continue
        identity = artifact_path_identity(
            directory,
            directory=True,
        )
        if directory_sha256(directory) != expected_directory_hash:
            raise RuntimeError(f"{description} changed")
        if (
            artifact_path_identity(
                directory,
                directory=True,
            )
            != identity
        ):
            raise RuntimeError(f"{description} identity changed")
        directory_identities[directory] = identity
    file_identities: dict[
        Path,
        tuple[int, int, int] | None,
    ] = {}
    for path, description in (
        (staged_index, "staged proof index"),
        (output_path, "promoted proof index"),
    ):
        if not path.exists() and not path.is_symlink():
            file_identities[path] = None
            continue
        identity = artifact_path_identity(
            path,
            directory=False,
        )
        if (
            authenticated_file_sha256(path, description)
            != expected_index_hash
        ):
            raise RuntimeError(f"{description} changed")
        if (
            artifact_path_identity(
                path,
                directory=False,
            )
            != identity
        ):
            raise RuntimeError(f"{description} identity changed")
        file_identities[path] = identity
    cleanup_succeeded = all(
        (
            quarantine_owned_path(
                output_path,
                file_identities[output_path],
                directory=False,
            ),
            quarantine_owned_path(
                proof_directory,
                directory_identities[proof_directory],
                directory=True,
            ),
            quarantine_owned_path(
                staged_index,
                file_identities[staged_index],
                directory=False,
            ),
            quarantine_owned_path(
                staging_directory,
                directory_identities[staging_directory],
                directory=True,
            ),
        )
    )
    if cleanup_succeeded:
        cleanup_succeeded = quarantine_owned_path(
            journal_path,
            journal_identity,
            directory=False,
        )
    if not cleanup_succeeded:
        raise RuntimeError(
            "promotion recovery could not safely remove all outputs"
        )
    return "ready-rolled-back"


def promote_bundle(
    staging_directory: Path,
    staged_index: Path,
    *,
    root: Path,
    proof_directory: Path,
    output_path: Path,
    journal_path: Path,
    token: str,
    expected_directory_hash: str,
    expected_index_hash: str,
    expected_staging_identity: tuple[int, int, int] | None = None,
    expected_staged_index_identity: tuple[int, int, int] | None = None,
    validate_inputs: Callable[[], None] | None = None,
) -> None:
    staging_identity = (
        artifact_path_identity(staging_directory, directory=True)
        if expected_staging_identity is None
        else expected_staging_identity
    )
    staged_index_identity = (
        artifact_path_identity(staged_index, directory=False)
        if expected_staged_index_identity is None
        else expected_staged_index_identity
    )
    journal_identity = None
    output_identity = None
    journal_published = False
    directory_published = False
    output_published = False
    try:
        if proof_directory.exists() or output_path.exists():
            raise RuntimeError("final bundle outputs already exist")
        require_sha256(expected_directory_hash, "staged bundle digest")
        require_sha256(expected_index_hash, "staged index digest")
        staged_index_payload, staged_index_digest = (
            load_authenticated_bytes(
                staged_index,
                "staged proof index",
            )
        )
        if (
            directory_sha256(staging_directory)
            != expected_directory_hash
            or staged_index_digest != expected_index_hash
        ):
            raise RuntimeError("staged bundle changed before promotion")
        if validate_inputs is not None:
            validate_inputs()
        if (
            artifact_path_identity(
                staging_directory,
                directory=True,
            )
            != staging_identity
            or artifact_path_identity(
                staged_index,
                directory=False,
            )
            != staged_index_identity
        ):
            raise RuntimeError(
                "staged bundle identity changed before promotion"
            )
        fsync_directory(staging_directory.parent)
        journal_identity = atomic_write_json(
            journal_path,
            promotion_journal_record(
                token=token,
                root=root,
                proof_directory=proof_directory,
                output_path=output_path,
                staging_directory=staging_directory,
                staged_index=staged_index,
                proof_directory_sha256=expected_directory_hash,
                output_sha256=expected_index_hash,
            ),
        )
        journal_published = True
        try:
            durable_publish_noreplace(
                staging_directory,
                proof_directory,
                directory=True,
                expected_source_identity=staging_identity,
            )
        except PublicationCommittedError:
            directory_published = True
            raise
        directory_published = True
        if (
            artifact_path_identity(
                proof_directory,
                directory=True,
            )
            != staging_identity
        ):
            raise RuntimeError("promoted proof directory identity changed")
        output_identity = atomic_write_bytes(
            output_path,
            staged_index_payload,
        )
        output_published = True
        if (
            directory_sha256(proof_directory) != expected_directory_hash
            or authenticated_file_sha256(
                output_path,
                "promoted proof index",
            )
            != expected_index_hash
        ):
            raise RuntimeError("promoted bundle identity changed")
        if validate_inputs is not None:
            validate_inputs()
        if (
            directory_sha256(proof_directory) != expected_directory_hash
            or authenticated_file_sha256(
                output_path,
                "promoted proof index",
            )
            != expected_index_hash
        ):
            raise RuntimeError(
                "promoted bundle changed during input validation"
            )
    except BaseException as error:
        cleanup_succeeded = all(
            (
                (
                    quarantine_owned_path(
                        output_path,
                        output_identity,
                        directory=False,
                    )
                    if output_published
                    else True
                ),
                (
                    quarantine_owned_path(
                        proof_directory,
                        staging_identity,
                        directory=True,
                    )
                    if directory_published
                    else True
                ),
                quarantine_owned_path(
                    staged_index,
                    staged_index_identity,
                    directory=False,
                ),
                quarantine_owned_path(
                    staging_directory,
                    staging_identity,
                    directory=True,
                ),
            )
        )
        if cleanup_succeeded and journal_published:
            cleanup_succeeded = quarantine_owned_path(
                journal_path,
                journal_identity,
                directory=False,
            )
        if not cleanup_succeeded:
            raise RuntimeError(
                "promotion rollback could not safely remove all outputs"
            ) from error
        raise
    cleanup_succeeded = all(
        (
            quarantine_owned_path(
                staged_index,
                staged_index_identity,
                directory=False,
            ),
            quarantine_owned_path(
                journal_path,
                journal_identity,
                directory=False,
            ),
        )
    )
    if not cleanup_succeeded:
        raise RuntimeError(
            "promotion cleanup could not safely remove temporary files"
        )
