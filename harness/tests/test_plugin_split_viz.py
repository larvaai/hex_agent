"""test_plugin_split_viz.py — the first real skill split: viz cluster hs -> hs-viz.

Five viz skills (excalidraw, mermaidjs, graphify, tech-graph, preview) move OUT of
core `hs` into the sibling plugin `hs-viz`. Core `hs` is immutable; only this
cluster's prefix changes (`/hs:excalidraw` -> `/hs-viz:excalidraw`). The split is
proven by structure (skills live under hs-viz, gate-clean), wiring (marketplace +
component), and a zero-stale-prefix sweep (plan Success: "0 ref prefix cũ").
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest  # noqa: F401

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "harness" / "scripts"))

import check_skill_structure as css  # noqa: E402
import verify_install as vi  # noqa: E402

VIZ = ["excalidraw", "mermaidjs", "graphify", "tech-graph", "preview"]
_HS = _REPO / "harness" / "plugins" / "hs" / "skills"
_HSVIZ = _REPO / "harness" / "plugins" / "hs-viz" / "skills"


def test_viz_skills_moved_to_hs_viz():
    for s in VIZ:
        assert (_HSVIZ / s / "SKILL.md").is_file(), "%s not under hs-viz/skills" % s
        assert not (_HS / s).exists(), "%s still under hs/skills (not moved)" % s


def test_moved_viz_skills_stay_gate_clean():
    # the move must not introduce a BLOCKING structural finding (advisory is fine —
    # these skills were PASS_WITH_RISK/advisory before the move too).
    for s in VIZ:
        v = css.check_skill(str(_HSVIZ / s))
        blocking = [f for f in v["findings"] if f.get("severity") != "advisory"]
        assert blocking == [], "%s gained blocking findings: %s" % (s, blocking)


def test_marketplace_declares_hs_viz():
    import json
    mp = json.loads((_REPO / "harness" / "plugins" / ".claude-plugin"
                     / "marketplace.json").read_text(encoding="utf-8"))
    names = {p["name"] for p in mp["plugins"]}
    assert "hs-viz" in names
    assert "hs" in names  # core stays


def test_plugin_presence_clean_for_hs_viz():
    probs = vi.plugin_presence_problems(_REPO)
    assert not any("hs-viz" in rel or "hs-viz" in prob for rel, prob in probs), probs


def test_components_maps_viz_to_hs_viz():
    import component_config as cc
    comps = cc.load_components()
    assert comps.get("viz", {}).get("plugin") == "hs-viz"


def test_zero_stale_old_prefix_refs():
    # plan Success criterion: "0 ref prefix cũ". No `hs:<viz>` (slash or bare) may
    # survive anywhere under harness/ or docs/ — every reference must read hs-viz:.
    # (hs-viz:excalidraw does NOT contain hs:excalidraw, so the pattern is safe.)
    pat = re.compile(r"\bhs:(?:%s)\b" % "|".join(re.escape(v) for v in VIZ))
    offenders = []
    for base in (_REPO / "harness", _REPO / "docs"):
        out = subprocess.run(
            ["grep", "-rEln", r"hs:(excalidraw|mermaidjs|graphify|tech-graph|preview)",
             "--include=*.md", "--include=*.yaml", "--include=*.yml", "--include=*.py",
             str(base)],
            capture_output=True, text=True).stdout
        for f in out.splitlines():
            if f.endswith("test_plugin_split_viz.py"):
                continue
            text = Path(f).read_text(encoding="utf-8")
            if pat.search(text):
                offenders.append(f)
    assert offenders == [], "stale hs:<viz> prefix in: %s" % offenders
