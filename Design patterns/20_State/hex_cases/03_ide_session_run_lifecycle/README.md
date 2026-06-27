# Case 03 — IDE Session: vòng đời run (idle → running → finished/failed/cancelled)

> Một biến thể **thread-safe** của State pattern. Hành vi của `cancel()` phụ thuộc state hiện
> tại: chỉ hủy được khi đang `running` (giống "chỉ đánh thức được khi đang ngủ"). Transition
> `idle → running` là một **vùng tới hạn nguyên tử** — hai yêu cầu chạy đồng thời không thể
> cùng thắng, nên không có hai run xen kẽ sự kiện hay ghi đè baseline của nhau.

---

## 1. Bối cảnh trong hex_agent

`ui/ide/` là backend của một IDE: mỗi `IdeSession` có một event buffer mà run của agent bơm
vào và socket SSE rút ra. Một phiên chỉ chạy được **một** agent run tại một thời điểm. Trạng
thái run đi qua `idle → running → finished/failed/cancelled`, và mọi thao tác HTTP (submit,
stop, poll status, diff) đọc/ghi trạng thái này từ **nhiều thread khác nhau**.

Vấn đề thật mà pattern giải:
- Run chạy trên một daemon thread; HTTP handler (cancel/diff/meta) chạy trên thread khác.
  Đọc-rồi-ghi `run_status` mà không đồng bộ → race: hai submit cùng đọc `"idle"` rồi cùng
  claim → hai run cùng chạy.
- Hành vi phụ thuộc state: `cancel()` chỉ có nghĩa khi `running`; gọi lúc `idle`/terminal là no-op.
- Cần transition **nguyên tử** (kiểm-tra-và-gán trong một lock).

File và dòng đã mở kiểm chứng:
- `ui/ide/session.py:48` — `self._cond = threading.Condition()`.
- `ui/ide/session.py:50` — `self.run_status = "idle"  # idle | running | finished | failed`.
- `ui/ide/session.py:109-112` — `set_status()` mutate + notify dưới lock.
- `ui/ide/session.py:118-129` — `try_begin_run()` guard nguyên tử `idle→running`; từ chối nếu đang running.
- `ui/ide/session.py:131-133` — `snapshot_status()` đọc dưới lock.
- `ui/ide/runner.py:80-88` — `cancel()` chỉ hoạt động khi `status == "running"`.
- `ui/ide/runner.py:90-121` — `start()` claim status nguyên tử (dòng 101) rồi spawn `_run` thread.
- `ui/ide/runner.py:123-183` — `_run` thread → `finished` (dòng 183).
- `ui/ide/runner.py:185-194` — `_finish_failed()` → `failed`.
- `ui/ide/runner.py:196-206` — `_finish_cancelled()` → `cancelled`.

---

## 2. Trích đoạn code thật

Guard nguyên tử `idle → running` (`ui/ide/session.py:118-133`):

```python
def try_begin_run(self, prompt: str, baseline: dict[str, str], scope: str) -> bool:
    """Atomically claim the session for a new run: refuse if one is already running ..."""
    with self._cond:
        if self.run_status == "running":
            return False
        self.last_prompt = prompt
        self.baseline = baseline
        self.baseline_scope = scope
        self.run_status = "running"
        self._cond.notify_all()
        return True

def snapshot_status(self) -> str:
    with self._cond:
        return self.run_status
```

`cancel()` — hành vi phụ thuộc state (`ui/ide/runner.py:80-88`):

```python
def cancel(self) -> bool:
    if self.session.snapshot_status() != "running":
        return False
    self._cancel.set()
    return True
```

Claim nguyên tử trong `start()` rồi mới spawn thread (`ui/ide/runner.py:100-121`):

