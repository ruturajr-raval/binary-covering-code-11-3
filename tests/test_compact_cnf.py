from __future__ import annotations

import importlib.util
import itertools
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from covering_code.core import verify_code


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools/generate_compact_cnf.py"
PYSAT_AVAILABLE = importlib.util.find_spec("pysat") is not None


@unittest.skipUnless(PYSAT_AVAILABLE, "python-sat is not installed")
class CompactCnfTests(unittest.TestCase):
    def test_primary_projection_matches_covering_semantics(self) -> None:
        from pysat.formula import CNF
        from pysat.solvers import Solver

        for encoding in ("kmtotalizer", "cardnetwrk"):
            with tempfile.TemporaryDirectory() as directory:
                formula_path = Path(directory) / "formula.cnf"
                metadata_path = Path(directory) / "metadata.json"
                subprocess.run(
                    [
                        sys.executable,
                        str(GENERATOR),
                        str(formula_path),
                        str(metadata_path),
                        "--length",
                        "3",
                        "--radius",
                        "1",
                        "--size",
                        "2",
                        "--encoding",
                        encoding,
                        "--anchor-zero",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                formula = CNF(from_file=str(formula_path))
                with Solver(
                    name="minisat22",
                    bootstrap_with=formula.clauses,
                ) as solver:
                    for size in range(9):
                        for code_tuple in itertools.combinations(
                            range(8),
                            size,
                        ):
                            code = set(code_tuple)
                            assumptions = [
                                word + 1
                                if word in code
                                else -(word + 1)
                                for word in range(8)
                            ]
                            expected = (
                                len(code) <= 2
                                and 0 in code
                                and bool(code)
                                and verify_code(
                                    code,
                                    length=3,
                                    radius=1,
                                ).valid
                            )
                            self.assertEqual(
                                solver.solve(assumptions=assumptions),
                                expected,
                                (encoding, code_tuple),
                            )


if __name__ == "__main__":
    unittest.main()
