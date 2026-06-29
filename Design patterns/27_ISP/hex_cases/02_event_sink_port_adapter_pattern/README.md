# Ca 02 — `EventSinkPort`: một Protocol hẹp nhất (1 method) cho event persistence

> ISP ở dạng tinh khiết: port chỉ có **đúng một method** `emit(event)`. Mọi việc nặng (validate, đánh seq, redact secret) nằm ở phía trước trong `EventEmitter`; sink chỉ persist. Thêm Kafka/Redis là *thêm adapter*, không sửa caller.

---

## 1. Bối cảnh trong hex_agent

Realtime Control Plane (Epic E21) cần một **đường publish event duy nhất, đã được validate/seq/redact** — thay cho `bus.publish(topic, dict)` rải rác. Vấn đề thiết kế: làm sao để v1 dùng in-process `EventBus` → JSONL, nhưng sau này (tier T2) thả vào một adapter Kafka/Redis/Postgres **mà không đụng** emitter, supervisor, hay kernel?

Lời giải ISP: định nghĩa một port **cực hẹp** `EventSinkPort` (`control/ports.py:14-22`) chỉ gồm `emit(event)`. `EventEmitter` (`control/emitter.py:39-61`) cầm một `Iterable[EventSinkPort]` và làm hết phần nặng — gate `event_type` theo registry, stamp `seq` đơn điệu per-session, redact secret theo visibility — **rồi mới** fan-out tới từng sink. Adapter `BusEventSink` (`control/emitter.py:28-36`) chỉ việc đẩy envelope vào `EventBus`. Docstring của port ghi thẳng: "T2: a Kafka adapter implementing the same `emit` is dropped in with no caller change."

Đã mở kiểm chứng:
- `control/ports.py:14-22` — `EventSinkPort` chỉ `emit`
- `control/emitter.py:28-36` — `BusEventSink`
- `control/emitter.py:39-61` — `EventEmitter.__init__` + `emit_event` (validate → seq → redact → fan-out)
- `control/emitter.py:93-95` — `bus_emitter` helper

## 2. Trích đoạn code thật

Port hẹp nhất — `control/ports.py:14-22`:

```python
@runtime_checkable
class EventSinkPort(Protocol):
    """A durable/transport sink the emitter forwards each finalized event to.

    v1 impl: ``BusEventSink`` (in-process EventBus → EventLogger JSONL). T2: a Kafka
    adapter implementing the same ``emit`` is dropped in with no caller change.
    """

    def emit(self, event: RuntimeEvent) -> None: ...
```

Adapter chỉ persist — `control/emitter.py:28-36`:

```python
class BusEventSink:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def emit(self, event: RuntimeEvent) -> None:
        self._bus.publish(event.event_type, event.as_dict())
```

Caller làm việc nặng rồi fan-out qua port hẹp — `control/emitter.py:53-61`:

```python
def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
    spec = self._registry.get(event.event_type)  # ControlContractError if unknown
    staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
    final = self._redactor.apply(staged, level=spec.visibility)
    for sink in self._sinks:
        sink.emit(final)
    return final
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò ISP | Trong file `.py` của ca này | Trong hex_agent thật |
|-------------|------------------------------|----------------------|
| Port hẹp (1 method) | `EventSinkPort` | `control/ports.py:14-22` |
| Adapter v1 (transport) | `BusEventSink` (+ `EventBus`) | `control/emitter.py:28-36` |
| Adapter swap-in (T2) | `FakeKafkaSink` | "Kafka adapter" (T2, doc trong port) |
| Adapter cho test | `MockEventSink` | dùng trong test suite của emitter |
| Client phụ thuộc port hẹp | `EventEmitter` | `control/emitter.py:39-61` |
| Việc nặng đặt TRƯỚC sink | `EventTypeRegistry` / `Redactor` / `SessionSeq` | `event_registry` / `redaction.Redactor` / `events.SessionSeq` |
| Helper lắp sink mặc định | `bus_emitter(...)` | `control/emitter.py:93-95` |

## 4. Bản rút gọn chạy được

File: [`event_sink_port_adapter_pattern.py`](event_sink_port_adapter_pattern.py) — chạy `python3 event_sink_port_adapter_pattern.py`.

Nó **mô phỏng**: port `EventSinkPort` một-method; ba adapter (`BusEventSink`, `FakeKafkaSink`, `MockEventSink`) implement đúng `emit()`; `EventEmitter` gate event_type qua registry, stamp seq, redact secret, rồi fan-out; sáu bước demo gồm multi-sink swap-in "Kafka" mà không đổi caller, redact secret trước sink, và registry chặn event lạ trước khi publish.

Nó **lược bỏ**: `EventBus`/`EventLogger` JSONL thật (thay bằng list trong RAM), registry load từ file (thay bằng dict), `Redactor` đầy đủ (thay bằng quy tắc "xoá key chứa 'secret'"), `TraceContext`/`Actor`/`RedactionInfo` đầy đủ của `RuntimeEvent`.

Đối chứng: `FatSinkPort` (4 method validate+stamp_seq+redact+persist) cho thấy nếu port "béo" thì mỗi adapter phải copy lại 3 logic chung; assert chứng minh `BusEventSink` **không** conform `FatSinkPort` (nó hẹp đúng 1 method), và khi validate fail thì **không** sink nào được gọi.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Logic chung tập trung ở một chỗ**: validate/seq/redact dồn vào `EventEmitter`. Nếu một transport *thật sự* cần seq/redact khác nhau, đặt nó trong sink lại hợp lý hơn — nhưng đó là ngoại lệ, không phải mặc định.
- **Port 1-method dễ bị lạm dụng thành "callback rỗng nghĩa"**: nếu nhiều sink cần thêm `flush()`, `close()` (lifecycle), cân nhắc một port hẹp thứ hai thay vì nhồi vào `EventSinkPort` — đừng để nó phình thành fat interface.
- Với hệ chỉ có một transport duy nhất và không có biên redeploy, tách port là over-engineering nhẹ; nhưng ở đây biên T2 (Kafka/Redis/Postgres) là có thật nên tách là đúng.

## 6. Câu hỏi tự kiểm tra

1. Vì sao validate/seq/redact được đặt trong `EventEmitter` chứ không trong từng sink? Nếu đặt trong sink (fat sink) thì khi thêm `KafkaSink` bạn phải làm thêm những gì?
2. `EventEmitter` cầm `Iterable[EventSinkPort]`. Điều này cho phép làm gì mà một tham số `sink: BusEventSink` cụ thể không cho?
3. Trong demo, khi `event_type` lạ thì có sink nào được gọi không? Câu trả lời này liên quan thế nào tới "validate đứng trước port"?
