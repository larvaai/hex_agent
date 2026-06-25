"""E08 RAG — Qdrant integration tests (Slice S2).

These exercise the *real* :class:`rag.stores_qdrant.QdrantVectorStore` against a
running Qdrant. They are skipped unless a server is reachable, so the default
offline suite (``test_rag.py``) stays docker-free. Bring Qdrant up with:

    docker compose -f docker-compose.rag.yml up -d

Embeddings use the deterministic ``FakeEmbedder`` so the tests assert *adapter*
behaviour (upsert / replace / threshold / health) without a model download — the
store is the new, risky infra here, not the embedder.
"""
from __future__ import annotations

import os
import uuid

import pytest

qdrant_client = pytest.importorskip("qdrant_client")

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")


def _qdrant_reachable() -> bool:
    try:
        # check_compatibility=False: this probe handles "down" itself; skip the
        # noisy server-version warning it would otherwise emit at collection time.
        client = qdrant_client.QdrantClient(url=QDRANT_URL, timeout=1.0, check_compatibility=False)
        client.get_collections()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _qdrant_reachable(), reason=f"Qdrant not reachable at {QDRANT_URL}"
)

# Imported after the skip guard so collection never fails when the dep/server is absent.
from rag.embedders import FakeEmbedder  # noqa: E402
from rag.ports import Chunk, RagConfig  # noqa: E402
from rag.service import RagService  # noqa: E402
from rag.stores_qdrant import QdrantVectorStore  # noqa: E402


def _embed(embedder: FakeEmbedder, source: str, texts: list[str]) -> list[Chunk]:
    vecs = embedder.embed(texts)
    return [Chunk(source, i, t, v) for i, (t, v) in enumerate(zip(texts, vecs))]


@pytest.fixture
def store():
    """A QdrantVectorStore backed by a throwaway collection, dropped on teardown."""
    cfg = RagConfig(collection=f"test_kb_{uuid.uuid4().hex[:8]}", qdrant_url=QDRANT_URL)
    s = QdrantVectorStore(cfg)
    try:
        yield s
    finally:
        try:
            s._client.delete_collection(cfg.collection)
        except Exception:
            pass


# ── S08.1 health ─────────────────────────────────────────────────────────────
def test_health_ok_and_count(store):
    h = store.health()
    assert h["ok"] is True and h["count"] == 0  # collection created lazily on first upsert
    store.upsert(_embed(FakeEmbedder(), "a.md", ["alpha alpha alpha"]))
    assert store.health()["count"] == 1


# ── S08.3 re-ingest replace ──────────────────────────────────────────────────
def test_reingest_replaces_source(store):
    emb = FakeEmbedder()
    store.upsert(_embed(emb, "a.md", ["alpha", "beta"]))
    assert store.health()["count"] == 2
    assert store.delete_by_source("a.md") == 2
    store.upsert(_embed(emb, "a.md", ["alpha only"]))
    assert store.health()["count"] == 1  # old chunks gone, no duplicates


# ── S08.4 search threshold + fields ──────────────────────────────────────────
def test_search_threshold_and_fields(store):
    emb = FakeEmbedder()
    store.upsert(_embed(emb, "match.md", ["alpha alpha alpha"]))
    store.upsert(_embed(emb, "other.md", ["zeta zeta zeta"]))
    qvec = emb.embed(["alpha alpha alpha"])[0]
    hits = store.search(qvec, top_k=5, score_threshold=0.8)
    assert len(hits) == 1  # disjoint "zeta" doc scores 0.0, filtered server-side
    assert hits[0].source == "match.md" and hits[0].chunk_index == 0
    assert hits[0].score >= 0.8


# ── end-to-end through the service (health gate + sandbox + ingest + search) ──
def test_service_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "kb.md").write_text("alpha alpha alpha", encoding="utf-8")
    cfg = RagConfig(collection=f"test_kb_{uuid.uuid4().hex[:8]}", qdrant_url=QDRANT_URL)
    store = QdrantVectorStore(cfg)
    svc = RagService(store, FakeEmbedder(), cfg)
    try:
        assert svc.health()["ok"] is True
        ingest = svc.ingest(".")
        assert ingest["ok"] is True and ingest["files"] == 1
        out = svc.search("alpha alpha alpha")
        assert out["ok"] is True and out["count"] == 1
        assert "kb.md" in out["hits"][0]["source"]
    finally:
        try:
            store._client.delete_collection(cfg.collection)
        except Exception:
            pass
