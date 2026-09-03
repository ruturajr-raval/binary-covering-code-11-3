#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

from bootstrap_drat_trim import validate_pinned_checkout
from generate_third_word_child_formula import (
    display_path,
)
from repository_lock import (
    acquire_repository_lock,
    subprocess_lock_kwargs,
)


DRAT_TRIM_COMMIT = "2e3b2dc0ecf938addbd779d42877b6ed69d9a985"
DRAT_TRIM_REPOSITORY = "https://github.com/marijnheule/drat-trim.git"
PROOF_BYTES = b"0\n"
PROOF_COMPRESSED = bytes.fromhex(
    "1f8b08000000000002ff33e0020012cd4a7e02000000"
)
FORMULA_DIRECTORY = Path("build/proofs/fourth-word")
PROOF_DIRECTORY = Path("evidence/proofs/fourth-word-rup-v1")
PROOF_INDEX = Path("evidence/fourth-word-rup-proof-index-v1.json")
REPLAY_ATTESTATION = Path(
    "evidence/fourth-word-rup-replay-attestation-v1.json"
)
PROMOTION_JOURNAL = Path(
    "evidence/.fourth-word-rup-promotion-v1.json"
)
PIPELINE_FILES = {
    "bundle_certifier": Path(
        "tools/certify_fourth_word_rup_bundle.py"
    ),
    "certified_revision_manager": Path(
        "tools/manage_fourth_word_rup_revision.py"
    ),
    "lock_assertion": Path("tools/assert_repository_lock.py"),
    "checker_bootstrap": Path("tools/bootstrap_drat_trim.py"),
    "formula_generator": Path("tools/generate_fourth_word_formula.py"),
    "formula_auditor": Path("tools/audit_fourth_word_formula.py"),
    "index_auditor": Path("tools/audit_fourth_word_rup_proofs.py"),
    "manifest_verifier": Path("tools/verify_checksum_manifest.py"),
    "plan_auditor": Path("tools/audit_fourth_word_rup_plan.py"),
    "plan_generator": Path("tools/generate_fourth_word_rup_plan.py"),
    "proof_checker_driver": Path("tools/check_drat_proof.py"),
    "proof_orchestrator": Path("tools/prove_fourth_word_rup_cases.py"),
    "repository_lock": Path("tools/repository_lock.py"),
    "repository_lock_runner": Path(
        "tools/run_with_repository_lock.py"
    ),
    "makefile": Path("Makefile"),
    "proof_requirements": Path("requirements-proof.txt"),
    "replay_requirements": Path("requirements-replay.txt"),
    "sat_requirements": Path("requirements-sat.txt"),
}


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def repository_path(path: Path, root: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    lexical = Path(os.path.abspath(str(candidate)))
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        raise SystemExit(f"path is outside the repository: {path}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SystemExit(f"path contains a symbolic link: {path}")
    return lexical


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bytes_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="ascii"))


def require_regular_single_link(path: Path, description: str) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_nlink != 1
    ):
        raise RuntimeError(
            f"{description} is not a single-link regular file: {path}"
        )


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
        f"{path.relative_to(root)}:{file_sha256(path)}\n"
        for path in sources
    )
    return {
        "roots": ["src", "tools"],
        "file_count": len(sources),
        "sha256": bytes_sha256(payload.encode("ascii")),
    }


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_unlink(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    path.unlink()
    fsync_directory(path.parent)


def durable_replace(source: Path, destination: Path) -> None:
    if source.is_dir() and not source.is_symlink():
        fsync_directory(source)
    os.replace(source, destination)
    fsync_directory(destination.parent)
    if source.parent != destination.parent:
        fsync_directory(source.parent)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        durable_replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            durable_unlink(temporary)


def atomic_write_json(path: Path, record: dict[str, object]) -> None:
    atomic_write_bytes(
        path,
        (
            json.dumps(record, indent=2, sort_keys=True) + "\n"
        ).encode("ascii"),
    )


def run_command(
    arguments: list[str],
    *,
    environment: dict[str, str],
    root: Path,
) -> None:
    result = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
        env=environment,
        **subprocess_lock_kwargs(environment),
    )
    if result.returncode != 0:
        output = result.stdout + result.stderr
        raise RuntimeError(
            "command failed:\n"
            + " ".join(arguments)
            + "\n"
            + output[-12000:]
        )


def command_output(
    arguments: list[str],
    *,
    environment: dict[str, str],
    root: Path,
) -> str:
    result = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
        env=environment,
        **subprocess_lock_kwargs(environment),
    )
    if result.returncode != 0:
        raise RuntimeError(
            "command failed:\n"
            + " ".join(arguments)
            + "\n"
            + result.stdout
            + result.stderr
        )
    return result.stdout.strip()


def branch_slug(branch_id: str) -> str:
    slug = branch_id.replace("::", "--")
    if not slug or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
        for character in slug
    ):
        raise SystemExit(f"branch id is not path-safe: {branch_id}")
    return slug


def shared_proof_summary(
    proof_path: Path,
    *,
    root: Path,
) -> dict[str, object]:
    return {
        "record_type": "shared-empty-clause-rup-proof",
        "schema_version": 1,
        "proof": display_path(proof_path, root),
        "proof_format": "text DRAT",
        "proof_strategy": "empty-clause RUP",
        "proof_compression": "gzip",
        "proof_lines": 1,
        "proof_uncompressed_bytes": len(PROOF_BYTES),
        "proof_uncompressed_sha256": bytes_sha256(PROOF_BYTES),
        "proof_compressed_bytes": len(PROOF_COMPRESSED),
        "proof_compressed_sha256": bytes_sha256(PROOF_COMPRESSED),
    }


