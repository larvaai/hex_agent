"""Thread-safe subscriber registry with detached event delivery."""
from __future__ import annotations

import copy
import threading
from typing import Any, Callable

Subscriber = Callable[[str, dict[str, Any]], None]


class EventBus:
    """Minimal pub/sub. Observability subscribes here (E04)."""

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
                fn(topic, copy.deepcopy(data))
            except Exception:
                # An observer must never break the runtime.
                pass
