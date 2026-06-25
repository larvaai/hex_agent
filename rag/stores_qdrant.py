"""Qdrant vector store adapter (production). Epic E08, Slice S2.

The real adapter behind :class:`rag.ports.VectorStorePort`. Imported lazily by
``rag.feature.build_service`` only when ``backend: qdrant`` is configured, so the base
install never imports ``qdrant_client``. Exercised by ``tests/test_rag_qdrant.py``,
which skips unless a Qdrant server is reachable (the offline suite stays docker-free).

Design notes:
  * The collection is created lazily on first ``upsert`` from the embedding width, so
    the store need not know the embedder's dimensionality up front.
  * Point IDs are deterministic ``uuid5(source::chunk_index)`` so re-upserting the same
    chunk overwrites it in place; ``delete_by_source`` still runs first (see RagService)
    to drop chunks that no longer exist after an edit (S08.3 re-ingest replace).
  * ``health()`` never raises: an unreachable server returns ``{"ok": False}`` so the
    S08.1 dependency-failure gate stays normal control flow, not an exception.
"""
from __future__ import annotations

import threading
import uuid

from rag.ports import Chunk, Hit, RagConfig

# Stable namespace so point ids are reproducible across processes/hosts.
_ID_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-00000000e008")


def _point_id(source: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, f"{source}::{chunk_index}"))


class QdrantVectorStore:
    """Production adapter over qdrant-client: lazy collection, deterministic ids."""

    def __init__(self, config: RagConfig, *, client: object | None = None) -> None:
        self._cfg = config
        self.collection = config.collection
        self._lock = threading.Lock()
        self._collection_ready = False
        if client is not None:
            self._client = client
        else:
            from qdrant_client import QdrantClient  # noqa: PLC0415 — optional dep

            self._client = QdrantClient(url=config.qdrant_url)

    # ── collection lifecycle ─────────────────────────────────────────────────
    def _ensure_collection(self, dim: int) -> None:
        if self._collection_ready:
            return
        from qdrant_client import models  # noqa: PLC0415

        # The existence check stays outside the lock so concurrent first upserts all observe
        # "missing"; the create is then guarded + double-checked so it runs exactly once.
        if self._client.collection_exists(self.collection):
            self._collection_ready = True
            return
        with self._lock:
            if self._collection_ready:
                return
            self._client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
            )
            # Index `source` so delete/count-by-source stays cheap as the KB grows.
            self._client.create_payload_index(
                self.collection, field_name="source", field_schema=models.PayloadSchemaType.KEYWORD
            )
            self._collection_ready = True

    def _source_filter(self, source: str):
        from qdrant_client import models  # noqa: PLC0415

        return models.Filter(
            must=[models.FieldCondition(key="source", match=models.MatchValue(value=source))]
        )

    # ── VectorStorePort ──────────────────────────────────────────────────────
    def health(self) -> dict:
        try:
            count = 0
            if self._client.collection_exists(self.collection):
                count = self._client.count(self.collection, exact=True).count
            return {"ok": True, "collection": self.collection, "count": count}
        except Exception as exc:  # unreachable server -> dependency failure, not a crash
            return {"ok": False, "collection": self.collection, "count": 0, "error": str(exc)}

    def delete_by_source(self, source: str) -> int:
        if not self._client.collection_exists(self.collection):
            return 0
        flt = self._source_filter(source)
        removed = self._client.count(self.collection, count_filter=flt, exact=True).count
        if removed:
            self._client.delete(self.collection, points_selector=flt)
        return removed

    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        # Validate the whole batch before any network call so a bad batch never half-writes
        # or creates a collection with the wrong width.
        if any(c.vector is None for c in chunks):
            raise ValueError("upsert requires embedded chunks; a chunk vector is None.")
        dims = {len(c.vector) for c in chunks}
        if 0 in dims:
            raise ValueError("upsert requires non-empty embedding vectors.")
        if len(dims) != 1:
            raise ValueError(f"upsert requires a consistent embedding dimension; got {sorted(dims)}.")
        from qdrant_client import models  # noqa: PLC0415

        self._ensure_collection(next(iter(dims)))
        points = [
            models.PointStruct(
                id=_point_id(c.source, c.chunk_index),
                vector=list(c.vector),
                payload={"source": c.source, "chunk_index": c.chunk_index, "text": c.text},
            )
            for c in chunks
        ]
        self._client.upsert(self.collection, points=points)
        return len(points)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        if not self._client.collection_exists(self.collection):
            return []
        response = self._client.query_points(
            self.collection,
            query=list(vector),
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        hits: list[Hit] = []
        for point in response.points:
            payload = point.payload or {}
            hits.append(
                Hit(
                    source=payload.get("source", ""),
                    chunk_index=int(payload.get("chunk_index", 0)),
                    text=payload.get("text", ""),
                    score=float(point.score),
                )
            )
        return hits
