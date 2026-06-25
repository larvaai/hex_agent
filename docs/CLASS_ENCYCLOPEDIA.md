# CLASS ENCYCLOPEDIA — toàn bộ class production của `core_agent`

> Snapshot source: **2026-06-25**. Coverage: **99 khai báo class top-level** trong 85 file Python
> ngoài `tests/` và `var/`. Các class giả lập nằm cục bộ trong test không được tính vì không phải
> API/runtime production.
>
> Ký hiệu trạng thái: **D** = đường chạy mặc định; **O** = optional feature/runtime; **L** = library
> đã test nhưng chưa compose vào UI; **C** = compatibility/internal.

## 1. Mô hình sở hữu

```text
AgentKernel (shared, frozen)
  ├─ CapabilityRegistry
  ├─ EventBus
  ├─ immutable config
  └─ middleware pipeline

KernelSession (per task/run)
  ├─ SessionIdentity
  ├─ StateStore
  ├─ allowed_capabilities
  └─ lifecycle active -> completed|failed

Compiled graph (per active/restored session)
  └─ AgentState (serializable checkpoint state)
```

Kernel không sở hữu mutable run state. `SessionFactory` là nơi duy nhất tạo/restore root và child
session. Node graph giữ session bằng closure; checkpoint chỉ giữ primitives.

## 2. `core.schemas` — data contracts

| Class | Kind | Vai trò và API chính | Tạo bởi / dùng bởi | Trạng thái và invariant |
|---|---|---|---|---|
| `TaskEnvelope` | frozen dataclass | User request + `context`, `metadata`, `task_id`; `as_dict/from_dict` | `SessionFactory.create_root/create_child`, legacy resume; nằm trong `StateStore` | D · được codec graph đặc cách khi checkpoint |
| `ToolRequest` | frozen dataclass | `name`, `args`, optional `ToolCallContext`, `request_id` | `AgentKernel.execute_tool`; mọi `ToolPort.execute` nhận | D · context không được trộn vào args |
| `ToolCallContext` | frozen dataclass | Lineage + scope; `event_fields()` | `KernelSession.call_context`; kernel đọc | D · `allowed_capabilities=None` nghĩa là không áp session scope |
| `CapabilityResult` | frozen dataclass | Envelope chuẩn; `from_raw`, `as_dict` | Kernel chuẩn hóa mọi executor/middleware result | D · sáu key chuẩn: ok/capability/feature/data/error/metadata |
| `FeatureDescriptor` | frozen dataclass | Metadata feature + capability names; `as_dict` | Hằng `FEATURE` của feature modules; `CapabilityRegistry` lưu | D/O · mô tả feature, không enforce policy |
| `DelegationSpec` | frozen dataclass | Objective, input context, output schema, constraints; `from_dict/as_dict` | Graph delegate node, ContextPacket, caller delegation | D/L · payload công việc, không mang quyền |
| `DelegationPolicy` | frozen dataclass | `max_steps`, `max_depth`, capability scope; `from_dict/as_dict` | Delegate node, Supervisor, PolicyEngine | D/L · scope cuối phải là subset của parent |
| `DelegationRequest` | frozen dataclass | Request đã gán ID, parent IDs, target, spec, policy; `as_dict` | `DelegationManager` | D · store/adapter nhận cùng object |
| `ArtifactEnvelope` | frozen dataclass | Artifact ID/kind/schema/payload; `as_dict` | Delegation adapters | D/L · frozen wrapper nhưng `payload` vẫn là dict mutable |
| `DelegationProgress` | frozen dataclass | Ordered progress event + artifact; `as_dict` | Adapter → progress sink/store/event bus | D/L · sequence liên tiếp, event_id idempotent |
| `DelegationResult` | frozen dataclass | Outcome, merged artifacts, summary/error; `as_dict` | Adapter/manager → graph/Supervisor | D/L · IDs phải khớp request và parent |

## 3. `core.ports` và `core.middleware` — structural contracts

