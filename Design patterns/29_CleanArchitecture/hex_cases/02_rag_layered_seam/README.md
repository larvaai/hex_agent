# Case 02 — RAG Ports + Adapter Selection (Embedder & VectorStore)

> **Pattern**: Clean Architecture áp cho *external service* (vector DB + embeddings).
> Use case `RagService` chỉ phụ thuộc `EmbedderPort` + `VectorStorePort`. Đổi backend
> (memory ↔ qdrant) chỉ rewire adapter ở composition root; use case hằng định. Lazy import
> giữ lõi không kéo theo `qdrant_client` khi không cần.

---

## 1. Bối cảnh trong hex_agent

RAG (retrieval-augmented generation) cần một **vector DB** và một **model embedding**. Cả hai đều là hạ tầng nặng: `qdrant_client` cần server Docker, `fastembed` cần tải model. Nếu `RagService` import thẳng chúng thì: (a) base install buộc kéo theo dependency nặng; (b) unit-test phải dựng Qdrant; (c) đổi sang Weaviate/Pinecone phải sửa logic.

hex_agent giải đúng theo Clean Architecture: **domain định nghĩa port**, adapter ở vòng ngoài implement, composition root chọn adapter theo config.

- `EmbedderPort` và `VectorStorePort` (Protocol) được khai báo trong **`rag/ports.py:24-36`**, cạnh các value object `Chunk`/`Hit` (**`rag/ports.py:8-21`**) và `RagConfig` (**`rag/ports.py:39-57`**).
- `RagService` (use case) ở **`rag/service.py:15-113`** chỉ gọi port; docstring file ghi rõ "logic never touches Qdrant directly (only via `VectorStorePort`)".
- `QdrantVectorStore` (adapter production) ở **`rag/stores_qdrant.py:32-49`**, **lazy import** `from qdrant_client import QdrantClient` tại **line 43** — nên base install không cần qdrant.
- Composition root **`rag/feature.py:27-42`** (`build_service`) đọc `backend` từ config: `memory` (default, offline) dùng adapter in-memory; `qdrant` mới lazy-import adapter production.

---

## 2. Trích đoạn code thật

Ports owned by domain (`rag/ports.py:24-36`):

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

Lazy import bên trong adapter — core không bao giờ thấy import này (`rag/stores_qdrant.py:40-49`):

```python
if client is not None:
    self._client = client
else:
    from qdrant_client import QdrantClient  # noqa: PLC0415 — optional dep
    self._client = QdrantClient(
        url=config.qdrant_url, timeout=config.qdrant_timeout, check_compatibility=False
    )
```

Composition root chọn adapter theo config (`rag/feature.py:27-42`):

