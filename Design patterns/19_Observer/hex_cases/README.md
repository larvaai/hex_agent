# Observer Pattern trong hex_agent — Case Studies

> Tài liệu dạy học đi kèm [`../19_Observer.md`](../19_Observer.md). Ở đây ta **soi pattern Observer trong codebase thật** của `hex_agent`, chưng cất (distill) thành các bản chạy được chỉ bằng thư viện chuẩn Python, để bạn thấy lý thuyết "amygdala broadcast salience 1-tới-N" hiện thân trong code production thế nào.

---

## Observer trong hex_agent là gì?

hex_agent dựng một **hệ event publish/subscribe** để tách rời **nguồn phát event** khỏi **bên tiêu thụ**:

- **Nguồn phát (Subject):** kernel chạy tool, orchestrator điều phối, máy trạng thái của `drag_from_zero` chuyển trạng thái.
- **Bên tiêu thụ (Observer):** bộ ghi log JSONL, cầu nối UI (IDE), bộ gom metric/analytics, thanh tiến trình.

Lõi của hệ là `EventBus` ở `core/events.py:11-31` — một pub/sub tối thiểu nhưng thread-safe: Subject giữ list subscriber, `publish` lặp qua và gọi từng cái, kèm hai bảo vệ thực chiến là **deepcopy tách rời payload** và **cô lập lỗi** ("một observer không bao giờ được phép kéo sập runtime"). Trên nền đó, nhiều hiện thân Observer mọc lên: `EventLogger` subscribe để ghi log durable, `KernelEventBridge` subscribe để dịch event kernel sang event UI, `EventLog` của `drag_from_zero` subscribe để theo dõi chuyển trạng thái, `EventEmitter` fan event ra N `EventSinkPort`.

Giá trị pattern mang lại đúng như bài học gốc: **loose coupling + Open/Closed** — thêm observer mới (logging, UI, analytics, sink Kafka tương lai) chỉ cần `subscribe`, **không phải sửa code Subject**.

## Các case con

| # | Case | Distill từ | Điểm dạy chính |
|---|------|-----------|----------------|
| [01](./01_event_bus_core/) | **EventBus: Lõi Pub/Sub thread-safe** | `core/events.py:11-31` + `tests/test_event_concurrency.py:9-21` | Observer thuần khiết: list + notify; deepcopy tách rời payload; cô lập lỗi; RLock. |
| [02](./02_event_logger_adapter/) | **EventLogger: Closure-as-Observer** | `observability/event_log.py:102-134, 60-73` + `ui/ide/runner.py:147-148` + `tests/test_event_concurrency.py:24-41` | Observer dạng closure cho observability; 1-tới-N trên cùng bus; gom metric + ghi durable; seq đơn điệu dưới đua thread; gỡ động. |
| [03](./03_event_log_broadcast/) | **EventLog: Observer + Event Sourcing** | `drag_from_zero/dragzero/events.py:37-43, 46-91` + `drag_from_zero/tests/unit/test_events.py:29-45, 90-93` | Event **frozen** (chống corrupt view); **durable trước broadcast**; biến thể **late subscription**; **replay** từ ledger để catch-up. |

Mỗi thư mục con có:
- `README.md` — bài học 6 mục (bối cảnh, code thật, bảng ánh xạ vai trò, bản rút gọn, cái giá, câu hỏi tự kiểm tra).
- `<name>.py` — bản distill chạy được (`python3 <name>.py`), in narration tiếng Việt từng bước, có assert chứng minh bất biến và ít nhất một đối chứng "không dùng pattern thì hỏng".

## Bản đồ vai trò pattern (tổng hợp 3 case)

| Vai trò Observer (theo `19_Observer.md`) | Hiện thân trong hex_agent |
|------------------------------------------|---------------------------|
| Subject / Publisher | `EventBus` (case 01), `EventLog` (case 03), `EventEmitter` (catalog #6) |
| Danh sách observers | `_subscribers` / `_subs` / `_sinks` |
| attach / detach | `subscribe` / `unsubscribe` |
| notify | `publish` / `append` / `emit_event` |
| Observer interface | `Subscriber = Callable[[str, dict], None]`, `EventSinkPort` Protocol, `Callable[[Event], None]` |
| Event | cặp `(topic, payload)` (case 01/02) hoặc `@dataclass(frozen=True) Event` (case 03) |
| Cô lập lỗi | `try/except Exception: pass` (`core/events.py:29-31`) |
| Event bất biến | `deepcopy` (case 01) / `frozen=True` (case 03) |

## Cách chạy nhanh tất cả

```bash
cd "Design patterns/19_Observer/hex_cases"
python3 01_event_bus_core/event_bus_core.py
python3 02_event_logger_adapter/event_logger_adapter.py
python3 03_event_log_broadcast/event_log_broadcast.py
```

Cả ba thoát code 0, không traceback. Mọi I/O nặng (JSONL trên đĩa, ledger, kernel/LLM) đã được thay bằng fake stdlib (in-memory CSV/list), nên không đụng gì tới hệ thống thật.

## Vét cạn occurrence

Xem [`CATALOG.md`](./CATALOG.md) — bảng đầy đủ 24 vị trí Observer trong codebase, kèm `path:line` đã đối chiếu và độ rõ.