| Class | Contract | Implementations/consumers | Trạng thái |
|---|---|---|---|
| `ToolPort` | `.name`; `execute(ToolRequest) -> dict` | Null, Echo, LLM, RAG, Fs*, Terminal, SafeToolPort, callable adapter | D |
| `DelegationPort` | `can_handle(target)`; `run(request, child_session, progress_sink)` | `LangGraphDelegationAgent`, `ScriptedDelegationAgent` | D |
| `DelegationStorePort` | `start`, `append_progress`, `finish`, `progress`, `result` | `InMemoryDelegationStore` | D |
| `DelegationServicePort` | `available_targets`, `delegate` | `DelegationManager`; graph/orchestrator nhận qua injection | D |
| `ToolMiddleware` | `__call__(request, next_handler) -> envelope` | BudgetGuard, CondenseResult, PolicyGate, Retry, TimingLog | O |

Các Protocol dùng structural typing; implementation không cần kế thừa. `runtime_checkable` chỉ có ở
Tool/Delegation ports phù hợp với các test `isinstance`.

## 4. `core.registry` — capability catalog

| Class | Vai trò và API | Tạo bởi / dùng bởi | Trạng thái và lưu ý |
|---|---|---|---|
| `ToolDescriptor` | Metadata frozen: `kind`, `idempotent`, `risk` | `register_tool(s)` tạo; nằm trong `ToolResolution`; kernel stamp vào envelope | D mới · Retry dùng để tránh lặp non-idempotent effect |
| `ToolResolution` | NamedTuple `(executor, feature, descriptor)` | `CapabilityRegistry.resolve_tool` → kernel | D |
| `NullToolPort` | Missing-tool executor trả structured failure | Registry giữ một instance và resolve khi miss | D · chỉ tới được khi call không bị session scope chặn trước |
| `CapabilityRegistry` | Register/freeze/resolve/list feature và tool | `build_kernel` tạo; feature installers ghi; kernel đọc | D · exact > fallback > null; freeze khi root session đầu tiên tạo |

`CapabilityRegistry` giữ executor, feature mapping và descriptor mapping riêng. `list_tools()` hiện
chỉ project `name/feature`, chưa trả descriptor.

## 5. `core.events`, `core.kernel`, `core.session`, `core.state`

| Class | Vai trò và API chính | Phụ thuộc / call-site | Trạng thái và invariant |
|---|---|---|---|
| `EventBus` | Thread-safe `subscribe/publish`; deep-copy payload cho từng subscriber | Kernel/Supervisor phát; EventLogger nghe | D · observer exception bị cô lập; chưa có unsubscribe |
| `AgentKernel` | Shared capability runtime; `freeze`, `use`, `execute_tool`, `describe_capabilities` | Bootstrap tạo; mọi session tham chiếu | D · không sở hữu run state; executor exception thành `kernel_error` |
| `SessionIdentity` | Frozen lineage: session/run/task/agent/parent/delegation/depth; `as_dict/from_dict` | SessionFactory tạo; graph checkpoint/restore | D |
| `KernelSession` | Per-task state, scope và lifecycle; `call_context`, `execute_tool`, `complete_task`, `fail_task` | Graph, delegation, Supervisor/KernelChatLLM | D · lifecycle chỉ đóng một lần; closed session không gọi tool |
| `SessionFactory` | `create_root`, `create_child`, `restore` | Orchestrator, DelegationManager, resume | D · freeze kernel; root scope ⊆ registry, child scope ⊆ parent |
| `StateStore` | Mutable key/value state per session; deep-copy `as_dict/snapshot/restore` | SessionFactory tạo; graph sync với `AgentState` | D · restore thay wholesale; serialization do graph codec chịu trách nhiệm |

## 6. `discipline` — loop/output controls

