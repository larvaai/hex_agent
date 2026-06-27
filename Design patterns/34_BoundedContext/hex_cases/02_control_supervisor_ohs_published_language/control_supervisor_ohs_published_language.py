"""
Case 02 — OHS + Published Language giữa Control Context và Supervisor Context.

Bản DISTILL TRUNG THỰC (chỉ stdlib) của các đoạn code thật trong hex_agent:

  Nguồn thật (đã mở file kiểm chứng):
  - control/events.py:113-151    RuntimeEvent: dataclass frozen, versioned (schema_version),
                                 tách payload (raw) khỏi ui_payload (đã redact) + RedactionInfo.
  - control/events.py:85-110     RedactionInfo(level, has_secret, redacted_fields).
  - control/events.py:193-211    SessionSeq: cấp seq monotonic theo từng session.
  - control/redaction.py:37-73   Redactor: che field bí mật, điền ui_payload + RedactionInfo.
  - control/emitter.py:39-90     EventEmitter.emit(): validate -> stamp seq -> redact -> fan-out.
  - supervisor/graph.py:56-76    SupervisorContext.emit(): NẾU có emitter thì đi qua envelope
                                 RuntimeEvent; nếu emitter=None thì publish raw dict (legacy).
  - supervisor/graph.py:103      topic 'loop.team_composed' phát qua emit().

Bài học Bounded Context được minh hoạ:
  * Control   = UPSTREAM OHS PROVIDER: publish 1 schema chuẩn (RuntimeEvent) cho mọi consumer.
  * Supervisor = DOWNSTREAM CONSUMER: route mọi event qua envelope chuẩn, không tự định dạng.
  * RuntimeEvent = Published Language (versioned, redactable) — hợp đồng lasting, đa-consumer.
  * Redactor = Anti-Corruption translation layer: payload thô không bao giờ chạm UI sink;
    secret bị che TRƯỚC khi rời Control context.

Hạ tầng nặng được thay bằng fake stdlib tối thiểu:
  - Không có KernelSession/SSE/Kafka: sink là list in-memory.
  - Không có event_registry YAML: registry là dict {event_type -> visibility} tối giản.
  - Không có TraceContext.new_root() từ uuid của repo: dùng giá trị cố định cho dễ đọc.

Chạy: python3 control_supervisor_ohs_published_language.py  ->  exit code 0, không traceback.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from typing import Any, Protocol


# ════════════════════════════════════════════════════════════════════════════
# CONTROL CONTEXT — ngôn ngữ riêng: "RuntimeEvent", "RedactionInfo", "Redactor",
#   "EventEmitter", "visibility level". 'Event' ở đây là MỘT BẢN GHI CONTROL-PLANE
#   có version + redaction, KHÔNG phải dict tuỳ tiện.
# ════════════════════════════════════════════════════════════════════════════

VISIBILITY_LEVELS = frozenset({"public", "ui_safe", "internal", "secret", "restricted"})


class ControlContractError(Exception):
    """Distill của control/errors.ControlContractError."""


@dataclass(frozen=True)
class RedactionInfo:
    """Distill của control/events.py:85-110."""
    level: str = "ui_safe"
    has_secret: bool = False
    redacted_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.level not in VISIBILITY_LEVELS:
            raise ControlContractError(f"RedactionInfo.level không hợp lệ: {self.level!r}")


@dataclass(frozen=True)
class RuntimeEvent:
    """Distill của control/events.py:113-151 — PUBLISHED LANGUAGE của Control context.

    Bất biến chính (__post_init__): một RuntimeEvent KHÔNG HỢP LỆ không thể tồn tại,
    nên không bao giờ được publish. payload (raw) tách khỏi ui_payload (đã redact).
    """
    event_type: str
    session_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    redaction: RedactionInfo = field(default_factory=RedactionInfo)
    schema_version: int = 1
    seq: int = 0
    ui_payload: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.event_type:
            raise ControlContractError("RuntimeEvent.event_type là bắt buộc.")
        if not self.session_id:
            raise ControlContractError("RuntimeEvent.session_id là bắt buộc.")
        if self.schema_version < 1:
            raise ControlContractError("RuntimeEvent.schema_version phải >= 1.")
        if self.seq < 0:
            raise ControlContractError("RuntimeEvent.seq phải >= 0.")
        if not isinstance(self.payload, dict):
            raise ControlContractError("RuntimeEvent.payload phải là mapping.")


class SessionSeq:
    """Distill của control/events.py:193-211 — cấp seq monotonic theo session."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, int] = {}

    def next(self, session_id: str) -> int:
        with self._lock:
            value = self._counters.get(session_id, 0) + 1
            self._counters[session_id] = value
            return value


