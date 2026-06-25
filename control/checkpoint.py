"""RuntimeCheckpoint — the approval-gate contract for risky actions. Epic E21 (S21.5).

Distinct from the *state* checkpoint (``supervisor.SqliteTaskLoopStore``, which exists to
resume): a RuntimeCheckpoint is a point where the runtime PAUSES for a human decision
before a dangerous action (tool call, file write, shell, permission change, artifact
overwrite). It starts ``waiting`` and resolves to one terminal status; ``with_status``
enforces the legal transition.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

from control.errors import ControlContractError

CHECKPOINT_STATUSES = frozenset({"waiting", "approved", "rejected", "expired", "auto_approved"})
RESOLVED_STATUSES = frozenset({"approved", "rejected", "expired", "auto_approved"})
RISK_LEVELS = frozenset({"low", "medium", "high", "dangerous"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RuntimeCheckpoint:
    checkpoint_type: str
    session_id: str
    risk_level: str
    status: str = "waiting"
    payload: dict[str, Any] = field(default_factory=dict)
    checkpoint_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_utc_now)
    resolved_at: str | None = None

    def __post_init__(self) -> None:
        for name in ("checkpoint_id", "checkpoint_type", "session_id", "created_at"):
            if not getattr(self, name):
                raise ControlContractError(f"RuntimeCheckpoint.{name} is required and must be non-empty.")
        if self.status not in CHECKPOINT_STATUSES:
            raise ControlContractError(
                f"RuntimeCheckpoint.status must be one of {sorted(CHECKPOINT_STATUSES)}, got {self.status!r}."
            )
        if self.risk_level not in RISK_LEVELS:
            raise ControlContractError(
                f"RuntimeCheckpoint.risk_level must be one of {sorted(RISK_LEVELS)}, got {self.risk_level!r}."
            )
        if not isinstance(self.payload, dict):
            raise ControlContractError("RuntimeCheckpoint.payload must be a mapping.")

    @property
    def is_waiting(self) -> bool:
        return self.status == "waiting"

    def with_status(self, status: str, *, resolved_at: str | None = None) -> "RuntimeCheckpoint":
        """Resolve a ``waiting`` checkpoint to a terminal status. Only ``waiting`` may
        transition; resolving an already-resolved checkpoint is rejected."""
        if status not in RESOLVED_STATUSES:
            raise ControlContractError(
                f"Cannot set checkpoint status to {status!r}; must be one of {sorted(RESOLVED_STATUSES)}."
            )
        if not self.is_waiting:
            raise ControlContractError(
                f"Checkpoint {self.checkpoint_id} is already {self.status!r}; cannot re-resolve."
            )
        return replace(self, status=status, resolved_at=resolved_at or _utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "checkpoint_type": self.checkpoint_type,
            "status": self.status,
            "risk_level": self.risk_level,
            "payload": dict(self.payload),
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RuntimeCheckpoint":
        return cls(
            checkpoint_type=str(d.get("checkpoint_type", "")),
            session_id=str(d.get("session_id", "")),
            risk_level=str(d.get("risk_level", "")),
            status=str(d.get("status", "waiting")),
            payload=dict(d.get("payload") or {}),
            checkpoint_id=str(d.get("checkpoint_id", "")) or uuid.uuid4().hex,
            created_at=str(d.get("created_at", "")) or _utc_now(),
            resolved_at=(str(d["resolved_at"]) if d.get("resolved_at") else None),
        )
