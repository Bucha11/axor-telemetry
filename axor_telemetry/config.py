"""
Telemetry configuration — resolved from env and ~/.axor/config.toml.

Priority (highest first):
  1. env vars AXOR_TELEMETRY, AXOR_TELEMETRY_ENDPOINT, AXOR_TELEMETRY_QUEUE
  2. ~/.axor/config.toml [telemetry] section
  3. defaults (off, stock endpoint, ~/.axor/telemetry_queue.jsonl)
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_CONFIG_PATH = Path("~/.axor/config.toml").expanduser()
_DEFAULT_QUEUE = "~/.axor/telemetry_queue.jsonl"
_DEFAULT_ENDPOINT = "https://telemetry.axor.dev/v1/records"


class TelemetryMode(str, Enum):
    OFF    = "off"
    LOCAL  = "local"
    REMOTE = "remote"


@dataclass(frozen=True)
class TelemetryConfig:
    mode: TelemetryMode = TelemetryMode.OFF
    endpoint: str       = _DEFAULT_ENDPOINT
    queue_path: str     = _DEFAULT_QUEUE
    fingerprint_kind: str = "minhash_v1"

    @property
    def enabled(self) -> bool:
        return self.mode is not TelemetryMode.OFF

    @property
    def ships_remote(self) -> bool:
        return self.mode is TelemetryMode.REMOTE

    @classmethod
    def load(cls, config_path: Path | None = None) -> "TelemetryConfig":
        """Resolve config from env + TOML file. Returns defaults when nothing is set."""
        path = config_path or _CONFIG_PATH
        data: dict = {}
        if path.is_file():
            try:
                with path.open("rb") as fh:
                    data = tomllib.load(fh).get("telemetry", {}) or {}
            except (OSError, tomllib.TOMLDecodeError):
                data = {}

        env_mode = os.environ.get("AXOR_TELEMETRY")
        mode_raw = env_mode or data.get("mode") or "off"
        try:
            mode = TelemetryMode(mode_raw.lower())
        except ValueError:
            mode = TelemetryMode.OFF

        endpoint   = os.environ.get("AXOR_TELEMETRY_ENDPOINT")   or data.get("endpoint")   or _DEFAULT_ENDPOINT
        queue_path = os.environ.get("AXOR_TELEMETRY_QUEUE")      or data.get("queue_path") or _DEFAULT_QUEUE
        fingerprint_kind = data.get("fingerprint_kind") or "minhash_v1"

        return cls(
            mode=mode,
            endpoint=endpoint,
            queue_path=queue_path,
            fingerprint_kind=fingerprint_kind,
        )

    def write(self, config_path: Path | None = None) -> Path:
        """
        Persist [telemetry] section to ~/.axor/config.toml, preserving other
        sections already present. Atomic: writes to tmp file then renames.
        """
        path = config_path or _CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)

        existing = ""
        if path.is_file():
            try:
                existing = path.read_text(encoding="utf-8")
            except OSError:
                existing = ""

        section = self._render_section()
        new_text = _replace_section(existing, "telemetry", section)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return path

    def _render_section(self) -> str:
        return (
            "[telemetry]\n"
            f'mode = "{self.mode.value}"\n'
            f'endpoint = "{_escape_toml(self.endpoint)}"\n'
            f'queue_path = "{_escape_toml(self.queue_path)}"\n'
            f'fingerprint_kind = "{_escape_toml(self.fingerprint_kind)}"\n'
        )


def _escape_toml(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _replace_section(text: str, section: str, new_block: str) -> str:
    """
    Rewrite a single `[section]` block in a TOML document. If missing, append.
    Preserves all other sections verbatim.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    replaced = False
    header = f"[{section}]"
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped == header:
            # skip until next header or EOF
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("["):
                j += 1
            out.append(new_block)
            if j < len(lines):
                out.append("\n")
            i = j
            replaced = True
            continue
        out.append(line)
        i += 1
    if not replaced:
        if out and not out[-1].endswith("\n"):
            out.append("\n")
        if out:
            out.append("\n")
        out.append(new_block)
    return "".join(out)
