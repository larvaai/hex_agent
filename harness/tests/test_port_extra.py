"""test_port_extra.py — ck misc/content/PM cluster ported into hs-extra.

Faithful port (master mapping): ask, llms, watzup, copywriting, ghpm, mintlify,
markdown-novel-viewer, cti-expert. The tests are DYNAMIC over whatever skills
currently live under hs-extra/skills, so they grow with each per-skill slice:
every ported skill must pass the structure gate (no blocking finding), carry no
stale `ck:` namespace, and have a STANDARDIZE provenance line. Wiring (marketplace
+ component) and plugin presence are checked once.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest  # noqa: F401

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "harness" / "scripts"))

import check_skill_structure as css  # noqa: E402
import verify_install as vi  # noqa: E402

_EXTRA = _REPO / "harness" / "plugins" / "hs-extra" / "skills"
_STANDARDIZE = _REPO / "docs" / "STANDARDIZE.md"


def _extra_skills():
    if not _EXTRA.is_dir():
        return []
    return sorted(d.name for d in _EXTRA.iterdir() if (d / "SKILL.md").is_file())


def test_ask_ported_first():
    assert "ask" in _extra_skills(), \
        "first slice: ask must live under hs-extra/skills"


def test_all_ported_extra_skills_gate_clean():
    skills = _extra_skills()
    assert skills, "no hs-extra skills yet"
    for s in skills:
        v = css.check_skill(str(_EXTRA / s))
        blocking = [f for f in v["findings"] if f.get("severity") != "advisory"]
        assert blocking == [], "%s gained blocking findings: %s" % (s, blocking)


def test_marketplace_declares_hs_extra():
    mp = json.loads((_REPO / "harness" / "plugins" / ".claude-plugin"
                     / "marketplace.json").read_text(encoding="utf-8"))
    names = {p["name"] for p in mp["plugins"]}
    assert "hs-extra" in names
    assert "hs" in names  # core stays


def test_plugin_presence_clean_for_hs_extra():
    probs = vi.plugin_presence_problems(_REPO)
    assert not any("hs-extra" in rel or "hs-extra" in prob
                   for rel, prob in probs), probs


def test_components_maps_extra_to_hs_extra():
    import component_config as cc
    comps = cc.load_components()
    assert comps.get("extra", {}).get("plugin") == "hs-extra"


def test_every_ported_extra_skill_in_standardize():
    std = _STANDARDIZE.read_text(encoding="utf-8")
    for s in _extra_skills():
        assert s in std, "%s missing a STANDARDIZE provenance line" % s


def test_no_stale_ck_namespace_in_hs_extra():
    # the port re-brands ck:<skill> -> hs-extra:<skill>; no `ck:` command
    # namespace may survive in the ported tree (a bare 'ck' word in prose is fine).
    if not _EXTRA.parent.is_dir():
        pytest.skip("hs-extra not created yet")
    out = subprocess.run(
        ["grep", "-rEln", r"\bck:[a-z]", str(_EXTRA.parent)],
        capture_output=True, text=True).stdout
    offenders = [f for f in out.splitlines()
                 if not f.endswith("test_port_extra.py")]
    assert offenders == [], "stale ck: namespace in: %s" % offenders
