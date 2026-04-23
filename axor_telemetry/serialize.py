"""
Serialization helpers for AnonymizedTraceRecord → wire-format dict.

Handles the fact that axor-core may or may not be importable. When it is,
uses the real contract class for type-checked serialization. When it isn't,
walks dataclass-like attributes and produces the same wire format the
telemetry-server expects (see axor-telemetry-server/app/schemas.py).
"""
from __future__ import annotations

from typing import Any


def record_to_wire(record: Any, axor_version: str = "") -> dict:
    """
    Convert an AnonymizedTraceRecord (or any object with compatible fields) to
    the wire-format dict accepted by the telemetry server.
    """
    signal = getattr(record, "signal_chosen", None)
    if signal is None:
        raise ValueError("record missing signal_chosen")

    # Signal may be a TaskSignal (with .complexity.value and .nature.value),
    # a plain string, or a dict. Normalize to 'complexity_nature' string.
    signal_key = _signal_key(signal)

    fingerprint = getattr(record, "input_embedding", None)
    fingerprint_int: list[int] | None = None
    if fingerprint is not None:
        fingerprint_int = [int(x) for x in fingerprint]

    return {
        "signal_chosen":    signal_key,
        "classifier_used":  getattr(record, "classifier_used", ""),
        "confidence":       float(getattr(record, "confidence", 0.0)),
        "tokens_spent":     int(getattr(record, "tokens_spent", 0)),
        "policy_adjusted":  bool(getattr(record, "policy_adjusted", False)),
        "fingerprint":      fingerprint_int,
        "fingerprint_kind": getattr(record, "fingerprint_kind", "") or "none",
        "axor_version":     axor_version,
        "schema_version":   1,
    }


def _signal_key(signal: Any) -> str:
    if isinstance(signal, str):
        return signal
    if isinstance(signal, dict):
        c = signal.get("complexity", "")
        n = signal.get("nature", "")
        c = getattr(c, "value", c)
        n = getattr(n, "value", n)
        return f"{c}_{n}".strip("_")
    c = getattr(signal, "complexity", "")
    n = getattr(signal, "nature", "")
    c = getattr(c, "value", c)
    n = getattr(n, "value", n)
    return f"{c}_{n}".strip("_")
