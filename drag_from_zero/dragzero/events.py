"""Event types and the append-only log — the single source of truth.

The execution tree (Đồ thị 2) is never stored; it is folded from these events.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Optional


class EventType(str, Enum):
    ROOT_TASK_CREATED = "root_task_created"
    TASK_STARTED = "task_started"
    PLAN_PRODUCED = "plan_produced"
    DELEGATION_DECIDED = "delegation_decided"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    SUBTASK_SPAWNED = "subtask_spawned"
    TASK_WAITING = "task_waiting"
    AGENT_JOINED = "agent_joined"
    AGENT_LEFT = "agent_left"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    BUDGET_EXCEEDED = "budget_exceeded"
    HOOK_BLOCKED = "hook_blocked"
    # Gap 3 — capability gate (append-only: the value string is the on-disk wire format)
    TOOL_DENIED = "tool_denied"
    CAPABILITY_EXHAUSTED = "capability_exhausted"
    # Gap 2 — decompose-until-trivial
    LEAF_VERIFIED = "leaf_verified"                    # a code-owned PASS/FAIL of one leaf attempt
    DECOMPOSITION_PROPOSED = "decomposition_proposed"  # worker proposed children
    DECOMPOSITION_ACCEPTED = "decomposition_accepted"  # Gate-2 accepted (mu shrank, covered)
    DECOMPOSITION_REJECTED = "decomposition_rejected"  # Gate-2 rejected (reasons in payload)


@dataclass(frozen=True)
class Event:
    type: EventType
    seq: int = -1
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    payload: dict = field(default_factory=dict)


class EventLog:
    """Append-only event log. In-memory is a cache; when a `ledger` is attached, the JSONL on
    disk is the truth — every append is flushed durably before it returns, so resume = re-read.

    The live view subscribes; it never owns state.
    """

    def __init__(self, ledger=None) -> None:
        self._events: list[Event] = []
        self._subs: list[Callable[[Event], None]] = []
        self._ledger = ledger  # a ledger.Ledger, or None for in-memory-only (unit tests)

    def append(self, event: Event) -> Event:
        stamped = replace(event, seq=len(self._events))
        self._events.append(stamped)
        if self._ledger is not None:
            self._ledger.append(stamped)  # durable BEFORE subscribers see it
        for sub in self._subs:
            sub(stamped)
        return stamped

    @classmethod
    def replay(cls, ledger) -> "EventLog":
        """Rebuild an EventLog from a disk ledger (preserving on-disk seqs), attached so further
        appends continue the same ledger. Resume is `reduce(replay(ledger).events())`."""
        log = cls(ledger=ledger)
        log._events = ledger.read()  # seqs come from disk, not re-stamped
        return log

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        self._subs.append(fn)

    def events(self) -> list[Event]:
        return list(self._events)

    def of_type(self, t: EventType) -> list[Event]:
        return [e for e in self._events if e.type == t]

    def types(self) -> list[EventType]:
        return [e.type for e in self._events]

    def __iter__(self):
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)
