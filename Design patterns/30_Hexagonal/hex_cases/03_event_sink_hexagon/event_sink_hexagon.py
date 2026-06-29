"""
Hexagonal (Ports & Adapters) — Case 03: Event Control Plane, driven port EventSinkPort + adapter.

Bản DISTILL TRUNG THỰC từ codebase hex_agent. Nguồn thật:
  - control/ports.py:14-22      -> EventSinkPort (DRIVEN PORT: chỉ 1 method emit(event))
                                   comment: "v1 BusEventSink; T2 a Kafka adapter ... no caller change"
  - control/emitter.py:28-36    -> BusEventSink (DRIVEN ADAPTER v1: adapt in-process EventBus)
  - control/emitter.py:39-90    -> EventEmitter (DOMAIN CORE: validate -> stamp seq -> redact -> fan-out)
  - control/emitter.py:93-95    -> bus_emitter() (COMPOSITION ROOT nhỏ: EventEmitter + BusEventSink)
  - control/events.py           -> RuntimeEvent / SessionSeq (value types, seq monotonic per session)
  - tools/gen_t1_fixture.py:30-42 -> _Collect: 1 EventSinkPort tự chế (fake adapter) để gom event

Điều case này LƯỢC BỎ so với bản thật:
  - Bỏ EventTypeRegistry đầy đủ (load từ YAML): thay bằng set tên hợp lệ tối thiểu.
  - Bỏ Redactor đầy đủ: thay bằng redactor đơn giản che field 'api_key' -> '***'.
  - Bỏ Actor/TraceContext phức tạp: RuntimeEvent giữ field cốt lõi.
  - Giữ NGUYÊN: EventEmitter chỉ gọi sink.emit(); zero hiểu biết về transport;
    seq stamp monotonic per session; redact theo visibility; fan-out đến nhiều sink.

Chỉ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent, KHÔNG thư viện bên thứ ba.
Chạy: python3 event_sink_hexagon.py   (thoát code 0, không traceback)
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Protocol, runtime_checkable

# ─────────────────────────────────────────────────────────────────────────────
# 0) VALUE TYPES + SessionSeq  (distill control/events.py)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    session_id: str
    payload: dict = field(default_factory=dict)
    seq: int = 0
    ui_payload: dict | None = None       # do Redactor lấp đầy ở lõi

    def as_dict(self) -> dict:
        return {"event_type": self.event_type, "session_id": self.session_id,
                "seq": self.seq, "payload": self.payload, "ui_payload": self.ui_payload}


class SessionSeq:
    """Cấp seq tăng đơn điệu theo từng session (để Last-Event-ID có ý nghĩa)."""
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next(self, session_id: str) -> int:
        n = self._counters.get(session_id, 0) + 1
        self._counters[session_id] = n
        return n


class ControlContractError(Exception):
    """Ném khi event_type không có trong registry (gate của lõi)."""


@dataclass(frozen=True)
class _EventSpec:
    event_type: str
    visibility: str       # "public" -> hiện ui_payload đầy đủ; "internal" -> redact secret


class MiniRegistry:
    """distill control/event_registry — chỉ giữ phần gate: biết event_type + visibility."""
    def __init__(self, specs: dict[str, str]) -> None:
        self._specs = {k: _EventSpec(k, v) for k, v in specs.items()}

    def get(self, event_type: str) -> _EventSpec:
        spec = self._specs.get(event_type)
        if spec is None:
            raise ControlContractError(f"Unknown event_type: {event_type!r}")
        return spec


class MiniRedactor:
    """distill control/redaction.Redactor — lấp ui_payload, che secret nếu không public."""
    SECRET_KEYS = {"api_key", "password", "token"}

    def apply(self, event: RuntimeEvent, *, level: str) -> RuntimeEvent:
        if level == "public":
            ui = dict(event.payload)
        else:
            ui = {k: ("***" if k in self.SECRET_KEYS else v) for k, v in event.payload.items()}
        return replace(event, ui_payload=ui)


# ─────────────────────────────────────────────────────────────────────────────
# 1) DRIVEN PORT  (distill control/ports.py:14-22)
#    1 method duy nhất. Lõi (EventEmitter) gọi RA; adapter thực thi transport thật.
# ─────────────────────────────────────────────────────────────────────────────
@runtime_checkable
class EventSinkPort(Protocol):
    """Sink mà emitter forward mỗi event đã finalize. v1: BusEventSink; tương lai: Kafka/Redis."""
    def emit(self, event: RuntimeEvent) -> None: ...


# ─────────────────────────────────────────────────────────────────────────────
# 2) DRIVEN ADAPTERS  — cùng EventSinkPort, khác transport.
# ─────────────────────────────────────────────────────────────────────────────
class EventBus:
    """Bus in-process tối thiểu (distill core/events.EventBus)."""
    def __init__(self) -> None:
        self._subscribers: list = []

    def subscribe(self, fn) -> None:
        self._subscribers.append(fn)

    def publish(self, topic: str, payload: dict) -> None:
        for fn in self._subscribers:
            fn(topic, payload)


class BusEventSink:
    """DRIVEN ADAPTER v1 (distill control/emitter.py:28-36).
    Adapt EventBus: publish dict event dưới topic=event_type cho subscriber cũ (vd EventLogger)."""
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def emit(self, event: RuntimeEvent) -> None:
        self._bus.publish(event.event_type, event.as_dict())


class MemorySink:
    """DRIVEN ADAPTER fake (distill tools/gen_t1_fixture.py:30-42 _Collect).
    Chỉ gom event vào list — dùng cho test/fixture, không transport gì cả."""
    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    def emit(self, event: RuntimeEvent) -> None:
        self.events.append(event)


class KafkaLikeSink:
    """DRIVEN ADAPTER tương lai (minh hoạ T2): cùng EventSinkPort, 'gửi' vào topic.
    Ở đây 'Kafka' là 1 dict topic->list cho deterministic; lõi KHÔNG cần biết khác biệt."""
    def __init__(self) -> None:
        self.topics: dict[str, list[dict]] = {}

    def emit(self, event: RuntimeEvent) -> None:
        self.topics.setdefault(event.event_type, []).append(event.as_dict())


# ─────────────────────────────────────────────────────────────────────────────
# 3) DOMAIN CORE  (distill control/emitter.py:39-90)
#    EventEmitter chỉ nhận list[EventSinkPort]. Nó validate -> stamp seq -> redact ->
#    gọi sink.emit() cho từng sink. ZERO hiểu biết về Bus/Kafka/Redis.
# ─────────────────────────────────────────────────────────────────────────────
class EventEmitter:
    def __init__(self, sinks: Iterable[EventSinkPort], *, registry: MiniRegistry,
                 redactor: MiniRedactor | None = None, seq: SessionSeq | None = None) -> None:
        self._sinks = list(sinks)
        self._registry = registry
        self._redactor = redactor or MiniRedactor()
        self._seq = seq or SessionSeq()

    def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
        """Validate, stamp seq, redact, rồi fan-out. event_type lạ -> ném TRƯỚC khi publish."""
        spec = self._registry.get(event.event_type)            # gate: ControlContractError nếu lạ
        staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
        final = self._redactor.apply(staged, level=spec.visibility)
        for sink in self._sinks:                                # lõi chỉ biết .emit()
            sink.emit(final)
        return final

    def emit(self, event_type: str, *, session_id: str, payload: dict | None = None) -> RuntimeEvent:
        return self.emit_event(RuntimeEvent(event_type, session_id, dict(payload or {})))


# ─────────────────────────────────────────────────────────────────────────────
# 4) COMPOSITION ROOT  (distill control/emitter.py:93-95 bus_emitter())
# ─────────────────────────────────────────────────────────────────────────────
def _default_registry() -> MiniRegistry:
    return MiniRegistry({
        "loop.turn": "public",
        "tool.call": "internal",     # có thể chứa api_key -> phải redact
        "loop.finished": "public",
    })


def bus_emitter(bus: EventBus, **kwargs) -> EventEmitter:
    """EventEmitter nối với BusEventSink (v1 default)."""
    kwargs.setdefault("registry", _default_registry())
    return EventEmitter([BusEventSink(bus)], **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 5) PHẢN VÍ DỤ: lõi gọi thẳng bus.publish() (không qua port)
# ─────────────────────────────────────────────────────────────────────────────
class LeakyEmitter:
    """ANTI-PATTERN: lõi cầm trực tiếp EventBus và tự gọi publish().
    Muốn thêm Kafka phải SỬA lõi (thêm self._kafka.send...). Mất pluggability transport;
    cũng dễ quên validate/redact vì không còn 1 đường publish duy nhất."""
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus     # ← lõi biết transport cụ thể: SAI

    def emit(self, event_type: str, payload: dict) -> None:
        self._bus.publish(event_type, payload)   # raw, không seq, không redact


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 72)
    print("CASE 03 — Event Control Plane: driven port EventSinkPort + adapter")
    print("=" * 72)

    # --- (1) v1: EventEmitter + BusEventSink, verify event qua bus ---
    print("\n[1] bus_emitter(bus) — emitter forward qua BusEventSink ra EventBus")
    bus = EventBus()
    received: list[dict] = []
    bus.subscribe(lambda topic, payload: received.append({"topic": topic, **payload}))
    emitter = bus_emitter(bus)
    emitter.emit("loop.turn", session_id="s1", payload={"agent_id": "A"})
    emitter.emit("loop.turn", session_id="s1", payload={"agent_id": "B"})
    print(f"    bus nhận {len(received)} event; seq = {[r['seq'] for r in received]}")
    assert [r["seq"] for r in received] == [1, 2], "seq phải tăng đơn điệu per session"
    print("    [assert] seq stamp monotonic per session = [1, 2]. OK")

    # --- (2) Swap BusEventSink -> MemorySink: CÙNG EventEmitter, khác adapter ---
    print("\n[2] Swap sang MemorySink (fake adapter) — lõi EventEmitter không đổi")
    mem = MemorySink()
    emitter2 = EventEmitter([mem], registry=_default_registry())
    emitter2.emit("loop.turn", session_id="s2", payload={"agent_id": "C"})
    assert len(mem.events) == 1 and mem.events[0].seq == 1
    print(f"    MemorySink gom {len(mem.events)} event; seq={mem.events[0].seq}. OK")

    # --- (3) Tương lai: thêm KafkaLikeSink — vẫn 0 thay đổi lõi ---
    print("\n[3] Tương lai T2: thêm KafkaLikeSink — fan-out tới NHIỀU sink cùng lúc")
    mem2 = MemorySink()
    kafka = KafkaLikeSink()
    emitter3 = EventEmitter([mem2, kafka], registry=_default_registry())
    emitter3.emit("loop.finished", session_id="s3", payload={"status": "done"})
    assert len(mem2.events) == 1 and kafka.topics["loop.finished"]
    print(f"    cùng 1 emit -> MemorySink={len(mem2.events)}, "
          f"KafkaLikeSink topics={list(kafka.topics)}. OK")
    print("    => thêm Kafka/Redis = thêm sink mới, KHÔNG đụng EventEmitter.")

    # --- (4) Redaction theo visibility (lõi làm, mọi sink hưởng) ---
    print("\n[4] Redact: event 'tool.call' internal chứa api_key -> ui_payload che '***'")
    mem3 = MemorySink()
    em4 = EventEmitter([mem3], registry=_default_registry())
    final = em4.emit("tool.call", session_id="s4",
                     payload={"tool": "search", "api_key": "sk-SECRET-123"})
    assert final.payload["api_key"] == "sk-SECRET-123"     # payload gốc giữ nguyên
    assert final.ui_payload["api_key"] == "***"            # ui_payload bị redact
    print(f"    payload.api_key='{final.payload['api_key']}' | "
          f"ui_payload.api_key='{final.ui_payload['api_key']}'. OK")

    # --- (5) Gate: event_type lạ -> ném TRƯỚC khi publish (không sink nào nhận) ---
    print("\n[5] Gate: emit event_type chưa đăng ký -> ControlContractError, không publish")
    mem4 = MemorySink()
    em5 = EventEmitter([mem4], registry=_default_registry())
    try:
        em5.emit("totally.unknown", session_id="s5", payload={})
        raise AssertionError("đáng lẽ phải ném ControlContractError")
    except ControlContractError as exc:
        print(f"    bắt được: {exc}")
    assert mem4.events == [], "sink KHÔNG được nhận gì khi gate chặn"
    print("    [assert] sink rỗng vì gate chặn trước fan-out. OK")

    # --- (6) PHẢN VÍ DỤ ---
    print("\n[6] PHẢN VÍ DỤ — LeakyEmitter gọi thẳng bus.publish()")
    leaky_bus = EventBus()
    raw: list = []
    leaky_bus.subscribe(lambda t, p: raw.append((t, p)))
    leaky = LeakyEmitter(leaky_bus)
    leaky.emit("tool.call", {"api_key": "sk-LEAKED"})   # không seq, không redact!
    assert raw[0][1]["api_key"] == "sk-LEAKED"
    print(f"    secret rò ra bus nguyên vẹn: {raw[0][1]['api_key']!r} (không redact, không seq)")
    print("    Muốn thêm Kafka phải sửa lõi LeakyEmitter. => đây là cái port giải phóng ta khỏi.")

    print("\n" + "=" * 72)
    print("KẾT LUẬN: EventSinkPort là 1 method emit(); EventEmitter chỉ gọi nó.")
    print("Bus -> Memory -> Kafka -> Redis: đổi/thêm sink, lõi emit-path NGUYÊN VẸN.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
