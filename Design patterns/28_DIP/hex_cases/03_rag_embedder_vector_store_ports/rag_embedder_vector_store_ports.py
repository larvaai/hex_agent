"""
Case 03 — DIP: EmbedderPort & VectorStorePort — tách hạ tầng RAG khỏi logic
============================================================================

Bản DISTILL TRUNG THỰC từ hex_agent:

  - rag/ports.py:24-28
        @runtime_checkable
        class EmbedderPort(Protocol):     # dim + embed(texts) -> ABSTRACTION do domain rag/ sở hữu
  - rag/ports.py:31-36
        @runtime_checkable
        class VectorStorePort(Protocol):  # health/delete_by_source/upsert/search
  - rag/embedders.py:33-46
        class FakeEmbedder:               # adapter: deterministic, offline (test, không tải model)
  - rag/embedders.py:49-60
        class FastEmbedEmbedder:          # adapter: production (fastembed, lazy import dòng 53)
  - rag/stores_qdrant.py:32-49
        class QdrantVectorStore:          # adapter: production, bọc qdrant-client (lazy import dòng 43)
  - rag/service.py:15-19
        class RagService:                 # CẤP CAO nhận store + embedder + config qua constructor (DI),
                                          # chỉ gọi method của port — KHÔNG biết backend cụ thể.

Ý tưởng DIP ở đây:
  * rag/ (domain, cấp cao) ĐỊNH NGHĨA 2 cái nó cần: embed text + thao tác vector store.
    docstring rag/ports.py:1 gọi đây là "the seam between logic and infra".
  * Embedder/store cụ thể là adapter. FakeEmbedder cho test offline; Qdrant cho production.
  * RagService chỉ import ports.py; KHÔNG import qdrant_client/fastembed (lazy trong adapter).
  * Swap embedder/store (Fake -> FastEmbed, InMemory -> Qdrant) -> RagService BẤT BIẾN.

Bản rút gọn này thay fastembed + qdrant-client + workspace sandbox + chunking file thật
bằng fake stdlib. FakeEmbedder giữ đúng tinh thần bản gốc: bag-of-words hash chuẩn hoá,
nên text giống nhau cosine ~1.0, text rời rạc ~0.0 (đủ để kích score threshold).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# ───────────────────────────────────────────────────────────────────────────
# Value types (mô phỏng rag/ports.py:8-21)
# ───────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Chunk:
    source: str
    chunk_index: int
    text: str
    vector: list[float] | None = None


@dataclass(frozen=True)
class Hit:
    source: str
    chunk_index: int
    text: str
    score: float


@dataclass(frozen=True)
class RagConfig:
    collection: str = "agent_kb"
    score_threshold: float = 0.8
    top_k: int = 5


# ───────────────────────────────────────────────────────────────────────────
# 1) ABSTRACTIONS — sống ở "cấp cao" rag/ (mô phỏng rag/ports.py:24-36)
# ───────────────────────────────────────────────────────────────────────────
@runtime_checkable
class EmbedderPort(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class VectorStorePort(Protocol):
    def health(self) -> dict: ...
    def delete_by_source(self, source: str) -> int: ...
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...


# ───────────────────────────────────────────────────────────────────────────
# 2) EMBEDDER ADAPTERS (mô phỏng rag/embedders.py:33-60)
# ───────────────────────────────────────────────────────────────────────────
def _tokenize(text: str) -> list[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if t]


def _bucket(token: str, dim: int) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dim


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return vec if norm == 0.0 else [x / norm for x in vec]


class FakeEmbedder:
    """Deterministic offline embedder (no network, no model). (rag/embedders.py:33-46)"""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            vec[_bucket(tok, self.dim)] += 1.0
        return _normalize(vec)


class StubFastEmbedEmbedder:
    """Stand-in cho FastEmbedEmbedder (rag/embedders.py:49-60).

    Bản gốc lazy-import 'fastembed' ở constructor (dòng 53). Ở đây ta KHÔNG import gì
    bên ngoài — chỉ minh hoạ rằng một adapter production khác cũng thoả EmbedderPort,
    cùng .dim + .embed(). Logic vector tái dùng FakeEmbedder cho gọn.
    """

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5", dim: int = 64) -> None:
        self.model = model
        self.dim = dim
        self._impl = FakeEmbedder(dim)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._impl.embed(texts)


# ───────────────────────────────────────────────────────────────────────────
# 3) VECTOR STORE ADAPTERS
#    InMemoryVectorStore (như rag/stores.py có) + StubQdrantVectorStore (như stores_qdrant.py)
# ───────────────────────────────────────────────────────────────────────────
def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))   # vector đã chuẩn hoá nên dot == cosine


class InMemoryVectorStore:
    """Vector store trong bộ nhớ — fake cho test, không backend. Thoả VectorStorePort."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._healthy = True

    def set_healthy(self, ok: bool) -> None:
        self._healthy = ok

    def health(self) -> dict:
        return {"ok": self._healthy, "collection": "memory", "count": len(self._chunks)}

    def delete_by_source(self, source: str) -> int:
        before = len(self._chunks)
        self._chunks = [c for c in self._chunks if c.source != source]
        return before - len(self._chunks)

    def upsert(self, chunks: list[Chunk]) -> int:
        self._chunks.extend(chunks)
        return len(chunks)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        scored = []
        for c in self._chunks:
            if c.vector is None:
                continue
            score = _cosine(vector, c.vector)
            if score >= score_threshold:
                scored.append(Hit(c.source, c.chunk_index, c.text, score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]


class StubQdrantVectorStore:
    """Stand-in cho QdrantVectorStore (rag/stores_qdrant.py:32-49).

    Bản gốc lazy-import 'qdrant_client' ở constructor (dòng 43) và cho phép tiêm
    ``client`` để test. Ở đây ta tiêm 1 'client' giả là InMemoryVectorStore để cho thấy:
    cùng VectorStorePort, một backend production có thể drop-in mà RagService không đổi.
    """

    def __init__(self, config: RagConfig, *, client: object | None = None) -> None:
        self._cfg = config
        # bản gốc: if client is None: from qdrant_client import QdrantClient(...)
        self._client = client or InMemoryVectorStore()

    def health(self) -> dict:
        h = self._client.health()
        return {"ok": h["ok"], "collection": self._cfg.collection, "count": h["count"]}

    def delete_by_source(self, source: str) -> int:
        return self._client.delete_by_source(source)

    def upsert(self, chunks: list[Chunk]) -> int:
        return self._client.upsert(chunks)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        return self._client.search(vector, top_k, score_threshold)


# ───────────────────────────────────────────────────────────────────────────
# 4) CẤP CAO tiêu thụ — RagService (mô phỏng rag/service.py:15-...)
#    Constructor nhận VectorStorePort + EmbedderPort + RagConfig. Chỉ gọi method của port.
# ───────────────────────────────────────────────────────────────────────────
class RagService:
    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._cfg = config

    def _require_healthy(self) -> dict | None:
        h = self._store.health()
        if not h.get("ok"):
            return {"ok": False, "code": "dependency_unavailable",
                    "error": f"RAG store unhealthy (collection={h.get('collection')})."}
        return None

    def ingest(self, source: str, texts: list[str]) -> dict:
        """Gate health -> embed -> delete cũ -> upsert. (mô phỏng rag/service.py:42-75)"""
        gate = self._require_healthy()
        if gate is not None:
            return gate
        vectors = self._embedder.embed(texts)
        if len(vectors) != len(texts):
            raise ValueError(
                f"embedder returned {len(vectors)} embeddings for {len(texts)} chunks (count mismatch)."
            )
        chunks = [Chunk(source, i, t, v) for i, (t, v) in enumerate(zip(texts, vectors))]
        self._store.delete_by_source(source)   # re-ingest replaces previous chunks
        self._store.upsert(chunks)
        return {"ok": True, "source": source, "chunks": len(chunks)}

    def search(self, query: str, *, top_k: int | None = None,
               score_threshold: float | None = None) -> dict:
        """Gate health -> validate -> embed query -> search. (mô phỏng rag/service.py:78-113)"""
        gate = self._require_healthy()
        if gate is not None:
            return gate
        if not query or not query.strip():
            raise ValueError("search query must not be empty.")
        k = int(top_k) if top_k is not None else self._cfg.top_k
        threshold = float(score_threshold) if score_threshold is not None else self._cfg.score_threshold
        vector = self._embedder.embed([query])[0]
        hits = self._store.search(vector, k, threshold)
        return {
            "ok": True,
            "count": len(hits),
            "hits": [{"source": h.source, "chunk_index": h.chunk_index,
                      "text": h.text, "score": round(h.score, 6)} for h in hits],
        }


# ───────────────────────────────────────────────────────────────────────────
# COMPOSITION ROOT / FACTORY (mô phỏng rag/feature.py:build_service)
# ───────────────────────────────────────────────────────────────────────────
def build_service(*, backend: str, config: RagConfig) -> RagService:
    """Chọn adapter dựa config; RagService nhận chúng qua DI."""
    embedder: EmbedderPort = FakeEmbedder(dim=64)
    store: VectorStorePort
    if backend == "qdrant":
        store = StubQdrantVectorStore(config)         # production adapter
    else:
        store = InMemoryVectorStore()                 # fake/offline adapter
    return RagService(store, embedder, config)


# ───────────────────────────────────────────────────────────────────────────
# DEMO
# ───────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 72)
    print("CASE 03 — EmbedderPort & VectorStorePort (DIP)")
    print("=" * 72)

    cfg = RagConfig(score_threshold=0.3, top_k=3)

    # --- Ingest + search với FakeEmbedder + InMemoryVectorStore (test offline) ---
    print("\n[1] RagService với FakeEmbedder + InMemoryVectorStore (offline, không backend).")
    svc = RagService(InMemoryVectorStore(), FakeEmbedder(dim=64), cfg)
    print("    health ->", svc._store.health())
    r_ing = svc.ingest("kb/notes.md", [
        "Dependency Inversion Principle keeps high level modules independent",
        "Cats and dogs are friendly pets at home",
    ])
    print("    ingest ->", r_ing)
    assert r_ing["ok"] and r_ing["chunks"] == 2

    r_search = svc.search("dependency inversion principle modules")
    print("    search 'dependency inversion ...' ->", r_search)
    assert r_search["ok"] and r_search["count"] >= 1
    assert r_search["hits"][0]["source"] == "kb/notes.md"
    assert "Dependency Inversion" in r_search["hits"][0]["text"]

    # --- Bất biến: text giống nhau cosine ~1.0 ---
    print("\n[2] Bất biến embedder: cùng text -> cosine ~1.0; text rời rạc -> thấp.")
    emb = FakeEmbedder(dim=64)
    v1 = emb.embed(["dependency inversion principle"])[0]
    v2 = emb.embed(["dependency inversion principle"])[0]
    v3 = emb.embed(["totally unrelated kitchen recipe"])[0]
    same = _cosine(v1, v2)
    diff = _cosine(v1, v3)
    print(f"    cosine(same)={same:.4f}  cosine(diff)={diff:.4f}")
    assert abs(same - 1.0) < 1e-9 and diff < 0.5

    # --- Swap STORE (InMemory -> StubQdrant) mà KHÔNG đụng RagService ---
    print("\n[3] Swap store: InMemory -> StubQdrant. RagService KHÔNG đổi 1 dòng.")
    svc_q = build_service(backend="qdrant", config=cfg)
    svc_q.ingest("kb/notes.md", ["high level policy depends on abstraction not detail"])
    rq = svc_q.search("abstraction policy")
    print("    qdrant-backed search ->", rq)
    assert rq["ok"] and rq["count"] >= 1

    # --- Swap EMBEDDER (Fake -> StubFastEmbed) qua DI ---
    print("\n[4] Swap embedder: FakeEmbedder -> StubFastEmbedEmbedder qua constructor.")
    svc_fe = RagService(InMemoryVectorStore(), StubFastEmbedEmbedder(dim=64), cfg)
    svc_fe.ingest("kb/x.md", ["ports define the seam between logic and infra"])
    rfe = svc_fe.search("seam between logic and infra")
    print("    fastembed-stub search ->", rfe)
    assert rfe["ok"] and rfe["count"] >= 1

    # --- Health gate: store hỏng -> trả lỗi phụ thuộc, không crash ---
    print("\n[5] Health gate: store unhealthy -> envelope dependency_unavailable (không I/O bừa).")
    bad_store = InMemoryVectorStore()
    bad_store.set_healthy(False)
    svc_bad = RagService(bad_store, FakeEmbedder(), cfg)
    rbad = svc_bad.search("anything")
    print("    search khi store hỏng ->", rbad)
    assert rbad["ok"] is False and rbad["code"] == "dependency_unavailable"

    # --- Bằng chứng DIP ---
    print("\n[6] Bất biến DIP: mọi adapter thoả đúng port (structural).")
    assert isinstance(FakeEmbedder(), EmbedderPort)
    assert isinstance(StubFastEmbedEmbedder(), EmbedderPort)
    assert isinstance(InMemoryVectorStore(), VectorStorePort)
    assert isinstance(StubQdrantVectorStore(cfg), VectorStorePort)
    print("    Fake/StubFastEmbed -> EmbedderPort; InMemory/StubQdrant -> VectorStorePort.")

    # --- ĐỐI CHỨNG ---
    print("\n[7] ĐỐI CHỨNG — nếu RagService import thẳng qdrant_client + fastembed:")
    print("    Unit test phải dựng Qdrant (docker) + tải model -> chậm, phụ thuộc mạng.")
    print("    Đổi sang Pinecone/Weaviate -> sửa RagService. Với DIP: thêm 1 adapter, 0 sửa logic.")

    print("\nTẤT CẢ ASSERT PASS. DIP biến RagService thành logic thuần, test offline, swap backend dễ.\n")


if __name__ == "__main__":
    demo()
