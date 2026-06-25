"""RoleSpec (canonical) + RoleView (E10 projection) + role loader. Epic E09.

The role→allowlist derivation lives here (and only here), per the cycle-break: a
skill is role-agnostic and only declares tool names; the role unions its explicit
tools, its skills' declared tools, and the core tools, then subtracts skill-
forbidden tools (forbidden wins). See CYCLE_E07_E09_skill_role.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:  # avoid a hard import cycle; only needed for typing
    from skills import SkillRegistry

_REQUIRED = ("name", "role", "department", "system_prompt")


@dataclass(frozen=True)
class TestOwnership:
    """Separation-of-duties marker. A role that does not own validation must hand
    its work to ``must_handoff_to`` rather than self-certify."""

    owns_validation: bool = True
    must_handoff_to: str | None = None


@dataclass(frozen=True)
class RoleView:
    """The slim role projection E10's orchestrator reads (BUILD_PLAN §1a)."""

    agent_id: str
    role: str
    system_prompt: str
    default_scope: frozenset[str]


@dataclass(frozen=True)
class RoleSpec:
    name: str
    role: str
    department: str
    system_prompt: str
    explicit_tools: tuple[str, ...] = ()       # yaml: allowed_tools
    allowed_skills: tuple[str, ...] = ()
    may_route_to: tuple[str, ...] = ()          # yaml: route_permissions.may_route_to
    test_ownership: TestOwnership = field(default_factory=TestOwnership)
    lenses: tuple[str, ...] = ()

    def allowed_tools(
        self, skills: "SkillRegistry", core_tools: frozenset[str] = frozenset()
    ) -> frozenset[str]:
        """Derive the runtime tool allowlist. The single place skills + roles meet."""
        union: set[str] = set(self.explicit_tools) | set(core_tools)
        forbidden: set[str] = set()
        for skill_name in self.allowed_skills:
            sk = skills.get(skill_name)
            union |= set(sk.allowed_tools)
            forbidden |= set(sk.forbidden_tools)
        return frozenset(union - forbidden)  # forbidden wins


def _as_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    return tuple(str(v).strip() for v in value if str(v).strip())


def _sequence_tuple(value, field: str, source: str) -> tuple[str, ...]:
    """Like ``_as_tuple`` but rejects non-sequence containers (dict/int/…) with a
    source-labelled ValueError instead of silently iterating keys or raising TypeError."""
    if value is not None and not isinstance(value, (str, list, tuple)):
        raise ValueError(f"Role '{source}' field '{field}' must be a list of strings.")
    return _as_tuple(value)


def _mapping(value, field: str, source: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Role '{source}' field '{field}' must be a mapping.")
    return value


def parse_role(data: dict, *, source: str = "<role>") -> RoleSpec:
    """Parse role config into a RoleSpec. Raises ValueError naming file + field."""
    if not isinstance(data, dict):
        raise ValueError(f"Role '{source}' must be a YAML mapping.")
    for fieldname in _REQUIRED:
        value = data.get(fieldname)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError(f"Role '{source}' is missing required field '{fieldname}'.")

    route = _mapping(data.get("route_permissions"), "route_permissions", source)
    owns = _mapping(data.get("test_ownership"), "test_ownership", source)
    return RoleSpec(
        name=str(data["name"]).strip(),
        role=str(data["role"]).strip(),
        department=str(data["department"]).strip(),
        system_prompt=str(data["system_prompt"]).strip(),
        explicit_tools=_sequence_tuple(data.get("allowed_tools"), "allowed_tools", source),
        allowed_skills=_sequence_tuple(data.get("allowed_skills"), "allowed_skills", source),
        may_route_to=_sequence_tuple(route.get("may_route_to"), "route_permissions.may_route_to", source),
        test_ownership=TestOwnership(
            owns_validation=bool(owns.get("owns_validation", True)),
            must_handoff_to=(str(owns["must_handoff_to"]).strip() if owns.get("must_handoff_to") else None),
        ),
        lenses=_sequence_tuple(data.get("lenses"), "lenses", source),
    )


def load_role_file(path: str | Path) -> RoleSpec:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return parse_role(data, source=path.name)
