"""ToolMiddleware protocol — pre/post hook around execute_tool. Epic E01/E06."""
from __future__ import annotations

from typing import Any, Callable, Protocol

from core.schemas import ToolRequest

ToolHandler = Callable[[ToolRequest], dict[str, Any]]


class ToolMiddleware(Protocol):
    """Receives the request and `nxt` (the inner handler). May act before/after,
    short-circuit (return without calling nxt), or modify the result envelope."""

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]: ...
