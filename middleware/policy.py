"""PolicyGate — deny-list chokepoint; blocks a tool before it runs. Epic E06."""
from __future__ import annotations

from typing import Any, Callable

from core.schemas import ToolRequest


class PolicyGate:
    def __init__(self, *, deny: set[str] | None = None,
                 on_block: Callable[[ToolRequest], None] | None = None) -> None:
        self.deny = set(deny or ())
        self.on_block = on_block

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        if request.name in self.deny:
            if self.on_block:
                self.on_block(request)
            return {"ok": False, "capability": request.name, "feature": None, "data": {},
                    "error": f"Blocked by policy: {request.name}", "metadata": {"policy_block": True}}
        return nxt(request)
