"""Convergence meters for the decompose loop — three independent counters (vendored from
decompose_agent/budget.py). They fail for different reasons and must never bleed:

  * RootBudget — per-root STEP backstop (D10). Every decompose() costs a step; the run stops
    when steps exceed the cap, independent of the mu proof.
  * AttemptBudget — per-node leaf attempts (K). Exhausting K means "decompose or block", not
    "stop the run". Leaf-ness is DISCOVERED by exhausting K, never asked of the model.
  * ParseBudget — gated on the CONSECUTIVE fumble streak, not the lifetime total: a scattered
    bad reply that then recovers is fine; only a run of them means the model is stuck.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RootBudget:
    """Per-root step backstop. Strict `>`: at-limit is allowed, the next step trips it."""

    max_steps: int = 60
    steps: int = 0

    def record_step(self) -> None:
        self.steps += 1

    def step_exceeded(self) -> bool:
        return self.steps > self.max_steps


@dataclass
class AttemptBudget:
    """Per-node leaf-attempt counter (K). Orthogonal to the step budget."""

    k: int = 3
    attempts: int = 0

    def record_attempt(self) -> None:
        self.attempts += 1

    def exhausted(self) -> bool:
        return self.attempts >= self.k


@dataclass
class ParseBudget:
    """Parse-fumble meter on the CONSECUTIVE streak. A good reply clears the streak."""

    max_parse: int = 4
    consecutive: int = 0
    lifetime: int = 0

    def record_error(self) -> None:
        self.consecutive += 1
        self.lifetime += 1

    def record_success(self) -> None:
        self.consecutive = 0

    def parse_exceeded(self) -> bool:
        return self.consecutive >= self.max_parse
