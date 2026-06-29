"""
rag_build_service_factory.py — Abstract Factory (Creational), bản DISTILL chạy được.

Bản rút gọn TRUNG THỰC của Abstract Factory trong hex_agent, distill từ:

  - rag/feature.py:27-42   -> build_service(config): hàm "Abstract Factory".
                              Đọc backend từ config, rồi tạo NGUYÊN HỌ (embedder + store)
                              khớp nhau. backend="memory" -> họ Memory;
                              backend="qdrant" -> họ Qdrant (lazy import); backend lạ -> raise.
  - rag/ports.py:24-36     -> EmbedderPort (24-28) + VectorStorePort (31-36):
                              hai "Abstract Product" dạng Protocol @runtime_checkable.
  - rag/embedders.py:33-46 -> FakeEmbedder (ConcreteProduct họ Memory).
  - rag/embedders.py:49-60 -> FastEmbedEmbedder (ConcreteProduct họ Qdrant, lazy import).
  - rag/stores.py:24-56    -> InMemoryVectorStore (ConcreteProduct họ Memory).
  - rag/stores_qdrant.py   -> QdrantVectorStore (ConcreteProduct họ Qdrant).
  - rag/service.py:15-19   -> RagService(store, embedder, cfg): "Client" nhận hai product
                              QUA Protocol (đa hình), không bao giờ chạm class cụ thể.

Trong file gốc, "họ Qdrant" cần qdrant-client + fastembed + một Qdrant server (docker).
Ở bản distill này ta thay toàn bộ hạ tầng nặng đó bằng fake tối thiểu bằng stdlib:
  - Embedder thật -> hash từ vector (FakeEmbedder) / vector "dày" giả lập model (ProdEmbedder).
  - Vector store thật -> dict trong RAM, cosine tính tay (giống InMemoryVectorStore).
KHÔNG import gì từ hex_agent, KHÔNG import thư viện bên thứ ba — chỉ stdlib Python 3.14.

Điểm cốt lõi muốn chứng minh:
  1. MỘT factory (build_service) quyết định CẢ HỌ object, client không tự ghép.
  2. Hai họ KHÔNG tương thích (số chiều vector khác nhau) -> "trộn họ" = hỏng ngầm.
  3. Client (RagService) chỉ phụ thuộc abstraction (Protocol), nên đa hình.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# ─────────────────────────────────────────────────────────────────────────────
# (a) ABSTRACT PRODUCTS — hai "interface product" như rag/ports.py:24-36
# Trong gốc là Protocol @runtime_checkable: chỉ cần có đúng method/attribute là "khớp".
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Chunk:
    """Value type — như rag/ports.py:8-13 (rút gọn: bỏ chunk_index dài dòng)."""
    source: str
    text: str
    vector: list[float] | None = None


@dataclass(frozen=True)
class Hit:
    """Value type — như rag/ports.py:16-21."""
    source: str
    text: str
    score: float


@runtime_checkable
class EmbedderPort(Protocol):
    """Abstract Product #1 — rag/ports.py:24-28. Phải có .dim và .embed()."""
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class VectorStorePort(Protocol):
    """Abstract Product #2 — rag/ports.py:31-36. Health-gate + upsert + search."""
    def health(self) -> dict: ...
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...