| Class | Vai trò và API | Dùng bởi | Trạng thái |
|---|---|---|---|
| `Budget` | Step, parse-error, same-tool counters; `record_*`, `*_exceeded`, `tool_key` | Single graph, child graph, Supervisor parse retry, BudgetGuard | D/L · parse error không tiêu step |
| `JsonGateError` | Parse/schema error có `stage` và `candidate` | JSON gate raise; agent/Supervisor catch | D/L |

Glue functions cùng tầng: `parse_json_object`, `parse_action`, `build_retry_message`, `condense`,
`check_finish`.

## 7. `features` — registered executors

| Class | Tool/capability | Tạo bởi / dùng bởi | Trạng thái |
|---|---|---|---|
| `EchoTool` | `echo`; trả lại args | `features.example_echo.install` | D · smoke/example |
| `LLMChatTool` | `llm.chat`; gọi OpenAI-compatible adapter | `features.llm_chat.install`; graph và Supervisor gọi qua session | D · injected client hỗ trợ test; transport error hiện được adapter mã hóa thành JSON text |

`features.loader` không có class: nó import module được bật rồi gọi `install(kernel)` trước khi
kernel freeze.

## 8. `middleware` — wrappers quanh kernel core handler

| Class | Hành vi | Trạng thái và invariant |
|---|---|---|
| `BudgetGuard` | Đếm repeated `(tool,args)`, short-circuit bằng `budget_block` | O · phải tạo per-run, không wire thành shared middleware mặc định |
| `CondenseResult` | Condense `env.data`; bỏ qua `llm.*` | O · mutate envelope sau inner call |
| `PolicyGate` | Deny exact tool names trước executor | O · `policy_block` không được Retry lặp lại |
| `Retry` | Gọi lại inner handler khi `ok=false` nếu `_retryable`; bỏ policy block và non-idempotent effect | O · phụ thuộc metadata kernel stamp từ `ToolDescriptor` |
| `TimingLog` | Đo wall time và gửi record tới optional sink | O · đăng ký outermost để đo cả chain |

Bootstrap order khi bật đầy đủ: `TimingLog -> PolicyGate -> Retry -> CondenseResult -> core`.

## 9. `safety` và `toolbox`

| Class | Vai trò/API | Tạo bởi / dùng bởi | Trạng thái và invariant |
|---|---|---|---|
| `SandboxError` | Path vượt workspace | `resolve_in_workspace` raise; Fs*/RAG catch | D/O |
| `PolicyDecision` | Frozen gate result: allowed/reason/code/risk | `classify_terminal`, `ToolPolicy` → SafeToolPort | D |
| `ToolPolicy` | Phân loại terminal/git mutation; optional `repair_mode` chặn whole-file write | Một instance dùng chung trong toolbox installer | D · policy argv, không phải OS sandbox; repair mode chưa được runtime tự chuyển |
| `SafeToolPort` | Policy wrapper trước concrete executor | Toolbox bọc Fs*/Terminal rồi register | D |
| `FsRead` | `fs_read`: UTF-8 file trong workspace jail | SafeToolPort → kernel | D |
| `FsWrite` | `fs_write`: mkdir parent + UTF-8 write | SafeToolPort → kernel | D · field `bytes` hiện là character count |
| `FsList` | `fs_list`: directory/file listing | SafeToolPort → kernel | D |
| `Terminal` | `terminal_run`: subprocess argv, no shell, timeout 1..30s, cwd workspace | SafeToolPort → kernel | D · cwd không chặn process truy cập ngoài workspace |

## 10. `delegation` và `adapters.agents`

| Class | Vai trò/API | Tạo bởi / dùng bởi | Trạng thái và invariant |
|---|---|---|---|
| `DelegationPolicyEngine` | Validate step/depth/scope; trả active policy | DelegationManager | D |
| `DelegationRegistry` | Thread-safe register/freeze/resolve target; reject duplicate/ambiguous | Delegation bootstrap/manager | D |
| `InMemoryDelegationStore` | Ordered, idempotent progress + final result | Default delegation service | D · process-local, không resume được |
| `DelegationManager` | Application chokepoint: validate → start → child → adapter → progress → result | Graph delegate node, Supervisor | D · store progress trước emit; parent giữ active |
| `LangGraphDelegationAgent` | Concrete child agent chạy cùng single-agent graph với InMemorySaver | Default target `agent:general` | D · sequential, non-durable, recursive delegation tắt |
| `ScriptedDelegationAgent` | Deterministic artifact producer | Tests/local architecture usage | C |

