"""Session-owned in-memory state with detached snapshot/restore for persistence."""
from __future__ import annotations

import copy
from typing import Any


class StateStore:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def snapshot(self) -> dict[str, Any]:
        """Detached copy of all state, safe to seed another session/checkpoint."""
        return copy.deepcopy(self._data)

    def restore(self, data: dict[str, Any]) -> None:
        """Replace all state wholesale (used on resume)."""
        self._data = copy.deepcopy(data)
