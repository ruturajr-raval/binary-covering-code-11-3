from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from repository_lock import (
    LOCK_FD_ENV,
    LOCK_PATH,
    acquire_repository_lock,
    require_inherited_repository_lock,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_with_repository_lock.py"
ARTIFACTS = ROOT / ".research-artifacts"


class RepositoryLockRunnerTests(unittest.TestCase):
    def test_internal_make_target_requires_inherited_lock(self) -> None:
        environment = dict(os.environ)
        environment.pop(LOCK_FD_ENV, None)
        result = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "prepare-fourth-word-proof-formulas-locked",
                f"PYTHON={sys.executable}",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "an inherited repository lock is required",
            result.stderr,
        )

    @unittest.skipIf(
        LOCK_FD_ENV in os.environ,
        "test requires no outer repository lock",
    )
    def test_unlocked_inherited_descriptor_is_upgraded(self) -> None:
        lock_path = ROOT / LOCK_PATH
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        previous = os.environ.get(LOCK_FD_ENV)
        os.environ[LOCK_FD_ENV] = str(descriptor)
        contender_marker = ARTIFACTS / "upgraded-lock-contender"
        contender_marker.unlink(missing_ok=True)
        try:
            require_inherited_repository_lock(ROOT)
            contender = subprocess.Popen(
                [
                    sys.executable,
                    str(RUNNER),
                    "--",
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path\n"
                        f"Path({str(contender_marker)!r})"
                        ".write_text('entered')\n"
                    ),
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key != LOCK_FD_ENV
                },
            )
            time.sleep(0.2)
            self.assertIsNone(contender.poll())
            self.assertFalse(contender_marker.exists())
        finally:
            os.close(descriptor)
            if previous is None:
                os.environ.pop(LOCK_FD_ENV, None)
            else:
                os.environ[LOCK_FD_ENV] = previous
        contender.wait(timeout=5)
        self.assertEqual(contender.returncode, 0)
        self.assertTrue(contender_marker.exists())
        contender_marker.unlink()

    def test_nested_acquisition_restores_lock_environment(self) -> None:
        previous = os.environ.get(LOCK_FD_ENV)
        outer = acquire_repository_lock(ROOT)
        try:
            outer_descriptor = os.environ[LOCK_FD_ENV]
            nested = acquire_repository_lock(ROOT)
            try:
                self.assertNotEqual(
                    os.environ[LOCK_FD_ENV],
                    outer_descriptor,
                )
            finally:
                nested.close()
            self.assertEqual(os.environ[LOCK_FD_ENV], outer_descriptor)
        finally:
            outer.close()
        self.assertEqual(os.environ.get(LOCK_FD_ENV), previous)

    def test_nested_locks_reject_out_of_order_close(self) -> None:
        previous = os.environ.get(LOCK_FD_ENV)
        outer = acquire_repository_lock(ROOT)
        inner = acquire_repository_lock(ROOT)
        with self.assertRaisesRegex(
            RuntimeError,
            "last-in, first-out",
        ):
            outer.close()
        inner.close()
        outer.close()
        self.assertEqual(os.environ.get(LOCK_FD_ENV), previous)

    def test_child_retains_lock_if_wrapper_is_terminated(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            ready = base / "ready"
            contender_marker = base / "contender"
            child_script = (
                "from pathlib import Path\n"
                "import time\n"
                "import sys\n"
                f"sys.path.insert(0, {str(ROOT / 'tools')!r})\n"
                "from repository_lock import acquire_repository_lock\n"
                f"lock=acquire_repository_lock(Path({str(ROOT)!r}))\n"
                f"Path({str(ready)!r}).write_text('ready')\n"
                "time.sleep(1.5)\n"
            )
            wrapper = subprocess.Popen(
                [
                    sys.executable,
                    str(RUNNER),
                    "--",
                    sys.executable,
                    "-c",
                    child_script,
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            wrapper.terminate()
            wrapper.wait(timeout=5)
            contender = subprocess.Popen(
                [
                    sys.executable,
                    str(RUNNER),
                    "--",
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path\n"
                        f"Path({str(contender_marker)!r})"
                        ".write_text('entered')\n"
                    ),
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.2)
            self.assertIsNone(contender.poll())
            self.assertFalse(contender_marker.exists())
            contender.wait(timeout=5)
            self.assertEqual(contender.returncode, 0)
            self.assertTrue(contender_marker.exists())

    def test_grandchild_retains_inherited_lock(self) -> None:
        ARTIFACTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            base = Path(directory)
            ready = base / "grandchild-ready"
            contender_marker = base / "contender"
            grandchild_script = (
                "from pathlib import Path\n"
                "import time\n"
                f"Path({str(ready)!r}).write_text('ready')\n"
                "time.sleep(1.5)\n"
            )
            child_script = (
                "import subprocess\n"
                "import sys\n"
                f"sys.path.insert(0, {str(ROOT / 'tools')!r})\n"
                "from repository_lock import subprocess_lock_kwargs\n"
                f"subprocess.Popen([{sys.executable!r}, '-c', "
                f"{grandchild_script!r}], "
                "**subprocess_lock_kwargs())\n"
            )
            wrapper = subprocess.Popen(
                [
                    sys.executable,
                    str(RUNNER),
                    "--",
                    sys.executable,
                    "-c",
                    child_script,
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            wrapper.wait(timeout=5)
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            contender = subprocess.Popen(
                [
                    sys.executable,
                    str(RUNNER),
                    "--",
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path\n"
                        f"Path({str(contender_marker)!r})"
                        ".write_text('entered')\n"
                    ),
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.2)
            self.assertIsNone(contender.poll())
            self.assertFalse(contender_marker.exists())
            contender.wait(timeout=5)
            self.assertEqual(contender.returncode, 0)
            self.assertTrue(contender_marker.exists())


if __name__ == "__main__":
    unittest.main()
