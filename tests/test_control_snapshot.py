"""E21 Phase B — B2 TaskLoopSnapshot projection tests. Maps to acceptance.md S21.9.

The snapshot is a *pure projection* of the canonical event stream (+ optional Blackboard).
These prove: the live agent graph is derived correctly (A done / B running / C pending) with
``orchestrator.last_decision`` + ``pending_agent_calls``; a raw secret never reaches the
snapshot (it reads ``ui_payload`` only); the fold is idempotent under duplicate/out-of-order
events; tool calls + acceptance project through; and it works end-to-end off a real run.
"""
from __future__ import annotations

import json

from control import (
    Actor,
    EventEmitter,
    SessionSeq,
    TraceContext,
    build_snapshot,
)
from supervisor import run_task_loop
from supervisor.state import AcceptanceCheck, TaskLoopState, decode_taskloop_state
from tests.conftest import compose_json, decision_json


class _ListSink:
    """Captures finalized RuntimeEvents the way a durable sink/EventLogger would."""

    def __init__(self) -> None:
        self.events: list = []

    def emit(self, event) -> None:
        self.events.append(event)


def _emitter() -> tuple[EventEmitter, _ListSink]:
    sink = _ListSink()
    return EventEmitter([sink], seq=SessionSeq()), sink


def _run_scenario() -> list:
    """O selects A,B,C and decides to call all three; A finishes, B is mid-run, C never starts.
    B's before_run carries an api_key to prove redaction holds through the projection."""
    em, sink = _emitter()
    trace = TraceContext.new_root()

    def emit(event_type: str, payload: dict) -> None:
        em.emit(event_type, session_id="s1", actor=Actor(type="runtime", id="supervisor"),
                trace=trace, payload=payload)

    emit("loop.team_composed", {"selected": ["A", "B", "C"]})
    emit("loop.decision", {
        "round": 1, "decision": "continue", "reason": "spread the work",
        "next_agent_calls": [
            {"agent_id": "A", "objective": "oa"},
            {"agent_id": "B", "objective": "ob"},
            {"agent_id": "C", "objective": "oc"},
        ],
    })
    emit("agent.before_run", {"agent_id": "A", "round_no": 1})
    emit("agent.after_run", {"agent_id": "A", "summary": "A finished"})
    emit("agent.before_run", {"agent_id": "B", "round_no": 1, "api_key": "sk-secret-xyz"})
    return sink.events


# ── S21.9 live graph projection ──────────────────────────────────────────────
def test_build_snapshot_projects_live_agent_graph():
    snap = build_snapshot(_run_scenario())

    assert snap.agent("A").status == "done"
    assert snap.agent("A").last_output == "A finished"
    assert snap.agent("B").status == "running"
    assert snap.agent("C").status == "pending"

    assert snap.orchestrator["last_decision"] == "continue"
    assert snap.orchestrator["reason"] == "spread the work"
    # Only the not-yet-started call (C) remains queued; A/B have left the queue.
    assert [c["agent_id"] for c in snap.pending_agent_calls] == ["C"]
    assert snap.pending_agent_calls[0]["objective"] == "oc"


def test_snapshot_never_leaks_raw_secret():
    snap = build_snapshot(_run_scenario())
    blob = json.dumps(snap.as_dict())
    assert "sk-secret-xyz" not in blob  # projection reads ui_payload, never raw payload


def test_snapshot_idempotent_under_duplicate_and_out_of_order_events():
    events = _run_scenario()
    duplicated = list(reversed(events)) + events + events  # replay + reorder + at-least-once
    snap = build_snapshot(duplicated)

    assert {a.agent_id: a.status for a in snap.agents} == {"A": "done", "B": "running", "C": "pending"}
    assert len(snap.agents) == 3
    assert [c["agent_id"] for c in snap.pending_agent_calls] == ["C"]


def test_snapshot_projects_tool_calls_without_duplication():
    em, sink = _emitter()
    trace = TraceContext.new_root()
    em.emit("loop.tool", session_id="s1", actor=Actor(type="tool", id="echo"),
            trace=trace, payload={"tool": "echo", "ok": True})
    snap = build_snapshot(sink.events + sink.events)  # same event twice
    assert len(snap.tool_calls) == 1
    assert snap.tool_calls[0]["tool"] == "echo" and snap.tool_calls[0]["ok"] is True


def test_snapshot_enriches_acceptance_and_status_from_blackboard():
    state = TaskLoopState(session_id="s1", task_id="t1", status="in_discussion")
    state.acceptance_checks = [AcceptanceCheck(id="ac1", text="do it", status="passed", evidence_ids=["a-1"])]
    snap = build_snapshot([], state=state)
    assert snap.acceptance_status == ({"id": "ac1", "text": "do it", "status": "passed", "evidence_ids": ["a-1"]},)
    assert snap.status == "in_discussion"  # no terminal event → trust the Blackboard
    assert snap.session_id == "s1"


# ── end-to-end off a real supervisor run ─────────────────────────────────────
def test_snapshot_from_live_supervisor_run(make_env):
    emitter, sink = _emitter()
    env = make_env(
        compose=compose_json(("code", "r"), ("test", "r")),
        decisions=[
            decision_json("continue", next_agent_calls=[
                {"agent_id": "code", "objective": "build", "allowed_capabilities": []},
                {"agent_id": "test", "objective": "verify", "allowed_capabilities": []},
            ]),
            decision_json("blocked", reason="stop"),
        ],
        agent_ids=("code", "test"),
    )
    result = run_task_loop(
        env.supervisor_session, "multi-agent task",
        acceptance_criteria=[("ac1", "do the thing")],
        delegation_service=env.delegation_service,
        orchestrator=env.orchestrator,
        broker=env.broker,
        emitter=emitter,
    )
    snap = build_snapshot(sink.events, state=decode_taskloop_state(result["state"]))

    assert snap.agent("code").status == "done"
    assert snap.agent("test").status == "done"
    assert snap.status == "blocked"  # the loop ended on a blocked decision
    assert snap.session_id == env.supervisor_session.identity.session_id
