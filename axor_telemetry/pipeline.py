"""
TelemetryPipeline — bridges axor-core traces to a TelemetrySink.

Two entry points:

  `record_decision(...)`
      Low-level, takes primitive arguments; no axor-core import.

  `ingest_trace(decision_trace)`
      Convenience wrapper for code that already has a `DecisionTrace`
      from axor-core. Walks the event list to extract SignalChosenEvent
      and TokensSpentEvent, then delegates to `record_decision()`.

The pipeline is a no-op when TelemetryMode is OFF — user code can always
call `record_decision()` unconditionally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from axor_telemetry.config import TelemetryConfig, TelemetryMode


@runtime_checkable
class _EmbedderLike(Protocol):
    @property
    def kind(self) -> str: ...
    def embed(self, text: str) -> list[float]: ...


@runtime_checkable
class _SinkLike(Protocol):
    async def send(self, records: list[Any]) -> None: ...
    async def flush(self) -> None: ...


@dataclass
class _FallbackRecord:
    """
    Used when axor-core is not importable. Mirrors AnonymizedTraceRecord
    shape so serialize.record_to_wire() handles both identically.
    """
    signal_chosen: Any
    classifier_used: str
    confidence: float
    tokens_spent: int
    policy_adjusted: bool
    input_embedding: list[float] | None = None
    fingerprint_kind: str = ""
    tool_selection: dict | None = None


def _make_record(
    *,
    signal: Any,
    classifier_used: str,
    confidence: float,
    tokens_spent: int,
    policy_adjusted: bool,
    embedding: list[float] | None,
    fingerprint_kind: str,
    tool_selection: dict | None = None,
) -> Any:
    # AnonymizedTraceRecord is a frozen dataclass that does not (yet) carry
    # tool_selection. When the caller has tool_selection stats we need to
    # carry them on the record, so fall back to _FallbackRecord — the wire
    # serializer treats both shapes identically.
    if tool_selection is None:
        try:
            from axor_core.contracts.trace import AnonymizedTraceRecord
            return AnonymizedTraceRecord(
                signal_chosen=signal,
                classifier_used=classifier_used,
                confidence=confidence,
                tokens_spent=tokens_spent,
                policy_adjusted=policy_adjusted,
                input_embedding=embedding,
                fingerprint_kind=fingerprint_kind,
            )
        except ImportError:
            pass
    return _FallbackRecord(
        signal_chosen=signal,
        classifier_used=classifier_used,
        confidence=confidence,
        tokens_spent=tokens_spent,
        policy_adjusted=policy_adjusted,
        input_embedding=embedding,
        fingerprint_kind=fingerprint_kind,
        tool_selection=tool_selection,
    )


class TelemetryPipeline:
    def __init__(
        self,
        embedder: _EmbedderLike | None,
        sink: _SinkLike | None,
        config: TelemetryConfig | None = None,
        axor_version: str = "",
    ) -> None:
        self._embedder = embedder
        self._sink = sink
        self._config = config or TelemetryConfig()
        self._axor_version = axor_version

    @property
    def enabled(self) -> bool:
        return self._config.enabled and self._sink is not None

    async def record_decision(
        self,
        *,
        raw_input: str,
        signal: Any,
        classifier_used: str,
        confidence: float,
        tokens_spent: int = 0,
        policy_adjusted: bool = False,
        tool_selection: dict | None = None,
    ) -> None:
        if not self.enabled:
            return
        embedding: list[float] | None = None
        kind = ""
        if self._embedder is not None:
            try:
                embedding = self._embedder.embed(raw_input)
                kind = self._embedder.kind
            except Exception:
                # Never raise from telemetry path.
                embedding = None
                kind = ""
        record = _make_record(
            signal=signal,
            classifier_used=classifier_used,
            confidence=confidence,
            tokens_spent=tokens_spent,
            policy_adjusted=policy_adjusted,
            embedding=embedding,
            fingerprint_kind=kind,
            tool_selection=tool_selection,
        )
        try:
            await self._sink.send([record])
        except Exception:
            # Telemetry must never break the host application.
            return

    async def ingest_trace(self, decision_trace: Any, raw_input: str = "") -> None:
        """
        Extract SignalChosenEvent + cumulative tokens from a DecisionTrace and
        record it. Safe to call with any duck-typed trace carrying `.events`.
        """
        if not self.enabled:
            return

        events = getattr(decision_trace, "events", []) or []
        signal_event = None
        tokens = 0
        adjusted = False
        for event in events:
            kind_value = getattr(getattr(event, "kind", None), "value", None)
            if kind_value == "signal_chosen":
                signal_event = event
            elif kind_value == "policy_adjusted":
                adjusted = True
            elif kind_value == "tokens_spent":
                tokens += int(getattr(event, "input_tokens", 0)) + int(getattr(event, "output_tokens", 0))

        if signal_event is None:
            return

        await self.record_decision(
            raw_input=raw_input or getattr(signal_event, "raw_input", "") or "",
            signal=getattr(signal_event, "signal", None),
            classifier_used=getattr(signal_event, "classifier", "unknown"),
            confidence=float(getattr(signal_event, "confidence", 0.0)),
            tokens_spent=tokens,
            policy_adjusted=adjusted,
        )

    async def flush(self) -> None:
        if self._sink is not None:
            try:
                await self._sink.flush()
            except Exception:
                return

    async def aclose(self) -> None:
        await self.flush()
        if self._sink is not None:
            close = getattr(self._sink, "aclose", None)
            if close is not None:
                try:
                    await close()
                except Exception:
                    return


# ── Factory helpers ───────────────────────────────────────────────────────────


def build_pipeline(
    config: TelemetryConfig | None = None,
    axor_version: str = "",
) -> TelemetryPipeline:
    """
    Construct a pipeline matching a resolved TelemetryConfig:
      OFF    → embedder/sink = None (pipeline.enabled == False)
      LOCAL  → MinHashEmbedder + FileTelemetrySink
      REMOTE → MinHashEmbedder + HTTPTelemetrySink (queue-backed)
    """
    cfg = config or TelemetryConfig.load()
    if cfg.mode is TelemetryMode.OFF:
        return TelemetryPipeline(embedder=None, sink=None, config=cfg, axor_version=axor_version)

    from axor_telemetry.embedder import MinHashEmbedder
    embedder = MinHashEmbedder()

    if cfg.mode is TelemetryMode.LOCAL:
        from axor_telemetry.sinks.file_sink import FileTelemetrySink
        sink = FileTelemetrySink(queue_path=cfg.queue_path, axor_version=axor_version)
    else:
        from axor_telemetry.sinks.http_sink import HTTPTelemetrySink
        sink = HTTPTelemetrySink(
            endpoint=cfg.endpoint,
            queue_path=cfg.queue_path,
            axor_version=axor_version,
        )

    return TelemetryPipeline(embedder=embedder, sink=sink, config=cfg, axor_version=axor_version)
