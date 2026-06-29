# ISP trong hex_agent — Bộ ca thực chiến (hex_cases)

> Bài học gốc: [`../27_ISP.md`](../27_ISP.md) — "Receptor Specificity: mỗi receptor chỉ nghe một ligand, không có god receptor".
> Bộ ca này lấy các interface có thật trong `hex_agent` và chưng cất (distill) thành code stdlib chạy được, để thấy ISP "đời thực" trong một kiến trúc hexagonal.

---

## ISP nói gì (một dòng)

> **Clients không bị ép phụ thuộc vào method họ không dùng.** Interface là *góc nhìn của client*, không phải catalog method của implementation. Thay vì 1 interface to với 12 method, ta tạo **nhiều Protocol hẹp** đặc thù theo *từng role*.

## ISP trong hex_agent — bức tranh tổng

`hex_agent` là một kiến trúc **hexagonal (ports & adapters)**. Bản chất của hexagonal là ISP ở quy mô hệ thống: mỗi "port" là một `typing.Protocol` **hẹp**, định nghĩa đúng *một role* mà logic cần, và mỗi adapter chỉ implement port của mình — không có "god port".

Vài quan sát then chốt khi đọc codebase:

- **Port hẹp, nhiều cái, đặt theo role**: `EventSinkPort` (chỉ `emit`), `ToolPort` (chỉ `name` + `execute`), `EmbedderPort` (chỉ `embed`) tách hẳn `VectorStorePort` (search/upsert/…), `ToolMiddleware` (chỉ `__call__`), `OrchestratorPort` vs `BrokerPort`, `ChatLLM` (chỉ `complete`). Mỗi cái 1-4 method.
- **Structural subtyping**: phần lớn port là `@runtime_checkable Protocol`. Adapter "tự nhiên có" đúng method là conform, không cần kế thừa — đúng tinh thần "duck typing với type safety" của Mục 2.4.
- **Adapter = receptor đặc hiệu**: mỗi adapter (`BusEventSink`, `FakeEmbedder`, `InMemoryVectorStore`, `QdrantVectorStore`, `SafeToolPort`, `Retry`, `TimingLog`…) implement đúng *một* port hẹp. Swap-in (Kafka thay EventBus, Qdrant thay in-memory) là *thêm adapter*, không sửa caller.
- **Client thấy hẹp**: `RagService` cầm `store: VectorStorePort` + `embedder: EmbedderPort` (2 role độc lập); `EventEmitter` cầm `Iterable[EventSinkPort]`; kernel cầm một stack `ToolMiddleware`. Không ai cầm "interface tổng".

Đây chính là "receptor specificity": `EmbedderPort` chỉ nghe "embed", `VectorStorePort` chỉ nghe "search/upsert" — không protein nào nghe cả hai.

---

## Ba ca chủ lực (flagships)

| # | Thư mục | Ý chính | Port thật |
|---|---------|---------|-----------|
| 01 | [`01_rag_embedder_vectorstore_segregation/`](01_rag_embedder_vectorstore_segregation/) | Tách `EmbedderPort` khỏi `VectorStorePort` — 2 role độc lập, mỗi adapter chỉ biết 1 | `rag/ports.py:24-36` |
| 02 | [`02_event_sink_port_adapter_pattern/`](02_event_sink_port_adapter_pattern/) | `EventSinkPort` một-method, durable adapter phía sau, swap-in Kafka không sửa caller | `control/ports.py:14-22` |
| 03 | [`03_tool_middleware_composition/`](03_tool_middleware_composition/) | `ToolMiddleware` — Protocol callable hẹp 1 chữ ký, compose thành chain | `core/middleware.py:11-22` |

Mỗi thư mục có `README.md` (6 mục: bối cảnh → trích code thật → bảng ánh xạ → bản rút gọn → cái giá → câu hỏi) và một file `.py` chạy được bằng `python3` với narration tiếng Việt + assert.

## Vét cạn occurrence

Xem [`CATALOG.md`](CATALOG.md) — bảng MỌI nơi ISP xuất hiện trong codebase (port + adapter + client), kèm `path:line` và độ rõ.

---

## Cách chạy

```bash
python3 "01_rag_embedder_vectorstore_segregation/rag_embedder_vectorstore_segregation.py"
python3 "02_event_sink_port_adapter_pattern/event_sink_port_adapter_pattern.py"
python3 "03_tool_middleware_composition/tool_middleware_composition.py"
```

Mỗi file chỉ dùng thư viện chuẩn Python 3.14, không import `hex_agent` hay thư viện bên thứ ba, thoát code 0.

## Đọc theo thứ tự nào?

1. **Ca 01** trước — ví dụ gốc nhất của ISP: hai role (embed / store) tách thành hai port, client cầm cả hai nhưng phụ thuộc hẹp.
2. **Ca 02** — port một-method tối giản + adapter swap-in (canonical hexagonal port).
3. **Ca 03** — ISP áp lên interface dạng *callable* (Protocol `__call__`), thấy structural typing cho phép compose mà các thành phần không biết nhau.
