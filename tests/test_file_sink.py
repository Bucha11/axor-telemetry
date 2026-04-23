from __future__ import annotations

import json

import pytest

from axor_telemetry.pipeline import _FallbackRecord
from axor_telemetry.sinks.file_sink import FileTelemetrySink


def _record(signal: str = "focused_generative", embedding=None):
    return _FallbackRecord(
        signal_chosen=signal,
        classifier_used="heuristic",
        confidence=0.8,
        tokens_spent=150,
        policy_adjusted=False,
        input_embedding=embedding,
        fingerprint_kind="minhash_v1" if embedding else "",
    )


async def test_send_appends_lines(tmp_queue_path):
    sink = FileTelemetrySink(queue_path=tmp_queue_path, axor_version="0.3.0")
    await sink.send([_record(), _record(signal="focused_readonly")])
    lines = open(tmp_queue_path).read().splitlines()
    assert len(lines) == 2
    parsed = json.loads(lines[0])
    assert parsed["signal_chosen"] == "focused_generative"
    assert parsed["axor_version"] == "0.3.0"
    assert parsed["schema_version"] == 1


async def test_send_preserves_embedding_as_ints(tmp_queue_path):
    sink = FileTelemetrySink(queue_path=tmp_queue_path)
    await sink.send([_record(embedding=[1.0, 2.5, 3.9])])
    line = json.loads(open(tmp_queue_path).read().splitlines()[0])
    assert line["fingerprint"] == [1, 2, 3]
    assert line["fingerprint_kind"] == "minhash_v1"


async def test_send_empty_batch_is_noop(tmp_queue_path):
    sink = FileTelemetrySink(queue_path=tmp_queue_path)
    await sink.send([])
    assert not open(tmp_queue_path, "a").closed  # handle never opened for write


def test_drain_parses_and_skips_malformed(tmp_path):
    path = tmp_path / "q.jsonl"
    path.write_text(
        '{"a": 1}\n'
        '{not valid json}\n'
        '{"b": 2}\n',
        encoding="utf-8",
    )
    sink = FileTelemetrySink(queue_path=str(path))
    records = list(sink.drain())
    assert records == [{"a": 1}, {"b": 2}]


def test_truncate_removes_file(tmp_path):
    path = tmp_path / "q.jsonl"
    path.write_text('{"a":1}\n', encoding="utf-8")
    sink = FileTelemetrySink(queue_path=str(path))
    sink.truncate()
    assert not path.exists()


async def test_rotation_caps_file_size(tmp_queue_path):
    sink = FileTelemetrySink(queue_path=tmp_queue_path, max_bytes=2_000)
    # Fill past cap
    for _ in range(500):
        await sink.send([_record()])
    import os
    size = os.path.getsize(tmp_queue_path)
    assert size <= 2_000 * 2  # loose bound: within one batch of cap


async def test_missing_queue_returns_empty_drain(tmp_path):
    sink = FileTelemetrySink(queue_path=str(tmp_path / "missing.jsonl"))
    assert list(sink.drain()) == []
