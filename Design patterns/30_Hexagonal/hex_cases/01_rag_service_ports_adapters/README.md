# Case 01 — RAG Service: hai adapter cạnh tranh cho một DRIVEN PORT

> Đây là ví dụ "sách giáo khoa" của Hexagonal: **một** driven port, **hai** adapter (offline + production)
> tranh nhau cắm vào, lõi `RagService` không biết cái nào đang chạy.

---

## 1. Bối cảnh trong hex_agent

RAG (Retrieval-Augmented Generation) cần hai thứ ngoài lõi: **embedder** (biến text → vector) và
**vector store** (lưu/tìm vector). Production dùng `fastembed` + Qdrant (cần docker, network).
Nhưng bộ test chấp nhận (acceptance suite) phải chạy **hoàn toàn offline** — không docker, không network.

hex_agent giải bằng Hexagonal: lõi `RagService` chỉ phụ thuộc hai **driven port**, còn việc dùng
Qdrant hay in-memory là quyết định của **composition root**.

- `rag/ports.py:24-36` — định nghĩa `EmbedderPort` và `VectorStorePort` (chỉ `Protocol`, không impl).
- `rag/service.py:15-19` — `RagService.__init__(self, store: VectorStorePort, embedder: EmbedderPort, config)`.
- `rag/service.py:78-113` — `search()` gọi `self._embedder.embed(...)` rồi `self._store.search(...)` — lõi gọi RA port.
- `rag/stores.py:24-57` — `InMemoryVectorStore` (adapter offline, cosine in-memory).
- `rag/stores_qdrant.py:32-148` — `QdrantVectorStore` (adapter production qua qdrant-client).
- `rag/feature.py:27-42` — `build_service()` chọn adapter theo `config['backend']` (`memory` mặc định, `qdrant` tùy chọn).

Lời tự thuật của codebase (`rag/__init__.py:1-7`):
> "Production uses Qdrant + fastembed, but all logic sits behind `VectorStorePort` and `EmbedderPort`
> so the acceptance suite runs fully offline against `InMemoryVectorStore` + `FakeEmbedder`."

---

## 2. Trích đoạn code thật

Driven port — lõi sở hữu, adapter uốn theo (`rag/ports.py:24-36`):

```python
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
```

Lõi nhận port qua DI, gọi RA, không biết adapter cụ thể (`rag/service.py:15-19` + `:97-98`):

```python
class RagService:
    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._cfg = config
    # ...
        vector = self._embedder.embed([query])[0]      # gọi RA driven port
        hits = self._store.search(vector, k, threshold) # gọi RA driven port
```

Composition root chọn adapter theo config (`rag/feature.py:30-41`):

```python
backend = (config.get("backend") or "memory").lower()
if backend == "memory":
    store = InMemoryVectorStore(collection=cfg.collection)
    embedder = FakeEmbedder()
    return RagService(store, embedder, cfg)
if backend == "qdrant":
    from rag.stores_qdrant import QdrantVectorStore  # lazy import — base install không cần qdrant-client
    store = QdrantVectorStore(cfg)
    embedder = FastEmbedEmbedder(cfg.model)
    return RagService(store, embedder, cfg)
```

---

## 3. Ánh xạ vai trò Hexagonal ↔ code thật

| Vai Hexagonal | Thành phần code thật (hex_agent) | Trong bản distill |
|---|---|---|
| **Driven Port** (lõi định nghĩa, lõi gọi ra) | `EmbedderPort`, `VectorStorePort` — `rag/ports.py:24-36` | `EmbedderPort`, `VectorStorePort` |
| **Domain Core** (logic thuần, inject deps) | `RagService` — `rag/service.py:15-113` | `RagService` |
| **Driven Adapter** (offline, test) | `InMemoryVectorStore` — `rag/stores.py:24-57` | `InMemoryVectorStore` |
| **Driven Adapter** (production) | `QdrantVectorStore` — `rag/stores_qdrant.py:32-148` | `QdrantVectorStore` + `FakeQdrantClient` |
| **Composition Root** (chọn adapter theo config) | `build_service()` — `rag/feature.py:27-42` | `build_service()` |

