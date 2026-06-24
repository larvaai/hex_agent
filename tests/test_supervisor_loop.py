"""E10 supervisor TaskLoop — core plumbing (offline, deterministic).

AC: S10.1 compose, S10.2 bounded loop, S10.3 scoped packet, S10.5 worker=delegation,
S10.8 structured decision, S10.9 tool via chokepoint, S10.11 E05 substrate reuse.
"""
from __future__ import annotations

from adapters.agents import LangGraphDelegationAgent
from core.ports import DelegationPort
from supervisor import run_task_loop
from tests.conftest import RecordingDelegationAgent, compose_json, decision_json

AC = [("ac1", "do the thing")]


def call(agent_id, *, scope=(), objective="work"):
    return {
        "agent_id": agent_id,
        "objective": objective,
        "scope_of_work": f"{agent_id} scope",
        "allowed_capabilities": list(scope),
    }


def run(env, **kw):
    return run_task_loop(
        env.supervisor_session,
        "multi-agent task",
        acceptance_criteria=AC,
        delegation_service=env.delegation_service,
        orchestrator=env.orchestrator,
        broker=env.broker,
        **kw,
    )


# ── S10.1 team composition ───────────────────────────────────────────────────
def test_compose_minimal_team_with_reasons(make_env):
    env = make_env(
        compose=compose_json(("code", "needs a code change")),  # picks 1 of 2
        decisions=[decision_json("blocked", reason="done exploring")],
        agent_ids=("code", "test"),
    )
    result = run(env)
    assert result["selected_agents"] == ["code"]  # fewer than N
    plan = result["state"]["artifacts"]["session_plan-0000"]
    assert plan["selected_agents"][0]["reason"] == "needs a code change"


# ── S10.2 bounded dialogue loop ──────────────────────────────────────────────
def test_round_delegates_each_agent_once(make_env):
    workers = {"code": RecordingDelegationAgent("code"), "test": RecordingDelegationAgent("test")}
    env = make_env(
        compose=compose_json(("code", "r"), ("test", "r")),
        decisions=[
            decision_json("continue", next_agent_calls=[call("code"), call("test")]),
            decision_json("blocked", reason="stop"),
        ],
        agent_ids=("code", "test"),
        workers=workers,
    )
    result = run(env)
    assert len(workers["code"].calls) == 1
    assert len(workers["test"].calls) == 1
    round0_turns = [t for t in result["state"]["turns"] if t["round_no"] == 0]
    assert {t["agent_id"] for t in round0_turns} == {"code", "test"}


# ── S10.3 scoped context packet ──────────────────────────────────────────────
def test_child_has_only_packet_not_parent_transcript(make_env):
    worker = RecordingDelegationAgent("code")
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[
            decision_json("continue", next_agent_calls=[call("code", scope=["fs_read"])]),
            decision_json("blocked", reason="stop"),
        ],
        workers={"code": worker},
    )
    run(env)
    child_context = worker.calls[0]["context"]
    assert set(child_context) == {"briefing", "source_ids"}  # only the packet
    assert "messages" not in child_context  # no parent transcript


# ── S10.5 worker turn = delegation, scope subset ─────────────────────────────
def test_turn_runs_via_delegate_with_scope_subset(make_env):
    worker = RecordingDelegationAgent("code")
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[
            decision_json("continue", next_agent_calls=[call("code", scope=["fs_read"])]),
            decision_json("blocked", reason="stop"),
        ],
        workers={"code": worker},
    )
    run(env)
    assert worker.calls[0]["scope"] == {"fs_read"}
    assert worker.calls[0]["scope"] <= set(env.supervisor_session.allowed_capabilities)


# ── S10.8 structured O decision ──────────────────────────────────────────────
def test_bad_json_repaired_then_proceeds(make_env):
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=['{"decision":"blocked","reason":"trailing comma",}'],  # repairable
    )
    result = run(env)
    assert result["status"] == "blocked"
    assert result["reason"] == "trailing comma"


def test_parse_error_budget_exhausted_fails(make_env):
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=["not json", "still not json", "nope"],
    )
    result = run(env)
    assert result["status"] == "failed"
    assert "parse-error budget" in result["reason"]


# ── S10.9 tool via the kernel chokepoint ─────────────────────────────────────
def test_need_tool_crosses_execute_tool(make_env):
    env = make_env(
        compose=compose_json(("code", "r")),
        decisions=[
            decision_json("need_tool", tool_requests=[{"tool": "echo", "args": {"x": 1}}]),
            decision_json("blocked", reason="stop"),
        ],
    )
    seen: list[str] = []
    env.kernel.events.subscribe(lambda topic, payload: seen.append(topic))
    result = run(env)
    assert "tool.requested" in seen and "tool.completed" in seen
    tool_artifacts = [a for a in result["state"]["artifacts"].values() if a["kind"] == "tool_result"]
    assert tool_artifacts and tool_artifacts[0]["tool"] == "echo" and tool_artifacts[0]["ok"] is True


# ── S10.11 reuse the single-agent substrate (structural) ─────────────────────
def test_worker_uses_e05_delegation_substrate():
    # Worker turns delegate through a DelegationPort; the E05 graph adapter IS one,
    # so the loop reuses the single-agent substrate rather than a bespoke loop.
    assert isinstance(LangGraphDelegationAgent("agent:general"), DelegationPort)
