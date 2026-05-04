from __future__ import annotations

from axor_telemetry.config import TelemetryConfig, TelemetryMode
from axor_telemetry.embedder import MinHashEmbedder
from axor_telemetry.pipeline import TelemetryPipeline, build_pipeline
from axor_telemetry.sinks.file_sink import FileTelemetrySink


class _CaptureSink:
    def __init__(self):
        self.batches: list[list] = []
        self.flushed = 0

    async def send(self, records):
        self.batches.append(list(records))

    async def flush(self):
        self.flushed += 1


async def test_pipeline_off_by_default_does_nothing():
    sink = _CaptureSink()
    p = TelemetryPipeline(embedder=MinHashEmbedder(), sink=sink,
                          config=TelemetryConfig(mode=TelemetryMode.OFF))
    await p.record_decision(
        raw_input="hello", signal="focused_generative",
        classifier_used="heuristic", confidence=0.9,
    )
    assert sink.batches == []


async def test_pipeline_local_sends_with_embedding():
    sink = _CaptureSink()
    p = TelemetryPipeline(embedder=MinHashEmbedder(), sink=sink,
                          config=TelemetryConfig(mode=TelemetryMode.LOCAL))
    await p.record_decision(
        raw_input="explain why this function is slow",
        signal="focused_readonly",
        classifier_used="heuristic",
        confidence=0.9,
        tokens_spent=120,
    )
    assert len(sink.batches) == 1
    rec = sink.batches[0][0]
    assert rec.classifier_used == "heuristic"
    assert rec.fingerprint_kind == "minhash_v1"
    assert rec.input_embedding is not None
    assert len(rec.input_embedding) == 128


async def test_pipeline_passes_tool_selection_through_to_record():
    sink = _CaptureSink()
    p = TelemetryPipeline(embedder=None, sink=sink,
                          config=TelemetryConfig(mode=TelemetryMode.LOCAL))
    await p.record_decision(
        raw_input="describe the schema",
        signal="focused_readonly",
        classifier_used="heuristic",
        confidence=0.6,
        tool_selection={
            "mode":              "relevance",
            "offered":           5,
            "kept":              2,
            "dropped_relevance": 3,
            "dropped_denied":    0,
        },
    )
    rec = sink.batches[0][0]
    # Whether axor-core is installed or not, the record carries tool_selection.
    assert getattr(rec, "tool_selection", None) == {
        "mode":              "relevance",
        "offered":           5,
        "kept":              2,
        "dropped_relevance": 3,
        "dropped_denied":    0,
    }


async def test_pipeline_tolerates_embedder_failure():
    class BadEmbedder:
        kind = "broken_v1"
        def embed(self, text): raise RuntimeError("boom")

    sink = _CaptureSink()
    p = TelemetryPipeline(embedder=BadEmbedder(), sink=sink,
                          config=TelemetryConfig(mode=TelemetryMode.LOCAL))
    await p.record_decision(
        raw_input="x", signal="focused_generative",
        classifier_used="heuristic", confidence=0.5,
    )
    rec = sink.batches[0][0]
    assert rec.input_embedding is None
    assert rec.fingerprint_kind == ""


async def test_pipeline_tolerates_sink_failure():
    class BadSink:
        async def send(self, records): raise RuntimeError("network")
        async def flush(self): raise RuntimeError("network")
    p = TelemetryPipeline(embedder=None, sink=BadSink(),
                          config=TelemetryConfig(mode=TelemetryMode.LOCAL))
    # Must not raise
    await p.record_decision(
        raw_input="x", signal="focused_generative",
        classifier_used="heuristic", confidence=0.5,
    )
    await p.flush()


class _FakeEvent:
    def __init__(self, kind_value: str, **attrs):
        self.kind = type("K", (), {"value": kind_value})()
        for k, v in attrs.items():
            setattr(self, k, v)


class _FakeTrace:
    def __init__(self, events):
        self.events = events