## 11. `graph`, `orchestrator`, `observability`

| Class | Vai trò/API | Tạo bởi / dùng bởi | Trạng thái và invariant |
|---|---|---|---|
| `AgentState` | `TypedDict` schema v2 cho LangGraph | `new_agent_state`; mọi graph node/checkpoint | D · chỉ primitives/encoded session state |
| `_CallableLLMTool` | Adapter từ callback `llm_call` cũ sang `llm.chat` ToolPort | `graph.runtime.run_agent` | C |
| `Checkpoint` | Stable JSON read-model/legacy schema; `to_json/from_json/from_graph_state` | Projection UI, migration legacy | D/C · không phải state truth của modern resume |
| `EventLogger` | Thread-safe JSONL events, summary và metrics; `emit/count/finish` | UI, compat graph, smoke; `attach_to_bus` | D · lock trong process; raw event payload được ghi nguyên dạng |

Các graph nodes là functions, không phải class: `guard_node`, `agent_node`, `tool_node`,
`delegation_node`, `finish_node`, `fail_node`. `build_agent_graph()` bind session/service vào node
bằng `partial`.

## 12. `rag` — optional retrieval subsystem

| Class | Kind/vai trò | Tạo bởi / dùng bởi | Trạng thái và invariant |
|---|---|---|---|
| `Chunk` | Frozen vector-store input: source/index/text/vector | RagService → VectorStorePort | D/O |
| `Hit` | Frozen search output: source/index/text/score | VectorStorePort → RagService | D/O |
| `EmbedderPort` | `dim`, `embed(texts)` protocol | Fake/FastEmbed implement; RagService nhận | D/O |
| `VectorStorePort` | health/delete/upsert/search protocol | Memory/Qdrant implement; RagService nhận | D/O |
| `RagConfig` | Frozen collection/model/chunk/search/Qdrant config; `from_dict` | `build_service` | D/O |
| `FakeEmbedder` | Deterministic hashed bag-of-words | Default memory backend/tests | D |
| `FastEmbedEmbedder` | Lazy `fastembed.TextEmbedding` adapter | Qdrant branch | O · dependency optional không nằm base install |
| `InMemoryVectorStore` | Health-switchable cosine store | Default memory backend/tests | D · process-local, không thread-safe |
| `QdrantVectorStore` | Production Qdrant adapter; lazy collection, deterministic IDs, health-safe failure | Qdrant backend + optional integration tests | O · lazy `qdrant-client`, cần local/remote Qdrant |
| `RagService` | Health-gated ingest/search; workspace jail; port-only logic | RAG tools | D/O |
| `_RagTool` | Base giữ `name`, service và semantic event emitter | Ba RAG tool subclasses | D/internal |
| `RagHealthTool` | `rag_health` → service + `rag.health` event | RAG feature installer | D |
| `RagIngestTool` | `rag_ingest(path)` + `rag.ingest` event | RAG feature installer | D |
| `RagSearchTool` | `rag_search(query, top_k, threshold)` + `rag.search` event | RAG feature installer | D |

Memory backend là default self-contained. `backend=qdrant` dùng production adapter + fastembed qua
optional extras `[rag]`; integration tests skip khi Qdrant không reachable.

## 13. `skills`

| Class | Vai trò/API | Tạo bởi / dùng bởi | Trạng thái |
|---|---|---|---|
| `SkillSpec` | Frozen role-agnostic contract: triggers, allowed/forbidden tools, Steps/Report | `parse_skill`, SkillRegistry, RoleSpec | L |
| `SkillRegistry` | Load/register/get/render/lint/union tools | Role registry/Agent prompt, tests | L · `contract` ẩn Steps/Report; `full` hiện đầy đủ |

