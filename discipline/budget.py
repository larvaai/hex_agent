"""Loop budgets — steps, parse-errors, same-tool repeats (parse errors do not consume steps). Epic E02."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Budget:
    """Loop control. Parse-error retries do NOT consume the step budget."""

    max_steps: int = 30
    max_parse_errors: int = 3
    max_same_tool_calls: int = 3
    steps: int = 0
    parse_errors: int = 0
    _tool_calls: dict[str, int] = field(default_factory=dict)

    def record_step(self) -> None:
        self.steps += 1

    def step_exceeded(self) -> bool:
        return self.steps > self.max_steps

    def record_parse_error(self) -> None:
        self.parse_errors += 1

    def parse_exceeded(self) -> bool:
        return self.parse_errors >= self.max_parse_errors

    def record_tool_call(self, key: str) -> int:
        self._tool_calls[key] = self._tool_calls.get(key, 0) + 1
        return self._tool_calls[key]

    def same_tool_exceeded(self, key: str) -> bool:
        return self._tool_calls.get(key, 0) > self.max_same_tool_calls

    @staticmethod
    def tool_key(tool_name: str, args: dict[str, Any]) -> str:
        import json

        return tool_name + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False)
