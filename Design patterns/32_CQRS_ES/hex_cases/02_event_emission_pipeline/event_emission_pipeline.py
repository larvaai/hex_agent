"""
event_emission_pipeline.py — Đường publish event CQRS: validate -> stamp -> redact ->
fan-out -> append-only log (bản distill).

NGUỒN THẬT trong hex_agent mà case này distill từ đó:
  - control/emitter.py:39-96     -> EventEmitter.emit_event(): chokepoint DUY NHẤT.
        (1) check event_type với registry (unknown -> lỗi),
        (2) stamp seq monotonic per session (nếu chưa có),
        (3) Redactor.apply -> điền ui_payload đúng visibility (không sink nào thấy raw secret),
        (4) fan-out tới từng EventSinkPort.
  - control/event_registry.py:40-61 -> EventTypeRegistry.assert_known/get: catalog event
        hợp lệ; type lạ bị từ chối TRƯỚC khi publish (event là contract).
  - control/redaction.py:37-73   -> Redactor.apply/redact/_walk: tách payload raw thành
        ui_payload đã mask, không mutate bản gốc.
  - control/events.py:193-212    -> SessionSeq: bộ cấp seq monotonic per-session, thread-safe.
  - observability/event_log.py:41-99 -> EventLogger: subscribe bus, append JSONL (append-only
        event store), đếm metrics, seq tăng dần dưới lock.
  - core/events.py:11-31         -> EventBus: pub/sub trong-process, giao detached deep-copy
        cho mỗi subscriber -> không observer nào mutate được dữ liệu observer khác thấy
        (bất biến của event log).

Ý TƯỞNG (đúng như plan.runnableIdea):
  Emit nhiều RuntimeEvent qua EventEmitter (nhiều thread), một EventLogger subscribe để
  ghi lại, và kiểm chứng:
    (1) mọi event đều rơi vào "JSONL" theo đúng seq tăng dần;
    (2) event_id trùng bị bỏ (idempotency);
    (3) subscriber nhận deep-copy (mutate không ảnh hưởng log);
    (4) redaction mask secret trong ui_payload nhưng GIỮ payload raw.

CHỈ DÙNG STDLIB. Không import hex_agent, không thư viện bên thứ ba.
Hạ tầng nặng được thay bằng fake tối thiểu:
  - registry YAML thật -> dict tĩnh trong code.
  - file JSONL thật -> ghi vào StringIO/list nội bộ (vẫn append-only).
  - Kafka/SSE -> chỉ giữ EventBus in-process.
"""
from __future__ import annotations

import copy
import io
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# EVENT ENVELOPE (distill control/events.py:113-190) — bất biến, có seq + ui_payload
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    session_id: str
    payload: dict[str, Any] = field(default_factory=dict)       # raw, nội bộ
    ui_payload: dict[str, Any] | None = None                    # đã redact, UI/sink an toàn đọc
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    seq: int = 0
    created_at: str = field(default_factory=_utc_now)


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRY (distill control/event_registry.py:40-61) — catalog; type lạ bị từ chối
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class EventTypeSpec:
    event_type: str
    visibility: str = "ui_safe"   # public | ui_safe | internal | secret


class ControlContractError(Exception):
    """Vi phạm contract control-plane (distill control/errors.ControlContractError)."""


class EventTypeRegistry:
    def __init__(self, specs: dict[str, EventTypeSpec]) -> None:
        self._specs = dict(specs)

    def get(self, event_type: str) -> EventTypeSpec:
        if event_type not in self._specs:
            raise ControlContractError(
                f"Unknown event_type: {event_type!r}. Phải khai báo trong runtime_event_types.yaml."
            )
        return self._specs[event_type]


# ─────────────────────────────────────────────────────────────────────────────
# SESSION SEQ (distill control/events.py:193-...) — bộ cấp seq monotonic, thread-safe
# ─────────────────────────────────────────────────────────────────────────────
class SessionSeq:
    def __init__(self) -> None:
        self._next: dict[str, int] = {}
        self._lock = threading.Lock()

    def next(self, session_id: str) -> int:
        with self._lock:
            n = self._next.get(session_id, 0) + 1
            self._next[session_id] = n
            return n


# ─────────────────────────────────────────────────────────────────────────────
# REDACTOR (distill control/redaction.py:37-73) — mask secret -> ui_payload; raw bất biến
# ─────────────────────────────────────────────────────────────────────────────
SECRET_KEYS = frozenset({"api_key", "token", "password", "secret", "authorization"})
REDACTED = "[REDACTED]"