SECRET_KEYS = frozenset({"api_key", "token", "password", "secret", "authorization"})
REDACTED = "[REDACTED]"


class Redactor:
    """Distill của control/redaction.py:37-73 — Anti-Corruption translation layer.

    Che mọi field bí mật (đệ quy), điền ui_payload + RedactionInfo. KHÔNG mutate payload gốc.
    """

    def __init__(self, secret_keys: frozenset[str] = SECRET_KEYS) -> None:
        self._secret_keys = frozenset(k.lower() for k in secret_keys)

    def _walk(self, value: Any, path: str, fields: list[str]) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                child = f"{path}.{key}" if path else str(key)
                if str(key).lower() in self._secret_keys:
                    out[key] = REDACTED
                    fields.append(child)
                else:
                    out[key] = self._walk(item, child, fields)
            return out
        if isinstance(value, list):
            return [self._walk(v, f"{path}[{i}]", fields) for i, v in enumerate(value)]
        return value

    def apply(self, event: RuntimeEvent, *, level: str) -> RuntimeEvent:
        fields: list[str] = []
        ui_payload = self._walk(event.payload, "", fields)
        info = RedactionInfo(level=level, has_secret=bool(fields),
                             redacted_fields=tuple(sorted(set(fields))))
        return replace(event, ui_payload=ui_payload, redaction=info)


class EventSinkPort(Protocol):
    """Distill của control/ports.EventSinkPort."""
    def emit(self, event: RuntimeEvent) -> None: ...


class EventTypeRegistry:
    """Distill tối giản của control/event_registry.

    Là CỔNG (gate): event_type lạ -> ControlContractError TRƯỚC khi publish.
    Mỗi type có 'visibility' (mức redaction áp dụng).
    """

    def __init__(self, table: dict[str, str]) -> None:
        self._table = dict(table)

    def visibility(self, event_type: str) -> str:
        if event_type not in self._table:
            raise ControlContractError(f"Unknown event_type: {event_type!r}")
        return self._table[event_type]


class EventEmitter:
    """Distill của control/emitter.py:39-90 — đường publish DUY NHẤT, đã chuẩn hoá.

    emit(): (1) validate type qua registry; (2) stamp seq monotonic;
            (3) redact để điền ui_payload; (4) fan-out tới mọi sink.
    """

    def __init__(self, sinks: list[EventSinkPort], *, registry: EventTypeRegistry,
                 redactor: Redactor | None = None, seq: SessionSeq | None = None) -> None:
        self._sinks = list(sinks)
        self._registry = registry
        self._redactor = redactor or Redactor()
        self._seq = seq or SessionSeq()

    def emit(self, event_type: str, *, session_id: str, payload: dict[str, Any]) -> RuntimeEvent:
        visibility = self._registry.visibility(event_type)        # gate (emitter.py:56)
        staged = RuntimeEvent(event_type=event_type, session_id=session_id, payload=dict(payload))
        staged = replace(staged, seq=self._seq.next(session_id))   # emitter.py:57
        final = self._redactor.apply(staged, level=visibility)     # emitter.py:58
        for sink in self._sinks:
            sink.emit(final)                                       # emitter.py:59-60
        return final


# ── Sinks fake (thay cho SSE/JSONL/Kafka) ───────────────────────────────────

