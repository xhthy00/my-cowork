import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parent.parent


def test_import_linter_contract():
    """
    Verify that the independent harness and host architecture contract is satisfied.
    This test shells out to `lint-imports` so that import-linter's own
    reporting is used; the exit code is the contract pass/fail signal.
    """
    result = subprocess.run(
        [str(Path(sys.executable).parent / ("lint-imports.exe" if sys.platform == "win32" else "lint-imports"))],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0, f"Import linter contract failed:\n{result.stdout}\n{result.stderr}"
