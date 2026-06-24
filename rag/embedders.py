"""Embedder adapters. Epic E08.

FakeEmbedder is deterministic and offline: a normalized bag-of-words hash so that
identical text scores cosine 1.0 and disjoint text scores 0.0 — enough to exercise
the score threshold without a model download. FastEmbedEmbedder (Slice S2) wraps
fastembed for production and is imported lazily so the base install stays light.
"""
from __future__ import annotations

import hashlib
import math
import re

_TOKEN_RE = re.compile(r"\w+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bucket(token: str, dim: int) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dim


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


class FakeEmbedder:
    """Deterministic offline embedder (no network, no model)."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            vec[_bucket(tok, self.dim)] += 1.0
        return _normalize(vec)


class FastEmbedEmbedder:
    """Production embedder backed by fastembed (lazy import; Slice S2)."""

    def __init__(self, model: str) -> None:
        from fastembed import TextEmbedding  # noqa: PLC0415 — optional dep

        self._model = TextEmbedding(model_name=model)
        # Probe dimensionality once.
        self.dim = len(next(iter(self._model.embed(["probe"]))))

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(v) for v in self._model.embed(texts)]
