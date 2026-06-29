"""test_port_ai.py — ck AI/media cluster ported into the sibling plugin hs-ai.

Faithful port (master mapping): ai-multimodal, ai-artist, stitch, shader, threejs,
html-video, remotion, media-processing. The tests are DYNAMIC over whatever skills
currently live under hs-ai/skills, so they grow with each per-skill slice: every
ported skill must pass the structure gate (no blocking finding), carry no stale
`ck:` namespace, and have a STANDARDIZE provenance line. Wiring (marketplace +
component) and plugin presence are checked once.
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

_AI = _REPO / "harness" / "plugins" / "hs-ai" / "skills"
_STANDARDIZE = _REPO / "docs" / "STANDARDIZE.md"


def _ai_skills():
    if not _AI.is_dir():
        return []
    return sorted(d.name for d in _AI.iterdir() if (d / "SKILL.md").is_file())


def test_ai_multimodal_ported_first():
    assert "ai-multimodal" in _ai_skills(), \
        "first slice: ai-multimodal must live under hs-ai/skills"


def test_all_ported_ai_skills_gate_clean():
    skills = _ai_skills()
    assert skills, "no hs-ai skills yet"
    for s in skills:
        v = css.check_skill(str(_AI / s))
        blocking = [f for f in v["findings"] if f.get("severity") != "advisory"]
        assert blocking == [], "%s gained blocking findings: %s" % (s, blocking)


def test_marketplace_declares_hs_ai():
    mp = json.loads((_REPO / "harness" / "plugins" / ".claude-plugin"
                     / "marketplace.json").read_text(encoding="utf-8"))
    names = {p["name"] for p in mp["plugins"]}
    assert "hs-ai" in names
    assert "hs" in names  # core stays


def test_plugin_presence_clean_for_hs_ai():
    probs = vi.plugin_presence_problems(_REPO)
    assert not any("hs-ai" in rel or "hs-ai" in prob
                   for rel, prob in probs), probs


def test_components_maps_ai_to_hs_ai():
    import component_config as cc
    comps = cc.load_components()
    assert comps.get("ai", {}).get("plugin") == "hs-ai"


def test_every_ported_ai_skill_in_standardize():
    std = _STANDARDIZE.read_text(encoding="utf-8")
    for s in _ai_skills():
        assert s in std, "%s missing a STANDARDIZE provenance line" % s


def test_no_stale_ck_namespace_in_hs_ai():
    # the port re-brands ck:<skill> -> hs-ai:<skill>; no `ck:` command namespace
    # may survive in the ported tree (a bare 'ck' word in prose is fine).
    if not _AI.parent.is_dir():
        pytest.skip("hs-ai not created yet")
    out = subprocess.run(
        ["grep", "-rEln", r"\bck:[a-z]", str(_AI.parent)],
        capture_output=True, text=True).stdout
    offenders = [f for f in out.splitlines() if not f.endswith("test_port_ai.py")]
    assert offenders == [], "stale ck: namespace in: %s" % offenders