# ─────────────────────────────────────────────────────────────────────────────
# (b) CONCRETE PRODUCTS — họ MEMORY (offline, deterministic)
# Distill rag/embedders.py:33-46 và rag/stores.py:24-56.
# ─────────────────────────────────────────────────────────────────────────────
_TOKEN_RE = re.compile(r"\w+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return vec if norm == 0.0 else [x / norm for x in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    # Giống rag/stores.py:15-21. Vector lệch chiều -> zip cắt ngắn -> điểm sai/0.0.
    if len(a) != len(b):
        # Trong gốc, lệch chiều với Qdrant gây lỗi server; ở đây ta phơi bày rõ.
        raise ValueError(f"số chiều vector lệch nhau: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0.0 or nb == 0.0 else dot / (na * nb)


class FakeEmbedder:
    """ConcreteProduct #1a — họ Memory. Distill rag/embedders.py:33-46.

    Hash bag-of-words ra vector dim chiều (mặc định 64). Offline, không model.
    """

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
            vec[int.from_bytes(digest, "big") % self.dim] += 1.0
        return _normalize(vec)


class InMemoryVectorStore:
    """ConcreteProduct #2a — họ Memory. Distill rag/stores.py:24-56.

    Store trong RAM, cosine tính tay. health() chuyển được để test gate.
    """

    def __init__(self, *, collection: str = "agent_kb", healthy: bool = True) -> None:
        self.collection = collection
        self._healthy = healthy
        self._chunks: list[Chunk] = []

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
                hits.append(Hit(c.source, c.text, score))
        hits.sort(key=lambda h: (-h.score, h.source))
        return hits[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# (b') CONCRETE PRODUCTS — họ "PROD" (đứng thay họ Qdrant)
# Trong gốc đây là FastEmbedEmbedder (rag/embedders.py:49-60, dùng fastembed) +
# QdrantVectorStore (rag/stores_qdrant.py, dùng qdrant-client + docker).
# Ở bản distill, ta giả lập "model production" bằng vector DÀY HƠN (dim khác) để
# chứng minh hai họ KHÔNG tương thích — đây chính là bất biến mà Abstract Factory bảo vệ.
# ─────────────────────────────────────────────────────────────────────────────
class ProdEmbedder:
    """ConcreteProduct #1b — họ Prod (đứng thay FastEmbedEmbedder).

    Giả lập model thật: dim 384 (như bge-small) thay vì 64 của FakeEmbedder.
    Số chiều KHÁC -> vector hai họ không thể đem search lẫn nhau.
    """

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5", dim: int = 384) -> None:
        self.model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Hash khác salt + dim khác -> "không gian vector" khác hẳn họ Memory.
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in _tokenize(text):
                digest = hashlib.blake2b(
                    tok.encode("utf-8"), key=b"prod", digest_size=8
                ).digest()
                vec[int.from_bytes(digest, "big") % self.dim] += 1.0
            out.append(_normalize(vec))
        return out


class ProdVectorStore:
    """ConcreteProduct #2b — họ Prod (đứng thay QdrantVectorStore).

    Trong gốc store này nói chuyện với Qdrant server; ở đây vẫn là RAM nhưng
    được "khai báo" với số chiều cố định (expected_dim) để mô phỏng việc Qdrant
    tạo collection theo width của embedder. Nạp vector sai chiều -> từ chối.
    """

    def __init__(self, *, collection: str = "agent_kb", expected_dim: int = 384,
                 healthy: bool = True) -> None:
        self.collection = collection
        self.expected_dim = expected_dim
        self._healthy = healthy
        self._chunks: list[Chunk] = []

    def health(self) -> dict:
        return {"ok": self._healthy, "collection": self.collection, "count": len(self._chunks)}

    def upsert(self, chunks: list[Chunk]) -> int:
        for c in chunks:
            if c.vector is not None and len(c.vector) != self.expected_dim:
                # Giống Qdrant: collection có width cố định; sai width -> lỗi.
                raise ValueError(
                    f"store '{self.collection}' chờ vector {self.expected_dim} chiều, "
                    f"nhận {len(c.vector)} chiều (sai họ embedder?)"
                )
        self._chunks.extend(chunks)
        return len(chunks)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        if len(vector) != self.expected_dim:
            raise ValueError(
                f"store '{self.collection}' chờ query {self.expected_dim} chiều, "
                f"nhận {len(vector)} chiều (sai họ embedder?)"
            )
        hits: list[Hit] = []
        for c in self._chunks:
            if c.vector is None:
                continue
            score = _cosine(vector, c.vector)
            if score >= score_threshold:
                hits.append(Hit(c.source, c.text, score))
        hits.sort(key=lambda h: (-h.score, h.source))
        return hits[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# (c) CLIENT — RagService nhận HAI product QUA Protocol (đa hình)
# Distill rag/service.py:15-19, 22-28, 42-..., 78-98 (rút gọn: bỏ sandbox/chunking).
# Service chỉ gọi method của Port, KHÔNG bao giờ biết class cụ thể là gì.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RagConfig:
    collection: str = "agent_kb"
    model: str = "BAAI/bge-small-en-v1.5"
    # Khớp giá trị thật: RagConfig gốc (rag/ports.py:45) và config/features.yaml:21
    # đều đặt score_threshold = 0.8.
    score_threshold: float = 0.8
    top_k: int = 5


class RagService:
    """Client — rag/service.py:15-19. Phụ thuộc abstraction, không phụ thuộc concrete."""

    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._cfg = config

    def health(self) -> dict:
        h = self._store.health()
        return {"ok": bool(h.get("ok")), "collection": h.get("collection"), "count": h.get("count", 0)}

    def ingest(self, source: str, texts: list[str]) -> dict:
        # health-gate trước (rag/service.py:42-45) rồi mới embed + upsert.
        if not self._store.health().get("ok"):
            return {"ok": False, "code": "dependency_unavailable"}
        vectors = self._embedder.embed(texts)
        chunks = [Chunk(source, t, v) for t, v in zip(texts, vectors)]
        n = self._store.upsert(chunks)
        return {"ok": True, "chunks": n}

    def search(self, query: str) -> dict:
        if not self._store.health().get("ok"):
            return {"ok": False, "code": "dependency_unavailable"}
        vector = self._embedder.embed([query])[0]
        hits = self._store.search(vector, self._cfg.top_k, self._cfg.score_threshold)
        return {"ok": True, "count": len(hits), "hits": hits}


# ─────────────────────────────────────────────────────────────────────────────
# (AbstractFactory) build_service(config) — distill rag/feature.py:27-42
# MỘT điểm duy nhất quyết định "dùng họ nào". Client KHÔNG tự ghép embedder + store.
# ─────────────────────────────────────────────────────────────────────────────
def build_service(config: dict | None) -> RagService:
    config = config or {}
    cfg = RagConfig(
        collection=config.get("collection", "agent_kb"),
        model=config.get("model", "BAAI/bge-small-en-v1.5"),
    )
    backend = (config.get("backend") or "memory").lower()

    if backend == "memory":
        # Họ Memory: FakeEmbedder (dim 64) + InMemoryVectorStore — khớp nhau.
        store: VectorStorePort = InMemoryVectorStore(collection=cfg.collection)
        embedder: EmbedderPort = FakeEmbedder(dim=64)
        return RagService(store, embedder, cfg)

    if backend == "prod":
        # Họ Prod (đứng thay Qdrant): trong gốc đây là lazy import
        #   from rag.embedders import FastEmbedEmbedder
        #   from rag.stores_qdrant import QdrantVectorStore
        # để base install không cần qdrant-client/fastembed (rag/feature.py:36-37).
        # Ở distill, embedder dim 384 + store expected_dim 384 — khớp nhau.
        embedder = ProdEmbedder(model=cfg.model, dim=384)
        store = ProdVectorStore(collection=cfg.collection, expected_dim=embedder.dim)
        return RagService(store, embedder, cfg)

    # backend lạ -> raise (rag/feature.py:42).
    raise ValueError(f"Unknown rag backend: {backend!r}")


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 70)
    print("Abstract Factory — build_service(config) chọn NGUYÊN HỌ product")
    print("Distill từ rag/feature.py:27-42 (hex_agent)")
    print("=" * 70)

    # ── Bước 1: chọn họ Memory bằng config (rag/feature.py:31-34) ─────────────
    print("\n[1] build_service(backend='memory') — họ offline mặc định")
    mem = build_service({"backend": "memory"})
    emb_mem = mem._embedder
    store_mem = mem._store
    print(f"    embedder = {type(emb_mem).__name__} (dim={emb_mem.dim})")
    print(f"    store    = {type(store_mem).__name__}")
    assert isinstance(emb_mem, FakeEmbedder)
    assert isinstance(store_mem, InMemoryVectorStore)
    assert emb_mem.dim == 64
    print("    -> factory đã ghép FakeEmbedder + InMemoryVectorStore (cùng họ Memory).")

    # ── Bước 2: chọn họ Prod bằng config (rag/feature.py:35-41) ───────────────
    print("\n[2] build_service(backend='prod') — họ 'production' (thay Qdrant)")
    prod = build_service({"backend": "prod"})
    emb_prod = prod._embedder
    store_prod = prod._store
    print(f"    embedder = {type(emb_prod).__name__} (dim={emb_prod.dim})")
    print(f"    store    = {type(store_prod).__name__} (expected_dim={store_prod.expected_dim})")
    assert isinstance(emb_prod, ProdEmbedder)
    assert isinstance(store_prod, ProdVectorStore)
    assert emb_prod.dim == 384 and store_prod.expected_dim == 384
    print("    -> factory đã ghép ProdEmbedder + ProdVectorStore (cùng họ Prod).")

    # ── Bước 3: cả hai họ đều CHẠY ĐÚNG khi không trộn ───────────────────────
    print("\n[3] Mỗi họ tự nó chạy đúng (client RagService đa hình trên Port):")
    for name, svc in [("memory", mem), ("prod", prod)]:
        svc.ingest("doc.md", ["alpha alpha beta", "gamma delta epsilon"])
        out = svc.search("alpha beta")
        print(f"    backend={name:6s}: search ok={out['ok']} count={out['count']}")
        assert out["ok"] is True
        assert out["count"] >= 1, f"họ {name} phải tìm thấy ít nhất 1 hit"
    print("    -> RagService KHÔNG đổi 1 dòng nào, vẫn chạy với cả hai họ (đa hình).")

    # ── Bước 4: ĐỐI CHỨNG — khi KHÔNG dùng factory, tự tay trộn họ -> HỎNG ────
    print("\n[4] ĐỐI CHỨNG: không dùng factory, tự ghép embedder họ Memory (dim 64)")
    print("    vào store họ Prod (chờ dim 384) — 'heterotopia' trong code:")
    frankenstein = RagService(
        store=ProdVectorStore(expected_dim=384),  # họ Prod
        embedder=FakeEmbedder(dim=64),            # họ Memory  <-- TRỘN SAI
        config=RagConfig(),
    )
    blew_up = False
    try:
        frankenstein.ingest("doc.md", ["alpha beta gamma"])
    except ValueError as exc:
        blew_up = True
        print(f"    -> NỔ như mong đợi: {exc}")
    assert blew_up, "trộn hai họ phải gây lỗi, nếu không thì pattern vô nghĩa"
    print("    -> Đúng kịch bản pattern chặn: client không có cách nào lấy được")
    print("       store-của-họ-này ghép vào embedder-của-họ-kia QUA build_service.")

    # ── Bước 5: bất biến — chỉ build_service mới biết 'họ nào' ────────────────
    print("\n[5] backend lạ -> build_service từ chối (rag/feature.py:42):")
    rejected = False
    try:
        build_service({"backend": "postgres"})
    except ValueError as exc:
        rejected = True
        print(f"    -> {exc}")
    assert rejected
    print("    -> Quyết định 'họ nào' tập trung MỘT chỗ, không rò rỉ ra client.")

    print("\n" + "=" * 70)
    print("KẾT LUẬN: build_service = Abstract Factory. Một config -> nguyên một họ")
    print("embedder + store khớp nhau; client đa hình; trộn họ bị chặn từ kiến trúc.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
