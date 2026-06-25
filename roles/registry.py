"""AgentRegistry — one role store shared by single- and multi-agent paths. Epic E09.

Holds the canonical ``RoleSpec`` definitions plus the skill/lens registries and the
core tool set. ``build_agent`` is what E05 (single) and E10 (multi) both call, so a
role has exactly one definition (S09.6). ``list_roles`` returns the slim
``RoleView`` projection E10's orchestrator consumes.
"""
from __future__ import annotations

from pathlib import Path

from roles.agent import Agent
from roles.lenses import LensRegistry
from roles.spec import RoleSpec, RoleView, load_role_file
from skills import SkillRegistry


class AgentRegistry:
    def __init__(
        self,
        *,
        skills: SkillRegistry,
        lenses: LensRegistry,
        core_tools: frozenset[str] = frozenset(),
    ) -> None:
        self._skills = skills
        self._lenses = lenses
        self._core_tools = frozenset(core_tools)
        self._roles: dict[str, RoleSpec] = {}

    # ── loading ────────────────────────────────────────────────────────────
    def register(self, spec: RoleSpec) -> RoleSpec:
        if spec.name in self._roles:
            raise ValueError(f"Role '{spec.name}' is already registered; names must be unique.")
        self._roles[spec.name] = spec
        return spec

    def load_file(self, path: str | Path) -> RoleSpec:
        return self.register(load_role_file(path))

    def load_dir(self, path: str | Path, *, pattern: str = "*.yaml") -> tuple[RoleSpec, ...]:
        """Load role yamls directly under ``path`` (non-recursive; lenses live deeper)."""
        return tuple(self.load_file(p) for p in sorted(Path(path).glob(pattern)))

    # ── access ─────────────────────────────────────────────────────────────
    def get(self, name: str) -> RoleSpec:
        try:
            return self._roles[name]
        except KeyError:
            known = ", ".join(self.names()) or "(none)"
            raise KeyError(f"Unknown role '{name}'. Known roles: {known}") from None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._roles))

    def __contains__(self, name: object) -> bool:
        return name in self._roles

    # ── department grouping (E21: department-targeted delegation) ─────────────
    def members_of(self, department: str) -> tuple[str, ...]:
        """Role names whose ``RoleSpec.department`` matches, sorted for determinism.

        An unknown/empty department returns () — the caller treats that as a soft
        rejection rather than an error (a department name might be a typo, or O
        meant to target a single agent)."""
        return tuple(sorted(n for n, spec in self._roles.items() if spec.department == department))

    def departments(self) -> dict[str, tuple[str, ...]]:
        """Every department mapped to its sorted member role names."""
        groups: dict[str, list[str]] = {}
        for name, spec in self._roles.items():
            groups.setdefault(spec.department, []).append(name)
        return {dept: tuple(sorted(members)) for dept, members in groups.items()}

    # ── build (shared by single & multi) ─────────────────────────────────────
    def build_agent(self, name: str) -> Agent:
        return Agent(
            self.get(name),
            skills=self._skills,
            lenses=self._lenses,
            core_tools=self._core_tools,
        )

    # ── E10 projection ───────────────────────────────────────────────────────
    def role_view(self, name: str) -> RoleView:
        spec = self.get(name)
        return RoleView(
            agent_id=spec.name,
            role=spec.role,
            system_prompt=spec.system_prompt,
            default_scope=spec.allowed_tools(self._skills, self._core_tools),
            department=spec.department,
        )

    def list_roles(self) -> tuple[RoleView, ...]:
        return tuple(self.role_view(name) for name in self.names())
