# Case 02 — Event Projection: fold `loop.*` event thành `TaskLoopSnapshot`

> Flagship: `event_projection_snapshot`
> Distill từ: `control/snapshot.py`, `supervisor/graph.py`

---

## 1. Bối cảnh trong hex_agent

Bài học gốc có sticky **GREEN = read model** (mục 1.3, 2.4): một view/dashboard *derive* ra từ event, KHÔNG phải nguồn sự thật. Invariant số 5 của Event Storming: mỗi bounded context có ≥ 1 read model.

hex_agent hiện thực đúng triết lý này trong `control/snapshot.py`. `TaskLoopSnapshot` là *projection*: nó được `build_snapshot` gập (fold) ra từ chuỗi `loop.*` event mà supervisor đã emit, để UI Graph/Inspector render. Docstring đầu file nói rõ (`control/snapshot.py:3`): "This is a *projection*, not state". UI không bao giờ mutate snapshot; nó render snapshot.

Sự thật nằm ở event, không ở projection. Vế business logic emit event được thấy rõ trong `supervisor/graph.py`:
- `compose_team` emit `loop.team_composed` (`supervisor/graph.py:103`)
- `o_decide` emit `loop.decision` (`supervisor/graph.py:122`)
- `run_round` emit `loop.turn` (`supervisor/graph.py:209`)
- `run_tool` emit `loop.tool` (`supervisor/graph.py:226`)

Hệ quả cốt lõi của event sourcing: **replay cùng chuỗi event luôn cho ra cùng snapshot**. Đó là cách Event Storming đảm bảo nhất quán — qua event bất biến + projection idempotent.

---

## 2. Trích đoạn code thật

`build_snapshot` fold tuyến tính, order-sensitive (`control/snapshot.py:189-198`):

```python
def build_snapshot(
    events: Iterable[RuntimeEvent | dict[str, Any]], *, session_id: str
) -> TaskLoopSnapshot:
    """Fold a sequence of loop.* events into a TaskLoopSnapshot (S21.9).

    Status derivation per the plan: an agent is ``done`` once it has a ``loop.turn``,
    ``running`` if it is in the most-recent decision's ``next_agent_calls`` and has no turn
    yet, ``waiting`` if a checkpoint references it, else ``pending``. The fold is linear and
    order-sensitive, exactly like the real event stream.
    """
```

Luật derive status — đúng tinh thần "view là hàm của event" (`control/snapshot.py:339-352`):

```python
running = {c["agent_id"] for c in latest_calls} - turned
agents = tuple(
    AgentView(
        agent_id=aid,
        role=meta[aid]["role"],
        status=("done" if aid in turned else "waiting" if aid in waiting else "running" if aid in running else "pending"),
        ...
    )
    for aid in order
)
```

Business logic emit event như một fact sau khi đổi state (`supervisor/graph.py:99-104`):

```python
state.selected_agents = list(ids)
art_id = _next_id("session_plan", state)
state.add_artifact(art_id, {"kind": "session_plan", **plan.as_dict()})
state.status = TaskLoopStatus.TEAM_SELECTED.value
ctx.emit("loop.team_composed", {"selected": list(state.selected_agents)})
```

Policy map event → session status, terminal không bị ghi đè (`control/snapshot.py:140-149`):

```python
_STATUS_BY_EVENT = {
    "loop.team_composed": "team_selected",
    "loop.decision": "in_discussion",
    "loop.turn": "in_discussion",
    "loop.tool": "waiting_tool",
    "loop.finished": "finished",
    ...
}
_TERMINAL_STATUS = {"finished", "blocked", "failed"}
```

---

## 3. Bảng ánh xạ vai trò pattern ↔ code thật

| Vai trò Event Storming | Khái niệm | Thành phần code thật |
|------------------------|-----------|----------------------|
| Sticky ORANGE | Domain event past-tense | `loop.team_composed` / `loop.decision` / `loop.turn` / `loop.tool` / `loop.finished` — emit ở `supervisor/graph.py:103,122,209,226` |
| Sticky GREEN | Read model (view UI) | `TaskLoopSnapshot` — `control/snapshot.py:88-134` |
| Node của read model | View 1 agent | `AgentView` — `control/snapshot.py:36-85` |
| Fold / left-fold | Gập event thành view | `build_snapshot` — `control/snapshot.py:189-365` |
| Policy (when X → status Y) | Suy ra status từ event | `_STATUS_BY_EVENT` + luật `done/running/waiting/pending` — `control/snapshot.py:140-148, 339-352` |
| Event là nguồn sự thật, không phải view | Business logic chỉ emit, UI chỉ render | `SupervisorContext.emit` — `supervisor/graph.py:56-75` |

