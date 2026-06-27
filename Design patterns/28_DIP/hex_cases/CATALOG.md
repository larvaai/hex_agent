# CATALOG — Mọi occurrence của DIP trong hex_agent

Vét cạn các điểm áp dụng **Dependency Inversion Principle** (port/Protocol + adapter +
dependency injection + composition root) trong codebase `hex_agent`. Đường dẫn là TƯƠNG ĐỐI so
với root `/Users/uspro/Desktop/namnson/hex_agent/`.

Các dòng được đánh dấu ★ là flagship đã dựng thành case con (xem thư mục tương ứng).

| path:line | Mô tả | Độ rõ |
|---|---|---|
| ★ `core/ports.py:19-26` | `ToolPort` — abstraction cốt lõi cho tool executor (`name` + `execute`) | high |
| `core/ports.py:32-45` | `DelegationPort` — abstraction cho delegation handler (`can_handle` + `run`) | high |
| `core/ports.py:48-62` | `DelegationStorePort` — abstraction lưu trạng thái delegation (`start`, `append_progress`, `finish`, `progress`, `result`) | high |
| `core/ports.py:65-76` | `DelegationServicePort` — abstraction cho delegation service (`available_targets`, `delegate`) | high |
| `core/registry.py:29-40` | `NullToolPort` — fallback khi không tìm thấy tool; graceful degradation sau interface `ToolPort` | medium |
| `core/middleware.py:11-22` | `ToolMiddleware` Protocol — structural protocol cho pre/post hook quanh execute_tool (theo tinh thần DIP cho chuỗi middleware) | high |
| ★ `control/ports.py:14-22` | `EventSinkPort` — abstraction định tuyến sự kiện (`emit`); docstring nhắc Kafka/Redis adapter sẽ đến sau (T2) | high |
| ★ `control/emitter.py:28-36` | `BusEventSink` — adapter implement `EventSinkPort`, bọc in-process `EventBus` | high |
| ★ `control/emitter.py:39-61` | `EventEmitter` — consumer cấp cao nhận `EventSinkPort` qua DI, fan-out tới mọi sink | high |
| `control/emitter.py:93-95` | `bus_emitter()` — factory nối `EventEmitter` với `BusEventSink` (composition) | high |
| ★ `rag/ports.py:24-28` | `EmbedderPort` — abstraction embed text (`dim` + `embed`) | high |
| ★ `rag/ports.py:31-36` | `VectorStorePort` — abstraction thao tác vector DB (`health`, `delete_by_source`, `upsert`, `search`) | high |
| ★ `rag/embedders.py:33-46` | `FakeEmbedder` — adapter implement `EmbedderPort`, deterministic offline cho test | high |
| ★ `rag/embedders.py:49-60` | `FastEmbedEmbedder` — adapter implement `EmbedderPort`, production (fastembed, lazy import dòng 53) | high |
| ★ `rag/stores_qdrant.py:32-148` | `QdrantVectorStore` — adapter đầy đủ implement `VectorStorePort`, bọc qdrant-client (lazy import dòng 43, `client` tiêm được dòng 35-49) | high |
| ★ `rag/service.py:15-19` | `RagService` — service cấp cao nhận `VectorStorePort` + `EmbedderPort` + config qua DI; không biết implementation cụ thể | high |
| ★ `safety/policy.py:105-124` | `SafeToolPort` — adapter bọc `ToolPort`, chèn policy gate trước khi delegate (composition of ports) | high |
| `supervisor/broker.py:17-21` | `BrokerPort` — abstraction cho context briefing (`write_packet`) | high |
| `supervisor/broker.py:24-55` | `DeterministicBroker` — adapter implement `BrokerPort`, sinh briefing offline (S1 reference) | high |
| `decompose_agent/worker.py:182-185` | `Worker` Protocol — abstraction cho task worker (`propose` + `decompose`) | high |
| `decompose_agent/worker.py:188-227` | `ScriptedWorker` — adapter implement `Worker`, double deterministic cho test (không LLM, dùng script) | high |
| `decompose_agent/worker.py:230-300` | `LocalLLMWorker` — adapter implement `Worker`, backend OpenAI-compatible với retry/backoff (`client` tiêm được, lazy import dòng 249) | high |
| ★ `toolbox/feature.py:67-77` | Composition root: `install()` bọc instance tool cụ thể trong `SafeToolPort` rồi register vào kernel; mọi tool đến từ `_TOOL_CLASSES`, policy áp đồng đều | high |
| `core/bootstrap.py:56-66` | `build_kernel()` — composition root tạo `AgentKernel` với `CapabilityRegistry` + `EventBus`, rồi install feature/middleware qua DI | medium |
| `tests_audit/test_core_edges_rigor.py:52-79` | `RecordingMiddleware` test double implement `ToolMiddleware` Protocol thuần cấu trúc (chỉ `__call__`); minh hoạ conformance không cần kế thừa | medium |
| `tests_audit/test_rag_edges_rigor.py` (rải rác) | Nhiều test double (`InMemoryVectorStore`, `_SpyEmbedder`, `FakeEmbedder`) implement các RAG port để unit test không cần backend thật | medium |

---

## Ghi chú đọc bảng

- **Abstraction sống ở gói cấp cao**: `core/ports.py`, `control/ports.py`, `rag/ports.py`,
  `supervisor/broker.py`, `decompose_agent/worker.py`. Đây là nơi consumer tuyên bố "tôi cần gì".
- **Adapter sống ở gói cấp thấp/hạ tầng**: `safety/policy.py`, `control/emitter.py`,
  `rag/embedders.py`, `rag/stores_qdrant.py` — chúng import abstraction, không bị abstraction
  import ngược.
- **Composition root** là điểm duy nhất thấy cả hai tầng: `toolbox/feature.py`,
  `core/bootstrap.py`, `rag/feature.py`, `control/emitter.py:bus_emitter`.
- **Lazy import** (`fastembed`, `qdrant_client`, `openai`) nằm bên trong adapter để base
  install và test offline không kéo theo dependency nặng — một hệ quả thực tế của DIP.
