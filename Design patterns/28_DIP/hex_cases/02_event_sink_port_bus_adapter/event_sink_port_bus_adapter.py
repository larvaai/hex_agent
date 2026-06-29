"""
Case 02 — DIP: EventSinkPort — trừu tượng định tuyến sự kiện cho các sink cắm-rút
==================================================================================

Bản DISTILL TRUNG THỰC từ hex_agent:

  - control/ports.py:14-22
        @runtime_checkable
        class EventSinkPort(Protocol):   # emit(event) -> ABSTRACTION do control plane (cấp cao) sở hữu
        # docstring nhắc rõ: T2 một Kafka adapter implement cùng emit() là drop-in, không sửa caller.
  - control/emitter.py:28-36
        class BusEventSink:              # adapter bọc in-process EventBus, convert event -> bus.publish
  - control/emitter.py:39-61
        class EventEmitter:             # cấp cao nhận list[EventSinkPort] qua constructor (DI),
                                        # validate + redact + stamp seq rồi fan-out tới mọi sink.
  - control/emitter.py:93-95
        def bus_emitter(bus): ...        # factory nối EventEmitter với BusEventSink

Ý tưởng DIP ở đây:
  * control/ (cấp cao) ĐỊNH NGHĨA cái nó cần ở 1 sink: chỉ một method emit(event).
  * Hạ tầng cung cấp adapter: BusEventSink (cho EventBus); sau này Kafka/Redis sink mới.
  * EventEmitter nhận sink qua constructor (dependency injection), lặp gọi sink.emit().
    Nó KHÔNG import BusEventSink hay bất kỳ sink cụ thể nào.
  * Đổi sink (Bus -> InMemory -> Kafka) chỉ là đổi 1 dòng ở factory; EventEmitter BẤT BIẾN.

Bản rút gọn này thay EventBus thật + EventTypeRegistry + Redactor đầy đủ bằng fake tối
thiểu (stdlib). Vẫn giữ đúng: validate event_type, stamp seq đơn điệu, fan-out tới sinks.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Protocol, runtime_checkable


# ───────────────────────────────────────────────────────────────────────────
# Value type — RuntimeEvent rút gọn (mô phỏng control/events.py)
# ───────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    session_id: str
    payload: dict = field(default_factory=dict)
    seq: int = 0

    def as_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "payload": self.payload,
            "seq": self.seq,
        }


# ───────────────────────────────────────────────────────────────────────────
# 1) ABSTRACTION — sống ở "cấp cao" control/ (mô phỏng control/ports.py:14-22)
# ───────────────────────────────────────────────────────────────────────────
@runtime_checkable
class EventSinkPort(Protocol):
    """A durable/transport sink the emitter forwards each finalized event to.

    v1 impl: BusEventSink (in-process EventBus). T2: một Kafka adapter implement cùng
    ``emit`` được drop-in mà không đổi caller. (control/ports.py:15-22)
    """

    def emit(self, event: RuntimeEvent) -> None: ...


# ───────────────────────────────────────────────────────────────────────────
# Hạ tầng cấp thấp: EventBus in-process (mô phỏng core/events.py)
# ───────────────────────────────────────────────────────────────────────────
class EventBus:
    """Bus xuất bản theo topic, giữ log để kiểm chứng (thay cho EventLogger JSONL thật)."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, envelope: dict) -> None:
        self.published.append((topic, envelope))


# ───────────────────────────────────────────────────────────────────────────
# 2) ADAPTER — BusEventSink bọc EventBus (mô phỏng control/emitter.py:28-36)
# ───────────────────────────────────────────────────────────────────────────
class BusEventSink:
    """Adapts the in-process EventBus to EventSinkPort. (control/emitter.py:28-36)"""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def emit(self, event: RuntimeEvent) -> None:
        self._bus.publish(event.event_type, event.as_dict())


class InMemorySink:
    """Fake sink cho test: ghi mọi event vào list, không I/O. Cũng là EventSinkPort."""

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    def emit(self, event: RuntimeEvent) -> None:
        self.events.append(event)


# ───────────────────────────────────────────────────────────────────────────
# Phụ trợ cấp cao: registry kiểu sự kiện + bộ đếm seq (rút gọn)
# ───────────────────────────────────────────────────────────────────────────
class ControlContractError(Exception):
    """Raise khi event_type chưa được đăng ký (registry là cổng gác)."""


class EventTypeRegistry:
    def __init__(self, known: set[str]) -> None:
        self._known = known

    def get(self, event_type: str) -> str:
        if event_type not in self._known:
            raise ControlContractError(f"unknown event_type: {event_type!r}")
        return event_type