---

## 4. Bản rút gọn chạy được

File: `event_projection_snapshot.py` (chỉ stdlib).

Nó mô phỏng:
- `fake_supervisor_run()` sinh chuỗi `loop.*` event của một vòng multi-agent: chọn team 3 agent → O quyết định giao 3 agent → 3 turn → 1 tool call → finished. (Tương ứng các điểm emit ở `supervisor/graph.py`.)
- `build_snapshot()` fold chuỗi đó thành `TaskLoopSnapshot` với danh sách `AgentView` (status `done`), tool call, orchestrator decision.
- Fold *dở chừng* (chỉ 2 event đầu) cho thấy cùng chuỗi nhưng prefix khác → 3 agent ở trạng thái `running` — projection không sai, chỉ là view của một tiền tố khác.
- Đối chứng: nếu UI tự nuôi state mutable (đếm turn bằng counter) thì một `loop.turn` bị giao lại lần 2 (at-least-once delivery) gây *double count*; còn projection idempotent theo `agent_id` (tập `turned`) thì writer vẫn đúng 1 trạng thái `done`.
- 4 assert bất biến: deterministic (replay cùng event → cùng snapshot), idempotent (duplicate turn không đổi snapshot), monotonic (tập agent chỉ lớn dần), terminal status không bị ghi đè.

Nó **lược bỏ** so với bản thật: bỏ Blackboard/`TaskLoopState`, `DelegationService`, `Broker`, orchestrator LLM (thay bằng hàm fake sinh event); bỏ redaction/`ui_payload` (đã minh hoạ ở case 01, đọc thẳng payload cho gọn); bỏ phần fold checkpoint/approval/permission (giữ lõi team_composed/decision/turn/tool/finished).

Chạy:

```bash
python3 event_projection_snapshot.py
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Fold lại từ đầu tốn kém**: với chuỗi event rất dài, fold mọi lúc là O(n) mỗi lần. Bản thật giới hạn bằng ring buffer 2048 event/session (`control/replay.py:24`) + snapshot làm điểm tựa; nếu bạn distill mà fold toàn bộ lịch sử mỗi frame, UI sẽ ì.
- **Order-sensitive**: fold phụ thuộc thứ tự event. Nếu transport giao event lệch thứ tự mà bạn không sort theo `seq` trước, projection sai. (Bản thật dùng `seq` + `EventReplayBuffer.events_after` để đảm bảo thứ tự.)
- **Không hợp khi không cần lịch sử**: nếu bạn chỉ cần "trạng thái hiện tại" và không bao giờ replay/audit/time-travel, một mutable state đơn giản gọn hơn nhiều. Projection trả giá phức tạp để đổi lấy replayability — chỉ đáng khi bạn thật sự cần nó.
- **Schema event đổi = mọi projection phải cập nhật**: thêm trường mới vào event mà projection cũ không đọc thì view thiếu thông tin; xoá trường thì projection cũ vỡ.

---

## 6. Câu hỏi tự kiểm tra

1. Trong bản distill, đếm số lần `writer` chạy bằng counter mutable cho ra 2 (double count) khi event bị giao lại, nhưng projection cho ra `status=done` không đổi. Tính chất nào của projection làm nó miễn nhiễm với at-least-once delivery? (Gợi ý: `turned` là `set`.)
2. `_STATUS_BY_EVENT` map cả `loop.finished` lẫn `loop.turn`, nhưng `_TERMINAL_STATUS` ngăn `loop.turn` ghi đè `finished`. Nếu bỏ kiểm tra terminal đó, một event `loop.turn` đến *sau* `loop.finished` sẽ làm gì với `snapshot.status`? Vì sao điều đó tệ?
3. Vì sao `supervisor/graph.py` emit `loop.team_composed` *sau* khi đã `state.selected_agents = list(ids)` (đổi state trước, emit fact sau), chứ không emit trước rồi mới đổi? (Gợi ý: event là "đã xảy ra", không phải "sắp xảy ra" — liên hệ anti-pattern future-tense trong bài gốc.)