def case_proof_summary(
    branch_id: str,
    formula: Path,
    formula_metadata: dict[str, object],
    proof_path: Path,
    *,
    root: Path,
) -> dict[str, object]:
    return {
        "case_id": branch_id,
        "case_formula": display_path(formula, root),
        "case_formula_sha256": formula_metadata["formula_sha256"],
        "variables": formula_metadata["variables"],
        "clauses": formula_metadata["clauses"],
        "solver": "unit propagation",
        "status": "UNSAT",
        "proof_format": "text DRAT",
        "proof_strategy": "empty-clause RUP",
        "proof_compression": "gzip",
        "proof_lines": 1,
        "proof_uncompressed_bytes": len(PROOF_BYTES),
        "proof_uncompressed_sha256": bytes_sha256(PROOF_BYTES),
        "proof_compressed": display_path(proof_path, root),
        "proof_compressed_bytes": len(PROOF_COMPRESSED),
        "proof_compressed_sha256": bytes_sha256(PROOF_COMPRESSED),
        "proof_verification": "recorded in a separate check file",
    }


def compare_json(path: Path, expected: dict[str, object]) -> None:
    require_regular_single_link(path, "retained artifact")
    if load_json(path) != expected:
        raise RuntimeError(f"retained artifact changed: {path}")


def validate_checker(
    checker: Path,
    commit: str,
    *,
    root: Path,
) -> str:
    expected = root / "build/drat-trim-src/drat-trim"
    if checker != expected:
        raise SystemExit(
            "checker must be build/drat-trim-src/drat-trim"
        )
    if commit != DRAT_TRIM_COMMIT:
        raise SystemExit("proof checker commit is not the pinned revision")
    require_regular_single_link(checker, "proof checker")
    if not os.access(checker, os.X_OK):
        raise SystemExit("proof checker is missing or not executable")
    checkout = checker.parent
    validate_pinned_checkout(
        checkout,
        commit,
        allowed_untracked={"drat-trim"},
    )
    return file_sha256(checker)


def validate_check(
    check: dict[str, object],
    *,
    branch_id: str,
    formula_sha256: str,
    checker_commit: str,
) -> None:
    expected = {
        "case_id": branch_id,
        "checker": "drat-trim",
        "checker_commit": checker_commit,
        "formula_sha256": formula_sha256,
        "proof_compressed_sha256": bytes_sha256(PROOF_COMPRESSED),
        "proof_uncompressed_sha256": bytes_sha256(PROOF_BYTES),
        "return_code": 0,
        "verified": True,
        "checker_timing_normalized": True,
    }
    for key, value in expected.items():
        if check.get(key) != value:
            raise RuntimeError(
                f"{branch_id}: proof-check field {key} is incorrect"
            )
    output = check.get("checker_output")
    if not isinstance(output, list) or "s VERIFIED" not in output:
        raise RuntimeError(f"{branch_id}: checker output is not verified")
    if not any(
        marker in str(line)
        for line in output
        for marker in (
            "UNSAT via unit propagation",
            "detected empty clause",
        )
    ):
        raise RuntimeError(
            f"{branch_id}: checker did not verify by unit propagation"
        )
    stable_output = "\n".join(str(line) for line in output) + "\n"
    if check.get("checker_output_sha256") != bytes_sha256(
        stable_output.encode("utf-8")
    ):
        raise RuntimeError(
            f"{branch_id}: checker output digest is incorrect"
        )


def expected_artifact_names(
    cases: list[dict[str, object]],
) -> set[str]:
    slugs = [
        branch_slug(str(case["branch_id"]))
        for case in cases
    ]
    if len(set(slugs)) != len(slugs):
        raise SystemExit("proof-plan branch slugs are not unique")
    names = {
        "empty-clause-rup.drat.gz",
        "empty-clause-rup.json",
    }
    for slug in slugs:
        names.update(
            {
                f"{slug}-formula.json",
                f"{slug}-proof.json",
                f"{slug}-check.json",
            }
        )
    return names


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


def interpreter_path_record(
    resolved_command: str,
    *,
    root: Path,
) -> dict[str, str]:
    path = Path(os.path.abspath(resolved_command))
    try:
        relative = path.relative_to(root)
    except ValueError:
        return {
            "scope": "absolute-path-sha256",
            "value": bytes_sha256(str(path).encode("utf-8")),
        }
    return {
        "scope": "repository-relative",
        "value": relative.as_posix(),
    }


def resolve_interpreter(
    python_command: str,
    *,
    environment: dict[str, str],
    root: Path,
) -> str:
    resolved_command = shutil.which(
        python_command,
        path=environment.get("PATH"),
    )
    if resolved_command is None:
        candidate = Path(python_command)
        if not candidate.is_absolute():
            candidate = root / candidate
        if candidate.exists():
            resolved_command = str(candidate)
    if resolved_command is None:
        raise SystemExit(f"Python interpreter is unavailable: {python_command}")
    resolved_path = Path(resolved_command)
    if not resolved_path.is_absolute():
        resolved_path = root / resolved_path
    resolved_path = Path(os.path.abspath(str(resolved_path)))
    parent_path = Path(os.path.abspath(sys.executable))
    try:
        matches_parent = os.path.samefile(
            resolved_path,
            parent_path,
        )
    except OSError as exc:
        raise SystemExit("Python interpreter identity cannot be checked") from exc
    if resolved_path != parent_path or not matches_parent:
        raise SystemExit(
            "--python must identify the interpreter running this process"
        )
    return str(resolved_path)


