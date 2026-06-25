"""SkillRegistry — load skills and render them with progressive disclosure. Epic E07.

``render(name, mode="contract")`` injects only description + Allowed + Forbidden
(the operating contract). ``mode="full"`` additionally includes Steps + Report,
used once a skill is selected for the active step. ``union_tools`` exposes the
declared-tool union that the E09 role allowlist derivation consumes — the
registry never references roles itself.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from skills.spec import SkillSpec, parse_skill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillSpec] = {}

    # ── loading ────────────────────────────────────────────────────────────
    def register(self, spec: SkillSpec) -> SkillSpec:
        if spec.name in self._skills:
            raise ValueError(f"Skill '{spec.name}' is already registered; names must be unique.")
        self._skills[spec.name] = spec
        return spec

    def load_text(self, text: str) -> SkillSpec:
        return self.register(parse_skill(text))

    def load_file(self, path: str | Path) -> SkillSpec:
        return self.load_text(Path(path).read_text(encoding="utf-8"))

    def load_dir(self, path: str | Path, *, pattern: str = "*.md") -> tuple[SkillSpec, ...]:
        """Load every matching skill file under ``path`` (recursively)."""
        loaded = [self.load_file(p) for p in sorted(Path(path).rglob(pattern))]
        return tuple(loaded)

    # ── access ─────────────────────────────────────────────────────────────
    def get(self, name: str) -> SkillSpec:
        try:
            return self._skills[name]
        except KeyError:
            known = ", ".join(self.names()) or "(none)"
            raise KeyError(f"Unknown skill '{name}'. Known skills: {known}") from None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._skills))

    def __contains__(self, name: object) -> bool:
        return name in self._skills

    def __len__(self) -> int:
        return len(self._skills)

    # ── rendering (progressive disclosure) ──────────────────────────────────
    def render(self, name: str, *, mode: str = "contract") -> str:
        if mode not in {"contract", "full"}:
            raise ValueError(f"mode must be 'contract' or 'full', got {mode!r}.")
        spec = self.get(name)
        parts = [
            f"## {spec.name}",
            spec.description,
            "",
            "### Allowed (tools)",
            _render_bullets(spec.allowed_tools),
            "",
            "### Forbidden (tools)",
            _render_bullets(spec.forbidden_tools),
        ]
        if mode == "full":
            if spec.steps_md:
                parts += ["", "### Steps", spec.steps_md]
            if spec.report_md:
                parts += ["", "### Report", spec.report_md]
        return "\n".join(parts).strip() + "\n"

    # ── allowlist support for E09 (declared-tool union only) ────────────────
    def union_tools(self, names: Iterable[str]) -> frozenset[str]:
        """Union of allowed_tools across the named skills.

        This is the *skill-side* contribution the E09 role derivation consumes;
        combining with core tools and applying forbidden-wins lives in
        ``RoleSpec.allowed_tools`` (E09), not here.
        """
        union: set[str] = set()
        for name in names:
            union |= set(self.get(name).allowed_tools)
        return frozenset(union)

    def lint(self, has_tool: Callable[[str], bool]) -> dict[str, tuple[str, ...]]:
        """Return {skill_name: unknown_tools} for tools not present per ``has_tool``."""
        report: dict[str, tuple[str, ...]] = {}
        for name, spec in self._skills.items():
            declared = set(spec.allowed_tools) | set(spec.forbidden_tools)
            unknown = tuple(sorted(t for t in declared if not has_tool(t)))
            if unknown:
                report[name] = unknown
        return report


def _render_bullets(tools: tuple[str, ...]) -> str:
    if not tools:
        return "- (none)"
    return "\n".join(f"- {t}" for t in tools)
