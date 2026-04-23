from __future__ import annotations

import pytest


@pytest.fixture
def tmp_queue_path(tmp_path):
    return str(tmp_path / "telemetry_queue.jsonl")


@pytest.fixture
def tmp_config_path(tmp_path, monkeypatch):
    """Redirect ~/.axor so CLI tests never touch the real home."""
    monkeypatch.setenv("HOME", str(tmp_path))
    from axor_telemetry import config as cfg_module
    monkeypatch.setattr(cfg_module, "_CONFIG_PATH", tmp_path / ".axor" / "config.toml")
    return tmp_path / ".axor" / "config.toml"
