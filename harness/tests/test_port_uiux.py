"""test_port_uiux.py — ck uiux cluster ported into the sibling plugin hs-uiux.

Faithful port (user-ratified): web-design-guidelines, design, frontend-design,
ui-ux-pro-max + agent ui-ux-designer. The tests are DYNAMIC over whatever skills
currently live under hs-uiux/skills, so they grow with each per-skill slice: every
ported skill must pass the structure gate (no blocking finding), carry no stale
`ck:` namespace, and have a STANDARDIZE provenance line. Wiring (marketplace +
component) and plugin presence are checked once.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest  # noqa: F401

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "harness" / "scripts"))

import check_skill_structure as css  # noqa: E402
import verify_install as vi  # noqa: E402

_UIUX = _REPO / "harness" / "plugins" / "hs-uiux" / "skills"
_STANDARDIZE = _REPO / "docs" / "STANDARDIZE.md"


def _uiux_skills():
    if not _UIUX.is_dir():
        return []
    return sorted(d.name for d in _UIUX.iterdir() if (d / "SKILL.md").is_file())


def test_web_design_guidelines_ported_first():
    assert "web-design-guidelines" in _uiux_skills(), \
        "first slice: web-design-guidelines must live under hs-uiux/skills"


def test_all_ported_uiux_skills_gate_clean():
    skills = _uiux_skills()
    assert skills, "no hs-uiux skills yet"
    for s in skills:
        v = css.check_skill(str(_UIUX / s))
        blocking = [f for f in v["findings"] if f.get("severity") != "advisory"]
        assert blocking == [], "%s gained blocking findings: %s" % (s, blocking)


def test_marketplace_declares_hs_uiux():
    mp = json.loads((_REPO / "harness" / "plugins" / ".claude-plugin"
                     / "marketplace.json").read_text(encoding="utf-8"))
    names = {p["name"] for p in mp["plugins"]}
    assert "hs-uiux" in names
    assert "hs" in names  # core stays


def test_plugin_presence_clean_for_hs_uiux():
    probs = vi.plugin_presence_problems(_REPO)
    assert not any("hs-uiux" in rel or "hs-uiux" in prob
                   for rel, prob in probs), probs


def test_components_maps_uiux_to_hs_uiux():
    import component_config as cc
    comps = cc.load_components()
    assert comps.get("uiux", {}).get("plugin") == "hs-uiux"


def test_every_ported_uiux_skill_in_standardize():
    std = _STANDARDIZE.read_text(encoding="utf-8")
    for s in _uiux_skills():
        assert s in std, "%s missing a STANDARDIZE provenance line" % s


def test_no_stale_ck_namespace_in_hs_uiux():
    # the port re-brands ck:<skill> -> hs-uiux:<skill>; no `ck:` command namespace
    # may survive in the ported tree (a bare 'ck' word in prose is fine — we match
    # the `ck:` prefix only).
    if not _UIUX.parent.is_dir():
        pytest.skip("hs-uiux not created yet")
    out = subprocess.run(
        ["grep", "-rEln", r"\bck:[a-z]", str(_UIUX.parent)],
        capture_output=True, text=True).stdout
    offenders = [f for f in out.splitlines() if not f.endswith("test_port_uiux.py")]
    assert offenders == [], "stale ck: namespace in: %s" % offenders
