# Kiến trúc hệ thống

Cập nhật: 2026-06-25 · Nguồn: `core/kernel.py:63`, `core/ports.py`, `graph/runtime.py:49-65`

Tài liệu này mô tả các seam (điểm kết nối) và lớp kiến trúc của hệ thống. Để theo dõi một task từ input đến output, xem [runtime-flow.md](./reference/runtime-flow.md). Để biết file nào chứa gì, xem [getting-started.md](./getting-started.md).

## 1. Hình dạng hexagonal / microkernel

Hệ thống tuân thủ mô hình hexagonal: một lõi cứng (microkernel) ở trung tâm (`core/`), xung quanh là các port (seam) nơi adapter (implementation cụ thể) nối vào.

```
┌─────────────────────────────────────────────┐
│  Entry Points (orchestrator.run/resume)     │
│           UI / run_smoke / tests            │
└──────────────┬──────────────────────────────┘
               │
               ↓
        AgentKernel (frozen)
       ┌───────────────────┐
       │ Chokepoint único   │
       │ execute_tool(...)  │
       │ Seam 1: ToolPort   │
       │ Seam 2: ToolMWare  │
       │ Registry + Events  │
       └───────────────────┘
       ↑        ↑        ↑
   LLM.Chat  Tools   Delegation
  (E03.adapt) (E06)  (DelegationPort)
              Safety
              Sandbox
              (E06)
```

**Nguyên lý lõi**: mọi gọi LLM và tool đều qua một cửa duy nhất `AgentKernel.execute_tool` (core/kernel.py:63). Không có đường tắt. Nhờ vậy, observability, safety, envelope và trace ID không bị bypass.

Delegation là **chokepoint riêng**: không phải method của kernel. Điều này tách quả quản lý scope/budget cho đệ quy ra khỏi logic execution của kernel (xem phần 3 dưới đây).

## 2. Bảng seam (port/adapter)

Mỗi seam định nghĩa một protocol: callee không biết implementer là ai. Ứng dụng wire adapter vào lúc khởi động.

| Seam / Protocol | Vị trí | Adapter tiêu chuẩn | Trách vụ |
|---|---|---|---|
| **ToolPort** | `core/ports.py:20` | `safety/SafeToolPort` (E06) | Thực thi một tool theo request |
| **ToolMiddleware** | `core/middleware.py:11` | Policy, Retry, Condense, TimingLog (E02/E06) | Bọc pre/post quanh chokepoint |
| **DelegationPort** | `core/ports.py:32` | `adapters/agents/langgraph.py` | Chạy task con (đại lý) |
| **DelegationStorePort** | `core/ports.py:48` | `delegation/store.py` (in-process) | Lưu trữ tiến trình delegation |
| **DelegationServicePort** | `core/ports.py:65` | `delegation/manager.py` | API cao cấp. `delegate(...)` |
| **EventSinkPort** | `control/ports.py:15` | `control/emitter.py::BusEventSink` | Forward event tới transport (Kafka sau) |
| **EmbedderPort** | `rag/ports.py:25` | `rag/stores_*.py` (fastembed) | Nhúng text thành vector |
| **VectorStorePort** | `rag/ports.py:32` | `rag/stores_qdrant.py` (Qdrant) | Lưu/tìm vector |
| **LLM client** | `llm/adapter.py:53` | OpenAI-compatible HTTP | `call_llm(messages, model, ...)` |

Mỗi seam là một Protocol với `@runtime_checkable`, cho phép duck typing và swap runtime.

## 3. Lớp kiến trúc (10 lớp ↔ directory ↔ epic)

Sắp xếp theo phụ thuộc (ngoài → trong):

