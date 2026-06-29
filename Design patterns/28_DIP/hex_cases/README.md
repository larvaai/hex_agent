# DIP (Dependency Inversion Principle) trong hex_agent — Bộ case học

> SOLID Pattern 5 — Dependency Inversion Principle.
> **Cấp cao định nghĩa abstraction; cấp thấp đến để thực hiện. Source-code dependency
> direction ĐẢO NGƯỢC runtime call direction.**
>
> Tài liệu lý thuyết gốc: `../28_DIP.md` (analogy thần kinh học: thalamus relay — cortex
> high-level định nghĩa "spike train pattern", retina/cochlea low-level phải adapt).

Đây là bộ case **thực chứng**: mỗi case soi một chỗ DIP có thật trong codebase `hex_agent`,
trích đúng file:line, rồi cung cấp một bản rút gọn chạy được chỉ bằng thư viện chuẩn Python.

---

## DIP trong hex_agent — tổng quan

hex_agent áp dụng DIP rất rộng theo lối **port (Protocol) + dependency injection**:

- Module **cấp cao** (logic nghiệp vụ) định nghĩa abstraction dưới dạng `Protocol` trong các
  file `ports.py` riêng (`core/ports.py`, `control/ports.py`, `rag/ports.py`, …).
- Adapter **hạ tầng cấp thấp** *implement* các port đó **mà không có chiều phụ thuộc ngược lại**
  (cấp cao không import cấp thấp).
- **Composition root** (vd `toolbox/feature.py`, `core/bootstrap.py`, `rag/feature.py`) là nơi
  duy nhất nối implementation cụ thể vào abstraction.

Các seam tiêu biểu: `ToolPort`/`SafeToolPort`, `EventSinkPort`/`BusEventSink`,
`EmbedderPort`/`VectorStorePort`, `BrokerPort`/`DeterministicBroker`, `Worker` protocol — mỗi
seam tách logic nghiệp vụ khỏi implementation cụ thể, cho phép test offline và swap hạ tầng.

Bằng chứng "đảo chiều": `core/` không import `toolbox/`; `rag/service.py` không import
`qdrant_client`/`fastembed` (lazy import nằm trong adapter). Xoá thư mục hạ tầng đi, package
cấp cao vẫn compile và vẫn unit-test được với fake.

---

## Các case con

| # | Case | Seam chính | Nguồn thật (file:line) |
|---|---|---|---|
| 01 | [`01_tool_safety_port_adapter`](01_tool_safety_port_adapter/) | `ToolPort` ← `SafeToolPort` adapter + kernel | `core/ports.py:19-26`, `safety/policy.py:105-124`, `toolbox/feature.py:67-77` |
| 02 | [`02_event_sink_port_bus_adapter`](02_event_sink_port_bus_adapter/) | `EventSinkPort` ← `BusEventSink`, `EventEmitter` (DI) | `control/ports.py:14-22`, `control/emitter.py:28-36`, `control/emitter.py:39-61` |
| 03 | [`03_rag_embedder_vector_store_ports`](03_rag_embedder_vector_store_ports/) | `EmbedderPort` + `VectorStorePort` ← `RagService` (DI) | `rag/ports.py:24-36`, `rag/embedders.py:33-60`, `rag/stores_qdrant.py:32-49`, `rag/service.py:15-19` |

Mỗi thư mục case có: một `README.md` (6 mục: bối cảnh, trích code thật, bảng ánh xạ vai trò,
bản rút gọn, cái giá, câu hỏi tự kiểm tra) và một file `.py` self-contained chạy được.

Danh mục **đầy đủ** mọi occurrence của DIP trong codebase: xem [`CATALOG.md`](CATALOG.md).

---

## Chạy thử

```bash
python3 01_tool_safety_port_adapter/tool_safety_port_adapter.py
python3 02_event_sink_port_bus_adapter/event_sink_port_bus_adapter.py
python3 03_rag_embedder_vector_store_ports/rag_embedder_vector_store_ports.py
```

Cả ba thoát code 0, in narration tiếng Việt từng bước và chứa các `assert` chứng minh bất biến
của DIP (adapter thoả port; swap hạ tầng không đụng logic; consumer không biết kiểu cụ thể).

---

## Nhớ một câu

> DIP không phải "dùng interface". DIP là "**high-level định nghĩa interface; low-level đến để
> thực hiện**" — và bằng chứng là gói cấp cao *không* `import` gói hạ tầng.
