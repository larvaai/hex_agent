# Case 03 — RAG `build_service` (Simple Factory) → Registry Factory

> Ranh giới dạy học: phân biệt **Simple Factory** (if-elif chọn implementation) với **Factory Method** GoF, và biết KHI NÀO cần nâng cấp.

---

## 1. Bối cảnh trong hex_agent

Feature RAG cần một `RagService` để health-check / ingest / search trên một **vector store**. Có hai backend: `memory` (offline, không cần docker — chạy được ngay) và `qdrant` (production, cần network + thư viện nặng). Backend nào dùng do `config['rag']['backend']` quyết định.

`build_service` đọc config, rồi `if-elif` chọn cặp (vector store + embedder) tương ứng và bọc vào cùng một `RagService`. Đây **không phải** Factory Method GoF — nó là **Simple Factory**: một hàm với if-elif. Bài học gốc gọi chính kiểu if-elif chọn class theo tham số là **anti-pattern** khi số nhánh phình to.

Tuy vậy ở đây nó **được thiết kế tốt** cho mục đích "vài backend cắm-rút": dùng **import lười** (chỉ kéo Qdrant/FastEmbed vào khi `backend == "qdrant"`), giữ cài đặt base nhẹ.

- File: `rag/feature.py:27-42` — `build_service(config) -> RagService`.
- File: `rag/feature.py:36-37` — import lười `QdrantVectorStore`, `FastEmbedEmbedder`.
- File: `rag/stores.py:24` — `InMemoryVectorStore` (concrete product); `rag/stores_qdrant.py:32` — `QdrantVectorStore`.
- Test: `tests/test_rag.py:146-150` — `build_service({"backend": "weaviate"})` ⇒ `ValueError`.

---

## 2. Trích đoạn code thật

```python
# rag/feature.py:27-42
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

```python
# tests/test_rag.py:146-150 — factory phải từ chối backend lạ
def test_build_service_rejects_unknown_backend():
    from rag.feature import build_service
    with pytest.raises(ValueError, match="backend"):
        build_service({"backend": "weaviate"})
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò | Thành phần trong hex_agent |
|---------|----------------------------|
| **Creator (Simple Factory)** | hàm `build_service` (`rag/feature.py:27`) |
| **Product interface** | `RagService` (trả về như nhau bất kể backend) |
| **Concrete products** | `InMemoryVectorStore` (`rag/stores.py:24`), `QdrantVectorStore` (`rag/stores_qdrant.py:32`) |
| **Context selector** | khoá `config['backend']` |
| **Tối ưu thật** | import lười (`rag/feature.py:36-37`) giữ base nhẹ |
| **Bảo vệ** | nhánh `else: raise ValueError` (test `test_rag.py:146`) |

---

## 4. Bản rút gọn chạy được

File: [`rag_service_factory.py`](./rag_service_factory.py) — chạy `python3 rag_service_factory.py`.

Nó mô phỏng:
- **(A)** `build_service` Simple Factory: cùng `RagService` cho mọi backend, default `memory`, import lười (mô phỏng bằng builder gọi trễ), `ValueError` cho backend lạ — khớp `test_rag.py:146-150`.
- **(B)** Nâng cấp `build_service_registry`: mỗi backend tự `register_backend(name, builder)`; hàm dựng chung **không còn if-elif**, thêm backend = đăng ký thêm 1 builder (Open-Closed). Demo thêm `weaviate` mà không sửa hàm chung.

Đã lược bỏ: embedding thật, Qdrant/network (fake hoá hoàn toàn bằng list trong RAM). Giữ nguyên: cùng interface `RagService`, config quyết định concrete product, xử lý lỗi backend lạ.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Simple Factory là đủ** khi: số backend ít và ổn định, khởi tạo đơn giản. Đừng nâng cấp sớm.
- **Hãy nâng lên Registry/Factory Method** khi: (1) backend được thêm thường xuyên, (2) logic khởi tạo từng backend phình to, (3) muốn cho phép plugin bên ngoài tự đăng ký backend.
- **Cái giá của Registry**: thêm gián tiếp + state toàn cục (`_BACKENDS`); thứ tự import/đăng ký trở nên quan trọng.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `build_service` là **Simple Factory** chứ không phải **Factory Method** GoF? Khác biệt cốt lõi nằm ở đâu?
2. Import lười (`from rag.stores_qdrant import ...` bên trong nhánh `qdrant`) giải quyết vấn đề thực tế gì?
3. Khi nào việc thêm if-elif vào `build_service` trở thành "mùi" cần refactor sang registry? Nêu ít nhất hai dấu hiệu.
