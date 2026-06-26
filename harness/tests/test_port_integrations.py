"""test_port_integrations.py — ck integrations cluster ported into hs-integrations.

Faithful port (master mapping): payment-integration, shopify, google-adk-python,
use-mcp, gkg. The tests are DYNAMIC over whatever skills currently live under
hs-integrations/skills, so they grow with each per-skill slice: every ported skill
must pass the structure gate (no blocking finding), carry no stale `ck:` namespace,
and have a STANDARDIZE provenance line. Wiring (marketplace + component) and plugin
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

_INT = _REPO / "harness" / "plugins" / "hs-integrations" / "skills"
_STANDARDIZE = _REPO / "docs" / "STANDARDIZE.md"


def _int_skills():
    if not _INT.is_dir():
        return []
    return sorted(d.name for d in _INT.iterdir() if (d / "SKILL.md").is_file())


def test_gkg_ported_first():
    assert "gkg" in _int_skills(), \
        "first slice: gkg must live under hs-integrations/skills"


def test_all_ported_integration_skills_gate_clean():
    skills = _int_skills()
    assert skills, "no hs-integrations skills yet"
    for s in skills:
        v = css.check_skill(str(_INT / s))
        blocking = [f for f in v["findings"] if f.get("severity") != "advisory"]
        assert blocking == [], "%s gained blocking findings: %s" % (s, blocking)


def test_marketplace_declares_hs_integrations():
    mp = json.loads((_REPO / "harness" / "plugins" / ".claude-plugin"
                     / "marketplace.json").read_text(encoding="utf-8"))
    names = {p["name"] for p in mp["plugins"]}
    assert "hs-integrations" in names
    assert "hs" in names  # core stays


def test_plugin_presence_clean_for_hs_integrations():
    probs = vi.plugin_presence_problems(_REPO)
    assert not any("hs-integrations" in rel or "hs-integrations" in prob
                   for rel, prob in probs), probs


def test_components_maps_integrations_to_hs_integrations():
    import component_config as cc
    comps = cc.load_components()
    assert comps.get("integrations", {}).get("plugin") == "hs-integrations"


def test_every_ported_integration_skill_in_standardize():
    std = _STANDARDIZE.read_text(encoding="utf-8")
    for s in _int_skills():
        assert s in std, "%s missing a STANDARDIZE provenance line" % s


def test_no_stale_ck_namespace_in_hs_integrations():
    # the port re-brands ck:<skill> -> hs-integrations:<skill>; no `ck:` command
    # namespace may survive in the ported tree (a bare 'ck' word in prose is fine).
    if not _INT.parent.is_dir():
        pytest.skip("hs-integrations not created yet")
    out = subprocess.run(
        ["grep", "-rEln", r"\bck:[a-z]", str(_INT.parent)],
        capture_output=True, text=True).stdout
    offenders = [f for f in out.splitlines()
                 if not f.endswith("test_port_integrations.py")]
    assert offenders == [], "stale ck: namespace in: %s" % offenders
