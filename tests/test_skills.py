"""E07 Skills — acceptance tests (offline, deterministic).

AC map (docs/rebuild_from_zero/E07_skills/acceptance.md):
  S07.1 declared tools / lint   -> test_lint_* , test_library_skills_lint_clean
  S07.2 contract mode           -> test_render_contract_excludes_steps_report
  S07.3 full mode               -> test_render_full_includes_steps_report
  S07.4 derive allowlist (union)-> test_union_tools_across_skills
  S07.5 frontmatter validation  -> test_missing_name_raises / test_missing_description_raises
"""
from __future__ import annotations

from pathlib import Path

import pytest

import skills as skills_pkg
from skills import SkillRegistry, parse_skill

LIBRARY = Path(skills_pkg.__file__).parent / "library"

CANONICAL_TOOLS = {"fs_read", "fs_write", "fs_list", "terminal_run"}

SKILL_TEXT = """---
name: demo
description: A demo skill.
triggers: [alpha, beta]
---

## Allowed (tools)
- fs_read
- `fs_list`

## Forbidden (tools)
- fs_write

## Steps
1. Do the thing.

## Report
- summary: done.
"""


def test_parse_extracts_contract_fields():
    spec = parse_skill(SKILL_TEXT)
    assert spec.name == "demo"
    assert spec.description == "A demo skill."
    assert spec.triggers == ("alpha", "beta")
    assert spec.allowed_tools == ("fs_read", "fs_list")  # backticks stripped
    assert spec.forbidden_tools == ("fs_write",)
    assert "Do the thing" in spec.steps_md
    assert "done" in spec.report_md


# ── S07.5 frontmatter validation ───────────────────────────────────────────
def test_missing_name_raises():
    text = "---\ndescription: no name here\n---\n\n## Steps\nx\n"
    with pytest.raises(ValueError, match="name"):
        parse_skill(text)


def test_missing_description_raises():
    text = "---\nname: nodesc\n---\n\n## Steps\nx\n"
    with pytest.raises(ValueError, match="description"):
        parse_skill(text)


def test_missing_frontmatter_raises():
    with pytest.raises(ValueError, match="frontmatter"):
        parse_skill("## Allowed (tools)\n- fs_read\n")


# ── S07.2 contract mode / S07.3 full mode ──────────────────────────────────
def test_render_contract_excludes_steps_report():
    reg = SkillRegistry()
    reg.load_text(SKILL_TEXT)
    out = reg.render("demo", mode="contract")
    assert "A demo skill." in out
    assert "Allowed (tools)" in out and "fs_read" in out
    assert "Forbidden (tools)" in out and "fs_write" in out
    assert "Steps" not in out  # body after ## Steps is withheld
    assert "Do the thing" not in out
    assert "Report" not in out


def test_render_full_includes_steps_report():
    reg = SkillRegistry()
    reg.load_text(SKILL_TEXT)
    out = reg.render("demo", mode="full")
    assert "Do the thing" in out
    assert "summary: done" in out


def test_render_unknown_mode_rejected():
    reg = SkillRegistry()
    reg.load_text(SKILL_TEXT)
    with pytest.raises(ValueError, match="contract"):
        reg.render("demo", mode="verbose")


# ── S07.4 derive allowlist (skill-side union; E09 does the rest) ────────────
def test_union_tools_across_skills():
    reg = SkillRegistry()
    reg.load_dir(LIBRARY)
    union = reg.union_tools(["code_review", "file_edit"])
    # union of declared allowed tools across both skills
    assert union == {"fs_read", "fs_list", "fs_write"}
    # a role's allowlist must be a superset of this union (E09 adds core tools)
    role_allowlist = union | {"finish"}
    assert role_allowlist >= union


# ── S07.1 declared tools reference canonical names / lint ───────────────────
def test_library_skills_lint_clean():
    reg = SkillRegistry()
    reg.load_dir(LIBRARY)
    report = reg.lint(lambda t: t in CANONICAL_TOOLS)
    assert report == {}  # every declared tool exists in the registry


def test_lint_flags_unknown_tools():
    reg = SkillRegistry()
    reg.load_text(
        "---\nname: bad\ndescription: bad skill\n---\n\n"
        "## Allowed (tools)\n- fs_read\n- bogus_tool\n"
    )
    report = reg.lint(lambda t: t in CANONICAL_TOOLS)
    assert report == {"bad": ("bogus_tool",)}


def test_get_unknown_skill_raises():
    reg = SkillRegistry()
    with pytest.raises(KeyError, match="Unknown skill"):
        reg.get("nope")


def test_load_dir_returns_all_library_skills():
    reg = SkillRegistry()
    loaded = reg.load_dir(LIBRARY)
    assert {s.name for s in loaded} == set(reg.names())
    assert "code_review" in reg and "file_edit" in reg
