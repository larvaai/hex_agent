"""Phase D: the disabled-group reference nudge (advisory, fail-open).

After the decomposition a fresh install enables only the spine; the six themed
groups are opt-in. A skill handoff that points at a skill in a disabled group is
NOT a broken reference — the nudge spots it and suggests enabling the group (or
reading the skill inline), without ever deleting the reference or blocking.
"""
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "harness" / "hooks"
sys.path.insert(0, str(HOOKS))
import disabled_ref_nudge as drn  # noqa: E402


def _settings(tmp: Path, enabled: dict) -> None:
    d = tmp / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    (d / "settings.local.json").write_text(json.dumps({"enabledPlugins": enabled}))


def test_hook_class_is_nudge():
    assert drn.HOOK_CLASS == "nudge"


def test_ref_to_disabled_group_nudges(tmp_path, monkeypatch):
    _settings(tmp_path, {"hs@hs-local": True})  # only spine enabled
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    msg = drn.core({"prompt": "please run hs-mem:remember to save this"})
    assert msg, "expected a nudge for a disabled-group ref"
    assert "hs-mem:remember" in msg
    assert "enable" in msg.lower()


def test_ref_to_enabled_group_is_silent(tmp_path, monkeypatch):
    _settings(tmp_path, {"hs@hs-local": True, "hs-mem@hs-local": True})
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert drn.core({"prompt": "run hs-mem:remember"}) is None


def test_spine_ref_never_nudges(tmp_path, monkeypatch):
    _settings(tmp_path, {"hs@hs-local": True})
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert drn.core({"prompt": "run hs:plan then hs:cook then hs:ship"}) is None


def test_no_refs_is_silent(tmp_path, monkeypatch):
    _settings(tmp_path, {"hs@hs-local": True})
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert drn.core({"prompt": "just a normal message, no skill refs"}) is None


def test_main_is_fail_open_on_garbage_stdin(tmp_path, monkeypatch):
    # enabling the nudge + feeding non-JSON must still exit 0 (never break a session)
    cfg = tmp_path / "harness-hooks.yaml"
    cfg.write_text(yaml.safe_dump({"hooks": {"disabled_ref_nudge": {"enabled": True}}}))
    env = {
        "PATH": "/usr/bin:/bin",
        "HARNESS_HOOK_CONFIG": str(cfg),
        "CLAUDE_PROJECT_DIR": str(tmp_path),
    }
    proc = subprocess.run(
        [sys.executable, str(HOOKS / "disabled_ref_nudge.py")],
        input="this is not json", capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0


def test_registered_and_enabled():
    reg = (ROOT / "harness/install/hooks-registration.yaml").read_text()
    assert "disabled_ref_nudge.py" in reg
    cfg = yaml.safe_load((ROOT / "harness/hooks/harness-hooks.yaml").read_text())
    entry = (cfg.get("hooks") or {}).get("disabled_ref_nudge") or {}
    assert entry.get("enabled") is True


def test_rule_exists_and_routed_in_claude_md():
    assert (ROOT / "harness/rules/disabled-group-handling.md").is_file()
    assert "disabled-group-handling" in (ROOT / "CLAUDE.md").read_text()


def test_non_boolean_enabled_value_reads_as_disabled(tmp_path, monkeypatch):
    # enabledPlugins values are JSON booleans; a malformed value (the string
    # "false") must NOT count as enabled. bool("false") is True, so a naive
    # coercion would silence the nudge — only real boolean True means enabled.
    _settings(tmp_path, {"hs@hs-local": True, "hs-mem@hs-local": "false"})
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    msg = drn.core({"prompt": "run hs-mem:remember"})
    assert msg, "string 'false' must read as disabled -> nudge fires"
    assert "hs-mem:remember" in msg


def test_ref_inside_url_or_domain_is_not_a_false_positive(tmp_path, monkeypatch):
    # A skill-looking token inside a URL/domain (preceded by '.' or '/') is not a
    # code reference — the nudge must not fire on it.
    _settings(tmp_path, {"hs@hs-local": True})
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert drn.core(
        {"prompt": "see https://example.com/hs-flow:plan and www.hs-mem:remember.io"}
    ) is None
