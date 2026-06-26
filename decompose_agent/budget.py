"""Convergence meters — step / consecutive-parse / per-node attempt, all independent
(lift discipline/budget.py:11-67).

Three separate meters because they fail for different reasons and must not bleed into each
other: a parse fumble is not progress (so it must NOT consume a step), and it is only a
*streak* of fumbles that means the model is stuck — a scattered one that then recovers is
fine. Per-node attempts (K) are local to a leaf and orthogonal to the per-root step budget.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RootBudget:
    """Per-root step budget — the single D10 backstop. `step_exceeded` mirrors the lifted
    strict-`>` semantics: at-limit is still allowed, the next step trips it."""

    max_steps: int = 30
    steps: int = 0

    @classmethod
    def from_env(cls) -> "RootBudget":
        return cls(max_steps=int(os.getenv("AGENT_MAX_STEPS", "30")))

    def record_step(self) -> None:
        self.steps += 1

    def step_exceeded(self) -> bool:
        return self.steps > self.max_steps


@dataclass
class ParseBudget:
    """Parse-error meter gated on the **consecutive** streak, not the lifetime total.

    `consecutive` resets on every good parse and is what trips the gate; `lifetime` keeps
    counting for telemetry. Gating on lifetime would kill a long run that fumbled a few
    scattered actions but kept making progress (the local-model-quirks lesson)."""

    max_parse: int = 8
    consecutive: int = 0
    lifetime: int = 0

    @classmethod
    def from_env(cls) -> "ParseBudget":
        return cls(max_parse=int(os.getenv("AGENT_MAX_PARSE_ERRORS", "8")))

    def record_error(self) -> None:
        self.consecutive += 1
        self.lifetime += 1

    def record_success(self) -> None:
        """A well-formed reply arrived — clear the streak even if it consumed no step."""
        self.consecutive = 0

    def parse_exceeded(self) -> bool:
        return self.consecutive >= self.max_parse


@dataclass
class AttemptBudget:
    """Per-node leaf-attempt counter (K). Independent of the step budget — exhausting K
    means "decompose or block this node", not "stop the run"."""

    k: int = 3
    attempts: int = 0

    def record_attempt(self) -> None:
        self.attempts += 1

    def exhausted(self) -> bool:
        return self.attempts >= self.k

    def remaining(self) -> int:
        return max(0, self.k - self.attempts)
