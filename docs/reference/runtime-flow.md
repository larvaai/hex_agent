# RUNTIME_FLOW — một task chạy từ input → output như thế nào

> Trạng thái: **mô tả hiện thực đang chạy** (không phải spec). Khớp với code tại thời điểm
> viết — đã verify trực tiếp trên `orchestrator/loop.py`, `graph/runtime.py`, `graph/nodes.py`,
> `core/kernel.py`. Nếu sửa các file đó, cập nhật lại tài liệu này.
>
> Đây là tầng "RUNTIME_FLOW" trong `../getting-started.md`. Muốn biết *file nào là gì* xem
> `MAP.md`; muốn biết *tại sao* xem `../spec/`.

## 1. Ranh giới (boundary)

Chỉ có **một** runtime agent. LangGraph chỉ lo điều phối (orchestration); `core/` không import
LangGraph và vẫn là microkernel framework-agnostic.

Hai chokepoint, tách biệt có chủ đích:

1. **`AgentKernel.execute_tool`** (`core/kernel.py`) — *mọi* hành động LLM **và** tool đều đi qua đây.
   LLM cũng là một capability (`llm.chat`), không có đường tắt.
2. **`DelegationServicePort.delegate`** (inject vào graph, hiện thực ở `delegation/manager.py`) —
   delegation đi đường riêng, **không** phải method của kernel. Đây là lý do có node `delegate`
   riêng trong graph.

```mermaid
flowchart LR
    caller["UI / caller / run_smoke"] --> facade["orchestrator.run / resume"]
    facade --> graph["compiled StateGraph (1 substrate)"]
    graph --> agent["agent node"]
    graph --> tool["tool node"]
    graph --> delegate["delegate node"]
    graph --> finish["finish / fail nodes"]
    agent --> kernel["AgentKernel.execute_tool (llm.chat + tools)"]
    tool --> kernel
    delegate --> delport["DelegationServicePort.delegate (chokepoint riêng)"]
    finish --> lifecycle["session.complete_task / fail_task"]
    graph --> sqlite[("var/agent_runs/&lt;run_id&gt;/langgraph.sqlite")]
```

## 2. Entrypoints

| Đường vào | File | Ghi chú |
|---|---|---|
| `run()` / `resume()` | `orchestrator/loop.py` | Facade công khai, ổn định. Dùng cái này. |
| `run_agent(...)` | `graph/runtime.py` | Facade tương thích ngược cho test cũ (`llm_call=`). Cùng một graph. |
| Local UI | `ui/server.py` | Gọi facade, hiển thị run/state/log realtime. |
| Smoke (no LLM/network) | `run_smoke.py` | In `CORE_AGENT_SMOKE_OK`. |

`run_id` ↔ LangGraph `thread_id`; `task_id` là correlation ID cho lifecycle + tool event.

## 3. Topology graph (sự thật, từ `graph/runtime.py::build_agent_graph`)

```text
START -> guard
guard    -> agent | fail
agent    -> tool | delegate | finish | guard | fail
tool     -> guard | fail
delegate -> guard | fail
finish   -> guard (bị chặn) | END
fail     -> END
```

> Lưu ý: node `delegate` và cạnh `finish -> guard` là thật trong code. Sơ đồ cũ trong
> `architecture/LANGGRAPH.md` (đã xóa) thiếu cả hai — đừng dùng lại nó.

## 4. Vòng đời một step (từng node, `graph/nodes.py`)

1. **`guard`** — chặn trước mỗi lần gọi LLM nếu `budget.steps >= max_steps` → `fail`
   (emit `graph.budget_blocked`). Ngược lại → `agent`.
2. **`agent`** — gọi `session.execute_tool("llm.chat", {messages, model, json_mode})`, rồi
   `parse_action` (JSON gate của `discipline/`) lấy **đúng một** action:
   - parse lỗi → `record_parse_error`; quá ngưỡng → `fail`, chưa quá → quay `guard` kèm
     retry message.
   - hợp lệ → `record_step`, route theo verb: `tool` → tool, `delegate` → delegate,
     `final` → finish, verb lạ → quay `guard`.
