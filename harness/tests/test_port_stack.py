"""test_port_stack.py — ck full-stack cluster ported into the sibling plugin hs-stack.

Faithful port (master mapping): backend-development, frontend-development,
mobile-development, databases, react-best-practices, web-frameworks, tanstack,
better-auth. The tests are DYNAMIC over whatever skills currently live under
hs-stack/skills, so they grow with each per-skill slice: every ported skill must
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

_STACK = _REPO / "harness" / "plugins" / "hs-stack" / "skills"
_STANDARDIZE = _REPO / "docs" / "STANDARDIZE.md"


def _stack_skills():
    if not _STACK.is_dir():
        return []
    return sorted(d.name for d in _STACK.iterdir() if (d / "SKILL.md").is_file())


def test_react_best_practices_ported_first():
    assert "react-best-practices" in _stack_skills(), \
        "first slice: react-best-practices must live under hs-stack/skills"


def test_all_ported_stack_skills_gate_clean():
    skills = _stack_skills()
    assert skills, "no hs-stack skills yet"
    for s in skills:
        v = css.check_skill(str(_STACK / s))
        blocking = [f for f in v["findings"] if f.get("severity") != "advisory"]
        assert blocking == [], "%s gained blocking findings: %s" % (s, blocking)


def test_marketplace_declares_hs_stack():
    mp = json.loads((_REPO / "harness" / "plugins" / ".claude-plugin"
                     / "marketplace.json").read_text(encoding="utf-8"))
    names = {p["name"] for p in mp["plugins"]}
    assert "hs-stack" in names
    assert "hs" in names  # core stays


def test_plugin_presence_clean_for_hs_stack():
    probs = vi.plugin_presence_problems(_REPO)
    assert not any("hs-stack" in rel or "hs-stack" in prob
                   for rel, prob in probs), probs


def test_components_maps_stack_to_hs_stack():
    import component_config as cc
    comps = cc.load_components()
    assert comps.get("stack", {}).get("plugin") == "hs-stack"


def test_every_ported_stack_skill_in_standardize():
    std = _STANDARDIZE.read_text(encoding="utf-8")
    for s in _stack_skills():
        assert s in std, "%s missing a STANDARDIZE provenance line" % s


def test_no_stale_ck_namespace_in_hs_stack():
    # the port re-brands ck:<skill> -> hs-stack:<skill>; no `ck:` command namespace
    # may survive in the ported tree (a bare 'ck' word in prose is fine).
    if not _STACK.parent.is_dir():
        pytest.skip("hs-stack not created yet")
    out = subprocess.run(
        ["grep", "-rEln", r"\bck:[a-z]", str(_STACK.parent)],
        capture_output=True, text=True).stdout
    offenders = [f for f in out.splitlines() if not f.endswith("test_port_stack.py")]
    assert offenders == [], "stale ck: namespace in: %s" % offenders
