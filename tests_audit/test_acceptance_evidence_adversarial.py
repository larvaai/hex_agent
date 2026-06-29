"""Adversarial matrix for evidence-typed acceptance + AC report. Epic E10/E21 (S21.33).

Pins the corners the happy-path tests don't reach: a report cited as its own
evidence (AC5), a resume after FINISHED that must not duplicate the report (AC6),
and the load-bearing gate invariant via hypothesis — a check only ends `passed`
when every cited id resolves on the board AND ≥1 is a real evidence type.
"""
from __future__ import annotations

import json

from hypothesis import given
from hypothesis import strategies as st

from adapters.agents import ScriptedDelegationAgent
from core.bootstrap import build_kernel
from core.session import SessionFactory
from delegation import DelegationManager, DelegationRegistry, InMemoryDelegationStore
from supervisor import SqliteTaskLoopStore, resume_task_loop, run_task_loop
from supervisor.broker import DeterministicBroker
from supervisor.contracts import parse_decision
from supervisor.evidence import evidence_type_of
from supervisor.graph import judge_acceptance
from supervisor.orchestrator import ScriptedOrchestrator
from supervisor.state import AcceptanceCheck, TaskLoopState

KERNEL_CONFIG = {
    "features": {
        "example_echo": {"enabled": True, "module": "features.example_echo"},
        "toolbox": {"enabled": True, "module": "toolbox.feature"},
    }
}
AC = [("ac1", "the criterion")]


def _decision(decision: str, **kw) -> str:
    return json.dumps({"decision": decision, **kw})


def _loop_env():
    """A fully wired offline TaskLoop env (mirrors tests/conftest make_env)."""
    kernel = build_kernel(KERNEL_CONFIG)
    factory = SessionFactory(kernel=kernel)
    supervisor_session = factory.create_root("multi-agent task")
    registry = DelegationRegistry()
    registry.register(ScriptedDelegationAgent("code", artifacts=[{"kind": "finding", "agent": "code"}]))
    delegation_service = DelegationManager(
        registry=registry, sessions=factory, store=InMemoryDelegationStore()
    )
    return supervisor_session, delegation_service


def _run(session, delegation_service, decisions, *, checkpoint_store=None):
    return run_task_loop(
        session,
        "task",
        acceptance_criteria=AC,
        delegation_service=delegation_service,
        orchestrator=ScriptedOrchestrator(
            compose=json.dumps({"selected_agents": [{"agent_id": "code", "reason": "r"}]}),
            decisions=list(decisions),
        ),
        broker=DeterministicBroker(),
        checkpoint_store=checkpoint_store,
    )


# ── AC5: an ac_report cited as evidence is rejected (no circular self-evidence) ──
def test_ac_report_cannot_be_its_own_evidence():
    state = TaskLoopState(session_id="s", task_id="t")
    state.acceptance_checks = [AcceptanceCheck(id="ac1", text="c")]
    state.add_artifact("ac_report-s", {"kind": "ac_report", "session_id": "s", "checks": []})
    decision = parse_decision(
        _decision(
            "finished",
            acceptance_status=[{"id": "ac1", "status": "passed", "evidence_ids": ["ac_report-s"]}],
        )
    )
    judge_acceptance(state, None, decision)  # ctx unused by the gate
    assert state.acceptance_by_id("ac1").status == "pending"


# ── AC6: resume after FINISHED keeps exactly one, unchanged ac_report ────────────
def test_resume_after_finish_keeps_single_ac_report(tmp_path):
    session, delegation_service = _loop_env()
    decisions = [
        _decision("need_tool", tool_requests=[{"tool": "echo", "args": {"k": 1}}]),
        _decision(
            "finished",
            acceptance_status=[{"id": "ac1", "status": "passed", "evidence_ids": ["tool_result-0001"]}],
            final_output={"answer": 1},
        ),
    ]
    store = SqliteTaskLoopStore("run-acreport", path=tmp_path / "acr.sqlite")
    first = _run(session, delegation_service, decisions, checkpoint_store=store)
    assert first["status"] == "finished"
    reports_first = [a for a in first["state"]["artifacts"].values() if a.get("kind") == "ac_report"]
    assert len(reports_first) == 1

    # Resuming a terminal checkpoint returns the persisted result without re-driving.
    resumed = resume_task_loop(
        session,
        checkpoint_store=store,
        delegation_service=delegation_service,
        orchestrator=ScriptedOrchestrator(compose="{}", decisions=[]),
        broker=DeterministicBroker(),
    )
    reports_resumed = [a for a in resumed["state"]["artifacts"].values() if a.get("kind") == "ac_report"]
    assert len(reports_resumed) == 1
    assert reports_resumed[0] == reports_first[0]  # round-tripped through encode/decode, no duplicate


# ── Property: finished/passed ⇒ all cited ids exist AND ≥1 is real evidence ──────
_KINDS = ["tool_result", "delegation_result", "diff", "reviewer_report", "test_result",
          "context_packet", "session_plan", "ac_report", "", "weird_unknown", "__ghost__"]


@given(
    claimed=st.sampled_from(["passed", "failed", "pending"]),
    kinds=st.lists(st.sampled_from(_KINDS), max_size=6),
)
def test_passed_implies_existing_and_typed_evidence(claimed, kinds):
    state = TaskLoopState(session_id="s", task_id="t")
    state.acceptance_checks = [AcceptanceCheck(id="ac1", text="c")]
    evidence_ids = []
    for i, kind in enumerate(kinds):
        eid = f"art-{i}"
        evidence_ids.append(eid)
        if kind != "__ghost__":  # __ghost__ stays off the board (missing id)
            state.add_artifact(eid, {"kind": kind})
    decision = parse_decision(
        _decision("finished", acceptance_status=[{"id": "ac1", "status": claimed, "evidence_ids": evidence_ids}])
    )
    judge_acceptance(state, None, decision)

    check = state.acceptance_by_id("ac1")
    if check.status == "passed":
        # S21.33 invariant at the gate.
        assert all(e in state.artifacts for e in check.evidence_ids)
        assert any(evidence_type_of(state.artifacts[e]) is not None for e in check.evidence_ids)
