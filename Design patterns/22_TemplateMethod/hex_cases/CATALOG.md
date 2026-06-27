# CATALOG — Mọi occurrence của Template Method trong hex_agent

> Vét cạn từ bước *discover*. Các flagship (đã dựng thành case) đứng đầu; phần còn lại
> là catalog đầy đủ. Mọi `path:line` đã được mở lại để xác nhận trước khi ghi.
> Độ rõ: **cao** = pattern hiện rõ, dạy được ngay; **trung bình** = nhận ra được nhưng
> trộn với nhiều logic khác; **thấp** = chỉ thoáng dạng pattern.

## Flagships (đã dựng case)

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `decompose_agent/worker.py:182-301` | **Worker Protocol**: `Worker(Protocol)` (182-185) khai báo khung hai bước `propose`/`decompose`; `ScriptedWorker` (188-227) và `LocalLLMWorker` (230-301) là hai hiện thực — test double tất định vs production gọi LLM + retry. Cùng chữ ký, nội tạng khác hẳn. → Case 01. | cao |
| `graph/runtime.py:31-66` | **build_agent_graph()**: dựng skeleton cố định START→guard→agent→{tool\|delegate\|finish}→END qua `StateGraph`; `_route` (27-28) chọn cạnh. StateGraph là "skeleton enforcer". → Case 02. | cao |
| `graph/nodes.py:40-255` | Mỗi node (`guard_node` 40-48, `agent_node` 51-103, `tool_node` 106-138, `delegation_node` 141-199, `finish_node` 202-240, `fail_node` 243-255) là hook cùng hợp đồng: restore → xử lý chuyên biệt → emit → return update có `route`. Shared: `_restore_session`/`_emit` (20-37). → Case 02. | cao |

## Catalog đầy đủ

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `middleware/budget.py:15-23` | `BudgetGuard.__call__` là template: record tool call → check `same_tool_exceeded` → (optional) gọi hook `on_block` → rẽ nhánh: return error hoặc gọi `nxt(request)`. Khung "trước → gọi nxt". | cao |
| `middleware/policy.py:15-21` | `PolicyGate.__call__`: check deny-set → (optional) `on_block` → return error hoặc `nxt(request)`. Cùng khung BudgetGuard, guard logic khác. | cao |
| `middleware/retry.py:27-33` | `Retry.__call__`: gọi `nxt(request)` → lặp khi kết quả không ok và còn lượt và `_retryable(env)` (14-20) → gọi lại `nxt`. Khung vòng-retry cố định; hook là `_retryable` quyết định có tiếp không. | trung bình |
| `middleware/condense.py:20-30` | `CondenseResult.__call__`: luôn gọi `nxt(request)` → bỏ qua nếu là `llm.*` → (optional) condense `data` → (optional) hook `on_condense`. Khung "execute → post-process"; `fail_open=True` (12). | cao |
| `middleware/timing.py:16-26` | `TimingLog.__call__`: ghi `t0` → gọi `nxt(request)` → đo elapsed → (optional) hook `sink` với metrics → return env. Khung đo thời gian quanh `nxt`; `fail_open=True` (11). | cao |
| `core/kernel.py:192-225` | `execute_tool` dựng chuỗi middleware: `handler = core`; với mỗi mw (đảo ngược) `handler = _wrap(mw, handler, ...)`. Chuỗi này là skeleton — mỗi middleware cùng chữ ký `__call__(request, nxt)`, bọc `nxt` bằng logic trước/sau. | thấp |
| `orchestrator/loop.py:93-147` | `run()` theo các pha cố định: tạo/nhận session → `new_agent_state` → `build_agent_graph` → `_stream(...)` → `_sync_budget` → `_outcome`. `_stream` (69-90) là skeleton lặp `graph.stream()` với xử lý lỗi nhất quán (checkpoint khi exception, khôi phục final_state). | trung bình |
| `supervisor/loop.py:148-201` | `_drive()` là template vòng task: `while not terminal` → check round limit → `o_decide` → judge → record progress → checkpoint. Thứ tự cố định; `decision.decision` chọn hook (finished/need_tool/continue/blocked/failed). | trung bình |
| `drag_from_zero/dragzero/orchestrator.py:186-271` | `_process_one()`: restore agent → budget gate → start task → hook `pre_plan` (204) → vòng ReAct/tool (`_react_until_terminal` 220-250) → quyết định cuối (`_handle_terminal` 252-271) → hook `pre_delegate` (259) → spawn hoặc complete. Khung cố định với hook ở các điểm then chốt. | trung bình |
| `drag_from_zero/dragzero/orchestrator.py:145-152` | `run_until_idle()` (145-148): `while _ready and not _halted` → `_process_one(_ready.popleft())`. `run()` (150-152) bọc: `start()` → `run_until_idle()`. Khung ép xử lý FIFO; hook nằm trong `_process_one`. | cao |
| `decompose_agent/solve.py:80-122` | `solve_leaf()`: init budget/attempts → `while not exhausted` → `assemble_4cell` → hook `worker.propose` → parse/handle → `_run_action` → `run_checks` → check gate. Khung loop-attempt-check; hook là `worker.propose`, `_run_action`, `run_checks`. → liên quan Case 01. | trung bình |
| `decompose_agent/solve.py:132-184` | `_decompose()`: check cache → `while True` → record step → hook `worker.decompose` → parse/error → `accept_decomposition` → (optional) cache + commit. Khung decompose cố định; hook là `worker.decompose` và `accept_decomposition`. → liên quan Case 01. | trung bình |
| `drag_from_zero/dragzero/adapters/tools_fs.py:44-95` | `ReadFileTool`/`WriteFileTool`/`ListDirTool`/`RunCommandTool` cùng skeleton: thuộc tính `name` + `run(args, sandbox) -> ToolResult`. Hợp đồng giống hệt, hiện thực khác. Dùng structural Protocol (`Tool`) thay vì base class. | cao |

## Ghi chú về số dòng

Một số mục trong plan discover ghi khoảng dòng tương đối (vd retry "23-33",
kernel "150-250"). Bảng trên đã **thu hẹp về đúng phương thức/đoạn** sau khi mở lại
file thật:
- `middleware/retry.py`: `_retryable` ở 14-20, `__call__` ở 27-33.
- `core/kernel.py`: đoạn dựng chuỗi middleware (`for mw in reversed(self._middlewares): handler = _wrap(...)`) ở 192-194, trọn vòng đời `execute_tool` quanh 192-225.
- `drag_from_zero/dragzero/orchestrator.py`: `_process_one` bắt đầu ở 186; hook `pre_plan` ở 204, phần `_handle_terminal` chứa hook `pre_delegate` ở 259.
