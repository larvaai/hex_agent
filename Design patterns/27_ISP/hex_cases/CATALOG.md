# CATALOG — Mọi occurrence của ISP trong hex_agent

Bảng vét cạn các nơi ISP biểu hiện (port hẹp, adapter implement đúng 1 port, client phụ thuộc interface hẹp). Mọi `path:line` đều tương đối so với root `/Users/uspro/Desktop/namnson/hex_agent/` và đã được mở kiểm chứng.

Cột "Vai trò ISP": **Port** = narrow interface (Protocol/abstract); **Adapter** = impl concrete một port; **Client** = nơi phụ thuộc port hẹp.

| # | path:line | Vai trò ISP | Mô tả | Độ rõ |
|---|-----------|-------------|-------|-------|
| 1 | `rag/ports.py:24-28` | Port | `@runtime_checkable EmbedderPort(Protocol)`: `dim` property + `embed(texts)`. 2 adapter: `FakeEmbedder` (offline), `FastEmbedEmbedder` (production). | cao |
| 2 | `rag/ports.py:31-36` | Port | `@runtime_checkable VectorStorePort(Protocol)`: 4 method (`health`, `delete_by_source`, `upsert`, `search`). `InMemoryVectorStore` + `QdrantVectorStore` implement. | cao |
| 3 | `rag/service.py:15-19` | Client | `RagService(store: VectorStorePort, embedder: EmbedderPort, config)` — phụ thuộc 2 port hẹp độc lập, dễ test/mock từng cái. | cao |
| 4 | `rag/embedders.py:33-46` | Adapter | `FakeEmbedder` implement chỉ `EmbedderPort` (`dim` + `embed`), không biết về `VectorStorePort`. | cao |
| 5 | `rag/embedders.py:49-60` | Adapter | `FastEmbedEmbedder` implement same `EmbedderPort` qua fastembed (lazy import). Swap-in production, không sửa client. | cao |
| 6 | `rag/stores.py:24-56` | Adapter | `InMemoryVectorStore` implement chỉ `VectorStorePort` (4 method, cosine offline), không biết embedding. | cao |
| 7 | `rag/stores_qdrant.py:32-148` | Adapter | `QdrantVectorStore` (production) implement `VectorStorePort`: lazy collection init, deterministic uuid5 ids. Tách biệt hẳn `EmbedderPort`. | cao |
| 8 | `rag/feature.py:27-42` | Client | `build_service` chọn adapter (`FakeEmbedder`/`FastEmbedEmbedder`, `InMemoryVectorStore`/`QdrantVectorStore`) độc lập theo backend. | cao |
| 9 | `control/ports.py:14-22` | Port | `@runtime_checkable EventSinkPort(Protocol)` chỉ 1 method `emit(event)`. Doc ghi rõ "T2: Kafka adapter implementing the same emit dropped in". | cao |
| 10 | `control/emitter.py:28-36` | Adapter | `BusEventSink` adapt in-process `EventBus` thành `EventSinkPort`. Chỉ cần `emit()`. | cao |
| 11 | `control/emitter.py:39-61` | Client | `EventEmitter` nhận `Iterable[EventSinkPort]`, fan-out tới mọi sink sau khi validate/seq/redact. Caller chỉ thấy port hẹp. | cao |
| 12 | `core/middleware.py:11-22` | Port | `ToolMiddleware(Protocol)`: callable `__call__(request, nxt) -> dict`. Hẹp, structural, `fail_open` là optional attribute (đọc bằng getattr). | cao |
| 13 | `middleware/retry.py:23-33` | Adapter | `Retry` implement `__call__(request, nxt)` — conform `ToolMiddleware`, không biết middleware khác. | cao |
| 14 | `middleware/timing.py:10-26` | Adapter | `TimingLog` implement `__call__`, declare `fail_open=True` (advisory). Tách biệt hoàn toàn với `Retry`. | cao |
| 15 | `core/ports.py:19-26` | Port | `@runtime_checkable ToolPort(Protocol)`: `name` property + `execute(request) -> dict`. Mỗi tool adapter implement port này. | cao |
| 16 | `core/ports.py:32-45` | Port | `@runtime_checkable DelegationPort(Protocol)`: `name`, `can_handle()`, `run()` — handler cho 1 delegation target. | cao |
| 17 | `core/ports.py:48-62` | Port | `DelegationStorePort(Protocol)`: `start`, `append_progress`, `finish`, `progress`, `result` — storage interface. | cao |
| 18 | `core/ports.py:65-77` | Port | `DelegationServicePort(Protocol)`: `available_targets`, `delegate` — orchestration port cấp cao. | cao |
| 19 | `core/registry.py:29-40` | Adapter | `NullToolPort`: fallback graceful, implement `ToolPort` contract (`name` + `execute`) nhưng trả `missing_capability`. | cao |
| 20 | `core/registry.py:43-122` | Client | `CapabilityRegistry.resolve_tool` trả executor như `ToolPort`, không biết impl cụ thể. | vừa |
| 21 | `delegation/manager.py:19-31` | Client | `DelegationManager.__init__` nhận `registry`, `sessions`, `store: DelegationStorePort` — tách 3 concern. | cao |
| 22 | `delegation/store.py:9-56` | Adapter | `InMemoryDelegationStore` implement `DelegationStorePort` (thread-safe v1; T2 sẽ là PostgreSQL adapter). | cao |
| 23 | `supervisor/orchestrator.py:15-18` | Port | `@runtime_checkable OrchestratorPort(Protocol)`: `compose_team`, `decide`. `ScriptedOrchestrator` + `LLMOrchestrator` implement. | cao |
| 24 | `supervisor/orchestrator.py:21-39` | Adapter | `ScriptedOrchestrator` implement `OrchestratorPort`, canned responses cho test offline (không phụ thuộc LLM). | cao |
| 25 | `supervisor/llm.py:52-54` | Port | `@runtime_checkable ChatLLM(Protocol)`: 1 method `complete(messages)`. Hẹp, dùng bởi orchestrator/broker. | cao |
| 26 | `supervisor/llm.py:57-68` | Adapter | `KernelChatLLM` implement `ChatLLM`, reach model via `kernel.execute_tool('llm.chat')`. Adapt kernel thành LLM protocol. | cao |
| 27 | `supervisor/llm.py:71-91` | Client | `LLMOrchestrator(llm: ChatLLM)` implement `OrchestratorPort`. Phụ thuộc chỉ `ChatLLM`, không biết `KernelChatLLM` impl. | cao |
| 28 | `supervisor/broker.py:17-21` | Port | `@runtime_checkable BrokerPort(Protocol)`: 1 method `write_packet(assignment, store_slice) -> ContextPacket`. | cao |
| 29 | `supervisor/broker.py:24-55` | Adapter | `DeterministicBroker` implement `BrokerPort` offline + grounded. `LLMBroker` (S2) swap-in same port. | cao |
| 30 | `safety/policy.py:105-124` | Adapter | `SafeToolPort` wrap inner executor, implement `ToolPort` (`name` + `execute`): policy gate → inner tool. | cao |
| 31 | `toolbox/feature.py:67-77` | Client | `install()` register mỗi tool qua `SafeToolPort(tool.name, tool, policy)`. Mỗi tool adapter implement `ToolPort`. | vừa |
| 32 | `decompose_agent/worker.py:182-186` | Port | `@runtime_checkable Worker(Protocol)`: `propose(ctx)` + `decompose(node)`. `ScriptedWorker` + `LocalLLMWorker` implement. | cao |
| 33 | `decompose_agent/worker.py:188-227` | Adapter | `ScriptedWorker` implement `Worker`, deterministic double offline. `LocalLLMWorker` implement same port cho real LLM. | cao |

---

## Đọc bảng thế nào

- **Port** xuất hiện rất nhiều và đều **hẹp** (1-5 method): đây là tín hiệu ISP tốt theo metric Mục 2.6 (method/interface = 2-5).
- Mỗi **Adapter** chỉ implement **một** port → không có refused bequest (`raise NotImplementedError`), trừ `decompose()` của `ScriptedWorker` raise khi script thiếu (đó là test-double có chủ đích, không phải vi phạm contract của port).
- **Client** luôn type-hint port hẹp (`store: VectorStorePort`, `llm: ChatLLM`, `sinks: Iterable[EventSinkPort]`), không cầm "interface tổng".
- Cặp tách điển hình: `EmbedderPort` vs `VectorStorePort` (ca 01), `OrchestratorPort` vs `BrokerPort` (vai O vs Broker), `DelegationPort` (handler) vs `DelegationStorePort` (storage) — đúng nguyên tắc "interface = client view".
