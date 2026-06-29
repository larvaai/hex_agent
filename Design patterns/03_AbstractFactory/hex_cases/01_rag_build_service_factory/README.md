# Case 01 — RAG Feature Backend Factory (Memory vs Qdrant)

> **Abstract Factory thật trong hex_agent**: `build_service(config)` tạo nguyên một **họ**
> object khớp nhau (embedder + vector store) dựa theo backend cấu hình, để client không bao giờ
> ghép nhầm `FakeEmbedder` của họ này với `QdrantVectorStore` của họ kia.

---

## 1. Bối cảnh trong hex_agent

Feature RAG (Retrieval-Augmented Generation, Epic E08) cần chạy được ở **hai chế độ song song**:

- **`memory`** — offline, không docker, không tải model: dùng cho test/dev và làm mặc định để
  kernel "tự chứa". Cặp đôi: `FakeEmbedder` (hash bag-of-words, `dim=64`) + `InMemoryVectorStore`
  (dict trong RAM, cosine tính tay).
- **`qdrant`** — production: cần `qdrant-client` + `fastembed` + một Qdrant server qua docker.
  Cặp đôi: `FastEmbedEmbedder` (model thật, `dim` dò từ model) + `QdrantVectorStore`.

Hai cặp này **phải đi cùng họ**. Vector của `FakeEmbedder` có 64 chiều; vector của model
production có số chiều khác (vd 384 với `bge-small`). Một Qdrant collection được tạo với một
`size` cố định theo width của embedder (xem `rag/stores_qdrant.py:65-68`). Nếu ai đó vô tình ghép
embedder của họ này với store của họ kia, hệ thống **compile được, chỉ runtime mới hỏng** — đúng
kiểu "heterotopia" mà bài học gốc mô tả (neuron lạc chỗ giữa môi trường sai họ).

Toàn bộ quyết định "dùng họ nào" được gói gọn trong **một hàm duy nhất**:
`build_service(config)` tại `rag/feature.py:27-42`. Đó là Abstract Factory.

File đã mở kiểm chứng:
- `rag/feature.py:27-42` — `build_service`.
- `rag/ports.py:24-36` — hai Protocol product.
- `rag/embedders.py:33-46` và `49-60` — hai concrete embedder.
- `rag/stores.py:24-56` — `InMemoryVectorStore`.
- `rag/stores_qdrant.py:32-49, 65-68` — `QdrantVectorStore` + tạo collection theo `dim`.
- `rag/service.py:15-19` — client `RagService` nhận hai Port.

---

## 2. Trích đoạn code thật

`build_service` — Abstract Factory chọn nguyên họ (`rag/feature.py:27-42`):

```python
def build_service(config: dict[str, Any] | None) -> RagService:
    config = config or {}
    cfg = RagConfig.from_dict(config)
    backend = (config.get("backend") or "memory").lower()
    if backend == "memory":
        store = InMemoryVectorStore(collection=cfg.collection)
        embedder = FakeEmbedder()
        return RagService(store, embedder, cfg)
    if backend == "qdrant":  # pragma: no cover — needs Qdrant
        from rag.embedders import FastEmbedEmbedder
        from rag.stores_qdrant import QdrantVectorStore

        store = QdrantVectorStore(cfg)
        embedder = FastEmbedEmbedder(cfg.model)
        return RagService(store, embedder, cfg)
    raise ValueError(f"Unknown rag backend: {backend!r}")
```

Hai abstract product là Protocol `@runtime_checkable` (`rag/ports.py:24-36`):

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

Client chỉ nhận Port, không biết class cụ thể (`rag/service.py:15-19`):

```python
class RagService:
    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._cfg = config
```

Qdrant collection được tạo với `size=dim` của embedder — đây là chỗ "khóa họ" về số chiều
(`rag/stores_qdrant.py:65-68`):

```python
self._client.create_collection(
    self.collection,
    vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
)
```

---

## 3. Bảng ánh xạ vai trò pattern ↔ code thật

| Vai trò Abstract Factory | Thành phần trong hex_agent | path:line |
|---|---|---|
| **AbstractFactory** (chọn họ) | hàm `build_service(config)` | `rag/feature.py:27-42` |
| **ConcreteFactory** họ Memory | nhánh `backend == "memory"` | `rag/feature.py:31-34` |
| **ConcreteFactory** họ Qdrant | nhánh `backend == "qdrant"` (lazy import) | `rag/feature.py:35-41` |
| **AbstractProduct #1** (embedder) | `EmbedderPort` Protocol | `rag/ports.py:24-28` |
| **AbstractProduct #2** (store) | `VectorStorePort` Protocol | `rag/ports.py:31-36` |
| **ConcreteProduct #1a** | `FakeEmbedder` | `rag/embedders.py:33-46` |
| **ConcreteProduct #1b** | `FastEmbedEmbedder` | `rag/embedders.py:49-60` |
| **ConcreteProduct #2a** | `InMemoryVectorStore` | `rag/stores.py:24-56` |
| **ConcreteProduct #2b** | `QdrantVectorStore` | `rag/stores_qdrant.py:32-148` |
| **Client** (đa hình trên Port) | `RagService` | `rag/service.py:15-113` |
| **Composition root** (gọi factory) | `install()` → `build_service(...)` | `rag/feature.py:109-110` |

