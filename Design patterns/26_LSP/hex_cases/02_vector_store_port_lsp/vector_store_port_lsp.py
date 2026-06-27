"""
LSP case 02 — VectorStorePort: InMemoryVectorStore & QdrantVectorStore thay thế cho nhau.

Bản DISTILL TRUNG THỰC (chỉ stdlib) của port-adapter VectorStorePort trong hex_agent.

NGUỒN THẬT đã mở kiểm chứng (đường dẫn tương đối so với /Users/uspro/Desktop/namnson/hex_agent):
  - rag/ports.py:31-36              VectorStorePort(Protocol): health/delete_by_source/upsert/search (@runtime_checkable)
  - rag/stores.py:24-56             InMemoryVectorStore — adapter in-process, cosine tất định
  - rag/stores.py:35-36             health() KHÔNG raise (trả {"ok": bool, "collection", "count"})
  - rag/stores.py:47-56             search() trả list[Hit] sort theo (-score, source, chunk_index), cắt top_k
  - rag/stores_qdrant.py:32-149     QdrantVectorStore — adapter gRPC remote, cùng interface
  - rag/stores_qdrant.py:83-90      health() KHÔNG raise: server unreachable -> {"ok": False} (control flow, không exception)
  - rag/service.py:16, 22-23, 71-72 RagService gọi store.health()/delete_by_source()/upsert(), không isinstance
  - tests_audit/test_rag_edges_rigor.py:559-563  isinstance(QdrantVectorStore, VectorStorePort)
  - tests_audit/test_rag_edges_rigor.py:566       cả hai store chia sẻ cùng key envelope health()

CONTRACT của VectorStorePort (cái mà RagService dựa vào):
  - health()          : KHÔNG BAO GIỜ raise; trả dict có ít nhất key "ok": bool.
                        => lỗi hạ tầng (server chết) thành {"ok": False}, KHÔNG ném exception lên caller.
  - delete_by_source(): idempotent — xóa nguồn đã xóa rồi -> trả 0, không lỗi.
  - upsert()          : trả số chunk đã ghi.
  - search()          : trả list[Hit] SORT tất định và CẮT về top_k.
LSP: hai impl cùng giữ contract dù nội tạng khác hẳn (list trong RAM vs gRPC) ->
     RagService.ingest/search KHÔNG cần branch theo loại store.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# ───────────────────────── value types (rag/ports.py:8-21) ─────────────────
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


# ───────────────────────── ABSTRACTION (supertype) ─────────────────────────
# Distill của rag/ports.py:31-36.
@runtime_checkable
class VectorStorePort(Protocol):
    def health(self) -> dict: ...
    def delete_by_source(self, source: str) -> int: ...
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ───────────────────────── SUBTYPE 1: in-process ──────────────────────────
# Distill của rag/stores.py:24-56.
class InMemoryVectorStore:
    """Store offline; cosine search tất định. Nội tạng = một list trong RAM."""

    def __init__(self, *, collection: str = "agent_kb", healthy: bool = True) -> None:
        self.collection = collection
        self._healthy = healthy
        self._chunks: list[Chunk] = []

    def set_healthy(self, value: bool) -> None:  # rag/stores.py:32-33
        self._healthy = value

    def health(self) -> dict:  # rag/stores.py:35-36 — không raise
        return {"ok": self._healthy, "collection": self.collection, "count": len(self._chunks)}

    def delete_by_source(self, source: str) -> int:  # rag/stores.py:38-41 — idempotent
        before = len(self._chunks)
        self._chunks = [c for c in self._chunks if c.source != source]
        return before - len(self._chunks)

    def upsert(self, chunks: list[Chunk]) -> int:  # rag/stores.py:43-45
        self._chunks.extend(chunks)
        return len(chunks)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        # rag/stores.py:47-56 — sort tất định rồi cắt top_k.
        hits = [
            Hit(c.source, c.chunk_index, c.text, _cosine(vector, c.vector))
            for c in self._chunks
            if c.vector is not None and _cosine(vector, c.vector) >= score_threshold
        ]
        hits.sort(key=lambda h: (-h.score, h.source, h.chunk_index))
        return hits[:top_k]


# ───────────────────────── SUBTYPE 2: "remote" (giả lập Qdrant) ────────────
# Distill của rag/stores_qdrant.py:32-149. Ta thay client gRPC bằng "fake client"
# stdlib nhưng GIỮ NGUYÊN contract: lazy collection, health() không raise khi server chết,
# id tất định -> upsert idempotent.
class _FakeQdrantClient:
    """Đứng thay QdrantClient. reachable=False mô phỏng server chết."""

    def __init__(self, *, reachable: bool = True) -> None:
        self.reachable = reachable
        self._points: dict[str, dict] = {}  # point_id -> payload+vector

    def ping(self) -> None:
        if not self.reachable:
            raise ConnectionError("qdrant unreachable")  # hạ tầng raise — adapter PHẢI nuốt

    def count(self) -> int:
        self.ping()
        return len(self._points)

    def upsert(self, points: dict[str, dict]) -> None:
        self.ping()
        self._points.update(points)  # id tất định -> ghi đè tại chỗ (idempotent)

    def delete(self, source: str) -> int:
        self.ping()
        ids = [pid for pid, p in self._points.items() if p["source"] == source]
        for pid in ids:
            del self._points[pid]
        return len(ids)

    def query(self, vector, top_k, threshold):
        self.ping()
        return list(self._points.values())


class QdrantVectorStore:
    """Adapter 'production' qua client remote; cùng interface VectorStorePort."""

    def __init__(self, *, collection: str = "agent_kb", client: _FakeQdrantClient | None = None) -> None:
        self.collection = collection
        self._client = client or _FakeQdrantClient()

    @staticmethod
    def _point_id(source: str, chunk_index: int) -> str:
        return f"{source}::{chunk_index}"  # id tất định -> upsert ghi đè (idempotent)

    def health(self) -> dict:  # rag/stores_qdrant.py:83-90 — KHÔNG raise
        try:
            return {"ok": True, "collection": self.collection, "count": self._client.count()}
        except Exception as exc:  # server chết -> dependency failure, không phải crash
            return {"ok": False, "collection": self.collection, "count": 0, "error": str(exc)}

    def delete_by_source(self, source: str) -> int:  # rag/stores_qdrant.py:92-99
        try:
            return self._client.delete(source)
        except Exception:
            return 0

    def upsert(self, chunks: list[Chunk]) -> int:  # rag/stores_qdrant.py:101-125
        if not chunks:
            return 0
        if any(c.vector is None for c in chunks):
            raise ValueError("upsert requires embedded chunks; a chunk vector is None.")
        points = {
            self._point_id(c.source, c.chunk_index): {
                "source": c.source, "chunk_index": c.chunk_index, "text": c.text, "vector": list(c.vector),
            }
            for c in chunks
        }
        self._client.upsert(points)
        return len(points)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        rows = self._client.query(vector, top_k, score_threshold)
        hits = [
            Hit(p["source"], p["chunk_index"], p["text"], _cosine(vector, p["vector"]))
            for p in rows
            if _cosine(vector, p["vector"]) >= score_threshold
        ]
        hits.sort(key=lambda h: (-h.score, h.source, h.chunk_index))
        return hits[:top_k]


# ───────────────────────── CALLER (depend on abstraction) ──────────────────
# Distill của rag/service.py:16, 22-23, 30-39, 71-75.
class RagService:
    def __init__(self, store: VectorStorePort) -> None:
        self._store = store  # không lưu loại cụ thể, không isinstance

    def _require_healthy(self) -> dict | None:
        h = self._store.health()  # health() KHÔNG raise -> gate là control flow bình thường
        if not h.get("ok"):
            return {"ok": False, "code": "dependency_unavailable",
                    "error": f"RAG store unhealthy (collection={h.get('collection')})."}
        return None

    def ingest(self, chunks: list[Chunk]) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
        # re-ingest replace: xóa nguồn cũ trước rồi upsert (rag/service.py:71-72).
        for source in {c.source for c in chunks}:
            self._store.delete_by_source(source)
        return {"ok": True, "chunks": self._store.upsert(chunks)}

    def search(self, vector: list[float], *, top_k: int = 5, threshold: float = 0.0) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
        hits = self._store.search(vector, top_k, threshold)
        return {"ok": True, "count": len(hits), "hits": [(h.source, h.chunk_index) for h in hits]}


# ───────────────────────── LISKOV CONTRACT TEST (abstract) ─────────────────
def liskov_contract(store: VectorStorePort) -> None:
    """Bộ test contract chạy y hệt trên MỌI store impl."""
    assert isinstance(store, VectorStorePort), "phải thỏa VectorStorePort"
    # health() KHÔNG raise và có key 'ok': bool.
    h = store.health()
    assert isinstance(h.get("ok"), bool), "health() phải có 'ok': bool"
    # upsert + search tất định.
    aligned = [1.0, 0.0]
    store.upsert([
        Chunk("c.md", 0, "c", aligned), Chunk("a.md", 0, "a", aligned), Chunk("b.md", 0, "b", aligned),
    ])
    hits = store.search(aligned, 2, 0.0)  # (vector, top_k, score_threshold) — chữ ký port
    # tie score -> sort (source, chunk_index); top_k giữ 2 đầu.
    assert [h.source for h in hits] == ["a.md", "b.md"], "search phải sort tất định + cắt top_k"
    # delete_by_source idempotent.
    assert store.delete_by_source("a.md") == 1
    assert store.delete_by_source("a.md") == 0, "xóa lần 2 phải idempotent -> 0"


def demo() -> None:
    print("=" * 72)
    print("LSP case 02 — VectorStorePort: InMemory & Qdrant swap")
    print("=" * 72)

    mem = InMemoryVectorStore(collection="kb")
    qdr = QdrantVectorStore(collection="kb")

    print("\n[1] Liskov contract test trên CẢ HAI store (cùng 1 bộ assert):")
    for name, st in (("InMemoryVectorStore", mem), ("QdrantVectorStore", qdr)):
        liskov_contract(st)
        print(f"    - {name:21s}: PASS")

    print("\n[2] RagService phụ thuộc abstraction — KHÔNG đổi 1 dòng khi swap store:")
    for name, st in (("InMemoryVectorStore", InMemoryVectorStore()), ("QdrantVectorStore", QdrantVectorStore())):
        svc = RagService(st)
        v = [1.0, 0.0]
        svc.ingest([Chunk("doc.md", 0, "alpha", v), Chunk("doc.md", 1, "beta", v)])
        res = svc.search(v, top_k=5, threshold=0.0)
        print(f"    - RagService(store={name:21s}).search -> count={res['count']}, hits={res['hits']}")
        assert res["count"] == 2

    print("\n[3] CONTRACT về exception: server CHẾT -> health() trả {'ok': False}, KHÔNG raise:")
    dead = QdrantVectorStore(collection="kb", client=_FakeQdrantClient(reachable=False))
    h = dead.health()
    print(f"    - dead.health() = {{'ok': {h['ok']}, 'error': ...}}  (control flow, không exception)")
    assert h["ok"] is False
    svc = RagService(dead)
    res = svc.ingest([Chunk("x.md", 0, "z", [1.0, 0.0])])
    print(f"    - RagService.ingest trên store chết -> {res['code']!r} (gate bình thường)")
    assert res["code"] == "dependency_unavailable"

    print("\n[4] ĐỐI CHỨNG — store VI PHẠM exception contract (health() RAISE thay vì nuốt):")

    class CrashingStore:
        collection = "kb"

        def health(self) -> dict:
            raise ConnectionError("boom")  # ← mở rộng exception type ngoài hợp đồng!

        def delete_by_source(self, source: str) -> int: return 0
        def upsert(self, chunks): return 0
        def search(self, vector, top_k, threshold): return []

    svc = RagService(CrashingStore())
    try:
        svc.ingest([Chunk("x.md", 0, "z", [1.0])])
        raise AssertionError("đáng lẽ crash")
    except ConnectionError:
        print("    - health() raise ConnectionError -> THOÁT qua _require_healthy -> caller crash.")
        print("      Caller code KHÔNG hề try/except ConnectionError (vì hợp đồng nói health() không raise).")
        print("      => Subtype mở rộng exception type = vi phạm LSP; ép caller phải biết loại store.")

    print("\nTẤT CẢ ASSERT PASS. ✅")


if __name__ == "__main__":
    demo()
