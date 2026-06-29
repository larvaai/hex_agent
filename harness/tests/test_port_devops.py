"""test_port_devops.py — ck devops cluster ported into the sibling plugin hs-devops.

Faithful port (master mapping): deploy, devops, web-testing, agent-browser,
chrome-profile. The tests are DYNAMIC over whatever skills currently live under
hs-devops/skills, so they grow with each per-skill slice: every ported skill must
pass the structure gate (no blocking finding), carry no stale `ck:` namespace, and
have a STANDARDIZE provenance line. Wiring (marketplace + component) and plugin
presence are checked once.
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

_DEVOPS = _REPO / "harness" / "plugins" / "hs-devops" / "skills"
_STANDARDIZE = _REPO / "docs" / "STANDARDIZE.md"


def _devops_skills():
    if not _DEVOPS.is_dir():
        return []
    return sorted(d.name for d in _DEVOPS.iterdir() if (d / "SKILL.md").is_file())


def test_agent_browser_ported_first():
    assert "agent-browser" in _devops_skills(), \
        "first slice: agent-browser must live under hs-devops/skills"


def test_all_ported_devops_skills_gate_clean():
    skills = _devops_skills()
    assert skills, "no hs-devops skills yet"
    for s in skills:
        v = css.check_skill(str(_DEVOPS / s))
        blocking = [f for f in v["findings"] if f.get("severity") != "advisory"]
        assert blocking == [], "%s gained blocking findings: %s" % (s, blocking)


def test_marketplace_declares_hs_devops():
    mp = json.loads((_REPO / "harness" / "plugins" / ".claude-plugin"
                     / "marketplace.json").read_text(encoding="utf-8"))
    names = {p["name"] for p in mp["plugins"]}
    assert "hs-devops" in names
    assert "hs" in names  # core stays


def test_plugin_presence_clean_for_hs_devops():
    probs = vi.plugin_presence_problems(_REPO)
    assert not any("hs-devops" in rel or "hs-devops" in prob
                   for rel, prob in probs), probs


def test_components_maps_devops_to_hs_devops():
    import component_config as cc
    comps = cc.load_components()
    assert comps.get("devops", {}).get("plugin") == "hs-devops"


def test_every_ported_devops_skill_in_standardize():
    std = _STANDARDIZE.read_text(encoding="utf-8")
    for s in _devops_skills():
        assert s in std, "%s missing a STANDARDIZE provenance line" % s


def test_no_stale_ck_namespace_in_hs_devops():
    # the port re-brands ck:<skill> -> hs-devops:<skill>; no `ck:` command
    # namespace may survive in the ported tree (a bare 'ck' word in prose is fine).
    if not _DEVOPS.parent.is_dir():
        pytest.skip("hs-devops not created yet")
    out = subprocess.run(
        ["grep", "-rEln", r"\bck:[a-z]", str(_DEVOPS.parent)],
        capture_output=True, text=True).stdout
    offenders = [f for f in out.splitlines() if not f.endswith("test_port_devops.py")]
    assert offenders == [], "stale ck: namespace in: %s" % offenders
