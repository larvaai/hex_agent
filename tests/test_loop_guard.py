"""E10 loop guard — S10.7: terminate on no-progress, max_rounds, or repeated decisions."""
from __future__ import annotations

from supervisor import run_task_loop
from tests.conftest import compose_json, decision_json

AC = [("ac1", "the criterion")]


def call(agent_id="code"):
    return {"agent_id": agent_id, "objective": "work", "scope_of_work": "s", "allowed_capabilities": []}


def run(env, **kw):
    return run_task_loop(
        env.supervisor_session,
        "task",
        acceptance_criteria=AC,
        delegation_service=env.delegation_service,
        orchestrator=env.orchestrator,
        broker=env.broker,
        **kw,
    )


def test_no_progress_blocks(make_env):
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[decision_json("continue", next_agent_calls=[])],  # nothing happens
    )
    result = run(env)
    assert result["status"] == "blocked"
    assert "no progress" in result["reason"]


def test_max_rounds_terminates(make_env):
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[decision_json("continue", next_agent_calls=[call()]) for _ in range(5)],
    )
    result = run(env, max_rounds=2)
    assert result["status"] == "blocked"
    assert result["reason"] == "max_rounds reached"
    assert result["rounds"] == 2


def test_repeated_decision_blocks(make_env):
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[decision_json("continue", next_agent_calls=[call()]) for _ in range(6)],
    )
    result = run(env, max_rounds=10, max_decision_repeats=2)
    assert result["status"] == "blocked"
    assert "repeated the same decision" in result["reason"]
