# Case 03 — IDE UI Event Bridge: dịch event kernel sang event UI qua subscriber

> EDA **đa tầng**: tầng kernel phát event thô `tool.*` lên bus; tầng bridge là một subscriber thuần, nghe và **dịch** thành từ vựng UI `loop.*`; rồi `session.emit` đẩy vào buffer cho SSE drain. Bridge không bao giờ gọi kernel — nó chỉ lắng nghe. Đây là minh hoạ EDA cho phép **phân tầng kiến trúc** mà không tạo call-chain phức tạp.

---

## 1. Bối cảnh trong hex_agent

Kernel single-agent phát `tool.requested` / `tool.completed` / `tool.failed` (và `graph.parse_error`) trên `EventBus` của nó. Nhưng UI (Graph + Timeline) lại nói từ vựng `loop.*` mà `build_snapshot` gấp lại. Nếu để kernel tự đẩy thẳng UI, kernel sẽ phải:

- biết từ vựng UI `loop.tool`,
- biết về `EventReplayBuffer`, redaction, SSE,
- và muốn thêm UI thứ hai (web/CLI) phải sửa kernel.

hex_agent tách bằng một **adapter là event handler thuần**: `KernelEventBridge` subscribe vào `kernel.events`, dịch `tool.*` → `loop.*`, đẩy qua `IdeSession.emit`. Runner chỉ ráp dây và tự phát các event *boundary* (mở/đóng run) vì chỉ runner biết run bắt đầu & kết thúc khi nào.

Một chi tiết EDA hay: `tool.completed` **không mang args** (chỉ `tool.requested` mang). Bridge giữ trạng thái `_pending` để **correlate** hai event qua `request_id`, nhấc `path` lên event completion — biến timeline từ "fs_write ✓" thành "fs_write ✓ · src/app.py".

Các điểm thật đã mở kiểm chứng:

- `ui/ide/bridge.py:32-44` — `KernelEventBridge`: giữ `_pending: dict[request_id -> {tool, path}]`; `subscriber(topic, payload)` gắn qua `kernel.events.subscribe`, never raise.
- `ui/ide/bridge.py:46-86` — `_handle`: `tool.requested` lưu meta; `tool.completed/failed` pop meta + correlate + `session.emit("loop.tool", ...)`; `graph.parse_error` → `loop.parse_error`.
- `ui/ide/bridge.py:88-96` — `_extract_path(args)` nhấc `args["path"]`.
- `ui/ide/runner.py:147-148` — `kernel.events.subscribe(bridge.subscriber)` + `attach_to_bus(EventLogger(...), kernel.events)`: **nhiều subscriber độc lập trên một bus**.
- `ui/ide/runner.py:105-116, 175-182` — runner tự phát `chat.user` / `loop.team_composed` / `loop.decision` (mở) và `loop.turn` / `loop.finished` / `chat.assistant` (đóng).
- `ui/ide/session.py:64-90` — `IdeSession.emit`: dưới `Condition`, cấp seq, redact, append vào `EventReplayBuffer`, notify reader SSE. Là **chỗ duy nhất** event vào buffer.
- `core/events.py:11-31` — `EventBus` mà bridge subscribe vào (xem Case 01).

---

## 2. Trích đoạn code thật

`ui/ide/bridge.py:60-78` — correlate `request_id` để nhấc `path` lên event UI, rồi `session.emit`:

```python
if topic in ("tool.completed", "tool.failed"):
    request_id = str(payload.get("request_id") or "")
    with self._lock:
        meta = self._pending.pop(request_id, {})
    tool = str(payload.get("tool") or meta.get("tool") or "")
    ok = bool(payload.get("ok")) if topic == "tool.completed" else False
    ui_payload: dict[str, Any] = {"tool": tool, "ok": ok, "status": "ok" if ok else "failed"}
    path = meta.get("path")
    if path:
        ui_payload["path"] = path
    ...
    self.session.emit("loop.tool", ui_payload, actor=Actor(type="agent", id=actor_id))
    return
```

`ui/ide/runner.py:147-148` — nhiều subscriber độc lập trên cùng một bus:

