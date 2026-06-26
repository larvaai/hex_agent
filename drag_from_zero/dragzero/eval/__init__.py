"""Eval harness (Slice 3b) — scored, not pass/fail.

Invariant tests (Slice 1-3a) pin the harness deterministically. Eval is the
separate, *non-deterministic* slice that scores semantic behaviour — "did the
planner delegate to the right role?" — over many trials and aggregates into a
report. The eval machinery itself is tested deterministically by scoring known
FakeLLM behaviours.

This subpackage consumes the core (orchestrator, events, read-model); the core
never imports it.
"""
from .model import EvalContext, ScoreResult, ScorerAgg
from .runner import render_report, run_scenario, run_suite, run_trial
from .scenario import Scenario

__all__ = [
    "EvalContext",
    "ScoreResult",
    "ScorerAgg",
    "render_report",
    "run_scenario",
    "run_suite",
    "run_trial",
    "Scenario",
]
