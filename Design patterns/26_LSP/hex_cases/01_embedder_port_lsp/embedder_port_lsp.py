"""
LSP case 01 — EmbedderPort: FakeEmbedder & FastEmbedEmbedder thay thế cho nhau.

Bản DISTILL TRUNG THỰC (chỉ stdlib) của seam port-adapter trong hex_agent.

NGUỒN THẬT đã mở kiểm chứng (đường dẫn tương đối so với /Users/uspro/Desktop/namnson/hex_agent):
  - rag/ports.py:24-28        EmbedderPort(Protocol): dim: int ; embed(texts) -> list[list[float]]  (@runtime_checkable)
  - rag/embedders.py:33-46    FakeEmbedder  — offline, hash bag-of-words, .dim + .embed
  - rag/embedders.py:49-60    FastEmbedEmbedder — production, lazy fastembed, .dim + .embed
  - rag/service.py:15-19      RagService.__init__ phụ thuộc EmbedderPort (abstraction), không isinstance
  - rag/service.py:63         vectors = self._embedder.embed(texts)  (ingest)
  - rag/service.py:64-69      RagService TỪ CHỐI cardinality mismatch: len(vectors) != len(texts) -> ValueError
  - rag/service.py:97         vector = self._embedder.embed([query])[0]  (search)
  - tests_audit/test_rag_edges_rigor.py:95-99   isinstance(FastEmbedEmbedder, EmbedderPort)
  - tests_audit/test_rag_edges_rigor.py:103-108 FakeEmbedder: [] -> [] ; text rỗng -> zero-vector

CONTRACT của EmbedderPort (cái mà RagService dựa vào):
  - Precondition : texts là list[str] BẤT KỲ, kể cả [] (rỗng được chấp nhận).
  - Postcondition: trả list[list[float]] với len(output) == len(texts) (cardinality khớp).
  - Invariant    : .dim không đổi trong suốt vòng đời 1 instance.
  - Exception    : không "mở rộng" exception type ra ngoài hợp đồng caller.
LSP: mọi impl giữ contract -> RagService swap được mà KHÔNG cần if/elif theo loại.
"""
from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable


# ───────────────────────── ABSTRACTION (supertype) ─────────────────────────
# Distill của rag/ports.py:24-28 (EmbedderPort Protocol, @runtime_checkable).
@runtime_checkable
class EmbedderPort(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


# ───────────────────────── SUBTYPE 1: offline (FakeEmbedder) ───────────────
# Distill của rag/embedders.py:33-46.
class FakeEmbedder:
    """Embedder offline, tất định: bag-of-words băm rồi chuẩn hóa. Không model, không network."""

    def __init__(self, dim: int = 16) -> None:
        self.dim = dim  # invariant: cố định sau __init__

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Postcondition: 1 vector cho mỗi text -> len(output) == len(texts).
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in text.lower().split():
            bucket = int.from_bytes(
                hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest(), "big"
            ) % self.dim
            vec[bucket] += 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm else vec


# ───────────────────────── SUBTYPE 2: "production" (giả lập fastembed) ─────
# Distill của rag/embedders.py:49-60. Bản thật lazy-import fastembed + probe dim 1 lần.
# Ở đây ta thay model nặng bằng một "fake model" stdlib nhưng GIỮ NGUYÊN cấu trúc:
# probe dim đúng 1 lần trong __init__, embed() materialize ra list[list[float]].
class _StubTextEmbedding:
    """Đứng thay TextEmbedding của fastembed: map mỗi từ -> vector cố định theo độ dài."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._width = 3

    def embed(self, texts: list[str]):
        for t in texts:
            n = float(len(t))
            yield (n, n + 1.0, n + 2.0)  # generator -> bản thật cũng nhận generator


class FastEmbedEmbedder:
    """Embedder 'production': lazy build model + probe dim một lần (như bản thật)."""

    def __init__(self, model: str) -> None:
        self._model = _StubTextEmbedding(model)  # bản thật: from fastembed import TextEmbedding
        # rag/embedders.py:57 — probe dim đúng 1 lần từ vector đầu của "probe".
        self.dim = len(next(iter(self._model.embed(["probe"]))))

    def embed(self, texts: list[str]) -> list[list[float]]:
        # rag/embedders.py:60 — materialize generator thành list[list[float]].
        return [list(v) for v in self._model.embed(texts)]


# ───────────────────────── CALLER (depend on abstraction) ──────────────────
# Distill của rag/service.py:15-19, 63-69, 97. Caller CHỈ biết EmbedderPort.
class RagService:
    def __init__(self, embedder: EmbedderPort, *, dim_required: int | None = None) -> None:
        self._embedder = embedder  # không lưu loại cụ thể, không isinstance
        self._dim = dim_required

    def ingest(self, texts: list[str]) -> dict:
        vectors = self._embedder.embed(texts)  # rag/service.py:63
        # rag/service.py:64-69 — TỪ CHỐI cardinality mismatch trước khi upsert.
        if len(vectors) != len(texts):
            raise ValueError(
                f"embedder returned {len(vectors)} embeddings for {len(texts)} chunks (count mismatch)."
            )
        return {"ok": True, "chunks": len(vectors)}

    def search(self, query: str) -> list[float]:
        return self._embedder.embed([query])[0]  # rag/service.py:97


# ───────────────────────── LISKOV CONTRACT TEST (abstract) ─────────────────
def liskov_contract(embedder: EmbedderPort) -> None:
    """Bộ test contract chạy y hệt trên MỌI impl — đây là bằng chứng LSP."""
    # 1. isinstance theo Protocol cấu trúc (rag .../test_rag_edges_rigor.py:99).
    assert isinstance(embedder, EmbedderPort), "phải thỏa EmbedderPort (.dim + .embed)"
    # 2. Precondition: chấp nhận list rỗng -> trả rỗng.
    assert embedder.embed([]) == [], "embed([]) phải là []"
    # 3. Postcondition: cardinality khớp.
    out = embedder.embed(["alpha beta", "gamma", "delta epsilon zeta"])
    assert len(out) == 3, "len(output) phải == len(texts)"
    assert all(isinstance(v, list) for v in out), "mỗi phần tử là list[float] (không generator/tuple)"
    # 4. Invariant: dim không đổi qua nhiều lần gọi.
    d = embedder.dim
    embedder.embed(["x"])
    assert embedder.dim == d, "dim phải bất biến trong vòng đời instance"


def demo() -> None:
    print("=" * 72)
    print("LSP case 01 — EmbedderPort: FakeEmbedder & FastEmbedEmbedder swap")
    print("=" * 72)

    fake = FakeEmbedder(dim=16)
    fast = FastEmbedEmbedder("BAAI/bge-small-en-v1.5")

    print("\n[1] Chạy Liskov contract test trên CẢ HAI impl (cùng 1 bộ assert):")
    for name, emb in (("FakeEmbedder", fake), ("FastEmbedEmbedder", fast)):
        liskov_contract(emb)
        print(f"    - {name:18s}: PASS  (dim={emb.dim})")

    print("\n[2] RagService phụ thuộc abstraction — KHÔNG đổi 1 dòng khi swap embedder:")
    for name, emb in (("FakeEmbedder", fake), ("FastEmbedEmbedder", fast)):
        svc = RagService(emb)
        res = svc.ingest(["câu một", "câu hai", "câu ba"])
        print(f"    - RagService(embedder={name:18s}).ingest(3 texts) -> {res}")
        assert res == {"ok": True, "chunks": 3}

    print("\n[3] ĐỐI CHỨNG — một subtype VI PHẠM postcondition (weaken cardinality):")

    class BrokenEmbedder:
        """Trả ÍT vector hơn số text -> phá postcondition len(out)==len(texts)."""

        dim = 16

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] * self.dim]  # luôn 1 vector, bất kể số text!

    broken = BrokenEmbedder()
    # Nó vẫn "trông giống" EmbedderPort về cấu trúc:
    assert isinstance(broken, EmbedderPort), "cấu trúc khớp nhưng HÀNH VI sai"
    print("    - isinstance(broken, EmbedderPort) =", isinstance(broken, EmbedderPort), "(qua mặt cấu trúc!)")
    svc = RagService(broken)
    try:
        svc.ingest(["a", "b", "c"])  # 3 text nhưng nhận 1 vector
        raise AssertionError("đáng lẽ phải lỗi")
    except ValueError as exc:
        print(f"    - ingest 3 text -> ValueError: {exc}")
        print("    => LSP dạy: 'trông giống' (cấu trúc) KHÁC 'thay được' (hợp đồng).")
        print("       RagService bắt vi phạm ở chokepoint cardinality (rag/service.py:64-69).")

    print("\n[4] Kết luận: 2 impl LSP-compliant -> caller không cần if/elif theo loại.")
    print("    Subtype phá postcondition -> caller buộc phòng thủ -> chính là OCP collapse.")
    print("\nTẤT CẢ ASSERT PASS. ✅")


if __name__ == "__main__":
    demo()