def measure_interpreter(
    python_command: str,
    *,
    environment: dict[str, str],
    root: Path,
) -> dict[str, object]:
    resolved_command = resolve_interpreter(
        python_command,
        environment=environment,
        root=root,
    )
    probe = (
        "import hashlib,importlib.metadata,json,platform,stat,sys\n"
        "from pathlib import Path\n"
        "import pycard,pyformula,pysat,pysolvers\n"
        "package_root=Path(pysat.__file__).parent\n"
        "package_root_metadata=package_root.lstat()\n"
        "if not stat.S_ISDIR(package_root_metadata.st_mode) "
        "or stat.S_ISLNK(package_root_metadata.st_mode):\n"
        " raise RuntimeError('python-sat package root is invalid')\n"
        "package_entries=[]\n"
        "for package_path in sorted(package_root.rglob('*')):\n"
        " relative=package_path.relative_to(package_root)\n"
        " if '__pycache__' in relative.parts or package_path.suffix "
        "in {'.pyc','.pyo'}:\n"
        "  continue\n"
        " metadata=package_path.lstat()\n"
        " if stat.S_ISLNK(metadata.st_mode):\n"
        "  raise RuntimeError('python-sat package contains a symlink')\n"
        " if stat.S_ISDIR(metadata.st_mode):\n"
        "  continue\n"
        " if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:\n"
        "  raise RuntimeError('python-sat package file is invalid')\n"
        " package_entries.append((relative.as_posix(),hashlib.sha256("
        "package_path.read_bytes()).hexdigest()))\n"
        "package_payload=''.join("
        "f'{name}:{digest}\\n' for name,digest in package_entries"
        ").encode('ascii')\n"
        "native_modules={}\n"
        "for native_module in (pycard,pyformula,pysolvers):\n"
        " native_path=Path(native_module.__file__)\n"
        " native_metadata=native_path.lstat()\n"
        " if native_path.parent != package_root.parent:\n"
        "  raise RuntimeError('python-sat native module path is invalid')\n"
        " if stat.S_ISLNK(native_metadata.st_mode) "
        "or not stat.S_ISREG(native_metadata.st_mode) "
        "or native_metadata.st_nlink != 1:\n"
        "  raise RuntimeError('python-sat native module is invalid')\n"
        " native_modules[native_module.__name__]={\n"
        "  'filename':native_path.name,\n"
        "  'sha256':hashlib.sha256("
        "native_path.read_bytes()).hexdigest(),\n"
        " }\n"
        "payload={\n"
        "'python_implementation':platform.python_implementation(),\n"
        "'python_version':platform.python_version(),\n"
        "'python_executable_sha256':hashlib.sha256("
        "Path(sys.executable).read_bytes()).hexdigest(),\n"
        "'python_sat_version':pysat.__version__,\n"
        "'python_sat_distribution_version':"
        "importlib.metadata.version('python-sat'),\n"
        "'python_sat_tree':{\n"
        " 'root':'pysat',\n"
        " 'file_count':len(package_entries),\n"
        " 'sha256':hashlib.sha256(package_payload).hexdigest(),\n"
        "},\n"
        "'python_sat_native_modules':native_modules,\n"
        "'platform_system':platform.system(),\n"
        "'platform_machine':platform.machine(),\n"
        "}\n"
        "print(json.dumps(payload,sort_keys=True))\n"
    )
    try:
        record = json.loads(
            command_output(
                [resolved_command, "-c", probe],
                environment=environment,
                root=root,
            )
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Python interpreter probe returned invalid JSON"
        ) from exc
    if not isinstance(record, dict):
        raise RuntimeError("Python interpreter probe schema is incorrect")
    record["python_executable_path"] = interpreter_path_record(
        resolved_command,
        root=root,
    )
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
    if not isinstance(record, dict) or set(record) != expected_keys:
        raise RuntimeError("Python interpreter probe schema is incorrect")
    require_sha256(
        record["python_executable_sha256"],
        "Python executable hash",
    )
    executable_path = record["python_executable_path"]
    if (
        not isinstance(executable_path, dict)
        or set(executable_path) != {"scope", "value"}
        or executable_path["scope"]
        not in {"repository-relative", "absolute-path-sha256"}
        or not isinstance(executable_path["value"], str)
        or not executable_path["value"]
    ):
        raise RuntimeError("Python executable path record is incorrect")
    if executable_path["scope"] == "absolute-path-sha256":
        require_sha256(
            executable_path["value"],
            "Python executable path hash",
        )
    else:
        relative_path = Path(executable_path["value"])
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path.as_posix() != executable_path["value"]
        ):
            raise RuntimeError(
                "Python executable repository path is incorrect"
            )
    python_sat_tree = record["python_sat_tree"]
    if (
        not isinstance(python_sat_tree, dict)
        or set(python_sat_tree) != {"root", "file_count", "sha256"}
        or python_sat_tree["root"] != "pysat"
        or type(python_sat_tree["file_count"]) is not int
        or python_sat_tree["file_count"] <= 0
    ):
        raise RuntimeError("python-sat package-tree record is incorrect")
    require_sha256(
        python_sat_tree["sha256"],
        "python-sat package-tree hash",
    )
    native_modules = record["python_sat_native_modules"]
    if (
        not isinstance(native_modules, dict)
        or set(native_modules) != {"pycard", "pyformula", "pysolvers"}
    ):
        raise RuntimeError("python-sat native-module record is incorrect")
    for name, native_record in native_modules.items():
        if (
            not isinstance(native_record, dict)
            or set(native_record) != {"filename", "sha256"}
            or not isinstance(native_record["filename"], str)
            or not native_record["filename"]
        ):
            raise RuntimeError(
                f"python-sat native-module record is incorrect: {name}"
            )
        require_sha256(
            native_record["sha256"],
            f"python-sat native-module hash for {name}",
        )
    if any(
        not isinstance(record[key], str) or not record[key]
        for key in expected_keys
        - {
            "python_executable_sha256",
            "python_executable_path",
            "python_sat_tree",
            "python_sat_native_modules",
        }
    ):
        raise RuntimeError("Python interpreter probe contains empty fields")
    if (
        record["python_sat_distribution_version"]
        != record["python_sat_version"]
    ):
        raise RuntimeError("python-sat module and distribution versions differ")
    return record


