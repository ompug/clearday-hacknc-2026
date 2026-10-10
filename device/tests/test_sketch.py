"""Compile the MCU sketch against host mocks and run its protocol checks (needs g++)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

CHECK = Path(__file__).resolve().parent.parent / "sketch" / "host_check" / "check.sh"


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not installed")
def test_sketch_compiles_and_renders(tmp_path):
    result = subprocess.run(
        ["bash", str(CHECK)], capture_output=True, text=True, env={**os.environ, "TMPDIR": str(tmp_path)}
    )
    assert result.returncode == 0, result.stderr
    assert "sketch host check: OK" in result.stdout