class SessionSeq:
    """Đếm seq đơn điệu theo từng session (mô phỏng control.events.SessionSeq)."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next(self, session_id: str) -> int:
        self._counters[session_id] = self._counters.get(session_id, 0) + 1
        return self._counters[session_id]


# ───────────────────────────────────────────────────────────────────────────
# 3) CẤP CAO tiêu thụ — EventEmitter (mô phỏng control/emitter.py:39-61)
#    Nhận Iterable[EventSinkPort] qua constructor. KHÔNG import sink cụ thể.
# ───────────────────────────────────────────────────────────────────────────
class EventEmitter:
    def __init__(
        self,
        sinks: Iterable[EventSinkPort],
        *,
        registry: EventTypeRegistry,
        seq: SessionSeq | None = None,
    ) -> None:
        self._sinks = list(sinks)          # giữ kiểu abstraction
        self._registry = registry
        self._seq = seq or SessionSeq()

    def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
        """Validate, stamp seq, rồi fan-out tới mọi sink. (control/emitter.py:53-61)"""
        self._registry.get(event.event_type)   # ControlContractError nếu lạ
        staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
        for sink in self._sinks:                # gọi qua abstraction
            sink.emit(staged)
        return staged


# ───────────────────────────────────────────────────────────────────────────
# 4) COMPOSITION ROOT / FACTORY — nối concrete vào abstraction (control/emitter.py:93-95)
# ───────────────────────────────────────────────────────────────────────────
def bus_emitter(bus: EventBus, registry: EventTypeRegistry) -> EventEmitter:
    """An EventEmitter wired to publish onto the given in-process EventBus (v1 default)."""
    return EventEmitter([BusEventSink(bus)], registry=registry)


# ───────────────────────────────────────────────────────────────────────────
# DEMO
# ───────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 72)
    print("CASE 02 — EventSinkPort + BusEventSink (DIP)")
    print("=" * 72)

    registry = EventTypeRegistry(known={"tool.started", "tool.finished"})

    # --- Config v1: EventBus thật qua adapter ---
    print("\n[1] Config v1: EventEmitter nối với EventBus qua BusEventSink (adapter).")
    bus = EventBus()
    emitter = bus_emitter(bus, registry)
    emitter.emit_event(RuntimeEvent("tool.started", session_id="s1", payload={"tool": "fs_read"}))
    emitter.emit_event(RuntimeEvent("tool.finished", session_id="s1", payload={"ok": True}))
    print("    Bus đã nhận:", bus.published)
    assert len(bus.published) == 2
    assert bus.published[0][0] == "tool.started"

    # --- Bất biến: seq đơn điệu theo session ---
    print("\n[2] Bất biến: seq được đóng dấu đơn điệu theo session.")
    seqs = [env["seq"] for _, env in bus.published]
    print("    seqs =", seqs)
    assert seqs == [1, 2], "seq phải tăng 1,2 trong cùng session"

    # --- Đổi sink mà KHÔNG đụng EventEmitter ---
    print("\n[3] Swap sink: dùng InMemorySink thay BusEventSink — EventEmitter KHÔNG đổi.")
    mem = InMemorySink()
    emitter2 = EventEmitter([mem], registry=registry)   # cùng lớp EventEmitter, chỉ đổi sink
    emitter2.emit_event(RuntimeEvent("tool.started", session_id="s2", payload={"tool": "echo"}))
    print("    InMemorySink giữ:", [e.as_dict() for e in mem.events])
    assert len(mem.events) == 1 and mem.events[0].seq == 1

    # --- Fan-out tới NHIỀU sink cùng lúc ---
    print("\n[4] Fan-out: cùng lúc gửi tới nhiều sink (Bus + InMemory + 'Kafka' giả).")
    bus3 = EventBus()
    mem3 = InMemorySink()

    class FakeKafkaSink:           # adapter mới — drop-in, EventEmitter không biết
        def __init__(self) -> None:
            self.topic_log: list[str] = []

        def emit(self, event: RuntimeEvent) -> None:
            self.topic_log.append(event.event_type)

    kafka = FakeKafkaSink()
    emitter3 = EventEmitter([BusEventSink(bus3), mem3, kafka], registry=registry)
    emitter3.emit_event(RuntimeEvent("tool.finished", session_id="s3"))
    assert len(bus3.published) == 1 and len(mem3.events) == 1 and kafka.topic_log == ["tool.finished"]
    print("    Cả 3 sink đều nhận event. Thêm sink mới = thêm 1 lớp emit(), 0 sửa EventEmitter.")

    # --- Cổng gác: event_type lạ bị chặn TRƯỚC khi publish ---
    print("\n[5] Cổng gác registry: event_type lạ raise trước khi bất kỳ sink nào thấy.")
    bus5 = EventBus()
    emitter5 = bus_emitter(bus5, registry)
    try:
        emitter5.emit_event(RuntimeEvent("tool.unknown", session_id="s5"))
        raise AssertionError("đáng lẽ phải raise ControlContractError")
    except ControlContractError as exc:
        print("    Bị chặn:", exc)
    assert bus5.published == [], "không sink nào được publish khi event_type lạ"

    # --- Bằng chứng DIP ---
    print("\n[6] Bất biến DIP: mọi sink đều thoả EventSinkPort (structural).")
    assert isinstance(BusEventSink(EventBus()), EventSinkPort)
    assert isinstance(InMemorySink(), EventSinkPort)
    assert isinstance(FakeKafkaSink(), EventSinkPort)
    print("    isinstance(BusEventSink/InMemorySink/FakeKafkaSink, EventSinkPort) = True")

    # --- ĐỐI CHỨNG ---
    print("\n[7] ĐỐI CHỨNG — nếu EventEmitter gọi thẳng bus.publish(topic, dict):")
    print("    Muốn thêm Kafka/Redis -> phải SỬA EventEmitter (vi phạm OCP).")
    print("    Muốn test -> phải dựng EventBus thật. Với DIP: inject InMemorySink là xong.")

    print("\nTẤT CẢ ASSERT PASS. DIP cho phép cắm-rút sink mà không đụng business logic.\n")


if __name__ == "__main__":
    demo()
