# Ca 01 — RAG: Tách `EmbedderPort` khỏi `VectorStorePort`

> ISP gốc nhất trong hex_agent: hai *role* (tạo embedding / lưu-tìm vector) được tách thành **hai Protocol hẹp** với lifecycle độc lập. Client `RagService` cầm cả hai nhưng phụ thuộc từng interface hẹp riêng.

---

## 1. Bối cảnh trong hex_agent

Feature RAG (Epic E08) phải làm hai việc bản chất khác nhau:

1. **Embedding**: biến văn bản thành vector. Production dùng `fastembed` (tải model, có thể chậm, cần GPU/CPU); test dùng một hàm hash offline.
2. **Vector store**: lưu chunk + tìm theo cosine. Production là **Qdrant** (server qua mạng, docker); test dùng một list trong RAM.

Nếu gộp cả hai vào một interface "RAG tổng", thì: test embedder buộc phải dựng Qdrant, test store buộc phải tải model, và thay backend này kéo theo backend kia. hex_agent tránh điều đó bằng **hai port hẹp** ở `rag/ports.py:24-36`, và `RagService` (`rag/service.py:15-19`) nhận cả hai như hai tham số riêng. `build_service` (`rag/feature.py:27-42`) chọn adapter cho từng port **độc lập** theo cấu hình `backend`.

Đã mở kiểm chứng các file:
- `rag/ports.py:24-28` (`EmbedderPort`), `rag/ports.py:31-36` (`VectorStorePort`)
- `rag/service.py:15-19` (`RagService.__init__`)
- `rag/embedders.py:33-46` (`FakeEmbedder`), `rag/stores.py:24-56` (`InMemoryVectorStore`)
- `rag/stores_qdrant.py:32-148` (`QdrantVectorStore`), `rag/feature.py:27-42` (`build_service`)

## 2. Trích đoạn code thật

Hai port hẹp, hoàn toàn độc lập — `EmbedderPort` ở `rag/ports.py:24-28`, `VectorStorePort` ở `rag/ports.py:31-36`:

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

Client cầm cả hai port hẹp — `rag/service.py:15-19`:

```python
class RagService:
    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._cfg = config
```

Chọn adapter từng port độc lập theo backend — `rag/feature.py:27-42` (rút gọn):

```python
def build_service(config):
    ...
    if backend == "memory":
        store = InMemoryVectorStore(collection=cfg.collection)
        embedder = FakeEmbedder()
        return RagService(store, embedder, cfg)
    if backend == "qdrant":
        from rag.embedders import FastEmbedEmbedder
        from rag.stores_qdrant import QdrantVectorStore
        store = QdrantVectorStore(cfg)
        embedder = FastEmbedEmbedder(cfg.model)
        return RagService(store, embedder, cfg)
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò ISP | Trong file `.py` của ca này | Trong hex_agent thật |
|-------------|------------------------------|----------------------|
| Port hẹp (role A: embedding) | `EmbedderPort` | `rag/ports.py:24-28` |
| Port hẹp (role B: vector store) | `VectorStorePort` | `rag/ports.py:31-36` |
| Adapter của port A (offline) | `FakeEmbedder` | `rag/embedders.py:33-46` |
| Adapter của port A (khác) | `ConstantEmbedder` | `FastEmbedEmbedder` `rag/embedders.py:49-60` |
| Adapter của port B (offline) | `InMemoryVectorStore` | `rag/stores.py:24-56` |
| Adapter của port B (khác) | `RecordingVectorStore` | `QdrantVectorStore` `rag/stores_qdrant.py:32-148` |
| Client phụ thuộc 2 port hẹp | `RagService` | `rag/service.py:15-19` |
| Lắp adapter độc lập | `build_service(...)` | `rag/feature.py:27-42` |

## 4. Bản rút gọn chạy được

File: [`rag_embedder_vectorstore_segregation.py`](rag_embedder_vectorstore_segregation.py) — chạy `python3 rag_embedder_vectorstore_segregation.py`.

Nó **mô phỏng**: hai Protocol hẹp `@runtime_checkable`; hai họ adapter (mỗi họ 2 adapter); `RagService` cầm cả hai port; `build_service` lắp adapter; 6 bước demo gồm test cô lập từng port, swap-in adapter mà không sửa client, gate dependency-failure; và đối chứng "god port" (`FatRagPort`) gây `raise NotImplementedError`.

Nó **lược bỏ**: Qdrant client + mạng thật (thay bằng `RecordingVectorStore` wrap in-memory), `fastembed` model thật (thay bằng `FakeEmbedder`/`ConstantEmbedder` hash offline), sandbox jail + chunking file (`ingest` nhận thẳng list text), và event publish. Logic cosine + hash bag-of-words giữ trung thực với bản gốc; `score_threshold` hạ từ 0.8 xuống 0.3 vì câu tiếng Việt ngắn cho cosine thấp hơn — đã chú thích trong code.

Assert chứng minh: `FakeEmbedder` là `EmbedderPort` nhưng **không** là `VectorStorePort` (và ngược lại); test embedder/store cô lập; swap-in adapter giữ nguyên hành vi `RagService`; gate unhealthy chặn trước khi embed.

## 5. Cái giá / khi nào KHÔNG nên tách

- **Số file/interface tăng**: 2 port + N adapter thay vì 1 lớp. Chỉ đáng khi hai role thật sự có lifecycle khác (ở đây: model vs server) — đúng heuristic Mục 1.6 ("có client nào dùng 70-80% cả hai role cùng cách không?").
- **Nếu embedding và store luôn đi cùng một backend duy nhất, không bao giờ test riêng**, thì tách là over-ISP: thêm navigation overhead vô ích.
- **Trùng method tên giữa port**: nếu sau này cả hai port cùng có `health()` với *khác* contract thì đó là vấn đề (xem checklist "Duplicate method" của bài gốc). Ở đây chỉ `VectorStorePort` có `health()`, sạch.

## 6. Câu hỏi tự kiểm tra

1. Vì sao `RagService` nhận `embedder` và `store` là **hai tham số riêng** thay vì một đối tượng "rag backend" duy nhất? Lợi ích cụ thể khi viết test là gì?
2. Khi thêm `QdrantVectorStore` (production), những file nào KHÔNG phải sửa? Vì sao `EmbedderPort` hoàn toàn không bị ảnh hưởng?
3. Đối chứng `FatEmbedderOnly` phải `raise NotImplementedError` ở `search/upsert/...`. Bài học gốc gọi smell này là gì, và ISP xoá nó bằng cách nào?