| Lớp | Directory | Epic | Trách vụ |
|---|---|---|---|
| Entry & orchestration | `orchestrator/` | E05 | Public `run()/resume()` façade; checkpoint SQLite; task loop |
| Đơn-agent graph | `graph/` | E05 | LangGraph state, nodes, topology; lệnh định tuyến |
| Multi-agent task loop | `supervisor/` | E10 | Agent-O round-based blackboard; delegation policy; judge acceptance |
| Delegation (chokepoint 2) | `delegation/` | E10 | Manager, policy validate, in-process store, scope enforce |
| Delegation adapters | `adapters/` | E10 | Scripted và LangGraph implementation |
| Control plane | `control/` | E21 | RuntimeEvent envelope, EventEmitter, redaction |
| Observability | `observability/` | E04 | EventLogger → JSONL/summary/metrics, inspect CLI |
| Tools & safety (adapter layer) | `toolbox/`, `safety/`, `middleware/` | E06 | SafeToolPort, ToolPolicy, workspace jail, fs/terminal tools |
| Discipline (reusable logic) | `discipline/` | E02 | JSON gate, finish gate, budget, condense |
| LLM adapter | `llm/`, `features/llm_chat.py` | E03 | OpenAI-compatible, JSON-mode, retry, lazy client |
| **Microkernel (chokepoint 1)** | `core/` | E01 | Registry, EventBus, session factory, middleware chaining, freeze |

Lõi (`core/`) **không import** từ bất kỳ lớp nào khác (ngoại trừ `schemas`). Vòng tròn phụ thuộc bị cắt ở seam.

Ứng dụng bootstrap (E01+E02+...+E06 feature load) xảy ra lúc `create_kernel` → `install_configured_features` → `_install_middleware` → freeze kernel trước session đầu.

## 4. Chokepoint 1: AgentKernel.execute_tool (E01)

Hình dạng:

```python
# core/kernel.py:63
def execute_tool(
    self,
    tool_name: str,
    args: dict | None = None,
    *,
    context: ToolCallContext | None = None,
) -> dict[str, Any]:
    # 1. Deep-copy args (không cho tool mutate input của caller)
    request = ToolRequest(name=..., args=copy.deepcopy(args), context=context)
    
    # 2. Publish tool.requested (event)
    self.events.publish("tool.requested", {...lineage..., "args": ...})
    
    # 3. Scope check: allowed_capabilities có chứa tool_name?
    if context and tool_name not in context.allowed_capabilities:
        # → scope_block, publish tool.failed, return
        return CapabilityResult(..., error="...", scope_block=True).as_dict()
    
    # 4. Build middleware onion (outer → inner = reversed registration order)
    # Each middleware is a Protocol: __call__(request, nxt) → dict
    chain = self._wrap(middlewares[0], self._wrap(middlewares[1], ...core...))
    
    # 5. Core: resolve tool → execute → normalize to CapabilityResult
    # Tool không được ném exception (try/except bọc executor)
    envelope = CapabilityResult.from_raw(tool.execute(request), kind=..., idempotent=...)
    
    # 6. Publish tool.completed | tool.failed
    self.events.publish("tool.completed|failed", {...lineage..., "ok": ..., "error": ...})
    
    return envelope.as_dict()
```

**Bất biến giữ nguyên:**
- Không có đường tắt: mọi `llm.chat` call cũng đi qua `execute_tool` (xem `features/llm_chat.py:11`).
- Argument được deep-copy → tool không mutate.
- Middleware chaining qua `_wrap()` (tránh late-binding closure bug, xem `core/kernel.py:24`).
- Try/except bọc executor → tool exception không làm sập kernel (return `error-final`).
- Event được publish ở điểm chuẩn hóa: trước, quanh giữa, và sau logic thực thi.

## 5. Chokepoint 2: DelegationManager.delegate (E10)

Tách khỏi kernel. Luồng:

```python
# delegation/manager.py:63
def delegate(
    parent_session: KernelSession,
    target: str,
    spec: DelegationSpec,
    policy: DelegationPolicy | None = None,
) -> DelegationResult:
    # 1. Policy validate (depth, budget, scope, token)
    policy.validate(parent_session, target, spec)
    
    # 2. Create child session: scope con ⊆ scope cha
    child = SessionFactory.create_child(
        parent=parent_session,
        name=delegation_id,
        allowed_capabilities=spec.allowed_capabilities
    )
    
    # 3. Forward handler (adapter qua DelegationPort)
    handler.run(request, child_session, progress_sink)
    
    # 4. Persist progress → publish
```

