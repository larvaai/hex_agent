"""Skills system — operating contracts that declare canonical tools. Epic E07.

A skill is a role-agnostic contract (it never references a role). It declares the
canonical MCP/tool names it is *allowed* and *forbidden* to use, plus optional
Steps/Report bodies that are only surfaced when the skill is selected for the
active step (progressive disclosure). Roles (E09) consume the declared tools to
derive their allowlist; skills do not depend on roles. See
``docs/rebuild_from_zero/CYCLE_E07_E09_skill_role.md``.
"""
from __future__ import annotations

from skills.registry import SkillRegistry
from skills.spec import SkillSpec, parse_skill

__all__ = ["SkillSpec", "parse_skill", "SkillRegistry"]
