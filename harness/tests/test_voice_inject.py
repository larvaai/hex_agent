"""test_voice_inject.py — SessionStart hook that injects the terminal-voice
guidance as additionalContext.

Telemetry-class + fail-open: it advises the model, it NEVER blocks. The resolved
knob values plus the floor + scope-fence ride in additionalContext so the voice
is live for the whole session (and re-fires on /compact). A broken config or a
crashing core degrades to a plain continue, never to exit 2.

The hook is driven as a subprocess (the real stdin/stdout contract) with
HARNESS_TERMINAL_VOICE pointed at a scratch yaml; the fail-open-no-context path
is exercised in-process against the hook_runtime wrapper.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_RULES = Path(__file__).resolve().parent.parent / "rules"
sys.path.insert(0, str(_HOOKS))


def _env(tmp_path, voice_file=None, **extra):
    env = dict(os.environ)
    env["HARNESS_STATE_DIR"] = str(tmp_path / "state")
    env["HARNESS_HOOK_LOG_DIR"] = str(tmp_path / "logs")
    env["HARNESS_HOOK_AUDIT_DISABLED"] = "1"
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("HARNESS_TELEMETRY_DISABLED", None)
    if voice_file is not None:
        env["HARNESS_TERMINAL_VOICE"] = str(voice_file)
    else:
        env["HARNESS_TERMINAL_VOICE"] = str(tmp_path / "absent.yaml")  # → defaults
    env.update(extra)
    return env


def _run(tmp_path, stdin_obj, voice_file=None, **extra):
    return subprocess.run(
        [sys.executable, str(_HOOKS / "voice_inject.py")],
        input=json.dumps(stdin_obj), capture_output=True, text=True,
        env=_env(tmp_path, voice_file=voice_file, **extra),
    )


def _voice(tmp_path, doc):
    import yaml
    p = tmp_path / "terminal-voice.yaml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return p


def _ctx(proc):
    out = json.loads(proc.stdout)
    hs = out.get("hookSpecificOutput") or {}
    return hs.get("additionalContext", "")


# ----------------------------------------------------------- defaults inject ---

def test_defaults_inject_level5_depth5(tmp_path):
    proc = _run(tmp_path, {"session_id": "s1", "source": "startup"})
    assert proc.returncode == 0
    ctx = _ctx(proc)
    assert "voice_level=5" in ctx
    assert "terminal_voice_level=5" in ctx


def test_context_names_floor_and_fence(tmp_path):
    ctx = _ctx(_run(tmp_path, {"session_id": "s1"}))
    assert "Universal-harm floor" in ctx
    assert "Scope-fence" in ctx
    assert "terminal-voice.md" in ctx  # points at the authority, not a restatement


# -------------------------------------------------------------- level 9 register ---

def test_level9_names_register(tmp_path):
    p = _voice(tmp_path, {"voice_level": 9})
    ctx = _ctx(_run(tmp_path, {"session_id": "s1"}, voice_file=p))
    assert "voice_level=9" in ctx
    assert "profanity" in ctx.lower()       # work-aimed register named
    assert "Universal-harm floor" in ctx    # ...but the floor still rides along


# ------------------------------------------------------- artifact-voice carve-out ---

def test_context_carves_out_artifact_voice(tmp_path):
    # The injected guidance must tell the model voice_level does NOT touch an
    # artifact's own designed voice — naming the two existing cases.
    ctx = _ctx(_run(tmp_path, {"session_id": "s1"}))
    low = ctx.lower()
    assert "journal" in low
    assert "critique" in low


def test_no_markdown_flag_surfaces(tmp_path):
    p = _voice(tmp_path, {"no_markdown": True})
    ctx = _ctx(_run(tmp_path, {"session_id": "s1"}, voice_file=p))
    assert "no_markdown" in ctx or "plain prose" in ctx.lower()


def test_persona_surfaces_in_context(tmp_path):
    p = _voice(tmp_path, {"persona": "pirate"})
    ctx = _ctx(_run(tmp_path, {"session_id": "s1"}, voice_file=p))
    assert "persona=pirate" in ctx
    assert "voice_level sets" in ctx  # the form-vs-harshness precedence line


# ----------------------------------------------------- ladder drift-guard (M1) ---

# The hook restates a terse per-level register/depth descriptor; the canonical
# table lives in terminal-voice.md. These anchors must appear in BOTH so a rule
# edit that drops an anchor (or a hook edit that drifts) trips CI — the same
# discipline the persona ids already get from their parity test.
_REGISTER_ANCHORS = {
    1: "polite, measured",
    3: "direct but courteous",
    5: "NO profanity",
    6: "name a bad idea as bad",
    7: "roast the work",
    8: "vi pronouns",
    9: "đm/vl",
}
_DEPTH_ANCHORS = {0: "answer only", 3: "reasoning + key trade-offs", 5: "full reasoning"}


def test_register_ladder_anchors_match_rule():
    import voice_inject
    rule = (_RULES / "terminal-voice.md").read_text(encoding="utf-8")
    for level, anchor in _REGISTER_ANCHORS.items():
        assert anchor in voice_inject._register(level), (level, "hook")
        assert anchor in rule, (level, "rule")


def test_depth_ladder_anchors_match_rule():
    import voice_inject
    rule = (_RULES / "terminal-voice.md").read_text(encoding="utf-8")
    for level, anchor in _DEPTH_ANCHORS.items():
        assert anchor in voice_inject._depth(level), (level, "hook")
        assert anchor in rule, (level, "rule")


def test_interview_knobs_surface_in_context(tmp_path):
    p = _voice(tmp_path, {"interview_rigor": "deep",
                          "action_prompting": "proactive",
                          "detail_level": "verbose"})
    ctx = _ctx(_run(tmp_path, {"session_id": "s1"}, voice_file=p))
    assert "interview_rigor=deep" in ctx
    assert "action_prompting=proactive" in ctx
    assert "detail_level=verbose" in ctx


# --------------------------------------------------------------------- fail-open ---

def test_corrupt_config_continues_never_blocks(tmp_path):
    p = tmp_path / "terminal-voice.yaml"
    p.write_text("voice_level: [oops\n:::bad", encoding="utf-8")
    proc = _run(tmp_path, {"session_id": "s1"}, voice_file=p)
    assert proc.returncode == 0                 # never exit 2
    json.loads(proc.stdout)                      # valid JSON contract
    # tolerant loader → defaults → still sane guidance (level 5)
    assert "voice_level=5" in _ctx(proc)


def test_garbage_stdin_never_exits_2(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(_HOOKS / "voice_inject.py")],
        input="not json at all", capture_output=True, text=True,
        env=_env(tmp_path),
    )
    assert proc.returncode == 0


def test_telemetry_disabled_emits_continue_no_context(tmp_path):
    proc = _run(tmp_path, {"session_id": "s1"}, HARNESS_TELEMETRY_DISABLED="1")
    assert proc.returncode == 0
    assert _ctx(proc) == ""               # disabled → no injection
    assert "continue" in proc.stdout


def test_failopen_no_context_on_load_raise(monkeypatch, capsys):
    # Direct unit on voice_inject's own fail-open path: if the loader itself
    # raises (it shouldn't — it's tolerant — but defense in depth), the hook
    # degrades to a plain continue with NO additionalContext, never exit 2.
    import voice_inject

    def _boom(*_a, **_k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(voice_inject.voice_prefs, "load", _boom)
    monkeypatch.setenv("HARNESS_HOOK_AUDIT_DISABLED", "1")
    voice_inject.run(raw="{}")
    out = capsys.readouterr().out
    assert "additionalContext" not in out
    assert "continue" in out


# ------------------------------------------------------------ rule presence ---

def test_rule_file_carries_artifact_voice_section():
    md = (_RULES / "terminal-voice.md").read_text(encoding="utf-8")
    assert "Terminal voice vs artifact voice" in md   # the carve-out subsection
    assert "journal" in md.lower()
    assert "critique" in md.lower()
    assert "Scope-fence" in md or "scope-fence" in md.lower()


def test_rule_file_has_floor_and_ladder():
    md = (_RULES / "terminal-voice.md").read_text(encoding="utf-8")
    assert "Universal-harm floor" in md
    assert "voice_level" in md
