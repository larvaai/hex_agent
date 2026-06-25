"""Command-type registry — declares when each command applies and what it needs. Epic E21 (S21.4).

Loaded from ``config/runtime_command_types.yaml``. Each command type declares ``apply_at``
(``next_checkpoint`` | ``immediate_if_waiting`` | ``immediate``) and ``requires_permission``
(a permission name or null). An unknown command type is rejected at the gateway.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from control.errors import ControlContractError

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "runtime_command_types.yaml"

APPLY_AT = frozenset({"next_checkpoint", "immediate_if_waiting", "immediate"})


@dataclass(frozen=True)
class CommandTypeSpec:
    command_type: str
    apply_at: str
    requires_permission: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "command_type": self.command_type,
            "apply_at": self.apply_at,
            "requires_permission": self.requires_permission,
        }


class CommandTypeRegistry:
    def __init__(self, specs: dict[str, CommandTypeSpec]) -> None:
        self._specs = dict(specs)

    def __contains__(self, command_type: str) -> bool:
        return command_type in self._specs

    def assert_known(self, command_type: str) -> None:
        if command_type not in self._specs:
            raise ControlContractError(
                f"Unknown command_type: {command_type!r}. Declare it in runtime_command_types.yaml."
            )

    def get(self, command_type: str) -> CommandTypeSpec:
        self.assert_known(command_type)
        return self._specs[command_type]

    def apply_at(self, command_type: str) -> str:
        return self.get(command_type).apply_at

    def requires_permission(self, command_type: str) -> str | None:
        return self.get(command_type).requires_permission

    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))


def parse_command_registry(data: dict[str, Any], *, source: str = "<command-registry>") -> CommandTypeRegistry:
    if not isinstance(data, dict):
        raise ControlContractError(f"Command registry '{source}' must be a YAML mapping.")
    rows = data.get("command_types")
    if not isinstance(rows, dict) or not rows:
        raise ControlContractError(f"Command registry '{source}' must have a non-empty 'command_types' mapping.")
    specs: dict[str, CommandTypeSpec] = {}
    for name, raw in rows.items():
        command_type = str(name).strip()
        if not command_type:
            raise ControlContractError(f"Command registry '{source}': empty command_type name.")
        raw = raw or {}
        if not isinstance(raw, dict):
            raise ControlContractError(f"Command registry '{source}': '{command_type}' must be a mapping.")
        apply_at = str(raw.get("apply_at", "next_checkpoint"))
        if apply_at not in APPLY_AT:
            raise ControlContractError(
                f"Command registry '{source}': '{command_type}' apply_at {apply_at!r} "
                f"must be one of {sorted(APPLY_AT)}."
            )
        requires = raw.get("requires_permission")
        specs[command_type] = CommandTypeSpec(
            command_type=command_type,
            apply_at=apply_at,
            requires_permission=(str(requires) if requires else None),
        )
    return CommandTypeRegistry(specs)


def load_command_registry(path: str | Path | None = None) -> CommandTypeRegistry:
    path = Path(path) if path is not None else _DEFAULT_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return parse_command_registry(data, source=path.name)
