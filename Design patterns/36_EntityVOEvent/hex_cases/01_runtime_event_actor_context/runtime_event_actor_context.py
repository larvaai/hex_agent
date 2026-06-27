"""
Case 01 — RuntimeEvent + Actor + TraceContext (Domain Event + composite Value Objects)

BẢN DISTILL TRUNG THỰC từ codebase hex_agent:
    - control/events.py:32-50    -> Actor              (Value Object, frozen, validate __post_init__)
    - control/events.py:53-82    -> TraceContext       (Value Object, frozen, validate + child())
    - control/events.py:85-110   -> RedactionInfo      (Value Object, frozen, validate level)
    - control/events.py:113-190  -> RuntimeEvent       (Domain Event: frozen, event_id/created_at auto,
                                                          schema_version, as_dict/from_dict, validate)
    - control/events.py:28-29    -> utc_now()          (timestamp tiện ích)

Ba building block của DDD tactical (Lesson 36) cùng xuất hiện trong MỘT contract thật:
    * RuntimeEvent = DOMAIN EVENT  — "đã xảy ra X tại T": frozen, có event_id (idempotency),
      created_at (timestamp), schema_version (versioning để replay).
    * Actor        = VALUE OBJECT  — "ai/cái gì gây ra event": không identity, frozen, equality by attribute.
    * TraceContext = VALUE OBJECT  — lineage cho distributed tracing: frozen, side-effect-free child().
    * RedactionInfo= VALUE OBJECT  — mức hiển thị: frozen, validate ở constructor.

ĐÃ LƯỢC BỎ so với bản thật (thay bằng fake stdlib tối thiểu):
    - control.errors.ControlContractError  -> dùng ValueError thuần (cùng vai trò "invalid khi construct").
    - ui_payload / Redactor / SSE gateway   -> bỏ; chỉ giữ payload + redaction để minh hoạ versioning.
    - SessionSeq (allocator thread-safe)    -> rút thành 1 counter đơn giản trong demo.
    - threading                              -> không cần, demo chạy đơn luồng.

Chạy: python3 runtime_event_actor_context.py   (thoát code 0, không traceback)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, FrozenInstanceError
from datetime import datetime, timezone
from typing import Any


# ── Tập giá trị hợp lệ (giữ nguyên tinh thần control/events.py:24-25) ──────────────
ACTOR_TYPES = frozenset({"human", "agent", "tool", "system", "runtime"})
VISIBILITY_LEVELS = frozenset({"public", "ui_safe", "internal", "secret", "restricted"})


def utc_now() -> str:
    """Distill control/events.py:28-29 — timestamp ISO-8601 ở UTC cho mọi event."""
    return datetime.now(timezone.utc).isoformat()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ VALUE OBJECT #1 — Actor (control/events.py:32-50)                          ║
# ║   "ai/cái gì gây ra event". Không identity. Frozen. Validate khi construct ║
# ╚══════════════════════════════════════════════════════════════════════════╝
@dataclass(frozen=True)
class Actor:
    """VALUE OBJECT: 2 Actor cùng (type, id) là MỘT — equality by attribute, không identity riêng."""

    type: str
    id: str

    def __post_init__(self) -> None:
        # Bất biến enforce ngay tại constructor: một Actor không hợp lệ KHÔNG THỂ tồn tại.
        if self.type not in ACTOR_TYPES:
            raise ValueError(f"Actor.type phải thuộc {sorted(ACTOR_TYPES)}, nhận {self.type!r}.")
        if not self.id:
            raise ValueError("Actor.id không được rỗng.")

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type, "id": self.id}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Actor":
        return cls(type=str(d.get("type", "")), id=str(d.get("id", "")))


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ VALUE OBJECT #2 — TraceContext (control/events.py:53-82)                   ║
# ║   lineage tracing. Frozen. child() là side-effect-free → trả VO MỚI.       ║
# ╚══════════════════════════════════════════════════════════════════════════╝
@dataclass(frozen=True)
class TraceContext:
    """VALUE OBJECT: mô tả "đường truy vết". child() KHÔNG mutate self, trả một TraceContext mới."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None

    def __post_init__(self) -> None:
        if not self.trace_id:
            raise ValueError("TraceContext.trace_id không được rỗng.")
        if not self.span_id:
            raise ValueError("TraceContext.span_id không được rỗng.")

    @classmethod
    def new_root(cls) -> "TraceContext":
        return cls(trace_id=uuid.uuid4().hex, span_id=uuid.uuid4().hex, parent_span_id=None)

    def child(self) -> "TraceContext":
        """Side-effect-free: span con cùng trace, parent = span hiện tại. Self KHÔNG đổi."""
        return TraceContext(trace_id=self.trace_id, span_id=uuid.uuid4().hex, parent_span_id=self.span_id)

    def as_dict(self) -> dict[str, Any]:
        return {"trace_id": self.trace_id, "span_id": self.span_id, "parent_span_id": self.parent_span_id}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TraceContext":
        return cls(
            trace_id=str(d.get("trace_id", "")),
            span_id=str(d.get("span_id", "")),
            parent_span_id=(str(d["parent_span_id"]) if d.get("parent_span_id") else None),
        )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ VALUE OBJECT #3 — RedactionInfo (control/events.py:85-110)                 ║
