"""BudgetGuard — block repeated identical tool calls; reuses discipline.Budget. Epic E02/E06."""
from __future__ import annotations

from typing import Any, Callable

from core.schemas import ToolRequest
from discipline import Budget


class BudgetGuard:
    def __init__(self, budget: Budget, *, on_block: Callable[[ToolRequest], None] | None = None) -> None:
        self.budget = budget
        self.on_block = on_block

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        key = Budget.tool_key(request.name, request.args)
        self.budget.record_tool_call(key)
        if self.budget.same_tool_exceeded(key):
            if self.on_block:
                self.on_block(request)
            return {"ok": False, "capability": request.name, "feature": None, "data": {},
                    "error": "Same-tool budget exceeded.", "metadata": {"budget_block": True}}
        return nxt(request)
