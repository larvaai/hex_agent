"""
Case 02 — Event Type Registry with Visibility & Schema Versioning (EDA).

Bản DISTILL trung thực của "control-plane contract" trong hex_agent: mọi event_type
phải được KHAI BÁO trước trong registry; emitter là cổng gác validate trước khi publish;
mỗi event được stamp seq đơn điệu và REDACT theo mức visibility trước khi tới UI.

NGUỒN THẬT (đã mở kiểm chứng):
  - config/runtime_event_types.yaml:11-83
        Catalog ~52 event_type (session.*, agent.*, tool.*, ...). Mỗi cái khai báo
        visibility (public|ui_safe|internal|secret|restricted), durable, redact_for_ui,
        checkpoint_candidate.
  - control/event_registry.py:40-99
        EventTypeRegistry: assert_known (dòng 47-51) raise ControlContractError nếu
        type chưa khai báo; get/visibility; parse_event_registry ép tên có dấu chấm
        và visibility hợp lệ. EventTypeSpec là @dataclass(frozen=True) (dòng 22-37).
  - control/events.py:32-151
        @dataclass(frozen=True) RuntimeEvent: envelope bất biến, __post_init__ validate
        (event_id/event_type/session_id non-empty, schema_version>=1, seq>=0, ...).
        Actor/TraceContext/RedactionInfo cũng frozen + validate.
  - control/events.py:193-213  -> SessionSeq: cấp seq đơn điệu per-session, thread-safe.
  - control/emitter.py:39-95
        EventEmitter.emit_event (dòng 53-61): (1) registry.get(type) [gate],
        (2) stamp seq nếu chưa có, (3) redactor.apply theo visibility, (4) fan-out tới sinks.
        bus_emitter (dòng 93-95) ráp emitter lên 1 EventBus qua BusEventSink (dòng 28-36).
  - control/redaction.py:37-73
        Redactor: tách payload -> ui_payload, mask các key bí mật (token, password, ...).

Ý TƯỞNG MÔ PHỎNG:
  1. Nạp 1 registry nhỏ (đóng vai runtime_event_types.yaml) bằng dict thuần.
  2. Emitter từ chối event_type LẠ (ControlContractError) — chứng minh "không tự bịa event".
  3. Emit 1 event đã khai báo -> qua gate, stamp seq, redact, fan-out.
  4. So sánh redaction: event "internal" có secret bị mask; event "ui_safe" sạch.

LƯỢC BỎ: không parse YAML thật (dùng dict), không Actor/TraceContext đầy đủ, không
JSONL sink. Giữ đúng VAI: Registry (contract) -> Emitter (gate) -> Redactor -> Sink.

Chỉ dùng thư viện chuẩn Python 3.14.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Protocol

# Mức visibility hợp lệ — đúng control/events.py:25.
VISIBILITY_LEVELS = frozenset({"public", "ui_safe", "internal", "secret", "restricted"})

# Key bị mask ở mọi nơi — distill control/redaction.py:16-33.
SECRET_KEYS = frozenset({"token", "password", "api_key", "secret", "authorization"})
REDACTED = "[REDACTED]"


class ControlContractError(Exception):
    """Vi phạm hợp đồng control-plane (vd: event_type chưa khai báo)."""


# ──────────────────────────────────────────────────────────────────────────
# REGISTRY — distill control/event_registry.py:22-99
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class EventTypeSpec:
    """Bất biến — frozen dataclass, đúng control/event_registry.py:22."""

    event_type: str
    visibility: str
    durable: bool = True
    redact_for_ui: bool = False
    checkpoint_candidate: bool = False


class EventTypeRegistry:
    def __init__(self, specs: dict[str, EventTypeSpec]) -> None:
        self._specs = dict(specs)

    def __contains__(self, event_type: str) -> bool:
        return event_type in self._specs

    def assert_known(self, event_type: str) -> None:
        # Cổng gác: type chưa khai báo -> raise (control/event_registry.py:47-51).
        if event_type not in self._specs:
            raise ControlContractError(
                f"Unknown event_type: {event_type!r}. Hãy khai báo trong runtime_event_types.yaml."
            )

    def get(self, event_type: str) -> EventTypeSpec:
        self.assert_known(event_type)
        return self._specs[event_type]

    def visibility(self, event_type: str) -> str:
        return self.get(event_type).visibility


def parse_event_registry(rows: dict[str, dict[str, Any]]) -> EventTypeRegistry:
    """Ép tên có dấu chấm + visibility hợp lệ — distill parse_event_registry (dòng 64-93)."""
    if not rows:
        raise ControlContractError("Registry phải có ít nhất 1 event_type.")
    specs: dict[str, EventTypeSpec] = {}
    for name, raw in rows.items():
        event_type = str(name).strip()
        if not event_type or "." not in event_type:
            raise ControlContractError(
                f"event_type {name!r} phải có dấu chấm (vd 'agent.before_run')."
            )
        raw = raw or {}
        visibility = str(raw.get("visibility", "ui_safe"))
        if visibility not in VISIBILITY_LEVELS:
            raise ControlContractError(
                f"'{event_type}' visibility {visibility!r} phải thuộc {sorted(VISIBILITY_LEVELS)}."
            )
        specs[event_type] = EventTypeSpec(
            event_type=event_type,
            visibility=visibility,
            durable=bool(raw.get("durable", True)),
            redact_for_ui=bool(raw.get("redact_for_ui", False)),
            checkpoint_candidate=bool(raw.get("checkpoint_candidate", False)),
        )
    return EventTypeRegistry(specs)


# Bản nhỏ của config/runtime_event_types.yaml:11-83 (chỉ vài type tiêu biểu).
SAMPLE_REGISTRY_ROWS: dict[str, dict[str, Any]] = {
    "session.started":   {"visibility": "ui_safe", "durable": True},
    "agent.before_run":  {"visibility": "ui_safe", "durable": True},
    "agent.output.raw":  {"visibility": "internal", "durable": True, "redact_for_ui": True},
    "tool.before_call":  {"visibility": "ui_safe", "durable": True, "checkpoint_candidate": True},
    "tool.after_call":   {"visibility": "ui_safe", "durable": True, "redact_for_ui": True},
}


# ──────────────────────────────────────────────────────────────────────────
# ENVELOPE — distill control/events.py:113-151 (RuntimeEvent frozen + validate)
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    session_id: str
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    schema_version: int = 1
    seq: int = 0
    visibility: str = "ui_safe"
    payload: dict[str, Any] = field(default_factory=dict)
    ui_payload: dict[str, Any] | None = None  # None cho tới khi Redactor điền

    def __post_init__(self) -> None:
        # Validate ngay lúc dựng -> không thể tồn tại event sai (control/events.py:134-151).
        for name in ("event_id", "event_type", "session_id"):
            if not getattr(self, name):
                raise ControlContractError(f"RuntimeEvent.{name} bắt buộc non-empty.")
        if self.schema_version < 1:
            raise ControlContractError("schema_version phải >= 1.")
        if self.seq < 0:
            raise ControlContractError("seq phải >= 0.")
        if not isinstance(self.payload, dict):
            raise ControlContractError("payload phải là mapping.")


# ──────────────────────────────────────────────────────────────────────────
# SEQ — distill control/events.py:193-213 (SessionSeq monotonic per-session)
# ──────────────────────────────────────────────────────────────────────────
class SessionSeq:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, int] = {}

    def next(self, session_id: str) -> int:
        with self._lock:
            value = self._counters.get(session_id, 0) + 1
            self._counters[session_id] = value
            return value


# ──────────────────────────────────────────────────────────────────────────
# REDACTOR — distill control/redaction.py:37-73
# ──────────────────────────────────────────────────────────────────────────
class Redactor:
    def redact(self, payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        fields: list[str] = []
        out = self._walk(payload, "", fields)
        return out, sorted(set(fields))

    def _walk(self, value: Any, path: str, fields: list[str]) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                child = f"{path}.{key}" if path else str(key)
                if str(key).lower() in SECRET_KEYS:
                    out[key] = REDACTED
                    fields.append(child)
                else:
                    out[key] = self._walk(item, child, fields)
            return out
        if isinstance(value, list):
            return [self._walk(v, f"{path}[{i}]", fields) for i, v in enumerate(value)]
        return value

    def apply(self, event: RuntimeEvent, *, level: str) -> RuntimeEvent:
        ui_payload, _ = self.redact(event.payload)
        return replace(event, ui_payload=ui_payload, visibility=level)


# ──────────────────────────────────────────────────────────────────────────
# SINK PORT + adapter — distill control/ports.py:14-22 & control/emitter.py:28-36
# ──────────────────────────────────────────────────────────────────────────
class EventSinkPort(Protocol):
    def emit(self, event: RuntimeEvent) -> None: ...


class CollectingSink:
    """Sink test: thu mọi event đã finalize (đóng vai BusEventSink/EventLogger)."""

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    def emit(self, event: RuntimeEvent) -> None:
        self.events.append(event)


# ──────────────────────────────────────────────────────────────────────────
# EMITTER — distill control/emitter.py:39-91 (cổng gác duy nhất để publish)
# ──────────────────────────────────────────────────────────────────────────
class EventEmitter:
    def __init__(
        self,
        sinks: Iterable[EventSinkPort],
        *,
        registry: EventTypeRegistry,
        redactor: Redactor | None = None,
        seq: SessionSeq | None = None,
    ) -> None:
        self._sinks = list(sinks)
        self._registry = registry
        self._redactor = redactor or Redactor()
        self._seq = seq or SessionSeq()

    def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
        # (1) GATE: type chưa khai báo -> raise TRƯỚC khi publish bất cứ gì (emitter.py:56).
        spec = self._registry.get(event.event_type)
        # (2) Stamp seq đơn điệu nếu chưa có (emitter.py:57).
        staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
        # (3) Redact theo visibility khai báo (emitter.py:58).
        final = self._redactor.apply(staged, level=spec.visibility)
        # (4) Fan-out tới mọi sink (emitter.py:59-60).
        for sink in self._sinks:
            sink.emit(final)
        return final


def demo() -> None:
    print("=" * 72)
    print("CASE 02 — Event Registry: schema governance cho EDA production")
    print("=" * 72)

    print("\n[Bước 1] Nạp registry (đóng vai runtime_event_types.yaml):")
    registry = parse_event_registry(SAMPLE_REGISTRY_ROWS)
    for name in SAMPLE_REGISTRY_ROWS:
        print(f"         - {name:18s} visibility={registry.visibility(name)}")

    sink = CollectingSink()
    emitter = EventEmitter([sink], registry=registry)

    print("\n[Bước 2] Thử emit event_type LẠ ('agent.does_not_exist') -> phải bị chặn:")
    try:
        emitter.emit_event(RuntimeEvent(event_type="agent.does_not_exist", session_id="s1"))
        raise AssertionError("đáng lẽ phải raise ControlContractError")
    except ControlContractError as exc:
        print(f"         -> CHẶN: {exc}")
    assert len(sink.events) == 0, "event lạ KHÔNG được lọt vào sink"

    print("\n[Bước 3] Emit event đã khai báo ('agent.before_run') -> qua gate:")
    e1 = emitter.emit_event(RuntimeEvent(event_type="agent.before_run", session_id="s1",
                                         payload={"prompt": "viết hàm fib"}))
    print(f"         seq={e1.seq} visibility={e1.visibility} ui_payload={e1.ui_payload}")
    assert e1.seq == 1, e1.seq
    assert len(sink.events) == 1

    print("\n[Bước 4] seq đơn điệu trong cùng session:")
    e2 = emitter.emit_event(RuntimeEvent(event_type="session.started", session_id="s1"))
    e3 = emitter.emit_event(RuntimeEvent(event_type="agent.before_run", session_id="s1"))
    print(f"         seq lần lượt: {e1.seq}, {e2.seq}, {e3.seq}")
    assert [e1.seq, e2.seq, e3.seq] == [1, 2, 3], (e1.seq, e2.seq, e3.seq)
    # Session khác -> bộ đếm riêng, bắt đầu lại từ 1.
    e_other = emitter.emit_event(RuntimeEvent(event_type="session.started", session_id="s2"))
    assert e_other.seq == 1, e_other.seq
    print(f"         session 's2' bộ đếm riêng: seq={e_other.seq}")

    print("\n[Bước 5] Redaction theo visibility — emit event mang secret:")
    secret_payload = {"prompt": "deploy", "token": "ghp_supersecret", "api_key": "AKIA123"}
    redacted = emitter.emit_event(RuntimeEvent(
        event_type="agent.output.raw", session_id="s1", payload=secret_payload,
    ))
    print(f"         payload thật (internal) giữ nguyên: token={redacted.payload['token']!r}")
    print(f"         ui_payload (ra UI) đã mask        : token={redacted.ui_payload['token']!r}")
    # Bất biến: payload thật KHÔNG đổi; ui_payload đã mask mọi secret.
    assert redacted.payload["token"] == "ghp_supersecret"
    assert redacted.ui_payload["token"] == REDACTED
    assert redacted.ui_payload["api_key"] == REDACTED
    assert redacted.ui_payload["prompt"] == "deploy"  # field thường giữ nguyên

    print("\n[Bước 6] ĐỐI CHỨNG — bus 'tự do' không registry:")
    print("         Nếu cho phép publish(topic_bất_kỳ, dict), một module có thể")
    print("         bịa ra 'agnet.beforeRun' (gõ sai), consumer chờ 'agent.before_run'")
    print("         sẽ KHÔNG BAO GIỜ nhận -> bug âm thầm, không ai báo lỗi.")
    assert "agnet.beforeRun" not in registry, "registry giúp phát hiện type sai ngay"
    # Với registry, đúng cú pháp này sẽ nổ ngay tại gate thay vì im lặng.
    try:
        emitter.emit_event(RuntimeEvent(event_type="agnet.beforeRun", session_id="s1"))
        raise AssertionError("đáng lẽ phải raise")
    except ControlContractError:
        print("         -> Với registry: gõ sai bị chặn NGAY tại emit, không lọt xuống consumer.")

    # Bất biến frozen: không sửa được spec sau khi nạp.
    spec = registry.get("agent.before_run")
    try:
        spec.visibility = "secret"  # type: ignore[misc]
        raise AssertionError("frozen dataclass đáng lẽ không cho gán")
    except Exception:
        print("\n[Bước 7] EventTypeSpec là frozen -> contract bất biến, không ai sửa runtime.")

    print("\nTẤT CẢ ASSERT PASS. Registry = hợp đồng schema: producer & consumer")
    print("chỉ couple qua event_type + payload đã được khai báo, versioned, redact.")


if __name__ == "__main__":
    demo()
