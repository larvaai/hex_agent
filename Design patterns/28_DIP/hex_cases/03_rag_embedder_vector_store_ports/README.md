# Case 03 — `EmbedderPort` & `VectorStorePort`: tách hạ tầng RAG khỏi logic

> DIP (Dependency Inversion Principle) — SOLID Pattern 5
> Domain `rag/` (cấp cao) ĐỊNH NGHĨA hai port; hạ tầng (fastembed, Qdrant) ADAPT theo.

---

## 1. Bối cảnh trong hex_agent

`RagService` chứa logic nghiệp vụ RAG: health-gate trước mỗi ingest/search, chunk + embed văn
bản, upsert/search vector. Nhưng việc embed thực tế cần model nặng (fastembed) và việc lưu
vector cần một vector DB (Qdrant). Nếu `RagService` import thẳng `qdrant_client` và `fastembed`
thì: unit test phải dựng Qdrant (docker) + tải model (mạng), và đổi sang Pinecone/Weaviate phải
sửa logic.

hex_agent giải bằng DIP. Domain `rag/ports.py` định nghĩa `EmbedderPort` (`dim` + `embed`) và
`VectorStorePort` (`health/delete_by_source/upsert/search`). Docstring `rag/ports.py:1` gọi
thẳng đây là **"the seam between logic and infra"** — port CHÍNH LÀ đường nối. `FakeEmbedder`
là adapter offline cho test; `FastEmbedEmbedder` là adapter production (lazy import `fastembed`);
`QdrantVectorStore` là adapter production (lazy import `qdrant_client`, cho phép tiêm `client`).
`RagService` nhận store + embedder + config qua constructor (DI) và chỉ gọi method của port.

File:line thật đã mở kiểm chứng:
- `rag/ports.py:24-28` — `EmbedderPort` Protocol.
- `rag/ports.py:31-36` — `VectorStorePort` Protocol.
- `rag/embedders.py:33-46` — `FakeEmbedder` (adapter offline).
- `rag/embedders.py:49-60` — `FastEmbedEmbedder` (adapter production, lazy import dòng 53).
- `rag/stores_qdrant.py:32-49` — `QdrantVectorStore` (adapter production, lazy import dòng 43, `client` tiêm được).
- `rag/service.py:15-19` — `RagService.__init__` nhận port qua DI.

---

## 2. Trích đoạn code thật

`rag/ports.py:24-36` — hai abstraction là "the seam":

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

`rag/service.py:15-19` — consumer nhận port qua constructor (DI), không biết backend:

```python
class RagService:
    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._cfg = config
```

`rag/stores_qdrant.py:40-49` — adapter lazy-import + cho phép tiêm client (để test):

```python
        if client is not None:
            self._client = client
        else:
            from qdrant_client import QdrantClient  # noqa: PLC0415 — optional dep
            self._client = QdrantClient(
                url=config.qdrant_url, timeout=config.qdrant_timeout, check_compatibility=False
            )
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò DIP | Thành phần trong hex_agent | Trong bản rút gọn |
|---|---|---|
| Abstraction (do cấp cao sở hữu) | `EmbedderPort`, `VectorStorePort` — `rag/ports.py:24-36` | `EmbedderPort`, `VectorStorePort` |
| Cấp cao tiêu thụ (consumer) | `RagService` — `rag/service.py:15-...` | `RagService` |
| Adapter embedder (test/offline) | `FakeEmbedder` — `rag/embedders.py:33-46` | `FakeEmbedder` |
| Adapter embedder (production) | `FastEmbedEmbedder` — `rag/embedders.py:49-60` | `StubFastEmbedEmbedder` |
| Adapter store (production) | `QdrantVectorStore` — `rag/stores_qdrant.py:32-148` | `StubQdrantVectorStore` |
| Adapter store (fake) | `InMemoryVectorStore` (test doubles, `rag/stores.py`) | `InMemoryVectorStore` |
| Composition root / factory | `rag/feature.py:build_service` | `build_service()` |

Đảo chiều source code: `rag/service.py` chỉ import `rag/ports.py`; `qdrant_client`/`fastembed`
chỉ được import **bên trong adapter** (lazy), nên base install và test offline không cần chúng.

---

## 4. Bản rút gọn chạy được

File: `rag_embedder_vector_store_ports.py` (chỉ thư viện chuẩn).

Mô phỏng đầy đủ: hai port Protocol; `FakeEmbedder` (bag-of-words hash chuẩn hoá, giữ đúng tinh
thần bản gốc: cùng text → cosine ~1.0, rời rạc → ~0.0); hai store adapter (`InMemoryVectorStore`,
`StubQdrantVectorStore` với client tiêm được); `RagService` với health-gate, ingest (embed →
delete cũ → upsert) và search (validate → embed query → search); factory `build_service()`.

Lược bỏ / thay bằng fake: `fastembed` → `StubFastEmbedEmbedder` (không import gì ngoài, tái dùng
logic vector); `qdrant_client` → `StubQdrantVectorStore` bọc một in-memory client; workspace
sandbox + đọc/chunk file thật → `ingest()` nhận thẳng `list[str]` thay vì path; bỏ redaction và
cardinality-check chi tiết (giữ lại check count-mismatch vì nó là bất biến đáng minh hoạ).

Chạy:

```bash
python3 rag_embedder_vector_store_ports.py
```

Bước [3]/[4] swap store và embedder qua DI mà `RagService` không đổi. Bước [5] health-gate. Bước
[7] là đối chứng nếu import thẳng `qdrant_client` + `fastembed`.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- Hai port + nhiều adapter → nhiều file. Với prototype RAG dùng một backend cố định và không
  cần test offline, import thẳng có thể nhanh hơn.
- Rủi ro **leaky abstraction**: nếu port lỡ để lộ chi tiết Qdrant (vd nhận filter syntax riêng
  của Qdrant) thì adapter Pinecone không drop-in được nữa. Port phải nói ngôn ngữ domain
  (`search(vector, top_k, threshold)`), không nói ngôn ngữ backend.
- `FakeEmbedder` là xấp xỉ có chủ đích (lossy): điểm số không khớp model thật, nên nó phục vụ
  test logic chứ không thay được đánh giá chất lượng embedding production.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao việc `QdrantVectorStore` cho phép **tiêm** `client` (thay vì luôn tự tạo) lại giúp test
   adapter mà không cần một server Qdrant thật?
2. `RagService` import những gì? Nó có biết `qdrant_client`/`fastembed` tồn tại không? Tại sao
   đó là biểu hiện của "đảo chiều source-code dependency"?
3. Nếu thêm một `PineconeVectorStore`, bạn phải sửa `RagService` không? Bất biến health-gate có
   bị ảnh hưởng không?
