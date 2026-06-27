# CATALOG — Mọi occurrence của OCP trong hex_agent

Bảng vét cạn các chỗ áp dụng Open/Closed Principle trong codebase hex_agent. Mỗi dòng đã được
mở file kiểm chứng `path:line` (số dòng chỉnh khớp với mã thật tại thời điểm viết). "Độ rõ" =
mức độ một chỗ minh họa OCP rõ ràng đến đâu (cao / vừa / trung).

Gốc tham chiếu: `/Users/uspro/Desktop/namnson/hex_agent/<path>`.

## Flagship (có case con chi tiết)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `core/ports.py:19-27` | `ToolPort` Protocol — seam mọi tool implement: `name` + `execute(request) -> dict`. Structural typing (Protocol) cho phép duck-typing, không cần kế thừa. → Case 01 | cao |
| `core/registry.py:43-122` | `CapabilityRegistry` — lưu tools + descriptors; `resolve_tool()` trả executor theo name string; fallback `NullToolPort` cho tool thiếu. Không if/switch trên loại tool. → Case 01 | cao |
| `features/llm_chat.py:17-37` | `LLMChatTool` implements `ToolPort`; `install(kernel)` đăng ký qua `register_tools()`. Thêm tool mới = class mới + install, 0 sửa registry/kernel. → Case 01 | cao |
| `rag/feature.py:53-121` | `_RagTool` base + `RagHealthTool`/`RagIngestTool`/`RagSearchTool`; `install()` đăng ký 3 tool qua registry. Feature plugin pattern. → Case 01 | cao |
| `core/middleware.py:11-22` | `ToolMiddleware` Protocol — `__call__(request, nxt) -> dict`; thuộc tính tùy chọn `fail_open` cho middleware advisory. → Case 02 | cao |
| `core/kernel.py:49-73` | `_wrap()` — decorator factory tạo closure cho 1 middleware quanh handler kế tiếp; nhánh fail-open dùng `_LatchedNext`. → Case 02 | cao |
| `core/kernel.py:100-104` | `AgentKernel.use(middleware)` — append vào `_middlewares`; thêm middleware = `kernel.use(NewMiddleware())`, không sửa execute_tool. → Case 02 | cao |
| `decompose_agent/worker.py:182-185` | `Worker` Protocol — `propose(ctx)` + `decompose(node, ...)`. Contract cấu trúc, mỗi impl phải có 2 method. → Case 03 | cao |
| `decompose_agent/worker.py:188-227` | `ScriptedWorker` — deterministic double, test-friendly; `propose()` tra script, `decompose()` dùng decompose_scripts. → Case 03 | cao |
| `decompose_agent/worker.py:230-301` | `LocalLLMWorker` — LLM-backed; `propose()`/`decompose()` gọi `_chat()` (retry/backoff), client injectable. Khác hẳn ScriptedWorker, cùng 2 method. → Case 03 | cao |

## Ports & abstractions khác (catalog)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `core/ports.py:29-77` | `DelegationPort`, `DelegationStorePort`, `DelegationServicePort` — 3 Protocol cho delegation system; cho phép nhiều implementation cho delegation orchestration. | cao |
| `core/registry.py:29-40` | `NullToolPort` — fallback giữ kernel sống khi tool thiếu; trả lỗi có cấu trúc thay vì raise. Một phần của trục OCP (graceful degradation). | cao |
| `rag/ports.py:24-37` | `EmbedderPort` (`embed`) + `VectorStorePort` (`health`/`delete_by_source`/`upsert`/`search`). Thêm embedder hay vector store mới = class mới, `RagService` không đổi. | cao |
| `rag/embedders.py:33-60` | `FakeEmbedder` (deterministic, offline) vs `FastEmbedEmbedder` (fastembed, lazy import). Cùng interface; `InMemoryVectorStore` phụ thuộc embedder generic. | cao |
| `rag/stores.py:24-57` | `InMemoryVectorStore` implements `VectorStorePort` (health/delete/upsert/search); `QdrantVectorStore` cũng impl cùng interface. RagService phụ thuộc abstraction, không hardcode Qdrant. | cao |
| `rag/feature.py:27-42` | `build_service(config)` chọn backend theo `config['backend']` string: `'memory'` → InMemory + Fake; `'qdrant'` → Qdrant + FastEmbed. Config-driven dispatch ở tầng feature (không if/elif ở caller). | cao |
| `features/example_echo.py:1-26` | `EchoTool` = `ToolPort` impl đơn giản nhất; `install()` = extension point pattern (FeatureDescriptor + class + install). | cao |
| `supervisor/llm.py:52-91` | `ChatLLM` Protocol (`complete`). `KernelChatLLM` impl (qua `execute_tool`); `LLMOrchestrator`/`LLMBroker` phụ thuộc `ChatLLM` qua DI. Thêm mock/remote ChatLLM không sửa Orchestrator/Broker. | cao |
| `supervisor/orchestrator.py:15-39` | `OrchestratorPort` (`compose_team`, `decide`). `ScriptedOrchestrator` = test impl, `LLMOrchestrator` = prod impl. Supervisor loop phụ thuộc port, không hardcode. | cao |
| `control/ports.py:14-22` | `EventSinkPort` (`emit`). Comment nêu rõ planned extension: v1 `BusEventSink`, T2 Kafka adapter cùng `emit` — thay transport mà không sửa emitter. | cao |
| `llm/adapter.py:72-119` | `call_llm(messages, *, model, ..., client=None)` — client injectable (None → lazy `_get_client()`). Adapter pattern: retry/backoff/fallback (downgrade json→text) độc lập. | trung |
| `core/bootstrap.py:28-66` | `_install_middleware` + `build_kernel` — composition-over-configuration: `kernel.use(...)` theo config, rồi install features. Mỗi feature/middleware tự chứa. | vừa |
| `control/event_registry.py:40-61` | `EventTypeRegistry` — registry pattern xác nhận `event_type` hợp lệ; data-driven (load từ YAML). Thêm event type = thêm dòng YAML, không sửa code. | vừa |
| `control/command_registry.py:36-60` | `CommandTypeRegistry` — tương tự `EventTypeRegistry`. Data-driven extension; thêm command type = thêm entry YAML. | vừa |
