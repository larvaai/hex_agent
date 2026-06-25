"""Ports for the Realtime Control Plane — the seams transport/storage sit behind. Epic E21.

Phase A/B keep concrete impls local (in-process EventBus → JSONL, SQLite). These Protocols
are the swap points so Kafka/Redis/Postgres adapters can land later WITHOUT touching the
emitter, supervisor, or kernel (the T2 tier in 02_FULL_FEATURE_MAP).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from control.events import RuntimeEvent


@runtime_checkable
class EventSinkPort(Protocol):
    """A durable/transport sink the emitter forwards each finalized event to.

    v1 impl: ``BusEventSink`` (in-process EventBus → EventLogger JSONL). T2: a Kafka
    adapter implementing the same ``emit`` is dropped in with no caller change.
    """

    def emit(self, event: RuntimeEvent) -> None: ...