async def test_ingest_trace_extracts_signal_and_tokens():
    sink = _CaptureSink()
    p = TelemetryPipeline(embedder=MinHashEmbedder(), sink=sink,
                          config=TelemetryConfig(mode=TelemetryMode.LOCAL))

    trace = _FakeTrace(events=[
        _FakeEvent("signal_chosen",
                   signal="focused_generative",
                   classifier="heuristic",
                   confidence=0.85,
                   raw_input="write a test for auth"),
        _FakeEvent("tokens_spent", input_tokens=100, output_tokens=50),
        _FakeEvent("tokens_spent", input_tokens=20, output_tokens=10),
        _FakeEvent("policy_adjusted"),
    ])
    await p.ingest_trace(trace)
    rec = sink.batches[0][0]
    assert rec.tokens_spent == 180
    assert rec.policy_adjusted is True
    assert rec.classifier_used == "heuristic"


async def test_build_pipeline_off_returns_disabled():
    p = build_pipeline(config=TelemetryConfig(mode=TelemetryMode.OFF))
    assert p.enabled is False
    # record_decision is a no-op
    await p.record_decision(raw_input="", signal="x", classifier_used="h", confidence=0.0)


async def test_build_pipeline_local_uses_file_sink(tmp_path):
    p = build_pipeline(
        config=TelemetryConfig(
            mode=TelemetryMode.LOCAL,
            queue_path=str(tmp_path / "q.jsonl"),
        )
    )
    assert p.enabled is True
    assert isinstance(p._sink, FileTelemetrySink)


async def test_build_pipeline_remote_uses_http_sink(tmp_path):
    from axor_telemetry.sinks.http_sink import HTTPTelemetrySink
    p = build_pipeline(
        config=TelemetryConfig(
            mode=TelemetryMode.REMOTE,
            endpoint="https://example.invalid/v1/records",
            queue_path=str(tmp_path / "q.jsonl"),
        )
    )
    assert p.enabled is True
    assert isinstance(p._sink, HTTPTelemetrySink)


async def test_pipeline_aclose_calls_sink_aclose():
    class TrackedSink:
        def __init__(self):
            self.aclose_called = False
            self.flushed = 0
        async def send(self, records): pass
        async def flush(self): self.flushed += 1
        async def aclose(self): self.aclose_called = True

    sink = TrackedSink()
    p = TelemetryPipeline(embedder=None, sink=sink,
                          config=TelemetryConfig(mode=TelemetryMode.LOCAL))
    await p.aclose()
    assert sink.flushed >= 1
    assert sink.aclose_called is True


async def test_pipeline_aclose_without_aclose_method():
    class NoAcloseSink:
        async def send(self, records): pass
        async def flush(self): pass

    p = TelemetryPipeline(embedder=None, sink=NoAcloseSink(),
                          config=TelemetryConfig(mode=TelemetryMode.LOCAL))
    # Must not raise when sink lacks aclose.
    await p.aclose()


async def test_ingest_trace_no_signal_event_is_noop():
    sink_calls = []
    class S:
        async def send(self, records): sink_calls.append(records)
        async def flush(self): pass

    p = TelemetryPipeline(embedder=MinHashEmbedder(), sink=S(),
                          config=TelemetryConfig(mode=TelemetryMode.LOCAL))

    class FakeTrace:
        events = []  # no signal_chosen → no record emitted

    await p.ingest_trace(FakeTrace())
    assert sink_calls == []


async def test_ingest_trace_when_disabled_is_noop():
    p = TelemetryPipeline(embedder=None, sink=None,
                          config=TelemetryConfig(mode=TelemetryMode.OFF))
    class FakeTrace: events = []
    # No exception, no-op.
    await p.ingest_trace(FakeTrace())


async def test_fallback_record_used_when_core_unavailable(monkeypatch):
    """Force ImportError path in _make_record to cover _FallbackRecord branch."""
    from axor_telemetry import pipeline as pmod
    import sys, builtins

    # Force ImportError when code tries to import axor_core.contracts.trace
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name.startswith("axor_core"):
            raise ImportError("axor-core hidden in test")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    rec = pmod._make_record(
        signal="focused_generative",
        classifier_used="heuristic",
        confidence=0.5,
        tokens_spent=0,
        policy_adjusted=False,
        embedding=None,
        fingerprint_kind="",
    )
    assert isinstance(rec, pmod._FallbackRecord)
    assert rec.signal_chosen == "focused_generative"
