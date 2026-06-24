"""E10 S10.10 — checkpoint/resume from the SQLite Blackboard.

A run interrupted mid-loop resumes from the persisted Blackboard and continues from
the next pending round, without re-running a completed worker turn.
"""
from __future__ import annotations

from supervisor import SqliteTaskLoopStore, resume_task_loop, run_task_loop
from supervisor.state import AcceptanceCheck, AgentTurn, TaskLoopState, TaskLoopStatus
from tests.conftest import RecordingDelegationAgent, compose_json, decision_json

AC = [("ac1", "the criterion")]


def call(agent_id):
    return {"agent_id": agent_id, "objective": "work", "scope_of_work": "s", "allowed_capabilities": []}


def test_checkpoint_persisted_during_run(make_env, tmp_path):
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[decision_json("blocked", reason="stop")],
    )
    store = SqliteTaskLoopStore("run-persist", path=tmp_path / "persist.sqlite")
    result = run_task_loop(
        env.supervisor_session,
        "task",
        acceptance_criteria=AC,
        delegation_service=env.delegation_service,
        orchestrator=env.orchestrator,
        broker=env.broker,
        checkpoint_store=store,
    )
    loaded = store.load()
    assert loaded is not None
    assert loaded.status == result["status"] == "blocked"


def test_resume_skips_completed_turn(make_env, tmp_path):
    code = RecordingDelegationAgent("code")
    test = RecordingDelegationAgent("test")
    env = make_env(
        compose=compose_json(("code", "r"), ("test", "r")),
        decisions=[decision_json("continue", next_agent_calls=[call("code"), call("test")])],
        agent_ids=("code", "test"),
        workers={"code": code, "test": test},
    )
    store = SqliteTaskLoopStore("run-resume", path=tmp_path / "resume.sqlite")

    # Seed a Blackboard interrupted mid-round 0: "code" already produced its turn.
    state = TaskLoopState(
        session_id=env.supervisor_session.identity.session_id,
        task_id=env.supervisor_session.identity.task_id,
        status=TaskLoopStatus.IN_DISCUSSION.value,
        selected_agents=["code", "test"],
        round_no=0,
        max_rounds=3,
    )
    state.acceptance_checks = [AcceptanceCheck(id="ac1", text="c")]
    state.artifacts = {"session_plan-0000": {"kind": "session_plan"}, "seed-art": {"kind": "x"}}
    state.turns = [AgentTurn(round_no=0, agent_id="code", packet_id="p", output_summary="success", artifact_ids=["seed-art"])]
    store.save(state)

    result = resume_task_loop(
        env.supervisor_session,
        checkpoint_store=store,
        delegation_service=env.delegation_service,
        orchestrator=env.orchestrator,
        broker=env.broker,
    )
    assert code.calls == []           # completed turn was NOT re-run
    assert len(test.calls) == 1       # the remaining agent ran
    assert result["selected_agents"] == ["code", "test"]  # Blackboard restored


def test_resume_terminal_checkpoint_returns_result(make_env, tmp_path):
    env = make_env(compose=compose_json(("code", "r")), decisions=[])
    store = SqliteTaskLoopStore("run-terminal", path=tmp_path / "terminal.sqlite")
    store.save(
        TaskLoopState(
            session_id="s", task_id="t", status=TaskLoopStatus.FINISHED.value, final_output={"x": 1}
        )
    )
    result = resume_task_loop(
        env.supervisor_session,
        checkpoint_store=store,
        delegation_service=env.delegation_service,
        orchestrator=env.orchestrator,
        broker=env.broker,
    )
    assert result["status"] == "finished"
    assert result["final_output"] == {"x": 1}