```python
kernel.events.subscribe(bridge.subscriber)
attach_to_bus(EventLogger(run_id=run_id), kernel.events)  # persist to var/agent_runs too
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai EDA | Trong hex_agent | Trong bản rút gọn `ide_ui_event_bridge.py` |
|---|---|---|
| **Producer (tầng kernel)** | `AgentKernel.execute_tool` phát `tool.*` (`core/kernel.py:123-224`) | `MiniKernel.execute_tool` |
| **Bus** | `kernel.events` = `EventBus` (`core/events.py:11-31`) | `MiniBus` |
| **Consumer = adapter dịch** | `KernelEventBridge.subscriber` (`ui/ide/bridge.py:38-86`) | `KernelEventBridge.subscriber` |
| **Correlation theo request_id** | `_pending` (`ui/ide/bridge.py:36, 47-64`) | `_pending` (distill 1-1) |
| **Sink UI (chỗ duy nhất vào buffer)** | `IdeSession.emit` (`ui/ide/session.py:64-90`) | `IdeSession.emit` |
| **Điều phối lifecycle boundary** | `AgentRunner` (`ui/ide/runner.py:105-116, 147-182`) | `AgentRunner.run` |
| **Nhiều subscriber/1 bus** | bridge + EventLogger (`ui/ide/runner.py:147-148`) | demo bước 1 + đối chứng |

---

## 4. Bản rút gọn chạy được

File: [`ide_ui_event_bridge.py`](./ide_ui_event_bridge.py) — chạy `python3 ide_ui_event_bridge.py` (exit 0).

**Mô phỏng gì:**
- `MiniBus` (kernel bus) + `KernelEventBridge` (subscriber dịch) + `IdeSession` (buffer + emit cấp seq).
- `MiniKernel` phát `tool.requested` (mang `args.path`) rồi `tool.completed`/`tool.failed` (không mang args).
- Bridge correlate hai event qua `request_id`, nhấc `path` lên `loop.tool`.
- `AgentRunner.run` ráp dây (`subscribe(bridge.subscriber)`) và tự phát các event boundary (`loop.team_composed`/`loop.decision`/`loop.turn`/`loop.finished`).
- Buffer cuối cùng chứa cả event của runner LẪN event do bridge dịch, theo đúng thứ tự seq.

**Lược bỏ:** không thread/SSE/`Condition` thật, không `Redactor`/`EventReplayBuffer` đầy đủ (buffer = list), không HTTP, không `Actor` envelope đầy đủ. Giữ đúng vai Producer(kernel) → Bus → Consumer(bridge dịch) → `session.emit` → buffer; và cơ chế correlation theo `request_id`.

**Bất biến được assert:**
- Thứ tự event đúng: runner mở → 2 `loop.tool` do bridge dịch → runner đóng.
- seq đơn điệu, liên tục `1..6`.
- Correlation: `path` từ `tool.requested` được nhấc lên `loop.tool` (event completed vốn không mang args).
- `_pending` đã dọn sạch sau correlate (không rò rỉ).
- **Đối chứng:** không subscribe bridge → event kernel rơi (fire-and-forget không subscriber), buffer UI rỗng.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Trạng thái correlation phải bị giới hạn:** `_pending` có thể rò rỉ nếu một tool không bao giờ báo completion — bản thật giới hạn `_MAX_PENDING` và evict cái cũ nhất.
- **Thêm một tầng gián tiếp:** với hệ rất nhỏ chỉ 1 UI, dịch trực tiếp đơn giản hơn là chèn bridge.
- **Khó truy vết end-to-end:** một sự kiện đi qua kernel → bus → bridge → session — debug cần correlation id, không có call stack liền mạch.
- **Ordering phụ thuộc seq:** nếu hai tầng phát seq từ bộ đếm khác nhau mà không thống nhất, UI có thể sắp xếp sai — phải có một nguồn seq (ở đây là `IdeSession`).

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao **runner** (không phải bridge) phát các event boundary `loop.team_composed`/`loop.turn`/`loop.finished`? (Gợi ý: chỉ ai biết run bắt đầu & kết thúc khi nào mới được phát chúng — `ui/ide/bridge.py:8-13`.)
2. Bridge phải correlate `tool.requested` với `tool.completed` qua `request_id`. Điều gì xảy ra với timeline nếu bỏ `_pending` và chỉ đọc `tool.completed`?
3. Trong đối chứng "không subscribe bridge", event kernel rơi mà không báo lỗi. Tính chất EDA nào khiến điều này xảy ra, và vì sao đôi khi nó là tính năng (chứ không phải bug)?
