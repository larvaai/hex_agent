"""Budgets — step / consecutive-parse / per-node attempt, all independent
(lift discipline/budget.py:11-67; consecutive-streak gate mirrors local-model-quirks memory)."""
from __future__ import annotations

from decompose_agent.budget import AttemptBudget, ParseBudget, RootBudget


def test_root_step_budget_increments_and_trips():
    b = RootBudget(max_steps=3)
    for _ in range(3):
        b.record_step()
    assert b.steps == 3
    assert not b.step_exceeded()  # at-limit is fine; lifted strict-`>` semantics
    b.record_step()
    assert b.step_exceeded()  # 4 > 3


def test_parse_budget_gates_on_consecutive_streak():
    pb = ParseBudget(max_parse=3)
    pb.record_error()
    pb.record_error()
    assert pb.consecutive == 2
    assert not pb.parse_exceeded()

    pb.record_success()  # a good parse clears the streak (not the lifetime)
    assert pb.consecutive == 0
    assert not pb.parse_exceeded()

    pb.record_error()
    pb.record_error()
    pb.record_error()
    assert pb.parse_exceeded()  # 3 >= 3 consecutive
    assert pb.lifetime == 5  # lifetime keeps counting for telemetry


def test_parse_error_does_not_advance_step_budget():
    rb = RootBudget(max_steps=5)
    pb = ParseBudget(max_parse=3)
    pb.record_error()
    pb.record_error()
    assert rb.steps == 0  # parse fumbles never consume the step budget


def test_attempt_budget_is_per_node_and_independent():
    a = AttemptBudget(k=3)
    rb = RootBudget(max_steps=100)
    a.record_attempt()
    a.record_attempt()
    assert not a.exhausted()
    a.record_attempt()
    assert a.exhausted()  # 3 >= K
    assert rb.steps == 0  # attempts are independent of the step budget
