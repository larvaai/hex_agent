"""ToolPort protocol — the seam every concrete tool implements. Epic E01."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.schemas import ToolRequest


@runtime_checkable
class ToolPort(Protocol):
    """A tool executor. Concrete behavior lives behind this port."""

    name: str

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        ...
