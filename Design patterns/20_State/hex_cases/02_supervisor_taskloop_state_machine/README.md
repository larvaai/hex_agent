# Case 02 — Supervisor TaskLoop: enum status + transitions có guard

> Một "đêm ngủ" của agent: `CREATED → TEAM_SELECTED → IN_DISCUSSION → WAITING_TOOL →
> REVIEWING_AC → FINISHED/BLOCKED/FAILED`. Mỗi vòng (round) đi qua cùng một đường, chỉ
> khác ở quyết định của O định tuyến tới handler nào. Tập state cuối (`TERMINAL`) gom về
> một nơi — vào là không ra, đúng như stage terminal của một chu kỳ.

---

## 1. Bối cảnh trong hex_agent

`supervisor/` điều phối một phiên multi-agent: Agent-O chọn đội, rồi mỗi vòng đưa ra một
quyết định có cấu trúc (`continue` / `need_tool` / `finished` / `blocked` / `failed`).
Quyết định đó **lái** trạng thái của `TaskLoopState` qua các giai đoạn. Toàn bộ trạng thái
là dữ liệu nguyên thuỷ để có thể checkpoint xuống SQLite và **resume**.

Vấn đề thật mà pattern giải:
- Phiên có nhiều giai đoạn với hành vi khác biệt; cần một **enum trạng thái rõ ràng** + một
  **tập terminal** để biết khi nào dừng — thay vì rải `if status in (...)` khắp nơi.
- Cần các **guard** (max_rounds, không tiến triển, O lặp lại quyết định) để máy trạng thái
  không quay vòng vô hạn — giống "đủ NREM trước khi vào REM".
- Logic máy trạng thái (`_drive`) phải **tách khỏi** business logic của từng handler.

File và dòng đã mở kiểm chứng:
- `supervisor/state.py:14-25` — `TaskLoopStatus(str, Enum)` 8 state + `TERMINAL = {FINISHED, BLOCKED, FAILED}`.
- `supervisor/state.py:84` — `TaskLoopState.status` giữ state hiện tại.
- `supervisor/state.py:105-107` — `is_terminal`.
- `supervisor/state.py:109-111` — `acceptance_snapshot()` (đầu vào của loop guard "không tiến triển").
- `supervisor/graph.py:102` — `compose_team()` → `TEAM_SELECTED`.
- `supervisor/graph.py:211` — `run_round()` → `IN_DISCUSSION`.
- `supervisor/graph.py:227` — `run_tool()` → `WAITING_TOOL`.
- `supervisor/graph.py:256` — `judge_acceptance()` → `REVIEWING_AC`.
- `supervisor/loop.py:148-201` — `_drive()` (Context orchestrator).
- `supervisor/loop.py:204-208` — `_terminate()` set state terminal.

---

## 2. Trích đoạn code thật

Enum trạng thái + tập terminal (`supervisor/state.py:14-25, 105-107`):

```python
class TaskLoopStatus(str, Enum):
    CREATED = "created"
    TEAM_SELECTED = "team_selected"
    IN_DISCUSSION = "in_discussion"
    WAITING_TOOL = "waiting_tool"
    REVIEWING_AC = "reviewing_ac"
    FINISHED = "finished"
    BLOCKED = "blocked"
    FAILED = "failed"

TERMINAL = {TaskLoopStatus.FINISHED, TaskLoopStatus.BLOCKED, TaskLoopStatus.FAILED}

# @property is_terminal:
return TaskLoopStatus(self.status) in TERMINAL
```

Context orchestrator route theo decision + guard (`supervisor/loop.py:154-199`):

```python
while not state.is_terminal:
    if state.round_no >= state.max_rounds:
        _terminate(state, ctx, TaskLoopStatus.BLOCKED, "max_rounds reached")
        break
    ...
    if decision.decision == "finished":
        judge_acceptance(state, ctx, decision)
        if state.all_accepted():
            ...
            _terminate(state, ctx, TaskLoopStatus.FINISHED, ...)
            break
    elif decision.decision == "need_tool":
        run_tool(state, ctx, decision)
        judge_acceptance(state, ctx, decision)
    elif decision.decision == "continue":
        run_round(state, ctx, decision)
        judge_acceptance(state, ctx, decision)
    ...
    progressed = len(state.artifacts) > before_artifacts or state.acceptance_snapshot() != before_acceptance
    if not progressed:
        _terminate(state, ctx, TaskLoopStatus.BLOCKED, "no progress this round")
        break
```

Handler đổi state (`supervisor/graph.py:102, 211, 227, 256`):