# ║   mức hiển thị. redacted_fields là TUPLE (không List) → immutable thực sự. ║
# ╚══════════════════════════════════════════════════════════════════════════╝
@dataclass(frozen=True)
class RedactionInfo:
    """VALUE OBJECT: dùng tuple cho redacted_fields để event không thể bị mutate gián tiếp."""

    level: str = "ui_safe"
    has_secret: bool = False
    redacted_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.level not in VISIBILITY_LEVELS:
            raise ValueError(f"RedactionInfo.level phải thuộc {sorted(VISIBILITY_LEVELS)}, nhận {self.level!r}.")

    def as_dict(self) -> dict[str, Any]:
        return {"level": self.level, "has_secret": self.has_secret, "redacted_fields": list(self.redacted_fields)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RedactionInfo":
        return cls(
            level=str(d.get("level", "ui_safe")),
            has_secret=bool(d.get("has_secret", False)),
            redacted_fields=tuple(str(f) for f in (d.get("redacted_fields") or ())),
        )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ DOMAIN EVENT — RuntimeEvent (control/events.py:113-190)                    ║
# ║   "đã xảy ra X tại T". Frozen + event_id + created_at + schema_version.    ║
# ║   Compose 3 Value Object ở trên làm payload ngữ cảnh.                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝
@dataclass(frozen=True)
class RuntimeEvent:
    """DOMAIN EVENT chính tắc:
        - past-tense fact (event_type kiểu "task.completed")
        - frozen → đã fire thì không "unfire"
        - event_id auto (idempotency), created_at auto (timestamp), schema_version (versioning).
    """

    event_type: str
    session_id: str
    actor: Actor
    trace: TraceContext
    redaction: RedactionInfo
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=utc_now)
    schema_version: int = 1
    seq: int = 0
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("event_id", "event_type", "session_id", "created_at"):
            if not getattr(self, name):
                raise ValueError(f"RuntimeEvent.{name} bắt buộc và không được rỗng.")
        if not isinstance(self.actor, Actor):
            raise ValueError("RuntimeEvent.actor phải là Actor.")
        if not isinstance(self.trace, TraceContext):
            raise ValueError("RuntimeEvent.trace phải là TraceContext.")
        if not isinstance(self.redaction, RedactionInfo):
            raise ValueError("RuntimeEvent.redaction phải là RedactionInfo.")
        if self.schema_version < 1:
            raise ValueError("RuntimeEvent.schema_version phải >= 1.")
        if self.seq < 0:
            raise ValueError("RuntimeEvent.seq phải >= 0.")
        if not isinstance(self.payload, dict):
            raise ValueError("RuntimeEvent.payload phải là mapping.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "seq": self.seq,
            "actor": self.actor.as_dict(),
            "trace": self.trace.as_dict(),
            "payload": dict(self.payload),
            "redaction": self.redaction.as_dict(),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RuntimeEvent":
        return cls(
            event_type=str(d.get("event_type", "")),
            session_id=str(d.get("session_id", "")),
            actor=Actor.from_dict(d.get("actor") or {}),
            trace=TraceContext.from_dict(d.get("trace") or {}),
            redaction=RedactionInfo.from_dict(d.get("redaction") or {}),
            event_id=str(d.get("event_id", "")),
            created_at=str(d.get("created_at", "")),
            schema_version=int(d.get("schema_version", 1)),
            seq=int(d.get("seq", 0)),
            payload=dict(d.get("payload") or {}),
        )


# ── ĐỐI CHỨNG: Domain Event KHÔNG frozen (anti-pattern Lesson 36, Vi phạm C) ──────
@dataclass  # CỐ Ý quên frozen=True — đây là cách LÀM SAI
class MutableEventBad:
    """Anti-pattern: event mutable + payload là list → consumer này mutate, consumer kia thấy sai."""

    event_type: str
    items: list[str] = field(default_factory=list)


def demo() -> None:
    print("=" * 74)
    print("CASE 01 — RuntimeEvent (Domain Event) + Actor/TraceContext/Redaction (VO)")
    print("Distill từ: control/events.py:32-190")
    print("=" * 74)

    # ── Bước 1: Dựng các Value Object ngữ cảnh ────────────────────────────────────
    print("\n[1] Dựng Value Object: Actor + TraceContext + RedactionInfo")
    actor = Actor(type="agent", id="agent:planner")
    root_trace = TraceContext.new_root()
    redaction = RedactionInfo(level="ui_safe", has_secret=False, redacted_fields=("api_key",))
    print(f"    Actor       = {actor.as_dict()}")
    print(f"    TraceContext= trace={root_trace.trace_id[:8]}.. span={root_trace.span_id[:8]}..")
    print(f"    Redaction   = {redaction.as_dict()}")

    # VO: equality by attribute — 2 instance cùng dữ liệu là MỘT.
    actor_copy = Actor(type="agent", id="agent:planner")
    assert actor == actor_copy, "VO phải equal-by-attribute"
    assert actor is not actor_copy, "nhưng là 2 instance khác nhau trong memory"
    print("    [assert] Actor(...) == Actor(...) cùng dữ liệu  -> VO equality by attribute  OK")

    # ── Bước 2: Dựng Domain Event compose các VO ──────────────────────────────────
    print("\n[2] Dựng Domain Event RuntimeEvent (event_id + created_at tự sinh)")
    evt = RuntimeEvent(
        event_type="task.completed",
        session_id="sess-42",
        actor=actor,
        trace=root_trace,
        redaction=redaction,
        seq=1,
        payload={"task_id": "T-1", "status": "ok"},
    )
    print(f"    event_id       = {evt.event_id}")
    print(f"    created_at     = {evt.created_at}")
    print(f"    schema_version = {evt.schema_version}")
    print(f"    event_type     = {evt.event_type!r}  (past-tense fact)")
    assert evt.event_id, "Domain Event phải có event_id (idempotency)"
    assert evt.created_at, "Domain Event phải có timestamp"
    print("    [assert] event có event_id + created_at  -> đặc trưng Domain Event  OK")

    # ── Bước 3: Round-trip as_dict()/from_dict() — Public schema versioned ────────
    print("\n[3] Round-trip as_dict() -> from_dict() (event là wire format ổn định)")
    wire = evt.as_dict()
    restored = RuntimeEvent.from_dict(wire)
    assert restored == evt, "round-trip phải bảo toàn dữ liệu"
    print(f"    schema_version giữ nguyên = {restored.schema_version}")
    print("    [assert] from_dict(as_dict(evt)) == evt  -> bảo toàn cho replay  OK")

    # ── Bước 4: Immutability — đã fire thì không thể đổi ──────────────────────────
    print("\n[4] Bất biến (frozen): không thể mutate event đã phát")
    try:
        evt.seq = 999  # type: ignore[misc]
        raise AssertionError("LẼ RA phải raise FrozenInstanceError")
    except FrozenInstanceError:
        print("    [assert] gán evt.seq = 999  -> FrozenInstanceError  (đúng: event immutable)  OK")

    # ── Bước 5: child span side-effect-free ───────────────────────────────────────
    print("\n[5] TraceContext.child() side-effect-free (trả VO mới, không đổi cha)")
    child_trace = root_trace.child()
    assert child_trace.trace_id == root_trace.trace_id, "con cùng trace với cha"
    assert child_trace.parent_span_id == root_trace.span_id, "con trỏ về span cha"
    assert root_trace.parent_span_id is None, "cha KHÔNG bị thay đổi"
    print(f"    child.parent_span_id == root.span_id ({child_trace.parent_span_id[:8]}..)")
    print("    [assert] root_trace.parent_span_id vẫn None  -> child() không mutate cha  OK")

    # ── Bước 6: Versioning cho replay (schema_version) ────────────────────────────
    print("\n[6] schema_version cho phép tiến hoá schema khi replay")
    v2 = RuntimeEvent(
        event_type="task.completed",
        session_id="sess-42",
        actor=actor,
        trace=root_trace,
        redaction=redaction,
        schema_version=2,
        payload={"task_id": "T-1", "status": "ok", "channel": "web"},  # field thêm ở v2
    )
    assert v2.schema_version == 2 and "channel" in v2.payload
    print("    v2 thêm payload['channel'] mà v1 vẫn replay được nhờ schema_version  OK")

    # ── Bước 7: Validate ở constructor — invalid KHÔNG thể tồn tại ─────────────────
    print("\n[7] Validate tại constructor: object sai KHÔNG bao giờ ra đời")
    for bad, why in [
        (lambda: Actor(type="alien", id="x"), "Actor.type không hợp lệ"),
        (lambda: Actor(type="agent", id=""), "Actor.id rỗng"),
        (lambda: RedactionInfo(level="top-secret"), "RedactionInfo.level không hợp lệ"),
    ]:
        try:
            bad()
            raise AssertionError(f"LẼ RA phải raise: {why}")
        except ValueError:
            print(f"    [assert] {why}  -> ValueError tại __post_init__  OK")

    # ── Bước 8: ĐỐI CHỨNG — Domain Event mutable thì hỏng thế nào ──────────────────
    print("\n[8] ĐỐI CHỨNG: nếu Domain Event KHÔNG frozen + payload là list")
    bad_evt = MutableEventBad(event_type="task.completed", items=["a"])
    snapshot_before = list(bad_evt.items)
    # Consumer A vô tình mutate event đang được broadcast cho nhiều consumer:
    bad_evt.items.append("b")
    print(f"    consumer A thấy {snapshot_before}, sau khi mutate consumer B thấy {bad_evt.items}")
    assert bad_evt.items != snapshot_before, "đúng như Lesson 36 cảnh báo: event bị thay đổi giữa các consumer"
    print("    => Bài học: Domain Event PHẢI frozen + dùng tuple, như RuntimeEvent/RedactionInfo ở trên")

    print("\n" + "=" * 74)
    print("KẾT LUẬN: 1 Domain Event (RuntimeEvent) compose nhiều Value Object (Actor,")
    print("TraceContext, RedactionInfo). Frozen + validate-at-construction + event_id +")
    print("created_at + schema_version = đủ 5 đặc điểm Domain Event của Lesson 36.")
    print("=" * 74)


if __name__ == "__main__":
    demo()
