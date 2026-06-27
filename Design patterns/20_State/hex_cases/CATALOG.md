# CATALOG — Mọi nơi xuất hiện State pattern (và biến thể) trong hex_agent

Bảng vét cạn các occurrence liên quan tới State pattern, từ bước discover. Ba dòng độ rõ
**cao** đã được tách thành case con (`01_`, `02_`, `03_`). Phần còn lại là các occurrence
biên — có yếu tố trạng thái nhưng không (hoặc chỉ một phần) là máy trạng thái lái-hành-vi.

> Mọi `path:line` dưới đây đã được mở lại trong `/Users/uspro/Desktop/namnson/hex_agent/`
> để xác nhận. Một mục trong plan trỏ `orchestrator/loop.py` cho `_route`; vị trí thật của
> `_route` là `graph/runtime.py:27` (và các cập nhật `route` ở `graph/nodes.py`) — đã sửa
> cho khớp ở bảng này.
>
> Lần kiểm định gần nhất còn sửa thêm: (a) các `path:line` của case 01 (`node.py`,
> `solve.py`) đã trôi vài dòng so với bản gốc hiện tại — đã cập nhật lại đúng vị trí
> (`VALID_STATUSES` ở `node.py:28`, guard status ở `127-128`; `solve_reduce` ở `204-224`,
> `_close_done_parents` ở `229-253`, `solve()` ở `258-304`); (b) class fake O trong
> `supervisor/orchestrator.py:21-39` tên thật là `ScriptedOrchestrator` (không phải `FakeO`).

## Flagship — đã thành case con (độ rõ: cao)

| path:line | mô tả | độ rõ | case |
|---|---|---|---|
| `decompose_agent/node.py:28, 127-128` | `VALID_STATUSES` (tập 5 state) + guard `status` ở `__post_init__`; `Node` frozen, transition qua `dataclasses.replace`. | cao | [01](./01_task_decomposition_navigator/) |
| `decompose_agent/tree.py:31-32, 43-51` | `Tree.set_status()` đóng gói transition; `next_node()` cursor chọn node `pending` có deps `done`. | cao | [01](./01_task_decomposition_navigator/) |
| `decompose_agent/solve.py:80-121, 204-224, 229-253, 258-304` | `solve_leaf/reduce` đổi status; `_close_done_parents` cascade `decomposed→done`; `solve()` driver — behavior đổi theo `outcome.status`. | cao | [01](./01_task_decomposition_navigator/) |
| `supervisor/state.py:14-25, 84, 105-111` | `TaskLoopStatus` enum 8 state + `TERMINAL`; `status` field; `is_terminal`; `acceptance_snapshot`. | cao | [02](./02_supervisor_taskloop_state_machine/) |
| `supervisor/graph.py:102, 211, 227, 256` | Transition trong các node graph: `→TEAM_SELECTED / IN_DISCUSSION / WAITING_TOOL / REVIEWING_AC`. | cao | [02](./02_supervisor_taskloop_state_machine/) |
| `supervisor/loop.py:148-201, 204-208` | `_drive()` Context orchestrator: route `decision.decision` tới handler; `_terminate()` set state terminal. | cao | [02](./02_supervisor_taskloop_state_machine/) |
| `ui/ide/session.py:48-50, 109-112, 118-129, 131-133` | `run_status` (idle/running/finished/failed) + `Condition`; `set_status`/`try_begin_run` (guard nguyên tử)/`snapshot_status`. | cao | [03](./03_ide_session_run_lifecycle/) |
| `ui/ide/runner.py:80-88, 90-121, 159-206` | `cancel()` (chỉ khi running); `start()` claim nguyên tử + spawn thread; `_run`/`_finish_failed`/`_finish_cancelled` set status. | cao | [03](./03_ide_session_run_lifecycle/) |

## Occurrence biên (không tách case)

| path:line | mô tả | độ rõ |
|---|---|---|
| `graph/state.py:36-37, 94, 97` | `AgentState.status` ('running' + final) + `new_agent_state()` khởi tạo. Không phải máy trạng thái: `status` là **output**, không lái hành vi. | thấp |
| `core/session.py:60-61, 87-98` | `KernelSession.is_active` kiểm tra `current_task`; `complete_task()` đóng phiên (`_closed=True`). Vòng đời task (active→completed) nhưng behavior ít đổi theo state — thiên về dữ liệu. | thấp |
| `decompose_agent/gates.py:213-228` | `run_checks()` đọc child statuses (`all_children_done`) để quyết verdict, **nhưng không transition** — gate là observer của state, không phải actor máy trạng thái. | vừa |
| `ui/server.py:236, 243, 254, 259` | `_update()` đặt run status (starting/running/failed/...). Là báo cáo ra client, không dùng để branch logic executor. | thấp |
| `decompose_agent/store.py:84` | `commit` flip parent thành `decomposed` qua `replace(parent, status="decomposed")` — tham gia transition nhưng không phải actor chính (Navigator mới là chủ). | vừa |
| `supervisor/orchestrator.py:21-39` | `ScriptedOrchestrator` (fake O): `decision.decision` ('finished'/'need_tool'/'continue'/'blocked'/'failed') lái transition của `TaskLoopState`, nhưng O **không sở hữu** state — `_drive` mới là Context. | vừa |
| `control/checkpoint.py:32, 42-66` | `RuntimeCheckpoint.status` ('waiting'→terminal) với `with_status` + guard re-resolve. Có guard transition nhưng là metadata của checkpoint, không lái-hành-vi runtime. | thấp |
| `graph/runtime.py:27-28, 50-64` + `graph/nodes.py:47-96` | `route` field ('guard'/'agent'/'tool'/'delegate'/'finish'/'fail') lái conditional edges của LangGraph qua `_route`. Là routing đồ thị gắn chặt LangGraph, không phải máy trạng thái tổng quát. | vừa |

### Ghi chú độ rõ
- **cao** = đủ cả ba: tập state hữu hạn rõ ràng, hành vi đổi theo state (không if/elif rải rác), transition có guard.
- **vừa** = có tham gia transition/đọc state nhưng không sở hữu máy trạng thái, hoặc gắn chặt khung (LangGraph).
- **thấp** = `status` chủ yếu là dữ liệu/output báo cáo, không lái nhánh hành vi.