```python
def build_service(config: dict[str, Any] | None) -> RagService:
    cfg = RagConfig.from_dict(config or {})
    backend = (config.get("backend") or "memory").lower()
    if backend == "memory":
        store = InMemoryVectorStore(collection=cfg.collection)
        embedder = FakeEmbedder()
        return RagService(store, embedder, cfg)
    if backend == "qdrant":
        from rag.embedders import FastEmbedEmbedder      # lazy
        from rag.stores_qdrant import QdrantVectorStore  # lazy
        return RagService(QdrantVectorStore(cfg), FastEmbedEmbedder(cfg.model), cfg)
    raise ValueError(f"Unknown rag backend: {backend!r}")
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Clean Architecture | Thành phần trong hex_agent | File:line |
|---|---|---|
| **Entities / Value Object (vòng 1)** | `Chunk`, `Hit` (frozen dataclass) | `rag/ports.py:8-21` |
| **DIP metadata** | `RagConfig` (backend, collection, top_k...) | `rag/ports.py:39-57` |
| **Output port** | `EmbedderPort`, `VectorStorePort` (Protocol) | `rag/ports.py:24-36` |
| **Use case (vòng 2)** | `RagService.ingest/search` gọi port, health-gate | `rag/service.py:15-113` |
| **Adapter production (vòng 3)** | `QdrantVectorStore`, lazy import client | `rag/stores_qdrant.py:32-49` |
| **Adapter offline (vòng 3)** | `InMemoryVectorStore`, `FakeEmbedder` | `rag/stores.py`, `rag/embedders.py` |
| **Composition root (vòng 4)** | `build_service` chọn adapter theo `backend` | `rag/feature.py:27-42` |

---

## 4. Bản rút gọn chạy được

File: [`rag_layered_seam.py`](rag_layered_seam.py)

Nó **mô phỏng**:
- Value object `Chunk`/`Hit`, `RagConfig`, hai port, use case `RagService` (health-gate + ingest + search).
- Hai adapter store cùng implement `VectorStorePort`: `InMemoryVectorStore` (offline) và `QdrantVectorStore` (production-style, có lazy import). Một `FakeEmbedder` implement `EmbedderPort`.
- Composition root `build_service` chọn adapter theo `backend`.
- Một bộ đếm `_HEAVY_DEP_IMPORTS` đứng thay `from qdrant_client import QdrantClient` để **chứng minh lazy import**: build `memory` không chạm dep nặng; chỉ build `qdrant` mới chạm.
- Đối chứng `UnreachableVectorStore`: server chết → `health()` trả `ok=False` (không raise), use case trả envelope `dependency_unavailable`.

Nó **lược bỏ** (so với bản thật):
- Qdrant client + server thật → `QdrantVectorStore` ở đây bọc một `InMemoryVectorStore` phía sau; "import nặng" được giả lập bằng một hàm đếm.
- `fastembed`/model BGE thật → `FakeEmbedder` hashing-bag-of-words (cùng từ → gần nhau), đủ để cosine search trả kết quả hợp lý mà không cần numpy.
- Sandbox jail đọc file, chunking theo ký tự, deterministic point-id `uuid5`, payload index → bỏ; `ingest` nhận sẵn `{source: text}`.

Chạy:

```bash
python3 rag_layered_seam.py
```

Các `assert` chứng minh: (a) cùng query cho cùng top hit ở cả hai backend (use case bất biến); (b) cả hai adapter + embedder thoả Protocol; (c) lazy import chỉ tăng khi tạo `QdrantVectorStore`, không tăng khi build `memory`; (d) health-gate trả envelope thay vì crash khi store chết.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Port khoá API tối thiểu chung**: `VectorStorePort` chỉ phơi `health/delete/upsert/search`. Nếu một backend có tính năng đặc thù (ví dụ hybrid search của Qdrant) mà bạn muốn dùng, hoặc phải mở rộng port (mọi adapter phải theo), hoặc phải "rò rỉ" abstraction — cả hai đều có giá.
- **Lazy import là con dao hai lưỡi**: lỗi import (thiếu `qdrant_client`) bị dời tới *runtime* lúc build service, thay vì lúc khởi động. Phải có test/health-check bắt sớm.
- **Chỉ đáng khi thực sự có ≥ 2 backend** (hoặc chắc chắn sẽ swap). Với một app chỉ-Qdrant-mãi-mãi, một lớp port là chi phí không sinh lời; gọi thẳng client đơn giản hơn.
- Như bài học gốc nhấn mạnh: pattern này đáng giá theo *churn của vùng hạ tầng*. hex_agent giữ cả memory (offline test, docker-free) lẫn qdrant (prod) nên rất đáng.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `from qdrant_client import QdrantClient` nằm **bên trong** `QdrantVectorStore.__init__` (`rag/stores_qdrant.py:43`) chứ không ở đầu file? Điều gì xảy ra với base install nếu nó ở đầu file?
2. `RagService.health()` gọi `store.health()`. Vì sao `QdrantVectorStore.health()` được thiết kế để **không bao giờ raise** (`rag/stores_qdrant.py:83-90`)? Liên hệ tới health-gate trong `rag/service.py:30-39`.
3. Muốn thêm backend Weaviate, bạn phải tạo/sửa những file nào? `RagService` có nằm trong số đó không? Vì sao?
