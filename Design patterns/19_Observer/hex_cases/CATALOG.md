# CATALOG — Mọi occurrence của Observer trong hex_agent

Bảng vét cạn các nơi pattern Observer (publish/subscribe, notify-1-tới-N, callback-as-observer) xuất hiện. Mỗi dòng đã được **mở file đối chiếu số dòng** tại thời điểm soạn (codebase gốc `/Users/uspro/Desktop/namnson/hex_agent`). Cột "độ rõ" theo đánh giá trong plan discover (đã hiệu chỉnh số dòng nơi lệch).

| # | path:line | Mô tả vai trò Observer | Độ rõ |
|---|-----------|------------------------|-------|
| 1 | `core/events.py:11-31` | **Subject lõi.** `EventBus` giữ `_subscribers` (list Observer), `subscribe`=attach, `publish`=notify. Cô lập lỗi (29-31) + deepcopy tách rời payload (25, 28) + RLock (16). → **Case 01.** | cao |
| 2 | `observability/event_log.py:102-134` | **ConcreteObserver dạng closure.** `attach_to_bus` tạo `sink` (105-132): quan sát topic+payload, lọc theo loại, gom metric, ghi JSONL; `bus.subscribe(sink)` (134). → **Case 02.** | cao |
| 3 | `observability/event_log.py:60-73` | `EventLogger.emit`: state của observer — seq đơn điệu dưới lock (61-62), ghi 1 dòng durable (71-72). | cao |
| 4 | `drag_from_zero/dragzero/events.py:46-91` | **Subject append-only.** `EventLog._subs` là list Observer (55), `append`=notify (58-65, durable trước broadcast tại 61-62), `subscribe`=attach (75-76), `replay` (67-73). → **Case 03.** | cao |
| 5 | `drag_from_zero/dragzero/events.py:37-43` | **Event bất biến** `@dataclass(frozen=True)` — observer không mutate được, chống corrupt view chung. | cao |
| 6 | `control/emitter.py:59-60` | `EventEmitter.emit_event` fan event ra N sink: `for sink in self._sinks: sink.emit(final)`. Mỗi sink là Observer (`EventSinkPort`). | cao |
| 7 | `control/emitter.py:35-36` | `BusEventSink.emit` — ConcreteObserver cụ thể: nhận `RuntimeEvent` rồi `bus.publish(...)`. Adapter sink → EventBus. | cao |
| 8 | `control/ports.py:14-22` | **Observer interface** dạng Protocol: `EventSinkPort` chỉ có `emit(event)`. Nhiều impl (BusEventSink, tương lai KafkaSink) thoả mà không sửa emitter — textbook. | cao |
| 9 | `ui/ide/bridge.py:38-45` | `KernelEventBridge.subscriber(topic, payload)` — Observer gắn qua `kernel.events.subscribe(bridge.subscriber)`; nhận event kernel, dịch sang event UI. Chữ ký `(topic, payload)` khớp `Subscriber`. | cao |
| 10 | `ui/ide/runner.py:147-148` | **1-tới-N thực chiến:** `kernel.events.subscribe(bridge.subscriber)` + `attach_to_bus(EventLogger(...), kernel.events)` — hai observer độc lập trên cùng bus. | cao |
| 11 | `ui/ide/session.py:63-90` | `IdeSession.emit` là Subject method; dòng 89 `self._cond.notify_all()` đánh thức các SSE drainer — observer đợi trên Condition variable. | trung bình |
| 12 | `ui/ide/session.py:98-103` | `drain()` — observer đọc buffer khi được `notify_all` đánh thức (wait/notify variant của Observer). | trung bình |
| 13 | `tests/test_event_concurrency.py:9-21` | `test_subscribers_receive_detached_payloads`: 2 observer (mutate + append) chứng minh deepcopy chặn lan truyền mutation. → bằng chứng cho **Case 01**. | cao |
| 14 | `tests/test_event_concurrency.py:24-41` | Logger là observer; 10 thread × 25 event = 250; seq vẫn `[1..251]`, không mất/trùng. → bằng chứng cho **Case 02**. | cao |
| 15 | `tests/test_control_emitter.py:25-28` | `_collector(bus)`: tạo observer (lambda) bắt `(topic, payload)`. Mẫu observer tối thiểu dùng xuyên suốt test. | cao |
| 16 | `tests/test_control_emitter.py:93-109` | `test_emitter_durable_via_event_logger`: EventLogger gắn vào bus, publish, rồi verify JSONL — observer ghi durable stream. | cao |
| 17 | `tests/test_control_emitter.py:112-136` | `SupervisorContext.emit` → EventEmitter fan ra N sink; verify seq đơn điệu (75) + redaction áp cho mọi sink. Observer lồng: ctx → emitter → sinks. | trung bình |
| 18 | `drag_from_zero/tests/unit/test_events.py:29-36` | `test_subscribe_fires_on_every_append_with_stamped_event`: observer nhận mọi event đã đóng dấu seq. → bằng chứng **Case 03**. | cao |
| 19 | `drag_from_zero/tests/unit/test_events.py:39-45` | `test_subscribe_after_appends_only_sees_future_events`: biến thể **late subscription** — observer vào sau chỉ thấy `[1]`. → **Case 03**. | trung bình |
| 20 | `drag_from_zero/tests/unit/test_events.py:90-93` | `test_event_is_frozen_dataclass`: gán `e.seq=99` → `FrozenInstanceError`. Bất biến frozen của Event. → **Case 03**. | cao |
| 21 | `middleware/condense.py:15,28-29` | `CondenseResult` nhận callback `on_condense` (15); khi tool result bị condense, gọi callback notify observer (28-29). Biến thể callback đơn giản (chưa phải Observer đầy đủ). | thấp |
| 22 | `run_smoke.py:13` | `attach_to_bus(logger, kernel.events)` — ví dụ wiring observer tối giản (smoke không LLM/network). | cao |
| 23 | `ui/server.py:241` | `attach_to_bus(logger, kernel.events)` — wiring observability trong ngữ cảnh IDE backend chạy thật. | trung bình |
| 24 | `drag_from_zero/dragzero/server.py:307-317` | `subscribe()/unsubscribe()` quản lý set subscriber cho SSE; `log.events()` trả bản sao GIL-atomic để đọc graph từ thread khác an toàn. Observer + cân nhắc thread-safety. | thấp |

> Ghi chú hiệu chỉnh số dòng so với plan discover: mục 11/12 (`session.py`) — `notify_all` ở dòng **89**, `drain` ở **98-103**; mục 22 (`run_smoke.py`) — `attach_to_bus` ở dòng **13** (plan ghi 1-5 là vùng docstring/import); mục 23 (`ui/server.py`) — ở dòng **241** (plan ghi 49-50 là vùng hằng số `SENSITIVE_NAMES`); mục 24 (`dragzero/server.py`) — `subscribe/unsubscribe` thực ở **307-317** (plan ghi 15-16 là docstring). Các mục còn lại khớp plan.
