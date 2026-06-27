# CATALOG — Mọi occurrence của Hexagonal (Ports & Adapters) trong `hex_agent`

Bảng vét cạn các điểm pattern Hexagonal xuất hiện trong codebase. Mỗi dòng đã được **mở file kiểm chứng**
số dòng vào ngày soạn (path tương đối so với root `/Users/uspro/Desktop/namnson/hex_agent`).
Cột "độ rõ" = mức độ thể hiện pattern rõ ràng (cao / trung bình).

> Ghi chú hiệu chỉnh so với plan gốc:
> - DelegationManager (lõi orchestration, inject `registry`+`sessions`+`store`) thật sự được **định nghĩa** ở
>   `delegation/manager.py:19-32`, không phải `delegation/__init__.py` (file đó chỉ 7 dòng, chỉ re-export).
> - Sink `EventSinkPort` tự chế trong `tools/gen_t1_fixture.py` tên thật là **`_Collect`** (dòng 30-37), không phải `RecordingSink`.

---

## A. Ba flagship (có case con chi tiết)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `rag/ports.py:24-36` | `EmbedderPort` + `VectorStorePort` — driven port, chỉ `Protocol`, không impl. → [Case 01](./01_rag_service_ports_adapters/) | cao |
| `rag/service.py:15-40` | `RagService.__init__` nhận `store: VectorStorePort` + `embedder: EmbedderPort` qua DI; health-gate. | cao |
| `rag/service.py:78-113` | `search()` — lõi gọi RA `embedder.embed` rồi `store.search`, không biết adapter cụ thể. | cao |
| `rag/stores.py:24-57` | `InMemoryVectorStore` — driven adapter offline (cosine in-memory), dùng test/dev. | cao |
| `rag/stores_qdrant.py:32-148` | `QdrantVectorStore` — driven adapter production qua qdrant-client; `health()` không ném. | cao |
| `rag/feature.py:27-42` | `build_service()` — composition root RAG, chọn adapter theo `config['backend']`, lazy import Qdrant. | cao |
| `core/ports.py:32-45` | `DelegationPort` — driving port: `name`+`can_handle()`+`run()`. → [Case 02](./02_delegation_agents_pattern/) | cao |
| `adapters/agents/scripted.py:17-59` | `ScriptedDelegationAgent` — driving adapter deterministic cho test. | cao |
| `adapters/agents/langgraph_agent.py:21-95` | `LangGraphDelegationAgent` — driving adapter production, stream LangGraph, emit artifact per step. | cao |
| `delegation/bootstrap.py:13-24` | `create_delegation_service()` — composition root: nơi duy nhất import `LangGraphDelegationAgent`. | cao |
| `control/ports.py:14-22` | `EventSinkPort` — driven port một method `emit`; docstring nêu lộ trình v1 Bus → T2 Kafka. → [Case 03](./03_event_sink_hexagon/) | cao |
| `control/emitter.py:28-36` | `BusEventSink` — driven adapter v1, adapt in-process `EventBus`. | cao |
| `control/emitter.py:39-90` | `EventEmitter` — lõi: validate → seq → redact → fan-out; chỉ nhận `list[EventSinkPort]`. | cao |

---

## B. Catalog vét cạn (các occurrence còn lại)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `core/ports.py:19-26` | `ToolPort` (Protocol) — seam mọi tool cụ thể implement; "Concrete behavior lives behind this port". | cao |
| `core/ports.py:48-62` | `DelegationStorePort` (Protocol) — driven port lưu progress/result của delegation. | cao |
| `core/ports.py:65-77` | `DelegationServicePort` (Protocol) — driving port của dịch vụ delegation (available_targets/delegate). | cao |
| `core/kernel.py:76-98` | `AgentKernel` + `freeze()` — lõi hệ thống; "Concrete behavior lives behind ports/adapters in the registry". | cao |
| `core/registry.py:29-41` | `NullToolPort` — adapter fallback cho tool thiếu, implement `ToolPort`, trả lỗi graceful. | cao |
| `core/registry.py:43-122` | `CapabilityRegistry` — `resolve_tool()` trả `ToolResolution(executor, feature, descriptor)`; không hard-code adapter. | cao |
| `core/bootstrap.py:56-71` | `build_kernel()` / `create_kernel()` — composition root: load config, build bus + registry, install feature + middleware. | cao |
| `core/middleware.py:11-23` | `ToolMiddleware` (Protocol) — seam middleware quanh `execute_tool`; lõi chỉ biết Protocol (Decorator + Hexagonal). | cao |
| `control/emitter.py:93-95` | `bus_emitter()` — factory nhỏ, trả `EventEmitter([BusEventSink(bus)])` (composition root cho event sink). | cao |
| `delegation/manager.py:19-32` | `DelegationManager.__init__` — lõi orchestration, inject `registry`+`sessions`+`store` (đều port/interface). | cao |
| `delegation/manager.py:119-160` | `delegate()` — `registry.resolve(target)` rồi `handler.run(...)` qua driving port. | cao |
| `delegation/store.py:9-56` | `InMemoryDelegationStore` — implement `DelegationStorePort`; comment "a durable adapter can implement the same port later". | cao |
| `delegation/__init__.py:1-7` | Re-export `DelegationManager`/`DelegationRegistry`/`InMemoryDelegationStore` — public interface lõi. | trung bình |
| `rag/feature.py:109-122` | `install(kernel)` — wire `RagService` (sau port) thành 3 tool đăng ký vào registry. | cao |
| `rag/__init__.py:10-20` | Export `Chunk`/`EmbedderPort`/`VectorStorePort`/`RagService` — public port interface, adapter để private. | trung bình |
| `supervisor/orchestrator.py:15-39` | `OrchestratorPort` (driving) + `ScriptedOrchestrator` (adapter canned); S2 swap LLM-backed, cùng JSON. | cao |
| `supervisor/broker.py:17-55` | `BrokerPort` (driving) + `DeterministicBroker` (adapter offline); S2 sẽ có LLM adapter cùng port. | cao |
| `tests/test_delegation.py:14-23` | `_manager()` wire `DelegationManager` với `ScriptedDelegationAgent`+`InMemoryDelegationStore` — lõi test offline. | cao |
| `tests/conftest.py:31-52` | `RecordingDelegationAgent` (adapter test ghi lại scope/context) — composition pattern qua fixture. | trung bình |
| `tools/gen_t1_fixture.py:30-42` | `_Collect` — một `EventSinkPort` fake + `EventEmitter([sink])`; chứng minh port inversion + swap adapter. | cao |
| `llm/adapter.py:1-50` | LLM adapter — không Protocol nhưng `_get_client()` lazy + injectable + retry; façade qua OpenAI-compatible. Semi-Hexagonal. | trung bình |
