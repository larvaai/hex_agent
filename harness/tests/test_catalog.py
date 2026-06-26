"""test_catalog.py — skill catalog loader + slug↔dir normalization.

Harness skills live in harness/skills/<dir>/SKILL.md where the dir is
kebab-case (`hs-plan`) and the invoke name in frontmatter is namespaced
(`name: hs:plan`). The catalog maps every recorded identity back to
the canonical dir slug; `owned` = dirs whose name starts with `hs:`.
"""
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from catalog import load_catalog, tier_problems, to_dir_id  # noqa: E402


def _mk_skill(sdir: Path, dirname: str, name: str):
    d = sdir / dirname
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: %s\ndescription: x\n---\n\n# %s\n" % (name, name),
        encoding="utf-8",
    )


def _mk_skill_tier(sdir: Path, dirname: str, name: str, tier: str):
    d = sdir / dirname
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: %s\ndescription: x\nmetadata:\n  owner: harness\n"
        "  compliance-tier: %s\n---\n\n# %s\n" % (name, tier, name),
        encoding="utf-8",
    )


@pytest.fixture()
def skills(tmp_path):
    sdir = tmp_path / "skills"
    _mk_skill(sdir, "hs-plan", "hs:plan")
    _mk_skill(sdir, "hs-cook", "hs:cook")
    _mk_skill(sdir, "vendored-tool", "ck:tool")
    (sdir / "not-a-skill").mkdir()  # no SKILL.md → ignored
    return sdir


class TestLoadCatalog:
    def test_dirs_are_dirs_with_skill_md_only(self, skills):
        cat = load_catalog(skills)
        assert cat["dirs"] == {"hs-plan", "hs-cook", "vendored-tool"}

    def test_slug_map_covers_name_and_hyphen_variant_and_dir(self, skills):
        cat = load_catalog(skills)
        s2d = cat["slug_to_dir"]
        assert s2d["hs:plan"] == "hs-plan"
        assert s2d["hs-plan"] == "hs-plan"

    def test_owned_is_hs_prefixed_only(self, skills):
        cat = load_catalog(skills)
        assert cat["owned"] == {"hs-plan", "hs-cook"}

    def test_missing_dir_fail_soft_empty(self, tmp_path):
        cat = load_catalog(tmp_path / "nope")
        assert cat == {"dirs": set(), "slug_to_dir": {}, "owned": set()}

    def test_real_catalog_is_family_wide_across_plugins(self):
        # After the viz split the no-arg catalog must span ALL harness plugins
        # (harness/plugins/*/skills), not just hs — else find-skills' phantom-guard
        # and the usage/chain lenses go blind to the hs-viz sibling's skills.
        cat = load_catalog()  # no sdir -> real, family-wide
        assert "plan" in cat["dirs"]          # core hs still present
        assert "excalidraw" in cat["dirs"]    # hs-viz sibling included
        assert "excalidraw" in cat["owned"]   # hs-viz: is the owned hs family
        assert to_dir_id("hs-viz:excalidraw", cat) == "excalidraw"  # folds like hs:
        assert to_dir_id("hs:plan", cat) == "plan"

    def test_two_plugins_with_same_dir_name_both_counted(self, tmp_path):
        # family scan merges sibling plugins; an explicit sdir still scans one.
        a = tmp_path / "plugins" / "hs" / "skills"
        b = tmp_path / "plugins" / "hs-viz" / "skills"
        _mk_skill(a, "plan", "hs:plan")
        _mk_skill(b, "excalidraw", "hs-viz:excalidraw")
        import catalog as _c
        merged = {"dirs": set(), "slug_to_dir": {}, "owned": set()}
        for s in (a, b):
            one = load_catalog(s)
            merged["dirs"] |= one["dirs"]
            merged["owned"] |= one["owned"]
        assert merged["owned"] == {"plan", "excalidraw"}


class TestToDirId:
    def test_invoke_name_resolves_to_dir(self, skills):
        cat = load_catalog(skills)
        assert to_dir_id("hs:plan", cat) == "hs-plan"

    def test_dir_form_resolves_to_itself(self, skills):
        cat = load_catalog(skills)
        assert to_dir_id("hs-cook", cat) == "hs-cook"

    def test_unknown_skill_counted_under_flat_slug_never_dropped(self, skills):
        cat = load_catalog(skills)
        assert to_dir_id("xx:mystery", cat) == "xx-mystery"

    def test_foreign_namespaced_skill_not_conflated_into_bare_hs_dir(self, tmp_path):
        # The real catalog ships bare dirs (`docs`) whose frontmatter name is `hs-mem:docs`.
        # A FOREIGN namespaced identity that shares the tail (ck:docs from another
        # plugin) must NOT fold into that hs dir via the tail-match — else the lens
        # over-counts hs-mem:docs with another plugin's usage. The hs skill still resolves.
        sk = tmp_path / "skills"
        d = sk / "docs"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\nname: hs-mem:docs\ncompliance-tier: knowledge\n---\n# t\n", encoding="utf-8")
        cat = load_catalog(sk)
        assert to_dir_id("hs-mem:docs", cat) == "docs"      # the real hs skill resolves
        assert to_dir_id("ck:docs", cat) == "ck-docs"   # foreign stays flat, not "docs"

    def test_empty_yields_empty(self, skills):
        assert to_dir_id("", load_catalog(skills)) == ""


class TestTierProblems:
    def test_valid_tiers_pass(self, tmp_path):
        sdir = tmp_path / "skills"
        _mk_skill_tier(sdir, "hs-a", "hs:a", "workflow")
        _mk_skill_tier(sdir, "hs-b", "hs:b", "gate")
        _mk_skill_tier(sdir, "hs-c", "hs:c", "knowledge")
        assert tier_problems(sdir) == []

    def test_invalid_tier_flagged(self, tmp_path):
        sdir = tmp_path / "skills"
        _mk_skill_tier(sdir, "hs-bad", "hs:bad", "bogus")
        assert any("hs-bad" in p and "invalid" in p for p in tier_problems(sdir))

    def test_missing_tier_flagged_for_owned(self, tmp_path):
        sdir = tmp_path / "skills"
        _mk_skill(sdir, "hs-x", "hs:x")  # _mk_skill writes no metadata block
        assert any("hs-x" in p and "missing" in p for p in tier_problems(sdir))

    def test_vendored_skill_is_exempt(self, tmp_path):
        sdir = tmp_path / "skills"
        _mk_skill(sdir, "vendored", "ck:tool")  # not hs: → not the harness's
        assert tier_problems(sdir) == []

    def test_body_prose_enum_is_not_a_false_positive(self, tmp_path):
        # A skill whose BODY documents the tier enum must not be flagged —
        # only the frontmatter value counts.
        sdir = tmp_path / "skills"
        d = sdir / "hs-doc"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\nname: hs:doc\ndescription: x\nmetadata:\n"
            "  compliance-tier: workflow\n---\n\n"
            "Tiers: compliance-tier: workflow | gate | telemetry | knowledge\n",
            encoding="utf-8")
        assert tier_problems(sdir) == []
