"""Phase E: hs-cli — a thin operator front-end over existing harness scripts.

Each verb wraps a script that already carries the logic (verify_install, preflight,
migrate_decomposition, component_config, install). The CLI adds no new behaviour, so
the tests assert it dispatches correctly and propagates exit codes — not that it
re-implements anything.
"""
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "harness" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import hs_cli  # noqa: E402


def test_version_prints_release_fields(capsys):
    rel = json.loads((ROOT / "harness/release.json").read_text())
    assert hs_cli.main(["version"]) == 0
    out = capsys.readouterr().out
    assert rel["harness_version"] in out
    assert rel["kit_digest"][:8] in out


def test_migrate_check_proxies_engine_exit():
    # the real tree is migrated → engine --check reports 0 dangling → exit 0
    assert hs_cli.main(["migrate", "--check"]) == 0


def test_list_shows_plugins_and_skills(capsys):
    assert hs_cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "hs-flow" in out
    assert "loop" in out          # a flow skill
    assert "hs" in out and "plan" in out  # spine + a spine skill


def test_components_enable_flips_policy_and_settings(tmp_path):
    pol = tmp_path / "policy.yaml"
    pol.write_text("components: {}\n")          # ship-all baseline
    settings = tmp_path / "settings.json"
    settings.write_text("{}")
    hooks = tmp_path / "hooks.yaml"
    hooks.write_text("hooks: {}\n")
    state = tmp_path / "state.json"
    rc = hs_cli.main([
        "components", "--disable", "hs-flow",
        "--policy-file", str(pol), "--settings-file", str(settings),
        "--hooks-file", str(hooks), "--state-file", str(state),
    ])
    assert rc == 0
    # disabling a component is recorded as a deviation from ship-all
    pdata = yaml.safe_load(pol.read_text()) or {}
    assert pdata.get("components", {}).get("flow") is False
    # and projected into enabledPlugins
    sdata = json.loads(settings.read_text())
    keys = {k.split("@", 1)[0]: v for k, v in sdata.get("enabledPlugins", {}).items()}
    assert keys.get("hs-flow") is False


def test_components_accepts_bare_group_name(tmp_path):
    pol = tmp_path / "policy.yaml"
    pol.write_text("components: {}\n")
    rc = hs_cli.main(["components", "--disable", "think",
                      "--policy-file", str(pol),
                      "--hooks-file", str(tmp_path / "h.yaml"),
                      "--state-file", str(tmp_path / "s.json")])
    assert rc == 0
    assert (yaml.safe_load(pol.read_text()) or {}).get("components", {}).get("think") is False


def test_unknown_verb_is_nonzero():
    proc = subprocess.run([sys.executable, str(SCRIPTS / "hs_cli.py"), "bogus"],
                          capture_output=True, text=True)
    assert proc.returncode != 0


def test_doctor_runs_clean_on_this_repo():
    # verify_install --strict + preflight on the live (consistent) tree → 0
    assert hs_cli.main(["doctor"]) == 0
