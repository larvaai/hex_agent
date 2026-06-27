# Case 02 — Event Emission & Sink Pipeline (đường publish CQRS)

> Distill từ `control/emitter.py`, `observability/event_log.py`, `core/events.py`, `control/redaction.py` trong hex_agent. File chạy được: [`event_emission_pipeline.py`](./event_emission_pipeline.py).

Case 01 lo phần **read** (fold event → snapshot). Case này lo phần **write/publish**: một event đi qua đúng MỘT chokepoint — *validate → stamp seq → redact → fan-out → append-only log*. Ba thành phần (`EventEmitter` + `EventBus` + `EventLogger`) hợp thành xương sống kiểu Event Sourcing: event log là system-of-record cho audit/replay, subscriber không thể làm hỏng nó.

---

## 1. Bối cảnh trong hex_agent

Trước Epic E21, mỗi nơi tự gọi `bus.publish(topic, dict)` tuỳ tiện. Hệ quả: event type tự chế (không ai kiểm), secret lọt ra UI, seq không nhất quán nên UI không order/dedup được. E21 đặt ra **một đường publish duy nhất** để mọi event control-plane đi qua.

Vấn đề thật, kiểm chứng tại file:
- `control/emitter.py:53-61` — `EventEmitter.emit_event()`: (1) `registry.get(event_type)` raise nếu type lạ; (2) stamp `seq` monotonic per-session; (3) `Redactor.apply` điền `ui_payload` đúng visibility; (4) fan-out tới từng `EventSinkPort`.
- `control/event_registry.py:47-55` — `assert_known`/`get`: catalog event hợp lệ; type lạ bị từ chối **trước** khi publish (event là contract).
- `control/redaction.py:44-73` — `redact`/`_walk`/`apply`: mask key secret đệ quy (dict + list), không mutate payload gốc.
- `observability/event_log.py:60-99` — `EventLogger.emit`: append JSONL dưới lock, `seq` tăng dần, đếm metrics; là append-only event store.
- `core/events.py:22-31` — `EventBus.publish`: giao **detached deep-copy** cho từng subscriber → không observer nào mutate được dữ liệu observer khác thấy.

Test thật chứng minh xương sống vững dưới đồng thời:
- `tests/test_event_concurrency.py:9-21` — subscriber nhận payload detached (mutator không phá observer).
- `tests/test_event_concurrency.py:24-41` — 10 worker × 25 event: JSONL có đúng 251 dòng, `sequence == 1..251`.

---

## 2. Trích đoạn code thật

Chokepoint publish (`control/emitter.py:53-61`):

```python
def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
    """Validate, stamp seq, redact, then fan out to sinks. Returns the finalized event.
    An unknown event_type raises before anything is published (registry is the gate)."""
    spec = self._registry.get(event.event_type)  # ControlContractError if unknown
    staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
    final = self._redactor.apply(staged, level=spec.visibility)
    for sink in self._sinks:
        sink.emit(final)
    return final
```

EventBus giao bản copy riêng — bất biến của event log (`core/events.py:22-31`):

```python
def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
    with self._lock:
        subscribers = tuple(self._subscribers)
    data = copy.deepcopy(payload or {})
    for fn in subscribers:
        try:
            fn(topic, copy.deepcopy(data))   # mỗi subscriber một bản RIÊNG
        except Exception:
            pass                             # observer không bao giờ làm sập runtime
```

Append-only JSONL dưới lock, seq tăng đơn điệu (`observability/event_log.py:60-73`):

```python
def emit(self, kind: str, **fields: Any) -> dict[str, Any]:
    with self._lock:
        self.seq += 1
        event = {"sequence": self.seq, "timestamp": _now(), "run_id": self.run_id, "kind": kind, **fields}
        if self.enabled:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event
```

Redactor mask secret nhưng không đụng bản gốc (`control/redaction.py:65-73`):

