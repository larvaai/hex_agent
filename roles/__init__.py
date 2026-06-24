"""Roles & Lenses — one source of truth for an agent's identity. Epic E09.

A ``RoleSpec`` (loaded from ``roles/<role>.yaml``) is the canonical definition used
by BOTH the single-agent (E05) and multi-agent (E10) paths. It references skills by
name (E07) and derives its runtime tool allowlist via ``allowed_tools``. ``RoleView``
is the slimmed projection E10's orchestrator consumes (agent_id / role /
system_prompt / default_scope). See CYCLE_E07_E09_skill_role.md and
E10_multi_agent_graph/BUILD_PLAN.md §1a.
"""
from __future__ import annotations

from roles.agent import Agent
from roles.lenses import LensRegistry, LensSpec
from roles.registry import AgentRegistry
from roles.spec import RoleSpec, RoleView, TestOwnership, parse_role

__all__ = [
    "RoleSpec",
    "RoleView",
    "TestOwnership",
    "parse_role",
    "Agent",
    "AgentRegistry",
    "LensSpec",
    "LensRegistry",
]
