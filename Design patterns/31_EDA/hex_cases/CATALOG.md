# CATALOG — mọi occurrence của Event-Driven Architecture trong `hex_agent`

> Bảng vét cạn các điểm thực thi/đụng chạm EDA trong codebase. **Mọi `path:line` đã được mở lại và xác minh** so với cây nguồn thật tại `/Users/uspro/Desktop/namnson/hex_agent/`. Độ rõ: **cao** = vai EDA hiển nhiên tại chính dòng đó; **trung bình** = đúng vai nhưng cần đọc ngữ cảnh xung quanh; **thấp** = liên quan gián tiếp / chỉ là điểm phát event lẻ.

> Ghi chú hiệu chỉnh: tham chiếu test EventBus trong plan ban đầu ghi `181-228` nhưng các test bus thực sự nằm ở **`tests_audit/test_core_edges_rigor.py:519-578`** (đã sửa). Tham chiếu `core/kernel.py:181-190` được mở rộng thành **`179-190`** để bao trọn `def on_skip`.

---

## Bus lõi — `core/events.py`

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `core/events.py:8` | `Subscriber = Callable[[str, dict[str, Any]], None]` — chữ ký handler thuần hàm (topic, payload). | cao |
| `core/events.py:11-31` | `class EventBus` — pub/sub tối thiểu, thread-safe. Trái tim EDA của hex_agent. | cao |
| `core/events.py:14-16` | `_subscribers: list` + `_lock: RLock` — đăng ký thread-safe. | cao |
| `core/events.py:18-20` | `subscribe(fn)` — thêm subscriber dưới lock. | cao |
| `core/events.py:22-31` | `publish(topic, payload)` — deepcopy payload, snapshot subscriber dưới lock (dòng 23-24), giao deepcopy riêng cho từng người (dòng 28), nuốt exception per-subscriber (dòng 29-31). Fire-and-forget. | cao |

---

## Producer lõi — `core/kernel.py`, `core/bootstrap.py`

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `core/kernel.py:9` | `from core.events import EventBus` — kernel sở hữu `events: EventBus`, chia sẻ cho mọi session/run của instance. | cao |
| `core/kernel.py:86` | `events: EventBus` — field của `AgentKernel` (bus dùng chung suốt vòng đời kernel). | cao |
| `core/kernel.py:123-126` | publish `tool.requested` TRƯỚC khi chạy tool; mang `tool`, `request_id`, `args`, lineage (run_id/task_id/session_id...). | cao |
| `core/kernel.py:140-150` | publish `tool.failed` (scope_block) khi tool ngoài `allowed_capabilities`. Là event, không phải exception. | cao |
| `core/kernel.py:179-190` | `def on_skip` → publish `middleware.skipped` khi middleware fail-open (advisory) raise và bị bỏ qua. Observability cho middleware bị skip. | trung bình |
| `core/kernel.py:215-224` | publish `tool.completed`/`tool.failed` SAU khi chạy tool. Consumed bởi observability, UI bridge, metrics. Fire-and-forget — kernel return ngay. | cao |
| `core/bootstrap.py:56-66` | `build_kernel`: tạo `EventBus()` và truyền vào `AgentKernel`. Đây là instance bus in-process dùng chung cho vòng đời kernel. | cao |

---

## Generator event của graph — `graph/nodes.py`, `orchestrator/loop.py`

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `graph/nodes.py:29-37` | `def _emit(session, topic, state, **payload)` — helper phát event cấp graph qua `session.kernel.events.publish(topic, {...})`. Mỗi node loop gọi nó để phát `graph.step`, `graph.parse_error`, `graph.completed`, `graph.budget_blocked`, `graph.finish_blocked`. | cao |
| `graph/nodes.py:67` | `_emit(..., "graph.parse_error", ...)` — phát khi parse output LLM lỗi (UI bridge map → `loop.parse_error`). | trung bình |
| `graph/nodes.py:86` | `_emit(..., "graph.step", ...)` — phát mỗi bước loop (EventLogger đếm `steps`). | trung bình |
| `graph/nodes.py:212,233,249` | `_emit(..., "graph.completed", ...)` — phát khi loop kết thúc (completed/failed). | trung bình |
| `orchestrator/loop.py:69-90` | `_stream`: lặp `graph.stream(..., stream_mode="values")`, lưu projection mỗi vòng. Graph nội bộ phát state-transition qua các node; stream yield state cuối. | trung bình |

