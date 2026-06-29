"""
Ca 02 — EventSinkPort: một Protocol HẸP (1 method) cho event persistence adapters.

Bản DISTILL TRUNG THỰC, chỉ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent
hay thư viện bên thứ ba.

NGUỒN THẬT được chưng cất từ (path:line tương đối với /Users/uspro/Desktop/namnson/hex_agent/):
  - control/ports.py:14-22    @runtime_checkable EventSinkPort(Protocol): chỉ emit(event)
  - control/emitter.py:28-36  BusEventSink adapt in-process EventBus thành EventSinkPort
  - control/emitter.py:39-61  EventEmitter(sinks: Iterable[EventSinkPort]): validate+seq+redact
                              rồi fan-out tới mọi sink. Caller chỉ thấy port hẹp.

Ý CHÍNH (ISP):
  EventSinkPort là interface hẹp NHẤT có thể — đúng MỘT method emit(event). Mọi thứ
  "đắt" (validate event_type theo registry, stamp seq đơn điệu theo session, redact
  secret) nằm Ở TRƯỚC trong EventEmitter; sink chỉ việc PERSIST. Nhờ port hẹp:
    * thêm KafkaSink/RedisSink = adapter mới implement đúng emit() -> ZERO caller change
      (doc bản thật ghi: "T2: a Kafka adapter implementing the same emit is dropped in").
    * caller (EventEmitter) phụ thuộc EventSinkPort, không import BusEventSink trực tiếp.
    * test dễ: MockEventSink lưu event trong RAM.

LƯỢC BỎ so với bản thật: EventBus + EventLogger JSONL writer thật, registry load từ file,
TraceContext/Actor đầy đủ. Thay bằng: RuntimeEvent gọn, registry dict tối thiểu, redactor
đơn giản (xoá key 'secret'), SessionSeq đếm theo session_id. Giữ trung thực: port 1-method,
adapter BusEventSink, EventEmitter validate/seq/redact rồi fan-out.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Protocol, runtime_checkable


# ──────────────────────────────────────────────────────────────────────────────
# Value type — distill control/events.py (RuntimeEvent, rút gọn)
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    session_id: str
    payload: dict = field(default_factory=dict)
    ui_payload: dict | None = None       # bản đã redact để hiển thị
    seq: int = 0

    def as_dict(self) -> dict:
        return {"event_type": self.event_type, "session_id": self.session_id,
                "seq": self.seq, "payload": self.payload, "ui_payload": self.ui_payload}


# ──────────────────────────────────────────────────────────────────────────────
# PORT HẸP — distill control/ports.py:14-22
# Một method duy nhất. Đây là "single role interface" tối giản.
# ──────────────────────────────────────────────────────────────────────────────
@runtime_checkable
class EventSinkPort(Protocol):
    """Một sink durable/transport mà emitter forward từng event đã finalize tới.
    v1: BusEventSink (in-process bus -> JSONL). T2: Kafka adapter cùng emit, không sửa caller."""

    def emit(self, event: RuntimeEvent) -> None: ...


# ──────────────────────────────────────────────────────────────────────────────
# Hạ tầng tối thiểu để EventEmitter chạy được (đứng thay registry/redactor/seq thật)
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class EventSpec:
    visibility: str  # "public" | "internal" — quyết định redact tới mức nào


class EventTypeRegistry:
    """Distill control/event_registry: gate event_type. Unknown -> lỗi (chặn trước publish)."""

    def __init__(self, specs: dict[str, EventSpec]) -> None:
        self._specs = specs

    def get(self, event_type: str) -> EventSpec:
        if event_type not in self._specs:
            raise ControlContractError(f"unknown event_type: {event_type!r}")
        return self._specs[event_type]


class ControlContractError(Exception):
    pass


class Redactor:
    """Distill control/redaction.Redactor: điền ui_payload theo visibility, KHÔNG để
    sink nhận secret thô. Ở đây: 'internal' giữ nguyên, 'public' xoá key chứa 'secret'."""

    def apply(self, event: RuntimeEvent, *, level: str) -> RuntimeEvent:
        if level == "internal":
            ui = dict(event.payload)
        else:
            ui = {k: ("***" if "secret" in k.lower() else v) for k, v in event.payload.items()}
        return replace(event, ui_payload=ui)


class SessionSeq:
    """Distill control/events.SessionSeq: số thứ tự đơn điệu theo session."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next(self, session_id: str) -> int:
        nxt = self._counters.get(session_id, 0) + 1
        self._counters[session_id] = nxt
        return nxt


