# State Pattern trong hex_agent — hex_cases

> Tài liệu này soi pattern **State (Behavioral)** qua chính codebase `hex_agent`: tìm các nơi
> một object **đổi hành vi theo trạng thái nội bộ** (không phải đổi theo input từ ngoài — đó là
> Strategy), chưng cất mỗi nơi thành một ví dụ chạy được chỉ-bằng-stdlib, và đối chiếu từng
> dòng với code thật.

Tham chiếu lý thuyết: [`../20_State.md`](../20_State.md) — analogy "các giai đoạn ngủ"
(Wake → NREM1 → NREM2 → NREM3 → REM): **cùng một bộ não, hành vi neural đổi theo stage**, và
transition có quy luật (không nhảy thẳng Wake → REM trừ khi "bug" = narcolepsy).

---

## Pattern xuất hiện ở đâu trong hex_agent?

State pattern xuất hiện ở nhiều domain, mỗi domain là một máy trạng thái lái-hành-vi:

1. **Phân rã task** — vòng đời `Node`: `pending → active → decomposed/done/blocked`. Navigator
   delegate hành vi cho trạng thái hiện tại của node và transition qua cập nhật status tường minh.
2. **Supervisor TaskLoop** — `TaskLoopStatus` enum:
   `created → team_selected → in_discussion → waiting_tool → reviewing_ac → finished/blocked/failed`.
3. **IDE session run** — `run_status`: `idle → running → finished/failed/cancelled` (biến thể thread-safe).

Điểm chung: Context delegate hành vi cho state hiện tại và transition qua cập nhật status tường
minh — **tránh `if/elif` rải rác** trên một biến trạng thái.

---

## Các case con

| # | Case | Đặc trưng State | Nguồn thật chính |
|---|---|---|---|
| [01](./01_task_decomposition_navigator/) | **Task Decomposition Navigator** | Tập 5 state hữu hạn + `frozen dataclass` + cursor đọc status; transition state-driven **và** context-driven (`_close_done_parents`). | `decompose_agent/node.py`, `tree.py`, `solve.py` |
| [02](./02_supervisor_taskloop_state_machine/) | **Supervisor TaskLoop** | `Enum` 8 state + subset `TERMINAL`; Context orchestrator `_drive` route theo decision; guard `max_rounds`/progress/repeat. | `supervisor/state.py`, `graph.py`, `loop.py` |
| [03](./03_ide_session_run_lifecycle/) | **IDE Session run lifecycle** | Biến thể **thread-safe**: guard nguyên tử `idle→running` dưới `threading.Condition`; hành vi `cancel` phụ thuộc state. | `ui/ide/session.py`, `runner.py` |

Mỗi thư mục con có: một `README.md` (6 mục: bối cảnh thật → trích code thật → bảng ánh xạ vai
trò → bản rút gọn → cái giá → câu hỏi) và một file `.py` self-contained chạy được.

Danh sách **vét cạn** mọi occurrence (kể cả các nơi độ rõ vừa/thấp): xem [`CATALOG.md`](./CATALOG.md).

---

## Vì sao đây là State chứ không phải Strategy?

| Khía cạnh | hex_agent dùng State | (Strategy sẽ là) |
|---|---|---|
| Ai chọn hành vi? | Object tự, theo lifecycle (node fail → tự decompose; run xong → tự finished) | Client chọn từ ngoài |
| Khi nào đổi? | Thường xuyên, phản ứng sự kiện (gate fail, cancel, max_rounds) | Hiếm, set một lần |
| Có transition giữa các state? | Có — máy trạng thái có guard | Không — các strategy độc lập |

State pattern ở đây mua được: (1) **tập state hữu hạn** canh gác tại construction/transition,
(2) **không if/elif rải rác** trên biến status, (3) **guard** chặn transition sai (không leo
sớm, không vượt max_rounds, không claim run khi đang running).

---

## Chạy thử

```bash
cd "Design patterns/20_State/hex_cases"
python3 01_task_decomposition_navigator/task_decomposition_navigator.py
python3 02_supervisor_taskloop_state_machine/supervisor_taskloop_state_machine.py
python3 03_ide_session_run_lifecycle/ide_session_run_lifecycle.py
```

Mỗi file in narration từng bước (tiếng Việt) + chứa `assert` chứng minh bất biến của pattern,
thoát code 0 và không traceback. Cả ba **chỉ dùng thư viện chuẩn Python 3.14** — không import
`hex_agent` hay bất kỳ thư viện bên thứ ba nào.
