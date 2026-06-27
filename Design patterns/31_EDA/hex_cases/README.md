# Event-Driven Architecture (EDA) trong `hex_agent` — hex_cases

> Bộ case học thực chiến, distill từ chính codebase `hex_agent`, đi kèm bài học gốc [`31_EDA.md`](../31_EDA.md). Mỗi case có một README phân tích + một file `.py` self-contained (chỉ stdlib Python 3.14) chạy được, in narration tiếng Việt và assert bất biến của pattern.

---

## EDA hiện diện ở đâu trong hex_agent?

`hex_agent` xây EDA xuyên suốt qua một hệ **pub-sub event bus**. Kernel phát các domain event (`tool.requested`, `tool.completed`, `tool.failed`, `middleware.skipped`, `graph.*`...) lên một `EventBus` in-process; nhiều subscriber độc lập nghe và phản ứng mà producer **không biết** ai tiêu thụ. Metadata event được versioned qua một registry (`config/runtime_event_types.yaml`), quy tắc visibility/redaction được áp theo từng event_type, và được lưu qua một observability sink (`EventLogger` ghi JSONL).

Nhờ vậy ba tầng tách rời nhau chỉ qua *event schema*: tầng orchestration của agent, adapter UI bridge, và observability — không coupling temporal hay structural.

```
PRODUCER                      BUS                       CONSUMERS (độc lập)
AgentKernel.execute_tool() ─publish─▶ EventBus ─┬─▶ EventLogger.sink   (observability/JSONL)
   tool.requested                                ├─▶ KernelEventBridge  (dịch sang UI loop.*)
   tool.completed / tool.failed                  └─▶ (metrics / tracing / handler tương lai)
                                                       thêm consumer = bus.subscribe(...), 0 sửa kernel
```

Cốt lõi EDA của `hex_agent`:
- **Bus tối giản, an toàn:** `core/events.py:11-31` — snapshot subscriber dưới lock, deepcopy payload mỗi delivery, nuốt exception của từng subscriber ("an observer must never break the runtime").
- **Producer phát fact:** `core/kernel.py:106-225` — `execute_tool` phát `tool.requested` (trước) và `tool.completed`/`tool.failed` (sau), fire-and-forget.
- **Quản trị schema:** `control/event_registry.py` + `config/runtime_event_types.yaml` — mọi event_type phải khai báo trước; emitter (`control/emitter.py`) là gate validate → seq → redact → fan-out.
- **Phân tầng qua event:** `ui/ide/bridge.py` — bridge là subscriber thuần dịch `tool.*` → UI `loop.*`; `ui/ide/runner.py` ráp dây; `ui/ide/session.py` đẩy vào buffer cho SSE.

---

## Các case con

| # | Case | Trọng tâm | File chạy |
|---|---|---|---|
| 01 | [Core Kernel Event Pub/Sub](./01_kernel_event_pub_sub/) | Producer phát fact, bus fan-out tới nhiều consumer độc lập; cô lập lỗi; deepcopy payload | [`kernel_event_pub_sub.py`](./01_kernel_event_pub_sub/kernel_event_pub_sub.py) |
| 02 | [Event Registry & Versioning](./02_event_registry_versioning/) | Registry quản trị schema; emitter là gate validate; seq đơn điệu; redaction theo visibility | [`event_registry_versioning.py`](./02_event_registry_versioning/event_registry_versioning.py) |
| 03 | [IDE UI Event Bridge](./03_ide_ui_event_bridge/) | EDA đa tầng: bridge là subscriber dịch `tool.*` → `loop.*`, correlate qua `request_id` | [`ide_ui_event_bridge.py`](./03_ide_ui_event_bridge/ide_ui_event_bridge.py) |

Xem [`CATALOG.md`](./CATALOG.md) để có bảng **mọi occurrence** của EDA trong codebase (path:line + mô tả + độ rõ).

---

## Chạy tất cả

```bash
cd "Design patterns/31_EDA/hex_cases"
python3 01_kernel_event_pub_sub/kernel_event_pub_sub.py
python3 02_event_registry_versioning/event_registry_versioning.py
python3 03_ide_ui_event_bridge/ide_ui_event_bridge.py
```

Mỗi file thoát code 0, không traceback, in narration từng bước và kết thúc bằng "TẤT CẢ ASSERT PASS".

---

## Bản đồ EDA ↔ bài học gốc

| Khái niệm trong `31_EDA.md` | Hiện thực trong hex_agent | Case |
|---|---|---|
| Producer phát event, không await consumer | `AgentKernel.execute_tool` publish (`core/kernel.py`) | 01 |
| Event Bus (in-process, callback list) | `EventBus` (`core/events.py`) | 01, 03 |
| Fan-out nhiều consumer độc lập | EventLogger + KernelEventBridge cùng subscribe | 01, 03 |
| Cô lập lỗi (1 consumer fail không sập hệ) | `except Exception: pass` (`core/events.py:29-31`) | 01 |
| Event immutable | `RuntimeEvent` frozen (`control/events.py:113-151`) | 02 |
| Schema event versioned | `schema_version` + registry (`control/event_registry.py`) | 02 |
| Visibility / không lộ secret | `Redactor` (`control/redaction.py`) theo visibility | 02 |
| EDA đứng trên Hex (adapter pub-sub mới) | bridge dịch tầng kernel → tầng UI | 03 |
| Correlation id | `request_id` trong `_pending` (`ui/ide/bridge.py`) | 03 |