---

## Consumer observability — `observability/event_log.py`

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `observability/event_log.py:41-58` | `EventLogger.__init__` — tạo run dir, mở `events.jsonl`, khởi tạo dict `metrics`, emit event khởi động. | cao |
| `observability/event_log.py:60-73` | `EventLogger.emit(kind, **fields)` — tăng seq, timestamp, ghi 1 dòng JSON. | cao |
| `observability/event_log.py:102-134` | `attach_to_bus(logger, bus)` — `bus.subscribe(sink)`; `sink(topic, payload)` mirror event kernel vào JSONL (`logger.emit`) + cập nhật metrics theo topic. Subscriber fan-out thuần, không return, không block. | cao |

---

## Control plane — registry + envelope + emitter

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `config/runtime_event_types.yaml:11-83` | Registry ~52 event_type qua các lifecycle session/agent/hook/skill/tool/permission/approval/command/artifact/loop. Mỗi cái khai báo `visibility`, `durable`, `redact_for_ui`, `checkpoint_candidate`. | cao |
| `control/event_registry.py:22-37` | `EventTypeSpec` — `@dataclass(frozen=True)`, contract bất biến cho 1 event_type. | cao |
| `control/event_registry.py:40-61` | `EventTypeRegistry` — `assert_known` (47-51) raise `ControlContractError` nếu type lạ; `get`/`visibility`/`types`. | cao |
| `control/event_registry.py:64-93` | `parse_event_registry` — ép tên có dấu chấm, ép visibility ∈ `VISIBILITY_LEVELS`, dựng spec immutable. | cao |
| `control/event_registry.py:96-99` | `load_event_registry(path)` — đọc YAML → parse → registry. | trung bình |
| `control/events.py:24-25` | `ACTOR_TYPES`, `VISIBILITY_LEVELS` — bộ giá trị hợp lệ cho actor & visibility. | cao |
| `control/events.py:32-51` | `@dataclass(frozen=True) Actor` — ai/cái gì gây ra event; validate type/id. | cao |
| `control/events.py:53-83` | `@dataclass(frozen=True) TraceContext` — trace_id/span_id/parent + `new_root`/`child` cho distributed tracing. | trung bình |
| `control/events.py:85-110` | `@dataclass(frozen=True) RedactionInfo` — level + has_secret + redacted_fields. | cao |
| `control/events.py:113-151` | `@dataclass(frozen=True) RuntimeEvent` — envelope bất biến: event_id(UUID), event_type, session_id, actor, trace, redaction, schema_version, seq, payload, ui_payload. `__post_init__` validate mọi field. | cao |
| `control/events.py:153-190` | `RuntimeEvent.as_dict`/`from_dict` — serialize/deserialize envelope (dùng bởi sink/replay). | trung bình |
| `control/events.py:193-213` | `SessionSeq` — cấp seq đơn điệu per-session, thread-safe (RLock). Cho phép order/dedup khi delivery out-of-order. | cao |
| `control/emitter.py:28-36` | `BusEventSink.emit(event)` — adapt `RuntimeEvent` → `bus.publish(event_type, event.as_dict())`. Cầu nối envelope control-plane ↔ topic bus legacy. | trung bình |
| `control/emitter.py:39-51` | `EventEmitter.__init__` — nhận sinks + registry + redactor + seq. | cao |
| `control/emitter.py:53-61` | `EventEmitter.emit_event` — (1) `registry.get(type)` [gate], (2) stamp seq nếu thiếu, (3) `redactor.apply` theo visibility, (4) fan-out tới sinks. Trả về event đã finalize. | cao |
| `control/emitter.py:63-90` | `EventEmitter.emit(...)` — builder tiện dụng dựng `RuntimeEvent` rồi gọi `emit_event`. | trung bình |
| `control/emitter.py:93-95` | `bus_emitter(bus)` — factory ráp `EventEmitter` lên `EventBus` qua `BusEventSink`. Đổi sang Kafka chỉ là sink mới. | cao |
| `control/ports.py:14-22` | `EventSinkPort` (Protocol) — `emit(event: RuntimeEvent) -> None`. Trừu tượng nơi event đến; `BusEventSink` là 1 impl, Kafka/Redis là impl tương lai (T2). | cao |
| `control/redaction.py:16-34` | `SECRET_KEYS` + `REDACTED` — danh sách key bị mask. | trung bình |
| `control/redaction.py:37-73` | `Redactor` — tách `payload` → `ui_payload`, mask secret đệ quy (dict + list), không mutate bản gốc; `apply` điền `ui_payload` + `RedactionInfo` theo level. | trung bình |
| `control/replay.py:23-39` | `EventReplayBuffer` — ring buffer (maxlen 2048) dedup theo `event_id`. | trung bình |
| `control/replay.py:61-81` | `needs_resync` + `events_after` — catch-up theo seq cho SSE, phát hiện resync khi event rớt khỏi ring. Tách generation khỏi consumption. | trung bình |

