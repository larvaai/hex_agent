"""Data types shared by scorers and the runner (no core imports → no cycles)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScoreResult:
    name: str
    score: float          # 0.0 .. 1.0
    passed: bool          # the scorer's own threshold decision
    detail: str = ""


@dataclass
class EvalContext:
    scenario: object      # Scenario
    log: object           # EventLog
    root: object          # Optional[TaskNode]
    nodes: dict           # task_id -> TaskNode
    orchestrator: object  # Orchestrator (for roster lookups)


@dataclass
class ScorerAgg:
    name: str
    n: int
    pass_rate: float      # fraction of trials that passed
    mean: float
    min: float
    max: float
    variance: float       # population variance across trials
