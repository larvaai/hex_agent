# Case 03 — Event Control Plane: driven port `EventSinkPort` + adapter (Future Expansion)

> Case này dạy **Future Expansion** của Hexagonal: lõi `EventEmitter` chỉ biết một method `emit(event)`.
> Hôm nay sink là in-process bus (v1); ngày mai là Kafka/Redis (T2) — **thêm một adapter, không sửa lõi**.
> Codebase nói thẳng điều này trong docstring của port.

---

## 1. Bối cảnh trong hex_agent

Mọi event của control plane phải đi qua **một** đường publish được validate + redact + stamp seq. Nhưng
*đích đến* của event (transport/storage) phải thay được: v1 là in-process `EventBus` ghi JSONL; về sau có thể
là Kafka, Redis, Postgres. hex_agent tách đích đến sau một **driven port** `EventSinkPort` — đúng một method.

- `control/ports.py:14-22` — `EventSinkPort` (Protocol) với một method `emit(event)`. Docstring ghi rõ tầm nhìn:
  > "v1 impl: `BusEventSink` ... T2: a Kafka adapter implementing the same `emit` is dropped in with no caller change."
- `control/emitter.py:28-36` — `BusEventSink` (adapter v1): adapt `EventBus`, publish dict event dưới `topic=event_type`.
- `control/emitter.py:39-90` — `EventEmitter` (lõi): validate `event_type` qua registry → stamp `seq` monotonic →
  redact `ui_payload` theo visibility → fan-out tới từng `EventSinkPort`.
- `control/emitter.py:93-95` — `bus_emitter()`: composition root nhỏ, trả `EventEmitter([BusEventSink(bus)])`.
- `tools/gen_t1_fixture.py:30-42` — `_Collect`: một `EventSinkPort` tự chế (fake adapter) chỉ gom event vào list,
  chứng minh "viết một sink mới = vài dòng, lõi không đổi".

Tầm nhìn kiến trúc (`control/ports.py:1-6`):
> "These Protocols are the swap points so Kafka/Redis/Postgres adapters can land later WITHOUT touching the
> emitter, supervisor, or kernel (the T2 tier)."

---

## 2. Trích đoạn code thật

Driven port — một method duy nhất (`control/ports.py:14-22`):

```python
@runtime_checkable
class EventSinkPort(Protocol):
    """A durable/transport sink the emitter forwards each finalized event to.

    v1 impl: ``BusEventSink`` (in-process EventBus → EventLogger JSONL). T2: a Kafka
    adapter implementing the same ``emit`` is dropped in with no caller change.
    """
    def emit(self, event: RuntimeEvent) -> None: ...
```

Adapter v1 — adapt bus (`control/emitter.py:28-36`):

```python
class BusEventSink:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
    def emit(self, event: RuntimeEvent) -> None:
        self._bus.publish(event.event_type, event.as_dict())
```

Lõi — chỉ gọi `sink.emit()`, không biết transport (`control/emitter.py:53-61`):

```python
def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
    spec = self._registry.get(event.event_type)   # ControlContractError nếu lạ
    staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
    final = self._redactor.apply(staged, level=spec.visibility)
    for sink in self._sinks:
        sink.emit(final)
    return final
```

---

## 3. Ánh xạ vai trò Hexagonal ↔ code thật

| Vai Hexagonal | Thành phần code thật (hex_agent) | Trong bản distill |
|---|---|---|
| **Driven Port** (một method `emit`) | `EventSinkPort` — `control/ports.py:14-22` | `EventSinkPort` |
| **Domain Core** (validate/seq/redact/fan-out) | `EventEmitter` — `control/emitter.py:39-90` | `EventEmitter` |
| **Driven Adapter v1** (in-process bus) | `BusEventSink` — `control/emitter.py:28-36` | `BusEventSink` + `EventBus` |
| **Driven Adapter fake** (test/fixture) | `_Collect` — `tools/gen_t1_fixture.py:30-42` | `MemorySink` |
| **Driven Adapter tương lai** (T2) | (Kafka adapter chưa tồn tại — chỉ là tầm nhìn trong docstring) | `KafkaLikeSink` |
| **Gate + Redactor** (lõi, mọi sink hưởng) | `EventTypeRegistry`, `Redactor`, `SessionSeq` — `control/event_registry.py`, `control/redaction.py` | `MiniRegistry`, `MiniRedactor`, `SessionSeq` |
| **Composition Root** | `bus_emitter()` — `control/emitter.py:93-95` | `bus_emitter()` |

