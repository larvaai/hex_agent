"""Permission — the human-editable, per-agent capability profile. Epic E21 (S21.6).

A structured permission with an ``effective_from`` boundary. The Permission contract is
storage-agnostic here; B5 persists it append-only and the PolicyGate/DelegationPolicy read
the latest at a turn/checkpoint boundary. ``patched`` produces the next version from a
partial patch (used by ``UpdateAgentPermission``) without mutating the current one.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from control.errors import ControlContractError

# When a permission change takes effect. Default avoids changing scope mid-turn (S21.12).
EFFECTIVE_FROM = frozenset({"immediately", "next_turn", "next_checkpoint"})


@dataclass(frozen=True)
class Permission:
    allowed_tools: tuple[str, ...] = ()
    can_write_artifacts: bool = False
    can_call_other_agents: bool = False
    can_execute_shell: bool = False
    can_modify_workflow: bool = False
    can_modify_permissions: bool = False
    effective_from: str = "next_checkpoint"

    def __post_init__(self) -> None:
        if self.effective_from not in EFFECTIVE_FROM:
            raise ControlContractError(
                f"Permission.effective_from must be one of {sorted(EFFECTIVE_FROM)}, got {self.effective_from!r}."
            )

    def allows_tool(self, tool: str) -> bool:
        return tool in self.allowed_tools

    def patched(self, patch: dict[str, Any], *, effective_from: str | None = None) -> "Permission":
        """Return a new Permission with ``patch`` applied. Unknown keys are rejected so a
        typo cannot silently grant nothing/something."""
        if not isinstance(patch, dict):
            raise ControlContractError("Permission patch must be a mapping.")
        changes: dict[str, Any] = {}
        for key, value in patch.items():
            if key not in _FIELDS:
                raise ControlContractError(f"Unknown permission field in patch: {key!r}.")
            changes[key] = tuple(str(t) for t in value) if key == "allowed_tools" else bool(value)
        if effective_from is not None:
            changes["effective_from"] = effective_from
        return replace(self, **changes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed_tools": list(self.allowed_tools),
            "can_write_artifacts": self.can_write_artifacts,
            "can_call_other_agents": self.can_call_other_agents,
            "can_execute_shell": self.can_execute_shell,
            "can_modify_workflow": self.can_modify_workflow,
            "can_modify_permissions": self.can_modify_permissions,
            "effective_from": self.effective_from,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Permission":
        return cls(
            allowed_tools=tuple(str(t) for t in (d.get("allowed_tools") or ())),
            can_write_artifacts=bool(d.get("can_write_artifacts", False)),
            can_call_other_agents=bool(d.get("can_call_other_agents", False)),
            can_execute_shell=bool(d.get("can_execute_shell", False)),
            can_modify_workflow=bool(d.get("can_modify_workflow", False)),
            can_modify_permissions=bool(d.get("can_modify_permissions", False)),
            effective_from=str(d.get("effective_from", "next_checkpoint")),
        )


# Field names a patch may touch (excludes nothing structural; effective_from set separately).
_FIELDS = frozenset(
    {
        "allowed_tools",
        "can_write_artifacts",
        "can_call_other_agents",
        "can_execute_shell",
        "can_modify_workflow",
        "can_modify_permissions",
    }
)