---

## UI bridge / runner / session — EDA đa tầng

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `ui/ide/bridge.py:32-44` | `KernelEventBridge` — subscriber có trạng thái giữ `_pending {request_id -> {tool, path}}`; `subscriber(topic, payload)` gắn qua `kernel.events.subscribe`, never raise. | cao |
| `ui/ide/bridge.py:46-86` | `_handle` — pattern-match topic: `tool.requested` lưu meta; `tool.completed/failed` correlate qua `request_id` + `session.emit("loop.tool")`; `graph.parse_error` → `loop.parse_error`. | cao |
| `ui/ide/bridge.py:88-96` | `_extract_path(args)` — nhấc `args["path"]` để hiện trên timeline. | trung bình |
| `ui/ide/runner.py:123-158` | `AgentRunner._run` — tạo kernel, subscribe bridge, attach EventLogger, chạy agent. | cao |
| `ui/ide/runner.py:147-148` | `kernel.events.subscribe(bridge.subscriber)` + `attach_to_bus(EventLogger(...), kernel.events)` — NHIỀU subscriber độc lập trên 1 bus. | cao |
| `ui/ide/runner.py:105-116` | runner phát event mở run (`chat.user`, `loop.team_composed`, `loop.decision`). | trung bình |
| `ui/ide/runner.py:175-182` | runner phát event đóng run (`loop.turn`, `loop.finished`, `chat.assistant`). | trung bình |
| `ui/ide/session.py:64-90` | `IdeSession.emit` — dưới `Condition`: cấp seq, redact, append vào `EventReplayBuffer`, notify reader SSE. Chỗ DUY NHẤT event vào buffer. | cao |
| `ui/ide/session.py:98-103` | `drain(last_seq, timeout)` — trả event mới sau seq + cờ resync; sleep nếu chưa có gì (không busy-poll). | trung bình |

---

## Test bám sát hành vi EDA — `tests_audit/test_core_edges_rigor.py`

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `tests_audit/test_core_edges_rigor.py:523-529` | `test_publish_with_none_payload_delivers_empty_dict` — `publish(topic)` không payload giao dict rỗng mới cho mỗi subscriber. | cao |
| `tests_audit/test_core_edges_rigor.py:532-540` | `test_each_subscriber_gets_its_own_detached_payload_copy` — mutate ở subscriber này không ảnh hưởng subscriber kia (deepcopy mỗi delivery). | cao |
| `tests_audit/test_core_edges_rigor.py:543-559` | `test_subscriber_added_during_publish_does_not_receive_current_event` — snapshot list dưới lock trước khi giao; subscriber đăng ký giữa chừng không nhận event đang bay. | cao |
| `tests_audit/test_core_edges_rigor.py:562-578` | `test_concurrent_subscribe_and_publish_never_corrupts_registry` — interleave subscribe/publish đa luồng không crash, không vỡ invariant. | cao |
| `tests_audit/test_core_edges_rigor.py:223-233` | `test_fail_task_publishes_task_failed_with_reason` — subscribe bus rồi assert topic `task.failed` được phát; minh hoạ consumer test pattern. | trung bình |
