"""RuntimeEvent envelope — the single shape every control-plane event uses. Epic E21 (S21.1/S21.7-info).

One envelope so UI, audit, replay and any sink read the same format. Dataclasses
(frozen, with ``as_dict``/``from_dict``) to match the repo — not pydantic. Validation
runs in ``__post_init__`` so an invalid event can never exist (let alone be published).

Splitting ``payload`` (internal, raw) from ``ui_payload`` (redacted) + ``redaction``
metadata is mandatory: the gateway/SSE layer streams only ``ui_payload`` (see the
Redactor in ``control.redaction``). ``SessionSeq`` is a pure per-session monotonic
sequence allocator the emitter (Phase B) will use; kept here so the contract is
testable offline.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from control.errors import ControlContractError

# An event's `actor` is who/what caused it; `redaction.level` classifies who may see it.
ACTOR_TYPES = frozenset({"human", "agent", "tool", "system", "runtime"})
VISIBILITY_LEVELS = frozenset({"public", "ui_safe", "internal", "secret", "restricted"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Actor:
    type: str
    id: str

    def __post_init__(self) -> None:
        if self.type not in ACTOR_TYPES:
            raise ControlContractError(
                f"Actor.type must be one of {sorted(ACTOR_TYPES)}, got {self.type!r}."
            )
        if not self.id:
            raise ControlContractError("Actor.id must be non-empty.")

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type, "id": self.id}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Actor":
        return cls(type=str(d.get("type", "")), id=str(d.get("id", "")))


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None = None

    def __post_init__(self) -> None:
        if not self.trace_id:
            raise ControlContractError("TraceContext.trace_id must be non-empty.")
        if not self.span_id:
            raise ControlContractError("TraceContext.span_id must be non-empty.")

    def as_dict(self) -> dict[str, Any]:
        return {"trace_id": self.trace_id, "span_id": self.span_id, "parent_span_id": self.parent_span_id}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TraceContext":
        return cls(
            trace_id=str(d.get("trace_id", "")),
            span_id=str(d.get("span_id", "")),
            parent_span_id=(str(d["parent_span_id"]) if d.get("parent_span_id") else None),
        )

    @classmethod
    def new_root(cls) -> "TraceContext":
        return cls(trace_id=uuid.uuid4().hex, span_id=uuid.uuid4().hex, parent_span_id=None)

    def child(self) -> "TraceContext":
        """A child span sharing this trace, parented to the current span."""
        return TraceContext(trace_id=self.trace_id, span_id=uuid.uuid4().hex, parent_span_id=self.span_id)


@dataclass(frozen=True)
class RedactionInfo:
    level: str = "ui_safe"
    has_secret: bool = False
    redacted_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.level not in VISIBILITY_LEVELS:
            raise ControlContractError(
                f"RedactionInfo.level must be one of {sorted(VISIBILITY_LEVELS)}, got {self.level!r}."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "has_secret": self.has_secret,
            "redacted_fields": list(self.redacted_fields),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RedactionInfo":
        return cls(
            level=str(d.get("level", "ui_safe")),
            has_secret=bool(d.get("has_secret", False)),
            redacted_fields=tuple(str(f) for f in (d.get("redacted_fields") or ())),
        )


@dataclass(frozen=True)
class RuntimeEvent:
    """The canonical control-plane event. ``event_id``/``created_at`` auto-fill; everything
    else the caller supplies. ``ui_payload`` is None until a Redactor fills it (S21.7)."""

    event_type: str
    session_id: str
    actor: Actor
    trace: TraceContext
    redaction: RedactionInfo
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=utc_now)
    schema_version: int = 1
    seq: int = 0
    round_no: int | None = None
    workflow_id: str | None = None
    task_id: str | None = None
    source: str = "runtime"
    payload: dict[str, Any] = field(default_factory=dict)
    ui_payload: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        for name in ("event_id", "event_type", "session_id", "created_at", "source"):
            if not getattr(self, name):
                raise ControlContractError(f"RuntimeEvent.{name} is required and must be non-empty.")
        if not isinstance(self.actor, Actor):
            raise ControlContractError("RuntimeEvent.actor must be an Actor.")
        if not isinstance(self.trace, TraceContext):
            raise ControlContractError("RuntimeEvent.trace must be a TraceContext.")
        if not isinstance(self.redaction, RedactionInfo):
            raise ControlContractError("RuntimeEvent.redaction must be a RedactionInfo.")
        if self.schema_version < 1:
            raise ControlContractError("RuntimeEvent.schema_version must be >= 1.")
        if self.seq < 0:
            raise ControlContractError("RuntimeEvent.seq must be >= 0.")
        if not isinstance(self.payload, dict):
            raise ControlContractError("RuntimeEvent.payload must be a mapping.")
        if self.ui_payload is not None and not isinstance(self.ui_payload, dict):
            raise ControlContractError("RuntimeEvent.ui_payload must be a mapping or None.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "seq": self.seq,
            "round_no": self.round_no,
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            "source": self.source,
            "actor": self.actor.as_dict(),
            "trace": self.trace.as_dict(),
            "payload": dict(self.payload),
            "ui_payload": (dict(self.ui_payload) if self.ui_payload is not None else None),
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
            round_no=(int(d["round_no"]) if d.get("round_no") is not None else None),
            workflow_id=(str(d["workflow_id"]) if d.get("workflow_id") else None),
            task_id=(str(d["task_id"]) if d.get("task_id") else None),
            source=str(d.get("source", "runtime")),
            payload=dict(d.get("payload") or {}),
            ui_payload=(dict(d["ui_payload"]) if d.get("ui_payload") is not None else None),
        )


class SessionSeq:
    """Monotonic per-session sequence allocator (pure, in-memory, thread-safe).

    The emitter (Phase B) stamps ``seq`` so a UI can order/dedup events within a
    session even if delivery is out of order.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, int] = {}

    def next(self, session_id: str) -> int:
        with self._lock:
            value = self._counters.get(session_id, 0) + 1
            self._counters[session_id] = value
            return value

    def peek(self, session_id: str) -> int:
        with self._lock:
            return self._counters.get(session_id, 0)
