# CATALOG — Mọi occurrence của LSP trong hex_agent

Bảng vét cạn các chỗ LSP (port + ≥2 impl giữ contract, hoặc test chứng minh substitutability) trong
codebase `hex_agent`. Mọi `path:line` đã được mở file kiểm chứng. Đường dẫn tương đối so với
`/Users/uspro/Desktop/namnson/hex_agent`.

> Ghi chú hiệu chỉnh số dòng so với plan (đã mở file xác nhận):
> - `tests/test_supervisor_loop.py`: `isinstance(LangGraphDelegationAgent(...), DelegationPort)` nằm ở
>   **dòng 144-147** (file dài 147 dòng), không phải 237-241.
> - `tests_audit/test_rag_edges_rigor.py`: `isinstance(emb, EmbedderPort)` ở **dòng 95-99**;
>   các test `InMemoryVectorStore` ở **dòng 119-170**; `isinstance(store, VectorStorePort)` cho
>   `QdrantVectorStore` ở **dòng 559-563**, parity health envelope ở **dòng 566**.

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `core/ports.py:19-26` | `ToolPort` Protocol: `name: str`, `execute(request) -> dict`. `@runtime_checkable`. | cao |
| `core/ports.py:32-45` | `DelegationPort` Protocol: `name`, `can_handle(target)`, `run(request, session, sink) -> DelegationResult`. | cao |
| `core/middleware.py:11-22` | `ToolMiddleware` Protocol: `__call__(request, nxt) -> dict`. Có thể short-circuit không gọi `nxt`; thuộc tính `fail_open` tùy chọn. | cao |
| `rag/ports.py:24-28` | `EmbedderPort` Protocol: `dim: int`, `embed(texts) -> list[list[float]]`. `@runtime_checkable`. | cao |
| `rag/ports.py:31-36` | `VectorStorePort` Protocol: `health()`, `delete_by_source()`, `upsert()`, `search()`. `@runtime_checkable`. | cao |
| `supervisor/orchestrator.py:15-18` | `OrchestratorPort` Protocol: `compose_team(...) -> str`, `decide(...) -> str`. Cả hai trả JSON. | cao |
| `supervisor/broker.py:17-21` | `BrokerPort` Protocol: `write_packet(assignment, store_slice) -> ContextPacket`. `@runtime_checkable`. | cao |
| `supervisor/llm.py:52-54` | `ChatLLM` Protocol: `complete(messages: list[dict]) -> str`. `@runtime_checkable`. | cao |
| `toolbox/terminal.py:12-49` | `Terminal` impl `ToolPort`: `name='terminal_run'`, `execute(request) -> dict`. Trả `{ok, returncode, stdout, stderr}` hoặc `{ok:False, error}`. | cao |
| `toolbox/filesystem.py:16-45` | `FsRead`, `FsWrite`, `FsList` mỗi cái impl `ToolPort`: thuộc tính `name`, `execute(request) -> dict`. Nhiều tool swap qua `ToolPort`. | cao |
| `core/registry.py:29-40` | `NullToolPort`: impl interface `ToolPort`, trả `{ok:False, missing_capability}` khi không tìm thấy tool. Fallback giữ contract. | cao |
| `safety/policy.py:105-124` | `SafeToolPort` bọc bất kỳ `ToolPort`: `name`, `execute(request) -> dict`. Decorator: chèn policy chokepoint trước khi gọi tool trong. Giữ contract `ToolPort`. | cao |
| `middleware/condense.py:11-30` | `CondenseResult` impl `ToolMiddleware`: `__call__(request, nxt) -> dict`. Advisory (`fail_open=True`); bỏ qua tool `llm.*`. Sửa envelope kết quả nhưng giữ cấu trúc. | cao |
| `middleware/budget.py:10-23` | `BudgetGuard` impl `ToolMiddleware`: `__call__(request, nxt) -> dict`. Middleware chặn; từ chối lời gọi tool lặp lại. Trả envelope lỗi nhất quán. | cao |
| `middleware/policy.py:9-21` | `PolicyGate` impl `ToolMiddleware`: `__call__(request, nxt) -> dict`. Cổng deny-list; short-circuit nếu tool nằm trong tập deny. Giữ format envelope lỗi. | cao |
| `rag/service.py:15-113` | `RagService` phụ thuộc abstraction `EmbedderPort` + `VectorStorePort`. Không `isinstance`; swap tự do cả `FakeEmbedder`/`FastEmbedEmbedder` lẫn `InMemory`/`Qdrant`. | cao |
| `rag/stores.py:24-56` | `InMemoryVectorStore` impl `VectorStorePort`. Contract: `health()` luôn gọi được, `search()` trả list `Hit` đã sort, `delete_by_source()` idempotent. | cao |
| `rag/embedders.py:33-60` | `FakeEmbedder` và `FastEmbedEmbedder` cùng impl `EmbedderPort`: thuộc tính `.dim`, method `.embed(texts) -> list[list[float]]`. Test xác nhận `isinstance` cho `FastEmbedEmbedder`. | cao |
| `adapters/agents/langgraph_agent.py:21-95` | `LangGraphDelegationAgent` impl `DelegationPort`. Stream progress; trả `DelegationResult` với `(delegation_id, outcome, artifacts, summary)`. | cao |
| `adapters/agents/scripted.py:17-59` | `ScriptedDelegationAgent` impl `DelegationPort` y hệt: cùng interface, cùng contract `DelegationResult`, `outcome='success'`. | cao |
| `supervisor/llm.py:57-91` | `KernelChatLLM` + `LLMOrchestrator` impl `ChatLLM`, `OrchestratorPort`. Tới model qua kernel chokepoint; trả chuỗi JSON. | trung bình |
| `supervisor/llm.py:94-137` | `LLMBroker` impl `BrokerPort`; gọi LLM nhưng guardrail trong code: `source_ids` giao với slice thật (dòng 127-128), size cap (dòng 134), không field scope. | cao |
| `tests_audit/test_core_edges_rigor.py:52-100` | `RecordingMiddleware`: xác nhận Protocol `ToolMiddleware` thỏa được; chứng minh contract `__call__(request, nxt)` qua kernel execution thật (không chỉ chữ ký). | cao |
| `tests_audit/test_rag_edges_rigor.py:61-100` | Test xác nhận `FastEmbedEmbedder.embed()` trả `list[list[float]]`; `dim` probe đúng 1 lần; `isinstance(emb, EmbedderPort)` (dòng 99). | cao |
| `tests_audit/test_rag_edges_rigor.py:119-170` | Test xác nhận `InMemoryVectorStore` thỏa contract `VectorStorePort`: `health()` switchable, `search()` sort/cắt tất định, `delete_by_source()` idempotent. | cao |
| `tests_audit/test_rag_edges_rigor.py:559-566` | Test `isinstance(QdrantVectorStore(...), VectorStorePort)` (559-563); cả hai store chia sẻ cùng key envelope `health()` (566) — chứng minh parity contract. | cao |
| `tests/test_supervisor_loop.py:144-147` | Test xác nhận `isinstance(LangGraphDelegationAgent("agent:general"), DelegationPort)`. Chứng minh tuân thủ cấu trúc; minh họa substitutability trong `TaskLoop`. | cao |
| `tests/test_supervisor_loop.py:39-49` | Test truyền cả orchestrator Scripted lẫn LLM vào `run_task_loop()`; caller (`TaskLoop`) không branch; JSON từ orchestrator chảy vào json-gate bất kể nguồn. | cao |

---

## Nhóm theo port (để thấy tính swappable)

- **`ToolPort`** — `Terminal`, `FsRead/FsWrite/FsList`, `NullToolPort` (fallback), `SafeToolPort` (decorator).
- **`ToolMiddleware`** — `CondenseResult` (advisory), `BudgetGuard` (chặn), `PolicyGate` (deny-list), `RecordingMiddleware` (test).
- **`EmbedderPort`** — `FakeEmbedder` (offline), `FastEmbedEmbedder` (production). → **Case 01**.
- **`VectorStorePort`** — `InMemoryVectorStore` (in-process), `QdrantVectorStore` (gRPC remote). → **Case 02**.
- **`DelegationPort`** — `LangGraphDelegationAgent` (production), `ScriptedDelegationAgent` (test). → **Case 03**.
- **`OrchestratorPort`** — `ScriptedOrchestrator` (S1), `LLMOrchestrator` (S2). → **Case 04**.
- **`BrokerPort`** — `DeterministicBroker` (S1), `LLMBroker` (S2). → **Case 04**.
- **`ChatLLM`** — `KernelChatLLM` (seam tới model qua kernel chokepoint).
