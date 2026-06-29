"""
Hexagonal (Ports & Adapters) — Case 01: RAG Service, hai adapter cạnh tranh cho 1 driven port.

Bản DISTILL TRUNG THỰC từ codebase hex_agent. Nguồn thật:
  - rag/ports.py:24-36         -> EmbedderPort + VectorStorePort (DRIVEN PORTS, chỉ Protocol)
  - rag/service.py:15-40       -> RagService.__init__ + health()/_require_healthy() (DOMAIN CORE, inject port)
  - rag/service.py:78-113      -> RagService.search() (lõi gọi RA driven port, không biết adapter cụ thể)
  - rag/stores.py:24-57        -> InMemoryVectorStore (DRIVEN ADAPTER offline, cosine in-memory)
  - rag/stores_qdrant.py:32-148 -> QdrantVectorStore (DRIVEN ADAPTER production qua qdrant-client)
  - rag/feature.py:27-42       -> build_service() (COMPOSITION ROOT: chọn adapter theo config['backend'])

Điều case này LƯỢC BỎ so với bản thật:
  - Bỏ qdrant-client thật + network: thay bằng FakeQdrantClient bằng dict trong stdlib,
    giữ nguyên ranh giới adapter (cùng VectorStorePort) để chứng minh swap không đụng lõi.
  - Bỏ fastembed/model embedding thật: thay bằng HashingEmbedder (băm token -> vector) deterministic.
  - Bỏ sandbox/chunking/ingest-from-file: ingest nhận thẳng list văn bản.
  - Giữ nguyên: dependency injection qua __init__, health-gate, lõi chỉ gọi port,
    composition root quyết định adapter theo config.

Chỉ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent, KHÔNG thư viện bên thứ ba.
Chạy: python3 rag_service_ports_adapters.py   (thoát code 0, không traceback)
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# ─────────────────────────────────────────────────────────────────────────────
# 1) VALUE TYPES + DRIVEN PORTS  (distill rag/ports.py:8-36)
#    Đây là "seam giữa logic và infra". KHÔNG có implementation — chỉ chữ ký.
#    Lõi (RagService) sở hữu và định nghĩa port; adapter phải uốn theo port.
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


@runtime_checkable
class EmbedderPort(Protocol):
    """Driven port: lõi gọi RA để biến text -> vector. Không quan tâm model nào."""
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class VectorStorePort(Protocol):
    """Driven port: lõi gọi RA để lưu/tìm vector. Không quan tâm Qdrant hay in-memory."""
    def health(self) -> dict: ...
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...


# ─────────────────────────────────────────────────────────────────────────────
# 2) DOMAIN CORE  (distill rag/service.py:15-113)
#    RagService chứa logic thuần: health-gate, validate input, orchestrate embed->search.
#    Nó nhận store: VectorStorePort + embedder: EmbedderPort qua __init__ (DI).
#    Lõi KHÔNG import InMemoryVectorStore hay FakeQdrantStore — chỉ biết port.
# ─────────────────────────────────────────────────────────────────────────────
class RagService:
    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, *, top_k: int = 5,
                 score_threshold: float = 0.0) -> None:
        self._store = store
        self._embedder = embedder
        self._top_k = top_k
        self._score_threshold = score_threshold

    def _require_healthy(self) -> dict | None:
        """Health-gate: nếu store hỏng, trả envelope lỗi — KHÔNG ném exception (như bản thật)."""
        h = self._store.health()
        if not h.get("ok"):
            return {"ok": False, "code": "dependency_unavailable",
                    "error": f"RAG store unhealthy (collection={h.get('collection')})."}
        return None

    def ingest(self, source: str, texts: list[str]) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
        vectors = self._embedder.embed(texts)
        # Bản thật từ chối cardinality mismatch trước khi upsert (rag/service.py:64-69).
        if len(vectors) != len(texts):
            raise ValueError(
                f"embedder returned {len(vectors)} embeddings for {len(texts)} chunks (count mismatch)."
            )
        chunks = [Chunk(source, i, t, v) for i, (t, v) in enumerate(zip(texts, vectors))]
        written = self._store.upsert(chunks)
        return {"ok": True, "chunks": written}

    def search(self, query: str, *, top_k: int | None = None) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
        if not query or not query.strip():
            raise ValueError("search query must not be empty.")
        k = int(top_k) if top_k is not None else self._top_k
        vector = self._embedder.embed([query])[0]      # lõi gọi RA driven port (embedder)
        hits = self._store.search(vector, k, self._score_threshold)  # lõi gọi RA driven port (store)
        return {
            "ok": True,
            "count": len(hits),
            "hits": [{"source": h.source, "chunk_index": h.chunk_index,
                      "text": h.text, "score": round(h.score, 6)} for h in hits],
        }


# ─────────────────────────────────────────────────────────────────────────────
# 3) DRIVEN ADAPTERS  — cùng 1 port, hai công nghệ khác nhau.
# ─────────────────────────────────────────────────────────────────────────────
class HashingEmbedder:
    """Adapter offline cho EmbedderPort (distill rag/embedders.FakeEmbedder).
    Băm token thành chiều cố định -> vector deterministic, không cần model."""
    def __init__(self, dim: int = 16) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in text.lower().split():
                idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim
                vec[idx] += 1.0
            out.append(vec)
        return out


def _cosine(a: list[float], b: list[float]) -> float:
    """distill rag/stores.py:15-21 — cosine similarity, 0.0 nếu vector rỗng."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """DRIVEN ADAPTER offline (distill rag/stores.py:24-57).
    Dùng trong test/dev. health() switchable để test được nhánh dependency-failure."""
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


class FakeQdrantClient:
    """Thay cho qdrant-client thật: lưu point trong dict thay vì gọi network.
    Mục đích là giữ NGUYÊN ranh giới: QdrantVectorStore vẫn dịch port -> API client."""
    def __init__(self) -> None:
        self._points: dict[str, dict] = {}
        self.reachable = True

    def upsert(self, points: list[dict]) -> None:
        for p in points:
            self._points[p["id"]] = p

    def query_points(self, vector: list[float], limit: int, score_threshold: float) -> list[dict]:
        scored = []
        for p in self._points.values():
            score = _cosine(vector, p["vector"])
            if score >= score_threshold:
                scored.append((score, p))
        scored.sort(key=lambda t: -t[0])
        return [{"score": s, "payload": p["payload"]} for s, p in scored[:limit]]

    def count(self) -> int:
        return len(self._points)


class QdrantVectorStore:
    """DRIVEN ADAPTER production (distill rag/stores_qdrant.py:32-148).
    Dịch lời gọi của VectorStorePort thành thao tác trên client. health() KHÔNG ném —
    server không tới được trả {'ok': False} để health-gate vẫn là control flow bình thường."""
    def __init__(self, client: FakeQdrantClient, *, collection: str = "agent_kb") -> None:
        self._client = client
        self.collection = collection

    def health(self) -> dict:
        try:
            if not self._client.reachable:
                raise ConnectionError("qdrant unreachable")
            return {"ok": True, "collection": self.collection, "count": self._client.count()}
        except Exception as exc:  # unreachable -> dependency failure, không phải crash
            return {"ok": False, "collection": self.collection, "count": 0, "error": str(exc)}

    def upsert(self, chunks: list[Chunk]) -> int:
        if any(c.vector is None for c in chunks):
            raise ValueError("upsert requires embedded chunks; a chunk vector is None.")
        points = [
            {"id": f"{c.source}::{c.chunk_index}", "vector": list(c.vector),
             "payload": {"source": c.source, "chunk_index": c.chunk_index, "text": c.text}}
            for c in chunks
        ]
        self._client.upsert(points)
        return len(points)

    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]:
        rows = self._client.query_points(vector, limit=top_k, score_threshold=score_threshold)
        return [Hit(r["payload"]["source"], int(r["payload"]["chunk_index"]),
                    r["payload"]["text"], float(r["score"])) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# 4) COMPOSITION ROOT  (distill rag/feature.py:27-42)
#    Nơi DUY NHẤT biết về adapter cụ thể. Chọn adapter theo config['backend'].
#    RagService không thay đổi 1 dòng khi backend đổi.
# ─────────────────────────────────────────────────────────────────────────────
def build_service(config: dict | None = None) -> RagService:
    config = config or {}
    backend = (config.get("backend") or "memory").lower()
    embedder = HashingEmbedder()
    if backend == "memory":
        return RagService(InMemoryVectorStore(), embedder)
    if backend == "qdrant":
        client = config.get("client") or FakeQdrantClient()
        return RagService(QdrantVectorStore(client), embedder)
    raise ValueError(f"Unknown rag backend: {backend!r}")


# ─────────────────────────────────────────────────────────────────────────────
# 5) PHẢN VÍ DỤ: lõi import thẳng adapter cụ thể (LEAKY CORE).
#    Đây là cái Hexagonal CẤM. Để minh hoạ cái giá phải trả.
# ─────────────────────────────────────────────────────────────────────────────
class LeakyRagService:
    """ANTI-PATTERN: lõi tự khởi tạo InMemoryVectorStore -> hard-code I/O.
    Muốn đổi sang Qdrant phải SỬA lõi. Test bắt buộc dùng đúng adapter này."""
    def __init__(self) -> None:
        self._store = InMemoryVectorStore()    # ← lõi biết adapter cụ thể: SAI
        self._embedder = HashingEmbedder()

    def search(self, query: str) -> dict:
        v = self._embedder.embed([query])[0]
        hits = self._store.search(v, 5, 0.0)
        return {"ok": True, "count": len(hits)}


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 72)
    print("CASE 01 — RAG Service: 1 driven port, hai adapter cạnh tranh")
    print("=" * 72)

    docs = [
        "hexagonal architecture keeps the core free of infrastructure",
        "ports define the seam between domain logic and adapters",
        "the composition root wires ports to concrete adapters",
    ]

    # --- (1) Backend memory: build qua composition root ---
    print("\n[1] build_service(backend='memory') — lõi nhận InMemoryVectorStore qua DI")
    svc_mem = build_service({"backend": "memory"})
    svc_mem.ingest("kb.md", docs)
    res_mem = svc_mem.search("ports and adapters seam")
    print(f"    search ok={res_mem['ok']} count={res_mem['count']} "
          f"top='{res_mem['hits'][0]['text'][:38]}...'")

    # --- (2) Backend qdrant: CÙNG RagService logic, chỉ đổi adapter ---
    print("\n[2] build_service(backend='qdrant') — lõi nhận QdrantVectorStore qua DI")
    svc_qdr = build_service({"backend": "qdrant"})
    svc_qdr.ingest("kb.md", docs)
    res_qdr = svc_qdr.search("ports and adapters seam")
    print(f"    search ok={res_qdr['ok']} count={res_qdr['count']} "
          f"top='{res_qdr['hits'][0]['text'][:38]}...'")

    # BẤT BIẾN: đổi adapter KHÔNG đổi kết quả top-hit — lõi logic giống hệt.
    assert res_mem["hits"][0]["text"] == res_qdr["hits"][0]["text"], "top-hit phải giống nhau"
    print("    [assert] top-hit của hai backend GIỐNG NHAU -> lõi không phụ thuộc adapter. OK")

    # --- (3) Health-gate: store hỏng -> lõi trả envelope lỗi, không crash ---
    print("\n[3] Health-gate: đặt store unhealthy -> search trả dependency_unavailable")
    broken = InMemoryVectorStore(healthy=False)
    svc_broken = RagService(broken, HashingEmbedder())
    res_broken = svc_broken.search("anything")
    assert res_broken["ok"] is False and res_broken["code"] == "dependency_unavailable"
    print(f"    ok={res_broken['ok']} code={res_broken['code']} (không có traceback)")

    # --- (4) Inject adapter giả lập Qdrant chết -> health-gate vẫn bắt được ---
    print("\n[4] Qdrant 'chết' (reachable=False) -> health() trả ok=False, lõi gate sạch")
    dead = FakeQdrantClient()
    dead.reachable = False
    svc_dead = RagService(QdrantVectorStore(dead), HashingEmbedder())
    assert svc_dead.search("x")["ok"] is False
    print("    [assert] search trả ok=False qua đúng health-gate. OK")

    # --- (5) PHẢN VÍ DỤ: leaky core không thể swap adapter ---
    print("\n[5] PHẢN VÍ DỤ — LeakyRagService hard-code InMemoryVectorStore trong lõi")
    leaky = LeakyRagService()
    print("    LeakyRagService.__init__ tự new InMemoryVectorStore() -> KHÔNG thể")
    print("    đổi sang Qdrant mà không sửa lõi; test buộc dùng đúng store đó.")
    print("    => mất pluggability. Đây chính là cái Hexagonal cấm.")

    print("\n" + "=" * 72)
    print("KẾT LUẬN: port do lõi sở hữu; adapter cắm vào; composition root quyết định.")
    print("Đổi memory <-> qdrant = đổi 1 chỗ wiring, lõi RagService NGUYÊN VẸN.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
