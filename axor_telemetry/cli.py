"""
CLI for axor-telemetry: `python -m axor_telemetry <command>`.

Commands:
  consent  — interactive opt-in; writes mode + endpoint to ~/.axor/config.toml
  status   — show current effective config (env + file merged)
  preview  — print the last queued record so the user sees exactly what goes out
  on       — non-interactive: set mode=local
  off      — disable telemetry
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from axor_telemetry.config import TelemetryConfig, TelemetryMode


def cmd_consent(args: argparse.Namespace, stream=sys.stdout, prompt_input=input) -> int:
    current = TelemetryConfig.load()
    stream.write(_consent_text(current))
    stream.flush()
    try:
        answer = prompt_input("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        stream.write("\naborted. no change.\n")
        return 1

    if answer in ("r", "remote"):
        new = TelemetryConfig(mode=TelemetryMode.REMOTE, endpoint=current.endpoint,
                              queue_path=current.queue_path,
                              fingerprint_kind=current.fingerprint_kind)
    elif answer in ("l", "local"):
        new = TelemetryConfig(mode=TelemetryMode.LOCAL, endpoint=current.endpoint,
                              queue_path=current.queue_path,
                              fingerprint_kind=current.fingerprint_kind)
    else:
        new = TelemetryConfig(mode=TelemetryMode.OFF, endpoint=current.endpoint,
                              queue_path=current.queue_path,
                              fingerprint_kind=current.fingerprint_kind)

    path = new.write()
    stream.write(f"saved to {path}: mode={new.mode.value}\n")
    return 0


def cmd_status(args: argparse.Namespace, stream=sys.stdout) -> int:
    cfg = TelemetryConfig.load()
    stream.write(f"mode:             {cfg.mode.value}\n")
    stream.write(f"endpoint:         {cfg.endpoint}\n")
    stream.write(f"queue_path:       {cfg.queue_path}\n")
    stream.write(f"fingerprint_kind: {cfg.fingerprint_kind}\n")
    queue = Path(cfg.queue_path).expanduser()
    if queue.is_file():
        try:
            size = queue.stat().st_size
        except OSError:
            size = 0
        stream.write(f"queue_bytes:      {size}\n")
    return 0


def cmd_preview(args: argparse.Namespace, stream=sys.stdout) -> int:
    cfg = TelemetryConfig.load()
    queue = Path(cfg.queue_path).expanduser()
    if not queue.is_file():
        stream.write("queue is empty (no records have been generated yet).\n")
        return 0
    last = None
    try:
        with queue.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = line
    except OSError as exc:
        stream.write(f"failed to read queue: {exc}\n")
        return 1
    if not last:
        stream.write("queue file exists but is empty.\n")
        return 0
    try:
        record = json.loads(last)
        stream.write(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    except json.JSONDecodeError:
        stream.write(last + "\n")
    return 0


def cmd_on(args: argparse.Namespace, stream=sys.stdout) -> int:
    current = TelemetryConfig.load()
    mode = TelemetryMode.REMOTE if args.remote else TelemetryMode.LOCAL
    new = TelemetryConfig(mode=mode, endpoint=current.endpoint,
                          queue_path=current.queue_path,
                          fingerprint_kind=current.fingerprint_kind)
    path = new.write()
    stream.write(f"telemetry is now {mode.value}. config: {path}\n")
    return 0


def cmd_off(args: argparse.Namespace, stream=sys.stdout) -> int:
    current = TelemetryConfig.load()
    new = TelemetryConfig(mode=TelemetryMode.OFF, endpoint=current.endpoint,
                          queue_path=current.queue_path,
                          fingerprint_kind=current.fingerprint_kind)
    path = new.write()
    stream.write(f"telemetry disabled. config: {path}\n")
    return 0


def _consent_text(current: TelemetryConfig) -> str:
    return (
        "axor telemetry is opt-in. Nothing has been sent yet.\n"
        "\n"
        "What gets collected (when enabled):\n"
        "  - chosen classification (e.g. focused_generative)\n"
        "  - classifier name + confidence\n"
        "  - a 128-int MinHash fingerprint of the raw input (non-reversible)\n"
        "  - tokens spent, whether policy was adjusted mid-run\n"
        "\n"
        "What is NEVER collected:\n"
        "  - raw task text, file contents, tool arguments, secrets\n"
        "  - user/session identifiers\n"
        "\n"
        f"Current mode: {current.mode.value}\n"
        f"Endpoint (remote mode): {current.endpoint}\n"
        "\n"
        "Choose:\n"
        "  [l] local  — write records to a local JSONL queue, never send anywhere\n"
        "  [r] remote — also ship to the project telemetry server (retry on next start if offline)\n"
        "  [n] off    — do nothing (default)\n"
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m axor_telemetry")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("consent", help="interactive opt-in prompt")
    sub.add_parser("status",  help="show current effective config")
    sub.add_parser("preview", help="print the last queued record")
    on_parser = sub.add_parser("on", help="enable telemetry (local by default)")
    on_parser.add_argument("--remote", action="store_true", help="enable remote shipping")
    sub.add_parser("off", help="disable telemetry")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    dispatch = {
        "consent": cmd_consent,
        "status":  cmd_status,
        "preview": cmd_preview,
        "on":      cmd_on,
        "off":     cmd_off,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