Skill parser đọc YAML frontmatter và markdown headings. Skill không biết role; role là nơi hợp nhất
tool declarations và áp forbidden-wins.

## 14. `roles`

| Class | Vai trò/API | Tạo bởi / dùng bởi | Trạng thái và invariant |
|---|---|---|---|
| `TestOwnership` | Frozen separation-of-duties marker | Nằm trong RoleSpec; Agent.guard_finish | L |
| `RoleView` | Frozen projection cho Supervisor: agent_id/role/prompt/default_scope | AgentRegistry.role_view/list_roles | L |
| `RoleSpec` | Canonical role config; `allowed_tools(skills, core_tools)` | YAML loader, AgentRegistry | L · skill forbidden wins trên explicit/core/skill union |
| `Agent` | Role đã bind skill/lens; tool/finish guards + scoped prompt | AgentRegistry.build_agent | L · guard chưa được graph/Supervisor gọi tự động |
| `LensSpec` | Frozen review viewpoint + tool hints + output schema; `render` | LensRegistry, Agent prompt | L |
| `LensRegistry` | Register/load/get/render lens YAML | AgentRegistry composition | L |
| `AgentRegistry` | Canonical role store; build Agent; project RoleView | Có thể inject vào SupervisorContext | L |

Lưu ý: `LensSpec.allowed_tools/forbidden_tools` hiện chỉ được render vào prompt, không tham gia
`RoleSpec.allowed_tools()` hay `Agent.guard_tool_call()`.

## 15. `supervisor.contracts`

| Class | Vai trò/API | Luồng sử dụng | Trạng thái |
|---|---|---|---|
| `AgentSelection` | Agent ID + lý do chọn | `SessionPlan` | L |
| `SessionPlan` | Team đã chọn; `agent_ids/as_dict` | Agent O compose → Blackboard | L |
| `AgentAssignment` | Agent objective/scope-of-work/capability list | Agent O decision → Broker/worker | L |
| `OrchestratorDecision` | Decision verb + worker/tool/acceptance/final payload | `parse_decision` → TaskLoop driver | L |
| `ContextPacket` | Briefing + provenance + expected schema; `to_spec` | Broker → DelegationManager | L · cố ý không có capability scope |

## 16. `supervisor.state`

| Class | Vai trò/API | Luồng sử dụng | Trạng thái |
|---|---|---|---|
| `TaskLoopStatus` | Enum created/team/discussion/wait/review/terminal | TaskLoop state/driver | L |
| `AcceptanceCheck` | Criterion + status/evidence; `is_satisfied`, codec | Acceptance judge | L · passed cần evidence_ids không rỗng và có thật |
| `AgentTurn` | Round/agent/packet/summary/artifact IDs; codec | `run_round` append | L |
| `TaskLoopState` | Mutable Blackboard; artifacts, turns, AC, tool results; helpers | Toàn Supervisor loop; codec functions | L · serializable nhưng chưa checkpoint tự động |

## 17. `supervisor.broker`, `supervisor.llm`, `supervisor.orchestrator`, `supervisor.graph`