```python
def apply(self, event: RuntimeEvent, *, level: str | None = None) -> RuntimeEvent:
    """Return a copy of ``event`` with ``ui_payload`` + ``redaction`` filled from ``payload``."""
    ui_payload, fields = self.redact(event.payload)
    info = RedactionInfo(level=level or event.redaction.level, has_secret=bool(fields), redacted_fields=tuple(fields))
    return replace(event, ui_payload=ui_payload, redaction=info)
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò CQRS + ES | Trong hex_agent (file:line) | Trong bản distill (`event_emission_pipeline.py`) |
|---|---|---|
| **Command handler / emit pipeline** | `EventEmitter.emit_event`, `control/emitter.py:53-61` | `EventEmitter.emit_event` |
| **Event contract / catalog** | `EventTypeRegistry`, `control/event_registry.py:47-55` | `EventTypeRegistry.get` |
| **Seq allocator (order/dedup)** | `SessionSeq`, `control/events.py:193-212` | `SessionSeq.next` |
| **Redaction-as-policy** | `Redactor.apply`, `control/redaction.py:65-73` | `Redactor.apply` |
| **Event Bus (pub/sub broadcaster)** | `EventBus.publish`, `core/events.py:22-31` | `EventBus.publish` (detached deep-copy) |
| **Append-only event store** | `EventLogger.emit`, `observability/event_log.py:60-99` | `EventLogger.subscriber` (JSONL in-memory) — distill gấp logic append của `emit()` vào callback `subscriber()` để gắn thẳng vào bus (`bus.subscribe(logger.subscriber)`); cùng append-under-lock + tăng seq, chỉ khác điểm vào |
| **Idempotency (at-least-once)** | dedup theo `event_id` (`control/replay.py:28-39`) | `_seen_ids` trong `EventLogger` |
| **Sink port (swap Kafka sau)** | `BusEventSink`, `control/emitter.py:28-36` | `BusEventSink` |

---

## 4. Bản rút gọn chạy được

File [`event_emission_pipeline.py`](./event_emission_pipeline.py) **chỉ dùng stdlib**, mô phỏng và kiểm chứng đúng 4 tính chất plan yêu cầu:
1. 10 worker × 5 event đồng thời → cả 50 landed trong "JSONL", `sequence` logger liên tục `1..50`, và `seq` per-session (`SessionSeq`) cũng `1..50`.
2. **Idempotency**: phát lại cùng `event_id` → bị bỏ (đếm `duplicates`).
3. **Detached delivery**: subscriber mutate payload → observer khác vẫn thấy bản gốc.
4. **Redaction**: `ui_payload.api_key == "[REDACTED]"` nhưng `payload.api_key` raw giữ nguyên cho nội bộ/audit.

Đối chứng đầu file: emit `event_type` lạ → `ControlContractError`, và **không event nào lọt vào log** (gate chặn trước).

Đã **lược bỏ** so với code thật để giữ self-contained:
- File JSONL trên đĩa + `summary.json` + `index.jsonl` → thay bằng `io.StringIO` (vẫn append-only, vẫn dedup).
- Registry nạp từ YAML → dict tĩnh.
- `RedactionInfo` đầy đủ (level/has_secret/redacted_fields), `actor`/`trace`/`schema_version` của envelope, metrics nghiệp vụ chi tiết — giữ đúng phần load-bearing.
- LangGraph/Kafka/SSE thật.

Chạy:
```bash
python3 event_emission_pipeline.py   # exit 0, in narration từng bước
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chokepoint là điểm nghẽn tiềm tàng**: mọi event qua một đường → cần lock cẩn thận (hex_agent dùng `RLock` ở bus + logger). Hot path cực cao có thể cần batching/async sink.
- **Deep-copy mỗi subscriber tốn CPU/bộ nhớ**: payload lớn × nhiều subscriber × tần suất cao = đắt. Đổi lại là an toàn bất biến — cân nhắc nếu throughput là tối thượng.
- **Append-only nghĩa là không xoá**: log phình mãi; cần archive/rotate. Với GDPR right-to-erasure phải dùng crypto-shredding / tombstone (xem trade-off trong bài gốc).
- Nếu app single-thread, không cần audit/replay, không có secret → một `bus.publish` trần là đủ; pipeline này thừa.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `emit_event` gọi `registry.get(event.event_type)` **trước** khi stamp/redact/fan-out? Nếu đảo thứ tự (fan-out trước, validate sau) thì hỏng gì?
2. `EventBus.publish` deep-copy payload **hai lần** (một cho `data`, một cho mỗi subscriber). Bỏ lần copy thứ hai thì kịch bản "subscriber A mutate, subscriber B đọc nhầm" xảy ra thế nào? (Đối chiếu `tests/test_event_concurrency.py:9-21`.)
3. Idempotency theo `event_id` giải quyết hệ quả nào của *at-least-once delivery*? Vì sao redact tách `payload`/`ui_payload` lại là một dạng "read-model scoping" (giới hạn ai thấy gì)?
