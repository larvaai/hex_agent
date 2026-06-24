"""E09 Roles & Lenses — acceptance tests (offline, deterministic).

AC map (docs/rebuild_from_zero/E09_roles_lenses/acceptance.md):
  S09.1 build from config      -> test_build_agent_from_config
  S09.2 allowlist enforcement  -> test_out_of_scope_tool_blocked
  S09.3 config validation      -> test_missing_system_prompt_raises / test_missing_name_raises
  S09.4 separation of duties   -> test_non_owner_cannot_self_validate / test_owner_can_validate
  S09.5 scoped prompt          -> test_zero_tool_role_prompt_has_no_catalog
  S09.6 single source          -> test_single_and_multi_share_role_definition
"""
from __future__ import annotations

from pathlib import Path

import pytest

import roles as roles_pkg
import skills as skills_pkg
from roles import AgentRegistry, parse_role
from roles.lenses import LensRegistry
from skills import SkillRegistry

LIBRARY = Path(roles_pkg.__file__).parent / "library"
LENSES = LIBRARY / "lenses"
SKILLS_LIBRARY = Path(skills_pkg.__file__).parent / "library"


def make_registry(*, core_tools=frozenset()) -> AgentRegistry:
    skills = SkillRegistry()
    skills.load_dir(SKILLS_LIBRARY)
    lenses = LensRegistry()
    lenses.load_dir(LENSES)
    reg = AgentRegistry(skills=skills, lenses=lenses, core_tools=core_tools)
    reg.load_dir(LIBRARY)
    return reg


# ── S09.1 build from config ──────────────────────────────────────────────────
def test_build_agent_from_config():
    agent = make_registry().build_agent("code")
    # explicit fs_* + file_edit skill (adds fs_*, forbids terminal_run)
    assert agent.allowed_tools == {"fs_read", "fs_write", "fs_list"}
    assert agent.spec.lenses == ("correctness",)
    assert agent.spec.may_route_to == ("test", "reviewer")


def test_skill_forbidden_tool_wins_over_explicit():
    # a role that explicitly lists terminal_run but uses file_edit (forbids it)
    spec = parse_role(
        {
            "name": "r",
            "role": "x",
            "department": "d",
            "system_prompt": "p",
            "allowed_tools": ["terminal_run", "fs_read"],
            "allowed_skills": ["file_edit"],
        }
    )
    skills = SkillRegistry()
    skills.load_dir(SKILLS_LIBRARY)
    resolved = spec.allowed_tools(skills)
    assert "terminal_run" not in resolved  # forbidden wins
    assert {"fs_read", "fs_write", "fs_list"} <= resolved


# ── S09.2 allowlist enforcement ──────────────────────────────────────────────
def test_out_of_scope_tool_blocked():
    agent = make_registry().build_agent("code")
    assert agent.is_tool_allowed("git.git_commit") is False
    blocker = agent.guard_tool_call("git.git_commit")
    assert blocker is not None
    assert blocker["finish_reason"] == "blocker"
    assert blocker["blocked_tool"] == "git.git_commit"


def test_in_scope_tool_passes():
    agent = make_registry().build_agent("code")
    assert agent.guard_tool_call("fs_read") is None


# ── S09.3 config validation ──────────────────────────────────────────────────
def test_missing_system_prompt_raises():
    with pytest.raises(ValueError, match="system_prompt"):
        parse_role({"name": "x", "role": "r", "department": "d"}, source="x.yaml")


def test_missing_name_raises():
    with pytest.raises(ValueError, match="name"):
        parse_role({"role": "r", "department": "d", "system_prompt": "p"}, source="bad.yaml")


def test_error_names_the_file():
    with pytest.raises(ValueError, match="bad.yaml"):
        parse_role({"role": "r", "department": "d", "system_prompt": "p"}, source="bad.yaml")


# ── S09.4 separation of duties ───────────────────────────────────────────────
def test_non_owner_cannot_self_validate():
    agent = make_registry().build_agent("code")  # owns_validation=false
    handoff = agent.guard_finish(claim_validated=True)
    assert handoff is not None
    assert handoff["finish_reason"] == "blocker"
    assert handoff["handoff_to"] == "test"


def test_non_owner_may_finish_without_validation_claim():
    agent = make_registry().build_agent("code")
    assert agent.guard_finish(claim_validated=False) is None


def test_owner_can_validate():
    agent = make_registry().build_agent("test")  # owns_validation=true
    assert agent.guard_finish(claim_validated=True) is None


# ── S09.5 scoped prompt ──────────────────────────────────────────────────────
def test_zero_tool_role_prompt_has_no_catalog():
    agent = make_registry().build_agent("business_analyst")
    assert agent.allowed_tools == frozenset()
    prompt = agent.build_prompt()
    assert "- (none)" in prompt  # empty allowlist rendered explicitly
    assert "fs_read" not in prompt and "terminal_run" not in prompt
    # only its own lens group
    assert "Lens: requirements" in prompt
    assert "Lens: correctness" not in prompt


def test_code_prompt_includes_lens_and_skill_contract():
    prompt = make_registry().build_agent("code").build_prompt()
    assert "Lens: correctness" in prompt
    assert "file_edit" in prompt           # skill contract injected
    assert "Steps" not in prompt            # contract mode withholds skill Steps


# ── S09.6 single source ──────────────────────────────────────────────────────
def test_single_and_multi_share_role_definition():
    reg = make_registry()
    # "single-agent" path
    agent_scope = reg.build_agent("code").allowed_tools
    # "multi-agent" path (E10 projection)
    view = next(v for v in reg.list_roles() if v.agent_id == "code")
    assert view.default_scope == agent_scope          # one definition, two paths
    assert view.agent_id == "code"
    assert view.system_prompt == reg.get("code").system_prompt


def test_unknown_role_raises():
    with pytest.raises(KeyError, match="Unknown role"):
        make_registry().get("nope")
