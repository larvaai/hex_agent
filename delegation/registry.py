"""Target-to-port resolution with explicit ambiguity failure."""
from __future__ import annotations

import threading

from core.ports import DelegationPort


class DelegationRegistry:
    def __init__(self) -> None:
        self._handlers: list[DelegationPort] = []
        self._frozen = False
        self._lock = threading.RLock()

    def register(self, handler: DelegationPort) -> None:
        with self._lock:
            if self._frozen:
                raise RuntimeError("Delegation registry is frozen.")
            if any(existing.name == handler.name for existing in self._handlers):
                raise ValueError(f"Delegation handler already registered: {handler.name}")
            self._handlers.append(handler)

    def freeze(self) -> None:
        with self._lock:
            self._frozen = True

    def resolve(self, target: str) -> DelegationPort:
        with self._lock:
            handlers = tuple(self._handlers)
        matches = [handler for handler in handlers if handler.can_handle(target)]
        if not matches:
            raise LookupError(f"No delegation handler registered for target '{target}'.")
        if len(matches) > 1:
            names = sorted(handler.name for handler in matches)
            raise LookupError(f"Ambiguous delegation target '{target}': {names}")
        return matches[0]

    def targets(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(handler.name for handler in self._handlers))
