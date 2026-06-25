"""RagService — health-gated ingest/search logic over the ports. Epic E08.

Invariants (from BUILD_PLAN): health-gate before every ingest/search; ingest paths
go through the workspace sandbox jail; logic never touches Qdrant directly (only via
``VectorStorePort``). Every method returns a plain dict envelope ``{"ok": bool, ...}``
so it maps cleanly onto a tool result through ``execute_tool``.
"""
from __future__ import annotations

from rag.chunking import chunk_text, collect_files
from rag.ports import Chunk, EmbedderPort, RagConfig, VectorStorePort
from safety.sandbox import SandboxError, resolve_in_workspace


class RagService:
    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._cfg = config

    # ── health ──────────────────────────────────────────────────────────────
    def health(self) -> dict:
        h = self._store.health()
        return {
            "ok": bool(h.get("ok")),
            "collection": h.get("collection"),
            "count": h.get("count", 0),
        }

    def _require_healthy(self) -> dict | None:
        """Return a dependency-failure envelope if the store is unhealthy, else None."""
        h = self._store.health()
        if not h.get("ok"):
            return {
                "ok": False,
                "code": "dependency_unavailable",
                "error": f"RAG store unhealthy (collection={h.get('collection')}).",
            }
        return None

    # ── ingest ───────────────────────────────────────────────────────────────
    def ingest(self, raw_path: str) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
        try:
            root = resolve_in_workspace(raw_path)
        except SandboxError as exc:
            return {"ok": False, "code": "sandbox", "error": str(exc)}

        files = collect_files(root)
        total_chunks = 0
        sources: list[str] = []
        for file in files:
            source = str(file)
            texts = chunk_text(
                file.read_text(encoding="utf-8", errors="replace"),
                self._cfg.chunk_size,
                self._cfg.chunk_overlap,
            )
            if not texts:
                continue
            vectors = self._embedder.embed(texts)
            if len(vectors) != len(texts):
                # Refuse a cardinality mismatch before any upsert so we never write a
                # partial/misaligned set of chunks for the source.
                raise ValueError(
                    f"embedder returned {len(vectors)} embeddings for {len(texts)} chunks (count mismatch)."
                )
            chunks = [Chunk(source, i, t, v) for i, (t, v) in enumerate(zip(texts, vectors))]
            self._store.delete_by_source(source)  # re-ingest replaces previous chunks
            self._store.upsert(chunks)
            total_chunks += len(chunks)
            sources.append(source)
        return {"ok": True, "files": len(sources), "chunks": total_chunks, "sources": sources}

    # ── search ───────────────────────────────────────────────────────────────
    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        score_threshold: float | None = None,
    ) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
        # Validate caller inputs before doing any embedding work.
        if not query or not str(query).strip():
            raise ValueError("search query must not be empty.")
        k = int(top_k) if top_k is not None else self._cfg.top_k
        if k < 1:
            raise ValueError("top_k must be a positive integer (>= 1).")
        threshold = float(score_threshold) if score_threshold is not None else self._cfg.score_threshold
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("score_threshold must be between 0.0 and 1.0.")
        vector = self._embedder.embed([query])[0]
        hits = self._store.search(vector, k, threshold)
        return {
            "ok": True,
            "count": len(hits),
            "top_k": k,
            "score_threshold": threshold,
            "hits": [
                {
                    "source": h.source,
                    "chunk_index": h.chunk_index,
                    "text": h.text,
                    "score": round(h.score, 6),
                }
                for h in hits
            ],
        }
