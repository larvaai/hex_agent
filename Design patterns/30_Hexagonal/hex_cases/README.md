# Hexagonal (Ports & Adapters) trong `hex_agent` — Bộ case học

> Tài liệu dạy học đi kèm Lesson 30. Mục tiêu: chỉ ra Hexagonal Architecture **xuất hiện thật** ở đâu trong
> codebase `hex_agent`, rồi chưng cất mỗi chỗ thành một file Python **chạy được, self-contained, chỉ dùng stdlib**
> để học viên thấy đúng *vai trò pattern* mà không cần dựng Qdrant/LangGraph/LLM.

Thư mục này **không sửa** bài học gốc (`../30_Hexagonal.md`); nó bổ sung các ví dụ rút gọn từ code thật.

---

## Hexagonal trong hex_agent — bức tranh tổng

`hex_agent` được tổ chức quanh **một lõi domain** + **các adapter cắm vào qua port**, hiện rõ ở ba lớp:

1. **Domain core + Ports.** Các seam I/O được khai báo bằng `Protocol` mà lõi **không** import bản cụ thể:
   `core/ports.py` (`ToolPort`, `DelegationPort`, `DelegationStorePort`), `control/ports.py` (`EventSinkPort`),
   `rag/ports.py` (`EmbedderPort`, `VectorStorePort`), `supervisor/orchestrator.py` (`OrchestratorPort`),
   `supervisor/broker.py` (`BrokerPort`), `core/middleware.py` (`ToolMiddleware`).
2. **Adapters.** Bản thực thi cụ thể của các port, sống ở `adapters/`, `rag/`, `delegation/`, `control/`:
   `ScriptedDelegationAgent` / `LangGraphDelegationAgent`, `QdrantVectorStore` / `InMemoryVectorStore`,
   `BusEventSink`, `InMemoryDelegationStore`, `NullToolPort`…
3. **Composition roots.** `core/bootstrap.py` (`build_kernel`), các feature builder (`rag/feature.py` `build_service`,
   `delegation/bootstrap.py` `create_delegation_service`), `control/emitter.py` `bus_emitter` — nơi DUY NHẤT
   nối port + adapter cụ thể vào lõi.

Bất biến xuyên suốt: **domain core không bao giờ import adapter cụ thể — chỉ biết Protocol/Port.** Lời tự thuật
của lõi (`core/kernel.py:78-83`): *"Concrete behavior lives behind ports/adapters in the registry."*

Hai hướng port đều có mặt:
- **Driven port** (lõi gọi RA): `VectorStorePort`, `EmbedderPort`, `EventSinkPort`, `DelegationStorePort`.
- **Driving port** (thế giới ngoài / adapter thực hiện hành vi lõi công bố): `DelegationPort`, `OrchestratorPort`, `BrokerPort`, `ToolPort`.

---

## Các case con

| # | Case | Trục Hexagonal | Port chính | Hai adapter cạnh tranh |
|---|------|----------------|-----------|------------------------|
| [01](./01_rag_service_ports_adapters/) | RAG Service — triple adapter | **Driven** | `VectorStorePort`, `EmbedderPort` | `InMemoryVectorStore` (offline) vs `QdrantVectorStore` (prod) |
| [02](./02_delegation_agents_pattern/) | Delegation — driving adapters | **Driving** | `DelegationPort` | `ScriptedDelegationAgent` (test) vs `LangGraphDelegationAgent` (prod) |
| [03](./03_event_sink_hexagon/) | Event Control Plane — future expansion | **Driven** | `EventSinkPort` | `BusEventSink` (v1) → `MemorySink`/`KafkaLikeSink` (T2) |

Mỗi case con có:
- `README.md` — bài học 6 mục (bối cảnh thật, trích code thật, bảng ánh xạ vai trò, bản rút gọn, cái giá, câu hỏi).
- `<name>.py` — bản distill chạy được: `python3 <name>.py` (thoát code 0, có narration tiếng Việt + assert + phản ví dụ).

Xem [`CATALOG.md`](./CATALOG.md) để có **bảng vét cạn** mọi occurrence của pattern trong codebase (kèm path:line và độ rõ).

---

## Vì sao chọn ba case này làm flagship

- **Case 01** là minh hoạ kinh điển nhất: cùng một driven port có **hai adapter thực sự cạnh tranh** trong repo
  (Qdrant cho production, InMemory cho test offline), DI qua `__init__`, composition root chọn theo config.
- **Case 02** dạy điểm hay gây nhầm: **driving** port khác **driven** port. Lõi định nghĩa "việc nó làm được"
  (`run`), adapter thực thi; registry cho phép thêm chiến lược mà không sửa lõi.
- **Case 03** dạy **Future Expansion**: docstring của port nói thẳng "v1 Bus, T2 Kafka, no caller change" —
  ví dụ sống về việc kiến trúc *chuẩn bị sẵn* cho việc thay transport mà không đụng lõi.

---

## Cách chạy nhanh tất cả

```bash
cd "Design patterns/30_Hexagonal/hex_cases"
python3 01_rag_service_ports_adapters/rag_service_ports_adapters.py
python3 02_delegation_agents_pattern/delegation_agents_pattern.py
python3 03_event_sink_hexagon/event_sink_hexagon.py
```

Tất cả chỉ dùng thư viện chuẩn Python 3.14 — không cần cài gì, không cần docker/network/LLM.

---

## Bốn bất biến Hexagonal — đối chiếu với hex_agent

| Bất biến (Lesson 30, mục 2.2) | hex_agent tuân thế nào |
|---|---|
| 1. Domain core không import adapter package | `RagService`, `DelegationManager`, `EventEmitter` chỉ import port/Protocol |
| 2. Driving port định nghĩa bởi core | `DelegationPort`, `OrchestratorPort`, `BrokerPort` nằm trong `core/`, `supervisor/` |
| 3. Driven port định nghĩa bởi core; adapter implement | `VectorStorePort`/`EventSinkPort` ở `rag/`, `control/`; Qdrant/Bus adapter implement |
| 4. Composition root là nơi duy nhất biết cả core lẫn adapter | `build_kernel`, `build_service`, `create_delegation_service`, `bus_emitter` |
