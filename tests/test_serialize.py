"""Tests for serialize.record_to_wire — the AxorRecord → wire-dict edge."""
from __future__ import annotations

import pytest

from axor_telemetry.pipeline import _FallbackRecord
from axor_telemetry.serialize import record_to_wire, _signal_key


class _DummyEnum:
    """Mimics a str-Enum value with a .value attribute."""
    def __init__(self, value: str) -> None:
        self.value = value


class _SignalObj:
    def __init__(self, complexity, nature, raw_input: str = ""):
        self.complexity = complexity
        self.nature = nature
        self.raw_input = raw_input


def test_signal_key_from_plain_string():
    assert _signal_key("focused_generative") == "focused_generative"


def test_signal_key_from_dict_with_enum_values():
    d = {"complexity": _DummyEnum("focused"), "nature": _DummyEnum("mutative")}
    assert _signal_key(d) == "focused_mutative"


def test_signal_key_from_dict_with_plain_strings():
    d = {"complexity": "moderate", "nature": "readonly"}
    assert _signal_key(d) == "moderate_readonly"


def test_signal_key_from_object_with_enum_values():
    obj = _SignalObj(_DummyEnum("expansive"), _DummyEnum("mutative"))
    assert _signal_key(obj) == "expansive_mutative"


def test_signal_key_from_object_with_plain_strings():
    obj = _SignalObj("focused", "generative")
    assert _signal_key(obj) == "focused_generative"


def test_signal_key_strips_trailing_underscore_when_nature_missing():
    obj = _SignalObj("focused", "")
    assert _signal_key(obj) == "focused"


def test_record_to_wire_with_real_task_signal():
    """Round-trip with an actual axor-core TaskSignal, verifying enum values flatten."""
    from axor_core.contracts.policy import TaskComplexity, TaskNature, TaskSignal
    signal = TaskSignal(
        raw_input="write a test",
        complexity=TaskComplexity.FOCUSED,
        nature=TaskNature.GENERATIVE,
        estimated_scope=1,
        requires_children=False,
        requires_mutation=False,
        domain="coding",
    )
    rec = _FallbackRecord(
        signal_chosen=signal,
        classifier_used="heuristic",
        confidence=0.85,
        tokens_spent=42,
        policy_adjusted=False,
        input_embedding=[1.0, 2.0],
        fingerprint_kind="minhash_v1",
    )
    wire = record_to_wire(rec, axor_version="0.3.0")
    assert wire["signal_chosen"] == "focused_generative"
    assert wire["fingerprint"] == [1, 2]
    assert wire["axor_version"] == "0.3.0"


def test_record_to_wire_raises_when_signal_missing():
    rec = _FallbackRecord(
        signal_chosen=None,
        classifier_used="heuristic",
        confidence=0.0,
        tokens_spent=0,
        policy_adjusted=False,
    )
    with pytest.raises(ValueError, match="signal_chosen"):
        record_to_wire(rec)


def test_record_to_wire_empty_fingerprint_kind_becomes_none():
    rec = _FallbackRecord(
        signal_chosen="focused_readonly",
        classifier_used="heuristic",
        confidence=0.5,
        tokens_spent=0,
        policy_adjusted=False,
        input_embedding=None,
        fingerprint_kind="",
    )
    wire = record_to_wire(rec)
    assert wire["fingerprint_kind"] == "none"
    assert wire["fingerprint"] is None


def test_record_to_wire_includes_tool_selection_when_present():
    rec = _FallbackRecord(
        signal_chosen="focused_generative",
        classifier_used="heuristic",
        confidence=0.7,
        tokens_spent=10,
        policy_adjusted=False,
        tool_selection={
            "mode":              "relevance",
            "offered":           8,
            "kept":              3,
            "dropped_relevance": 4,
            "dropped_denied":    1,
        },
    )
    wire = record_to_wire(rec)
    assert wire["tool_selection"] == {
        "mode":              "relevance",
        "offered":           8,
        "kept":              3,
        "dropped_relevance": 4,
        "dropped_denied":    1,
    }


def test_record_to_wire_omits_tool_selection_when_absent():
    rec = _FallbackRecord(
        signal_chosen="focused_generative",
        classifier_used="heuristic",
        confidence=0.5,
        tokens_spent=0,
        policy_adjusted=False,
    )
    wire = record_to_wire(rec)
    assert "tool_selection" not in wire


def test_record_to_wire_drops_invalid_tool_selection():
    rec = _FallbackRecord(
        signal_chosen="focused_generative",
        classifier_used="heuristic",
        confidence=0.5,
        tokens_spent=0,
        policy_adjusted=False,
        tool_selection="not a dict",  # type: ignore[arg-type]
    )
    wire = record_to_wire(rec)
    assert "tool_selection" not in wire


def test_record_to_wire_clamps_negative_tool_selection_counts():
    rec = _FallbackRecord(
        signal_chosen="focused_generative",
        classifier_used="heuristic",
        confidence=0.5,
        tokens_spent=0,
        policy_adjusted=False,
        tool_selection={
            "mode":              "weird-mode",
            "offered":           -3,
            "kept":              "2",
            "dropped_relevance": -1,
            "dropped_denied":    0,
        },
    )
    wire = record_to_wire(rec)
    assert wire["tool_selection"] == {
        "mode":              "none",
        "offered":           0,
        "kept":              2,
        "dropped_relevance": 0,
        "dropped_denied":    0,
    }


def test_record_to_wire_coerces_numeric_types():
    """tokens_spent stored as int even if passed as float-like."""
    class Weird:
        signal_chosen = "focused_generative"
        classifier_used = "heuristic"
        confidence = "0.75"  # string
        tokens_spent = "100"  # string
        policy_adjusted = 1    # truthy int
        input_embedding = None
        fingerprint_kind = "none"

    wire = record_to_wire(Weird())
    assert isinstance(wire["confidence"], float)
    assert isinstance(wire["tokens_spent"], int)
    assert wire["policy_adjusted"] is True
