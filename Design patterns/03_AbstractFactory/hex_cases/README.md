# Abstract Factory trong hex_agent — Hex Cases

> Tài liệu dạy học: soi pattern **Abstract Factory (Creational)** *như nó thực sự xuất hiện*
> trong codebase `hex_agent`, rồi distill thành các bản chạy được bằng stdlib Python.
> Bổ trợ cho bài lý thuyết `../03_AbstractFactory.md` (analogy hệ thần kinh — "brain region
> ecosystem"); ở đây ta thay analogy bằng **code thật của dự án**.

---

## Pattern xuất hiện ở đâu?

Abstract Factory sống trong **feature RAG** (Retrieval-Augmented Generation, Epic E08). Hàm
`build_service(config)` (`rag/feature.py:27-42`) tạo nguyên một **họ** product liên quan dựa theo
backend cấu hình, đảm bảo embedder và vector store **luôn cùng họ**:

| Họ (family) | Embedder | Vector Store | Dùng khi |
|---|---|---|---|
| **memory** (mặc định) | `FakeEmbedder` (offline, `dim=64`) | `InMemoryVectorStore` (RAM) | test/dev, không docker |
| **qdrant** (production) | `FastEmbedEmbedder` (model thật) | `QdrantVectorStore` (server) | chạy thật, có Qdrant |

Pattern này ngăn đúng "bug heterotopia" mà bài học gốc cảnh báo: một `FakeEmbedder` (64 chiều)
**không bao giờ** vô tình ghép với một `QdrantVectorStore` đang chờ vector của model 384 chiều.
Mỗi họ được "đồng tiến hóa" để khớp số chiều, giống neuron + glia + ECM của một vùng não.

### Các vai trò pattern ↔ code

- **AbstractFactory** = `build_service(config)` — `rag/feature.py:27-42`, quyết định họ nào.
- **ConcreteFactory (memory)** = nhánh `backend == "memory"` — `rag/feature.py:31-34`.
- **ConcreteFactory (qdrant)** = nhánh `backend == "qdrant"` (lazy import) — `rag/feature.py:35-41`.
- **AbstractProduct #1** = `EmbedderPort` Protocol — `rag/ports.py:24-28`.
- **AbstractProduct #2** = `VectorStorePort` Protocol — `rag/ports.py:31-36`.
- **ConcreteProduct #1a/#1b** = `FakeEmbedder` / `FastEmbedEmbedder` — `rag/embedders.py:33-46, 49-60`.
- **ConcreteProduct #2a/#2b** = `InMemoryVectorStore` / `QdrantVectorStore` — `rag/stores.py:24-56`, `rag/stores_qdrant.py:32-148`.
- **Client** = `RagService` (đa hình trên Port) — `rag/service.py:15-113`.

Tại sao đây là **textbook Abstract Factory**: (1) có abstract port/interface rõ ràng; (2) nhiều
product type (embedder + store) phải đi cùng nhau; (3) cấu hình chọn **cả họ** trong một chỗ;
(4) lazy import để không phụ thuộc cứng vào thành phần optional (Qdrant); (5) client đa hình trên
abstraction, không phụ thuộc concrete.

---

## Các case con

| # | Case | Distill từ | Chạy |
|---|---|---|---|
| 01 | [RAG Feature Backend Factory (Memory vs Qdrant)](./01_rag_build_service_factory/) | `rag/feature.py:27-42`, `rag/ports.py:24-36`, `rag/embedders.py:33-60`, `rag/stores.py:24-56`, `rag/service.py:15-19` | `python3 01_rag_build_service_factory/rag_build_service_factory.py` |

Mỗi thư mục case có `README.md` (bài học 6 mục) + một file `.py` self-contained chạy được, in
narration tiếng Việt từng bước và có `assert` chứng minh bất biến của pattern.

> **Phạm vi (cố ý chỉ 1 case):** `build_service` là occurrence Abstract Factory **thuần** khả dụng
> duy nhất trong codebase, nên việc chỉ có 1 case là hợp lý chứ không phải thiếu sót. Toàn bộ các
> vị trí liên quan (lõi pattern, khai báo abstraction, test, composition root) đã được vét cạn đầy
> đủ trong [`CATALOG.md`](./CATALOG.md) (mục A–D).

---

## Liệt kê đầy đủ mọi occurrence

Xem [`CATALOG.md`](./CATALOG.md) — bảng vét cạn mọi nơi pattern (hoặc hạ tầng quanh nó) lộ diện,
kèm `path:line`, mô tả, và độ rõ ràng.
