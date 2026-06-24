"""E10 acceptance gate — S10.6: finished only with evidence on the Blackboard."""
from __future__ import annotations

from supervisor import run_task_loop
from tests.conftest import compose_json, decision_json

AC = [("ac1", "the criterion")]


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


def test_no_finish_without_evidence(make_env):
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[decision_json("finished", final_output={"answer": 1})],  # no acceptance evidence
    )
    result = run(env)
    assert result["status"] != "finished"
    assert result["acceptance"][0]["status"] == "pending"


def test_finished_evidence_must_exist_on_board(make_env):
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[
            decision_json(
                "finished",
                acceptance_status=[{"id": "ac1", "status": "passed", "evidence_ids": ["ghost-9999"]}],
                final_output={"answer": 1},
            )
        ],
    )
    result = run(env)
    assert result["status"] != "finished"  # fabricated evidence rejected
    assert result["acceptance"][0]["status"] == "pending"


def test_finish_allowed_with_real_evidence(make_env):
    # round 0 produces a real tool_result artifact; round 1 finishes citing it.
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[
            decision_json("need_tool", tool_requests=[{"tool": "echo", "args": {"k": 1}}]),
            decision_json(
                "finished",
                acceptance_status=[{"id": "ac1", "status": "passed", "evidence_ids": ["tool_result-0001"]}],
                final_output={"answer": 42},
            ),
        ],
    )
    result = run(env)
    assert result["status"] == "finished"
    assert result["acceptance"][0]["status"] == "passed"
    assert result["acceptance"][0]["evidence_ids"] == ["tool_result-0001"]
    assert result["final_output"] == {"answer": 42}