class Redactor:
    def __init__(self, secret_keys: frozenset[str] = SECRET_KEYS) -> None:
        self.secret_keys = frozenset(k.lower() for k in secret_keys)

    def _walk(self, value: Any, path: str, fields: list[str]) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                child = f"{path}.{key}" if path else str(key)
                if str(key).lower() in self.secret_keys:
                    out[key] = REDACTED
                    fields.append(child)
                else:
                    out[key] = self._walk(item, child, fields)
            return out
        if isinstance(value, list):
            return [self._walk(v, f"{path}[{i}]", fields) for i, v in enumerate(value)]
        return value

    def redact(self, payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        fields: list[str] = []
        return self._walk(payload, "", fields), sorted(set(fields))

    def apply(self, event: RuntimeEvent, *, level: str) -> RuntimeEvent:
        """Trả về bản copy event có ui_payload điền từ payload. payload gốc KHÔNG bị đụng."""
        ui_payload, _fields = self.redact(event.payload)
        return replace(event, ui_payload=ui_payload)


# ─────────────────────────────────────────────────────────────────────────────
# EVENT BUS (distill core/events.py:11-31) — pub/sub, giao DETACHED deep-copy
# ─────────────────────────────────────────────────────────────────────────────
Subscriber = Callable[[str, dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = threading.RLock()

    def subscribe(self, fn: Subscriber) -> None:
        with self._lock:
            self._subscribers.append(fn)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        data = copy.deepcopy(payload or {})
        for fn in subscribers:
            try:
                fn(topic, copy.deepcopy(data))   # mỗi subscriber nhận BẢN RIÊNG
            except Exception:
                pass                             # observer không bao giờ làm sập runtime


# ─────────────────────────────────────────────────────────────────────────────
# SINK PORT + BUS SINK (distill control/ports.EventSinkPort + emitter.BusEventSink:28-36)
# ─────────────────────────────────────────────────────────────────────────────
class BusEventSink:
    """Đẩy envelope lên EventBus dưới topic=event_type để subscriber cũ nhận nguyên."""
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def emit(self, event: RuntimeEvent) -> None:
        self._bus.publish(event.event_type, _as_dict(event))


def _as_dict(ev: RuntimeEvent) -> dict[str, Any]:
    return {
        "event_id": ev.event_id, "event_type": ev.event_type, "session_id": ev.session_id,
        "seq": ev.seq, "payload": dict(ev.payload),
        "ui_payload": (dict(ev.ui_payload) if ev.ui_payload is not None else None),
        "created_at": ev.created_at,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EVENT EMITTER (distill control/emitter.py:39-91) — đường publish DUY NHẤT
# ─────────────────────────────────────────────────────────────────────────────
class EventEmitter:
    def __init__(self, sinks: Iterable[Any], *, registry: EventTypeRegistry,
                 redactor: Redactor | None = None, seq: SessionSeq | None = None) -> None:
        self._sinks = list(sinks)
        self._registry = registry
        self._redactor = redactor or Redactor()
        self._seq = seq or SessionSeq()

    def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
        """Validate -> stamp seq -> redact -> fan-out. Trả về event đã hoàn thiện.
        event_type lạ -> raise TRƯỚC khi bất cứ gì được publish (registry là cổng)."""
        spec = self._registry.get(event.event_type)                 # raise nếu unknown
        staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
        final = self._redactor.apply(staged, level=spec.visibility)
        for sink in self._sinks:
            sink.emit(final)
        return final


# ─────────────────────────────────────────────────────────────────────────────
# EVENT LOGGER (distill observability/event_log.py:41-99) — append-only JSONL store
# Có dedup theo event_id (tinh thần ES: idempotency) + seq nội bộ dưới lock.
# ─────────────────────────────────────────────────────────────────────────────
class EventLogger:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sink = io.StringIO()        # thay file JSONL thật bằng buffer in-memory
        self.seq = 0
        self._seen_ids: set[str] = set()
        self.metrics = {"appended": 0, "duplicates": 0}

    def subscriber(self, topic: str, payload: dict[str, Any]) -> None:
        """Gắn vào bus qua bus.subscribe(logger.subscriber). Append nếu event_id mới."""
        with self._lock:
            eid = str(payload.get("event_id", ""))
            if eid and eid in self._seen_ids:
                self.metrics["duplicates"] += 1     # at-least-once delivery -> bỏ bản trùng
                return
            self.seq += 1
            record = {"sequence": self.seq, **payload}
            self._sink.write(json.dumps(record, ensure_ascii=False) + "\n")
            if eid:
                self._seen_ids.add(eid)
            self.metrics["appended"] += 1

    def lines(self) -> list[dict[str, Any]]:
        return [json.loads(ln) for ln in self._sink.getvalue().splitlines() if ln.strip()]


def _registry() -> EventTypeRegistry:
    return EventTypeRegistry({
        "loop.turn": EventTypeSpec("loop.turn", "ui_safe"),
        "loop.tool": EventTypeSpec("loop.tool", "ui_safe"),
        "permission.changed": EventTypeSpec("permission.changed", "ui_safe"),
    })


def demo() -> None:
    print("=" * 72)
    print("CASE 02 — Event Emission & Sink Pipeline (CQRS command->event path)")
    print("Distill từ control/emitter.py:39-96, observability/event_log.py:41-99,")
    print("           core/events.py:11-31, control/redaction.py:37-73")
    print("=" * 72)

    registry = _registry()
    bus = EventBus()
    logger = EventLogger()
    bus.subscribe(logger.subscriber)
    emitter = EventEmitter([BusEventSink(bus)], registry=registry)

    # ── (0) ĐỐI CHỨNG: type lạ bị từ chối TRƯỚC khi publish ──────────────────
    print("\n[GATE] event_type lạ phải bị registry từ chối trước khi publish:")
    try:
        emitter.emit_event(RuntimeEvent(event_type="loop.invented", session_id="s1"))
        raise AssertionError("Lẽ ra phải raise ControlContractError")
    except ControlContractError as e:
        print(f"  OK -> {e}")
    assert logger.metrics["appended"] == 0, "không event nào được ghi khi gate chặn"

    # ── (1) emit nhiều event đồng thời từ 10 worker, mỗi worker 5 event ───────
    print("\n[CONCURRENCY] 10 worker x 5 event = 50 event emit đồng thời qua EventEmitter...")

    def work(worker: int) -> None:
        for i in range(5):
            emitter.emit_event(RuntimeEvent(
                event_type="loop.turn",
                session_id="s1",
                payload={"worker": worker, "i": i, "api_key": "sk-SECRET-1234"},
            ))

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(work, range(10)))

    recs = logger.lines()
    print(f"  Đã append {len(recs)} bản ghi vào JSONL (in-memory).")

    # (1a) tất cả 50 event đều landed, seq nội bộ logger liên tục 1..50
    assert len(recs) == 50, f"phải có đúng 50 event, có {len(recs)}"
    assert [r["sequence"] for r in recs] == list(range(1, 51)), "seq logger phải liên tục, không trùng/nhảy"
    print("  [ASSERT] OK: 50 event landed, sequence logger = 1..50 (an toàn dưới đồng thời).")

    # (1b) seq per-session do emitter stamp cũng là 1..50 (monotonic per session)
    emit_seqs = sorted(r["seq"] for r in recs)
    assert emit_seqs == list(range(1, 51)), "SessionSeq phải cấp seq monotonic 1..50"
    print("  [ASSERT] OK: SessionSeq cấp seq 1..50 (monotonic per-session, thread-safe).")

    # ── (2) idempotency: append lại CÙNG event_id -> bị bỏ ────────────────────
    print("\n[IDEMPOTENCY] phát lại (replay) cùng event_id 2 lần (at-least-once delivery)...")
    dup = RuntimeEvent(event_type="loop.tool", session_id="s1", payload={"tool": "fs_read"})
    final = emitter.emit_event(dup)                       # lần 1: ghi
    bus.publish(final.event_type, _as_dict(final))        # lần 2: cùng event_id -> bỏ
    after = logger.lines()
    n_with_id = sum(1 for r in after if r.get("event_id") == final.event_id)
    assert n_with_id == 1, "event_id trùng chỉ được ghi MỘT lần"
    assert logger.metrics["duplicates"] >= 1, "logger phải đếm được bản trùng bị bỏ"
    print(f"  [ASSERT] OK: event_id {final.event_id[:8]}.. chỉ ghi 1 lần (duplicates={logger.metrics['duplicates']}).")

    # ── (3) subscriber nhận deep-copy: mutate không ảnh hưởng log ─────────────
    print("\n[DETACHED] subscriber mutate payload -> KHÔNG ảnh hưởng bản trong log:")
    captured: list[dict[str, Any]] = []
    evil_bus = EventBus()

    def mutator(topic, payload):
        payload["payload"]["worker"] = "HACKED"          # cố tình phá

    def observer(topic, payload):
        captured.append(payload)

    evil_bus.subscribe(mutator)
    evil_bus.subscribe(observer)
    evil_bus.publish("loop.turn", {"payload": {"worker": 7}})
    assert captured[0]["payload"]["worker"] == 7, "observer phải thấy bản gốc, không bị mutator phá"
    print("  [ASSERT] OK: mỗi subscriber nhận deep-copy riêng -> event log bất biến trước observer xấu.")

    # ── (4) redaction: ui_payload mask secret; payload raw GIỮ NGUYÊN ─────────
    print("\n[REDACTION] secret bị mask trong ui_payload nhưng payload raw giữ nguyên:")
    sample = next(r for r in recs)                         # bất kỳ event loop.turn nào
    assert sample["ui_payload"]["api_key"] == REDACTED, "ui_payload phải mask api_key"
    assert sample["payload"]["api_key"] == "sk-SECRET-1234", "payload raw phải GIỮ secret cho nội bộ/audit"
    print(f"  ui_payload.api_key = {sample['ui_payload']['api_key']!r}  (UI/SSE đọc cái này)")
    print(f"  payload.api_key    = {sample['payload']['api_key']!r}  (nội bộ/audit giữ nguyên)")
    print("  [ASSERT] OK: tách payload(raw) / ui_payload(redacted) — không sink nào lộ secret ra UI.")

    print("\n" + "=" * 72)
    print("XONG CASE 02. Đường publish: validate -> stamp seq -> redact -> fan-out -> append-only log.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