class UiSafeSink:
    """Sink mô phỏng UI/SSE: CHỈ được đọc ui_payload (đã redact), không bao giờ payload thô.

    Tương ứng quy tắc control/redaction.py docstring: gateway streams only ui_payload.
    """

    def __init__(self) -> None:
        self.received: list[dict[str, Any]] = []

    def emit(self, event: RuntimeEvent) -> None:
        if event.ui_payload is None:
            raise AssertionError("UI sink không được nhận event chưa redact (ui_payload=None).")
        self.received.append({"event_type": event.event_type, "seq": event.seq,
                              "ui_payload": event.ui_payload,
                              "redacted_fields": list(event.redaction.redacted_fields)})


class AuditSink:
    """Sink audit nội bộ: được phép giữ payload thô (level=internal)."""

    def __init__(self) -> None:
        self.received: list[RuntimeEvent] = []

    def emit(self, event: RuntimeEvent) -> None:
        self.received.append(event)


# ════════════════════════════════════════════════════════════════════════════
# SUPERVISOR CONTEXT — DOWNSTREAM CONSUMER.
#   Distill của supervisor/graph.py:56-76 (SupervisorContext.emit).
#   'event' ở Supervisor chỉ là (topic, payload) — Supervisor KHÔNG tự định dạng
#   envelope; nó nhờ Control context chuẩn hoá. Nếu emitter=None -> fallback raw dict.
# ════════════════════════════════════════════════════════════════════════════

class SupervisorContext:
    def __init__(self, session_id: str, emitter: EventEmitter | None) -> None:
        self.session_id = session_id
        self.emitter = emitter
        self.legacy_bus: list[tuple[str, dict[str, Any]]] = []   # đường raw khi không có emitter

    def emit(self, topic: str, payload: dict[str, Any]) -> None:
        # supervisor/graph.py:60-72: có emitter -> qua envelope chuẩn (OHS).
        if self.emitter is not None:
            self.emitter.emit(topic, session_id=self.session_id, payload=dict(payload))
            return
        # supervisor/graph.py:73-75: legacy raw dict (không qua Control context).
        self.legacy_bus.append((topic, dict(payload)))

    def compose_team(self) -> None:
        """Distill rút gọn của supervisor/graph.py compose_team -> phát 'loop.team_composed'."""
        # payload CỐ TÌNH chứa field bí mật để chứng minh redaction ở biên giới.
        # Redactor khớp THEO TÊN KEY chính xác (control/redaction.py:41-42) -> 'api_key' bị che.
        self.emit("loop.team_composed", {
            "selected": ["writer", "reviewer"],
            "credentials": {"api_key": "sk-super-secret-123"},  # secret rò xuống — Control phải che!
        })


# ════════════════════════════════════════════════════════════════════════════
# DEMO
# ════════════════════════════════════════════════════════════════════════════

def build_emitter() -> tuple[EventEmitter, UiSafeSink, AuditSink]:
    registry = EventTypeRegistry({
        "loop.team_composed": "ui_safe",
        "loop.decision": "ui_safe",
    })
    ui_sink, audit_sink = UiSafeSink(), AuditSink()
    emitter = EventEmitter([ui_sink, audit_sink], registry=registry)
    return emitter, ui_sink, audit_sink