```python
state.status = TaskLoopStatus.TEAM_SELECTED.value   # compose_team, l.102
state.status = TaskLoopStatus.IN_DISCUSSION.value    # run_round,    l.211
state.status = TaskLoopStatus.WAITING_TOOL.value     # run_tool,     l.227
state.status = TaskLoopStatus.REVIEWING_AC.value     # judge_acceptance, l.256
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò State pattern | Thành phần trong hex_agent | Ghi chú |
|---|---|---|
| **Context** | `TaskLoopState` (`state.py:80`) | Mang `status` hiện tại + blackboard (artifacts/turns/AC). |
| **State (interface)** | `TaskLoopStatus` enum (`state.py:14-22`) | 8 state, định danh giai đoạn. |
| **Terminal states** | `TERMINAL` (`state.py:25`) | Subset "vào là không ra"; gom về một nơi. |
| **Context orchestrator** | `_drive()` (`loop.py:148-201`) | `while not is_terminal`, route `decision.decision` tới handler. |
| **Transition (đổi state)** | `compose_team`/`run_round`/`run_tool`/`judge_acceptance` (`graph.py`) | Mỗi handler set `state.status`. |
| **Transition → terminal** | `_terminate()` (`loop.py:204-208`) | Set một state terminal + lý do. |
| **Guard** | `is_terminal`, `max_rounds`, progress check, `repeat_count` | Chặn transition sai / vòng lặp vô hạn. |

---

## 4. Bản rút gọn chạy được

File: [`supervisor_taskloop_state_machine.py`](./supervisor_taskloop_state_machine.py)

Mô phỏng đúng:
- `TaskLoopStatus` enum 8 state + `TERMINAL` + `is_terminal` + `acceptance_snapshot`.
- Handlers `compose_team` / `run_round` / `run_tool` / `judge_acceptance` đổi `state.status`.
- `_terminate` và `drive()` (bản distill của `_drive`) với đủ guard: `max_rounds`,
  "no progress", "repeated decision".
- Ba kịch bản: happy-path → `FINISHED`; `continue` mãi → guard `max_rounds` → `BLOCKED`;
  state đã terminal → `drive` không chạy vòng nào.
- Đối chứng giải thích vì sao thiếu enum + `TERMINAL` thì kiểm tra "khi nào dừng" bị rải rác.

Lược bỏ (thay bằng fake stdlib):
- **Agent-O (LLM)** → `ScriptedOrchestrator` với hàng đợi `Decision` cố định (giống `ScriptedOrchestrator` ở `supervisor/orchestrator.py:21-39`).
- **DelegationManager / Broker / KernelSession** → handler chỉ thêm artifact giả vào blackboard.
- **SQLite checkpoint / resume** → bỏ; giữ state trong RAM (giữ nguyên `acceptance_snapshot` để guard "no progress" vẫn thật).
- Bỏ `Budget` parse-error, `record_ac_report`, `emit` event — không liên quan tới máy trạng thái.

Chạy:
```bash
python3 supervisor_taskloop_state_machine.py
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- Máy trạng thái này là **context-driven** thuần: mọi transition tập trung ở `_drive`. Ưu
  điểm là dễ debug/audit; nhược điểm là `_drive` có xu hướng phình. Khi luồng phức tạp hơn
  (sub-state, parallel region) nên cân nhắc HSM/statechart thay vì nhồi vào một vòng `while`.
- Nếu chỉ có 2-3 giai đoạn tuyến tính, enum + một vài `if` đã đủ; dựng đủ guard + snapshot
  là thừa.
- `Enum(str)` tiện checkpoint (JSON-able) nhưng cũng cho phép so sánh với chuỗi thô — kỷ luật
  team phải luôn dùng `TaskLoopStatus(...)` khi kiểm tra terminal, tránh so sánh chuỗi lạc.
- Guard "no progress / repeated decision" là heuristic; chọn ngưỡng sai có thể cắt sớm một
  phiên đang tiến triển chậm. Cần đo thực tế.

---

## 6. Câu hỏi tự kiểm tra

1. `TERMINAL` đặt ở `state.py:25` thay vì lặp lại `status in ("finished","blocked","failed")`
   ở nhiều nơi mua được gì khi ta thêm một state terminal mới (vd `CANCELLED`)?
2. Trong `_drive`, vì sao guard `max_rounds` được kiểm tra **đầu** mỗi vòng còn guard
   "no progress" được kiểm tra **cuối** vòng? Đổi thứ tự có thay đổi hành vi không?
3. Quyết định `finished` của O không tự động đưa state về `FINISHED`. Điều kiện nào ở
   `_drive` phải đúng trước khi `_terminate(..., FINISHED, ...)` được gọi, và state đi qua
   giai đoạn trung gian nào?
