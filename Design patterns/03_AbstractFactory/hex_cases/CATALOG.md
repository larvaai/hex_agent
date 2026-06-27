# CATALOG — Mọi occurrence của Abstract Factory trong hex_agent

> Bảng vét cạn các vị trí pattern **Abstract Factory** xuất hiện hoặc liên quan trực tiếp.
> Mọi `path:line` đã được mở kiểm chứng so với mã nguồn thực tại
> `/Users/uspro/Desktop/namnson/hex_agent/`.
> Cột "độ rõ": **cao** = vai trò pattern hiển nhiên; **trung bình** = thành phần của họ/đối chứng;
> **thấp** = chỉ là composition root / dây nối, không phải pattern thuần.

## A. Lõi pattern (flagship — xem case 01)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `rag/feature.py:27-42` | **AbstractFactory**: `build_service(config)` đọc `backend` (dòng 30) rồi tạo nguyên họ — họ Memory (31-34: `FakeEmbedder`+`InMemoryVectorStore`) hoặc họ Qdrant (35-41: `FastEmbedEmbedder`+`QdrantVectorStore` qua lazy import); `backend` lạ → `raise` (42). | cao |
| `rag/ports.py:24-28` | **AbstractProduct #1** `EmbedderPort` (Protocol `@runtime_checkable`): hợp đồng `dim` + `embed(texts)`. | cao |
| `rag/ports.py:31-36` | **AbstractProduct #2** `VectorStorePort` (Protocol): `health`/`delete_by_source`/`upsert`/`search`. | cao |
| `rag/embedders.py:33-46` | **ConcreteProduct #1a** `FakeEmbedder` — offline, deterministic (hash bag-of-words, `dim=64`). | cao |
| `rag/embedders.py:49-60` | **ConcreteProduct #1b** `FastEmbedEmbedder` — production, model-backed, **lazy import** `fastembed` (dòng 53). | cao |
| `rag/stores.py:24-56` | **ConcreteProduct #2a** `InMemoryVectorStore` — RAM, cosine tính tay; `health()` chuyển được để test gate. | cao |
| `rag/stores_qdrant.py:1-16` | Header giải thích: adapter này **import lazily bởi `build_service`** chỉ khi `backend: qdrant`, để base install không cần `qdrant-client`. | trung bình |
| `rag/stores_qdrant.py:32-49` | **ConcreteProduct #2b** `QdrantVectorStore.__init__` — cho inject `client` (test) hoặc tự dựng `QdrantClient` (lazy import dòng 43). | trung bình |
| `rag/stores_qdrant.py:65-68` | Tạo collection với `size=dim` của embedder — chỗ "khóa họ" về số chiều (bất biến chống trộn họ). | trung bình |
| `rag/service.py:15-19` | **Client** `RagService.__init__(store: VectorStorePort, embedder: EmbedderPort, ...)` — nhận hai product đa hình. | cao |
| `rag/service.py:63, 72, 98` | Client chỉ gọi method của Port (`embed`, `upsert`, `search`), không chạm class cụ thể. | cao |

## B. Khai báo abstraction / cấu hình họ

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `rag/__init__.py:1-12` | Public API re-export ports + value types (`Chunk`, `Hit`, `EmbedderPort`, `VectorStorePort`, `RagConfig`, `RagService`) — tách "cái client phụ thuộc" (abstraction) khỏi "cái factory tạo" (concrete). | trung bình |
| `config/features.yaml:15-24` | Cấu hình chọn họ: `backend: memory` (dòng 19) là mặc định; comment 15-17 giải thích đổi sang `qdrant` cho production; 20-23 là config dùng chung cho cả hai họ. | cao |

## C. Test chứng minh hai họ hợp lệ & hoán đổi được

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `tests/test_rag.py:21-24` | Helper `make_service()` dựng `RagService` với họ Memory (`FakeEmbedder`+`InMemoryVectorStore`) cho test. | cao |
| `tests/test_rag.py:125-128` | Hằng `RAG_CFG` minh họa cấu hình backend qua config (`{"rag": {"backend": "memory"}}`). | cao |
| `tests_audit/test_rag_edges_rigor.py:1-11` | Header mô tả bộ test phủ cả hai họ offline: stub `fastembed` cho `FastEmbedEmbedder`, stub `qdrant_client` cho `QdrantClient`. | trung bình |
| `tests_audit/test_rag_edges_rigor.py:61-72` | Test `FastEmbedEmbedder` lazy import + dò `dim` một lần (pin embedders.py:53-57). | cao |
| `tests_audit/test_rag_edges_rigor.py:95-99` | Khẳng định `FastEmbedEmbedder` thỏa `EmbedderPort` (có `.dim` + `.embed`) — bằng chứng tính hoán đổi qua abstraction. | cao |
| `tests_audit/test_rag_edges_rigor.py:296-300` | Helper `_service()` dựng họ Memory để test các nhánh service. | trung bình |
| `tests_audit/test_rag_qdrant_adapter_contract.py:1-16` | Contract test cho `QdrantVectorStore`; import cả `FakeEmbedder`+`InMemoryVectorStore` để đối chiếu — chứng minh các thành viên họ hoán đổi được ở mức Port. | trung bình |
| `tests/test_rag_qdrant.py` | Test riêng cho họ Qdrant (skip nếu không có Qdrant server) — **bù lại rủi ro lazy import**: nhánh `qdrant` chỉ import lúc runtime, nên cần test này để lỗi cấu hình/thiếu dep không tới muộn. Được nhắc tới ở `rag/feature.py:35` và `rag/stores_qdrant.py:5`. | trung bình |

## D. Composition root (dây nối, không phải pattern thuần)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `rag/feature.py:109-110` | `install(kernel)` gọi `build_service(kernel.config['rag'])` — nơi Abstract Factory được kích hoạt ở composition root. | trung bình |
| `core/bootstrap.py:56-66` | `build_kernel()` gọi `install_configured_features()` để cài feature RAG; factory chạy bên trong `rag.feature.install()`. | thấp |
| `features/loader.py:10-26` | `install_configured_features()` nạp động các feature bật trong config, mỗi feature có `install()`. Không phải Abstract Factory, nhưng là phần composition root nối factory vào kernel. | thấp |