---

## 4. Bản rút gọn chạy được

File: [`rag_service_ports_adapters.py`](./rag_service_ports_adapters.py) — chạy `python3 rag_service_ports_adapters.py`.

**Mô phỏng gì:**
- `RagService` nguyên vẹn cấu trúc: nhận `store` + `embedder` qua `__init__`, health-gate trước
  mọi ingest/search, gọi RA port để embed rồi search.
- Hai adapter cùng `VectorStorePort`: `InMemoryVectorStore` (cosine in-memory) và `QdrantVectorStore`
  (dịch port → API của một `FakeQdrantClient`).
- `build_service({"backend": ...})` là composition root chọn adapter.
- Demo chứng minh: top-hit của `memory` và `qdrant` **giống hệt** → lõi không phụ thuộc adapter;
  health-gate bắt được store hỏng / Qdrant chết mà không crash.

**Lược bỏ gì:**
- `qdrant-client` thật + network → `FakeQdrantClient` bằng `dict` (giữ nguyên ranh giới adapter).
- `fastembed`/model thật → `HashingEmbedder` băm token (deterministic, không cần tải model).
- sandbox + chunking + ingest-from-file → `ingest()` nhận thẳng `list[str]`.
- **Bớt một method khỏi port**: `VectorStorePort` bản distill chỉ giữ 3 method (`health`, `upsert`, `search`),
  bỏ `delete_by_source(source) -> int` có trong nguồn thật (`rag/ports.py:34`). Đây là lược bỏ có chủ ý cho
  mục đích dạy học — search/ingest đủ minh họa "lõi gọi RA port"; xoá theo source không thêm gì cho bài học port/adapter.

Có một **phản ví dụ** `LeakyRagService`: lõi tự `new InMemoryVectorStore()` trong `__init__` →
hard-code I/O → muốn đổi Qdrant phải sửa lõi. Đây chính là *Leaky core* mà Hexagonal cấm
(bài gốc, Ví dụ 2 — Vi phạm A).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chỉ có một backend mãi mãi**: nếu hệ thống không bao giờ cần đổi store (vd luôn là Postgres),
  thì cặp port + 1 adapter chỉ là boilerplate. Hex trả về tiền khi có **≥ 2 adapter alternatives** —
  đúng như hex_agent (Qdrant cho prod, InMemory cho test).
- **CRUD đơn giản**: nếu "search" chỉ là `SELECT ... LIKE`, một port `VectorStorePort` 4 method là quá nặng.
- **Mỗi field một port**: chống cám dỗ tách port quá nhỏ. hex_agent gom đúng theo *role* (một store, một embedder),
  không phải mỗi method một port.
- Chi phí: phải duy trì **contract test** cho cả hai adapter (InMemory phải hành xử như Qdrant ở các bất biến
  như sắp xếp theo score, lọc theo threshold), nếu không hai adapter sẽ lệch nhau.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `health()` của `QdrantVectorStore` **bắt mọi exception và trả `{"ok": False}`** thay vì để ném ra?
   (Gợi ý: `rag/service.py:30-39` dùng `_require_healthy()` như *control flow*, không phải xử lý exception.)
2. `build_service` dùng `from rag.stores_qdrant import QdrantVectorStore` **bên trong** nhánh `backend=="qdrant"`
   chứ không import ở đầu file. Điều này phục vụ bất biến Hexagonal nào? Nếu import ở đầu file thì base install
   gặp vấn đề gì?
3. Trong demo, top-hit của `memory` và `qdrant` giống nhau. Nếu một ngày `QdrantVectorStore.search` trả thứ tự
   *khác* `InMemoryVectorStore.search` cho cùng dữ liệu, đó là lỗi ở đâu — ở lõi, ở port, hay ở adapter? Vì sao?
