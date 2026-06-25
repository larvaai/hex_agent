"""Lenses — review viewpoints rendered into an agent's prompt. Epic E09.

A lens is a named viewpoint (e.g. "correctness", "security") with a purpose,
optional allowed/forbidden tools, and an output schema. An agent's prompt includes
only the lenses its role declares (S09.5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class LensSpec:
    name: str
    purpose: str
    allowed_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    output_schema: dict = field(default_factory=dict)

    def render(self) -> str:
        lines = [f"### Lens: {self.name}", self.purpose]
        if self.allowed_tools:
            lines.append("allowed: " + ", ".join(self.allowed_tools))
        if self.forbidden_tools:
            lines.append("forbidden: " + ", ".join(self.forbidden_tools))
        if self.output_schema:
            keys = ", ".join(sorted(self.output_schema))
            lines.append(f"output_schema: {{{keys}}}")
        return "\n".join(lines)


def _as_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    return tuple(str(v).strip() for v in value if str(v).strip())


def parse_lens(data: dict, *, source: str = "<lens>") -> LensSpec:
    if not isinstance(data, dict):
        raise ValueError(f"Lens '{source}' must be a YAML mapping.")
    name = str(data.get("name") or "").strip()
    purpose = str(data.get("purpose") or "").strip()
    if not name:
        raise ValueError(f"Lens '{source}' is missing required field 'name'.")
    if not purpose:
        raise ValueError(f"Lens '{name}' is missing required field 'purpose'.")
    output_schema = data.get("output_schema") or {}
    if not isinstance(output_schema, dict):
        raise ValueError(f"Lens '{name}' field 'output_schema' must be a mapping.")
    return LensSpec(
        name=name,
        purpose=purpose,
        allowed_tools=_as_tuple(data.get("allowed_tools")),
        forbidden_tools=_as_tuple(data.get("forbidden_tools")),
        output_schema=dict(output_schema),
    )


class LensRegistry:
    def __init__(self) -> None:
        self._lenses: dict[str, LensSpec] = {}

    def register(self, spec: LensSpec) -> LensSpec:
        if spec.name in self._lenses:
            raise ValueError(f"Lens '{spec.name}' is already registered; names must be unique.")
        self._lenses[spec.name] = spec
        return spec

    def load_file(self, path: str | Path) -> LensSpec:
        path = Path(path)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return self.register(parse_lens(data, source=path.name))

    def load_dir(self, path: str | Path, *, pattern: str = "*.yaml") -> tuple[LensSpec, ...]:
        return tuple(self.load_file(p) for p in sorted(Path(path).glob(pattern)))

    def get(self, name: str) -> LensSpec:
        try:
            return self._lenses[name]
        except KeyError:
            known = ", ".join(sorted(self._lenses)) or "(none)"
            raise KeyError(f"Unknown lens '{name}'. Known lenses: {known}") from None

    def render(self, name: str) -> str:
        return self.get(name).render()

    def __contains__(self, name: object) -> bool:
        return name in self._lenses