**Khác với kernel.** Không vào registry; scope là constraint không optional; không middleware; state là `DelegationProgress/Result` (không `CapabilityResult`).

Lý do tách riêng: delegation có semantic khác (nó là RPC, có request/response, không execute-and-return-dict). Nếu nhét vào kernel, registry sẽ có delegation handler ở cạnh fs-read. Nhầm lẫn.

## 6. Session & scope (E04)

`KernelSession` là **per-run state**. Kernel là **shared** (frozen). Mỗi session:

- Có `session_id`, `parent_session_id`, `allowed_capabilities` (subset cha).
- Lưu giữ message history, last result, task state.
- `SessionFactory.create_child()` là constructor duy nhất cho child (enforce scope shrink, `create_child` line 163 trong `core/session.py`).

**Freeze trước session đầu.** Điều này ngăn config/registry bị sửa khi có session chạy (state rò qua các run).

## 7. Topology đơn-agent (E05)

Từ `graph/runtime.py:49-65`:

```
START
  ↓
guard (check budget)
  ├→ fail (budget exceeded)
  ↓
agent (llm.chat + parse_action)
  ├→ tool (execute + guard same-tool)
  ├→ delegate (delegation RPC)
  ├→ finish (check_finish gate)
  ├→ guard (quay lại)
  ├→ fail (parse lỗi, không khôi phục)
  ↓
tool/delegate → (route back)
  ├→ guard
  ├→ fail
  ↓
finish (check_finish)
  ├→ guard (blocked, emit graph.finish_blocked)
  ├→ END (success)
  ↓
fail
  ├→ END
```

Mỗi node là hàm. Routing qua state field `route` (string verb). Conditional edges xử lý routing.

**Đóng lifecycle đúng một lần:**
- Nếu `finish` thành công → `session.complete_task()` → status = `completed`.
- Nếu `fail` → `session.fail_task()` → status = `failed`.
- Mỗi task chỉ đóng một lần (vòng lặp không quay lại `finish` sau khi gọi `complete_task`).

## 8. Persistence & resume (E05)

**SQLite là sự thật duy nhất.** Checkpoint JSON chỉ là projection cho UI.

```
orchestrator.run()
  → build graph (session-bound)
  → LangGraph stream() → SQLite (langgraph.sqlite)
  → save AgentState after each step
  
orchestrator.resume(run_id)
  → read SQLite via get_state (truth)
  → restore KernelSession
  → stream(None) tiếp tục
  → nếu đã completed/failed, trả outcome
```

File checkpoint:
- `langgraph.sqlite` (thật): lưu bởi `orchestrator/checkpoint.py::open_checkpointer`.
- `checkpoint.json` (UI projection): ghi sau mỗi transition (`save_graph_projection`).

**Lưu ý.** `resume()` không bao giờ đọc JSON (ngoại trừ nhánh migrate legacy run cũ).

## 9. Observability (E04)

Kernel chỉ publish; chuyên viên subscribe. Flow:

```
AgentKernel.execute_tool
  → events.publish("tool.requested|completed|failed", {...})
  
EventLogger.attach_to_bus(kernel.events)
  → subscribe(*topics)
  → transform (add timestamp, index)
  → write var/agent_runs/<run_id>/events.jsonl
  
EventLogger.finalize(run_id)
  → aggregate counters → summary.json
```

**Lineage:**
- `run_id`: task ID từ orchestrator.
- `task_id`: từ `ToolCallContext.event_fields()` (accept_task gắn nó vào context).
- `session_id`, `parent_session_id`, `delegation_id`, `actor_id`: phục vụ truy vết.

Tất cả `tool.*` event có lineage, cho phép khôi phục trace gọi từ events.jsonl.