def directory_sha256(directory: Path) -> str:
    if not directory.is_dir() or directory.is_symlink():
        raise RuntimeError(f"proof artifact directory is invalid: {directory}")
    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    payload = bytearray()
    for entry in entries:
        require_regular_single_link(entry, "proof artifact")
        payload.extend(entry.name.encode("ascii"))
        payload.extend(b":")
        payload.extend(file_sha256(entry).encode("ascii"))
        payload.extend(b"\n")
    return bytes_sha256(bytes(payload))


def promotion_paths(
    record: dict[str, object],
    *,
    root: Path,
    proof_directory: Path,
    output_path: Path,
) -> tuple[Path, Path]:
    if (
        record["proof_directory"]
        != display_path(proof_directory, root)
        or record["output"] != display_path(output_path, root)
    ):
        raise RuntimeError("promotion journal destinations are invalid")
    staging_directory = repository_path(
        Path(str(record["staging_directory"])),
        root,
    )
    staged_index = repository_path(
        Path(str(record["staged_index"])),
        root,
    )
    if (
        staging_directory.parent != proof_directory.parent
        or not staging_directory.name.startswith(
            f".{proof_directory.name}."
        )
        or staged_index.parent != output_path.parent
        or not staged_index.name.startswith(f".{output_path.name}.")
    ):
        raise RuntimeError("promotion journal staging paths are invalid")
    return staging_directory, staged_index


def begin_promotion_build(
    *,
    root: Path,
    proof_directory: Path,
    output_path: Path,
    staging_directory: Path,
    staged_index: Path,
    journal_path: Path,
) -> None:
    if journal_path.exists() or journal_path.is_symlink():
        raise RuntimeError("promotion journal already exists")
    atomic_write_json(
        journal_path,
        {
            "record_type": "fourth-word-rup-promotion",
            "schema_version": 2,
            "phase": "building",
            "proof_directory": display_path(proof_directory, root),
            "output": display_path(output_path, root),
            "staging_directory": display_path(staging_directory, root),
            "staged_index": display_path(staged_index, root),
        },
    )


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
    record = load_json(journal_path)
    base_keys = {
        "record_type",
        "schema_version",
        "phase",
        "proof_directory",
        "output",
        "staging_directory",
        "staged_index",
    }
    if (
        record.get("record_type") != "fourth-word-rup-promotion"
        or record.get("schema_version") != 2
        or record.get("phase") not in {"building", "ready"}
    ):
        raise RuntimeError("promotion journal is invalid")
    staging_directory, staged_index = promotion_paths(
        record,
        root=root,
        proof_directory=proof_directory,
        output_path=output_path,
    )
    if record["phase"] == "building":
        if set(record) != base_keys:
            raise RuntimeError("building promotion journal is invalid")
        if (
            proof_directory.exists()
            or proof_directory.is_symlink()
            or output_path.exists()
            or output_path.is_symlink()
        ):
            raise RuntimeError(
                "building promotion journal conflicts with final artifacts"
            )
        if staging_directory.exists() or staging_directory.is_symlink():
            if (
                not staging_directory.is_dir()
                or staging_directory.is_symlink()
            ):
                raise RuntimeError(
                    "building promotion staging directory is invalid"
                )
            shutil.rmtree(staging_directory)
            fsync_directory(staging_directory.parent)
        if staged_index.exists() or staged_index.is_symlink():
            require_regular_single_link(
                staged_index,
                "building staged proof index",
            )
            durable_unlink(staged_index)
        durable_unlink(journal_path)
        return "building-cleared"
    expected_keys = base_keys | {
        "proof_directory_sha256",
        "output_sha256",
    }
    if set(record) != expected_keys:
        raise RuntimeError("ready promotion journal is invalid")
    expected_directory_sha256 = require_sha256(
        record["proof_directory_sha256"],
        "promotion proof-directory hash",
    )
    expected_output_sha256 = require_sha256(
        record["output_sha256"],
        "promotion index hash",
    )
    if proof_directory.exists() or proof_directory.is_symlink():
        if staging_directory.exists() or staging_directory.is_symlink():
            raise RuntimeError(
                "promotion has both staged and final proof directories"
            )
        if directory_sha256(proof_directory) != expected_directory_sha256:
            raise RuntimeError("promoted proof directory hash is incorrect")
    else:
        if (
            not staging_directory.is_dir()
            or staging_directory.is_symlink()
        ):
            raise RuntimeError("promotion staging directory is missing")
        if directory_sha256(staging_directory) != expected_directory_sha256:
            raise RuntimeError("staged proof directory hash is incorrect")
        durable_replace(staging_directory, proof_directory)
    if output_path.exists() or output_path.is_symlink():
        require_regular_single_link(output_path, "promoted proof index")
        if file_sha256(output_path) != expected_output_sha256:
            raise RuntimeError("promoted proof index hash is incorrect")
    else:
        require_regular_single_link(staged_index, "staged proof index")
        if file_sha256(staged_index) != expected_output_sha256:
            raise RuntimeError("staged proof index hash is incorrect")
        atomic_write_bytes(output_path, staged_index.read_bytes())
    if directory_sha256(proof_directory) != expected_directory_sha256:
        raise RuntimeError("final proof directory hash is incorrect")
    if file_sha256(output_path) != expected_output_sha256:
        raise RuntimeError("final proof index hash is incorrect")
    durable_unlink(staged_index)
    durable_unlink(journal_path)
    return "ready-completed"