| Class | Vai trò/API | Tạo bởi / dùng bởi | Trạng thái và invariant |
|---|---|---|---|
| `BrokerPort` | `write_packet(assignment, store_slice)` protocol | DeterministicBroker/LLMBroker; SupervisorContext | L |
| `DeterministicBroker` | Briefing offline có char cap + source IDs | Tests/local TaskLoop | L |
| `ChatLLM` | `complete(messages) -> str` protocol | KernelChatLLM/Fake tests; LLM agents nhận | L |
| `KernelChatLLM` | Chat adapter qua `KernelSession.execute_tool("llm.chat")` | LLMOrchestrator/LLMBroker | L · giữ chokepoint và lineage |
| `LLMOrchestrator` | Agent O compose team/decide bằng model | TaskLoop | L |
| `LLMBroker` | Context packet bằng model; lọc source IDs, cap briefing | TaskLoop | L · code không thể chứng minh nội dung briefing thực sự grounded |
| `OrchestratorPort` | `compose_team`, `decide` protocol | LLM/Scripted implementations | L |
| `ScriptedOrchestrator` | Queue JSON deterministic; tự block khi hết script | Acceptance tests | C/L |
| `SupervisorContext` | Runtime dependency bundle + role catalog + event/checkpoint helpers | Mọi supervisor node function | L |
| `SqliteTaskLoopStore` | SQLite latest-state store; `save/load` encoded Blackboard | Optional `run_task_loop/resume_task_loop` checkpoint store | L · save sau completed turn/round/terminal; không lưu current decision/Budget/repeat history |

Supervisor nodes và driver là functions. `run_task_loop()` hiện không gọi
`supervisor_session.complete_task/fail_task`; optional `SqliteTaskLoopStore` có resume nhưng driver
không phải LangGraph và UI chưa khởi tạo nó.

## 18. `ui.server`

| Class | Vai trò/API | Tạo bởi / dùng bởi | Trạng thái và invariant |
|---|---|---|---|
| `RunJob` | Dataclass job memory: prompt/system/status/timestamps/error | RunController | D · mất khi process restart; artifacts vẫn trên disk |
| `RunController` | Queue/run tối đa N workers; `start/get/close` | AgentUIServer/handler | D · mỗi job tạo kernel/logger/delegation service riêng |
| `AgentUIHandler` | HTTP API + static + SSE | ThreadingHTTPServer tạo mỗi request | D · local console, không có auth |
| `AgentUIServer` | `ThreadingHTTPServer` giữ shared RunController | `ui.server.main` | D · daemon request threads, default bind 127.0.0.1 |

Frontend `app.js` không khai báo JavaScript class; nó dùng một state object và các render/event
functions. Vì vậy bách khoa này không bỏ sót frontend class nào.

## 19. Ai tạo ai ở runtime mặc định

```text
RunController
  ├─ EventLogger
  ├─ create_kernel
  │    ├─ CapabilityRegistry
  │    │    ├─ ToolDescriptor per registered capability
  │    │    ├─ EchoTool
  │    │    ├─ LLMChatTool
  │    │    └─ SafeToolPort -> FsRead/FsWrite/FsList/Terminal
  │    ├─ EventBus
  │    └─ AgentKernel
  ├─ create_delegation_service
  │    ├─ DelegationRegistry -> LangGraphDelegationAgent
  │    ├─ InMemoryDelegationStore
  │    ├─ DelegationPolicyEngine
  │    └─ DelegationManager
  └─ orchestrator.run
       ├─ SessionFactory -> SessionIdentity + StateStore + KernelSession
       ├─ AgentState + Budget
       ├─ Checkpoint/SqliteSaver
       └─ graph nodes
            ├─ ToolRequest -> ToolResolution -> CapabilityResult
            └─ optional delegation -> child KernelSession -> child AgentState
```

## 20. Invariant theo class boundary

1. `AgentKernel` shared và frozen; `KernelSession` mutable và per-task.
2. `ToolCallContext` mang quyền/lineage; tool args chỉ mang business input.
3. `CapabilityRegistry` là nơi duy nhất map capability name → executor/feature/descriptor.
4. `CapabilityResult` là shape duy nhất đi lên graph/Supervisor.
5. `AgentState` không giữ runtime object; `StateStore` snapshot phải encode được.
6. `DelegationManager` là chokepoint duy nhất cho parent→child application call.
7. `ContextPacket` không được mang scope; scope do policy/assignment quyết định.
8. `Checkpoint` JSON là read model; LangGraph SQLite mới là parent resume truth.
9. `Agent`, roles, lenses và skills hiện là library policy layer; đừng giả định chúng đã bảo vệ
   default UI runtime cho tới khi composition/enforcement được wire.
