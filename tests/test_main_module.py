"""Smoke test the python -m axor_telemetry entrypoint."""
from __future__ import annotations

import subprocess
import sys


def test_module_entrypoint_shows_help():
    """`python -m axor_telemetry --help` must exit 0 and mention subcommands."""
    result = subprocess.run(
        [sys.executable, "-m", "axor_telemetry", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "consent" in result.stdout
    assert "preview" in result.stdout


def test_module_entrypoint_status(tmp_path):
    """`python -m axor_telemetry status` runs and prints config summary."""
    env = {
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
    }
    result = subprocess.run(
        [sys.executable, "-m", "axor_telemetry", "status"],
        capture_output=True, text=True, timeout=10, env=env,
    )
    assert result.returncode == 0
    assert "mode:" in result.stdout
