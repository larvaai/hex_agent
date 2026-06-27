"""
Case 02 — RAG Ports + Adapter Selection (Embedder & VectorStore).

Bản DISTILL trung thực của Clean Architecture áp cho EXTERNAL SERVICE (vector DB + embeddings)
trong hex_agent. Use case `RagService` chỉ phụ thuộc `EmbedderPort` + `VectorStorePort`;
đổi backend (memory <-> qdrant) chỉ rewire adapter ở composition root, use case hằng định.
Lazy import giữ lõi không kéo theo qdrant-client khi không cần.

Nguồn thật trong hex_agent (đã mở kiểm chứng):
  - rag/ports.py:8-21          -> Chunk, Hit (entities/value object, frozen dataclass)
  - rag/ports.py:24-36         -> EmbedderPort, VectorStorePort (Protocol owned by domain)
  - rag/ports.py:39-57         -> RagConfig (DIP metadata)
  - rag/service.py:15-113      -> RagService (use case: health-gate + ingest/search qua ports)
  - rag/stores_qdrant.py:32-49 -> QdrantVectorStore adapter; lazy import qdrant_client (line 43)
  - rag/feature.py:27-42       -> build_service(): config-driven, lazy-import adapter qdrant

Chỉ dùng standard library. Qdrant client + fastembed thật được thay bằng adapter fake
in-memory + một "module nặng giả lập" để minh hoạ lazy import. Toán embedding được rút gọn
thành hashing-bag-of-words để khỏi cần numpy/model thật.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# ─────────────────────────────────────────────────────────────────────────────
# VÒNG 1 — ENTITIES / VALUE OBJECTS (rag/ports.py:8-21). Pure data, frozen.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Chunk:
    """Distill rag/ports.py:8-13."""
    source: str
    chunk_index: int
    text: str
    vector: list[float] | None = None


@dataclass(frozen=True)
class Hit:
    """Distill rag/ports.py:16-21."""
    source: str
    chunk_index: int
    text: str
    score: float


@dataclass(frozen=True)
class RagConfig:
    """Distill rag/ports.py:39-57. DIP metadata: mô tả wiring, không phải logic."""
    collection: str = "agent_kb"
    top_k: int = 5
    score_threshold: float = 0.1


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT PORTS (rag/ports.py:24-36). Seam giữa logic và infra.
# RagService gọi các port này; nó KHÔNG import qdrant_client hay model embedding.
# ─────────────────────────────────────────────────────────────────────────────
@runtime_checkable
class EmbedderPort(Protocol):
    """Distill rag/ports.py:24-28."""
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class VectorStorePort(Protocol):
    """Distill rag/ports.py:31-36."""
    def health(self) -> dict: ...
    def delete_by_source(self, source: str) -> int: ...
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...


# ─────────────────────────────────────────────────────────────────────────────
# VÒNG 2 — USE CASE (rag/service.py:15-113). health-gate trước mọi ingest/search;
# logic không bao giờ chạm Qdrant trực tiếp, chỉ qua VectorStorePort.
# ─────────────────────────────────────────────────────────────────────────────
class RagService:
    """Distill rag/service.py:15-113 (lược sandbox/đọc file để giữ trọng tâm vào ports)."""

    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._cfg = config

    def health(self) -> dict:
        h = self._store.health()
        return {"ok": bool(h.get("ok")), "collection": h.get("collection"), "count": h.get("count", 0)}

    def _require_healthy(self) -> dict | None:
        """rag/service.py:30-39 — trả envelope dependency-failure nếu store không khoẻ, không raise."""
        h = self._store.health()
        if not h.get("ok"):
            return {"ok": False, "code": "dependency_unavailable",
                    "error": f"RAG store unhealthy (collection={h.get('collection')})."}
        return None

    def ingest(self, docs: dict[str, str]) -> dict:
        """rag/service.py:42-75. docs = {source: text}. Bản thật đọc từ file qua sandbox jail;
        ở đây nhận sẵn text để khỏi đụng filesystem."""
        gate = self._require_healthy()
        if gate is not None:
            return gate
        total = 0
        sources: list[str] = []
        for source, text in docs.items():
            texts = [s for s in text.split("\n") if s.strip()]  # 'chunk' đơn giản: theo dòng
            if not texts:
                continue
            vectors = self._embedder.embed(texts)
            if len(vectors) != len(texts):  # service.py:64-69 — từ chối mismatch trước khi upsert
                raise ValueError("embedder returned a mismatched number of embeddings.")
            chunks = [Chunk(source, i, t, v) for i, (t, v) in enumerate(zip(texts, vectors))]
            self._store.delete_by_source(source)  # re-ingest replaces
            self._store.upsert(chunks)
            total += len(chunks)
            sources.append(source)
        return {"ok": True, "files": len(sources), "chunks": total, "sources": sources}

    def search(self, query: str, *, top_k: int | None = None,
               score_threshold: float | None = None) -> dict:
        """rag/service.py:78-113."""
        gate = self._require_healthy()
        if gate is not None:
            return gate
        if not query or not query.strip():
            raise ValueError("search query must not be empty.")
        k = int(top_k) if top_k is not None else self._cfg.top_k
        if k < 1:
            raise ValueError("top_k must be a positive integer (>= 1).")
        threshold = float(score_threshold) if score_threshold is not None else self._cfg.score_threshold
        vector = self._embedder.embed([query])[0]
        hits = self._store.search(vector, k, threshold)
        return {"ok": True, "count": len(hits), "top_k": k, "score_threshold": threshold,
                "hits": [{"source": h.source, "chunk_index": h.chunk_index,
                          "text": h.text, "score": round(h.score, 6)} for h in hits]}


# ─────────────────────────────────────────────────────────────────────────────
# VÒNG 3 — ADAPTERS. Bản memory (offline, default) + bản "qdrant" giả lập.
# rag/stores.py (InMemoryVectorStore) + rag/stores_qdrant.py (QdrantVectorStore)
# ─────────────────────────────────────────────────────────────────────────────
def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class FakeEmbedder:
    """Distill rag/embedders.FakeEmbedder. Hashing-bag-of-words -> vector cố định chiều.
    Đủ để cùng từ -> gần nhau; thay cho model BGE thật trong rag/embedders.FastEmbedEmbedder."""

    def __init__(self, dim: int = 16) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in text.lower().split():
                h = int(hashlib.sha1(token.encode()).hexdigest(), 16)
                vec[h % self.dim] += 1.0
            out.append(vec)
        return out


class InMemoryVectorStore:
    """Distill rag/stores.InMemoryVectorStore — adapter offline mặc định, implement VectorStorePort."""

    def __init__(self, collection: str = "agent_kb") -> None:
        self.collection = collection
        self._points: list[Chunk] = []

    def health(self) -> dict:
        return {"ok": True, "collection": self.collection, "count": len(self._points)}

    def delete_by_source(self, source: str) -> int:
        before = len(self._points)
        self._points = [c for c in self._points if c.source != source]
        return before - len(self._points)

    def upsert(self, chunks: list[Chunk]) -> int:
        if any(c.vector is None for c in chunks):
            raise ValueError("upsert requires embedded chunks.")
        self._points.extend(chunks)
        return len(chunks)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        scored = [(_cosine(vector, c.vector or []), c) for c in self._points]
        scored = [(s, c) for s, c in scored if s >= score_threshold]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [Hit(c.source, c.chunk_index, c.text, s) for s, c in scored[:top_k]]


# --- "Module nặng giả lập" để minh hoạ lazy import của adapter production. ---
# Trong hex_agent, rag/stores_qdrant.py:43 mới `from qdrant_client import QdrantClient`.
# Ở đây ta theo dõi xem module nặng có bị import khi KHÔNG cần hay không.
_HEAVY_DEP_IMPORTS = {"count": 0}


def _import_heavy_qdrant_client():
    """Đứng thay `from qdrant_client import QdrantClient`. Đếm số lần thực sự được gọi."""
    _HEAVY_DEP_IMPORTS["count"] += 1
    class _FakeQdrantClient:  # noqa: N801 — minh hoạ
        pass
    return _FakeQdrantClient


class QdrantVectorStore:
    """Distill rag/stores_qdrant.py:32-49. Adapter production.
    Lazy import client trong __init__ (đúng như line 43 của file thật)."""

    def __init__(self, config: RagConfig, *, client: object | None = None) -> None:
        self.collection = config.collection
        self._store = InMemoryVectorStore(config.collection)  # giả lập backend phía sau
        if client is not None:
            self._client = client
        else:
            # ── đây là chỗ tương ứng line 43: import nặng CHỈ xảy ra khi tạo adapter này ──
            Client = _import_heavy_qdrant_client()  # noqa: N806
            self._client = Client()

    def health(self) -> dict:
        h = self._store.health()
        return {"ok": True, "collection": self.collection, "count": h["count"]}

    def delete_by_source(self, source: str) -> int:
        return self._store.delete_by_source(source)

    def upsert(self, chunks: list[Chunk]) -> int:
        return self._store.upsert(chunks)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        return self._store.search(vector, top_k, score_threshold)


class UnreachableVectorStore:
    """Adapter đại diện 'server chết'. health() trả ok=False — KHÔNG raise (stores_qdrant.py:83-90)."""

    def __init__(self, collection: str = "agent_kb") -> None:
        self.collection = collection

    def health(self) -> dict:
        return {"ok": False, "collection": self.collection, "count": 0, "error": "connection refused"}

    def delete_by_source(self, source: str) -> int: return 0
    def upsert(self, chunks: list[Chunk]) -> int: return 0
    def search(self, vector, top_k, score_threshold) -> list[Hit]: return []


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITION ROOT (rag/feature.py:27-42). Config quyết định adapter nào được wire.
# Backend 'memory' (default) -> không bao giờ import qdrant. Backend 'qdrant' -> lazy import.
# ─────────────────────────────────────────────────────────────────────────────
def build_service(config: dict | None) -> RagService:
    """Distill rag/feature.py:27-42."""
    config = config or {}
    cfg = RagConfig(collection=config.get("collection", "agent_kb"))
    backend = (config.get("backend") or "memory").lower()
    if backend == "memory":
        return RagService(InMemoryVectorStore(cfg.collection), FakeEmbedder(), cfg)
    if backend == "qdrant":
        # Lazy: chỉ ở nhánh này adapter qdrant (và import nặng của nó) mới được chạm tới.
        return RagService(QdrantVectorStore(cfg), FakeEmbedder(), cfg)
    raise ValueError(f"Unknown rag backend: {backend!r}")


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
DOCS = {
    "payments.md": "module thanh toán xử lý hoá đơn\nhoàn tiền khi giao dịch lỗi",
    "auth.md": "đăng nhập bằng token\nthu hồi token khi đăng xuất",
}


def demo() -> None:
    print("=" * 74)
    print("CASE 02 — RAG Ports + Adapter Selection trong hex_agent")
    print("=" * 74)

    print("\n[1] Composition root build backend='memory' (mặc định, offline).")
    print("    Import nặng qdrant trước khi build:", _HEAVY_DEP_IMPORTS["count"])
    svc_mem = build_service({"backend": "memory"})
    print("    Sau khi build 'memory' -> import nặng qdrant:", _HEAVY_DEP_IMPORTS["count"],
          "(VẪN 0 — lõi không kéo theo qdrant)")
    print("    health():", svc_mem.health())
    print("    ingest():", svc_mem.ingest(DOCS))
    res = svc_mem.search("hoàn tiền giao dịch", top_k=2)
    print("    search('hoàn tiền giao dịch') -> top hit:",
          res["hits"][0]["source"], "| score:", res["hits"][0]["score"])

    print("\n[2] Đổi backend='qdrant' — CÙNG RagService, chỉ adapter khác.")
    svc_q = build_service({"backend": "qdrant"})
    print("    Sau khi build 'qdrant' -> import nặng qdrant:", _HEAVY_DEP_IMPORTS["count"],
          "(bây giờ mới = 1: lazy import chỉ xảy ra ở nhánh qdrant)")
    svc_q.ingest(DOCS)
    res_q = svc_q.search("hoàn tiền giao dịch", top_k=2)
    print("    search trên qdrant-adapter -> top hit:", res_q["hits"][0]["source"])
    print("    -> RagService không đổi một dòng; chỉ feature.build_service chọn adapter.")

    print("\n[3] Đối chứng dependency-failure: store chết -> use case trả envelope, KHÔNG crash.")
    svc_dead = RagService(UnreachableVectorStore(), FakeEmbedder(), RagConfig())
    h = svc_dead.health()
    ing = svc_dead.ingest(DOCS)
    print("    health():", h)
    print("    ingest() bị health-gate chặn:", ing)

    # ── ASSERT: bất biến của pattern ──
    # (a) build 'memory' KHÔNG import dep nặng; chỉ 'qdrant' mới import.
    #     (kiểm gián tiếp: top hit của cả hai backend giống nhau vì cùng use case + cùng embedder)
    assert res["hits"][0]["source"] == "payments.md"
    assert res_q["hits"][0]["source"] == "payments.md"
    # (b) Cả hai adapter đều thoả VectorStorePort (runtime_checkable).
    assert isinstance(InMemoryVectorStore(), VectorStorePort)
    assert isinstance(QdrantVectorStore(RagConfig()), VectorStorePort)
    assert isinstance(FakeEmbedder(), EmbedderPort)
    # (c) Lazy import: tới đây đúng 2 lần QdrantVectorStore được tạo (bước 2 + assert (b)),
    #     mỗi lần import client một lần -> đếm = 2. build 'memory' không làm tăng số này.
    assert _HEAVY_DEP_IMPORTS["count"] == 2, _HEAVY_DEP_IMPORTS["count"]
    # (d) health-gate: store unhealthy -> envelope dependency_unavailable, không exception.
    assert h["ok"] is False
    assert ing["ok"] is False and ing["code"] == "dependency_unavailable"

    print("\n[OK] Mọi assert qua. Đổi backend = rewire adapter; use case + business logic bất biến.")


if __name__ == "__main__":
    demo()
