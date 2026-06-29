"""Loop budgets — steps, parse-errors, same-tool repeats (parse errors do not consume steps). Epic E02."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Budget:
    """Loop control. Parse-error retries do NOT consume the step budget.

    Parse errors are gated on the **consecutive** streak, not the lifetime total: a local
    model that fumbles one JSON action then recovers has not failed — only a model stuck
    emitting garbage N times *in a row* has. ``parse_errors`` stays as a lifetime counter for
    telemetry; ``consecutive_parse_errors`` (reset on every good parse) is what trips the gate.
    Earlier this gated on the lifetime total at a limit of 3, so 3 scattered fumbles across a
    30-step run killed a run that was making progress."""

    max_steps: int = 30
    max_parse_errors: int = 8  # CONSECUTIVE fumbles tolerated before giving up
    max_same_tool_calls: int = 3
    steps: int = 0
    parse_errors: int = 0  # lifetime total — telemetry only
    consecutive_parse_errors: int = 0  # resets on any good parse — drives the gate
    _tool_calls: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> Budget:
        """Default run budget, tunable without a code change (the IDE/orchestrator knob)."""
        return cls(
            max_steps=int(os.getenv("AGENT_MAX_STEPS", "30")),
            max_parse_errors=int(os.getenv("AGENT_MAX_PARSE_ERRORS", "8")),
            max_same_tool_calls=int(os.getenv("AGENT_MAX_SAME_TOOL", "3")),
        )

    def record_step(self) -> None:
        self.steps += 1
        self.consecutive_parse_errors = 0  # a completed step proves the model recovered

    def step_exceeded(self) -> bool:
        return self.steps > self.max_steps

    def record_parse_error(self) -> None:
        self.parse_errors += 1
        self.consecutive_parse_errors += 1

    def record_parse_success(self) -> None:
        """A well-formed action arrived. Clears the consecutive-fumble streak even when the
        action consumes no step (e.g. an orchestrator decision in the supervisor loop)."""
        self.consecutive_parse_errors = 0

    def parse_exceeded(self) -> bool:
        return self.consecutive_parse_errors >= self.max_parse_errors

    def record_tool_call(self, key: str) -> int:
        self._tool_calls[key] = self._tool_calls.get(key, 0) + 1
        return self._tool_calls[key]

    def same_tool_exceeded(self, key: str) -> bool:
        return self._tool_calls.get(key, 0) > self.max_same_tool_calls

    @staticmethod
    def tool_key(tool_name: str, args: dict[str, Any]) -> str:
        import json

        return tool_name + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False)
