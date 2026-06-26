"""RuntimeCommand — the one structured shape for every UI/human intervention. Epic E21 (S21.3).

UI never mutates state directly; it submits a ``RuntimeCommand``. The gateway validates
it (``parse_command``) before it enters the queue. ``idempotency_key`` + ``issued_by`` are
mandatory: the first guards against double-apply, the second names who acted (for authz +
audit). ``apply_at`` / ``requires_permission`` live in the command-type registry, not here.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from control.errors import ControlContractError

ISSUER_TYPES = frozenset({"human", "agent", "system"})
# A CommandAck is the *synchronous receipt* the gateway returns from POST /api/commands.
# It says only "we received / we rejected" — the later accepted/applied outcome arrives
# asynchronously over SSE (S21.15). So the status set is intentionally just two values.
ACCEPT_STATUSES = frozenset({"received", "rejected"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class IssuedBy:
    type: str
    user_id: str | None = None
    agent_id: str | None = None

    def __post_init__(self) -> None:
        if self.type not in ISSUER_TYPES:
            raise ControlContractError(
                f"IssuedBy.type must be one of {sorted(ISSUER_TYPES)}, got {self.type!r}."
            )
        if self.type == "human" and not self.user_id:
            raise ControlContractError("IssuedBy(type='human') requires a user_id.")
        if self.type == "agent" and not self.agent_id:
            raise ControlContractError("IssuedBy(type='agent') requires an agent_id.")

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type, "user_id": self.user_id, "agent_id": self.agent_id}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IssuedBy":
        return cls(
            type=str(d.get("type", "")),
            user_id=(str(d["user_id"]) if d.get("user_id") else None),
            agent_id=(str(d["agent_id"]) if d.get("agent_id") else None),
        )


@dataclass(frozen=True)
class RuntimeCommand:
    command_type: str
    session_id: str
    issued_by: IssuedBy
    idempotency_key: str
    payload: dict[str, Any] = field(default_factory=dict)
    command_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_utc_now)
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in ("command_id", "command_type", "session_id", "idempotency_key", "created_at"):
            if not getattr(self, name):
                raise ControlContractError(f"RuntimeCommand.{name} is required and must be non-empty.")
        if not isinstance(self.issued_by, IssuedBy):
            raise ControlContractError("RuntimeCommand.issued_by must be an IssuedBy.")
        if not isinstance(self.payload, dict):
            raise ControlContractError("RuntimeCommand.payload must be a mapping.")
        if self.schema_version < 1:
            raise ControlContractError("RuntimeCommand.schema_version must be >= 1.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type,
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "issued_by": self.issued_by.as_dict(),
            "payload": dict(self.payload),
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RuntimeCommand":
        return cls(
            command_type=str(d.get("command_type", "")),
            session_id=str(d.get("session_id", "")),
            issued_by=IssuedBy.from_dict(d.get("issued_by") or {}),
            idempotency_key=str(d.get("idempotency_key", "")),
            payload=dict(d.get("payload") or {}),
            command_id=str(d.get("command_id", "")) or uuid.uuid4().hex,
            created_at=str(d.get("created_at", "")) or _utc_now(),
            schema_version=int(d.get("schema_version", 1)),
        )


@dataclass(frozen=True)
class CommandAck:
    """The synchronous receipt for a submitted RuntimeCommand. Epic E21 (S21.15).

    Returned in < ~300ms from POST /api/commands. ``status`` is ``received`` (queued,
    will be applied later) or ``rejected`` (failed validation/authz up front). ``seq``
    correlates an accepted command into the SSE stream (the ``command.received`` event's
    sequence); it is None on rejection. A ``rejected`` ack must carry a reason — mirrors
    the IssuedBy guard above: a rejection that cannot say why is a contract hole.
    """

    command_id: str
    status: str
    seq: int | None = None
    rejection_reason: str | None = None
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.command_id:
            raise ControlContractError("CommandAck.command_id is required and must be non-empty.")
        if self.status not in ACCEPT_STATUSES:
            raise ControlContractError(
                f"CommandAck.status must be one of {sorted(ACCEPT_STATUSES)}, got {self.status!r}."
            )
        if self.status == "rejected" and not self.rejection_reason:
            raise ControlContractError("CommandAck(status='rejected') requires a rejection_reason.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "status": self.status,
            "seq": self.seq,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CommandAck":
        return cls(
            command_id=str(d.get("command_id", "")),
            status=str(d.get("status", "")),
            seq=(int(d["seq"]) if d.get("seq") is not None else None),
            rejection_reason=(str(d["rejection_reason"]) if d.get("rejection_reason") else None),
            created_at=str(d.get("created_at", "")) or _utc_now(),
        )


def parse_command(data: dict[str, Any]) -> RuntimeCommand:
    """Validate an incoming command dict into a RuntimeCommand. Missing required fields
    (e.g. ``idempotency_key``, ``issued_by``) raise ControlContractError so the gateway can
    reject + emit ``command.rejected`` before anything enters the queue."""
    if not isinstance(data, dict):
        raise ControlContractError("Command must be a mapping.")
    if not data.get("idempotency_key"):
        raise ControlContractError("Command requires a non-empty 'idempotency_key'.")
    if not isinstance(data.get("issued_by"), dict):
        raise ControlContractError("Command requires an 'issued_by' object.")
    return RuntimeCommand.from_dict(data)
