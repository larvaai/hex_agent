"""StateStore — in-memory run state held by the kernel; snapshot/restore for persistence. Epic E01/E07."""
from __future__ import annotations

from typing import Any


class StateStore:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def snapshot(self) -> dict[str, Any]:
        """Shallow copy of all state, for checkpointing."""
        return dict(self._data)

    def restore(self, data: dict[str, Any]) -> None:
        """Replace all state wholesale (used on resume)."""
        self._data = dict(data)