```python
with self._lock:
    if not self.session.try_begin_run(prompt, baseline, "workspace"):
        return None
    self._cancel.clear()
...
thread = threading.Thread(target=self._run, args=(run_id, prompt, system_prompt), ...)
thread.start()
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò State pattern | Thành phần trong hex_agent | Ghi chú |
|---|---|---|
| **Context** | `IdeSession` (`session.py`) | Giữ `run_status` + event buffer; delegate run cho runner thread. |
| **State (interface)** | field `run_status` ∈ {idle, running, finished, failed, cancelled} | Định danh giai đoạn run. |
| **Transition (đóng gói)** | `set_status()` (`session.py:109-112`) | Mutate + `notify_all` dưới `Condition`. |
| **Guard nguyên tử** | `try_begin_run()` (`session.py:118-129`) | Kiểm-tra-và-gán `idle→running` trong một vùng tới hạn; từ chối `running→running`. |
| **Hành vi phụ thuộc state** | `cancel()` (`runner.py:80-88`) | Chỉ tác dụng khi `running`. |
| **Transition state-driven** | `_run` / `_finish_failed` / `_finish_cancelled` (`runner.py`) | Runner thread đẩy `running → finished/failed/cancelled`. |
| **Đọc state an toàn** | `snapshot_status()` (`session.py:131-133`) | HTTP handler đọc qua lock của session để không race. |

---

## 4. Bản rút gọn chạy được

File: [`ide_session_run_lifecycle.py`](./ide_session_run_lifecycle.py)

Mô phỏng đúng:
- `IdeSession` với `run_status`, `threading.Condition`, `set_status`, `try_begin_run`, `snapshot_status`.
- `AgentRunner` với `start()` (claim nguyên tử + spawn thread), `cancel()` (chỉ khi running),
  `_run` / `_finish_failed` / `_finish_cancelled`.
- Bốn kịch bản: chạy hết → `finished`; hai `start` đồng thời → cái thứ hai bị từ chối;
  `cancel` giữa chừng → `cancelled`; `cancel` khi không running → no-op.
- Đối chứng mô tả race khi kiểm-tra-và-gán **không** nằm dưới lock.

Lược bỏ (thay bằng fake stdlib):
- **Kernel + LLM agent run** (`orchestrator.run`, middleware cancel ở `execute_tool`) →
  `fake_agent_work`: vài bước `time.sleep` ngắn, kiểm tra cờ cancel hợp tác (cooperative).
- **SSE buffer / Redactor / RuntimeEvent / EventReplayBuffer** → một list `events` chuỗi đơn giản.
- Bỏ baseline diff, trace, registry — chỉ giữ phần thể hiện máy trạng thái thread-safe.
- `RunCancelled` (subclass `BaseException`) → thay bằng `threading.Event` + kiểm tra cờ;
  giữ đúng tinh thần "cancel hợp tác", bỏ chi tiết slip-qua-except-Exception.

Chạy:
```bash
python3 ide_session_run_lifecycle.py
```

> Lưu ý: case này dùng đa luồng + `time.sleep` ngắn để demo tính nguyên tử. Thời gian ngủ
> nhỏ (10–20ms) nên chạy nhanh; `wait_until_terminal` chặn tới khi đạt state terminal để
> output ổn định, không phụ thuộc lịch định thời.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- Đây là biến thể nâng cao: thêm chi phí khoá (`Condition`). Nếu trạng thái run **không** bị
  nhiều thread truy cập (vd chạy đồng bộ trong một thread), thì không cần lock — một enum
  đơn giản là đủ.
- Phải kỷ luật: **mọi** đọc/ghi `run_status` đi qua lock của session (`snapshot_status` /
  `set_status` / `try_begin_run`). Lỡ đọc trực tiếp `self.run_status` ngoài lock là tái lập race.
- `cancel` là **hợp tác** (cooperative): run chỉ dừng ở điểm kiểm tra cờ kế tiếp, không
  cưỡng chế. Nếu cần dừng tức thì giữa một bước dài thì pattern này không đủ.
- Chỉ ~3-4 state hữu dụng; nếu vòng đời run nở ra nhiều nhánh (paused/resumed/retrying...)
  cần xem lại có nên dùng máy trạng thái tường minh hơn không.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao kiểm tra `if self.run_status == "running"` và phép gán `self.run_status = "running"`
   trong `try_begin_run` phải nằm trong **cùng một** khối `with self._cond`? Tách ra hai khối
   thì race nào xuất hiện?
2. `cancel()` đọc trạng thái qua `snapshot_status()` thay vì truy cập `session.run_status`
   trực tiếp. Lợi ích cụ thể với mô hình đa luồng là gì?
3. Trong các kịch bản, vì sao `cancel()` trả `False` khi state là `idle` hoặc đã `finished`,
   nhưng trả `True` khi `running`? Đây là biểu hiện nào của State pattern?
