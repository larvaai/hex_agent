"""Phase 3 — department targeting: registry lookup + pure expansion helper. Epic E21.

Two pieces under test, both pure:
- AgentRegistry.members_of / .departments — group roles by RoleSpec.department.
- expand_departments — turn a department-targeted call into one agent-level call
  per member, deferring not-yet-composed members to an admit list. No emit, no
  state mutation; the caller (Phase 4) wires the side effects.
"""
from __future__ import annotations

from pathlib import Path

import roles as roles_pkg
import skills as skills_pkg
from roles import AgentRegistry
from roles.lenses import LensRegistry
from skills import SkillRegistry
from supervisor.contracts import AgentAssignment, OrchestratorDecision
from supervisor.graph import expand_departments

LIBRARY = Path(roles_pkg.__file__).parent / "library"
LENSES = LIBRARY / "lenses"
SKILLS_LIBRARY = Path(skills_pkg.__file__).parent / "library"


def make_registry() -> AgentRegistry:
    skills = SkillRegistry()
    skills.load_dir(SKILLS_LIBRARY)
    lenses = LensRegistry()
    lenses.load_dir(LENSES)
    reg = AgentRegistry(skills=skills, lenses=lenses)
    reg.load_dir(LIBRARY)
    return reg


# ── AgentRegistry.members_of / departments ───────────────────────────────────
def test_members_of_returns_sorted_department_roles():
    reg = make_registry()
    # engineering holds code/reviewer/test in the shipped role library.
    assert reg.members_of("engineering") == ("code", "reviewer", "test")


def test_members_of_unknown_department_is_empty():
    assert make_registry().members_of("nonexistent") == ()


def test_departments_groups_every_role():
    depts = make_registry().departments()
    assert depts["engineering"] == ("code", "reviewer", "test")
    assert depts["product"] == ("business_analyst",)


# ── expand_departments (pure) ────────────────────────────────────────────────
def _dept_call(dept="engineering", scope=("fs_read",)) -> AgentAssignment:
    return AgentAssignment(
        agent_id=dept,
        objective="ship it",
        scope_of_work="the slice",
        allowed_capabilities=tuple(scope),
        target_kind="department",
    )


def _decision(*calls: AgentAssignment) -> OrchestratorDecision:
    return OrchestratorDecision(decision="continue", next_agent_calls=tuple(calls))


def _members_of(mapping):
    return lambda dept: tuple(mapping.get(dept, ()))


def test_expand_all_members_selected():
    members = _members_of({"engineering": ("code", "reviewer")})
    expanded, to_admit, rejected = expand_departments(
        _decision(_dept_call()), members_of=members, selected={"code", "reviewer"}
    )
    assert [a.agent_id for a in expanded] == ["code", "reviewer"]
    assert all(a.target_kind == "agent" for a in expanded)
    assert to_admit == []
    assert rejected == []


def test_expand_defers_uncomposed_member_to_admit():
    members = _members_of({"engineering": ("code", "reviewer")})
    expanded, to_admit, rejected = expand_departments(
        _decision(_dept_call()), members_of=members, selected={"code"}
    )
    # Only the already-selected member runs this round; the other is queued to admit.
    assert [a.agent_id for a in expanded] == ["code"]
    assert to_admit == ["reviewer"]
    assert rejected == []


def test_agent_target_kind_is_passed_through():
    agent_call = AgentAssignment(agent_id="code", objective="work", target_kind="agent")
    members = _members_of({})
    expanded, to_admit, rejected = expand_departments(
        _decision(agent_call), members_of=members, selected={"code"}
    )
    assert expanded == [agent_call]          # untouched
    assert to_admit == [] and rejected == []


def test_empty_or_unknown_department_is_rejected_not_raised():
    members = _members_of({})                # every lookup returns ()
    expanded, to_admit, rejected = expand_departments(
        _decision(_dept_call(dept="ghosts")), members_of=members, selected=set()
    )
    assert expanded == [] and to_admit == []
    assert len(rejected) == 1
    dept, reason = rejected[0]
    assert dept == "ghosts"
    # message must steer O toward target_kind='agent' when it meant a single agent
    assert "target_kind='agent'" in reason


def test_member_scope_does_not_widen():
    members = _members_of({"engineering": ("code",)})
    expanded, _, _ = expand_departments(
        _decision(_dept_call(scope=("fs_read",))), members_of=members, selected={"code"}
    )
    # member carries the department call's exact scope — no tool added.
    assert expanded[0].allowed_capabilities == ("fs_read",)