---

## 4. Bản rút gọn chạy được

File: [`event_sink_hexagon.py`](./event_sink_hexagon.py) — chạy `python3 event_sink_hexagon.py`.

**Mô phỏng gì:**
- `EventSinkPort` đúng một method `emit(event)`.
- `EventEmitter` giữ nguyên pipeline: gate `event_type` qua `MiniRegistry` → stamp `seq` monotonic per session
  qua `SessionSeq` → redact `ui_payload` theo visibility qua `MiniRedactor` → fan-out tới mọi sink.
- Ba adapter cùng port: `BusEventSink` (v1), `MemorySink` (fake — distill `_Collect`), `KafkaLikeSink` (tương lai T2).
- Demo chứng minh: swap Bus → Memory không đổi lõi; thêm Kafka = thêm sink, fan-out tới nhiều sink cùng lúc;
  redact che `api_key` ở `ui_payload`; event_type lạ → `ControlContractError` **trước** khi bất kỳ sink nào nhận.

**Lược bỏ gì:**
- `EventTypeRegistry` load từ YAML → `MiniRegistry` với một dict tên→visibility.
- `Redactor` đầy đủ → `MiniRedactor` che vài secret key (`api_key`/`password`/`token`).
- `Actor`/`TraceContext` → `RuntimeEvent` giữ field cốt lõi (`event_type`, `session_id`, `payload`, `seq`, `ui_payload`).

Có một **phản ví dụ** `LeakyEmitter`: lõi cầm `EventBus` và gọi thẳng `bus.publish()` → bỏ qua seq + redact
(secret rò ra nguyên vẹn), và muốn thêm Kafka phải sửa lõi. Đây minh hoạ vì sao "một đường publish duy nhất sau port"
vừa cho pluggability vừa ép mọi event đi qua gate/redact.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Mãi mãi một transport**: nếu chắc chắn chỉ dùng in-process bus, port `EventSinkPort` là tầng gián tiếp thừa.
  Hex ở đây đáng vì có **lộ trình rõ ràng** (v1 bus → T2 Kafka) ghi ngay trong docstring.
- **Cám dỗ "smart sink"**: adapter chỉ được dịch transport, **không** được chứa business rule (vd quyết định
  có nên gửi event hay không). Quyết định ấy thuộc lõi `EventEmitter` (qua registry/visibility).
- **Fan-out âm thầm nuốt lỗi**: khi có nhiều sink, một sink lỗi nên xử lý ra sao? Bản thật để lỗi sink leo lên;
  nếu cần "best-effort" phải thiết kế thêm — đó là chi phí của fan-out qua port.
- **Over-engineer cho prototype**: với script 1 lần chạy, in thẳng ra stdout còn nhanh hơn dựng emitter + sink + registry.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao seq được stamp **trong lõi** `EventEmitter` chứ không phải trong từng adapter sink? Nếu mỗi sink tự đánh seq
   thì điều gì hỏng khi có hai sink (vd Last-Event-ID để resume)?
2. `EventSinkPort` chỉ có **một** method. So với `VectorStorePort` (Case 01, bốn method), việc thêm một adapter mới
   cho `EventSinkPort` dễ/khó hơn ra sao? Liên hệ nguyên tắc ISP.
3. Trong demo `[5]`, khi `event_type` lạ thì **không** sink nào nhận event. Hãy chỉ ra dòng nào trong `emit_event`
   bảo đảm bất biến "gate chặn trước fan-out", và vì sao đặt gate trước vòng `for sink` lại quan trọng cho bảo mật.
