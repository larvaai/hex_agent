"""
Case 02 — RAG Service: Backend Strategy Selection (Memory vs "Qdrant")
=====================================================================

Bản DISTILL TRUNG THỰC từ hex_agent. Nguồn thật:
  - rag/ports.py:24-36         -> EmbedderPort + VectorStorePort (2 Strategy interface, Protocol)
  - rag/ports.py:8-22          -> Chunk, Hit value types
  - rag/embedders.py:33-46     -> FakeEmbedder (offline, hash bag-of-words, no-model)
  - rag/embedders.py:49-60     -> FastEmbedEmbedder (production, lazy-import fastembed)
  - rag/stores.py:24-56        -> InMemoryVectorStore (cosine search trong tiến trình)
  - rag/stores_qdrant.py:32-49 -> QdrantVectorStore (production, lazy-import qdrant_client)
  - rag/service.py:15-39       -> RagService = Context, delegate cho store/embedder
  - rag/feature.py:27-42       -> build_service(): chọn/inject strategy theo config['backend']

Đây là Strategy "chuẩn sách giáo khoa" nhất trong hex_agent:
  * 2 trục chiến lược trực giao: cách EMBED (FakeEmbedder vs FastEmbedEmbedder) và
    cách LƯU/TÌM vector (InMemory vs Qdrant).
  * Cả hai phía đều thỏa Protocol cấu trúc (duck typing, KHÔNG cần kế thừa).
  * RagService (Context) hoàn toàn KHÔNG biết backend nào đang chạy — nó chỉ gọi
    self._embedder.embed(...) và self._store.search(...).
  * Chọn strategy bằng config['backend'] tại factory build_service() — runtime selection.

Distill này thay fastembed (model thật, network) và Qdrant (HTTP server) bằng:
  - FakeEmbedder: y nguyên thuật toán hash bag-of-words của code thật.
  - "SlowQdrantLikeStore": fake một backend "production" CÙNG interface — vẫn cosine
    trong-tiến-trình nhưng mô phỏng latency + persistence (đếm số điểm đã ghi) để cho
    thấy trade-off, KHÔNG đụng network. Đây chính là điểm "thay hạ tầng nặng bằng fake".

CHẠY: python3 rag_backend_selection.py   (exit 0, không traceback)
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

_TOKEN_RE = re.compile(r"\w+")


# ─────────────────────────────────────────────────────────────────────────────
# VALUE TYPES — rag/ports.py:8-22
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY INTERFACES — rag/ports.py:24-36 (Protocol, structural)
# ─────────────────────────────────────────────────────────────────────────────
@runtime_checkable
class EmbedderPort(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class VectorStorePort(Protocol):
    def health(self) -> dict: ...
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...


# ─────────────────────────────────────────────────────────────────────────────
# CONCRETE STRATEGY (EMBED) — FakeEmbedder (rag/embedders.py:33-46)
# Thuật toán giữ NGUYÊN bản: normalized bag-of-words hash. Text giống nhau -> cosine 1.0.
# ─────────────────────────────────────────────────────────────────────────────
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
    """Embedder offline tất định (không network, không model)."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            vec[_bucket(tok, self.dim)] += 1.0
        return _normalize(vec)


class HeavyEmbedder:
    """Đại diện cho FastEmbedEmbedder (rag/embedders.py:49-60): trong code thật nó
    lazy-import fastembed và tải model. Ở đây ta CHỈ mô phỏng đặc tính 'nặng' (latency
    khởi tạo + per-call) nhưng dùng lại thuật toán fake để chạy offline. CÙNG interface
    EmbedderPort nên RagService không phân biệt."""

    def __init__(self, dim: int = 64, init_latency_ms: float = 0.0) -> None:
        # lazy "model load" — code thật: from fastembed import TextEmbedding
        time.sleep(init_latency_ms / 1000.0)
        self.dim = dim
        self._inner = FakeEmbedder(dim)
        self.loaded = True

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._inner.embed(texts)