---

## 4. Bản rút gọn chạy được

File: [`rag_build_service_factory.py`](./rag_build_service_factory.py) — chạy bằng
`python3 rag_build_service_factory.py`, chỉ dùng stdlib.

**Mô phỏng trung thực:**
- `build_service(config)` giữ nguyên cấu trúc gốc: đọc `backend`, rẽ nhánh thành nguyên một họ,
  `backend` lạ thì `raise ValueError` (đúng `rag/feature.py:42`).
- `EmbedderPort` / `VectorStorePort` là Protocol `@runtime_checkable` y như gốc.
- Họ Memory = `FakeEmbedder(dim=64)` + `InMemoryVectorStore` (cosine tính tay) — distill thật.
- `RagService` chỉ gọi method của Port, không chạm class cụ thể — đa hình như gốc.

**Lược bỏ / thay thế (vì là hạ tầng nặng):**
- Họ Qdrant thật (`fastembed` + `qdrant-client` + docker) được thay bằng họ **`prod`** giả lập
  trong RAM: `ProdEmbedder(dim=384)` + `ProdVectorStore(expected_dim=384)`. Điểm cốt lõi được giữ
  nguyên: **số chiều khác họ Memory** nên không thể trộn — đúng bất biến mà Qdrant collection
  khóa lại ở `rag/stores_qdrant.py:65-68`.
  - **Lưu ý thời điểm "khóa số chiều" (mô phỏng ≠ gốc):** trong code gốc, Qdrant collection được
    tạo **LAZY** ở lần `upsert` đầu tiên và lấy width **TỪ embedder** — `_ensure_collection(dim)`
    được gọi trong `upsert` (`rag/stores_qdrant.py:9-11` và `:52-68`, call site `:115`), nên width
    do embedder đầu tiên định nghĩa rồi mới khóa. Bản distill thì khóa **ngay từ `__init__`** vì
    `ProdVectorStore` nhận sẵn `expected_dim` cố định. Nói gọn: *gốc khóa khi tạo-collection-lần-đầu
    (lúc upsert), distill khóa ngay từ `__init__`*. Đừng hiểu nhầm rằng Qdrant kiểm tra số chiều
    ngay lúc khởi tạo store — gốc chỉ kiểm khi upsert lần đầu.
- Bỏ phần `lazy import` thật (chỉ ghi chú lại trong code), bỏ sandbox/chunking của `RagService`
  (không liên quan đến pattern), bỏ `delete_by_source` trong demo cho gọn.

**Đối chứng "không dùng pattern thì hỏng":** bước [4] tự tay dựng một `RagService` trộn
`FakeEmbedder(64)` (họ Memory) với `ProdVectorStore(expected_dim=384)` (họ Prod). Nó **nổ ngay**
khi upsert — chính là bug heterotopia. Nếu luôn đi qua `build_service`, client không có đường nào
ghép sai như vậy.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Khó thêm chiều product mới.** Hôm nay họ gồm 2 product (embedder + store). Nếu mai cần thêm
  product type thứ ba (vd `Reranker`), bạn phải sửa **mọi** nhánh trong `build_service` cùng lúc.
  Đây đúng là trade-off cốt lõi của Abstract Factory (dễ thêm *family*, khó thêm *product type*).
- **Thừa khi chỉ có 1 product hoặc 1 họ.** Nếu RAG chỉ có duy nhất backend memory, một Factory
  Method (lesson 02) hoặc thậm chí khởi tạo trực tiếp đã đủ; gói thành Abstract Factory là
  over-engineering. Ngưỡng hợp lý: ≥ 2 product đi cùng nhau **và** ≥ 2 họ song song.
- **Lazy import che lỗi cấu hình tới muộn.** Nhánh `qdrant` chỉ import khi được chọn, nên lỗi
  thiếu `qdrant-client` xuất hiện lúc runtime chứ không phải lúc import — phải có test riêng
  (`tests/test_rag_qdrant.py`) để bù lại.

---

## 6. Câu hỏi tự kiểm tra

1. Tại sao `build_service` đặt `import FastEmbedEmbedder`/`QdrantVectorStore` **bên trong** nhánh
   `if backend == "qdrant"` thay vì ở đầu file? Điều đó đánh đổi gì giữa "base install nhẹ" và
   "lỗi cấu hình hiện sớm"?
2. `RagService` được khai báo nhận `store: VectorStorePort, embedder: EmbedderPort`. Vì sao nhờ đó
   mà thêm một họ backend thứ ba (vd `pgvector`) **không cần sửa một dòng nào** trong `RagService`?
3. Trong bản distill, điều gì khiến việc trộn họ Memory với họ Prod **chắc chắn nổ** chứ không
   "im lặng trả kết quả sai"? Ánh xạ điều đó về dòng `rag/stores_qdrant.py:65-68` trong code thật.
