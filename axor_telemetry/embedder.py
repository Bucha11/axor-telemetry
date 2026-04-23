"""
MinHash embedder — pure-Python 128-dim fingerprint of a string.

Approach:
  1. Normalize the text (lowercase, collapse whitespace).
  2. Extract character 3-grams.
  3. For each of 128 hash "seeds", compute hash(seed, ngram) over all ngrams
     and keep the minimum. That minimum is one coordinate of the fingerprint.

Result is a deterministic `list[int]` of 128 non-negative 32-bit values.
Similar inputs collide on similar MinHash positions → Jaccard similarity
of the 3-gram sets is approximated by match rate between two fingerprints.

The fingerprint is one-way: it loses ordering, multiplicity, and the original
alphabet. Recovery of the source text is not feasible.
"""
from __future__ import annotations

import hashlib
import re

_WS = re.compile(r"\s+")
_DEFAULT_N = 3
_DEFAULT_DIMS = 128
_MAX_INT = (1 << 32) - 1


def _normalize(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


def _ngrams(text: str, n: int) -> list[str]:
    if len(text) < n:
        return [text] if text else []
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def _seeded_hash(seed: int, token: str) -> int:
    """Stable 32-bit hash of (seed, token). Uses blake2b for speed + uniformity."""
    h = hashlib.blake2b(
        token.encode("utf-8"),
        digest_size=4,
        salt=seed.to_bytes(2, "little", signed=False).ljust(8, b"\0")[:8],
    )
    return int.from_bytes(h.digest(), "little", signed=False)


class MinHashEmbedder:
    """
    128-dim MinHash embedder with char-3 n-grams.

    kind = "minhash_v1" — pinned identifier. Any change to the algorithm
    (n-gram size, dim count, hash function) requires a new kind so the
    server-side schema can reject / gate legacy fingerprints.
    """

    kind: str = "minhash_v1"

    def __init__(self, dims: int = _DEFAULT_DIMS, n: int = _DEFAULT_N) -> None:
        if dims <= 0:
            raise ValueError("dims must be positive")
        if n <= 0:
            raise ValueError("n must be positive")
        self._dims = dims
        self._n = n

    @property
    def dims(self) -> int:
        return self._dims

    def embed(self, text: str) -> list[float]:
        """
        Return the MinHash fingerprint as a list of floats for contract
        compatibility with `Embedder.embed() -> list[float]`. Values are
        integer-valued floats (0..2**32-1) so downstream consumers can
        round-trip them safely.
        """
        normalized = _normalize(text)
        grams = _ngrams(normalized, self._n)
        if not grams:
            # empty text → all-maxed signature so two empties are equal but
            # anything non-empty has near-zero similarity.
            return [float(_MAX_INT)] * self._dims

        sig = [_MAX_INT] * self._dims
        for seed in range(self._dims):
            m = _MAX_INT
            for g in grams:
                h = _seeded_hash(seed, g)
                if h < m:
                    m = h
            sig[seed] = m
        return [float(x) for x in sig]

    def similarity(self, a: list[float], b: list[float]) -> float:
        """Approximate Jaccard similarity between two fingerprints (0..1)."""
        if len(a) != len(b):
            raise ValueError("fingerprint length mismatch")
        if not a:
            return 1.0
        matches = sum(1 for x, y in zip(a, b) if x == y)
        return matches / len(a)
