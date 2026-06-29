# Case 01 — Hai Vector Store khác hẳn nhau sau cùng một `VectorStorePort`

> Adapter = **dịch interface, không đổi logic**. Đây là ví dụ Adapter rõ nhất trong
> hex_agent: hai backend hoàn toàn khác nhau (list trong RAM vs server Qdrant qua mạng)
> phục vụ chung một protocol, tới mức code của `RagService` y hệt dù dùng cái nào.

---

## 1. Bối cảnh trong hex_agent

RAG (retrieval-augmented generation) cần một kho vector. hex_agent muốn:
- chạy offline / test mà không cần Docker hay server Qdrant;
- vẫn dùng Qdrant thật khi triển khai.

Giải pháp: domain định nghĩa **một protocol** `VectorStorePort`, và viết **hai adapter**
cài đặt nó. `RagService` (logic) chỉ phụ thuộc protocol, nhận store qua dependency
injection ở `__init__`.

File:line thật (đã mở kiểm chứng):
- `rag/ports.py:31-36` — `VectorStorePort` (Protocol): `health()`, `delete_by_source()`,
  `upsert()`, `search()`. DTO `Chunk` ở `rag/ports.py:8-13`, `Hit` ở `rag/ports.py:16-21`.
- `rag/stores.py:24-57` — `InMemoryVectorStore`: bọc `self._chunks: list[Chunk]`, cosine
  search trong RAM. Có `set_healthy()` để bật/tắt đường lỗi-phụ-thuộc cho test.
- `rag/stores_qdrant.py:32-148` — `QdrantVectorStore`: bọc `qdrant_client.QdrantClient`
  (`self._client`), lazy tạo collection, dịch `Chunk → models.PointStruct` và
  `Hit ← query_points`. Đặc biệt `health()` (dòng 83-90) **không bao giờ raise**.
- `rag/service.py:15-19` — `RagService.__init__(self, store: VectorStorePort, ...)`: client
  nhận port qua DI. `service.py:30-39` health-gate; `service.py:78-113` `search()` chỉ gọi
  `self._store.health()` / `self._store.search()`.

---

## 2. Trích đoạn code thật

Target interface — `rag/ports.py:31-36`:

```python
@runtime_checkable
class VectorStorePort(Protocol):
    def health(self) -> dict: ...
    def delete_by_source(self, source: str) -> int: ...
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...
```

Adapter Qdrant dịch lỗi mạng thành dữ liệu thay vì exception — `rag/stores_qdrant.py:83-90`:

```python
def health(self) -> dict:
    try:
        count = 0
        if self._client.collection_exists(self.collection):
            count = self._client.count(self.collection, exact=True).count
        return {"ok": True, "collection": self.collection, "count": count}
    except Exception as exc:  # unreachable server -> dependency failure, not a crash
        return {"ok": False, "collection": self.collection, "count": 0, "error": str(exc)}
```

Client chỉ thấy port — `rag/service.py:15-19` + `service.py:97-98`:

```python
class RagService:
    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig) -> None:
        self._store = store          # ← chỉ biết VectorStorePort
        ...
        vector = self._embedder.embed([query])[0]
        hits = self._store.search(vector, k, threshold)   # không biết Qdrant hay list
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Adapter (GoF)        | Thành phần trong hex_agent                                            |
|------------------------------|----------------------------------------------------------------------|
| **Target** (interface client kỳ vọng) | `VectorStorePort` — `rag/ports.py:31-36`                    |
| **DTO** đi qua biên          | `Chunk`, `Hit` — `rag/ports.py:8-21`                                 |
| **Concrete Adapter #1**      | `InMemoryVectorStore` — `rag/stores.py:24-57` (composition: `_chunks` list) |
| **Concrete Adapter #2**      | `QdrantVectorStore` — `rag/stores_qdrant.py:32-148` (composition: `_client`) |
| **Adaptee #1**               | `list` Python thuần                                                   |
| **Adaptee #2**               | `qdrant_client.QdrantClient` (third-party, qua mạng)                  |
| **Client**                   | `RagService` — `rag/service.py:15-113`                               |

---

## 4. Bản rút gọn chạy được

File: [`rag_vector_store_adapter.py`](./rag_vector_store_adapter.py) — `python3 rag_vector_store_adapter.py`.

Mô phỏng:
- `VectorStorePort`, `Chunk`, `Hit`, hàm `_cosine` — giữ nguyên vai trò từ ports/stores thật.
- `InMemoryVectorStore` và `QdrantVectorStore` — hai Object Adapter, đúng cấu trúc gốc.
- `RagService` (client) — health-gate + search, chỉ gọi qua port.
- Demo: ingest cùng dữ liệu vào cả hai adapter, search cùng query, **assert** hai bên trả
  cùng thứ tự + cùng score (chứng minh substitutability). Sau đó "giết" server Qdrant
  (`alive=False`) để thấy `health()` trả `{"ok": False}` và client vào health-gate, không crash.
- Đối chứng `RagServiceNoAdapter`: client tự `if/else` theo backend + tự dịch định dạng.

Lược bỏ (vì là hạ tầng nặng / ngoài trọng tâm pattern):
- `qdrant_client` thật + server qua mạng → thay bằng `_FakeQdrantClient` (dict trong RAM,
  cờ `alive` mô phỏng server chết). Đây là **adaptee giả**, không phải adapter.
- Embedder thật, sandbox jail, `delete_by_source`, lazy point-id `uuid5`, chunking file.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí gián tiếp**: thêm một lớp + một protocol. Với dự án chỉ-một-backend-mãi-mãi và
  không cần test offline, port + adapter là over-engineering.
- **Port rò rỉ ngữ nghĩa**: nếu một adaptee có khả năng mà adaptee kia không có (vd Qdrant
  hỗ trợ filter phức tạp), nhét hết vào port sẽ làm in-memory phải giả lập — port phình to,
  mất ý nghĩa "interface segregation".
- **Adapter làm quá nhiều**: nếu adapter bắt đầu chứa logic nghiệp vụ (xếp hạng lại, gộp
  kết quả nhiều nguồn), nó không còn là Adapter mà ngả sang Facade/Decorator.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `QdrantVectorStore.health()` trả `{"ok": False}` thay vì để exception bay lên?
   Điều này giúp `RagService._require_healthy()` ở `service.py:30-39` được gì?
2. Nếu thêm backend thứ ba (Pinecone), bạn phải sửa những file nào? So sánh với
   `RagServiceNoAdapter` trong file demo.
3. `RagService` có bao giờ biết nó đang dùng Qdrant hay in-memory không? Dòng nào trong
   `rag/service.py` chứng minh điều đó?
