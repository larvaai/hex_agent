"""Vector store adapters. Epic E08.

InMemoryVectorStore is the offline adapter used by the acceptance suite; it makes
``health()`` switchable so the dependency-failure path (S08.1) is testable.
The optional production adapter lives in ``rag.stores_qdrant`` so importing this
module never requires qdrant-client.
"""
from __future__ import annotations

import math

from rag.ports import Chunk, Hit


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """Offline vector store; deterministic cosine search."""

    def __init__(self, *, collection: str = "agent_kb", healthy: bool = True) -> None:
        self.collection = collection
        self._healthy = healthy
        self._chunks: list[Chunk] = []

    def set_healthy(self, value: bool) -> None:
        self._healthy = value

    def health(self) -> dict:
        return {"ok": self._healthy, "collection": self.collection, "count": len(self._chunks)}

    def delete_by_source(self, source: str) -> int:
        before = len(self._chunks)
        self._chunks = [c for c in self._chunks if c.source != source]
        return before - len(self._chunks)

    def upsert(self, chunks: list[Chunk]) -> int:
        self._chunks.extend(chunks)
        return len(chunks)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        hits: list[Hit] = []
        for c in self._chunks:
            if c.vector is None:
                continue
            score = _cosine(vector, c.vector)
            if score >= score_threshold:
                hits.append(Hit(c.source, c.chunk_index, c.text, score))
        hits.sort(key=lambda h: (-h.score, h.source, h.chunk_index))
        return hits[:top_k]
