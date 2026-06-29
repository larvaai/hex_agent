"""test_inject_prompt_context.py — UserPromptSubmit hook re-injecting the live
working context as additionalContext on every prompt.

CLAUDE.md is loaded once and drifts out of the working set over a long session;
this hook re-states the load-bearing conventions every turn (a deliberate
token-for-quality trade) and adds the DYNAMIC context a static file cannot: the
current git branch, the dated report/plan naming pattern, and the path layout.
Ported harness-native from ClaudeKit's context-builder — it must point at
harness/rules/, never at .claude/.

Telemetry-class + fail-open: advisory, never blocks. Disabled or any crash ->
plain continue (no context, exit 0). The hook is driven as a subprocess (the
real stdin/stdout contract); the build_context core is also exercised in-process.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_HOOKS))
sys.path.insert(0, str(_SCRIPTS))


def _env(tmp_path, **extra):
    env = dict(os.environ)
    env["HARNESS_STATE_DIR"] = str(tmp_path / "state")
    env["HARNESS_HOOK_LOG_DIR"] = str(tmp_path / "logs")
    env["HARNESS_HOOK_AUDIT_DISABLED"] = "1"
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("HARNESS_TELEMETRY_DISABLED", None)
    env.update(extra)
    return env


def _run(tmp_path, stdin_obj, **extra):
    return subprocess.run(
        [sys.executable, str(_HOOKS / "inject_prompt_context.py")],
        input=json.dumps(stdin_obj), capture_output=True, text=True,
        env=_env(tmp_path, **extra),
    )


def _ctx(proc):
    out = json.loads(proc.stdout)
    hs = out.get("hookSpecificOutput") or {}
    return hs.get("additionalContext", "")


def test_emits_user_prompt_submit_event(tmp_path):
    proc = _run(tmp_path, {"prompt": "do the thing"})
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert out["hookSpecificOutput"]["additionalContext"]


def test_all_sections_present(tmp_path):
    ctx = _ctx(_run(tmp_path, {"prompt": "x"}))
    for header in ("## Session", "## Rules", "Modularization",
                   "## Paths", "## Plan Context", "## Naming"):
        assert header in ctx, f"missing section: {header}"


def test_points_at_harness_rules_not_claude(tmp_path):
    ctx = _ctx(_run(tmp_path, {"prompt": "x"}))
    assert "harness/rules" in ctx
    assert ".claude/rules" not in ctx
    assert ".claude/skills" not in ctx


def test_rule_routing_index_lists_harness_rules(tmp_path):
    # subprocess runs from repo root -> harness/rules/ globs the real files
    ctx = _ctx(_run(tmp_path, {"prompt": "x"}))
    assert "## Rule routing (load on demand)" in ctx
    assert "harness-contract" in ctx
    assert "verification-mechanism" in ctx


def test_voice_register_folded_into_refresh(tmp_path):
    ctx = _ctx(_run(tmp_path, {"prompt": "x"}))
    assert "Terminal voice" in ctx
    assert "voice_level=" in ctx


def test_rules_content_carried(tmp_path):
    ctx = _ctx(_run(tmp_path, {"prompt": "x"}))
    assert "YAGNI" in ctx
    assert "DO NOT create markdown files outside" in ctx


def test_naming_pattern_is_dated(tmp_path):
    ctx = _ctx(_run(tmp_path, {"prompt": "x"}))
    assert "{slug}" in ctx
    assert "{type}" in ctx
    # YYMMDD-HHMM stamp injected live
    assert re.search(r"\d{6}-\d{4}", ctx), "no dated naming stamp"


def test_branch_line_present_in_repo(tmp_path):
    # subprocess inherits cwd = repo root -> git branch resolves
    ctx = _ctx(_run(tmp_path, {"prompt": "x"}))
    assert "- Branch:" in ctx


def test_fail_open_when_disabled(tmp_path):
    proc = _run(tmp_path, {"prompt": "x"}, HARNESS_TELEMETRY_DISABLED="1")
    assert proc.returncode == 0
    assert _ctx(proc) == ""


def test_never_exits_two_on_garbage_stdin(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(_HOOKS / "inject_prompt_context.py")],
        input="not json at all", capture_output=True, text=True,
        env=_env(tmp_path),
    )
    assert proc.returncode == 0


def test_build_context_core_is_pure():
    import inject_prompt_context as m
    text = m.build_context(Path("/tmp/some-repo-root"))
    assert "## Session" in text
    assert "/tmp/some-repo-root/plans" in text
    assert ".claude/" not in text


def test_plan_context_reports_none_when_no_plans(tmp_path):
    import inject_prompt_context as m
    text = m.build_context(tmp_path)
    assert "- Plan: none" in text


def test_plan_context_resolves_latest_plan_abs_path(tmp_path):
    import inject_prompt_context as m
    # two plan dirs; the most-recently-touched plan.md is the active one
    old = tmp_path / "plans" / "260101-0900-old-thing"
    new = tmp_path / "plans" / "260617-0018-current-thing"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (old / "plan.md").write_text("old", encoding="utf-8")
    plan = new / "plan.md"
    plan.write_text("current", encoding="utf-8")
    # make `new` strictly newer
    os.utime(old / "plan.md", (1_700_000_000, 1_700_000_000))
    os.utime(plan, (1_800_000_000, 1_800_000_000))

    text = m.build_context(tmp_path)
    assert "- Plan: %s" % plan in text
    assert "- Plan: none" not in text


# --- decay-aware cadence: pure decision ---------------------------------------

def test_decide_first_prompt_injects():
    import inject_prompt_context as m
    should, state = m.decide(None, "UserPromptSubmit")
    assert should is True
    assert state == {"turns": 0, "force": False, "sig": None}


def test_decide_throttles_right_after_injection():
    import inject_prompt_context as m
    should, state = m.decide({"turns": 0, "force": False}, "UserPromptSubmit")
    assert should is False
    assert state["turns"] == 1


def test_decide_reinjects_after_n_turns():
    import inject_prompt_context as m
    # turns just below N -> this prompt crosses the threshold
    should, state = m.decide({"turns": m._INJECT_EVERY_TURNS - 1, "force": False},
                             "UserPromptSubmit")
    assert should is True
    assert state == {"turns": 0, "force": False, "sig": None}


def test_decide_session_start_arms_next_prompt():
    import inject_prompt_context as m
    should, state = m.decide({"turns": 3, "force": False}, "SessionStart", "compact")
    assert should is False
    assert state == {"turns": 0, "force": True, "sig": None}
    # armed -> the following UserPromptSubmit injects
    should2, _ = m.decide(state, "UserPromptSubmit")
    assert should2 is True


def test_decide_reinjects_when_sig_changes():
    import inject_prompt_context as m
    # not armed, only one turn in, BUT the meaningful context changed (voice /
    # branch / plan) -> inject NOW, do not wait out the throttle.
    should, state = m.decide({"turns": 1, "force": False, "sig": "old"},
                             "UserPromptSubmit", current_sig="new")
    assert should is True
    assert state == {"turns": 0, "force": False, "sig": "new"}


def test_decide_throttles_when_sig_unchanged():
    import inject_prompt_context as m
    should, state = m.decide({"turns": 1, "force": False, "sig": "same"},
                             "UserPromptSubmit", current_sig="same")
    assert should is False
    assert state == {"turns": 2, "force": False, "sig": "same"}


# --- decay-aware cadence: end-to-end through the real state file --------------

def test_throttles_second_consecutive_prompt(tmp_path):
    p1 = _run(tmp_path, {"prompt": "a"})
    p2 = _run(tmp_path, {"prompt": "b"})   # shares HARNESS_STATE_DIR via tmp_path
    assert _ctx(p1)          # first prompt injects
    assert _ctx(p2) == ""    # immediately throttled


def test_compact_rearms_after_throttle(tmp_path):
    p1 = _run(tmp_path, {"prompt": "a"})                  # inject (consumes arm)
    p2 = _run(tmp_path, {"prompt": "b"})                  # throttled
    s = _run(tmp_path, {"hook_event_name": "SessionStart", "source": "compact"})
    p3 = _run(tmp_path, {"prompt": "c"})                  # re-armed by compact
    assert _ctx(p1)
    assert _ctx(p2) == ""
    assert _ctx(s) == ""      # SessionStart emits no context, only arms
    assert _ctx(p3)


def test_change_reinjects_before_throttle_window(tmp_path):
    # a mid-window config change (here: the terminal voice) must surface on the
    # NEXT prompt, not wait out the N-turn throttle. The env seam points voice at
    # a scratch file we mutate between prompts; branch/plan stay constant so the
    # sig changes ONLY because of the voice toggle.
    voice = tmp_path / "voice.yaml"
    voice.write_text("voice_level: 5\n", encoding="utf-8")
    env = {"HARNESS_TERMINAL_VOICE": str(voice)}
    p1 = _run(tmp_path, {"prompt": "a"}, **env)            # first prompt injects
    p2 = _run(tmp_path, {"prompt": "b"}, **env)            # immediately throttled
    voice.write_text("voice_level: 9\n", encoding="utf-8")  # toggle mid-window
    p3 = _run(tmp_path, {"prompt": "c"}, **env)            # sig changed -> inject
    assert _ctx(p1)
    assert _ctx(p2) == ""
    assert _ctx(p3)
    assert "voice_level=9" in _ctx(p3)


def test_team_section_surfaces_reviewers():
    # team-context merged into the injector (DRY: no separate hook). With a roster
    # present in this repo's team.yaml, the section names the reviewers so the agent
    # has governance awareness. Empty roster -> empty section (fail-open).
    import inject_prompt_context as ipc
    repo = Path(__file__).resolve().parents[2]
    sec = ipc._team_section(repo)
    assert isinstance(sec, list)
    assert any("review" in ln.lower() for ln in sec)