def promote_bundle(
    staging_directory: Path,
    proof_directory: Path,
    staged_index: Path,
    output_path: Path,
    journal_path: Path,
    expected_directory_sha256: str,
    expected_output_sha256: str,
    *,
    root: Path,
) -> None:
    require_regular_single_link(staged_index, "staged proof index")
    require_sha256(
        expected_directory_sha256,
        "audited proof-directory hash",
    )
    require_sha256(expected_output_sha256, "audited proof-index hash")
    if directory_sha256(staging_directory) != expected_directory_sha256:
        raise RuntimeError("staged proof directory changed after audit")
    if file_sha256(staged_index) != expected_output_sha256:
        raise RuntimeError("staged proof index changed after audit")
    fsync_directory(staging_directory)
    fsync_directory(staging_directory.parent)
    journal_record = {
        "record_type": "fourth-word-rup-promotion",
        "schema_version": 2,
        "phase": "ready",
        "proof_directory": display_path(proof_directory, root),
        "proof_directory_sha256": expected_directory_sha256,
        "output": display_path(output_path, root),
        "output_sha256": expected_output_sha256,
        "staging_directory": display_path(staging_directory, root),
        "staged_index": display_path(staged_index, root),
    }
    atomic_write_json(journal_path, journal_record)
    outcome = recover_promotion(
        root=root,
        proof_directory=proof_directory,
        output_path=output_path,
        journal_path=journal_path,
    )
    if outcome != "ready-completed":
        raise RuntimeError("proof promotion did not complete")


