# Command pattern trong hex_agent — hex_cases

> Tài liệu dạy học đi kèm `14_Command.md`. Mỗi case là một bản **distill trung thực** từ code thật của `hex_agent`, chạy được bằng **chỉ thư viện chuẩn Python 3.14** (không import `hex_agent`, không thư viện bên thứ ba).

---

## Pattern "Command" xuất hiện ở đâu trong hex_agent?

Command pattern (Behavioral) xuất hiện **rõ ràng** trong `hex_agent` qua việc **đóng gói các hành động thành object có `execute()`** — để có thể queue, log, retry, lên lịch, replay và xử lý qua middleware — trong khi **invoker KHÔNG biết về receiver cụ thể**, chỉ biết gọi interface execute. Pattern này hiện diện ở **hai tầng**:

1. **Tầng tool (data-plane).** Mỗi lời gọi tool được đóng gói thành `ToolRequest` (immutable) và thực thi qua `ToolPort.execute()`. `AgentKernel.execute_tool()` là invoker duy nhất; middleware (retry, policy, budget...) bám quanh chokepoint đó. → **Case 01**.

2. **Tầng điều khiển (control-plane).** Mỗi can thiệp từ UI được đóng gói thành `RuntimeCommand` (immutable, có `command_type`/`idempotency_key`/`issued_by`). Gateway validate → chống trùng → lên lịch theo `apply_at` → dispatch tới receiver. → **Case 02**.

Cùng một ý tưởng cốt lõi: **"hành động trở thành first-class citizen"** — passable, queueable, replayable, decoupled khỏi receiver (đúng Insight ở `14_Command.md` Level 1).

---

## Các flagship (case con)

| # | Thư mục | Tiêu đề | Vai trò pattern (tóm tắt) |
|---|---|---|---|
| 01 | [`01_tool_request_execute_pattern/`](./01_tool_request_execute_pattern/) | `ToolRequest` + `ToolPort.execute()` — lõi Command | `ToolRequest`=ConcreteCommand; `ToolPort.execute`=Command interface; `EchoTool`/`FsRead`...=Receiver; `AgentKernel`=Invoker; middleware chain=lớp queue/xử lý |
| 02 | [`02_runtime_command_dispatch/`](./02_runtime_command_dispatch/) | `RuntimeCommand` — Command ở control-plane | `RuntimeCommand`=ConcreteCommand; `CommandTypeRegistry`=chiến lược lên lịch; `parse_command`=factory; `submit_command/_dispatch`=Invoker; `AgentRunner.start`=Receiver |

Mỗi case có:
- `README.md` — 6 mục: bối cảnh thật, trích code thật, bảng ánh xạ vai trò, bản rút gọn, cái giá, câu hỏi tự kiểm.
- `<name>.py` — code self-contained, có `demo()`, narration tiếng Việt, đối chứng "không dùng pattern", và `assert` chứng minh bất biến.

---

## Bản đồ đầy đủ mọi nơi pattern xuất hiện

Xem [`CATALOG.md`](./CATALOG.md) — bảng vét cạn mọi occurrence của Command pattern trong `hex_agent` (path:line, mô tả, độ rõ).

---

## Cách chạy

```bash
python3 01_tool_request_execute_pattern/tool_request_execute_pattern.py
python3 02_runtime_command_dispatch/runtime_command_dispatch.py
```

Cả hai thoát code 0, in ra từng bước demo bằng tiếng Việt và kết thúc bằng "TẤT CẢ assert PASS".

---

## Quan hệ với `14_Command.md`

- **Decoupling invoker ↔ receiver** (`14_Command.md` Level 1 obs. 6): Case 01 — `AgentKernel` không biết tool làm gì.
- **Queue / log / retry / replay** (Level 2 chiều 3): Case 01 middleware chain; Case 02 `apply_at` + dedup + event log.
- **Command như message qua mạng** (Level 2 chiều 5 — spatial decoupling): Case 02 — UI gửi `RuntimeCommand` qua HTTP.
- **Command IMMUTABLE & đủ context** (bài học Apraxia, mục III): cả hai case dùng `frozen=True` + validate.
- **Invoker là single point of failure** (bài học Parkinson): cả hai case bao try/except quanh chokepoint.
- Lưu ý: hex_agent **không dùng `undo()`** (nhiều tool có side-effect không hoàn tác); đây là biến thể "Command-as-message", một cách dùng hợp lệ và phổ biến của pattern.
