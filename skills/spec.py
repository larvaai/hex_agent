"""SkillSpec + SKILL.md parser. Epic E07.

A SKILL.md has YAML frontmatter (``name``, ``description``, optional ``triggers``)
followed by a markdown body with ``Allowed (tools)`` / ``Forbidden (tools)`` /
``Steps`` / ``Report`` sections. ``parse_skill`` is the single source of truth for
turning that text into an immutable :class:`SkillSpec`.

Design note (cycle-break): a SkillSpec is role-agnostic — it declares tools by
canonical name only and never references a role. The role→allowlist derivation
lives in E09, not here. See CYCLE_E07_E09_skill_role.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

# Headings are matched by substring (case-insensitive) so authors can write
# "## Allowed (tools)" or "## Allowed Tools" interchangeably.
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_PLACEHOLDERS = {"", "none", "(none)", "n/a", "-"}


@dataclass(frozen=True)
class SkillSpec:
    """An operating contract for one skill (immutable, role-agnostic)."""

    name: str
    description: str
    triggers: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    steps_md: str = ""
    report_md: str = ""


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Raise ValueError if no frontmatter block."""
    m = _FRONTMATTER_RE.match(text.lstrip("﻿"))
    if not m:
        raise ValueError("SKILL.md is missing a '---' YAML frontmatter block.")
    data = yaml.safe_load(m.group(1)) or {}
    if not isinstance(data, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping.")
    return data, m.group(2)


def _split_sections(body: str) -> dict[str, str]:
    """Split a markdown body into {lowercased-heading: text} by ## / ### headings."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in body.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1).strip().lower()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def _find_section(sections: dict[str, str], needle: str) -> str:
    for heading, text in sections.items():
        if needle in heading:
            return text
    return ""


def _bullets(text: str) -> tuple[str, ...]:
    """Extract tool names from a markdown bullet list, stripping markers/backticks."""
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s[:1] in {"-", "*", "+"}:
            item = s[1:].strip().strip("`").strip()
            if item.lower() not in _PLACEHOLDERS:
                out.append(item)
    return tuple(out)


def _triggers(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = re.split(r"[,\n]", value)
    else:
        parts = list(value)
    return tuple(str(p).strip() for p in parts if str(p).strip())


def parse_skill(text: str) -> SkillSpec:
    """Parse SKILL.md text into a SkillSpec. Raises ValueError on missing fields."""
    fm, body = _split_frontmatter(text)
    name = str(fm.get("name") or "").strip()
    description = str(fm.get("description") or "").strip()
    if not name:
        raise ValueError("SKILL.md frontmatter is missing required field 'name'.")
    if not description:
        raise ValueError(f"SKILL.md '{name}' is missing required field 'description'.")

    sections = _split_sections(body)
    return SkillSpec(
        name=name,
        description=description,
        triggers=_triggers(fm.get("triggers")),
        allowed_tools=_bullets(_find_section(sections, "allowed")),
        forbidden_tools=_bullets(_find_section(sections, "forbidden")),
        steps_md=_find_section(sections, "steps"),
        report_md=_find_section(sections, "report"),
    )
