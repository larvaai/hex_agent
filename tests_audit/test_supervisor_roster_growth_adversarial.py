"""Phase 5 — adversarial guards for E21 roster growth + department targeting.

Strict-audit discipline: no xfail, no lowered assertions. Each test attacks one
plan invariant under adversarial conditions and complements the Phase 1-4 unit
tests with integrated, resume-real scenarios:

  1. Resume never double-applies (real SQLite round-trip).
  1b. The end-of-round checkpoint is atomic — no snapshot ever shows a grown
      roster without the matching applied key (red-team FM6).
  2. Idempotency holds under repeated identical commands.
  3. An unknown role/department is surfaced (command.rejected), never silently
     swallowed into an empty team.
  4. Department expansion never widens scope, and O cannot grant a member a
     capability the supervisor itself lacks.
  5. The authority gate still raises for a non-admitted agent-level call.
  6. Trust-O does not leak to a human-issued command.

NOTE on (3): the plan body + Phase 3/4 (red-team round 2, FM4 'dept/agent
disambiguation') make an unresolved department a SOFT rejection — emit
command.rejected, do not raise — so one bad target cannot kill the round. That
supersedes the lone "run_round raise" wording in phase-05's requirement 3; the
shared intent ("don't swallow into a silently-empty team") is satisfied by the
surfaced rejection, which is what this test asserts.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

import roles as roles_pkg
import skills as skills_pkg
from adapters.agents import ScriptedDelegationAgent
from core.bootstrap import build_kernel
from core.session import SessionFactory
from delegation import DelegationManager, DelegationRegistry, InMemoryDelegationStore
from roles import AgentRegistry
from roles.lenses import LensRegistry
from skills import SkillRegistry
from supervisor import DeterministicBroker, SqliteTaskLoopStore, resume_task_loop, run_task_loop
from supervisor.orchestrator import ScriptedOrchestrator
from supervisor.state import (
    AcceptanceCheck,
    TaskLoopState,
    TaskLoopStatus,
    encode_taskloop_state,
)

LIBRARY = Path(roles_pkg.__file__).parent / "library"
LENSES = LIBRARY / "lenses"
SKILLS_LIBRARY = Path(skills_pkg.__file__).parent / "library"
KERNEL_CONFIG = {
    "features": {
        "example_echo": {"enabled": True, "module": "features.example_echo"},
        "toolbox": {"enabled": True, "module": "toolbox.feature"},
    }
}
AC = [("ac1", "the criterion")]


def make_registry() -> AgentRegistry:
    skills = SkillRegistry()
    skills.load_dir(SKILLS_LIBRARY)
    lenses = LensRegistry()
    lenses.load_dir(LENSES)
    reg = AgentRegistry(skills=skills, lenses=lenses)
    reg.load_dir(LIBRARY)
    return reg


def _compose(*selected: str) -> str:
    return json.dumps({"selected_agents": [{"agent_id": a, "reason": "r"} for a in selected]})


def _decision(decision: str, **kw: Any) -> str:
    return json.dumps({"decision": decision, **kw})


def _add(agent_id: str) -> dict:
    return {"command_type": "AddAgentToLoop", "payload": {"agent_id": agent_id}}


class RecordingScopeAgent:
    """Worker that records the child scope it was delegated with (for scope checks)."""

    def __init__(self, target: str) -> None:
        self.name = target          # DelegationRegistry indexes handlers by .name
        self.target = target
        self.scopes: list[frozenset[str]] = []

    def can_handle(self, target: str) -> bool:
        return target == self.target

    def run(self, request, child_session, progress_sink):
        from core.schemas import ArtifactEnvelope, DelegationResult
        import uuid
        self.scopes.append(frozenset(child_session.allowed_capabilities))
        art = ArtifactEnvelope(uuid.uuid4().hex, "record", {"agent": self.target})
        return DelegationResult(
            delegation_id=request.delegation_id,
            parent_task_id=request.parent_task_id,
            outcome="success",
            artifacts=(art,),
            summary={"agent": self.target},
        )


class RecordingStore:
    """Wraps a SqliteTaskLoopStore, snapshotting every saved state for invariants."""

    def __init__(self, inner: SqliteTaskLoopStore) -> None:
        self.inner = inner
        self.snapshots: list[dict[str, Any]] = []

    @property
    def run_id(self):
        return self.inner.run_id

    def save(self, state: TaskLoopState) -> None:
        self.snapshots.append(copy.deepcopy(encode_taskloop_state(state)))
        self.inner.save(state)

    def load(self):
        return self.inner.load()


def _wire(*, agent_ids, workers=None):
    kernel = build_kernel(KERNEL_CONFIG)
    factory = SessionFactory(kernel=kernel)
    session = factory.create_root("multi-agent task")
    topics: list[str] = []
    kernel.events.subscribe(lambda t, p: topics.append(t))
    registry = DelegationRegistry()
    built: dict[str, Any] = {}
    for aid in agent_ids:
        worker = (workers or {}).get(aid) or ScriptedDelegationAgent(aid, artifacts=[{"kind": "finding", "agent": aid}])
        registry.register(worker)
        built[aid] = worker
    delegation = DelegationManager(registry=registry, sessions=factory, store=InMemoryDelegationStore())
    return session, delegation, topics, built


def _run(session, delegation, *, compose, decisions, **kw):
    return run_task_loop(
        session, "ship a change",
        acceptance_criteria=AC,
        delegation_service=delegation,
        orchestrator=ScriptedOrchestrator(compose=compose, decisions=list(decisions)),
        broker=DeterministicBroker(),
        agent_registry=make_registry(),
        **kw,
    )


def _turn_agents(result: dict[str, Any]) -> list[str]:
    return [t["agent_id"] for t in result["state"]["turns"]]


# ── 1. resume never double-applies ───────────────────────────────────────────
def test_resume_does_not_double_apply(tmp_path):
    session, delegation, _, _ = _wire(agent_ids=("code", "reviewer"))
    store = SqliteTaskLoopStore("run-dbl", path=tmp_path / "dbl.sqlite")

    # Seed a checkpoint AS IF round 0 already admitted reviewer (atomic save).
    state = TaskLoopState(
        session_id=session.identity.session_id,
        task_id=session.identity.task_id,
        status=TaskLoopStatus.IN_DISCUSSION.value,
        selected_agents=["code", "reviewer"],
        round_no=1,
        max_rounds=5,
    )
    state.acceptance_checks = [AcceptanceCheck(id="ac1", text="c")]
    state.artifacts = {"session_plan-0000": {"kind": "session_plan"}}
    state.applied_command_keys = ["AddAgentToLoop:reviewer"]
    store.save(state)

    # Resume; O re-issues the SAME AddAgentToLoop. It must be deduped, not re-applied.
    result = resume_task_loop(
        session,
        checkpoint_store=store,
        delegation_service=delegation,
        orchestrator=ScriptedOrchestrator(
            compose="",
            decisions=[
                _decision("continue", next_agent_calls=[{"agent_id": "code", "objective": "x"}],
                          commands=[_add("reviewer")]),
                _decision("blocked", reason="done"),
            ],
        ),
        broker=DeterministicBroker(),
        agent_registry=make_registry(),
    )
    assert result["selected_agents"].count("reviewer") == 1
    loaded = store.load()
    assert loaded.applied_command_keys.count("AddAgentToLoop:reviewer") == 1


# ── 1b. the end-of-round checkpoint is atomic (red-team FM6) ──────────────────
def test_checkpoint_is_atomic_no_half_applied_state(tmp_path):
    session, delegation, _, _ = _wire(agent_ids=("code", "reviewer"))
    store = RecordingStore(SqliteTaskLoopStore("run-atomic", path=tmp_path / "atomic.sqlite"))
    result = _run(
        session, delegation,
        compose=_compose("code"),
        decisions=[
            _decision("continue", next_agent_calls=[{"agent_id": "code", "objective": "x"}],
                      commands=[_add("reviewer")]),
            _decision("blocked", reason="done"),
        ],
        checkpoint_store=store,
    )
    # Invariant: no snapshot ever shows reviewer in the roster without its applied key.
    for snap in store.snapshots:
        if "reviewer" in snap["selected_agents"]:
            assert "AddAgentToLoop:reviewer" in snap["applied_command_keys"]
    # And the persisted state is coherent: roster grown, key recorded, queue cleared.
    loaded = store.load()
    assert "reviewer" in loaded.selected_agents
    assert "AddAgentToLoop:reviewer" in loaded.applied_command_keys
    assert loaded.pending_commands == []
    assert "reviewer" in result["selected_agents"]


# ── 2. idempotency under repeated identical commands ─────────────────────────
def test_repeated_command_grows_roster_once():
    session, delegation, _, _ = _wire(agent_ids=("code", "reviewer"))
    same = _decision("continue", next_agent_calls=[{"agent_id": "code", "objective": "x"}],
                     commands=[_add("reviewer")])
    result = _run(session, delegation, compose=_compose("code"),
                  decisions=[same, same, _decision("blocked", reason="done")])
    assert result["selected_agents"].count("reviewer") == 1
    assert result["state"]["applied_command_keys"].count("AddAgentToLoop:reviewer") == 1


# ── 3. unknown role / department surfaced, not swallowed ─────────────────────
def test_unknown_role_is_rejected_and_not_added():
    session, delegation, topics, _ = _wire(agent_ids=("code",))
    result = _run(session, delegation, compose=_compose("code"),
                  decisions=[
                      _decision("continue", next_agent_calls=[{"agent_id": "code", "objective": "x"}],
                                commands=[_add("ghost")]),
                      _decision("blocked", reason="done"),
                  ])
    assert "ghost" not in result["selected_agents"]
    assert "command.rejected" in topics


def test_unknown_department_is_rejected_not_swallowed():
    # Soft rejection (FM4): the round survives, the error is surfaced, and no
    # phantom member is added — never a silently-empty team.
    session, delegation, topics, _ = _wire(agent_ids=("code",))
    result = _run(session, delegation, compose=_compose("code"),
                  decisions=[
                      _decision("continue", next_agent_calls=[
                          {"agent_id": "ghosts", "objective": "x", "target_kind": "department"}]),
                      _decision("blocked", reason="done"),
                  ])
    assert "command.rejected" in topics
    assert result["selected_agents"] == ["code"]      # nothing phantom admitted
    assert _turn_agents(result) == []                 # no spurious turn


# ── 4. scope never widens; ceiling still enforced after expansion ────────────
def test_department_members_keep_exact_scope():
    code = RecordingScopeAgent("code")
    reviewer = RecordingScopeAgent("reviewer")
    session, delegation, _, _ = _wire(agent_ids=("code", "reviewer"),
                                      workers={"code": code, "reviewer": reviewer})
    _run(session, delegation, compose=_compose("code", "reviewer"),
         decisions=[
             _decision("continue", next_agent_calls=[
                 {"agent_id": "engineering", "objective": "eng",
                  "allowed_capabilities": ["fs_read"], "target_kind": "department"}]),
             _decision("blocked", reason="done"),
         ])
    # Each member got EXACTLY the O-granted scope — no widening, no extra tool.
    assert code.scopes == [frozenset({"fs_read"})]
    assert reviewer.scopes == [frozenset({"fs_read"})]
    # …and that scope is within the supervisor's own ceiling.
    assert frozenset({"fs_read"}) <= frozenset(session.allowed_capabilities)


def test_department_member_cannot_exceed_supervisor_scope():
    # O grants a capability the supervisor root does not have. The scope-subset rule
    # (delegation/policy.py) rejects the delegation, so the phantom cap never reaches
    # a child session — the safety ceiling still holds after department expansion.
    member = RecordingScopeAgent("code")
    session, delegation, _, _ = _wire(agent_ids=("code",), workers={"code": member})
    result = _run(session, delegation, compose=_compose("code"),
                  decisions=[
                      _decision("continue", next_agent_calls=[
                          {"agent_id": "engineering", "objective": "eng",
                           "allowed_capabilities": ["phantom_cap_xyz"], "target_kind": "department"}]),
                      _decision("blocked", reason="done"),
                  ])
    assert member.scopes == []          # the member never ran with the phantom cap
    rejected = [
        a for a in result["state"]["artifacts"].values()
        if a.get("kind") == "delegation_result" and a.get("outcome") == "rejected"
    ]
    assert rejected, "out-of-ceiling scope must be rejected, not silently granted"
    assert "scope" in (rejected[0].get("error") or "").lower()


# ── 5. authority gate still raises for a non-admitted agent ──────────────────
def test_authority_gate_raises_for_non_admitted_agent():
    session, delegation, _, _ = _wire(agent_ids=("code", "reviewer"))
    with pytest.raises(PermissionError):
        _run(session, delegation, compose=_compose("code"),    # reviewer NOT composed
             decisions=[
                 _decision("continue", next_agent_calls=[{"agent_id": "reviewer", "objective": "x"}]),
             ])


# ── 6. trust-O does not leak to a human-issued command ───────────────────────
def test_human_issued_command_does_not_grow_roster(tmp_path):
    from control.commands import IssuedBy, RuntimeCommand
    session, delegation, topics, _ = _wire(agent_ids=("code", "reviewer"))
    store = SqliteTaskLoopStore("run-human", path=tmp_path / "human.sqlite")

    human_cmd = RuntimeCommand(
        command_type="AddAgentToLoop",
        session_id=session.identity.session_id,
        issued_by=IssuedBy(type="human", user_id="u1"),
        idempotency_key="AddAgentToLoop:reviewer",
        payload={"agent_id": "reviewer"},
    )
    state = TaskLoopState(
        session_id=session.identity.session_id,
        task_id=session.identity.task_id,
        status=TaskLoopStatus.IN_DISCUSSION.value,
        selected_agents=["code"],
        round_no=1,
        max_rounds=5,
    )
    state.acceptance_checks = [AcceptanceCheck(id="ac1", text="c")]
    state.artifacts = {"session_plan-0000": {"kind": "session_plan"}}
    state.pending_commands = [human_cmd.as_dict()]
    store.save(state)

    result = resume_task_loop(
        session,
        checkpoint_store=store,
        delegation_service=delegation,
        orchestrator=ScriptedOrchestrator(
            compose="",
            decisions=[
                _decision("continue", next_agent_calls=[{"agent_id": "code", "objective": "x"}]),
                _decision("blocked", reason="done"),
            ],
        ),
        broker=DeterministicBroker(),
        agent_registry=make_registry(),
    )
    assert "reviewer" not in result["selected_agents"]
    assert "command.rejected" in topics
