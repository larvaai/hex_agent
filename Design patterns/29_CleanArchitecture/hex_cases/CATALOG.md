# CATALOG — Mọi occurrence của Clean Architecture trong hex_agent

Bảng vét cạn các điểm mà pattern **Clean Architecture** (port owned by inner, adapter implement, dependency một chiều inward, composition root) xuất hiện trong codebase `hex_agent`.
Cột `path:line` là đường dẫn TƯƠNG ĐỐI so với root `hex_agent/`; mỗi dòng đã được mở kiểm chứng.
Độ rõ: **cao** = ví dụ sách giáo khoa của pattern; **trung bình** = mang tinh thần pattern nhưng trộn thêm trách nhiệm khác.

## Flagship (có case study riêng)

| path:line | Mô tả | Độ rõ |
|-----------|-------|-------|
| `core/ports.py:32-45` | `DelegationPort` Protocol — output port owned by core. Adapter implement nó; core không bao giờ import adapter. (Xem case 01) | cao |
| `adapters/agents/scripted.py:17-59` | `ScriptedDelegationAgent` implement `DelegationPort`. Chỉ import từ `core.ports`/`core.schemas`/`core.session`. Chi tiết cụ thể sống ở đây; core nguyên vẹn. (Case 01) | cao |
| `delegation/bootstrap.py:13-24` | Composition root: nơi duy nhất import cả core lẫn adapter. Wire `LangGraphDelegationAgent` vào `DelegationManager`. (Case 01) | cao |
| `rag/ports.py:24-36` | `EmbedderPort` & `VectorStorePort` Protocols. Domain (`Chunk`, `Hit`, `RagConfig`) tách khỏi adapter seam. (Case 02) | cao |
| `rag/stores_qdrant.py:32-49` | `QdrantVectorStore` adapter implement `VectorStorePort`; lazy import `qdrant_client` (line 43). Core không thấy import này. (Case 02) | cao |
| `rag/feature.py:27-42` | `build_service()`: lazy-import adapter qdrant chỉ khi `backend='qdrant'`. Config quyết định adapter nào được wire. (Case 02) | cao |
| `core/schemas.py:11-26, 132-198, 201-253` | Frozen dataclass cho mọi boundary: `TaskEnvelope`, `DelegationSpec`, `DelegationRequest`, `DelegationResult`... Pure data, không I/O. (Case 03) | cao |
| `core/session.py:49-102` | `KernelSession`: identity bất biến + state store mutable. Domain không biết HTTP/file/LLM. (Case 03) | cao |
| `core/kernel.py:76-225` | `AgentKernel`: orchestrator thuần (dispatch tool, publish event). Không phụ thuộc flask/sqlite/llm client. (Case 03) | cao |
| `core/bootstrap.py:56-66` | `build_kernel()`: composition root thấy nhiều vòng — gọi `install_configured_features` + `_install_middleware`. (Case 04) | cao |
| `features/llm_chat.py:17-37` | `LLMChatTool` adapter implement port tool; `install()` đăng ký vào registry. Feature = use case + adapter + port đóng gói. (Case 04) | cao |
| `features/loader.py:10-25` | Dynamic feature installer: lazy-load module từ config, gọi `install(kernel)`. (Case 04) | cao |

## Catalog mở rộng (occurrence khác cùng pattern)

| path:line | Mô tả | Độ rõ |
|-----------|-------|-------|
| `core/ports.py:48-77` | `DelegationStorePort`, `DelegationServicePort` Protocol — thêm các output port owned by core cho store/service. | cao |
| `core/registry.py:43-122` | `CapabilityRegistry`: registry của application; `NullToolPort` fallback (7-30 vùng descriptor). Dispatcher thuần, không I/O. | cao |
| `core/events.py:11-32` | `EventBus`: trừu tượng pub/sub, zero framework. Adapter subscribe, core publish. | cao |
| `control/ports.py:14-22` | `EventSinkPort`: output port của control plane. Adapter swap ở đây (JSONL → Kafka tương lai). | cao |
| `supervisor/orchestrator.py:15-19` | `OrchestratorPort`: protocol cho quyết định của AI agent. `ScriptedOrchestrator` (offline) vs llm-backed; cùng port. | cao |
| `supervisor/broker.py:17-21` | `BrokerPort`: writer context-package. `DeterministicBroker` (offline) vs llm.chat-backed. IoC qua protocol. | cao |
| `llm/adapter.py:25-119` | Adapter LLM OpenAI-compatible. Lazy module client (25-32), retry/backoff, injectable. Bọc chi tiết vendor. | cao |
| `rag/service.py:15-113` | Use case RAG: `ingest`/`search` qua `EmbedderPort` & `VectorStorePort`; không bao giờ import qdrant trực tiếp. | trung bình |
| `middleware/policy.py:9-21` | `PolicyGate`: tầng middleware lọc tool request. Wire qua composition `kernel.use(PolicyGate(...))`. Logic policy thuần, không I/O. | trung bình |
| `graph/nodes.py:1-55` | Graph nodes (`guard_node`, `agent_node`...): hàm thuần trên `AgentState`; mọi external action vẫn đi qua `execute_tool`. | trung bình |
| `delegation/store.py:9-56` | `InMemoryDelegationStore` implement `DelegationStorePort`. Bản in-memory; production swap DB/event-store cùng port. | cao |
| `delegation/registry.py:9-40` | `DelegationRegistry`: register & resolve handler theo port `DelegationPort`; freeze sau init. Registry thuần, không I/O. | cao |
| `delegation/policy.py:8-32` | `DelegationPolicyEngine`: validate policy (max_steps, max_depth, scope). Business rule thuần. | cao |
| `delegation/manager.py:19-192` | `DelegationManager` use case: orchestrate policy + child session + progress + result, chỉ gọi port (`DelegationStorePort`, `DelegationPort`). | cao |
| `adapters/agents/__init__.py:1-4` | Export package adapter: `ScriptedDelegationAgent`, `LangGraphDelegationAgent` — cả hai implement `DelegationPort`. | cao |
| `control/event_registry.py:22-55` | Event schema registry; validate `RuntimeEvent`. Data validation thuần, không framework. | trung bình |
| `tests/test_delegation.py:14-40` | Test cho thấy `DelegationManager` testable không cần adapter thật: `_manager()` wire fake store + `ScriptedDelegationAgent`. Zero framework import. | cao |
