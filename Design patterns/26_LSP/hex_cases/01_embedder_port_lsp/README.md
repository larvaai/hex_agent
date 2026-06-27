# Case 01 — EmbedderPort: FakeEmbedder & FastEmbedEmbedder thay thế cho nhau

> LSP trong thực chiến: hai adapter embedding rất khác nhau (hash offline vs model production)
> cùng tuân CÙNG MỘT contract `EmbedderPort`, nên `RagService` swap chúng mà không cần biết loại nào.

---

## 1. Bối cảnh trong hex_agent

RAG (Epic E08) cần biến text thành vector. Có hai hoàn cảnh:

- **Offline / test**: không tải model, không network — cần một embedder tất định để chạy acceptance suite.
- **Production**: cần model thật (`fastembed`) — nặng, lazy import để base install nhẹ.

Nếu `RagService` phải `if isinstance(embedder, FastEmbedEmbedder): ...` thì mỗi lần thêm backend
là phải sửa logic — OCP sụp. LSP là điều kiện *hành vi* để điều đó không xảy ra: cả hai embedder
giữ đúng hợp đồng nên caller không cần biết loại.

Port khai báo tại `rag/ports.py:24-28` (đã mở kiểm chứng):

- `EmbedderPort` là `Protocol`, `@runtime_checkable` → có thể `isinstance` theo *cấu trúc* (có `.dim` + `.embed`).
- Hai impl tại `rag/embedders.py`: `FakeEmbedder` (dòng 33-46), `FastEmbedEmbedder` (dòng 49-60).
- Caller `RagService` phụ thuộc abstraction tại `rag/service.py:15-19`; gọi `embedder.embed()` ở
  `rag/service.py:63` (ingest) và `rag/service.py:97` (search), KHÔNG `isinstance`.
- Chokepoint bảo vệ postcondition cardinality: `rag/service.py:64-69`.
- Test xác nhận tuân thủ cấu trúc: `tests_audit/test_rag_edges_rigor.py:95-99`
  (`isinstance(FastEmbedEmbedder(...), EmbedderPort)`).

---

## 2. Trích đoạn code thật

Abstraction (`rag/ports.py:24-28`):

```python
@runtime_checkable
class EmbedderPort(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Hai subtype cùng interface (`rag/embedders.py:33-46` và `49-60`):

```python
class FakeEmbedder:
    def __init__(self, dim: int = 64) -> None:
        self.dim = dim
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

class FastEmbedEmbedder:
    def __init__(self, model: str) -> None:
        from fastembed import TextEmbedding
        self._model = TextEmbedding(model_name=model)
        self.dim = len(next(iter(self._model.embed(["probe"]))))  # probe dim 1 lần
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(v) for v in self._model.embed(texts)]
```

Caller giữ hợp đồng cardinality (`rag/service.py:63-69`):

```python
vectors = self._embedder.embed(texts)
if len(vectors) != len(texts):
    raise ValueError(
        f"embedder returned {len(vectors)} embeddings for {len(texts)} chunks (count mismatch)."
    )
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò LSP | Thành phần trong hex_agent | File:line |
|---|---|---|
| Abstraction `T` (contract) | `EmbedderPort` Protocol | `rag/ports.py:24-28` |
| Caller (depend on `T`) | `RagService.__init__` / `.ingest` / `.search` | `rag/service.py:15-19, 63, 97` |
| Subtype `S₁` (offline) | `FakeEmbedder` | `rag/embedders.py:33-46` |
| Subtype `S₂` (production) | `FastEmbedEmbedder` | `rag/embedders.py:49-60` |
| Postcondition được caller bảo vệ | `len(vectors) != len(texts)` → `ValueError` | `rag/service.py:64-69` |
| Precondition (chấp nhận `[]`) | `embed([]) == []` | `tests_audit/test_rag_edges_rigor.py:87-92, 103-108` |
| Invariant (`dim` cố định) | `self.dim` set trong `__init__`, không đổi | `rag/embedders.py:36, 57` |
| Bằng chứng tuân thủ cấu trúc | `isinstance(emb, EmbedderPort)` | `tests_audit/test_rag_edges_rigor.py:95-99` |

---

## 4. Bản rút gọn chạy được

File: [`embedder_port_lsp.py`](./embedder_port_lsp.py) — `python3 embedder_port_lsp.py` (exit 0).

**Mô phỏng đúng:** Protocol `EmbedderPort`; `FakeEmbedder` (hash bag-of-words như bản thật);
`FastEmbedEmbedder` với cấu trúc *lazy build + probe dim 1 lần + materialize generator → list*;
`RagService` phụ thuộc abstraction và bảo vệ postcondition cardinality; một bộ `liskov_contract()`
abstract chạy y hệt trên cả hai impl.

**Lược bỏ:** thư viện `fastembed` thật (thay bằng `_StubTextEmbedding` stdlib map từ → vector theo
độ dài); phần chunking, sandbox, health-gate (thuộc các case khác); tuyệt đối không import hex_agent.

**Đối chứng:** `BrokenEmbedder` *trông giống* (qua `isinstance` cấu trúc) nhưng *làm yếu postcondition*
(trả ít vector hơn số text) → `RagService.ingest` ném `ValueError` ở chokepoint cardinality, minh họa
"trông giống ≠ thay được".

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí**: phải *document* và *kiểm thử* contract (cardinality, dim bất biến, chấp nhận rỗng).
  Nếu chỉ có DUY NHẤT một embedder mãi mãi, LSP không kích hoạt — viết thẳng concrete, đừng dựng Protocol.
- **Cạm bẫy**: `@runtime_checkable` chỉ kiểm tra *có method/attr*, KHÔNG kiểm tra *hành vi*. `isinstance`
  pass không có nghĩa là LSP-compliant (xem `BrokenEmbedder`). Vẫn cần Liskov contract test.
- Khi hai backend thật sự khác hợp đồng (ví dụ một cái trả vector chưa normalize), đừng nhét chung
  một port — hoặc chuẩn hóa tại biên, hoặc tách interface.

## 6. Câu hỏi tự kiểm tra

1. `@runtime_checkable` khiến `isinstance(broken, EmbedderPort)` trả `True` dù `broken` làm yếu
   postcondition. Vậy điều gì THỰC SỰ bắt được vi phạm trong hex_agent, và ở dòng nào?
2. Vì sao `FastEmbedEmbedder` probe `dim` đúng một lần trong `__init__` thay vì mỗi lần `embed`?
   Liên hệ với invariant "`dim` không đổi" của contract.
3. Nếu thêm `OpenAIEmbedder` mới, cần sửa bao nhiêu dòng trong `RagService`? Vì sao?
