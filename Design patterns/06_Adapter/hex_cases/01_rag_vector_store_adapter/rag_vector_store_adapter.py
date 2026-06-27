"""
Case 01 — Adapter: hai Vector Store khác hẳn nhau sau cùng một Port
====================================================================

Distill TRUNG THỰC từ hex_agent (Adapter / Structural):

  - rag/ports.py:31-36
        VectorStorePort (Protocol) — Target interface mà client kỳ vọng:
        health(), delete_by_source(), upsert(), search().
        Chunk (ports.py:8-13) và Hit (ports.py:16-21) là DTO.

  - rag/stores.py:24-57
        InMemoryVectorStore — Concrete Object Adapter bọc một list Python
        (_chunks) và làm cosine search trong bộ nhớ. Đây là adapter offline
        cho test.

  - rag/stores_qdrant.py:32-148
        QdrantVectorStore — Concrete Object Adapter bọc qdrant_client.QdrantClient
        (_client). Dịch Chunk -> PointStruct, Hit <- query_points(); health()
        KHÔNG BAO GIỜ raise (trả {"ok": False} khi server chết). Lazy tạo
        collection. Cùng Target interface với InMemoryVectorStore.

  - rag/service.py:15-19, 22-39, 78-113
        RagService — Client. Nhận VectorStorePort qua dependency injection
        (__init__). Logic search()/health() chỉ gọi _store.health(),
        _store.upsert(), _store.search() — không bao giờ coupling với Qdrant
        hay với list.

File này CHỈ dùng thư viện chuẩn Python 3.14. Hạ tầng nặng (mạng + server
Qdrant) được thay bằng một fake stdlib `_FakeQdrantClient` (dict-in-memory).
KHÔNG import gì từ hex_agent hay thư viện bên thứ ba.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# ──────────────────────────────────────────────────────────────────────────
# DTO — value types đi qua biên (tương ứng rag/ports.py:8-21)
# ──────────────────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────────────────
# TARGET interface — cái client (RagService) kỳ vọng (rag/ports.py:31-36)
# ──────────────────────────────────────────────────────────────────────────
@runtime_checkable
class VectorStorePort(Protocol):
    def health(self) -> dict: ...
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...


def _cosine(a: list[float], b: list[float]) -> float:
    """Trùng với rag/stores.py:15-21."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ──────────────────────────────────────────────────────────────────────────
# ADAPTER #1 — InMemoryVectorStore (Object Adapter bọc 1 list)
# Trùng vai trò rag/stores.py:24-57
# ──────────────────────────────────────────────────────────────────────────
class InMemoryVectorStore:
    """Adapter offline: adaptee là một list Python thuần (_chunks)."""

    def __init__(self, *, collection: str = "agent_kb", healthy: bool = True) -> None:
        self.collection = collection
        self._healthy = healthy
        self._chunks: list[Chunk] = []  # ← adaptee: cấu trúc dữ liệu stdlib

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


# ──────────────────────────────────────────────────────────────────────────
# Fake hạ tầng nặng: thay cho qdrant_client.QdrantClient (mạng + server)
# Trong hex_cases ta KHÔNG có server thật nên dùng dict trong bộ nhớ.
# Đây KHÔNG phải là adapter — nó là ADAPTEE (giả lập API của qdrant-client).
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class _FakePoint:
    payload: dict
    score: float


class _FakeQueryResponse:
    def __init__(self, points: list[_FakePoint]) -> None:
        self.points = points


class _FakeCount:
    def __init__(self, count: int) -> None:
        self.count = count


class _FakeQdrantClient:
    """Giả lập interface RAW của qdrant-client. CHÚ Ý: interface này khác hẳn
    VectorStorePort — đó chính là lý do cần Adapter để dịch.

    `alive=False` mô phỏng server chết: mọi lời gọi raise ConnectionError,
    giống lúc qdrant-client không kết nối được tới http://127.0.0.1:6333.
    """

    def __init__(self, *, alive: bool = True) -> None:
        self.alive = alive
        self._collections: dict[str, list[_FakePoint]] = {}

    def _guard(self) -> None:
        if not self.alive:
            raise ConnectionError("offline: cannot reach qdrant server")

    def collection_exists(self, collection: str) -> bool:
        self._guard()
        return collection in self._collections

    def create_collection(self, collection: str, **_kw) -> None:
        self._guard()
        self._collections.setdefault(collection, [])

    def count(self, collection: str, **_kw) -> _FakeCount:
        self._guard()
        return _FakeCount(len(self._collections.get(collection, [])))

    def upsert(self, collection: str, points: list[_FakePoint]) -> None:
        self._guard()
        self._collections.setdefault(collection, []).extend(points)

    def query_points(self, collection, query, limit, score_threshold, **_kw) -> _FakeQueryResponse:
        self._guard()
        scored: list[_FakePoint] = []
        for p in self._collections.get(collection, []):
            score = _cosine(query, p.payload["vector"])
            if score >= score_threshold:
                scored.append(_FakePoint(payload=p.payload, score=score))
        scored.sort(key=lambda x: (-x.score, x.payload["source"], x.payload["chunk_index"]))
        return _FakeQueryResponse(scored[:limit])


