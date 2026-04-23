"""
HTTPTelemetrySink — POST batches to the telemetry server with retry-on-next-start.

Design:
  - Every `send()` batch is first appended to a local FileTelemetrySink queue.
  - If network ship succeeds, the batched lines are removed from the queue.
  - If it fails (offline, 5xx, timeout), the queue retains them; the next
    process start calls `flush_queue()` to drain pending records.

Zero runtime deps — uses urllib from the stdlib.
"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from axor_telemetry.serialize import record_to_wire
from axor_telemetry.sinks.file_sink import FileTelemetrySink


class HTTPTelemetrySink:
    """
    `send(records)` → append-to-queue → attempt ship. Queue is the source of
    truth for pending records; the wire call is a drain attempt.
    """

    def __init__(
        self,
        endpoint: str,
        queue_path: str,
        axor_version: str = "",
        timeout_seconds: float = 10.0,
        batch_size: int = 200,
    ) -> None:
        self._endpoint = endpoint
        self._axor_version = axor_version
        self._timeout = timeout_seconds
        self._batch_size = batch_size
        self._file_sink = FileTelemetrySink(queue_path=queue_path, axor_version=axor_version)

    @property
    def queue_path(self) -> Path:
        return self._file_sink.path

    async def send(self, records: list[Any]) -> None:
        if not records:
            return
        await self._file_sink.send(records)
        await self._drain_and_ship()

    async def flush(self) -> None:
        """Attempt to drain any queued records. Called on pipeline start + close."""
        await self._drain_and_ship()

    async def aclose(self) -> None:
        await self.flush()
        await self._file_sink.aclose()

    # ── Drain loop ──────────────────────────────────────────────────────────

    async def _drain_and_ship(self) -> None:
        records = await asyncio.to_thread(list, self._file_sink.drain())
        if not records:
            return

        sent = 0
        for batch in _chunks(records, self._batch_size):
            ok = await asyncio.to_thread(self._post_batch, batch)
            if not ok:
                break
            sent += len(batch)

        if sent == len(records):
            await asyncio.to_thread(self._file_sink.truncate)
        elif sent > 0:
            # Partial success: rewrite queue with the unsent tail.
            await asyncio.to_thread(self._rewrite_tail, records[sent:])

    def _post_batch(self, batch: list[dict]) -> bool:
        payload = json.dumps(batch, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(
            self._endpoint,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent":   f"axor-telemetry/{self._axor_version or 'unknown'}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            return False

    def _rewrite_tail(self, remaining: list[dict]) -> None:
        # Replace queue contents with `remaining` — these stay for next start.
        self._file_sink.truncate()
        # Re-append without re-serializing (they're already wire dicts).
        path = self._file_sink.path
        with path.open("a", encoding="utf-8") as f:
            for rec in remaining:
                f.write(json.dumps(rec, separators=(",", ":")) + "\n")


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


# ── Back-compat helper for non-trace users ──────────────────────────────────

def wire_record(record: Any, axor_version: str = "") -> dict:
    """Public helper: convert an AnonymizedTraceRecord to the wire-format dict."""
    return record_to_wire(record, axor_version)
