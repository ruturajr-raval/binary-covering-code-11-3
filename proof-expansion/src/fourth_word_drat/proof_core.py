from __future__ import annotations

from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Iterable
import unicodedata

from bootstrap_drat_trim import validate_pinned_checkout
from fourth_word_drat.secure_io import (
    artifact_path_identity,
    authenticated_snapshot,
    authenticated_snapshots,
    authenticated_file_sha256,
    authenticated_file_version,
    descriptor_artifact_identity,
    durable_publish_noreplace,
    load_authenticated_bytes,
    load_authenticated_json,
    owned_temporary_directory,
    PublicationCommittedError,
    quarantine_owned_path,
    write_private_file,
)


DRAT_TRIM_COMMIT = "2e3b2dc0ecf938addbd779d42877b6ed69d9a985"
BUFFER_SIZE = 1024 * 1024
DEFAULT_MAX_SOLVE_SECONDS = 300
DEFAULT_MAX_RAW_PROOF_BYTES = 1024 * 1024 * 1024
DEFAULT_MAX_RETAINED_PROOF_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_MEMORY_BYTES = 12 * 1024 * 1024 * 1024
DEFAULT_MAX_CHECKER_SECONDS = 900
DEFAULT_MAX_CHECKER_OUTPUT_BYTES = 4 * 1024 * 1024


def normalized_path_parts(path: Path) -> tuple[str, ...]:
    absolute = Path(os.path.abspath(str(path)))
    return tuple(
        unicodedata.normalize("NFD", part).casefold()
        for part in absolute.parts
    )


def paths_overlap(left: Path, right: Path) -> bool:
    left_parts = normalized_path_parts(left)
    right_parts = normalized_path_parts(right)
    common_length = min(len(left_parts), len(right_parts))
    if left_parts[:common_length] == right_parts[:common_length]:
        return True
    if left.exists() and right.exists() and os.path.samefile(left, right):
        return True
    return False