# ──────────────────────────────────────────────────────────────────────────
# ADAPTER #2 — QdrantVectorStore (Object Adapter bọc _FakeQdrantClient)
# Trùng vai trò rag/stores_qdrant.py:32-148
# ──────────────────────────────────────────────────────────────────────────
class QdrantVectorStore:
    """Cùng Target interface (VectorStorePort) nhưng adaptee hoàn toàn khác:
    một client kiểu-Qdrant. Adapter dịch Chunk -> point, Hit <- query response,
    và quan trọng: health() KHÔNG bao giờ raise."""

    def __init__(self, client: _FakeQdrantClient, *, collection: str = "agent_kb") -> None:
        self._client = client            # ← adaptee (composition / has-a)
        self.collection = collection
        self._collection_ready = False

    def _ensure_collection(self) -> None:
        # Lazy tạo collection (trùng tinh thần stores_qdrant.py:52-73).
        if self._collection_ready:
            return
        if not self._client.collection_exists(self.collection):
            self._client.create_collection(self.collection)
        self._collection_ready = True

    def health(self) -> dict:
        # Dịch lỗi mạng thành dữ liệu, không thành exception
        # (trùng stores_qdrant.py:83-90).
        try:
            count = 0
            if self._client.collection_exists(self.collection):
                count = self._client.count(self.collection).count
            return {"ok": True, "collection": self.collection, "count": count}
        except Exception as exc:
            return {"ok": False, "collection": self.collection, "count": 0, "error": str(exc)}

    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        if any(c.vector is None for c in chunks):
            raise ValueError("upsert requires embedded chunks; a chunk vector is None.")
        self._ensure_collection()
        # Chunk (DTO của domain) -> point (định dạng của adaptee).
        points = [
            _FakePoint(
                payload={
                    "source": c.source,
                    "chunk_index": c.chunk_index,
                    "text": c.text,
                    "vector": list(c.vector),
                },
                score=0.0,
            )
            for c in chunks
        ]
        self._client.upsert(self.collection, points=points)
        return len(points)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        if not self._client.collection_exists(self.collection):
            return []
        response = self._client.query_points(
            self.collection, query=list(vector), limit=top_k, score_threshold=score_threshold
        )
        # query response (định dạng adaptee) -> Hit (DTO của domain).
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


# ──────────────────────────────────────────────────────────────────────────
# CLIENT — RagService (trùng vai trò rag/service.py:15-113)
# CHỈ phụ thuộc VectorStorePort. KHÔNG biết Qdrant hay list tồn tại.
# ──────────────────────────────────────────────────────────────────────────
class RagService:
    def __init__(self, store: VectorStorePort, *, top_k: int = 5, score_threshold: float = 0.1) -> None:
        self._store = store
        self._top_k = top_k
        self._score_threshold = score_threshold

    def _require_healthy(self) -> dict | None:
        h = self._store.health()
        if not h.get("ok"):
            return {
                "ok": False,
                "code": "dependency_unavailable",
                "error": f"RAG store unhealthy (collection={h.get('collection')}).",
            }
        return None

    def ingest(self, chunks: list[Chunk]) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
        n = self._store.upsert(chunks)
        return {"ok": True, "chunks": n}

    def search(self, vector: list[float]) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
        hits = self._store.search(vector, self._top_k, self._score_threshold)
        return {
            "ok": True,
            "count": len(hits),
            "hits": [
                {"source": h.source, "chunk_index": h.chunk_index, "text": h.text, "score": round(h.score, 6)}
                for h in hits
            ],
        }


# ──────────────────────────────────────────────────────────────────────────
# Anti-pattern: nếu KHÔNG có Adapter, client phải tự if/else theo backend
# ──────────────────────────────────────────────────────────────────────────
class RagServiceNoAdapter:
    """Đối chứng: client coupling trực tiếp với mọi backend. Mỗi backend mới
    đẻ thêm một nhánh if/else, và client phải tự dịch định dạng — đúng thứ
    Adapter sinh ra để loại bỏ."""

    def __init__(self, backend: str, store: object) -> None:
        self._backend = backend
        self._store = store

    def search(self, vector: list[float]) -> list[Hit]:
        if self._backend == "memory":
            # phải biết list._chunks là gì
            hits: list[Hit] = []
            for c in self._store._chunks:  # type: ignore[attr-defined]
                if c.vector is None:
                    continue
                s = _cosine(vector, c.vector)
                if s >= 0.1:
                    hits.append(Hit(c.source, c.chunk_index, c.text, s))
            hits.sort(key=lambda h: -h.score)
            return hits[:5]
        elif self._backend == "qdrant":
            # phải biết query_points trả về cái gì, tự dịch payload
            resp = self._store.query_points(  # type: ignore[attr-defined]
                "agent_kb", query=vector, limit=5, score_threshold=0.1
            )
            return [
                Hit(p.payload["source"], int(p.payload["chunk_index"]), p.payload["text"], float(p.score))
                for p in resp.points
            ]
        # elif self._backend == "pinecone": ... lại thêm một nhánh nữa
        raise ValueError(f"backend không hỗ trợ: {self._backend}")


