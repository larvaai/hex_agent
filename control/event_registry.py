"""Event-type registry — the central catalog so modules can't invent event names. Epic E21 (S21.2).

Every ``event_type`` an emitter uses must be declared here (loaded from
``config/runtime_event_types.yaml``). Each declares ``visibility`` (who may see it),
``durable`` (persist for replay), ``redact_for_ui``, and ``checkpoint_candidate``. An
unknown type is rejected — the emitter calls ``assert_known`` before publishing.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from control.errors import ControlContractError
from control.events import VISIBILITY_LEVELS

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "runtime_event_types.yaml"


@dataclass(frozen=True)
class EventTypeSpec:
    event_type: str
    visibility: str
    durable: bool = True
    redact_for_ui: bool = False
    checkpoint_candidate: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "visibility": self.visibility,
            "durable": self.durable,
            "redact_for_ui": self.redact_for_ui,
            "checkpoint_candidate": self.checkpoint_candidate,
        }


class EventTypeRegistry:
    def __init__(self, specs: dict[str, EventTypeSpec]) -> None:
        self._specs = dict(specs)

    def __contains__(self, event_type: str) -> bool:
        return event_type in self._specs

    def assert_known(self, event_type: str) -> None:
        if event_type not in self._specs:
            raise ControlContractError(
                f"Unknown event_type: {event_type!r}. Declare it in runtime_event_types.yaml."
            )

    def get(self, event_type: str) -> EventTypeSpec:
        self.assert_known(event_type)
        return self._specs[event_type]

    def visibility(self, event_type: str) -> str:
        return self.get(event_type).visibility

    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))


def parse_event_registry(data: dict[str, Any], *, source: str = "<event-registry>") -> EventTypeRegistry:
    if not isinstance(data, dict):
        raise ControlContractError(f"Event registry '{source}' must be a YAML mapping.")
    rows = data.get("event_types")
    if not isinstance(rows, dict) or not rows:
        raise ControlContractError(f"Event registry '{source}' must have a non-empty 'event_types' mapping.")
    specs: dict[str, EventTypeSpec] = {}
    for name, raw in rows.items():
        event_type = str(name).strip()
        if not event_type or "." not in event_type:
            raise ControlContractError(
                f"Event registry '{source}': event_type {name!r} must be dotted (e.g. 'agent.before_run')."
            )
        raw = raw or {}
        if not isinstance(raw, dict):
            raise ControlContractError(f"Event registry '{source}': '{event_type}' must be a mapping.")
        visibility = str(raw.get("visibility", "ui_safe"))
        if visibility not in VISIBILITY_LEVELS:
            raise ControlContractError(
                f"Event registry '{source}': '{event_type}' visibility {visibility!r} "
                f"must be one of {sorted(VISIBILITY_LEVELS)}."
            )
        specs[event_type] = EventTypeSpec(
            event_type=event_type,
            visibility=visibility,
            durable=bool(raw.get("durable", True)),
            redact_for_ui=bool(raw.get("redact_for_ui", False)),
            checkpoint_candidate=bool(raw.get("checkpoint_candidate", False)),
        )
    return EventTypeRegistry(specs)


def load_event_registry(path: str | Path | None = None) -> EventTypeRegistry:
    path = Path(path) if path is not None else _DEFAULT_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return parse_event_registry(data, source=path.name)
