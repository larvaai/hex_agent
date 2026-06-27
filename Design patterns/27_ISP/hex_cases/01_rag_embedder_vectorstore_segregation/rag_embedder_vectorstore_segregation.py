"""
Ca 01 — RAG: Tách EmbedderPort khỏi VectorStorePort (ISP trong hex_agent).

Bản DISTILL TRUNG THỰC, chỉ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent
hay thư viện bên thứ ba.

NGUỒN THẬT được chưng cất từ (path:line tương đối với /Users/uspro/Desktop/namnson/hex_agent/):
  - rag/ports.py:24-28      EmbedderPort(Protocol): dim + embed(texts)
  - rag/ports.py:31-36      VectorStorePort(Protocol): health/delete_by_source/upsert/search
  - rag/service.py:15-19    RagService(store: VectorStorePort, embedder: EmbedderPort, config)
  - rag/embedders.py:33-46  FakeEmbedder implement CHỈ EmbedderPort (offline, hash bag-of-words)
  - rag/stores.py:24-56     InMemoryVectorStore implement CHỈ VectorStorePort (cosine offline)
  - rag/stores_qdrant.py:32-148  QdrantVectorStore (production) implement CHỈ VectorStorePort
  - rag/feature.py:27-42    build_service chọn adapter của từng port độc lập theo backend

Ý CHÍNH (ISP):
  Embedding và lưu/tìm vector là HAI role khác nhau với lifecycle độc lập. hex_agent
  tách thành 2 Protocol hẹp: EmbedderPort (chỉ embed) và VectorStorePort (chỉ store/search).
  RagService là client gọi cả hai NHƯNG type-hint từng port hẹp riêng. Nhờ đó:
    * test embedder không cần Qdrant; test store không cần model.
    * thay FakeEmbedder -> FastEmbedEmbedder, hay InMemory -> Qdrant, KHÔNG sửa RagService.
  Đối chứng "god port" ở cuối cho thấy gộp 2 role lại sẽ hỏng thế nào.

LƯỢC BỎ so với bản thật: bỏ network/Qdrant client thật, bỏ sandbox jail + chunking file,
bỏ event publish. Giữ nguyên: 2 Protocol hẹp, hai họ adapter độc lập, client cầm 2 port,
cosine search + hash embedder deterministic (giống FakeEmbedder/InMemoryVectorStore thật).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# ──────────────────────────────────────────────────────────────────────────────
# Value types — distill từ rag/ports.py (Chunk, Hit)
# ──────────────────────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────────────────────
# HAI PORT HẸP — distill rag/ports.py:24-36
# Đây là trái tim ISP: mỗi role một interface đặc thù, không gộp.
# ──────────────────────────────────────────────────────────────────────────────
@runtime_checkable
class EmbedderPort(Protocol):
    """Role 1: biến text -> vector. KHÔNG biết gì về lưu trữ/tìm kiếm."""
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class VectorStorePort(Protocol):
    """Role 2: lưu & tìm vector. KHÔNG biết gì về cách tạo embedding."""
    def health(self) -> dict: ...
    def delete_by_source(self, source: str) -> int: ...
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...


# ──────────────────────────────────────────────────────────────────────────────
# ADAPTER cho EmbedderPort — distill rag/embedders.py:33-46 (FakeEmbedder)
# Implement CHỈ EmbedderPort. Không có method nào của VectorStorePort.
# ──────────────────────────────────────────────────────────────────────────────
def _tokenize(text: str) -> list[str]:
    # Bản thật (rag/embedders.py:17-18) dùng re.compile(r"\w+").findall(text.lower()).
    # Ở đây tách thủ công theo ký tự non-alnum để khỏi import re — khác biệt nhỏ về
    # cách lấy token, KHÔNG ảnh hưởng bài học ISP (vẫn là bag-of-words hash deterministic).
    return [w for w in "".join(c if c.isalnum() else " " for c in text.lower()).split() if w]


def _bucket(token: str, dim: int) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dim


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return vec if norm == 0.0 else [x / norm for x in vec]


class FakeEmbedder:
    """Embedder offline deterministic (giống FakeEmbedder thật): hash bag-of-words.
    Text giống nhau -> cosine 1.0; rời rạc -> 0.0. Đủ để test threshold không cần model."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            vec[_bucket(tok, self.dim)] += 1.0
        return _normalize(vec)


