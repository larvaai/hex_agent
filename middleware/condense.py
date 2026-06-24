"""CondenseResult — shrink a tool result before re-feeding the model; reuses discipline.condense.
Skips llm.* so the model's own JSON action reaches the parser intact. Epic E02."""
from __future__ import annotations

from typing import Any, Callable

from core.schemas import ToolRequest
from discipline import condense


class CondenseResult:
    def __init__(self, *, max_chars: int = 2000, max_list: int = 10,
                 on_condense: Callable[[ToolRequest], None] | None = None) -> None:
        self.max_chars = max_chars
        self.max_list = max_list
        self.on_condense = on_condense

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        env = nxt(request)
        if request.name.startswith("llm."):
            return env
        if isinstance(env, dict) and isinstance(env.get("data"), (dict, list, str)):
            env["data"] = condense(env["data"], max_chars=self.max_chars, max_list=self.max_list)
            if self.on_condense:
                self.on_condense(request)
        return env
