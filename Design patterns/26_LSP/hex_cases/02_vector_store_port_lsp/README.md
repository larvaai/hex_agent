# Case 02 — VectorStorePort: InMemoryVectorStore & QdrantVectorStore thay thế cho nhau

> LSP "trong veo": hai adapter store có nội tạng *trái ngược* (list trong RAM vs gRPC remote)
> cùng giữ một contract — đặc biệt là **`health()` không bao giờ raise** — nên `RagService`
> health-gate/ingest/search không hề `if/elif` theo loại store.

---

## 1. Bối cảnh trong hex_agent

RAG (Epic E08) lưu/tìm vector. Hai backend:

- **`InMemoryVectorStore`** (`rag/stores.py:24-56`): offline, dùng cho acceptance suite docker-free,
  cosine tất định, `health()` có thể bật/tắt để test nhánh "dependency failure" (S08.1).
- **`QdrantVectorStore`** (`rag/stores_qdrant.py:32-149`): production qua `qdrant-client` gRPC, lazy
  collection, point id tất định.

Điểm tinh tế nhất của contract: **`health()` KHÔNG raise**. Một server Qdrant chết phải biến thành
`{"ok": False}` (control flow bình thường), KHÔNG ném exception lên `RagService`. Nhờ vậy
`RagService._require_healthy` (`rag/service.py:30-39`) là một nhánh `if` đơn giản, đúng với CẢ HAI
store. Nếu một store phá điều này (raise thay vì nuốt), caller buộc phải `try/except` đặc thù →
ép biết loại store → OCP sụp.

Đã mở kiểm chứng:
- Port: `rag/ports.py:31-36` (`@runtime_checkable`).
- `InMemoryVectorStore.health()` không raise: `rag/stores.py:35-36`; `search()` sort + cắt top_k: `47-56`.
- `QdrantVectorStore.health()` nuốt lỗi server: `rag/stores_qdrant.py:83-90`.
- Caller: `rag/service.py:16, 22-23, 30-39, 71-72`.
- Test xác nhận tuân thủ cấu trúc: `tests_audit/test_rag_edges_rigor.py:559-563`
  (`isinstance(QdrantVectorStore(...), VectorStorePort)`); parity health envelope: `:566`.

---

## 2. Trích đoạn code thật

Abstraction (`rag/ports.py:31-36`):

```python
@runtime_checkable
class VectorStorePort(Protocol):
    def health(self) -> dict: ...
    def delete_by_source(self, source: str) -> int: ...
    def upsert(self, chunks: list[Chunk]) -> int: ...
    def search(self, vector: list[float], top_k: int, score_threshold: float) -> list[Hit]: ...
```

Contract `health()` không raise — hai impl, hai cách, cùng một lời hứa
(`rag/stores.py:35-36` và `rag/stores_qdrant.py:83-90`):

```python
# InMemoryVectorStore
def health(self) -> dict:
    return {"ok": self._healthy, "collection": self.collection, "count": len(self._chunks)}

# QdrantVectorStore
def health(self) -> dict:
    try:
        ...
        return {"ok": True, "collection": self.collection, "count": count}
    except Exception as exc:  # unreachable server -> dependency failure, not a crash
        return {"ok": False, "collection": self.collection, "count": 0, "error": str(exc)}
```

Caller dựa vào lời hứa đó (`rag/service.py:30-39`):

```python
def _require_healthy(self) -> dict | None:
    h = self._store.health()           # không bao giờ raise -> không cần try/except
    if not h.get("ok"):
        return {"ok": False, "code": "dependency_unavailable", ...}
    return None
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò LSP | Thành phần trong hex_agent | File:line |
|---|---|---|
| Abstraction `T` (contract) | `VectorStorePort` Protocol | `rag/ports.py:31-36` |
| Caller (depend on `T`) | `RagService` health-gate/ingest/search | `rag/service.py:16, 30-39, 71-72, 98` |
| Subtype `S₁` (in-process) | `InMemoryVectorStore` | `rag/stores.py:24-56` |
| Subtype `S₂` (remote gRPC) | `QdrantVectorStore` | `rag/stores_qdrant.py:32-149` |
| Exception contract (`health()` không raise) | nuốt lỗi server → `{"ok": False}` | `rag/stores_qdrant.py:83-90` |
| Postcondition (`search` sort + cắt top_k) | sort `(-score, source, chunk_index)` rồi `[:top_k]` | `rag/stores.py:47-56` |
| Invariant idempotent (`delete_by_source`) | xóa nguồn đã xóa → 0 | `tests_audit/test_rag_edges_rigor.py:154-160` |
| Bằng chứng tuân thủ cấu trúc | `isinstance(store, VectorStorePort)` | `tests_audit/test_rag_edges_rigor.py:559-563` |

---

## 4. Bản rút gọn chạy được

File: [`vector_store_port_lsp.py`](./vector_store_port_lsp.py) — `python3 vector_store_port_lsp.py` (exit 0).

**Mô phỏng đúng:** Protocol `VectorStorePort` 4 method; `InMemoryVectorStore` cosine tất định;
`QdrantVectorStore` qua một `_FakeQdrantClient` stdlib GIỮ NGUYÊN contract (lazy/idempotent id,
`health()` nuốt lỗi khi `reachable=False`); `RagService` health-gate + re-ingest replace; một bộ
`liskov_contract()` chạy y hệt trên hai store.

**Lược bỏ:** `qdrant-client` thật, gRPC, tạo collection/payload index thật, `uuid5` namespace
(thay bằng id `"source::index"` vẫn tất định/idempotent), embedding (dùng vector cho sẵn).

**Đối chứng:** `CrashingStore.health()` *raise* `ConnectionError` (mở rộng exception type ngoài
hợp đồng) → vì `RagService` không `try/except ConnectionError`, caller crash → minh họa vi phạm
quy tắc "exception type không được mở rộng".

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí**: contract "không raise" khó giữ — mọi đường lỗi hạ tầng (timeout, mất kết nối) phải
  được *nuốt và quy về `{"ok": False}`*. Dễ sót một nhánh exception. Phải có test cho server chết.
- **Cạm bẫy**: nếu một adapter rò rỉ exception hạ tầng *ngầm* (vd: `delete_by_source` raise khi mạng
  rớt), code chạy bình thường trong test nhưng vỡ trên production — đúng kiểu vi phạm LSP khó thấy.
- Khi chỉ có một backend và không bao giờ đổi, không cần Protocol; thêm tầng trừu tượng chỉ là chi phí.

## 6. Câu hỏi tự kiểm tra

1. Vì sao đặt contract "`health()` không raise" lại quan trọng hơn so với để `RagService` tự
   `try/except` quanh mỗi lời gọi store? (Gợi ý: nếu mỗi store raise một loại exception khác nhau thì sao?)
2. `search()` của cả hai store đều phải trả list `Hit` đã sort tất định rồi cắt `top_k`. Nếu một
   store cắt `top_k` TRƯỚC khi sort thì vi phạm quy tắc LSP nào, và caller hỏng ra sao?
3. `delete_by_source` phải idempotent (xóa lần hai trả 0). Đây là loại điều kiện gì trong 4 quy tắc
   LSP (pre/post/invariant/exception)?