def demo() -> None:
    print("=" * 74)
    print("CASE 02 — OHS + Published Language: Control (provider) -> Supervisor (consumer)")
    print("=" * 74)

    emitter, ui_sink, audit_sink = build_emitter()

    print("\n[1] Supervisor phát event QUA emitter -> đi vào envelope RuntimeEvent chuẩn (OHS).")
    sup = SupervisorContext(session_id="sess-1", emitter=emitter)
    sup.compose_team()
    sup.emit("loop.decision", {"round": 1, "decision": "continue"})

    print(f"    UI sink nhận {len(ui_sink.received)} event; Audit sink nhận {len(audit_sink.received)} event.")
    assert len(ui_sink.received) == 2 and len(audit_sink.received) == 2

    print("\n[2] Bất biến PUBLISHED LANGUAGE: mọi event đều versioned + có seq monotonic.")
    seqs = [e.seq for e in audit_sink.received]
    versions = {e.schema_version for e in audit_sink.received}
    print(f"    seq = {seqs}   schema_version = {versions}")
    assert seqs == [1, 2], "seq phải tăng đơn điệu theo session."
    assert versions == {1}, "mọi event chia sẻ cùng schema_version (hợp đồng versioned)."
    print("    -> ASSERT: seq=[1,2], schema_version={1}. Một định dạng chung cho mọi consumer.")

    print("\n[3] Bất biến ANTI-CORRUPTION: secret bị che TRƯỚC khi tới UI sink.")
    team_event_ui = ui_sink.received[0]
    print(f"    ui_payload (UI thấy)   = {team_event_ui['ui_payload']}")
    print(f"    redacted_fields        = {team_event_ui['redacted_fields']}")
    assert team_event_ui["ui_payload"]["credentials"]["api_key"] == "[REDACTED]", "UI không được thấy secret thô."
    assert "credentials.api_key" in team_event_ui["redacted_fields"]
    print("    -> ASSERT: UI chỉ thấy [REDACTED]; Control context không để secret rò sang UI.")

    print("\n[4] payload THÔ vẫn còn nguyên trong audit (internal) — không bị mutate.")
    team_event_raw = audit_sink.received[0]
    print(f"    payload thô (audit)    = {team_event_raw.payload}")
    assert team_event_raw.payload["credentials"]["api_key"] == "sk-super-secret-123", "payload gốc không bị đổi."
    assert team_event_raw.ui_payload["credentials"]["api_key"] == "[REDACTED]"
    print("    -> ASSERT: payload != ui_payload. Hai mặt của cùng một envelope, redact không phá raw.")

    print("\n[5] Bất biến GATE: event_type lạ bị từ chối TRƯỚC khi publish.")
    rogue = SupervisorContext(session_id="sess-1", emitter=emitter)
    try:
        rogue.emit("loop.unregistered_topic", {"x": 1})
        raise AssertionError("Đáng lẽ phải raise ControlContractError.")
    except ControlContractError as exc:
        print(f"    raise ControlContractError: {exc}")
    assert len(ui_sink.received) == 2, "Không event lạ nào được publish ra sink."
    print("    -> ASSERT: type không đăng ký -> chặn ngay, không lọt ra sink nào.")

    print("\n[ĐỐI CHỨNG] Supervisor KHÔNG dùng OHS (emitter=None): publish raw dict.")
    no_ohs_anti_pattern()

    print("\n" + "=" * 74)
    print("KẾT LUẬN: Supervisor không tự định dạng event — nó tiêu thụ Published Language")
    print("RuntimeEvent do Control phát. Redactor là tường ngăn secret giữa hai context.")
    print("=" * 74)


def no_ohs_anti_pattern() -> None:
    """emitter=None -> Supervisor rơi về raw dict, KHÔNG qua Control context.

    Hậu quả: không versioned, không seq, KHÔNG redact. Secret đi thẳng ra bus thô.
    Đây chính là rủi ro mà OHS+Published Language loại bỏ.
    """
    sup = SupervisorContext(session_id="sess-1", emitter=None)
    sup.compose_team()
    topic, payload = sup.legacy_bus[0]
    print(f"    legacy raw event: topic={topic!r}")
    print(f"    raw payload đi thẳng ra bus = {payload}")
    # Không có redaction nào: secret nằm trần trong raw dict.
    assert payload["credentials"]["api_key"] == "sk-super-secret-123"
    assert not hasattr(payload, "schema_version")
    print("    -> Không version, không seq, KHÔNG redact: secret 'api_key' lộ nguyên.")
    print("       Vì thế đường có-emitter (OHS) là đường an toàn, đa-consumer.")


if __name__ == "__main__":
    demo()
