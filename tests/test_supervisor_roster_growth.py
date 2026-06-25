"""Phase 4 — roster growth + department targeting wired live into the loop. Epic E21.

These drive the real ``run_task_loop`` with a scripted O and a real AgentRegistry
(the shipped role library: engineering = code/reviewer/test, product =
business_analyst). They prove the end-to-end behavior the earlier phases only
unit-tested: O-issued AddAgentToLoop grows the roster at the checkpoint, a
department target expands to its members, an admit-only round still counts as
progress, and the repeat-guard does not falsely BLOCK a department waiting on a
member.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import roles as roles_pkg
import skills as skills_pkg
from adapters.agents import ScriptedDelegationAgent
from core.bootstrap import build_kernel
from core.session import SessionFactory
from delegation import DelegationManager, DelegationRegistry, InMemoryDelegationStore
from roles import AgentRegistry
from roles.lenses import LensRegistry
from skills import SkillRegistry
from supervisor import DeterministicBroker, run_task_loop
from supervisor.graph import SupervisorContext, _state_view
from supervisor.orchestrator import ScriptedOrchestrator
from supervisor.state import TaskLoopState
from tests.conftest import KERNEL_CONFIG, compose_json, decision_json

LIBRARY = Path(roles_pkg.__file__).parent / "library"
LENSES = LIBRARY / "lenses"
SKILLS_LIBRARY = Path(skills_pkg.__file__).parent / "library"
AC = [("ac1", "the criterion")]


def make_registry() -> AgentRegistry:
    skills = SkillRegistry()
    skills.load_dir(SKILLS_LIBRARY)
    lenses = LensRegistry()
    lenses.load_dir(LENSES)
    reg = AgentRegistry(skills=skills, lenses=lenses)
    reg.load_dir(LIBRARY)
    return reg


def build_loop(*, compose: str, decisions: list[str], agent_ids: tuple[str, ...]):
    """Wire a real registry + scripted workers and return a runner + event log."""
    kernel = build_kernel(KERNEL_CONFIG)
    factory = SessionFactory(kernel=kernel)
    supervisor_session = factory.create_root("multi-agent task")

    topics: list[str] = []
    kernel.events.subscribe(lambda t, p: topics.append(t))

    registry = DelegationRegistry()
    for agent_id in agent_ids:
        registry.register(ScriptedDelegationAgent(agent_id, artifacts=[{"kind": "finding", "agent": agent_id}]))
    delegation_service = DelegationManager(
        registry=registry, sessions=factory, store=InMemoryDelegationStore()
    )

    def run(**kw):
        return run_task_loop(
            supervisor_session,
            "ship a change",
            acceptance_criteria=AC,
            delegation_service=delegation_service,
            orchestrator=ScriptedOrchestrator(compose=compose, decisions=list(decisions)),
            broker=DeterministicBroker(),
            agent_registry=make_registry(),
            **kw,
        )

    return run, topics


def _agent_ids_in_turns(result: dict[str, Any]) -> list[str]:
    return [t["agent_id"] for t in result["state"]["turns"]]


def _add(agent_id: str) -> dict:
    return {"command_type": "AddAgentToLoop", "payload": {"agent_id": agent_id}}


# ── AddAgentToLoop grows the roster, target passes authority next round ───────
def test_add_agent_to_loop_grows_roster_then_runs():
    decisions = [
        decision_json("continue", next_agent_calls=[{"agent_id": "code", "objective": "x"}],
                      commands=[_add("reviewer")]),
        decision_json("continue", next_agent_calls=[{"agent_id": "reviewer", "objective": "review"}]),
        decision_json("blocked", reason="done"),
    ]
    run, _ = build_loop(compose=compose_json(("code", "r")), decisions=decisions,
                        agent_ids=("code", "reviewer"))
    result = run()
    assert "reviewer" in result["selected_agents"]      # admitted at round-0 checkpoint
    assert "reviewer" in _agent_ids_in_turns(result)    # ran once it was in the roster


def test_add_agent_outside_catalog_is_rejected():
    decisions = [
        decision_json("continue", next_agent_calls=[{"agent_id": "code", "objective": "x"}],
                      commands=[_add("ghost")]),
        decision_json("blocked", reason="done"),
    ]
    run, topics = build_loop(compose=compose_json(("code", "r")), decisions=decisions,
                             agent_ids=("code",))
    result = run()
    assert "ghost" not in result["selected_agents"]
    assert "command.rejected" in topics


# ── department targeting ─────────────────────────────────────────────────────
def test_department_member_already_selected_runs_this_round():
    # Compose code + reviewer; target the engineering department. Both run now;
    # 'test' (also engineering, not composed) is deferred to admit.
    decisions = [
        decision_json("continue", next_agent_calls=[
            {"agent_id": "engineering", "objective": "do eng work", "target_kind": "department"}]),
        decision_json("blocked", reason="done"),
    ]
    run, _ = build_loop(compose=compose_json(("code", "r"), ("reviewer", "r")), decisions=decisions,
                        agent_ids=("code", "reviewer", "test"))
    result = run()
    ran = _agent_ids_in_turns(result)
    assert "code" in ran and "reviewer" in ran          # selected members ran this round
    assert "test" in result["selected_agents"]          # the missing member was admitted


def test_department_all_unselected_admits_then_runs_without_false_block():
    # No engineering member composed; round 0 admits them all (0 turns, applied>0),
    # so the loop must NOT BLOCK for "no progress". Round 1 runs one of them.
    decisions = [
        decision_json("continue", next_agent_calls=[
            {"agent_id": "engineering", "objective": "eng", "target_kind": "department"}]),
        decision_json("continue", next_agent_calls=[{"agent_id": "code", "objective": "do it"}]),
        decision_json("blocked", reason="done"),
    ]
    run, _ = build_loop(compose=compose_json(("business_analyst", "pm")), decisions=decisions,
                        agent_ids=("business_analyst", "code", "reviewer", "test"))
    result = run(max_rounds=6)
    # round 0 admitted the whole department, round 1 actually ran 'code'
    for member in ("code", "reviewer", "test"):
        assert member in result["selected_agents"]
    assert "code" in _agent_ids_in_turns(result)
    assert result["reason"] != "no progress this round"


def test_department_member_delegated_at_most_once_per_round():
    # Invariant (AC3, plan "one delegate() per member"): even if a member is named
    # twice in one decision — here the same department targeted twice — it must run
    # exactly once this round, not once per mention. Mirrors compose_team's
    # uniqueness rule. (Regression guard for the static done_this_round snapshot.)
    dept = {"agent_id": "engineering", "objective": "eng", "target_kind": "department"}
    decisions = [
        decision_json("continue", next_agent_calls=[dept, dept]),
        decision_json("blocked", reason="done"),
    ]
    run, _ = build_loop(compose=compose_json(("code", "r"), ("reviewer", "r"), ("test", "r")),
                        decisions=decisions, agent_ids=("code", "reviewer", "test"))
    result = run()
    ran = _agent_ids_in_turns(result)
    for member in ("code", "reviewer", "test"):
        assert ran.count(member) == 1, f"{member} delegated {ran.count(member)}x in one round"


def test_admitting_different_members_does_not_trigger_repeat_block():
    # Same shape of decision two rounds running, but each admits a DIFFERENT member.
    # With an aggressive repeat budget this must NOT terminate as a repeat.
    decisions = [
        decision_json("continue", next_agent_calls=[{"agent_id": "code", "objective": "x"}],
                      commands=[_add("reviewer")]),
        decision_json("continue", next_agent_calls=[{"agent_id": "code", "objective": "x"}],
                      commands=[_add("test")]),
        decision_json("blocked", reason="done"),
    ]
    run, _ = build_loop(compose=compose_json(("code", "r")), decisions=decisions,
                        agent_ids=("code", "reviewer", "test"))
    result = run(max_decision_repeats=1)
    assert result["reason"] != "orchestrator repeated the same decision"
    assert "reviewer" in result["selected_agents"]
    assert "test" in result["selected_agents"]


# ── exposure to O: slim state-view + role catalog ────────────────────────────
def test_state_view_pending_commands_is_slim():
    # pending_commands surfaced to O carry only {command_type, agent_id} — never the
    # random command_id/created_at, which would just be prompt noise.
    state = TaskLoopState(session_id="s", task_id="t")
    state.pending_commands = [{
        "command_type": "AddAgentToLoop",
        "payload": {"agent_id": "reviewer"},
        "command_id": "deadbeef",
        "created_at": "2026-01-01T00:00:00+00:00",
        "idempotency_key": "AddAgentToLoop:reviewer",
    }]
    ctx = SupervisorContext(
        supervisor_session=None, delegation_service=None, orchestrator=None,
        broker=None, agent_registry=make_registry(),
    )
    view = _state_view(state, ctx)
    assert view["pending_commands"] == [{"command_type": "AddAgentToLoop", "agent_id": "reviewer"}]
    assert "engineering" in view["departments"]


def test_role_catalog_includes_department():
    ctx = SupervisorContext(
        supervisor_session=None, delegation_service=None, orchestrator=None,
        broker=None, agent_registry=make_registry(),
    )
    rows = {r["agent_id"]: r for r in ctx.role_catalog()}
    assert rows["code"]["department"] == "engineering"
    assert rows["business_analyst"]["department"] == "product"
