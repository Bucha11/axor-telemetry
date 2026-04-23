from __future__ import annotations

import io
import json

from axor_telemetry import cli
from axor_telemetry.config import TelemetryConfig, TelemetryMode


def _run(argv, monkeypatch=None):
    stream = io.StringIO()
    # inject stream via dispatch
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    dispatch = {
        "consent": cli.cmd_consent,
        "status":  cli.cmd_status,
        "preview": cli.cmd_preview,
        "on":      cli.cmd_on,
        "off":     cli.cmd_off,
    }
    rc = dispatch[args.cmd](args, stream=stream)
    return rc, stream.getvalue()


def test_on_writes_local_mode(tmp_config_path):
    rc, out = _run(["on"])
    assert rc == 0
    assert "local" in out
    assert TelemetryConfig.load(config_path=tmp_config_path).mode is TelemetryMode.LOCAL


def test_on_remote_flag_writes_remote_mode(tmp_config_path):
    rc, out = _run(["on", "--remote"])
    assert rc == 0
    assert "remote" in out
    assert TelemetryConfig.load(config_path=tmp_config_path).mode is TelemetryMode.REMOTE


def test_off_writes_off_mode(tmp_config_path):
    rc, out = _run(["off"])
    assert rc == 0
    assert TelemetryConfig.load(config_path=tmp_config_path).mode is TelemetryMode.OFF


def test_status_shows_current_config(tmp_config_path):
    TelemetryConfig(mode=TelemetryMode.LOCAL).write(config_path=tmp_config_path)
    rc, out = _run(["status"])
    assert rc == 0
    assert "mode:" in out
    assert "local" in out


def test_preview_empty_when_no_queue(tmp_config_path):
    rc, out = _run(["preview"])
    assert rc == 0
    assert "empty" in out


def test_preview_prints_last_record(tmp_config_path, tmp_path):
    queue = tmp_path / "queue.jsonl"
    rec = {"signal_chosen": "focused_generative", "confidence": 0.9}
    queue.write_text(json.dumps({"a": 1}) + "\n" + json.dumps(rec) + "\n", encoding="utf-8")
    TelemetryConfig(mode=TelemetryMode.LOCAL, queue_path=str(queue)).write(config_path=tmp_config_path)
    rc, out = _run(["preview"])
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["signal_chosen"] == "focused_generative"


def test_consent_local_path(tmp_config_path):
    stream = io.StringIO()
    parser = cli.build_parser()
    args = parser.parse_args(["consent"])
    rc = cli.cmd_consent(args, stream=stream, prompt_input=lambda _: "l")
    assert rc == 0
    assert TelemetryConfig.load(config_path=tmp_config_path).mode is TelemetryMode.LOCAL


def test_consent_off_on_empty_input(tmp_config_path):
    stream = io.StringIO()
    parser = cli.build_parser()
    args = parser.parse_args(["consent"])
    rc = cli.cmd_consent(args, stream=stream, prompt_input=lambda _: "")
    assert rc == 0
    assert TelemetryConfig.load(config_path=tmp_config_path).mode is TelemetryMode.OFF
