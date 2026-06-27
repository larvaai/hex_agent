# Case 02 — RagService: Facade gác sức khoẻ trên chunking + embedding + vector store

> **`ingest()` / `search()` đơn giản phía trước 4 subsystem (sandbox, chunking, embedder, vector store) cộng một cổng sức khoẻ cross-cutting.**

---

## 1. Bối cảnh trong hex_agent

RAG (retrieval-augmented generation) cần phối hợp nhiều mảnh độc lập, theo **đúng thứ tự**: kiểm sức khoẻ store trước → resolve path qua sandbox jail → cắt file thành chunk có overlap → embed từng chunk thành vector → kiểm cardinality (số vector phải khớp số chunk) → xoá chunk cũ rồi upsert. Nếu mỗi tool tự làm chuỗi này thì rất dễ quên một bước (đặc biệt là kiểm cardinality và health-gate), gây ghi dữ liệu lệch.

`RagService` đứng làm chokepoint, expose 3 method và luôn trả envelope `{"ok": bool, ...}`:

- `rag/service.py:1-7` — docstring nêu invariants: *health-gate before every ingest/search; ingest paths go through the workspace sandbox jail; logic never touches Qdrant directly (only via VectorStorePort); mọi method trả dict envelope `{"ok": bool, ...}`*.
- `rag/service.py:15-19` — `__init__(store, embedder, config)` giữ 3 subsystem qua port.
- `rag/service.py:22-39` — `health()` và `_require_healthy()` (cross-cutting gate).
- `rag/service.py:42-75` — `ingest()`: gate → `resolve_in_workspace` → `collect_files` → `chunk_text` → `embed` → kiểm cardinality → `delete_by_source` + `upsert`.
- `rag/service.py:78-113` — `search()`: gate → validate query/top_k/threshold → embed → `store.search` → envelope hits.

Service được lắp & đăng ký thành tool tại `rag/feature.py:109-121` (`install()`); client là agent gọi tool `rag_ingest`/`rag_search`, **không** thấy `Chunk`, `Embedder`, `VectorStore` hay path raw.

## 2. Trích đoạn code thật

```python
# rag/service.py:42-75 (rút gọn)
def ingest(self, raw_path: str) -> dict:
    gate = self._require_healthy()
    if gate is not None:
        return gate
    try:
        root = resolve_in_workspace(raw_path)
    except SandboxError as exc:
        return {"ok": False, "code": "sandbox", "error": str(exc)}

    files = collect_files(root)
    ...
    for file in files:
        texts = chunk_text(file.read_text(...), self._cfg.chunk_size, self._cfg.chunk_overlap)
        if not texts:
            continue
        vectors = self._embedder.embed(texts)
        if len(vectors) != len(texts):
            # Refuse a cardinality mismatch before any upsert so we never write a
            # partial/misaligned set of chunks for the source.
            raise ValueError(f"embedder returned {len(vectors)} embeddings for {len(texts)} chunks ...")
        chunks = [Chunk(source, i, t, v) for i, (t, v) in enumerate(zip(texts, vectors))]
        self._store.delete_by_source(source)   # re-ingest replaces previous chunks
        self._store.upsert(chunks)
        ...
    return {"ok": True, "files": len(sources), "chunks": total_chunks, "sources": sources}
```

