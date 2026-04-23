from __future__ import annotations

from axor_telemetry.embedder import MinHashEmbedder


def test_fingerprint_dim_and_kind():
    e = MinHashEmbedder()
    fp = e.embed("write a test for the payment endpoint")
    assert len(fp) == 128
    assert e.kind == "minhash_v1"
    assert all(isinstance(x, float) for x in fp)


def test_deterministic_across_calls():
    e = MinHashEmbedder()
    text = "explain why this function is slow"
    assert e.embed(text) == e.embed(text)


def test_similar_texts_share_positions():
    e = MinHashEmbedder()
    a = e.embed("write a test for the payment endpoint")
    b = e.embed("write a test for the payment handler")
    sim = e.similarity(a, b)
    assert sim > 0.3, f"similar phrases should share positions, got {sim}"


def test_dissimilar_texts_diverge():
    e = MinHashEmbedder()
    a = e.embed("explain why this function is slow")
    b = e.embed("write a new migration from Python to Go")
    sim = e.similarity(a, b)
    assert sim < 0.2


def test_empty_text_produces_valid_fingerprint():
    e = MinHashEmbedder()
    fp = e.embed("")
    assert len(fp) == 128


def test_invalid_params_raise():
    import pytest
    with pytest.raises(ValueError):
        MinHashEmbedder(dims=0)
    with pytest.raises(ValueError):
        MinHashEmbedder(n=0)


def test_fingerprint_is_non_reversible_shape():
    # Smoke: different-length inputs produce the same-shape output and
    # the output is not trivially reconstructible (no text leaks through).
    e = MinHashEmbedder()
    short = e.embed("hi")
    long  = e.embed("hi " * 500)
    assert len(short) == len(long) == 128
    # Values must be non-negative 32-bit ints stored as float.
    for v in short + long:
        assert 0 <= v <= (1 << 32) - 1