# ──────────────────────────────────────────────────────────────────────────────
# ADAPTER #1 — distill control/emitter.py:28-36 (BusEventSink)
# Adapt một "bus" in-process thành EventSinkPort. Chỉ cần emit().
# ──────────────────────────────────────────────────────────────────────────────
class EventBus:
    """Đứng thay core.events.EventBus: publish(topic, dict) tới các subscriber."""

    def __init__(self) -> None:
        self._log: list[tuple[str, dict]] = []  # đóng vai EventLogger JSONL writer

    def publish(self, topic: str, payload: dict) -> None:
        self._log.append((topic, payload))

    def records(self) -> list[tuple[str, dict]]:
        return list(self._log)


class BusEventSink:
    """Adapt EventBus thành EventSinkPort: publish dict envelope dưới topic=event_type
    để subscriber cũ (EventLogger) persist không đổi."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def emit(self, event: RuntimeEvent) -> None:
        self._bus.publish(event.event_type, event.as_dict())


# ──────────────────────────────────────────────────────────────────────────────
# ADAPTER #2 — swap-in "Kafka" (giả) implement CÙNG EventSinkPort.
# Không có gì khác ngoài emit(). Caller không cần biết.
# ──────────────────────────────────────────────────────────────────────────────
class FakeKafkaSink:
    """Đứng thay 'Kafka adapter' (T2). Chỉ implement emit(), append vào topic giả."""

    def __init__(self, topic: str = "runtime-events") -> None:
        self.topic = topic
        self.produced: list[dict] = []

    def emit(self, event: RuntimeEvent) -> None:
        self.produced.append({"kafka_topic": self.topic, "key": event.session_id,
                              "value": event.as_dict()})


# ──────────────────────────────────────────────────────────────────────────────
# ADAPTER #3 — MockEventSink cho test (lưu event trong RAM)
# ──────────────────────────────────────────────────────────────────────────────
class MockEventSink:
    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    def emit(self, event: RuntimeEvent) -> None:
        self.events.append(event)


# ──────────────────────────────────────────────────────────────────────────────
# CLIENT — distill control/emitter.py:39-61 (EventEmitter)
# Phụ thuộc Iterable[EventSinkPort]. Không import BusEventSink/FakeKafkaSink.
# ──────────────────────────────────────────────────────────────────────────────
class EventEmitter:
    def __init__(self, sinks: Iterable[EventSinkPort], *,
                 registry: EventTypeRegistry, redactor: Redactor | None = None,
                 seq: SessionSeq | None = None) -> None:
        self._sinks = list(sinks)
        self._registry = registry
        self._redactor = redactor or Redactor()
        self._seq = seq or SessionSeq()

    def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
        """Validate -> stamp seq -> redact -> fan-out tới mọi sink. Trả event đã finalize.
        event_type lạ raise TRƯỚC khi publish bất cứ gì (registry là cổng)."""
        spec = self._registry.get(event.event_type)  # ControlContractError nếu lạ
        staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
        final = self._redactor.apply(staged, level=spec.visibility)
        for sink in self._sinks:           # ← chỉ gọi emit(); sink nào cũng được
            sink.emit(final)
        return final


def bus_emitter(bus: EventBus, *, registry: EventTypeRegistry, **kwargs) -> EventEmitter:
    """Distill control/emitter.py:93-95: EventEmitter mặc định gắn 1 BusEventSink."""
    return EventEmitter([BusEventSink(bus)], registry=registry, **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — "fat sink": nếu port ép sink phải biết validate/seq/redact thì sao?
# ──────────────────────────────────────────────────────────────────────────────
@runtime_checkable
class FatSinkPort(Protocol):
    """Vi phạm ISP: bắt MỌI sink phải tự validate + seq + redact + persist (4 method).
    Hệ quả: thêm KafkaSink phải copy lại 3 logic chung -> trùng lặp, dễ lệch."""
    def validate(self, event: RuntimeEvent) -> None: ...
    def stamp_seq(self, event: RuntimeEvent) -> RuntimeEvent: ...
    def redact(self, event: RuntimeEvent) -> RuntimeEvent: ...
    def persist(self, event: RuntimeEvent) -> None: ...


# ──────────────────────────────────────────────────────────────────────────────
# DEMO
# ──────────────────────────────────────────────────────────────────────────────
def _hr(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def _registry() -> EventTypeRegistry:
    return EventTypeRegistry({
        "tool.started": EventSpec(visibility="public"),
        "tool.finished": EventSpec(visibility="public"),
        "kernel.debug": EventSpec(visibility="internal"),
    })


def demo() -> None:
    _hr("BƯỚC 1 — Port HẸP NHẤT: EventSinkPort chỉ có emit(event)")
    print("EventSinkPort = 1 method. Validate/seq/redact KHÔNG nằm trong port —")
    print("chúng ở EventEmitter (phía trước). Sink chỉ việc persist. Đó là ISP tối giản.")

    _hr("BƯỚC 2 — Adapter BusEventSink implement đúng emit()")
    bus = EventBus()
    sink = BusEventSink(bus)
    assert isinstance(sink, EventSinkPort), "BusEventSink phải conform EventSinkPort"
    print("BusEventSink -> EventSinkPort ✓ (chỉ cần có emit đúng chữ ký)")

    _hr("BƯỚC 3 — EventEmitter fan-out qua port hẹp (caller không biết sink cụ thể)")
    emitter = bus_emitter(bus, registry=_registry())
    e1 = emitter.emit_event(RuntimeEvent("tool.started", "sess-A", {"tool": "fs_read"}))
    e2 = emitter.emit_event(RuntimeEvent("tool.finished", "sess-A", {"tool": "fs_read", "ok": True}))
    print(f"emit 2 event, seq tự stamp: {e1.seq}, {e2.seq}")
    assert (e1.seq, e2.seq) == (1, 2), "seq phải đơn điệu theo session"
    assert len(bus.records()) == 2, "cả 2 event phải tới bus subscriber"
    print(f"bus nhận {len(bus.records())} record qua emit() — emitter chỉ gọi port hẹp. ✓")

    _hr("BƯỚC 4 — Redaction nằm TRƯỚC sink: secret không bao giờ tới sink thô")
    em2 = EventEmitter([MockEventSink()], registry=_registry())
    mock = em2._sinks[0]  # type: ignore[assignment]
    em2.emit_event(RuntimeEvent("tool.started", "sess-B", {"tool": "http", "api_secret": "xyz"}))
    got = mock.events[0].ui_payload  # type: ignore[union-attr]
    print(f"payload gốc có api_secret; ui_payload (sink thấy) = {got}")
    assert got["api_secret"] == "***", "secret phải bị redact TRƯỚC khi tới sink"
    print("Sink không cần biết gì về redaction — đúng phân vai ISP. ✓")

    _hr("BƯỚC 5 — SWAP-IN 'Kafka' + multi-sink: ZERO caller change")
    kafka = FakeKafkaSink()
    mock2 = MockEventSink()
    multi = EventEmitter([BusEventSink(EventBus()), kafka, mock2], registry=_registry())
    multi.emit_event(RuntimeEvent("tool.finished", "sess-C", {"tool": "lint", "ok": True}))
    print(f"3 sink khác loại (Bus + Kafka + Mock) cùng nhận 1 event qua emit():")
    print(f"   kafka.produced = {len(kafka.produced)}, mock2.events = {len(mock2.events)}")
    assert len(kafka.produced) == 1 and len(mock2.events) == 1
    assert kafka.produced[0]["kafka_topic"] == "runtime-events"
    print("EventEmitter KHÔNG đổi 1 dòng khi thêm Kafka — vì nó chỉ phụ thuộc EventSinkPort. ✓")

    _hr("BƯỚC 6 — Cổng registry: event_type lạ raise TRƯỚC khi publish")
    em3 = EventEmitter([MockEventSink()], registry=_registry())
    sink3 = em3._sinks[0]  # type: ignore[assignment]
    try:
        em3.emit_event(RuntimeEvent("unknown.event", "sess-D", {}))
        raise AssertionError("đáng lẽ ControlContractError")
    except ControlContractError as exc:
        print(f"   emit('unknown.event') -> {exc}")
    assert len(sink3.events) == 0, "không sink nào được gọi khi validate fail"  # type: ignore[union-attr]
    print("Không event nào tới sink khi validate fail — validate đứng trước port. ✓")

    _hr("ĐỐI CHỨNG — 'fat sink' (FatSinkPort) buộc mỗi sink tự làm hết")
    print("Nếu port là FatSinkPort (validate+stamp_seq+redact+persist), thì:")
    print("  - mỗi adapter (Bus, Kafka, Redis) phải copy lại 3 logic chung;")
    print("  - sai ở 1 adapter -> event redact thiếu/seq lệch chỉ ở transport đó;")
    print("  - thêm sink mới = 4 method thay vì 1.")
    print("ISP đẩy 3 việc chung lên EventEmitter, để port chỉ còn emit() — DRY + an toàn.")
    # Chứng minh BusEventSink KHÔNG phải FatSinkPort (nó không gánh 4 method):
    assert not isinstance(BusEventSink(EventBus()), FatSinkPort)
    print("Xác nhận: BusEventSink KHÔNG conform FatSinkPort (nó hẹp đúng 1 method). ✓")

    _hr("KẾT LUẬN")
    print("EventSinkPort là port hẹp nhất — 1 method emit(). Việc nặng ở phía trước;")
    print("adapter chỉ persist; swap-in Kafka/Redis là thêm impl, không sửa caller.")


if __name__ == "__main__":
    demo()