def repository_path(path: Path, root: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    lexical = Path(os.path.abspath(str(candidate)))
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        raise ValueError(f"path is outside the repository: {path}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"path contains a symbolic link: {path}")
    return lexical


def display_path(path: Path, root: Path) -> str:
    return str(repository_path(path, root).relative_to(root))


def require_regular_single_link(path: Path, description: str) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_nlink != 1
    ):
        raise RuntimeError(
            f"{description} is not a single-link regular file: {path}"
        )


def file_metrics(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    size = 0
    lines = 0
    ended_with_newline = True
    with path.open("rb") as handle:
        while True:
            payload = handle.read(BUFFER_SIZE)
            if not payload:
                break
            digest.update(payload)
            size += len(payload)
            lines += payload.count(b"\n")
            ended_with_newline = payload.endswith(b"\n")
    if size and not ended_with_newline:
        lines += 1
    return {
        "bytes": size,
        "lines": lines,
        "sha256": digest.hexdigest(),
    }


def file_sha256(path: Path) -> str:
    return str(file_metrics(path)["sha256"])


def require_sha256(value: object, description: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(
            character not in "0123456789abcdef"
            for character in value
        )
    ):
        raise RuntimeError(f"{description} is not a SHA-256 digest")
    return value


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(
    path: Path,
    record: dict[str, object],
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
            handle.write(
                (
                    json.dumps(record, indent=2, sort_keys=True) + "\n"
                ).encode("ascii")
            )
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


def validate_checker(
    checker: Path,
    commit: str,
    *,
    root: Path,
) -> tuple[bytes, str]:
    expected = root / "build/drat-trim-src/drat-trim"
    if checker != expected:
        raise RuntimeError(
            "checker must be build/drat-trim-src/drat-trim"
        )
    if commit != DRAT_TRIM_COMMIT:
        raise RuntimeError("proof checker commit is not pinned")
    require_regular_single_link(checker, "proof checker")
    if not os.access(checker, os.X_OK):
        raise RuntimeError("proof checker is not executable")
    validate_pinned_checkout(
        checker.parent,
        commit,
        allowed_untracked={"drat-trim"},
    )
    return load_authenticated_bytes(checker, "proof checker")


def normalize_checker_output(result: subprocess.CompletedProcess[str]) -> dict[
    str,
    object,
]:
    combined = result.stdout + result.stderr
    output_lines = combined.splitlines()
    verified_markers = [
        line for line in output_lines if line.strip() == "s VERIFIED"
    ]
    if result.returncode != 0 or len(verified_markers) != 1:
        raise RuntimeError(
            "drat-trim did not verify the proof:\n" + combined[-12000:]
        )
    retained_lines = []
    timing_lines = 0
    for line in output_lines:
        if not line.strip():
            continue
        normalized, replacements = re.subn(
            r"^(c verification time:) [0-9.]+ seconds$",
            r"\1 <elapsed>",
            line,
        )
        timing_lines += replacements
        retained_lines.append(normalized)
    if timing_lines != 1:
        raise RuntimeError(
            "checker output must contain one verification-time line"
        )
    stable_output = "\n".join(retained_lines) + "\n"
    return {
        "return_code": result.returncode,
        "verified": True,
        "verified_marker_count": len(verified_markers),
        "output_line_count": len(output_lines),
        "output_sha256": hashlib.sha256(
            stable_output.encode("utf-8")
        ).hexdigest(),
        "output": retained_lines,
    }


def validate_checker_record(
    record: object,
    *,
    description: str,
) -> None:
    expected_keys = {
        "return_code",
        "verified",
        "verified_marker_count",
        "output_line_count",
        "output_sha256",
        "output",
    }
    if not isinstance(record, dict) or set(record) != expected_keys:
        raise RuntimeError(f"{description} schema is invalid")
    output = record["output"]
    if (
        type(record["return_code"]) is not int
        or record["return_code"] != 0
        or record["verified"] is not True
        or type(record["verified_marker_count"]) is not int
        or record["verified_marker_count"] != 1
        or type(record["output_line_count"]) is not int
        or record["output_line_count"] < 1
        or not isinstance(output, list)
        or any(not isinstance(line, str) for line in output)
        or record["output_line_count"] < len(output)
        or output.count("s VERIFIED") != 1
    ):
        raise RuntimeError(f"{description} result is invalid")
    stable_output = "\n".join(output) + "\n"
    if record["output_sha256"] != hashlib.sha256(
        stable_output.encode("utf-8")
    ).hexdigest():
        raise RuntimeError(f"{description} output digest is invalid")


def validate_proof_summary_record(
    record: object,
    *,
    case_id: str,
    formula_sha256: str,
    variables: int,
    clauses: int,
    proof_path: Path,
    checker_commit: str,
    checker_sha256: str,
    python_sat_version: str,
    max_solve_seconds: int = DEFAULT_MAX_SOLVE_SECONDS,
    max_raw_proof_bytes: int = DEFAULT_MAX_RAW_PROOF_BYTES,
    max_retained_proof_bytes: int = DEFAULT_MAX_RETAINED_PROOF_BYTES,
    max_memory_bytes: int = DEFAULT_MAX_MEMORY_BYTES,
) -> tuple[dict[str, object], dict[str, object]]:
    expected_keys = {
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
    if (
        not isinstance(record, dict)
        or set(record) != expected_keys
        or record.get("record_type")
        != "solver-generated-drat-core-proof"
        or record.get("schema_version") != 2
        or record.get("case_id") != case_id
        or record.get("status") != "UNSAT"
    ):
        raise RuntimeError("retained proof summary identity is invalid")
    if (
        record.get("case_formula_sha256") != formula_sha256
        or record.get("variables") != variables
        or record.get("clauses") != clauses
    ):
        raise RuntimeError("retained proof formula identity changed")
    if record.get("production") != {
        "solver": "glucose4",
        "python_sat_version": python_sat_version,
        "solver_output": "text DRAT",
        "core_extractor": "drat-trim",
        "core_extractor_mode": "-l",
        "checker_commit": checker_commit,
        "checker_binary_sha256": checker_sha256,
    }:
        raise RuntimeError("retained proof production metadata changed")
    if record.get("resource_limits") != {
        "solve_seconds": max_solve_seconds,
        "raw_proof_bytes": max_raw_proof_bytes,
        "retained_proof_bytes": max_retained_proof_bytes,
        "memory_watchdog_bytes": max_memory_bytes,
        "checker_seconds": DEFAULT_MAX_CHECKER_SECONDS,
        "checker_output_bytes": DEFAULT_MAX_CHECKER_OUTPUT_BYTES,
    }:
        raise RuntimeError("retained proof resource limits changed")

    raw = record.get("raw_solver_proof")
    if (
        not isinstance(raw, dict)
        or set(raw)
        != {"retained", "format", "bytes", "lines", "sha256"}
        or raw["retained"] is not False
        or raw["format"] != "text DRAT"
        or type(raw["bytes"]) is not int
        or raw["bytes"] <= 0
        or raw["bytes"] > max_raw_proof_bytes
        or type(raw["lines"]) is not int
        or raw["lines"] <= 0
    ):
        raise RuntimeError("raw proof metadata is invalid")
    require_sha256(raw["sha256"], "raw proof digest")
    validate_checker_record(
        record.get("core_extraction_check"),
        description="core extraction check",
    )

    retained = record.get("retained_proof")
    retained_keys = {
        "filename",
        "format",
        "strategy",
        "compression",
        "uncompressed_bytes",
        "uncompressed_lines",
        "uncompressed_sha256",
        "compressed_bytes",
        "compressed_sha256",
    }
    if (
        not isinstance(retained, dict)
        or set(retained) != retained_keys
        or retained.get("filename") != proof_path.name
        or retained.get("format") != "text DRAT"
        or retained.get("strategy") != "drat-trim core lemmas"
        or retained.get("compression") != "gzip"
        or type(retained.get("uncompressed_bytes")) is not int
        or retained["uncompressed_bytes"] <= 0
        or retained["uncompressed_bytes"] > max_retained_proof_bytes
        or type(retained.get("uncompressed_lines")) is not int
        or retained["uncompressed_lines"] <= 0
        or type(retained.get("compressed_bytes")) is not int
        or retained["compressed_bytes"] <= 0
        or retained["compressed_bytes"] > max_retained_proof_bytes
    ):
        raise RuntimeError("retained proof metadata is invalid")
    require_sha256(
        retained["uncompressed_sha256"],
        "retained uncompressed proof digest",
    )
    require_sha256(
        retained["compressed_sha256"],
        "retained compressed proof digest",
    )
    compressed_metrics = file_metrics(proof_path)
    if (
        retained["compressed_bytes"] != compressed_metrics["bytes"]
        or retained["compressed_sha256"] != compressed_metrics["sha256"]
    ):
        raise RuntimeError("retained compressed proof identity changed")

    replay = record.get("retained_replay")
    checker_record_keys = {
        "return_code",
        "verified",
        "verified_marker_count",
        "output_line_count",
        "output_sha256",
        "output",
    }
    replay_keys = {
        "checker",
        "checker_commit",
        "checker_binary_sha256",
        *checker_record_keys,
    }
    if (
        not isinstance(replay, dict)
        or set(replay) != replay_keys
        or replay.get("checker") != "drat-trim"
        or replay.get("checker_commit") != checker_commit
        or replay.get("checker_binary_sha256") != checker_sha256
    ):
        raise RuntimeError("retained proof replay metadata is invalid")
    validate_checker_record(
        {
            key: replay[key]
            for key in checker_record_keys
        },
        description="retained proof replay",
    )
    return retained, compressed_metrics


def run_checker(
    checker: Path,
    formula: Path,
    proof: Path,
    *,
    lemma_output: Path | None = None,
    timeout_seconds: int = DEFAULT_MAX_CHECKER_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_CHECKER_OUTPUT_BYTES,
) -> dict[str, object]:
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise RuntimeError("proof checker timeout is invalid")
    if type(max_output_bytes) is not int or max_output_bytes <= 0:
        raise RuntimeError("proof checker output limit is invalid")
    command = [
        str(checker),
        str(formula),
        str(proof),
    ]
    if lemma_output is not None:
        command.extend(["-l", str(lemma_output)])
    command.append("-w")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if process.stdout is None:
        raise RuntimeError("checker output pipe is unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + timeout_seconds
    failure = None
    try:
        while selector.get_map():
            now = time.monotonic()
            if now >= deadline:
                failure = "proof checker exceeded time limit"
                break
            for key, _events in selector.select(
                timeout=min(0.1, deadline - now)
            ):
                payload = os.read(key.fd, BUFFER_SIZE)
                if not payload:
                    selector.unregister(key.fileobj)
                    continue
                if len(output) + len(payload) > max_output_bytes:
                    failure = "proof checker output exceeds size limit"
                    break
                output.extend(payload)
            if failure is not None:
                break
        if failure is not None:
            terminate_process(process)
            raise RuntimeError(failure)
        try:
            return_code = process.wait(timeout=5)
        except subprocess.TimeoutExpired as exc:
            terminate_process(process)
            raise RuntimeError(
                "proof checker did not exit after closing output"
            ) from exc
    except BaseException:
        terminate_process(process)
        raise
    finally:
        selector.close()
        process.stdout.close()
    combined = output.decode("utf-8", errors="replace")
    result = subprocess.CompletedProcess(
        command,
        return_code,
        combined,
        "",
    )
    return normalize_checker_output(result)


def terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def write_solver_proof(
    lines: Iterable[str],
    output: Path,
    *,
    max_bytes: int,
) -> dict[str, object]:
    digest = hashlib.sha256()
    line_count = 0
    byte_count = 0
    with output.open("wb") as handle:
        for line in lines:
            payload = (line + "\n").encode("ascii")
            if byte_count + len(payload) > max_bytes:
                raise RuntimeError("raw solver proof exceeds size limit")
            handle.write(payload)
            digest.update(payload)
            line_count += 1
            byte_count += len(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "bytes": byte_count,
        "lines": line_count,
        "sha256": digest.hexdigest(),
    }


def deterministic_gzip(source: Path, destination: Path) -> None:
    with source.open("rb") as input_handle:
        with destination.open("wb") as output_handle:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=output_handle,
                mtime=0,
            ) as compressed:
                shutil.copyfileobj(
                    input_handle,
                    compressed,
                    length=BUFFER_SIZE,
                )
            output_handle.flush()
            os.fsync(output_handle.fileno())


def decompress_gzip(source: Path, destination: Path) -> None:
    decompress_gzip_limited(
        source,
        destination,
        max_bytes=DEFAULT_MAX_RETAINED_PROOF_BYTES,
    )


def decompress_gzip_limited(
    source: Path,
    destination: Path,
    *,
    max_bytes: int,
) -> None:
    written = 0
    with gzip.open(source, "rb") as input_handle:
        with destination.open("wb") as output_handle:
            while True:
                payload = input_handle.read(BUFFER_SIZE)
                if not payload:
                    break
                written += len(payload)
                if written > max_bytes:
                    raise RuntimeError(
                        "retained proof exceeds decompression limit"
                    )
                output_handle.write(payload)
            output_handle.flush()
            os.fsync(output_handle.fileno())


@contextmanager
def materialized_retained_proof(
    proof: Path,
    retained: dict[str, object],
    *,
    scratch_directory: Path,
    max_bytes: int,
):
    if (
        not scratch_directory.is_dir()
        or scratch_directory.is_symlink()
    ):
        raise RuntimeError("proof replay scratch directory is invalid")
    if paths_overlap(scratch_directory, proof.parent):
        raise RuntimeError(
            "proof replay scratch must be outside retained artifacts"
        )
    proof_payload, proof_sha256 = load_authenticated_bytes(
        proof,
        "retained proof",
    )
    try:
        with owned_temporary_directory(
            scratch_directory,
            prefix=f".{proof.stem}.replay.",
        ) as temporary:
            source_snapshot = write_private_file(
                temporary,
                "retained-proof.drat.gz",
                proof_payload,
            )
            uncompressed = temporary / "proof.drat"
            recompressed = temporary / "recompressed-proof.drat.gz"
            with authenticated_snapshot(
                source_snapshot,
                "retained proof snapshot",
            ) as source_snapshot_path:
                decompress_gzip_limited(
                    source_snapshot_path,
                    uncompressed,
                    max_bytes=max_bytes,
                )
                uncompressed_metrics = file_metrics(uncompressed)
                if (
                    retained.get("uncompressed_bytes")
                    != uncompressed_metrics["bytes"]
                    or retained.get("uncompressed_lines")
                    != uncompressed_metrics["lines"]
                    or retained.get("uncompressed_sha256")
                    != uncompressed_metrics["sha256"]
                ):
                    raise RuntimeError("retained proof content changed")
                deterministic_gzip(uncompressed, recompressed)
                if (
                    file_metrics(recompressed)
                    != file_metrics(source_snapshot_path)
                ):
                    raise RuntimeError(
                        "retained gzip encoding is not canonical"
                    )
            yield uncompressed, uncompressed_metrics
            if (
                authenticated_file_sha256(proof, "retained proof")
                != proof_sha256
            ):
                raise RuntimeError(
                    "retained proof changed during materialization"
                )
    except (EOFError, OSError) as exc:
        raise RuntimeError("retained proof gzip stream is invalid") from exc


def apply_file_size_limit(max_file_bytes: int) -> None:
    if type(max_file_bytes) is not int or max_file_bytes <= 0:
        raise RuntimeError("file-size limit is invalid")
    _soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    if hard != resource.RLIM_INFINITY and hard < max_file_bytes:
        raise RuntimeError(
            "hard file-size limit is below the requested limit"
        )
    resource.setrlimit(
        resource.RLIMIT_FSIZE,
        (max_file_bytes, max_file_bytes),
    )


def peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


class MemoryWatchdog:
    def __init__(self, max_bytes: int) -> None:
        if type(max_bytes) is not int or max_bytes <= 0:
            raise RuntimeError("memory limit is invalid")
        self.max_bytes = max_bytes
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="proof-memory-watchdog",
            daemon=True,
        )

    def _run(self) -> None:
        while not self._stop.wait(0.1):
            if peak_rss_bytes() > self.max_bytes:
                os._exit(97)

    def __enter__(self) -> MemoryWatchdog:
        if peak_rss_bytes() > self.max_bytes:
            raise RuntimeError("process already exceeds memory limit")
        self._thread.start()
        return self

    def __exit__(self, *_exc_info) -> None:
        self._stop.set()
        self._thread.join()


def read_dimacs_header(path: Path) -> tuple[int, int]:
    with path.open("r", encoding="ascii") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("c"):
                continue
            fields = stripped.split()
            if len(fields) != 4 or fields[:2] != ["p", "cnf"]:
                raise RuntimeError("formula has an invalid DIMACS header")
            return int(fields[2]), int(fields[3])
    raise RuntimeError("formula has no DIMACS header")


def validate_outputs(
    proof_output: Path,
    summary_output: Path,
    *,
    root: Path,
    verify_existing: bool,
) -> tuple[Path, Path]:
    proof = repository_path(proof_output, root)
    summary = repository_path(summary_output, root)
    if proof == summary:
        raise RuntimeError("proof and summary outputs must be distinct")
    if verify_existing:
        require_regular_single_link(proof, "retained proof")
        require_regular_single_link(summary, "retained proof summary")
    elif (
        proof.exists()
        or proof.is_symlink()
        or summary.exists()
        or summary.is_symlink()
    ):
        raise RuntimeError("proof outputs already exist")
    return proof, summary


def build_proof(
    formula_path: Path,
    proof_output: Path,
    summary_output: Path,
    *,
    case_id: str,
    solver_name: str,
    checker_path: Path,
    checker_commit: str,
    root: Path,
    max_solve_seconds: int = DEFAULT_MAX_SOLVE_SECONDS,
    max_raw_proof_bytes: int = DEFAULT_MAX_RAW_PROOF_BYTES,
    max_retained_proof_bytes: int = DEFAULT_MAX_RETAINED_PROOF_BYTES,
    max_memory_bytes: int = DEFAULT_MAX_MEMORY_BYTES,
) -> dict[str, object]:
    formula = repository_path(formula_path, root)
    require_regular_single_link(formula, "case formula")
    proof, summary = validate_outputs(
        proof_output,
        summary_output,
        root=root,
        verify_existing=False,
    )
    proof.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    if proof.parent != summary.parent:
        raise RuntimeError("proof and summary must share a directory")
    checker = repository_path(checker_path, root)
    checker_payload, checker_sha256 = validate_checker(
        checker,
        checker_commit,
        root=root,
    )
    formula_payload, formula_sha256 = load_authenticated_bytes(
        formula,
        "case formula",
    )
    if (
        type(max_solve_seconds) is not int
        or max_solve_seconds <= 0
        or type(max_raw_proof_bytes) is not int
        or max_raw_proof_bytes <= 0
        or type(max_retained_proof_bytes) is not int
        or max_retained_proof_bytes <= 0
    ):
        raise RuntimeError("proof resource limits are invalid")
    apply_file_size_limit(max_raw_proof_bytes)

    try:
        import pysat
        from pysat.formula import CNF
        from pysat.solvers import Solver
    except ImportError as exc:
        raise RuntimeError("python-sat is required") from exc

    proof_identity = None
    summary_identity = None
    try:
        with MemoryWatchdog(max_memory_bytes):
            with owned_temporary_directory(
                proof.parent,
                prefix=f".{proof.stem}.",
            ) as temporary:
                formula_snapshot = write_private_file(
                    temporary,
                    "formula.cnf",
                    formula_payload,
                )
                checker_snapshot = write_private_file(
                    temporary,
                    "drat-trim",
                    checker_payload,
                    executable=True,
                )
                raw_proof = temporary / "solver.drat"
                trimmed_proof = temporary / "trimmed.drat"
                compressed_proof = temporary / proof.name

                with authenticated_snapshot(
                    formula_snapshot,
                    "case formula snapshot",
                ) as formula_snapshot_path:
                    parsed_formula = CNF(
                        from_file=str(formula_snapshot_path)
                    )
                variables = parsed_formula.nv
                clauses = len(parsed_formula.clauses)
                with Solver(
                    name=solver_name,
                    bootstrap_with=parsed_formula.clauses,
                    with_proof=True,
                ) as solver:
                    del parsed_formula
                    timer = threading.Timer(
                        max_solve_seconds,
                        solver.interrupt,
                    )
                    timer.start()
                    try:
                        result = solver.solve_limited(
                            expect_interrupt=True
                        )
                    finally:
                        timer.cancel()
                        timer.join()
                        solver.clear_interrupt()
                    if result is None:
                        raise RuntimeError(
                            "case solve exceeded time limit"
                        )
                    proof_lines = solver.get_proof()
                if result is not False:
                    raise RuntimeError("case formula did not solve as UNSAT")
                if not proof_lines:
                    raise RuntimeError(
                        "solver did not return a proof trace"
                    )
                raw_metrics = write_solver_proof(
                    proof_lines,
                    raw_proof,
                    max_bytes=max_raw_proof_bytes,
                )
                del proof_lines

                with authenticated_snapshots(
                    (checker_snapshot, "proof checker snapshot"),
                    (formula_snapshot, "case formula snapshot"),
                ) as (
                    checker_snapshot_path,
                    formula_snapshot_path,
                ):
                    extraction_check = run_checker(
                        checker_snapshot_path,
                        formula_snapshot_path,
                        raw_proof,
                        lemma_output=trimmed_proof,
                    )
                require_regular_single_link(
                    trimmed_proof,
                    "trimmed proof",
                )
                trimmed_metrics = file_metrics(trimmed_proof)
                if (
                    int(trimmed_metrics["bytes"]) <= 0
                    or int(trimmed_metrics["bytes"])
                    > max_retained_proof_bytes
                ):
                    raise RuntimeError("trimmed proof size is invalid")
                with authenticated_snapshots(
                    (checker_snapshot, "proof checker snapshot"),
                    (formula_snapshot, "case formula snapshot"),
                ) as (
                    checker_snapshot_path,
                    formula_snapshot_path,
                ):
                    replay_check = run_checker(
                        checker_snapshot_path,
                        formula_snapshot_path,
                        trimmed_proof,
                    )
                deterministic_gzip(trimmed_proof, compressed_proof)
                compressed_metrics = file_metrics(compressed_proof)
                if (
                    int(compressed_metrics["bytes"])
                    > max_retained_proof_bytes
                ):
                    raise RuntimeError(
                        "compressed proof exceeds size limit"
                    )

                record = {
                    "record_type": "solver-generated-drat-core-proof",
                    "schema_version": 2,
                    "case_id": case_id,
                    "status": "UNSAT",
                    "case_formula_sha256": formula_sha256,
                    "variables": variables,
                    "clauses": clauses,
                    "production": {
                        "solver": solver_name,
                        "python_sat_version": pysat.__version__,
                        "solver_output": "text DRAT",
                        "core_extractor": "drat-trim",
                        "core_extractor_mode": "-l",
                        "checker_commit": checker_commit,
                        "checker_binary_sha256": checker_sha256,
                    },
                    "resource_limits": {
                        "solve_seconds": max_solve_seconds,
                        "raw_proof_bytes": max_raw_proof_bytes,
                        "retained_proof_bytes": (
                            max_retained_proof_bytes
                        ),
                        "memory_watchdog_bytes": max_memory_bytes,
                        "checker_seconds": DEFAULT_MAX_CHECKER_SECONDS,
                        "checker_output_bytes": (
                            DEFAULT_MAX_CHECKER_OUTPUT_BYTES
                        ),
                    },
                    "raw_solver_proof": {
                        "retained": False,
                        "format": "text DRAT",
                        **raw_metrics,
                    },
                    "core_extraction_check": extraction_check,
                    "retained_proof": {
                        "filename": proof.name,
                        "format": "text DRAT",
                        "strategy": "drat-trim core lemmas",
                        "compression": "gzip",
                        "uncompressed_bytes": trimmed_metrics["bytes"],
                        "uncompressed_lines": trimmed_metrics["lines"],
                        "uncompressed_sha256": (
                            trimmed_metrics["sha256"]
                        ),
                        "compressed_bytes": (
                            compressed_metrics["bytes"]
                        ),
                        "compressed_sha256": (
                            compressed_metrics["sha256"]
                        ),
                    },
                    "retained_replay": {
                        "checker": "drat-trim",
                        "checker_commit": checker_commit,
                        "checker_binary_sha256": checker_sha256,
                        **replay_check,
                    },
                }
                if (
                    authenticated_file_sha256(formula, "case formula")
                    != formula_sha256
                    or authenticated_file_sha256(
                        checker,
                        "proof checker",
                    )
                    != checker_sha256
                ):
                    raise RuntimeError(
                        "proof inputs changed during certificate production"
                    )
                staged_summary = temporary / summary.name
                staged_summary_identity = atomic_write_json(
                    staged_summary,
                    record,
                )
                compressed_proof_identity = artifact_path_identity(
                    compressed_proof,
                    directory=False,
                )
                compressed_proof_version = authenticated_file_version(
                    compressed_proof,
                    "compressed proof staging",
                )
                staged_summary_version = authenticated_file_version(
                    staged_summary,
                    "proof summary staging",
                )
                try:
                    proof_identity = durable_publish_noreplace(
                        compressed_proof,
                        proof,
                        directory=False,
                        expected_source_identity=(
                            compressed_proof_identity
                        ),
                        expected_source_version=(
                            compressed_proof_version
                        ),
                    )
                except PublicationCommittedError as committed:
                    proof_identity = committed.destination_identity
                    raise
                try:
                    summary_identity = durable_publish_noreplace(
                        staged_summary,
                        summary,
                        directory=False,
                        expected_source_identity=(
                            staged_summary_identity
                        ),
                        expected_source_version=staged_summary_version,
                    )
                except PublicationCommittedError as committed:
                    summary_identity = committed.destination_identity
                    raise
    except BaseException as error:
        cleanup_succeeded = True
        if summary_identity is not None:
            cleanup_succeeded = quarantine_owned_path(
                summary,
                summary_identity,
                directory=False,
            )
        if proof_identity is not None:
            cleanup_succeeded = (
                quarantine_owned_path(
                    proof,
                    proof_identity,
                    directory=False,
                )
                and cleanup_succeeded
            )
        if not cleanup_succeeded:
            raise RuntimeError(
                "proof output rollback could not safely remove outputs"
            ) from error
        raise
    return record


def verify_existing(
    formula_path: Path,
    proof_output: Path,
    summary_output: Path,
    *,
    case_id: str,
    checker_path: Path,
    checker_commit: str,
    root: Path,
    scratch_directory: Path,
    max_solve_seconds: int = DEFAULT_MAX_SOLVE_SECONDS,
    max_raw_proof_bytes: int = DEFAULT_MAX_RAW_PROOF_BYTES,
    max_retained_proof_bytes: int = DEFAULT_MAX_RETAINED_PROOF_BYTES,
    max_memory_bytes: int = DEFAULT_MAX_MEMORY_BYTES,
) -> dict[str, object]:
    formula = repository_path(formula_path, root)
    require_regular_single_link(formula, "case formula")
    proof, summary = validate_outputs(
        proof_output,
        summary_output,
        root=root,
        verify_existing=True,
    )
    scratch = repository_path(scratch_directory, root)
    checker = repository_path(checker_path, root)
    checker_payload, checker_sha256 = validate_checker(
        checker,
        checker_commit,
        root=root,
    )
    formula_payload, formula_sha256 = load_authenticated_bytes(
        formula,
        "case formula",
    )
    proof_payload, proof_sha256 = load_authenticated_bytes(
        proof,
        "retained proof",
    )
    record, summary_sha256 = load_authenticated_json(
        summary,
        "retained proof summary",
    )
    try:
        import pysat
    except ImportError as exc:
        raise RuntimeError("python-sat is required") from exc
    with owned_temporary_directory(
        scratch,
        prefix=f".{proof.stem}.inputs.",
    ) as snapshots:
        formula_snapshot = write_private_file(
            snapshots,
            "formula.cnf",
            formula_payload,
        )
        checker_snapshot = write_private_file(
            snapshots,
            "drat-trim",
            checker_payload,
            executable=True,
        )
        proof_snapshot = write_private_file(
            snapshots,
            proof.name,
            proof_payload,
        )
        with authenticated_snapshots(
            (formula_snapshot, "case formula snapshot"),
            (proof_snapshot, "retained proof snapshot"),
        ) as (formula_snapshot_path, proof_snapshot_path):
            variables, clauses = read_dimacs_header(
                formula_snapshot_path
            )
            retained, compressed_metrics = (
                validate_proof_summary_record(
                    record,
                    case_id=case_id,
                    formula_sha256=formula_sha256,
                    variables=variables,
                    clauses=clauses,
                    proof_path=proof_snapshot_path,
                    checker_commit=checker_commit,
                    checker_sha256=checker_sha256,
                    python_sat_version=pysat.__version__,
                    max_solve_seconds=max_solve_seconds,
                    max_raw_proof_bytes=max_raw_proof_bytes,
                    max_retained_proof_bytes=(
                        max_retained_proof_bytes
                    ),
                    max_memory_bytes=max_memory_bytes,
                )
            )
        with owned_temporary_directory(
            scratch,
            prefix=f".{proof.stem}.materialize.",
        ) as materialize_root:
            with authenticated_snapshot(
                proof_snapshot,
                "retained proof snapshot",
            ) as proof_snapshot_path:
                with materialized_retained_proof(
                    proof_snapshot_path,
                    retained,
                    scratch_directory=materialize_root,
                    max_bytes=max_retained_proof_bytes,
                ) as (
                    uncompressed,
                    uncompressed_metrics,
                ):
                    with authenticated_snapshots(
                        (
                            checker_snapshot,
                            "proof checker snapshot",
                        ),
                        (
                            formula_snapshot,
                            "case formula snapshot",
                        ),
                    ) as (
                        checker_snapshot_path,
                        formula_snapshot_path,
                    ):
                        replay = run_checker(
                            checker_snapshot_path,
                            formula_snapshot_path,
                            uncompressed,
                        )

    expected_replay = {
        "checker": "drat-trim",
        "checker_commit": checker_commit,
        "checker_binary_sha256": checker_sha256,
        **replay,
    }
    if record.get("retained_replay") != expected_replay:
        raise RuntimeError("retained proof replay metadata is invalid")
    if (
        authenticated_file_sha256(formula, "case formula")
        != formula_sha256
        or authenticated_file_sha256(checker, "proof checker")
        != checker_sha256
        or authenticated_file_sha256(proof, "retained proof")
        != proof_sha256
        or authenticated_file_sha256(summary, "proof summary")
        != summary_sha256
    ):
        raise RuntimeError("proof inputs changed during retained replay")
    return {
        "case_id": case_id,
        "formula_sha256": formula_sha256,
        "proof_compressed_sha256": compressed_metrics["sha256"],
        "proof_uncompressed_sha256": uncompressed_metrics["sha256"],
        "verified": True,
    }
    quarantine_owned_path,
