"""
Case 02 — RagService Facade: health-gate + chunking + embedding + vector store
sau một interface đơn giản ingest()/search()/health().

NGUỒN THẬT (đã mở & kiểm chứng trong hex_agent):
  - rag/service.py:1-7      -> docstring: invariants "health-gate before every ingest/search;
                               ingest paths go through the workspace sandbox jail; logic never
                               touches Qdrant directly (only via VectorStorePort); mọi method
                               trả envelope {"ok": bool, ...}".
  - rag/service.py:15-19    -> RagService.__init__(store, embedder, config) — giữ 3 subsystem.
  - rag/service.py:22-39    -> health() và _require_healthy() (CROSS-CUTTING health-gate).
  - rag/service.py:42-75    -> ingest(): gate -> resolve_in_workspace -> collect_files ->
                               chunk_text -> embed -> kiểm tra cardinality -> delete+upsert.
  - rag/service.py:64-69    -> kiểm tra cardinality TRƯỚC khi upsert (chống ghi lệch/dở).
  - rag/service.py:78-113   -> search(): gate -> validate query/top_k/threshold -> embed ->
                               store.search -> envelope hits.
  - rag/chunking.py         -> chunk_text(), collect_files() (Subsystem chunking).
  - rag/ports.py            -> EmbedderPort, VectorStorePort, Chunk, RagConfig (Subsystem embed/store).
  - safety/sandbox.py       -> resolve_in_workspace(), SandboxError (Subsystem sandbox jail).

VAI TRÒ FACADE Ở ĐÂY:
  Facade            = class RagService (health / ingest / search).
  Subsystem 1       = chunking: chunk_text(), collect_files() (cắt file thành chunk có overlap).
  Subsystem 2       = EmbedderPort (_embedder): text -> vector.
  Subsystem 3       = VectorStorePort (_store): lưu/tìm vector.
  Subsystem 4       = safety.sandbox.resolve_in_workspace(): chặn path ra ngoài workspace.
  Cross-cutting     = _require_healthy(): cổng sức khoẻ gác MỌI thao tác.
  Client            = chỉ gọi svc.ingest(path) / svc.search(q); chỉ thấy dict {ok: bool, ...},
                      KHÔNG bao giờ thấy Chunk/Embedder/Store/path raw.

Bản distill thay file thật bằng dict in-memory, Embedder/Store bằng fake stdlib,
nhưng GIỮ NGUYÊN thứ tự bắt buộc và bất biến: gate -> sandbox -> chunk -> embed ->
cardinality check -> upsert; mọi lỗi gói vào envelope thay vì lộ kiểu lỗi nội bộ.

Chỉ dùng thư viện chuẩn Python. KHÔNG import hex_agent, KHÔNG bên thứ ba.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


# ──────────────────────────────────────────────────────────────────────────────
# SUBSYSTEM 4 — Sandbox jail (safety/sandbox.py thật)
# ──────────────────────────────────────────────────────────────────────────────


class SandboxError(Exception):
    """safety.sandbox.SandboxError — path bị từ chối vì ra ngoài workspace."""


# "Workspace" giả lập: tên thư mục -> {tên file: nội dung}
WORKSPACE: dict[str, dict[str, str]] = {
    "docs": {
        "a.txt": "Facade pattern che subsystem phuc tap. " * 3,
        "b.txt": "Cortex chi phat intent cap cao. " * 3,
    },
    "empty": {},
}


def resolve_in_workspace(raw_path: str) -> str:
    """safety.sandbox.resolve_in_workspace — chỉ cho path nằm trong workspace jail."""
    if raw_path.startswith("/") or ".." in raw_path:
        raise SandboxError(f"Path {raw_path!r} thoát khỏi workspace jail.")
    if raw_path not in WORKSPACE:
        raise SandboxError(f"Path {raw_path!r} không tồn tại trong workspace.")
    return raw_path


# ──────────────────────────────────────────────────────────────────────────────
# SUBSYSTEM 1 — Chunking (rag/chunking.py thật)
# ──────────────────────────────────────────────────────────────────────────────


def collect_files(root: str) -> list[str]:
    """rag.chunking.collect_files — liệt kê file trong thư mục."""
    return sorted(WORKSPACE[root].keys())


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """rag.chunking.chunk_text — cắt text thành chunk có overlap."""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    for start in range(0, len(text), step):
        piece = text[start : start + chunk_size]
        if piece:
            chunks.append(piece)
        if start + chunk_size >= len(text):
            break
    return chunks


# ──────────────────────────────────────────────────────────────────────────────
# SUBSYSTEM 2/3 — Embedder & VectorStore ports (rag/ports.py thật)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class Chunk:
    """rag.ports.Chunk."""

    source: str
    chunk_index: int
    text: str
    vector: tuple[float, ...]


@dataclass
class Hit:
    source: str
    chunk_index: int
    text: str
    score: float


class FakeEmbedder:
    """EmbedderPort distill: text -> vector xác định bằng hash. (rag/embedders.py)"""

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self._vec(t) for t in texts]

    @staticmethod
    def _vec(text: str) -> tuple[float, ...]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        return tuple(b / 255.0 for b in h[:4])


class BrokenEmbedder(FakeEmbedder):
    """Embedder hỏng: trả ít vector hơn số chunk -> cardinality mismatch."""

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        vecs = super().embed(texts)
        return vecs[:-1] if len(vecs) > 1 else vecs


class InMemoryVectorStore:
    """VectorStorePort distill bằng list. (rag/stores.py)"""

    def __init__(self, collection: str = "default", healthy: bool = True) -> None:
        self.collection = collection
        self._healthy = healthy
        self._chunks: list[Chunk] = []

    def set_health(self, ok: bool) -> None:
        self._healthy = ok

    def health(self) -> dict:
        return {"ok": self._healthy, "collection": self.collection, "count": len(self._chunks)}

    def delete_by_source(self, source: str) -> None:
        self._chunks = [c for c in self._chunks if c.source != source]

    def upsert(self, chunks: list[Chunk]) -> None:
        self._chunks.extend(chunks)

    def search(self, vector: tuple[float, ...], k: int, threshold: float) -> list[Hit]:
        scored: list[Hit] = []
        for c in self._chunks:
            score = _cosine(vector, c.vector)
            if score >= threshold:
                scored.append(Hit(c.source, c.chunk_index, c.text, score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


@dataclass
class RagConfig:
    """rag.ports.RagConfig (rút gọn)."""

    chunk_size: int = 40
    chunk_overlap: int = 8
    top_k: int = 3
    score_threshold: float = 0.0


# ──────────────────────────────────────────────────────────────────────────────
# FACADE — RagService (rag/service.py:15 thật)
# ──────────────────────────────────────────────────────────────────────────────


class RagService:
    """
    FACADE: ingest()/search()/health() che 4 subsystem. (rag/service.py:15)
    Mọi method: (1) qua health-gate trước, (2) trả envelope {"ok": bool, ...},
    (3) không bao giờ ném kiểu lỗi nội bộ ra ngoài (gói vào envelope).
    """

    def __init__(self, store: InMemoryVectorStore, embedder: FakeEmbedder, config: RagConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._cfg = config

    # ── health (rag/service.py:22) ──
    def health(self) -> dict:
        h = self._store.health()
        return {"ok": bool(h.get("ok")), "collection": h.get("collection"), "count": h.get("count", 0)}

    def _require_healthy(self) -> dict | None:
        """rag/service.py:30 — cross-cutting gate; envelope lỗi nếu store unhealthy."""
        h = self._store.health()
        if not h.get("ok"):
            return {
                "ok": False,
                "code": "dependency_unavailable",
                "error": f"RAG store unhealthy (collection={h.get('collection')}).",
            }
        return None

    # ── ingest (rag/service.py:42) ──
    def ingest(self, raw_path: str) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
        try:
            root = resolve_in_workspace(raw_path)  # subsystem sandbox
        except SandboxError as exc:
            return {"ok": False, "code": "sandbox", "error": str(exc)}

        files = collect_files(root)  # subsystem chunking
        total_chunks = 0
        sources: list[str] = []
        for source in files:
            texts = chunk_text(
                WORKSPACE[root][source],
                self._cfg.chunk_size,
                self._cfg.chunk_overlap,
            )
            if not texts:
                continue
            vectors = self._embedder.embed(texts)  # subsystem embed
            if len(vectors) != len(texts):
                # rag/service.py:64-69 — chặn cardinality mismatch TRƯỚC mọi upsert
                # để không bao giờ ghi một tập chunk lệch/dở cho source này.
                # LƯU Ý (biến đổi đã công bố ở README §4): code thật `raise ValueError`
                # tại rag/service.py:67-69; bản distill gói thành envelope để minh hoạ
                # hợp đồng {"ok": bool, ...}. Bất biến "không ghi lệch" vẫn y hệt.
                return {
                    "ok": False,
                    "code": "embed_cardinality",
                    "error": (
                        f"embedder returned {len(vectors)} embeddings for "
                        f"{len(texts)} chunks (count mismatch)."
                    ),
                }
            chunks = [Chunk(source, i, t, v) for i, (t, v) in enumerate(zip(texts, vectors))]
            self._store.delete_by_source(source)  # re-ingest thay chunk cũ
            self._store.upsert(chunks)  # subsystem store
            total_chunks += len(chunks)
            sources.append(source)
        return {"ok": True, "files": len(sources), "chunks": total_chunks, "sources": sources}

    # ── search (rag/service.py:78) ──
    def search(self, query: str, *, top_k: int | None = None, score_threshold: float | None = None) -> dict:
        gate = self._require_healthy()
        if gate is not None:
            return gate
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
                {"source": h.source, "chunk_index": h.chunk_index, "text": h.text, "score": round(h.score, 6)}
                for h in hits
            ],
        }


# ──────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — client KHÔNG có facade phải tự điều phối từng subsystem
# ──────────────────────────────────────────────────────────────────────────────


def ingest_without_facade(
    store: InMemoryVectorStore, embedder: FakeEmbedder, cfg: RagConfig, raw_path: str
) -> dict:
    """
    'Ngây thơ': client tự gọi sandbox -> collect -> chunk -> embed -> kiểm cardinality
    -> delete -> upsert. Phải biết mọi subsystem, nhớ đúng thứ tự, tự xử lý lỗi từng tầng.
    Nếu quên kiểm cardinality TRƯỚC upsert => ghi chunk lệch (bug âm thầm).
    """
    # client phải tự lo health-gate (dễ quên!)
    if not store.health().get("ok"):
        return {"ok": False, "error": "store unhealthy"}
    try:
        root = resolve_in_workspace(raw_path)
    except SandboxError as exc:
        return {"ok": False, "error": str(exc)}
    total = 0
    for source in collect_files(root):
        texts = chunk_text(WORKSPACE[root][source], cfg.chunk_size, cfg.chunk_overlap)
        if not texts:
            continue
        vectors = embedder.embed(texts)
        # GIẢ SỬ client QUÊN bước kiểm cardinality (rất dễ xảy ra khi lặp logic):
        chunks = [Chunk(source, i, t, v) for i, (t, v) in enumerate(zip(texts, vectors))]
        store.delete_by_source(source)
        store.upsert(chunks)  # có thể upsert ít chunk hơn text -> lệch
        total += len(chunks)
    return {"ok": True, "chunks": total}


# ──────────────────────────────────────────────────────────────────────────────
# DEMO
# ──────────────────────────────────────────────────────────────────────────────


def demo() -> None:
    print("=" * 72)
    print("CASE 02 — RagService Facade (health-gate + chunk + embed + store)")
    print("=" * 72)

    cfg = RagConfig()
    store = InMemoryVectorStore(collection="kb")
    svc = RagService(store, FakeEmbedder(), cfg)

    print("\n[1] DÙNG FACADE: svc.ingest('docs') — 1 lời gọi, mọi subsystem ẩn.")
    res = svc.ingest("docs")
    print("    envelope =", res)
    assert res["ok"] is True
    assert res["files"] == 2 and res["chunks"] > 0
    print("    -> Client chỉ thấy {ok, files, chunks, sources}, không thấy Chunk/Embedder/path.")

    print("\n[2] search() cũng qua cùng facade & cùng dạng envelope.")
    found = svc.search("Facade pattern", top_k=2)
    print("    count =", found["count"], "| top hit source =", found["hits"][0]["source"])
    assert found["ok"] is True and found["count"] >= 1
    print("    -> Mọi lỗi/kết quả gói trong {ok: bool, ...}; không lộ kiểu nội bộ.")

    print("\n[3] HEALTH-GATE (cross-cutting): store unhealthy -> chặn cả ingest & search.")
    store.set_health(False)
    g1 = svc.ingest("docs")
    g2 = svc.search("bất kỳ")
    print("    ingest ->", g1)
    print("    search ->", g2)
    assert g1["ok"] is False and g1["code"] == "dependency_unavailable"
    assert g2["ok"] is False and g2["code"] == "dependency_unavailable"
    print("    -> Logic gate sửa ở 1 chỗ; client KHÔNG đổi dù gate tiến hoá.")
    store.set_health(True)

    print("\n[4] SANDBOX: path thoát jail -> envelope sandbox, không ném exception thô.")
    bad = svc.ingest("../../etc")
    print("    envelope =", bad)
    assert bad["ok"] is False and bad["code"] == "sandbox"

    print("\n[5] BẤT BIẾN cardinality: embedder hỏng -> facade từ chối TRƯỚC khi upsert.")
    store2 = InMemoryVectorStore(collection="kb2")
    svc_broken = RagService(store2, BrokenEmbedder(), cfg)
    before = store2.health()["count"]
    res_bad = svc_broken.ingest("docs")
    after = store2.health()["count"]
    print("    envelope =", res_bad)
    print(f"    store count: trước={before}, sau={after}")
    assert res_bad["ok"] is False and res_bad["code"] == "embed_cardinality"
    assert after == before, "FACADE không được ghi chunk lệch khi cardinality sai"
    print("    -> Facade bảo toàn bất biến: không bao giờ ghi tập chunk dở/lệch.")

    print("\n[6] ĐỐI CHỨNG: client tự điều phối & QUÊN kiểm cardinality -> ghi lệch.")
    store3 = InMemoryVectorStore(collection="naive")
    naive = ingest_without_facade(store3, BrokenEmbedder(), cfg, "docs")
    print("    envelope =", naive, "| store count =", store3.health()["count"])
    # zip() cắt theo vector ít hơn -> số chunk ghi < số text. 'ok' nhưng dữ liệu thiếu.
    assert naive["ok"] is True
    print("    -> 'ok' nhưng store nhận thiếu chunk: bug âm thầm vì thiếu chokepoint facade.")

    print("\nTẤT CẢ ASSERT QUA. RagService là facade gác sức khoẻ + điều phối 4 subsystem.")


if __name__ == "__main__":
    demo()
