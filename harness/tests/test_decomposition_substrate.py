"""Phase A substrate: 6 new themed plugins registered + default-only-hs.

The decomposition splits core `hs` into a spine plus six themed sibling plugins
(flow/think/research/create/mem/meta). This phase only REGISTERS them (empty dirs);
skills move in a later phase. Default install enables only the spine `hs`; every
themed plugin (the 7 ck-ports + these 6) ships but defaults disabled.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness" / "scripts"))
import component_config as cc  # noqa: E402

NEW_COMPONENTS = ["flow", "think", "research", "create", "mem", "meta"]
NEW_PLUGINS = ["hs-" + c for c in NEW_COMPONENTS]
THEMED_COMPONENTS = ["uiux", "viz", "devops", "ai", "stack", "integrations", "extra"]
THEMED_PLUGINS = ["hs-uiux", "hs-viz", "hs-devops", "hs-ai", "hs-stack",
                  "hs-integrations", "hs-extra"]
ALL_NONSPINE_PLUGINS = THEMED_PLUGINS + NEW_PLUGINS  # 13
EXPECTED_MARKETPLACE = {"hs", *THEMED_PLUGINS, *NEW_PLUGINS}  # 14


def test_marketplace_declares_all_14_plugins():
    mk = json.loads((ROOT / "harness/plugins/.claude-plugin/marketplace.json").read_text())
    names = {p["name"] for p in mk["plugins"]}
    assert names == EXPECTED_MARKETPLACE
    base = ROOT / "harness/plugins"
    for p in mk["plugins"]:
        assert (base / p["source"]).resolve().is_dir(), \
            f"{p['name']} source {p['source']} is not a dir"


def test_new_plugin_dirs_exist_with_manifest():
    base = ROOT / "harness/plugins"
    for plug in NEW_PLUGINS:
        pj = base / plug / ".claude-plugin" / "plugin.json"
        assert pj.is_file(), f"{plug} missing plugin.json"
        data = json.loads(pj.read_text())
        assert data["name"] == plug
        assert (base / plug / "skills").is_dir(), f"{plug} missing skills/ dir"


def test_new_components_declared():
    comps = cc.load_components()
    for comp, plug in zip(NEW_COMPONENTS, NEW_PLUGINS):
        assert comp in comps, f"component {comp} not declared"
        assert comps[comp].get("plugin") == plug


def test_default_install_enables_only_spine():
    comps = cc.load_components()
    sel = cc.load_policy()
    states = cc.plugin_states(comps, sel)
    # every themed plugin (7 ck-ports + 6 new) is OFF by default
    for plug in ALL_NONSPINE_PLUGINS:
        assert states.get(plug) is False, f"{plug} should default disabled"
    # the spine `hs` is not a component → never appears here → wired ON by install
    assert "hs" not in states