```python
# rag/service.py:30-39 — cross-cutting health-gate
def _require_healthy(self) -> dict | None:
    h = self._store.health()
    if not h.get("ok"):
        return {"ok": False, "code": "dependency_unavailable",
                "error": f"RAG store unhealthy (collection={h.get('collection')})."}
    return None
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Facade | Thành phần trong hex_agent | Trong bản distill `.py` |
|---|---|---|
| **Facade** (class, stateful nhẹ) | `RagService` — `rag/service.py:15` | `RagService` |
| Cross-cutting gate | `_require_healthy()` — `rag/service.py:30` | `_require_healthy()` |
| Subsystem 1 — sandbox jail | `resolve_in_workspace`, `SandboxError` (`safety/sandbox.py`) | `resolve_in_workspace`, `SandboxError` |
| Subsystem 2 — chunking | `collect_files`, `chunk_text` (`rag/chunking.py`) | `collect_files`, `chunk_text` |
| Subsystem 3 — embedding | `EmbedderPort` (`rag/ports.py`) | `FakeEmbedder` / `BrokenEmbedder` |
| Subsystem 4 — vector store | `VectorStorePort` (`rag/ports.py`, `rag/stores.py`) | `InMemoryVectorStore` |
| Bất biến chống ghi lệch | cardinality check trước upsert (`rag/service.py:64-69`) | check `len(vectors) != len(texts)` |
| Client | agent gọi tool `rag_ingest/rag_search` (`rag/feature.py:109`) | `demo()` gọi `svc.ingest/search` |

## 4. Bản rút gọn chạy được

File: [`rag_service_facade.py`](./rag_service_facade.py) — chạy `python3 rag_service_facade.py`.

**Mô phỏng gì:**
- Giữ nguyên thứ tự bắt buộc và envelope `{"ok": bool, ...}` của facade thật.
- Giữ nguyên invariant chống ghi lệch: cardinality check **trước** mọi `upsert`. `BrokenEmbedder` trả thiếu 1 vector để kích hoạt nhánh này; assert chứng minh store không nhận thêm chunk nào.
- `demo()`: (1) ingest OK; (2) search OK; (3) health-gate chặn cả ingest lẫn search khi store unhealthy; (4) sandbox từ chối path thoát jail thành envelope thay vì exception thô; (5) bất biến cardinality; (6) đối chứng `ingest_without_facade` *quên* check cardinality → ghi thiếu chunk mà vẫn báo `ok` (bug âm thầm).

**Lược bỏ gì (so với bản thật):**
- File hệ thống thật → `WORKSPACE` dict in-memory.
- Embedder thật (FastEmbed) / Qdrant store → `FakeEmbedder` hash + `InMemoryVectorStore` cosine.
- **Biến đổi hành vi (đã công bố, KHÔNG khớp 1:1):** ở nhánh lỗi cardinality, code thật `rag/service.py:67-69` dùng `raise ValueError` (ném exception ra ngoài), còn bản distill `rag_service_facade.py:245-252` gói thành envelope `{"ok": False, "code": "embed_cardinality"}`. Đây là khác biệt về **kiểu trả về** của nhánh lỗi này — người đọc cần lưu ý bản distill không phản ánh đúng kiểu lỗi của code thật ở điểm này. Mục đích là minh hoạ rõ hợp đồng envelope; **bất biến cốt lõi "không bao giờ ghi tập chunk lệch/dở trước khi từ chối" vẫn được giữ y hệt** (xem assert ở bước `[5]`).
- Tầng đăng ký tool `_RagTool`/`install()` (`rag/feature.py`) không tái dựng — đó là lớp adapter quanh facade.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Leaky Facade**: nếu trả thẳng đối tượng `Chunk`/`Hit` nội bộ thì coupling không giảm. hex_agent tránh bằng cách map về dict thuần trong `search()` (`rag/service.py:104-112`).
- **Gate có thể thành nút thắt**: mọi thao tác đều gọi `health()` thêm một lần round-trip; với store đắt đỏ cần cân nhắc cache/health-cache.
- **Khi cần thao tác bậc thấp** (ví dụ chỉ muốn embed mà không upsert), facade quá kín; người dùng nâng cao sẽ phải gọi thẳng port.
- **Subsystem chỉ 1 bước** thì facade là lớp thừa.

## 6. Câu hỏi tự kiểm tra

1. Vì sao kiểm cardinality phải đặt **trước** `upsert` chứ không phải sau? Bước `[5]` và `[6]` trong demo cho thấy hậu quả của việc đặt sai/bỏ qua như thế nào?
2. `_require_healthy()` là "cross-cutting concern". Nếu mai sau gate cần thêm logic (rate-limit, circuit-breaker), client có phải sửa gì không? Vì sao?
3. Facade này khác Adapter (lesson 06) ở điểm nào, biết rằng `EmbedderPort`/`VectorStorePort` bản thân đã là các port adapter? (Gợi ý: Facade tổng hợp 1→nhiều; Adapter dịch 1→1.)
