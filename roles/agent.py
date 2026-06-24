"""Agent — a role bound to its skills/lenses, enforcing its allowlist. Epic E09.

The Agent is framework-neutral: it resolves the role's tool allowlist once, builds
a scoped prompt (system + lenses + allowed tools + skill contracts), and exposes
two guards the loop calls — ``guard_tool_call`` (allowlist enforcement → blocker/
handoff) and ``guard_finish`` (separation of duties → forced handoff). Graph wiring
is E10's job, not this module's.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from roles.spec import RoleSpec

if TYPE_CHECKING:
    from roles.lenses import LensRegistry
    from skills import SkillRegistry


class Agent:
    def __init__(
        self,
        spec: RoleSpec,
        *,
        skills: "SkillRegistry",
        lenses: "LensRegistry",
        core_tools: frozenset[str] = frozenset(),
    ) -> None:
        self.spec = spec
        self._skills = skills
        self._lenses = lenses
        self.core_tools = frozenset(core_tools)
        self.allowed_tools = spec.allowed_tools(skills, self.core_tools)

    # ── enforcement ──────────────────────────────────────────────────────────
    def is_tool_allowed(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools

    def guard_tool_call(self, tool_name: str) -> dict | None:
        """Return a blocker/handoff envelope if the call is out of scope, else None."""
        if self.is_tool_allowed(tool_name):
            return None
        return {
            "finish_reason": "blocker",
            "blocked_tool": tool_name,
            "reason": f"Tool '{tool_name}' is outside role '{self.spec.name}' allowlist.",
            "may_route_to": list(self.spec.may_route_to),
        }

    def guard_finish(self, *, claim_validated: bool) -> dict | None:
        """Enforce separation of duties: a role that does not own validation cannot
        finalize its own work as validated; it is forced to hand off (S09.4)."""
        ownership = self.spec.test_ownership
        if claim_validated and not ownership.owns_validation:
            return {
                "finish_reason": "blocker",
                "reason": (
                    f"Role '{self.spec.name}' does not own validation; "
                    f"must hand off to '{ownership.must_handoff_to}'."
                ),
                "handoff_to": ownership.must_handoff_to,
            }
        return None

    # ── prompt (scoped) ───────────────────────────────────────────────────────
    def build_prompt(self) -> str:
        blocks: list[str] = [self.spec.system_prompt]

        for lens_name in self.spec.lenses:
            blocks.append(self._lenses.render(lens_name))

        tools = sorted(self.allowed_tools)
        tool_lines = "\n".join(f"- {t}" for t in tools) if tools else "- (none)"
        blocks.append("## Allowed tools\n" + tool_lines)

        for skill_name in self.spec.allowed_skills:
            blocks.append(self._skills.render(skill_name, mode="contract"))

        return "\n\n".join(b.strip() for b in blocks if b.strip()) + "\n"
