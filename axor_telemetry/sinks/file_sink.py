"""
FileTelemetrySink — append-only JSONL queue on local disk.

Serves two roles:
  1. Primary sink when TelemetryMode is LOCAL — user sees their own records.
  2. Buffer for HTTPTelemetrySink — records queued while offline are
     drained on next start.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any, Iterable

from axor_telemetry.serialize import record_to_wire


class FileTelemetrySink:
    """
    Thread-safe append-only JSONL sink.

    - `send()` serializes each record and appends one line per record.
    - `flush()` fsyncs the open handle.
    - `aclose()` closes it.
    - `drain()` iterates over all queued records, yielding parsed dicts,
      and truncates the file atomically when fully consumed.

    No locks are held during fsync/disk IO longer than necessary; the in-
    memory queue is bounded by `max_bytes` (default 50 MB) to prevent
    runaway growth if nobody drains it.
    """

    def __init__(
        self,
        queue_path: str | os.PathLike[str],
        axor_version: str = "",
        max_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self._path = Path(os.path.expanduser(str(queue_path)))
        self._axor_version = axor_version
        self._max_bytes = max_bytes
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    async def send(self, records: list[Any]) -> None:
        if not records:
            return
        lines = [
            json.dumps(record_to_wire(r, self._axor_version), separators=(",", ":"))
            for r in records
        ]
        await asyncio.to_thread(self._append_lines, lines)

    async def flush(self) -> None:
        # No persistent handle — every send() already closes after append.
        return

    async def aclose(self) -> None:
        await self.flush()

    def _append_lines(self, lines: list[str]) -> None:
        with self._lock:
            # Rotate if file would exceed cap — keeps newest half.
            try:
                if self._path.is_file() and self._path.stat().st_size > self._max_bytes:
                    self._rotate_truncate()
            except OSError:
                pass
            with self._path.open("a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass

    def _rotate_truncate(self) -> None:
        """Keep only the second half of the file by bytes. Caller holds lock."""
        raw = self._path.read_bytes()
        half = raw[len(raw) // 2 :]
        # Advance to the next newline so we don't keep a partial leading line.
        idx = half.find(b"\n")
        if idx != -1:
            half = half[idx + 1 :]
        self._path.write_bytes(half)

    # ── Drain for remote upload ────────────────────────────────────────────

    def drain(self) -> Iterable[dict]:
        """
        Read all queued records, yielding parsed dicts. Callers decide when
        to truncate by calling `truncate()` after successful consumption.
        Malformed lines are skipped.
        """
        with self._lock:
            if not self._path.is_file():
                return []
            out: list[dict] = []
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            return out

    def truncate(self) -> None:
        """Clear the queue. Use only after successful upload of all drain()ed records."""
        with self._lock:
            try:
                self._path.unlink()
            except FileNotFoundError:
                pass
