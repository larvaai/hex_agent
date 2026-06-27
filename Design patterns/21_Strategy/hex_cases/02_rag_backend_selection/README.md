# Case 02 — RAG Service: Backend Strategy Selection (Memory vs Qdrant)

> Strategy (Behavioral) ở dạng **chuẩn sách giáo khoa nhất** trong hex_agent: cùng một
> Context (`RagService`), hoán đổi *thuật toán* embed và *backend* lưu/tìm vector qua
> Protocol, chọn bằng config — Context không hề biết backend nào đang chạy.

---

## 1. Bối cảnh trong hex_agent

Feature RAG cần chạy được ở hai chế độ rất khác nhau:
- **offline/test**: nhanh, không cần docker, không tải model — để bộ acceptance suite chạy
  được trên CI mà không có hạ tầng.
- **production**: dùng model embedding thật (`fastembed`) và vector DB thật (Qdrant qua HTTP),
  có persistence và scale.

Nếu nhồi cả hai vào `RagService` bằng if/elif trong từng method (`ingest`, `search`, `health`,
`delete`) thì logic RAG (health-gate, chunking, sandbox jail) bị trộn lẫn với chi tiết backend,
không test tách rời được, thêm backend thứ ba phải sửa mọi method.

Giải pháp Strategy: định nghĩa hai Protocol **`EmbedderPort`** và **`VectorStorePort`**
(`rag/ports.py:24-36`). `RagService` (`rag/service.py:15-39`) là **Context** chỉ giữ
`self._store` và `self._embedder` rồi *delegate*. Factory `build_service()`
(`rag/feature.py:27-42`) **chọn và inject** ConcreteStrategy theo `config['backend']`:

```python
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
```

Hai chi tiết "hexagonal" đáng chú ý: (1) các adapter production được **lazy-import** ngay trong
nhánh — base install không cần `fastembed`/`qdrant-client`; (2) các strategy thỏa Protocol
**theo cấu trúc** (duck typing, `@runtime_checkable`), không cần kế thừa.

---

## 2. Trích đoạn code thật

`rag/ports.py:24-36` — hai Strategy interface:

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

`rag/service.py:15-19` — Context giữ strategy và delegate (không biết backend):

```python
class RagService:
    def __init__(self, store: VectorStorePort, embedder: EmbedderPort, config: RagConfig) -> None:
        self._store = store
        self._embedder = embedder
        self._cfg = config
```

`rag/embedders.py:33-46` — một ConcreteStrategy embed (offline):

```python
class FakeEmbedder:
    """Deterministic offline embedder (no network, no model)."""
    def __init__(self, dim: int = 64) -> None:
        self.dim = dim
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Strategy | Thành phần trong hex_agent | File:line |
|---|---|---|
| **Strategy interface (embed)** | `EmbedderPort` Protocol | `rag/ports.py:24-28` |
| **Strategy interface (store)** | `VectorStorePort` Protocol | `rag/ports.py:31-36` |
| **ConcreteStrategy (embed, offline)** | `FakeEmbedder` | `rag/embedders.py:33-46` |
| **ConcreteStrategy (embed, prod)** | `FastEmbedEmbedder` (lazy import) | `rag/embedders.py:49-60` |
| **ConcreteStrategy (store, offline)** | `InMemoryVectorStore` | `rag/stores.py:24-56` |
| **ConcreteStrategy (store, prod)** | `QdrantVectorStore` (lazy import) | `rag/stores_qdrant.py:32-49` |
| **Context** | `RagService` (delegate embed/store) | `rag/service.py:15-39` |
| **Factory chọn + inject strategy** | `build_service(config)` | `rag/feature.py:27-42` |

---

## 4. Bản rút gọn chạy được

File: [`rag_backend_selection.py`](./rag_backend_selection.py) — `python3 rag_backend_selection.py` (exit 0).

**Mô phỏng trung thực:**
- `EmbedderPort`/`VectorStorePort` là `@runtime_checkable` Protocol giống bản thật.
- `FakeEmbedder` giữ **nguyên thuật toán** hash bag-of-words + cosine của `rag/embedders.py`
  và `rag/stores.py` — text giống nhau cosine 1.0.
- `RagService` (Context) chỉ gọi `self._embedder.embed(...)` và `self._store.search(...)`,
  health-gate trước mọi thao tác như `rag/service.py`.
- `build_service(config)` chọn strategy theo `config['backend']` đúng cấu trúc factory thật.
- Demo chứng minh: cùng API trả **cùng thứ tự hit** bất kể backend (bất biến ngữ nghĩa);
  backend "qdrant" có latency cao hơn (trade-off); "qdrant" persist qua instance mới còn
  "memory" thì mất; cả hai strategy thỏa Protocol mà **không kế thừa**.

**Lược bỏ (thay bằng fake stdlib):** `FastEmbedEmbedder` thật (tải model `fastembed`) →
`HeavyEmbedder` chỉ mô phỏng latency khởi tạo rồi tái dùng thuật toán fake; `QdrantVectorStore`
thật (HTTP tới Qdrant server, `uuid5` id, tạo collection lazily) → `PersistentLikeStore` mô phỏng
latency-mỗi-query + persistence bằng một list "đĩa giả" trong RAM, **không network**. Chunking
và sandbox jail của `rag/service.py` được lược thành `ingest(list[(source,text)])`.

**Đối chứng:** `HardcodedRagService` nhồi `if backend == ...` vào method `search` — latency lặp
lại ở mọi method, thêm `pgvector` phải sửa toàn bộ.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Protocol phải "truth-telling".** Nếu `QdrantVectorStore` cần một tham số (vd. `Connection`)
  mà `InMemoryVectorStore` không cần, interface nói dối → vi phạm Liskov. hex_agent tránh được
  vì cả hai chỉ phơi `health/upsert/search/delete_by_source`.
- **Lazy import là con dao hai lưỡi.** Giữ base install nhẹ, nhưng lỗi thiếu `qdrant-client`
  chỉ lộ ra lúc runtime khi chọn `backend: qdrant`, không phải lúc import.
- **Hai strategy "tương đương" nhưng không thật sự interchangeable ở mọi call site** thì đừng
  ép chung interface. Ở đây chúng thật sự thay thế nhau được nên Strategy hợp lý.
- **Khi chỉ có duy nhất một backend mãi mãi** → một class cụ thể đơn giản hơn; đừng dựng Port +
  factory để đầu cơ.

---

## 6. Câu hỏi tự kiểm tra

1. `RagService.search()` gọi những method nào trên strategy? Vì sao nó không cần biết backend
   là memory hay qdrant — điều đó liên quan gì tới bất biến "cùng thứ tự hit"?
2. Tại sao `FastEmbedEmbedder`/`QdrantVectorStore` được import **bên trong** nhánh
   `if backend == "qdrant"` thay vì ở đầu file? Lợi và hại của lựa chọn này?
3. `@runtime_checkable` Protocol cho phép `isinstance(store, VectorStorePort)` trả True mà không
   cần kế thừa. Nó kiểm gì và KHÔNG kiểm gì (gợi ý: chữ ký method)?