class ConstantEmbedder:
    """Adapter thứ HAI cho EmbedderPort (đứng thay cho FastEmbedEmbedder production).
    Minh hoạ: thêm adapter mới = thêm impl, KHÔNG đụng port hay RagService."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Mọi text cùng dim, vector chuẩn hoá theo độ dài text (đủ deterministic cho demo).
        out: list[list[float]] = []
        for t in texts:
            v = [0.0] * self.dim
            v[len(t) % self.dim] = 1.0
            out.append(v)
        return out


# ──────────────────────────────────────────────────────────────────────────────
# ADAPTER cho VectorStorePort — distill rag/stores.py:24-56 (InMemoryVectorStore)
# Implement CHỈ VectorStorePort. Không có embed().
# ──────────────────────────────────────────────────────────────────────────────
def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """Store offline; cosine search deterministic. health() switchable để test
    đường dependency-failure (giống bản thật)."""

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


class RecordingVectorStore:
    """Adapter thứ HAI cho VectorStorePort (đứng thay QdrantVectorStore production):
    wrap một store khác + đếm số lần upsert/search. Minh hoạ swap-in store mà
    RagService không hề biết."""

    def __init__(self, inner: VectorStorePort) -> None:
        self._inner = inner
        self.upserts = 0
        self.searches = 0

    def health(self) -> dict:
        return self._inner.health()

    def delete_by_source(self, source: str) -> int:
        return self._inner.delete_by_source(source)

    def upsert(self, chunks: list[Chunk]) -> int:
        self.upserts += 1
        return self._inner.upsert(chunks)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        self.searches += 1
        return self._inner.search(vector, top_k, score_threshold)


# ──────────────────────────────────────────────────────────────────────────────
# CLIENT — distill rag/service.py:15-19 (RagService)
# Cầm CẢ HAI port nhưng mỗi cái là một role hẹp độc lập.
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RagConfig:
    # Bản thật default 0.8; ở đây hạ xuống 0.3 vì FakeEmbedder hash bag-of-words
    # cho câu tiếng Việt ngắn ra cosine thấp hơn — đủ để phân biệt khớp/không khớp.
    score_threshold: float = 0.3
    top_k: int = 5


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
        gate = self._require_healthy()
        if gate is not None:
            return gate
        vectors = self._embedder.embed(texts)              # ← chỉ dùng EmbedderPort.embed
        chunks = [Chunk(source, i, t, v) for i, (t, v) in enumerate(zip(texts, vectors))]
        self._store.delete_by_source(source)               # ← chỉ dùng VectorStorePort
        self._store.upsert(chunks)
        return {"ok": True, "source": source, "chunks": len(chunks)}

    def search(self, query: str, *, top_k: int | None = None) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
        if not query.strip():
            raise ValueError("search query must not be empty.")
        k = int(top_k) if top_k is not None else self._cfg.top_k
        vector = self._embedder.embed([query])[0]          # ← EmbedderPort
        hits = self._store.search(vector, k, self._cfg.score_threshold)  # ← VectorStorePort
        return {"ok": True, "count": len(hits),
                "hits": [{"source": h.source, "text": h.text, "score": round(h.score, 6)} for h in hits]}


# ──────────────────────────────────────────────────────────────────────────────
# build_service — distill rag/feature.py:27-42: chọn adapter mỗi port độc lập.
# ──────────────────────────────────────────────────────────────────────────────
def build_service(*, embedder: EmbedderPort, store: VectorStorePort) -> RagService:
    return RagService(store, embedder, RagConfig())


# ──────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG "god port": gộp cả 2 role vào MỘT interface to.
# ──────────────────────────────────────────────────────────────────────────────
class FatRagPort(Protocol):
    """Vi phạm ISP: một interface ôm cả embed lẫn store/search. Mọi adapter buộc
    implement cả 6 method, kể cả method nó không có vai trò."""
    dim: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def health(self) -> dict: ...
    def delete_by_source(self, source: str) -> int: ...
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...


class FatEmbedderOnly:
    """Một adapter chỉ biết embed nhưng buộc phải 'là' FatRagPort -> refused bequest."""
    dim = 64

    def embed(self, texts: list[str]) -> list[list[float]]:
        return FakeEmbedder(self.dim).embed(texts)

    def health(self) -> dict:
        raise NotImplementedError("FatEmbedderOnly không phải store!")

    def delete_by_source(self, source: str) -> int:
        raise NotImplementedError("FatEmbedderOnly không phải store!")

    def upsert(self, chunks: list[Chunk]) -> int:
        raise NotImplementedError("FatEmbedderOnly không phải store!")

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        raise NotImplementedError("FatEmbedderOnly không phải store!")


# ──────────────────────────────────────────────────────────────────────────────
# DEMO
# ──────────────────────────────────────────────────────────────────────────────
def _hr(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def demo() -> None:
    _hr("BƯỚC 1 — Hai port HẸP, độc lập (EmbedderPort vs VectorStorePort)")
    print("EmbedderPort  : dim + embed()            -> role 'tạo vector'")
    print("VectorStorePort: health/delete/upsert/search -> role 'lưu & tìm vector'")
    print("Không port nào nghe cả hai — đúng 'receptor specificity'.")

    _hr("BƯỚC 2 — Mỗi adapter implement ĐÚNG MỘT port")
    embedder = FakeEmbedder(dim=64)
    store = InMemoryVectorStore()
    # @runtime_checkable cho phép kiểm tra structural ở runtime.
    assert isinstance(embedder, EmbedderPort), "FakeEmbedder phải conform EmbedderPort"
    assert not isinstance(embedder, VectorStorePort), "FakeEmbedder KHÔNG nên là store"
    assert isinstance(store, VectorStorePort), "InMemoryVectorStore phải conform VectorStorePort"
    assert not isinstance(store, EmbedderPort), "Store KHÔNG nên là embedder"
    print("FakeEmbedder        -> EmbedderPort  ✓   (không phải VectorStorePort ✓)")
    print("InMemoryVectorStore -> VectorStorePort ✓ (không phải EmbedderPort ✓)")

    _hr("BƯỚC 3 — Client RagService cầm CẢ HAI port, mỗi cái hẹp")
    svc = build_service(embedder=embedder, store=store)
    r_in = svc.ingest("kb/animals.md", ["mèo kêu meo meo", "chó sủa gâu gâu", "mèo và chó"])
    print(f"ingest -> {r_in}")
    r_se = svc.search("mèo kêu", top_k=2)
    print(f"search('mèo kêu') -> count={r_se['count']}")
    for h in r_se["hits"]:
        print(f"   - [{h['score']:.3f}] {h['source']}: {h['text']}")
    assert r_in["ok"] and r_se["ok"]
    assert r_se["count"] >= 1, "phải tìm thấy ít nhất 1 chunk khớp"

    _hr("BƯỚC 4 — Test TỪNG port riêng lẻ (test isolation của ISP)")
    print("Test embedder KHÔNG cần store:")
    only_emb = FakeEmbedder(dim=8)
    v1 = only_emb.embed(["xin chào"])[0]
    v2 = only_emb.embed(["xin chào"])[0]
    assert v1 == v2, "embedder phải deterministic"
    print("   cùng input -> cùng vector ✓  (không dựng VectorStore nào)")
    print("Test store KHÔNG cần model:")
    only_store = InMemoryVectorStore()
    only_store.upsert([Chunk("s", 0, "x", [1.0, 0.0]), Chunk("s", 1, "y", [0.0, 1.0])])
    hits = only_store.search([1.0, 0.0], top_k=1, score_threshold=0.5)
    assert len(hits) == 1 and hits[0].chunk_index == 0
    print("   cosine search trả đúng chunk gần nhất ✓ (không gọi embed nào)")

    _hr("BƯỚC 5 — SWAP-IN adapter mà KHÔNG sửa RagService")
    rec_store = RecordingVectorStore(InMemoryVectorStore())
    svc2 = build_service(embedder=ConstantEmbedder(dim=64), store=rec_store)
    svc2.ingest("kb/x.md", ["alpha beta", "gamma"])
    svc2.search("alpha", top_k=1)
    print(f"Thay embedder=ConstantEmbedder, store=RecordingVectorStore (cùng RagService)")
    print(f"   store ghi nhận upserts={rec_store.upserts}, searches={rec_store.searches}")
    assert rec_store.upserts == 1 and rec_store.searches == 1
    print("   RagService không hề biết adapter đã đổi — đúng tinh thần build_service. ✓")

    _hr("BƯỚC 6 — Đường dependency-failure: store unhealthy gate trước embed")
    sick = InMemoryVectorStore(healthy=False)
    svc3 = build_service(embedder=FakeEmbedder(), store=sick)
    r = svc3.search("bất kỳ")
    print(f"store.health.ok=False -> search trả: {r}")
    assert r["ok"] is False and r["code"] == "dependency_unavailable"
    print("   Gate đọc CHỈ VectorStorePort.health(), không đụng embedder. ✓")

    _hr("ĐỐI CHỨNG — 'god port' (FatRagPort) gây refused bequest")
    fat = FatEmbedderOnly()
    print("FatEmbedderOnly chỉ thực sự biết embed, nhưng FatRagPort ép nó có cả store.")
    try:
        fat.search([1.0], 1, 0.5)
        raise AssertionError("đáng lẽ phải NotImplementedError")
    except NotImplementedError as exc:
        print(f"   gọi search() -> NotImplementedError: {exc}")
    print("Bài học: gộp 2 role vào 1 interface -> adapter buộc raise NotImplementedError")
    print("cho method không thuộc vai trò mình. ISP tách 2 port để xoá hẳn smell này.")

    _hr("KẾT LUẬN")
    print("Hai role tách thành hai Protocol hẹp; client cầm cả hai nhưng phụ thuộc hẹp;")
    print("adapter swap-in tự do; test cô lập từng port. Đó là ISP trong rag/ của hex_agent.")


if __name__ == "__main__":
    demo()
