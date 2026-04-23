from __future__ import annotations

from axor_telemetry.config import TelemetryConfig, TelemetryMode, _replace_section


def test_load_defaults_when_nothing_set(tmp_config_path):
    cfg = TelemetryConfig.load(config_path=tmp_config_path)
    assert cfg.mode is TelemetryMode.OFF
    assert cfg.queue_path.startswith("~") or "/" in cfg.queue_path
    assert cfg.fingerprint_kind == "minhash_v1"


def test_env_overrides_file(tmp_config_path, monkeypatch):
    tmp_config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_config_path.write_text('[telemetry]\nmode = "local"\n', encoding="utf-8")
    monkeypatch.setenv("AXOR_TELEMETRY", "remote")
    cfg = TelemetryConfig.load(config_path=tmp_config_path)
    assert cfg.mode is TelemetryMode.REMOTE


def test_invalid_mode_value_falls_back_to_off(tmp_config_path, monkeypatch):
    monkeypatch.setenv("AXOR_TELEMETRY", "garbage")
    cfg = TelemetryConfig.load(config_path=tmp_config_path)
    assert cfg.mode is TelemetryMode.OFF


def test_write_creates_file_with_telemetry_section(tmp_config_path):
    cfg = TelemetryConfig(mode=TelemetryMode.LOCAL)
    cfg.write(config_path=tmp_config_path)
    text = tmp_config_path.read_text(encoding="utf-8")
    assert "[telemetry]" in text
    assert 'mode = "local"' in text


def test_write_preserves_other_sections(tmp_config_path):
    tmp_config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_config_path.write_text(
        '[auth]\napi_key = "sk-xxx"\n\n[telemetry]\nmode = "off"\n',
        encoding="utf-8",
    )
    cfg = TelemetryConfig(mode=TelemetryMode.LOCAL)
    cfg.write(config_path=tmp_config_path)
    text = tmp_config_path.read_text(encoding="utf-8")
    assert '[auth]' in text
    assert 'api_key = "sk-xxx"' in text
    assert 'mode = "local"' in text


def test_replace_section_adds_when_missing():
    out = _replace_section('[auth]\nkey="x"\n', "telemetry", '[telemetry]\nmode="local"\n')
    assert "[auth]" in out
    assert "[telemetry]" in out
    assert 'mode="local"' in out


def test_escape_toml_handles_quotes_and_backslash(tmp_config_path):
    cfg = TelemetryConfig(
        mode=TelemetryMode.LOCAL,
        queue_path='/tmp/has "quotes"\\and backslash',
    )
    cfg.write(config_path=tmp_config_path)
    text = tmp_config_path.read_text(encoding="utf-8")
    # Round-trip must parse cleanly
    reloaded = TelemetryConfig.load(config_path=tmp_config_path)
    assert reloaded.queue_path == '/tmp/has "quotes"\\and backslash'