def parse_iso_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit("attestation date must use YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise SystemExit("attestation date must use YYYY-MM-DD")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("child_frontier", type=Path)
    parser.add_argument("fourth_frontier", type=Path)
    parser.add_argument("classification", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("formula_directory", type=Path)
    parser.add_argument("proof_directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--checker-commit", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--attestation-output", type=Path)
    parser.add_argument("--attestation-date")
    args = parser.parse_args()

    try:
        import pysat
    except ImportError as exc:
        raise SystemExit(
            "python-sat is required; install requirements-sat.txt"
        ) from exc

    root = repository_root()
    repository_lock = acquire_repository_lock(root)
    atexit.register(repository_lock.close)
    if bool(args.attestation_output) != bool(args.attestation_date):
        raise SystemExit(
            "attestation output and date must be provided together"
        )
    if args.attestation_output and not args.verify_existing:
        raise SystemExit(
            "a replay attestation requires --verify-existing"
        )
    source_paths = {
        "parent_manifest": repository_path(
            args.parent_manifest,
            root,
        ),
        "third_word_manifest": repository_path(
            args.third_word_manifest,
            root,
        ),
        "child_frontier": repository_path(
            args.child_frontier,
            root,
        ),
        "fourth_frontier": repository_path(
            args.fourth_frontier,
            root,
        ),
    }
    classification_path = repository_path(
        args.classification,
        root,
    )
    plan_path = repository_path(args.plan, root)
    formula_directory = repository_path(
        args.formula_directory,
        root,
    )
    proof_directory = repository_path(
        args.proof_directory,
        root,
    )
    output_path = repository_path(args.output, root)
    checker_path = repository_path(args.checker, root)
    attestation_path = (
        repository_path(args.attestation_output, root)
        if args.attestation_output
        else None
    )
    journal_path = repository_path(PROMOTION_JOURNAL, root)

    if formula_directory != root / FORMULA_DIRECTORY:
        raise SystemExit("formula directory is not the canonical path")
    if proof_directory != root / PROOF_DIRECTORY:
        raise SystemExit("proof directory is not the canonical path")
    if output_path != root / PROOF_INDEX:
        raise SystemExit("proof index is not the canonical path")
    if (
        attestation_path is not None
        and attestation_path != root / REPLAY_ATTESTATION
    ):
        raise SystemExit("replay attestation is not the canonical path")
    if attestation_path is not None and (
        attestation_path.exists() or attestation_path.is_symlink()
    ):
        raise SystemExit("replay attestation already exists")
    attestation_date = (
        parse_iso_date(str(args.attestation_date))
        if args.attestation_date
        else None
    )
    recovery_outcome = recover_promotion(
        root=root,
        proof_directory=proof_directory,
        output_path=output_path,
        journal_path=journal_path,
    )
    verify_existing = (
        args.verify_existing
        or recovery_outcome == "ready-completed"
    )
    environment = dict(os.environ)
    existing_python_path = environment.get("PYTHONPATH")
    required_python_path = os.pathsep.join(["src", "tools"])
    environment["PYTHONPATH"] = (
        required_python_path
        if not existing_python_path
        else required_python_path
        + os.pathsep
        + existing_python_path
    )
    python_command = resolve_interpreter(
        args.python,
        environment=environment,
        root=root,
    )
    interpreter = measure_interpreter(
        python_command,
        environment=environment,
        root=root,
    )
    if interpreter["python_sat_version"] != pysat.__version__:
        raise SystemExit(
            "child interpreter python-sat version differs from parent"
        )
    checker_sha256 = validate_checker(
        checker_path,
        args.checker_commit,
        root=root,
    )

    input_paths = {
        *source_paths.values(),
        classification_path,
        plan_path,
    }
    if len(input_paths) != 6:
        raise SystemExit("proof inputs must use distinct files")
    for path in input_paths:
        require_regular_single_link(path, "proof input")
    input_list = list(input_paths)
    if any(
        os.path.samefile(left, right)
        for index, left in enumerate(input_list)
        for right in input_list[index + 1:]
    ):
        raise SystemExit("proof inputs alias the same file")
    if output_path.exists():
        require_regular_single_link(output_path, "proof index output")
    if output_path in input_paths or (
        output_path.exists()
        and any(
            os.path.samefile(output_path, path)
            for path in input_paths
        )
    ):
        raise SystemExit("proof index output aliases an input")

    pipeline_paths = {
        label: repository_path(relative_path, root)
        for label, relative_path in PIPELINE_FILES.items()
    }
    for path in pipeline_paths.values():
        require_regular_single_link(path, "proof-pipeline file")
    pipeline_records = {
        label: {
            "path": display_path(path, root),
            "sha256": file_sha256(path),
        }
        for label, path in pipeline_paths.items()
    }
    pipeline_tree = python_tree_record(root)

    run_command(
        [
            python_command,
            "tools/audit_fourth_word_rup_plan.py",
            display_path(source_paths["parent_manifest"], root),
            display_path(source_paths["third_word_manifest"], root),
            display_path(source_paths["child_frontier"], root),
            display_path(source_paths["fourth_frontier"], root),
            display_path(classification_path, root),
            display_path(plan_path, root),
        ],
        environment=environment,
        root=root,
    )

    source_hashes = {
        label: file_sha256(path)
        for label, path in source_paths.items()
    }
    classification_sha256 = file_sha256(classification_path)
    plan_sha256 = file_sha256(plan_path)
    classification = load_json(classification_path)
    plan = load_json(plan_path)
    if (
        classification["python_sat_version"]
        != interpreter["python_sat_version"]
    ):
        raise SystemExit(
            "installed python-sat version does not match classification"
        )
    retained_sources = {
        label: {
            "path": display_path(path, root),
            "sha256": source_hashes[label],
        }
        for label, path in source_paths.items()
    }
    closed = [
        record
        for record in classification["branches"]
        if record["status"] == "rup-conflict"
    ]
    expected_cases = [
        {
            key: record[key]
            for key in (
                "branch_id",
                "branch_sha256",
                "parent_child_id",
                "fourth_orbit_index",
            )
        }
        for record in closed
    ]
    if len(expected_cases) != 184 or plan["cases"] != expected_cases:
        raise SystemExit("proof plan does not contain the exact 184 cases")
    if int(plan["case_count"]) != len(expected_cases):
        raise SystemExit("proof-plan case count is incorrect")

    formula_directory.mkdir(parents=True, exist_ok=True)
    if not formula_directory.is_dir() or formula_directory.is_symlink():
        raise SystemExit("formula directory is not a regular directory")

    expected_names = expected_artifact_names(expected_cases)
    staging_directory: Path | None = None
    staged_index_path: Path | None = None
    if verify_existing:
        if not proof_directory.is_dir() or proof_directory.is_symlink():
            raise SystemExit("retained proof directory is missing")
        require_regular_single_link(output_path, "retained proof index")
        artifact_directory = proof_directory
    else:
        if proof_directory.exists() or proof_directory.is_symlink():
            raise SystemExit(
                "immutable proof directory already exists; "
                "use --verify-existing"
            )
        if output_path.exists() or output_path.is_symlink():
            raise SystemExit(
                "immutable proof index already exists; "
                "use --verify-existing"
            )
        stale_staging = sorted(
            proof_directory.parent.glob(
                f".{proof_directory.name}.*"
            )
        )
        stale_indexes = sorted(
            output_path.parent.glob(f".{output_path.name}.*.staged")
        )
        if stale_staging or stale_indexes:
            raise SystemExit(
                "stale proof-promotion staging paths require inspection: "
                + ", ".join(
                    display_path(path, root)
                    for path in [*stale_staging, *stale_indexes]
                )
            )
        proof_directory.parent.mkdir(parents=True, exist_ok=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(16)
        staging_directory = proof_directory.parent / (
            f".{proof_directory.name}.{token}"
        )
        staged_index_path = output_path.parent / (
            f".{output_path.name}.{token}.staged"
        )
        if (
            staging_directory.exists()
            or staging_directory.is_symlink()
            or staged_index_path.exists()
            or staged_index_path.is_symlink()
        ):
            raise RuntimeError("generated proof staging paths already exist")

        def cleanup_staging() -> None:
            if journal_path.exists() or journal_path.is_symlink():
                return
            if (
                staging_directory is not None
                and staging_directory.exists()
            ):
                shutil.rmtree(staging_directory)
            if staged_index_path is not None:
                staged_index_path.unlink(missing_ok=True)

        atexit.register(cleanup_staging)
        begin_promotion_build(
            root=root,
            proof_directory=proof_directory,
            output_path=output_path,
            staging_directory=staging_directory,
            staged_index=staged_index_path,
            journal_path=journal_path,
        )
        staging_directory.mkdir(mode=0o700)
        fsync_directory(staging_directory.parent)
        artifact_directory = staging_directory

    actual_entries = list(artifact_directory.iterdir())
    if any(
        not entry.is_file()
        or entry.is_symlink()
        or entry.stat().st_nlink != 1
        for entry in actual_entries
    ):
        raise SystemExit("proof directory contains a non-regular artifact")
    actual_names = {entry.name for entry in actual_entries}
    extra_names = actual_names - expected_names
    if extra_names:
        raise SystemExit(
            "proof directory contains unexpected artifacts: "
            + ", ".join(sorted(extra_names))
        )
    if verify_existing:
        missing_names = expected_names - actual_names
        if missing_names:
            raise SystemExit(
                "proof directory is incomplete: "
                + ", ".join(sorted(missing_names))
            )

    shared_proof = proof_directory / "empty-clause-rup.drat.gz"
    shared_summary_path = proof_directory / "empty-clause-rup.json"
    artifact_shared_proof = (
        artifact_directory / "empty-clause-rup.drat.gz"
    )
    artifact_shared_summary = (
        artifact_directory / "empty-clause-rup.json"
    )
    expected_shared_summary = shared_proof_summary(
        shared_proof,
        root=root,
    )
    if verify_existing:
        if artifact_shared_proof.read_bytes() != PROOF_COMPRESSED:
            raise RuntimeError("shared RUP proof bytes changed")
        compare_json(
            artifact_shared_summary,
            expected_shared_summary,
        )
    else:
        atomic_write_bytes(artifact_shared_proof, PROOF_COMPRESSED)
        atomic_write_json(
            artifact_shared_summary,
            expected_shared_summary,
        )

    records = []
    for index, planned in enumerate(expected_cases, start=1):
        branch_id = str(planned["branch_id"])
        slug = branch_slug(branch_id)
        formula = formula_directory / f"{slug}.cnf"
        retained_metadata = proof_directory / f"{slug}-formula.json"
        retained_summary = proof_directory / f"{slug}-proof.json"
        retained_check = proof_directory / f"{slug}-check.json"
        artifact_metadata = (
            artifact_directory / f"{slug}-formula.json"
        )
        artifact_summary = artifact_directory / f"{slug}-proof.json"
        artifact_check = artifact_directory / f"{slug}-check.json"
        if formula.exists() or formula.is_symlink():
            raise RuntimeError(
                f"{branch_id}: transient formula path already exists"
            )

        try:
            with tempfile.TemporaryDirectory(
                dir=formula_directory,
                prefix=f".{slug}.",
            ) as temporary_name:
                temporary_directory = Path(temporary_name)
                temporary_metadata = (
                    temporary_directory / "formula.json"
                )
                temporary_summary = temporary_directory / "proof.json"
                temporary_check = temporary_directory / "check.json"
                run_command(
                    [
                        python_command,
                        "tools/generate_fourth_word_formula.py",
                        display_path(
                            source_paths["parent_manifest"],
                            root,
                        ),
                        display_path(
                            source_paths["third_word_manifest"],
                            root,
                        ),
                        display_path(
                            source_paths["child_frontier"],
                            root,
                        ),
                        display_path(
                            source_paths["fourth_frontier"],
                            root,
                        ),
                        branch_id,
                        display_path(formula, root),
                        display_path(temporary_metadata, root),
                    ],
                    environment=environment,
                    root=root,
                )
                run_command(
                    [
                        python_command,
                        "tools/audit_fourth_word_formula.py",
                        display_path(formula, root),
                        display_path(temporary_metadata, root),
                    ],
                    environment=environment,
                    root=root,
                )
                metadata = load_json(temporary_metadata)
                require_regular_single_link(
                    formula,
                    "transient fourth-word formula",
                )
                require_regular_single_link(
                    temporary_metadata,
                    "transient formula metadata",
                )
                if metadata["branch_id"] != branch_id:
                    raise RuntimeError(
                        f"{branch_id}: metadata branch mismatch"
                    )
                if (
                    metadata["branch_sha256"]
                    != planned["branch_sha256"]
                ):
                    raise RuntimeError(
                        f"{branch_id}: branch digest mismatch"
                    )
                if (
                    metadata["parent_child_id"]
                    != planned["parent_child_id"]
                    or metadata["fourth_orbit_index"]
                    != planned["fourth_orbit_index"]
                ):
                    raise RuntimeError(
                        f"{branch_id}: formula identity mismatch"
                    )
                if metadata["formula_sha256"] != file_sha256(formula):
                    raise RuntimeError(
                        f"{branch_id}: formula hash mismatch"
                    )
                expected_summary = case_proof_summary(
                    branch_id,
                    formula,
                    metadata,
                    shared_proof,
                    root=root,
                )
                atomic_write_json(
                    temporary_summary,
                    expected_summary,
                )
                run_command(
                    [
                        python_command,
                        "tools/check_drat_proof.py",
                        str(checker_path),
                        display_path(formula, root),
                        display_path(artifact_shared_proof, root),
                        display_path(temporary_summary, root),
                        display_path(temporary_check, root),
                        "--checker-commit",
                        args.checker_commit,
                    ],
                    environment=environment,
                    root=root,
                )
                check = load_json(temporary_check)
                validate_check(
                    check,
                    branch_id=branch_id,
                    formula_sha256=str(metadata["formula_sha256"]),
                    checker_commit=args.checker_commit,
                )

                if verify_existing:
                    compare_json(artifact_metadata, metadata)
                    compare_json(artifact_summary, expected_summary)
                    compare_json(artifact_check, check)
                else:
                    atomic_write_bytes(
                        artifact_metadata,
                        temporary_metadata.read_bytes(),
                    )
                    atomic_write_bytes(
                        artifact_summary,
                        temporary_summary.read_bytes(),
                    )
                    atomic_write_bytes(
                        artifact_check,
                        temporary_check.read_bytes(),
                    )

                records.append(
                    {
                        "branch_id": branch_id,
                        "branch_sha256": planned["branch_sha256"],
                        "parent_child_id": planned["parent_child_id"],
                        "fourth_orbit_index": planned[
                            "fourth_orbit_index"
                        ],
                        "formula": display_path(formula, root),
                        "formula_sha256": metadata["formula_sha256"],
                        "formula_metadata": display_path(
                            retained_metadata,
                            root,
                        ),
                        "formula_metadata_sha256": file_sha256(
                            artifact_metadata
                        ),
                        "variables": metadata["variables"],
                        "clauses": metadata["clauses"],
                        "proof": display_path(shared_proof, root),
                        "proof_sha256": bytes_sha256(PROOF_COMPRESSED),
                        "proof_summary": display_path(
                            retained_summary,
                            root,
                        ),
                        "proof_summary_sha256": file_sha256(
                            artifact_summary
                        ),
                        "proof_check": display_path(
                            retained_check,
                            root,
                        ),
                        "proof_check_sha256": file_sha256(
                            artifact_check
                        ),
                        "verified": True,
                    }
                )
        finally:
            formula.unlink(missing_ok=True)
        print(f"[{index}/{len(expected_cases)}] verified {branch_id}")

    final_entries = list(artifact_directory.iterdir())
    if any(
        not entry.is_file()
        or entry.is_symlink()
        or entry.stat().st_nlink != 1
        for entry in final_entries
    ):
        raise RuntimeError(
            "proof directory contains a non-regular artifact"
        )
    final_names = {entry.name for entry in final_entries}
    if final_names != expected_names:
        missing_names = expected_names - final_names
        extra_names = final_names - expected_names
        raise RuntimeError(
            "fourth-word proof artifact set is incorrect; "
            f"missing={sorted(missing_names)}, "
            f"extra={sorted(extra_names)}"
        )

    index_record = {
        "record_type": "fourth-word-rup-proof-index",
        "schema_version": 3,
        "sources": retained_sources,
        "classification": {
            "path": display_path(classification_path, root),
            "sha256": classification_sha256,
        },
        "proof_plan": {
            "path": display_path(plan_path, root),
            "sha256": plan_sha256,
        },
        "pipeline_files": pipeline_records,
        "pipeline_python_tree": pipeline_tree,
        "formula_directory": display_path(formula_directory, root),
        "formula_files_retained": False,
        "proof_directory": display_path(proof_directory, root),
        "checker": "drat-trim",
        "checker_repository": DRAT_TRIM_REPOSITORY,
        "checker_commit": args.checker_commit,
        "checker_source_validation": (
            "tracked modes and raw bytes matched the pinned Git tree"
        ),
        "certification_scope": {
            "selected_third_word_children": 4,
            "fourth_word_branches": 350,
            "rup_unsat_branches": 184,
            "unresolved_fourth_word_branches": 166,
            "closed_third_word_children": 0,
            "closed_normalized_parents": 0,
        },
        "shared_proof": {
            "path": display_path(shared_proof, root),
            "sha256": bytes_sha256(PROOF_COMPRESSED),
            "summary": display_path(shared_summary_path, root),
            "summary_sha256": file_sha256(
                artifact_shared_summary
            ),
        },
        "case_count": len(records),
        "closed_set_sha256": plan["closed_set_sha256"],
        "residual_set_sha256": plan["residual_set_sha256"],
        "all_verified": all(record["verified"] for record in records),
        "cases": records,
    }

    audited_directory_sha256: str | None = None
    audited_output_sha256: str | None = None
    if not verify_existing:
        if staging_directory is None or staged_index_path is None:
            raise RuntimeError("proof staging paths are missing")
        atomic_write_json(staged_index_path, index_record)
        staged_audit = json.loads(
            command_output(
                [
                    python_command,
                    "tools/audit_fourth_word_rup_proofs.py",
                    display_path(source_paths["parent_manifest"], root),
                    display_path(source_paths["third_word_manifest"], root),
                    display_path(source_paths["child_frontier"], root),
                    display_path(source_paths["fourth_frontier"], root),
                    display_path(classification_path, root),
                    display_path(plan_path, root),
                    display_path(staged_index_path, root),
                    display_path(staging_directory, root),
                    "--staged",
                ],
                environment=environment,
                root=root,
            )
        )
        if (
            staged_audit.get("structurally_valid") is not True
            or int(staged_audit.get("case_count", -1)) != 184
        ):
            raise RuntimeError("staged proof audit did not validate")
        audited_directory_sha256 = require_sha256(
            staged_audit.get("proof_directory_sha256"),
            "staged-audit proof-directory hash",
        )
        audited_output_sha256 = require_sha256(
            staged_audit.get("proof_index_sha256"),
            "staged-audit proof-index hash",
        )
        if (
            directory_sha256(staging_directory)
            != audited_directory_sha256
            or file_sha256(staged_index_path)
            != audited_output_sha256
        ):
            raise RuntimeError("staged proof bundle changed after audit")

    input_hashes = {
        **{
            path: source_hashes[label]
            for label, path in source_paths.items()
        },
        classification_path: classification_sha256,
        plan_path: plan_sha256,
        **{
            path: str(pipeline_records[label]["sha256"])
            for label, path in pipeline_paths.items()
        },
    }
    for path, digest in input_hashes.items():
        if file_sha256(path) != digest:
            raise RuntimeError(
                f"input changed during proof replay: "
                f"{display_path(path, root)}"
            )
    final_checker_sha256 = validate_checker(
        checker_path,
        args.checker_commit,
        root=root,
    )
    if final_checker_sha256 != checker_sha256:
        raise RuntimeError("proof checker binary changed during replay")
    if python_tree_record(root) != pipeline_tree:
        raise RuntimeError(
            "repository Python sources changed during replay"
        )
    if (
        measure_interpreter(
            python_command,
            environment=environment,
            root=root,
        )
        != interpreter
    ):
        raise RuntimeError("Python interpreter changed during proof replay")

    if verify_existing:
        compare_json(output_path, index_record)
        if attestation_path is not None:
            outcome_payload = "".join(
                (
                    f"{record['branch_id']}:"
                    f"{record['formula_sha256']}:"
                    f"{record['proof_check_sha256']}\n"
                )
                for record in records
            ).encode("ascii")
            attestation_record = {
                "record_type": (
                    "fourth-word-rup-replay-attestation"
                ),
                "schema_version": 3,
                "provenance": {
                    "scope": "local self-attestation",
                    "externally_signed": False,
                },
                "replay_date": attestation_date,
                "proof_index": {
                    "path": display_path(output_path, root),
                    "sha256": file_sha256(output_path),
                },
                "checker": {
                    "name": "drat-trim",
                    "repository": DRAT_TRIM_REPOSITORY,
                    "commit": args.checker_commit,
                    "binary_sha256": checker_sha256,
                },
                "pipeline_files": pipeline_records,
                "pipeline_python_tree": pipeline_tree,
                "environment": interpreter,
                "case_count": len(records),
                "case_outcomes_sha256": bytes_sha256(
                    outcome_payload
                ),
                "closed_set_sha256": plan["closed_set_sha256"],
                "residual_set_sha256": plan[
                    "residual_set_sha256"
                ],
                "all_verified": all(
                    record["verified"] for record in records
                ),
            }
            atomic_write_json(attestation_path, attestation_record)
    else:
        if (
            staging_directory is None
            or staged_index_path is None
            or audited_directory_sha256 is None
            or audited_output_sha256 is None
        ):
            raise RuntimeError("proof staging paths are missing")
        promote_bundle(
            staging_directory,
            proof_directory,
            staged_index_path,
            output_path,
            journal_path,
            audited_directory_sha256,
            audited_output_sha256,
            root=root,
        )
    result = {
        "all_verified": index_record["all_verified"],
        "case_count": len(records),
        "output": display_path(output_path, root),
        "promotion_recovery": recovery_outcome,
    }
    if attestation_path is not None:
        result["replay_attestation"] = display_path(
            attestation_path,
            root,
        )
    print(
        json.dumps(result, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
