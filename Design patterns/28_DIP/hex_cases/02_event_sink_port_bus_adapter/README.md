# Case 02 — `EventSinkPort`: trừu tượng định tuyến sự kiện cho các sink cắm-rút

> DIP (Dependency Inversion Principle) — SOLID Pattern 5
> Control plane (cấp cao) ĐỊNH NGHĨA `EventSinkPort`; hạ tầng transport (Bus/Kafka/Redis) ADAPT theo.

---

## 1. Bối cảnh trong hex_agent

Mọi sự kiện của control plane (tool started/finished, delegation progress…) đi qua một đường
xuất bản duy nhất: `EventEmitter`. Nó phải validate `event_type`, đóng dấu `seq` đơn điệu,
redact rồi đẩy ra "đâu đó" (in-process bus, sau này có thể là Kafka/Redis/Postgres).

Nếu `EventEmitter` gọi thẳng `bus.publish(topic, dict)` thì việc thêm Kafka/Redis về sau buộc
phải sửa `EventEmitter` (vi phạm OCP), và muốn test thì phải dựng bus thật. hex_agent giải bằng
DIP: cấp cao `control/` định nghĩa `EventSinkPort` (chỉ một method `emit(event)`); `BusEventSink`
là adapter bọc `EventBus`; `EventEmitter` nhận danh sách sink qua constructor (DI) và chỉ gọi
`sink.emit()`. Docstring `control/ports.py:1-5` nói rõ mục tiêu: Kafka/Redis adapter có thể "land
later WITHOUT touching the emitter".

File:line thật đã mở kiểm chứng:
- `control/ports.py:14-22` — `EventSinkPort` Protocol (abstraction do cấp cao sở hữu).
- `control/emitter.py:28-36` — `BusEventSink` (adapter bọc `EventBus`).
- `control/emitter.py:39-61` — `EventEmitter` (consumer nhận `Iterable[EventSinkPort]` qua DI).
- `control/emitter.py:93-95` — `bus_emitter()` factory.

---

## 2. Trích đoạn code thật

`control/ports.py:14-22` — abstraction + ghi chú swap point:

```python
@runtime_checkable
class EventSinkPort(Protocol):
    """A durable/transport sink the emitter forwards each finalized event to.

    v1 impl: ``BusEventSink`` (in-process EventBus → EventLogger JSONL). T2: a Kafka
    adapter implementing the same ``emit`` is dropped in with no caller change.
    """

    def emit(self, event: RuntimeEvent) -> None: ...
```

`control/emitter.py:28-36` — adapter bọc bus:

```python
class BusEventSink:
    """Adapts the in-process EventBus to EventSinkPort: publishes the envelope dict under
    ``topic=event_type`` so existing bus subscribers (e.g. EventLogger) persist it."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def emit(self, event: RuntimeEvent) -> None:
        self._bus.publish(event.event_type, event.as_dict())
```

`control/emitter.py:39-61` — consumer nhận sink qua DI, fan-out:

```python
class EventEmitter:
    def __init__(self, sinks: Iterable[EventSinkPort], *, registry=None, redactor=None, seq=None):
        self._sinks = list(sinks)
        ...
    def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
        spec = self._registry.get(event.event_type)   # ControlContractError nếu lạ
        staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
        final = self._redactor.apply(staged, level=spec.visibility)
        for sink in self._sinks:
            sink.emit(final)
        return final
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò DIP | Thành phần trong hex_agent | Trong bản rút gọn |
|---|---|---|
| Abstraction (do cấp cao sở hữu) | `EventSinkPort` — `control/ports.py:14-22` | `EventSinkPort` |
| Cấp cao tiêu thụ (consumer) | `EventEmitter` — `control/emitter.py:39-61` | `EventEmitter` |
| Adapter (production v1) | `BusEventSink` — `control/emitter.py:28-36` | `BusEventSink` |
| Cấp thấp cụ thể (transport) | `EventBus` — `core/events.py` | `EventBus` |
| Adapter tương lai (drop-in) | Kafka/Redis sink (T2, chưa code) | `FakeKafkaSink` (trong demo) |
| Fake cho test | (test doubles trong `tests_audit/`) | `InMemorySink` |
| Cổng gác hợp đồng | `EventTypeRegistry` — `control/event_registry.py` | `EventTypeRegistry` |
| Composition root / factory | `bus_emitter()` — `control/emitter.py:93-95` | `bus_emitter()` |

---

## 4. Bản rút gọn chạy được

File: `event_sink_port_bus_adapter.py` (chỉ thư viện chuẩn).

Mô phỏng đầy đủ: `EventSinkPort` Protocol; `BusEventSink` adapter; `EventEmitter` nhận sink qua
constructor và fan-out; validate `event_type` qua registry; đóng dấu `seq` đơn điệu theo session;
swap sink + fan-out nhiều sink; factory `bus_emitter()`.

Lược bỏ / thay bằng fake: `EventBus` JSONL/EventLogger thật → bus ghi vào list trong bộ nhớ;
`Redactor` + `RuntimeEvent` đầy đủ trường (actor/trace/redaction…) → `RuntimeEvent` rút gọn 4
trường; bỏ bước redact (giữ validate + seq + fan-out là phần cốt lõi của DIP).

Chạy:

```bash
python3 event_sink_port_bus_adapter.py
```

Bước [3]/[4] cho thấy đổi sink (InMemory) và thêm sink (`FakeKafkaSink`) mà `EventEmitter`
không đổi một dòng. Bước [7] là đối chứng nếu gọi thẳng `bus.publish`.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- Một lớp gián tiếp giữa emitter và transport. Với hệ chỉ-có-một-transport-mãi-mãi và không
  cần test cô lập, đây là chi phí thừa.
- Abstraction quá hẹp/quá rộng đều hại: nếu sink tương lai cần semantics khác hẳn (batch,
  ack, transaction) thì `emit(event)` một-event-một-lần có thể là wrong abstraction → phải
  sửa cả interface lẫn mọi adapter.
- Fan-out đồng bộ trong vòng lặp: một sink chậm/lỗi có thể chặn các sink sau — production cần
  cân nhắc cô lập lỗi (ngoài phạm vi case này).

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `EventTypeRegistry.get()` được gọi **trước** vòng lặp `for sink in self._sinks` lại
   quan trọng với bất biến "không sink nào thấy event không hợp lệ"?
2. Để thêm một `RedisEventSink`, bạn cần sửa `EventEmitter` không? Vì sao?
3. `InMemorySink` giúp gì cho việc unit-test logic của `EventEmitter` mà không cần `EventBus` thật?
