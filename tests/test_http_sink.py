from __future__ import annotations

import json
from unittest.mock import patch

from axor_telemetry.pipeline import _FallbackRecord
from axor_telemetry.sinks.http_sink import HTTPTelemetrySink


def _record(signal: str = "focused_generative"):
    return _FallbackRecord(
        signal_chosen=signal,
        classifier_used="heuristic",
        confidence=0.8,
        tokens_spent=100,
        policy_adjusted=False,
    )


async def test_send_posts_and_clears_queue_on_success(tmp_path):
    sink = HTTPTelemetrySink(
        endpoint="https://example.invalid/v1/records",
        queue_path=str(tmp_path / "q.jsonl"),
        axor_version="0.3.0",
    )
    captured: list[list[dict]] = []

    def fake_post(batch):
        captured.append(batch)
        return True

    with patch.object(sink, "_post_batch", side_effect=fake_post):
        await sink.send([_record(), _record(signal="focused_readonly")])

    assert len(captured) == 1
    assert len(captured[0]) == 2
    # Queue is drained after success
    assert not sink.queue_path.exists()


async def test_send_retains_on_failure_for_next_start(tmp_path):
    sink = HTTPTelemetrySink(
        endpoint="https://example.invalid/v1/records",
        queue_path=str(tmp_path / "q.jsonl"),
    )
    with patch.object(sink, "_post_batch", return_value=False):
        await sink.send([_record()])

    # Queue retains the record
    assert sink.queue_path.is_file()
    lines = sink.queue_path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["signal_chosen"] == "focused_generative"


async def test_flush_on_next_start_drains_queue(tmp_path):
    queue = tmp_path / "q.jsonl"
    queue.write_text(
        json.dumps({
            "signal_chosen":    "focused_readonly",
            "classifier_used":  "heuristic",
            "confidence":       0.9,
            "tokens_spent":     0,
            "policy_adjusted":  False,
            "fingerprint":      None,
            "fingerprint_kind": "none",
            "axor_version":     "0.2.0",
            "schema_version":   1,
        }) + "\n",
        encoding="utf-8",
    )

    sink = HTTPTelemetrySink(
        endpoint="https://example.invalid/v1/records",
        queue_path=str(queue),
    )
    with patch.object(sink, "_post_batch", return_value=True):
        await sink.flush()
    assert not queue.exists()


async def test_partial_success_preserves_tail(tmp_path):
    sink = HTTPTelemetrySink(
        endpoint="https://example.invalid/v1/records",
        queue_path=str(tmp_path / "q.jsonl"),
        batch_size=2,
    )

    # Prime queue with 5 records via a guaranteed failure, then retry
    with patch.object(sink, "_post_batch", return_value=False):
        await sink.send([_record() for _ in range(5)])

    # Now let the first batch succeed, the second fail: 2 shipped, 3 retained.
    results = iter([True, False])
    with patch.object(sink, "_post_batch", side_effect=lambda b: next(results)):
        await sink.flush()

    remaining = sink.queue_path.read_text().splitlines()
    assert len(remaining) == 3


async def test_post_batch_success_via_mocked_urlopen(tmp_path):
    """Exercise the real urllib path, intercepted at urlopen level."""
    import urllib.request
    sink = HTTPTelemetrySink(
        endpoint="https://example.invalid/v1/records",
        queue_path=str(tmp_path / "q.jsonl"),
        axor_version="0.3.0",
    )

    class _FakeResp:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *_): return None

    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["ua"] = req.headers.get("User-agent")
        return _FakeResp()

    with patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
        await sink.send([_record()])

    assert captured["url"] == "https://example.invalid/v1/records"
    assert b"focused_generative" in captured["data"]
    assert "axor-telemetry/0.3.0" == captured["ua"]
    assert not sink.queue_path.exists()


async def test_post_batch_returns_false_on_urlerror(tmp_path):
    import urllib.error
    import urllib.request
    sink = HTTPTelemetrySink(
        endpoint="https://example.invalid/v1/records",
        queue_path=str(tmp_path / "q.jsonl"),
    )

    def _raise(*a, **kw):
        raise urllib.error.URLError("connection refused")

    with patch.object(urllib.request, "urlopen", side_effect=_raise):
        await sink.send([_record()])

    # Record remains queued for next-start retry.
    assert sink.queue_path.read_text().count("\n") == 1


async def test_post_batch_returns_false_on_5xx(tmp_path):
    import urllib.request
    sink = HTTPTelemetrySink(
        endpoint="https://example.invalid/v1/records",
        queue_path=str(tmp_path / "q.jsonl"),
    )

    class _Fail:
        status = 502
        def __enter__(self): return self
        def __exit__(self, *_): return None

    with patch.object(urllib.request, "urlopen", return_value=_Fail()):
        await sink.send([_record()])

    assert sink.queue_path.is_file()
    assert sink.queue_path.read_text().count("\n") == 1


async def test_flush_with_empty_queue_is_noop(tmp_path):
    sink = HTTPTelemetrySink(
        endpoint="https://example.invalid/v1/records",
        queue_path=str(tmp_path / "q.jsonl"),
    )
    await sink.flush()  # must not raise
    assert not sink.queue_path.exists()


async def test_wire_record_helper(tmp_path):
    from axor_telemetry.sinks.http_sink import wire_record
    rec = _record(signal="focused_generative")
    wire = wire_record(rec, axor_version="0.9.0")
    assert wire["signal_chosen"] == "focused_generative"
    assert wire["axor_version"] == "0.9.0"


async def test_aclose_flushes_and_closes(tmp_path):
    import urllib.request
    sink = HTTPTelemetrySink(
        endpoint="https://example.invalid/v1/records",
        queue_path=str(tmp_path / "q.jsonl"),
    )
    # Prime failures so queue has content
    with patch.object(sink, "_post_batch", return_value=False):
        await sink.send([_record()])

    # Now let aclose drain successfully
    class _Ok:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): return None
    with patch.object(urllib.request, "urlopen", return_value=_Ok()):
        await sink.aclose()

    assert not sink.queue_path.exists()