3. **`tool`** — chặn same-tool budget (`same_tool_exceeded` → `fail`), rồi
   `session.execute_tool(name, args)`, nối envelope JSON vào messages → `guard`.
4. **`delegate`** — gọi `delegation_service.delegate(session, target, spec, policy)` (chokepoint
   riêng). Không cấu hình delegation hoặc spec sai → `fail`. Thành công → nối `DELEGATION_RESULT`
   vào messages → `guard`.
5. **`finish`** — áp **finish gate** dùng chung (`check_finish`): nếu chưa đạt (vd: đã đổi code mà
   chưa validate) → quay `guard` kèm lý do (emit `graph.finish_blocked`); nếu đạt →
   `session.complete_task(final)`, status `completed`, → END.
6. **`fail`** — `session.fail_task(reason, steps, parse_errors)`, status `failed`, → END.
   Cùng một lifecycle với run thành công.

## 5. Bên trong chokepoint kernel (`core/kernel.py::execute_tool`)

Thứ tự cho **mỗi** call (cả `llm.chat` lẫn tool thường):

```text
publish tool.requested  (lineage: run_id/task_id/session_id/parent_session_id/delegation_id/actor_id + args)
  -> scope check: name ∉ context.allowed_capabilities  => block "outside session scope" + tool.failed
  -> middleware chain (đăng ký order = ngoài -> trong; bọc reversed quanh core)
       core: registry.resolve_tool -> executor.execute -> chuẩn hóa thành CapabilityResult envelope
             (exception của tool KHÔNG bao giờ làm sập kernel -> kernel_error)
  -> publish tool.completed | tool.failed
```

Middleware cross-cutting (`middleware/`): timing → policy (deny-list) → budget → retry → condense,
v.v. Safety của toolbox còn một lớp `SafeToolPort` + workspace jail (`safety/`).

> ⚠️ Rủi ro đã biết: `tool.requested` hiện ghi **raw args** vào `events.jsonl` — secret/PII trong
> args có thể bị log. Mục §12 (redaction) trong `MCP_TOOLS.md` nêu cách xử lý trước khi bật write tool.

## 6. State & persistence

- **`AgentState`** (`graph/state.py`) là state điều phối, **chỉ chứa giá trị serializable**:
  task/run identity, messages, bộ đếm discipline, last action, outcome, và một snapshot **đã encode**
  của `session.state`. Service runtime được bắt lúc compile node, **không bao giờ** vào checkpoint.
- **Checkpoint thật = SQLite**: `var/agent_runs/<run_id>/langgraph.sqlite` (mở qua
  `orchestrator/checkpoint.py::open_checkpointer`). `resume()` đọc từ đây.
- **`checkpoint.json` chỉ là projection cho UI**, ghi sau mỗi transition (`save_graph_projection`).
  Resume **không** đọc nó — trừ một lần migrate run cũ tạo trước thời LangGraph (`_legacy_state`).
- Tạo tác mỗi run dưới `var/agent_runs/<run_id>/`: `events.jsonl`, `summary.json`,
  `langgraph.sqlite`, `checkpoint.json`. `var/` được `.gitignore`.

## 7. Resume (`orchestrator/loop.py::resume`)

```text
có langgraph.sqlite?
  không -> thử migrate legacy JSON checkpoint (_legacy_state) -> nếu là run cũ, chạy tiếp trên graph mới
  có    -> đọc SQLite (truth) -> restore KernelSession -> nếu status=running & còn node kế -> stream tiếp
                                                       -> ngược lại trả outcome đã có
```

## 8. Cách tự kiểm chứng nhanh

```bash
python run_smoke.py                              # CORE_AGENT_SMOKE_OK
python -m pytest -q                              # phải xanh hết
python -m observability.inspect summary latest   # xem run gần nhất
python -m observability.inspect events latest    # xem chuỗi event qua chokepoint
```
