"""
Case 03 — RAG build_service (Simple Factory) + nâng cấp lên Registry Factory.

DISTILL TRUNG THỰC TỪ MÃ THẬT:
  - rag/feature.py:27-42   (build_service(config) -> RagService; if-elif chọn backend)
  - rag/feature.py:109-121 (install(kernel): build_service rồi bọc 3 tool)
  - rag/stores.py:24       (class InMemoryVectorStore — concrete product)
  - rag/stores_qdrant.py:32(class QdrantVectorStore — concrete product, import lười)
  - tests/test_rag.py:146-150 (test_build_service_rejects_unknown_backend)

ĐÂY LÀ RANH GIỚI DẠY HỌC quan trọng của bài Factory Method:
build_service KHÔNG phải Factory Method (GoF) — nó là SIMPLE FACTORY: một hàm
duy nhất with if-elif chọn implementation theo tham số 'backend'. Bài học gốc
gọi chính kiểu if-else này là anti-pattern khi số nhánh phình to.

Nó vẫn ổn cho "vài backend cắm-rút" + import lười (chỉ import Qdrant khi cần).
Nhưng nếu thêm backend liên tục, ta NÊN nâng lên registry-based factory: mỗi
backend tự đăng ký 'builder' của mình, hàm chung không bao giờ phải sửa nữa.

Bản distill dùng stdlib. Lược bỏ: embedding thật, Qdrant/network. Giữ nguyên
vai trò: cùng một interface RagService trả về dù backend nào; config quyết định
concrete product; import lười mô phỏng bằng builder gọi trễ.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


# ─────────────────────────────────────────────────────────────────────────────
# Product interface + concrete products (distill từ rag/stores*.py)
# ─────────────────────────────────────────────────────────────────────────────
class VectorStore(Protocol):
    name: str
    def upsert(self, doc: str) -> None: ...
    def search(self, query: str) -> list[str]: ...


class InMemoryVectorStore:
    """Distill từ rag/stores.py:24 — backend offline, không cần docker."""

    name = "memory"

    def __init__(self, collection: str) -> None:
        self.collection = collection
        self._docs: list[str] = []

    def upsert(self, doc: str) -> None:
        self._docs.append(doc)

    def search(self, query: str) -> list[str]:
        return [d for d in self._docs if query.lower() in d.lower()]


class FakeQdrantVectorStore:
    """Distill từ rag/stores_qdrant.py:32 — ở đây fake hoá hoàn toàn (không network).

    Trong mã thật, class này chỉ được import KHI backend == 'qdrant' (import lười,
    rag/feature.py:36-37) để cài đặt base khỏi nặng. Ta mô phỏng 'import lười'
    bằng việc builder của qdrant mới khởi tạo class này."""

    name = "qdrant"

    def __init__(self, url: str) -> None:
        self.url = url
        self._docs: list[str] = []

    def upsert(self, doc: str) -> None:
        self._docs.append(doc)

    def search(self, query: str) -> list[str]:
        return [d for d in self._docs if query.lower() in d.lower()]


@dataclass
class RagService:
    """Interface chung trả về bất kể backend (distill từ rag/service.RagService)."""

    store: VectorStore

    def health(self) -> dict[str, Any]:
        return {"ok": True, "backend": self.store.name}

    def ingest(self, doc: str) -> dict[str, Any]:
        self.store.upsert(doc)
        return {"ok": True, "chunks": 1}

    def search(self, query: str) -> dict[str, Any]:
        hits = self.store.search(query)
        return {"ok": True, "count": len(hits), "hits": hits}


# ─────────────────────────────────────────────────────────────────────────────
# (A) SIMPLE FACTORY — distill TRUNG THỰC từ rag/feature.py:27-42
# ─────────────────────────────────────────────────────────────────────────────
def build_service(config: dict[str, Any] | None) -> RagService:
    """Một hàm if-elif chọn backend. Đây là Simple Factory, KHÔNG phải GoF FM.

    Giữ đúng cấu trúc thật: default 'memory'; 'qdrant' import lười; else ValueError.
    """
    config = config or {}
    collection = config.get("collection", "default")
    backend = (config.get("backend") or "memory").lower()
    if backend == "memory":
        return RagService(InMemoryVectorStore(collection=collection))
    if backend == "qdrant":
        # mô phỏng import lười: chỉ "kéo" Qdrant vào khi thật sự cần.
        url = config.get("url", "http://localhost:6333")
        return RagService(FakeQdrantVectorStore(url=url))
    raise ValueError(f"Unknown rag backend: {backend!r}")


# ─────────────────────────────────────────────────────────────────────────────
# (B) NÂNG CẤP -> REGISTRY-BASED FACTORY (khi backend thêm thường xuyên)
# ─────────────────────────────────────────────────────────────────────────────
# Mỗi backend đăng ký một "builder". Hàm dựng chung KHÔNG còn if-elif nữa,
# nên thêm backend mới = đăng ký thêm 1 builder, không sửa hàm chung (Open-Closed).
_BACKENDS: dict[str, Callable[[dict[str, Any]], RagService]] = {}


def register_backend(name: str, builder: Callable[[dict[str, Any]], RagService]) -> None:
    if name in _BACKENDS:
        raise ValueError(f"Backend '{name}' already registered.")
    _BACKENDS[name] = builder


def build_service_registry(config: dict[str, Any] | None) -> RagService:
    config = config or {}
    backend = (config.get("backend") or "memory").lower()
    try:
        builder = _BACKENDS[backend]
    except KeyError:
        known = ", ".join(sorted(_BACKENDS)) or "(none)"
        raise ValueError(f"Unknown rag backend: {backend!r}. Known: {known}") from None
    return builder(config)


# Đăng ký các backend có sẵn (tương đương 2 nhánh if-elif, nhưng tách rời):
register_backend("memory", lambda c: RagService(InMemoryVectorStore(c.get("collection", "default"))))
register_backend("qdrant", lambda c: RagService(FakeQdrantVectorStore(c.get("url", "http://localhost:6333"))))


def demo() -> None:
    print("=" * 72)
    print("CASE 03 — RAG build_service (Simple Factory) -> Registry Factory")
    print("Nguồn thật: rag/feature.py:27-42 ; tests/test_rag.py:146-150")
    print("=" * 72)

    print("\n[1] Simple Factory: cùng interface RagService dù backend khác nhau.")
    mem = build_service({"backend": "memory"})
    qdr = build_service({"backend": "qdrant"})
    print(f"    memory.health() = {mem.health()}")
    print(f"    qdrant.health() = {qdr.health()}")
    # Client xài giống hệt nhau, không cần biết concrete store:
    assert isinstance(mem, RagService) and isinstance(qdr, RagService)
    assert mem.health()["backend"] == "memory"
    assert qdr.health()["backend"] == "qdrant"

    print("\n[2] Client thao tác qua interface chung, bất kể backend.")
    for svc, label in [(mem, "memory"), (qdr, "qdrant")]:
        svc.ingest("alpha alpha alpha")
        res = svc.search("alpha")
        print(f"    [{label}] ingest+search('alpha') -> count = {res['count']}")
        assert res["count"] == 1

    print("\n[3] Default backend = 'memory' khi config rỗng (rag/feature.py:30).")
    assert build_service(None).health()["backend"] == "memory"
    assert build_service({}).health()["backend"] == "memory"
    print("    build_service(None) và build_service({}) -> memory. OK.")

    print("\n[4] Xử lý lỗi: backend lạ -> ValueError (khớp test_rag.py:146-150).")
    try:
        build_service({"backend": "weaviate"})
        raise AssertionError("phải reject backend lạ")
    except ValueError as e:
        print(f"    build_service({{'backend':'weaviate'}}) -> {e}")
        assert "backend" in str(e)

    print("\n[5] VÌ SAO ĐÂY LÀ RANH GIỚI: thêm 1 backend 'weaviate' vào Simple Factory")
    print("    nghĩa là SỬA hàm build_service (thêm 1 nhánh if). Khi nhánh phình to,")
    print("    đó chính là anti-pattern bài học cảnh báo.")

    print("\n[6] NÂNG CẤP -> Registry Factory: thêm backend = đăng ký, KHÔNG sửa hàm chung.")

    def _weaviate_builder(c: dict[str, Any]) -> RagService:
        # Emulator dùng tạm InMemoryVectorStore nhưng đặt lại name để health()
        # báo đúng backend được yêu cầu ('weaviate-emu'), tránh hiểu lầm 'memory'.
        store = InMemoryVectorStore(c.get("collection", "weaviate-emu"))
        store.name = "weaviate-emu"
        return RagService(store)

    register_backend("weaviate", _weaviate_builder)
    wv = build_service_registry({"backend": "weaviate"})
    print(f"    build_service_registry({{'backend':'weaviate'}}) -> {wv.health()}")
    assert isinstance(wv, RagService)
    assert wv.health()["backend"] == "weaviate-emu"
    # Backend cũ vẫn chạy, không regression:
    assert build_service_registry({"backend": "memory"}).health()["backend"] == "memory"
    print("    -> memory/qdrant cũ vẫn chạy; 'weaviate' thêm mà không đụng hàm dựng. Open-Closed.")

    print("\n[7] Registry vẫn báo lỗi gọn cho backend chưa đăng ký.")
    try:
        build_service_registry({"backend": "pinecone"})
        raise AssertionError("phải reject backend chưa đăng ký")
    except ValueError as e:
        print(f"    {e}")

    print("\nKẾT LUẬN: build_service là Simple Factory — ổn cho ít backend + import lười.")
    print("Khi backend thêm thường xuyên hoặc khởi tạo backend phức tạp dần, nâng lên")
    print("Registry Factory để tuân Open-Closed. Bài học: biết KHI NÀO Simple Factory đủ,")
    print("KHI NÀO phải nâng cấp.")
    print("\nTẤT CẢ ASSERT ĐỀU PASS.")


if __name__ == "__main__":
    demo()