# ──────────────────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────────────────
def _sample_chunks() -> list[Chunk]:
    # 3 vector 3-chiều đơn giản để cosine dễ kiểm chứng bằng mắt.
    return [
        Chunk("doc_a.md", 0, "hexagonal ports and adapters", [1.0, 0.0, 0.0]),
        Chunk("doc_b.md", 0, "qdrant vector database", [0.0, 1.0, 0.0]),
        Chunk("doc_c.md", 0, "in memory cosine search", [1.0, 1.0, 0.0]),
    ]


def demo() -> None:
    print("=" * 70)
    print("CASE 01 — Adapter: Vector Store kép sau cùng một VectorStorePort")
    print("=" * 70)

    chunks = _sample_chunks()
    query = [1.0, 0.2, 0.0]  # gần doc_a nhất, rồi tới doc_c

    # ---- Adapter A: in-memory --------------------------------------------
    print("\n[1] Client RagService dùng InMemoryVectorStore (adaptee = list)")
    mem = InMemoryVectorStore(collection="agent_kb")
    svc_mem = RagService(mem)
    print("    ingest:", svc_mem.ingest(chunks))
    res_mem = svc_mem.search(query)
    for h in res_mem["hits"]:
        print(f"      hit {h['source']} score={h['score']}")

    # ---- Adapter B: qdrant (fake) — CÙNG code client, không sửa gì -------
    print("\n[2] Client RagService dùng QdrantVectorStore (adaptee = client kiểu-Qdrant)")
    qclient = _FakeQdrantClient(alive=True)
    qdrant = QdrantVectorStore(qclient, collection="agent_kb")
    svc_qdrant = RagService(qdrant)  # ← ĐỔI ADAPTER, KHÔNG ĐỔI CLIENT
    print("    ingest:", svc_qdrant.ingest(chunks))
    res_qdrant = svc_qdrant.search(query)
    for h in res_qdrant["hits"]:
        print(f"      hit {h['source']} score={h['score']}")

    # ---- BẤT BIẾN: hai adapter cho cùng dữ liệu -> cùng kết quả -----------
    order_mem = [(h["source"], h["chunk_index"]) for h in res_mem["hits"]]
    order_qdrant = [(h["source"], h["chunk_index"]) for h in res_qdrant["hits"]]
    assert order_mem == order_qdrant, (order_mem, order_qdrant)
    for a, b in zip(res_mem["hits"], res_qdrant["hits"]):
        assert abs(a["score"] - b["score"]) < 1e-9
    print("\n[assert] Hai adapter substitutable: cùng thứ tự + cùng score. OK")

    # ---- health-gate bắt server chết, KHÔNG crash ------------------------
    print("\n[3] Qdrant server CHẾT -> health() trả {'ok': False}, search vào health-gate")
    dead_client = _FakeQdrantClient(alive=False)
    dead_store = QdrantVectorStore(dead_client, collection="agent_kb")
    h = dead_store.health()
    print("    store.health():", h)
    assert h["ok"] is False and "error" in h, h
    svc_dead = RagService(dead_store)
    gated = svc_dead.search(query)
    print("    svc.search():", gated)
    assert gated["ok"] is False and gated["code"] == "dependency_unavailable"
    print("[assert] Adapter dịch lỗi mạng thành dữ liệu; client không gặp exception. OK")

    # ---- Đối chứng: KHÔNG dùng Adapter -> if/else theo backend -----------
    print("\n[4] Đối chứng RagServiceNoAdapter: client phải tự if/else + tự dịch")
    no_adapter_mem = RagServiceNoAdapter("memory", mem)
    no_adapter_q = RagServiceNoAdapter("qdrant", qclient)
    na_mem = [(h.source, h.chunk_index) for h in no_adapter_mem.search(query)]
    na_q = [(h.source, h.chunk_index) for h in no_adapter_q.search(query)]
    print("    nhánh memory:", na_mem)
    print("    nhánh qdrant:", na_q)
    print("    -> mỗi backend mới = thêm một nhánh if/else; thêm pinecone là phải sửa client.")

    print("\nKẾT LUẬN: Adapter giấu hoàn toàn adaptee. Code client GIỐNG HỆT dù")
    print("backend là list trong RAM hay client kiểu-Qdrant — đổi backend chỉ là")
    print("đổi đối tượng truyền vào RagService(...).")


if __name__ == "__main__":
    demo()
