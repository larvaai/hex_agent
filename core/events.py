"""EventBus — minimal pub/sub that the observability layer subscribes to. Epic E01/E04."""
from __future__ import annotations

from typing import Any, Callable

Subscriber = Callable[[str, dict[str, Any]], None]


class EventBus:
    """Minimal pub/sub. Observability subscribes here (E04)."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, fn: Subscriber) -> None:
        self._subscribers.append(fn)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        data = payload or {}
        for fn in list(self._subscribers):
            try:
                fn(topic, data)
            except Exception:
                # An observer must never break the runtime.
                pass