# ─────────────────────────────────────────────────────────────────────────────
# CONCRETE STRATEGY (STORE) — InMemoryVectorStore (rag/stores.py:24-56)
# ─────────────────────────────────────────────────────────────────────────────
def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """Store offline; cosine search tất định, 0 latency, mất khi tiến trình kết thúc."""

    def __init__(self, *, collection: str = "agent_kb", healthy: bool = True) -> None:
        self.collection = collection
        self._healthy = healthy
        self._chunks: list[Chunk] = []

    def set_healthy(self, value: bool) -> None:
        self._healthy = value

    def health(self) -> dict:
        return {"ok": self._healthy, "collection": self.collection, "count": len(self._chunks)}

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


class PersistentLikeStore:
    """Đại diện cho QdrantVectorStore (rag/stores_qdrant.py:32-49): code thật mở HTTP
    tới Qdrant server, tạo collection lazily, id tất định để upsert idempotent. Ở đây
    ta mô phỏng đặc tính 'production' (latency mỗi query + persistence) bằng một dict
    'đĩa giả' — KHÔNG network. CÙNG interface VectorStorePort nên RagService không đổi.

    'Persistence' mô phỏng: cho phép truyền lại _disk để dữ liệu sống qua nhiều instance."""

    def __init__(self, *, collection: str = "agent_kb", query_latency_ms: float = 0.0,
                 disk: list[Chunk] | None = None) -> None:
        self.collection = collection
        self._latency = query_latency_ms / 1000.0
        self._disk: list[Chunk] = disk if disk is not None else []  # "đĩa" tồn tại lâu dài

    def health(self) -> dict:
        return {"ok": True, "collection": self.collection, "count": len(self._disk)}

    def upsert(self, chunks: list[Chunk]) -> int:
        self._disk.extend(chunks)  # ghi xuống "đĩa"
        return len(chunks)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        time.sleep(self._latency)  # mô phỏng round-trip mạng
        hits = [Hit(c.source, c.chunk_index, c.text, _cosine(vector, c.vector))
                for c in self._disk if c.vector is not None
                if _cosine(vector, c.vector) >= score_threshold]
        hits.sort(key=lambda h: (-h.score, h.source, h.chunk_index))
        return hits[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT — RagService (rag/service.py:15-39, rút gọn + thêm ingest/search tối thiểu)
# Delegate cho strategy; KHÔNG biết backend nào. Health-gate trước mọi search/ingest.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RagConfig:
    collection: str = "agent_kb"
    top_k: int = 5
    score_threshold: float = 0.3


class RagService:
    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._cfg = config

    def health(self) -> dict:
        h = self._store.health()
        return {"ok": bool(h.get("ok")), "collection": h.get("collection"), "count": h.get("count", 0)}

    def _require_healthy(self) -> dict | None:
        h = self._store.health()
        if not h.get("ok"):
            return {"ok": False, "code": "dependency_unavailable",
                    "error": f"RAG store unhealthy (collection={h.get('collection')})."}
        return None

    def ingest(self, docs: list[tuple[str, str]]) -> dict:
        """docs = [(source, text), ...]. Embed rồi upsert qua store strategy."""
        gate = self._require_healthy()
        if gate is not None:
            return gate
        texts = [t for _, t in docs]
        vectors = self._embedder.embed(texts)          # <-- delegate EMBED strategy
        chunks = [Chunk(src, i, txt, vec)
                  for i, ((src, txt), vec) in enumerate(zip(docs, vectors))]
        n = self._store.upsert(chunks)                 # <-- delegate STORE strategy
        return {"ok": True, "chunks": n}

    def search(self, query: str) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
        qvec = self._embedder.embed([query])[0]        # <-- delegate EMBED strategy
        hits = self._store.search(qvec, self._cfg.top_k, self._cfg.score_threshold)  # <-- STORE
        return {"ok": True, "count": len(hits),
                "hits": [{"source": h.source, "score": round(h.score, 4), "text": h.text} for h in hits]}


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY — build_service(): chọn strategy theo config (rag/feature.py:27-42)
# ─────────────────────────────────────────────────────────────────────────────
def build_service(config: dict | None, *, _shared_disk: list[Chunk] | None = None) -> RagService:
    config = config or {}
    cfg = RagConfig(
        collection=config.get("collection", "agent_kb"),
        top_k=config.get("top_k", 5),
        score_threshold=config.get("score_threshold", 0.3),
    )
    backend = (config.get("backend") or "memory").lower()
    if backend == "memory":
        store: VectorStorePort = InMemoryVectorStore(collection=cfg.collection)
        embedder: EmbedderPort = FakeEmbedder()
        return RagService(store, embedder, cfg)
    if backend == "qdrant":
        # code thật: lazy import FastEmbedEmbedder + QdrantVectorStore tại đây.
        store = PersistentLikeStore(collection=cfg.collection, query_latency_ms=2.0,
                                    disk=_shared_disk)
        embedder = HeavyEmbedder(init_latency_ms=1.0)
        return RagService(store, embedder, cfg)
    raise ValueError(f"Unknown rag backend: {backend!r}")


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — RagService nhồi if/elif backend vào TỪNG method (không Strategy)
# ─────────────────────────────────────────────────────────────────────────────
class HardcodedRagService:
    """Anti-pattern: Context tự if backend == 'memory' ... elif 'qdrant' bên trong
    MỖI method. Thêm backend thứ 3 (vd. pgvector) = sửa cả ingest lẫn search. Không
    test được logic RAG tách rời backend. Đây chính là cái Strategy loại bỏ."""

    def __init__(self, backend: str) -> None:
        self.backend = backend
        self._mem: list[Chunk] = []
        self._disk: list[Chunk] = []

    def search(self, query: str) -> dict:
        qvec = FakeEmbedder().embed([query])[0]
        if self.backend == "memory":
            pool = self._mem
        elif self.backend == "qdrant":
            time.sleep(0.002)  # latency lặp lại ở mọi method
            pool = self._disk
        else:
            raise ValueError(f"unknown backend {self.backend}")
        hits = sorted(
            (Hit(c.source, c.chunk_index, c.text, _cosine(qvec, c.vector)) for c in pool if c.vector),
            key=lambda h: -h.score)
        return {"ok": True, "count": len(hits)}


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
CORPUS = [
    ("doc/python.md", "Strategy pattern lets you swap algorithms at runtime in python"),
    ("doc/rag.md", "retrieval augmented generation embeds text into vectors for search"),
    ("doc/qdrant.md", "qdrant is a production vector database with persistence over network"),
]


def demo() -> None:
    print("=" * 72)
    print("CASE 02 — RAG Backend Strategy Selection (memory vs qdrant)")
    print("=" * 72)

    print("\n[1] CÙNG MỘT RagService API, đổi backend chỉ qua config['backend']\n")

    svc_mem = build_service({"backend": "memory", "score_threshold": 0.2})
    svc_mem.ingest(CORPUS)
    r_mem = svc_mem.search("swap algorithms at runtime")
    print(f"  backend=memory  -> count={r_mem['count']}, top={r_mem['hits'][0]['source']}")
    assert r_mem["ok"] and r_mem["count"] >= 1
    assert r_mem["hits"][0]["source"] == "doc/python.md", "query khớp doc python nhất"

    svc_q = build_service({"backend": "qdrant", "score_threshold": 0.2})
    svc_q.ingest(CORPUS)
    r_q = svc_q.search("swap algorithms at runtime")
    print(f"  backend=qdrant  -> count={r_q['count']}, top={r_q['hits'][0]['source']}")
    assert r_q["ok"] and r_q["hits"][0]["source"] == "doc/python.md"

    print("\n[2] BẤT BIẾN cốt lõi: kết quả ngữ nghĩa GIỐNG NHAU bất kể backend\n")
    top_mem = [h["source"] for h in r_mem["hits"]]
    top_q = [h["source"] for h in r_q["hits"]]
    print(f"  thứ tự hit (memory): {top_mem}")
    print(f"  thứ tự hit (qdrant): {top_q}")
    assert top_mem == top_q, "đổi STORE strategy không được đổi đúng-sai của logic RAG"
    print("  -> Context (RagService) không hề biết mình đang nói chuyện với backend nào.")

    print("\n[3] Trade-off đo được: qdrant strategy có latency, memory thì không\n")
    t0 = time.perf_counter()
    for _ in range(20):
        svc_mem.search("vectors")
    mem_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    for _ in range(20):
        svc_q.search("vectors")
    q_ms = (time.perf_counter() - t0) * 1000
    print(f"  20 truy vấn: memory={mem_ms:.2f}ms  vs  qdrant-like={q_ms:.2f}ms")
    assert q_ms > mem_ms, "qdrant strategy mô phỏng latency mạng -> chậm hơn"
    print("  -> đúng trade-off code thật: memory (nhanh, offline) vs qdrant (chậm, persistent).")

    print("\n[4] Persistence: 'qdrant' giữ dữ liệu qua instance mới; 'memory' thì mất\n")
    shared: list[Chunk] = []
    svc_q1 = build_service({"backend": "qdrant"}, _shared_disk=shared)
    svc_q1.ingest(CORPUS)
    svc_q2 = build_service({"backend": "qdrant"}, _shared_disk=shared)  # instance MỚI, cùng "đĩa"
    print(f"  qdrant instance#2 health.count = {svc_q2.health()['count']} (đọc lại từ đĩa)")
    assert svc_q2.health()["count"] == len(CORPUS), "qdrant strategy có persistence"
    svc_m2 = build_service({"backend": "memory"})
    print(f"  memory instance mới  health.count = {svc_m2.health()['count']} (rỗng, không persist)")
    assert svc_m2.health()["count"] == 0

    print("\n[5] Health-gate: store unhealthy -> RagService trả lỗi sạch, KHÔNG raise\n")
    bad_store = InMemoryVectorStore(healthy=False)
    svc_bad = RagService(bad_store, FakeEmbedder(), RagConfig())
    out = svc_bad.search("anything")
    print(f"  search khi store down -> ok={out['ok']}, code={out.get('code')}")
    assert out["ok"] is False and out["code"] == "dependency_unavailable"

    print("\n[6] Duck typing: cả 2 store thỏa Protocol VectorStorePort mà KHÔNG kế thừa\n")
    print(f"  isinstance(InMemoryVectorStore(), VectorStorePort) = {isinstance(InMemoryVectorStore(), VectorStorePort)}")
    print(f"  isinstance(PersistentLikeStore(), VectorStorePort) = {isinstance(PersistentLikeStore(), VectorStorePort)}")
    assert isinstance(InMemoryVectorStore(), VectorStorePort)
    assert isinstance(PersistentLikeStore(), VectorStorePort)
    assert isinstance(FakeEmbedder(), EmbedderPort)

    print("\n[7] ĐỐI CHỨNG — HardcodedRagService nhồi if/elif backend vào method\n")
    hk = HardcodedRagService("qdrant")
    hk.search("x")
    print("  search() phải tự biết backend, latency lặp ở mọi method.")
    print("  Thêm backend pgvector -> sửa MỌI method (ingest, search, delete...).")
    print("  Strategy: chỉ thêm 1 class store mới + 1 nhánh ở build_service(). Context bất biến.")

    print("\n" + "=" * 72)
    print("KẾT LUẬN: EmbedderPort/VectorStorePort = Strategy interface (Protocol).")
    print("FakeEmbedder/HeavyEmbedder, InMemory/PersistentLike = ConcreteStrategy.")
    print("RagService = Context delegate; build_service(config) = factory chọn strategy.")
    print("Cùng API, khác trade-off, đổi bằng config. Mọi assert PASS.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