## 10. Control plane (E21, partial)

**Trạng thái:** Phase A (contracts) + Phase B B1 (EventEmitter canonical path) shipped. Transport, command-lifecycle, approval gate, reliability PENDING.

Khi `EventEmitter` được inject vào `SupervisorContext` (opt-in, default None):

```
supervisor/graph.py (loop.* events)
  → EventEmitter.emit_event(RuntimeEvent envelope)
    → gate (permission check)
    → seq (assign monotonic sequence)
    → redact (mask secret via Redactor)
    → fan-out (EventSinkPort → BusEventSink → EventLogger)
    
Nếu không: supervisor dùng raw kernel bus.publish
```

`RuntimeEvent` (control/events.py:113) có `ui_payload=None` cho đến khi Redactor xử lý.

Config registries:
- `runtime_event_types.yaml`: event allowlist (visibility, durable, redact + apply_at).
- `runtime_command_types.yaml`: command allowlist (apply_at, requires_permission).

**Hiện tại:** không wired vào UI (ui/server.py không import control/). Supervisor emitter là opt-in (default None).

## 11. Các file thiết yếu (theo epic)

| Epic | File chính | Dòng cốt lõi |
|---|---|---|
| E01 | `core/kernel.py` | `execute_tool:63`, `freeze:48`, `use:57` |
| E01 | `core/ports.py` | `ToolPort:20`, `DelegationPort:32` |
| E02 | `discipline/json_gate.py` | `parse_json_object:64`, `parse_action:91` |
| E02 | `discipline/finish_gate.py` | `check_finish:15` |
| E03 | `llm/adapter.py` | `call_llm:53`, `_is_transient:40` |
| E04 | `observability/event_log.py` | `attach_to_bus:102`, `events.jsonl:60` |
| E05 | `graph/state.py` | `AgentState:12`, `encode_session_state` |
| E05 | `graph/runtime.py` | `build_agent_graph:31`, topology `:49-65` |
| E05 | `orchestrator/loop.py` | `run:89`, `resume:213` |
| E06 | `safety/sandbox.py` | `resolve_in_workspace:18` |
| E06 | `safety/policy.py` | `ToolPolicy.check:88`, `SafeToolPort:105` |
| E07/E09 | `roles/spec.py` | `allowed_tools:53` (cycle-break) |
| E08 | `rag/ports.py` | `VectorStorePort:32`, `EmbedderPort:25` |
| E10 | `supervisor/loop.py` | `run_task_loop:70` |
| E10 | `delegation/manager.py` | `delegate:63` |
| E21 | `control/emitter.py` | `EventEmitter.emit_event:53` |

## 12. Tóm tắt mối quan hệ

**Từ entry point đến outcome:**

1. **Orchestrator** (`run()/resume()`) → build graph + session bound.
2. **Graph** (node + conditional edges) → route based on LLM verb.
3. **Kernel** (execute_tool) ← chokepoint duy nhất cho tool/llm.
4. **Middleware** → timing, policy, retry, condense (order: timing → policy → retry → condense → core).
5. **Tool adapter** (ToolPort) → SafeToolPort bọc → workspace jail → fs/terminal.
6. **Delegation** (separate seam) → policy validate → child session → handler.run.
7. **Observability** → EventLogger subscribe → JSONL + summary.
8. **Control plane** (opt-in) → EventEmitter → redact → EventSinkPort → transport.
9. **Persistence** → SQLite truth + JSON projection.

**Crosscut:** freeze kernel → session factory enforce scope → BudgetGuard ở graph nodes (không ở middleware).

---

Để tìm hiểu thêm:
- [runtime-flow.md](./reference/runtime-flow.md): luồng chạy từng node.
- [known-risks.md](./reference/known-risks.md): file dễ vỡ và rủi ro.
- [getting-started.md](./getting-started.md): cách đọc repo khi nó lớn dần.
- Kiến trúc map (plans/reports/): danh sách chi tiết từng module.
