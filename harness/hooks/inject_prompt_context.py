#!/usr/bin/env python3
"""inject_prompt_context.py — context re-injection hook (telemetry-class).

CLAUDE.md is loaded near the top of each context window; within a long window it
drifts up and out of the model's working attention, and its conventions get
forgotten. This hook re-states the load-bearing rules on a decay-aware cadence —
NOT every prompt (that re-states freshly-loaded rules for no gain), but on the
two moments the working context actually goes stale:

  - SessionStart (startup / resume / clear / compact): arm a re-inject for the
    next prompt — the window just turned over, dynamic context (branch, active
    plan, paths) should be re-surfaced.
  - UserPromptSubmit: re-inject every N turns within a window, so a long stretch
    refreshes the rules before CLAUDE.md has drifted too far up.

Beyond the static rules it carries the DYNAMIC context a fixed file cannot: the
current git branch, the active plan's absolute path, and the dated report/plan
naming pattern (absolute paths so a deep CWD never spawns a stray plans/ subtree).

Ported harness-native from the upstream dev-rules-reminder + context-builder
(MIT). Rebranded on port: points at the harness rule layer (`harness/rules/`,
routed from CLAUDE.md), never `.claude/`. The upstream throttled on a 5-minute
wall-clock TTL; this uses a turns + session-boundary signal instead (decay
tracks context growth, not elapsed time). The active-plan path is salvaged from
the upstream cook-after-plan-reminder.

Telemetry-class + fail-open: advisory only, it NEVER blocks. Disabled, any
exception, or malformed stdin -> a plain continue (a broken context hook
degrades to "no reminder", never to a blocked prompt). Never raises, never
exits 2. Mirrors voice_inject's emit plumbing.
"""

import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(str(Path(__file__).resolve().parent.parent / "scripts"))
import hook_runtime   # noqa: E402
import harness_paths  # noqa: E402

HOOK_CLASS = "telemetry"

_RULES = "harness/rules/"
_DOCS_MAXLOC = 800

# Within a single context window, re-surface the rules roughly every N prompts.
# A session boundary (SessionStart, any source) always arms the next prompt.
_INJECT_EVERY_TURNS = 5
_STATE_NAME = "prompt-context.json"


# --- decay-aware cadence (pure decision + tiny transient state) ---------------

def decide(scope_state, event, source=None, current_sig=None):
    """Pure: given this scope's prior state + the firing event (+ the current
    context fingerprint), return (should_inject, new_scope_state).

    SessionStart of any source arms a re-inject (force) for the next prompt and
    emits nothing itself. UserPromptSubmit injects when (a) armed, (b) the
    meaningful context changed since the last injection (current_sig differs
    from the stored sig — a just-toggled voice/branch/plan shows up immediately,
    not N turns later), or (c) N prompts have elapsed since the last injection;
    otherwise it counts and stays quiet. An unseen scope defaults to armed, so a
    mid-session install still injects on its first prompt."""
    st = dict(scope_state or {})
    if event == "SessionStart":
        return (False, {"turns": 0, "force": True, "sig": current_sig})
    turns = int(st.get("turns", 0)) + 1
    armed = bool(st.get("force", True))
    changed = current_sig is not None and st.get("sig") != current_sig
    if armed or changed or turns >= _INJECT_EVERY_TURNS:
        return (True, {"turns": 0, "force": False, "sig": current_sig})
    return (False, {"turns": turns, "force": False, "sig": st.get("sig")})


def _state_path() -> Path:
    return harness_paths.state_dir() / _STATE_NAME


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 - missing/corrupt state -> empty (fail-open)
        return {}


def _save_state(state: dict) -> None:
    try:
        p = _state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state), encoding="utf-8")
    except Exception:  # noqa: BLE001 - state is best-effort coordination
        pass


# --- context builders ---------------------------------------------------------

def _git_branch(root: Path):
    """Current branch name, or None when git is absent / detached / errors."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            name = out.stdout.strip()
            return name or None
    except Exception:  # noqa: BLE001 - branch is best-effort context
        pass
    return None


def _naming_stamp() -> str:
    """YYMMDD-HHMM stamp for report/plan naming, matching the repo convention."""
    return datetime.now().strftime("%y%m%d-%H%M")


def _rule_routing_section(root: Path) -> list:
    """The load-on-demand INDEX, kept fresh so the agent never forgets which
    rules exist or that they must be loaded before the matching task. Globbed
    live from harness/rules/ — never a hand-maintained copy, so it cannot drift
    from the actual rule layer (the per-rule 'when' detail stays in CLAUDE.md)."""
    try:
        names = sorted(p.stem for p in (Path(root) / "harness" / "rules").glob("*.md"))
    except Exception:  # noqa: BLE001 - routing index is best-effort context
        names = []
    if not names:
        return []
    return [
        "## Rule routing (load on demand)",
        "Available in harness/rules/ — load the relevant one BEFORE the matching "
        "task (full 'when' mapping in CLAUDE.md): " + ", ".join(names),
        "",
    ]


def _voice_section() -> list:
    """Re-state the active terminal-voice register on the refresh cadence too.
    Reuses voice_inject's builder (single source of the voice text — no copy);
    voice_inject still owns the SessionStart immediacy. Folded here so the voice
    does not soften over a long window the way SessionStart-only injection lets
    it. Best-effort: a voice import/read failure just drops this section."""
    try:
        import voice_inject  # noqa: E402
        import voice_prefs    # noqa: E402
        text = voice_inject.build_context(voice_prefs.load())
        return ["", text] if text else []
    except Exception:  # noqa: BLE001 - voice refresh is best-effort context
        return []


def _active_plan(root: Path):
    """Absolute path of the most-recently-touched plans/<slug>/plan.md, or None.

    Salvaged from the upstream cook-after-plan-reminder: surfacing the plan path
    is the one durable bit of value (a fresh session after /clear can find where
    work lives). Mtime is the cheap proxy for 'active' — good enough, and far
    better than the static 'none' a file cannot keep current."""
    try:
        candidates = list((Path(root) / "plans").glob("*/plan.md"))
        if not candidates:
            return None
        return str(max(candidates, key=lambda p: p.stat().st_mtime))
    except Exception:  # noqa: BLE001 - plan lookup is best-effort context
        return None


def _context_sig(root: Path) -> str:
    """A stable fingerprint of the MEANINGFUL injected inputs — the active voice
    register, the git branch, and the active-plan path — so a mid-window change
    to any of them forces a re-inject on the NEXT prompt instead of waiting out
    the turn throttle (the whole point: a knob you just toggled shows up now).

    Deliberately EXCLUDES the naming timestamp and the session clock: the stamp
    ticks every minute, so fingerprinting the rendered block would make the sig
    change every minute and defeat the throttle entirely. Only user-meaningful
    state belongs here. Best-effort: any read failure degrades to a constant
    part, never raises."""
    parts = []
    try:
        import voice_prefs  # noqa: E402
        v = voice_prefs.load()
        parts.append("v=%s/%s/%s/%s/%s/%s/%s" % (
            v.get("voice_level"), v.get("persona"), v.get("terminal_voice_level"),
            v.get("no_markdown"), v.get("interview_rigor"),
            v.get("action_prompting"), v.get("detail_level")))
    except Exception:  # noqa: BLE001 - voice part is best-effort
        parts.append("v=?")
    parts.append("b=%s" % (_git_branch(root) or ""))
    parts.append("p=%s" % (_active_plan(root) or ""))
    return "|".join(parts)


def _session_section() -> list:
    return [
        "## Session",
        "- DateTime: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "- CWD: %s" % os.getcwd(),
        "- Timezone: %s" % (time.tzname[0] if time.tzname else "unknown"),
        "- OS: %s" % platform.system().lower(),
        "- User: %s" % (os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"),
        "- Locale: %s" % os.environ.get("LANG", ""),
        "- Spawning multiple subagents can cause performance issues; delegate only "
        "when the current user request authorizes subagent or parallel work.",
        "- Each subagent has its own context window; keep prompts scoped. Advisory "
        "subagents report findings and do not mutate plan/code unless tasked.",
        "- IMPORTANT: Include relevant environment information when prompting subagents.",
        "",
    ]


def _rules_section() -> list:
    return [
        "## Rules",
        '- Follow the harness rule layer in "%s" (load on demand; routing in CLAUDE.md).' % _RULES,
        '- Markdown files are organized in: Plans -> "{root}/plans" directory, '
        'Docs -> "{root}/docs" directory',
        '- **IMPORTANT:** DO NOT create markdown files outside of "{root}/plans" or '
        '"{root}/docs" UNLESS the user explicitly requests it.',
        "- When skills' scripts fail, report the failure unless the current task "
        "explicitly authorizes fixing skill code; only then fix and rerun.",
        "- Follow **YAGNI (You Aren't Gonna Need It) - KISS (Keep It Simple, Stupid) "
        "- DRY (Don't Repeat Yourself)** principles",
        "- Sacrifice grammar for the sake of concision when writing reports.",
        "- In reports, list any unresolved questions at the end, if any.",
        "- IMPORTANT: Ensure token consumption efficiency while maintaining high quality.",
        "",
    ]


def _modularization_section() -> list:
    return [
        "## **[IMPORTANT] Consider Modularization:**",
        "- Check existing modules before creating new",
        "- Analyze logical separation boundaries (functions, classes, concerns)",
        "- Prefer kebab-case for JS/TS/shell; respect language conventions "
        "(Python/Go/Rust use snake_case, C#/Java use PascalCase)",
        "- Write descriptive code comments",
        "- After modularization, continue with the main task only when the current "
        "request authorizes implementation; advisory/report-only tasks report the recommendation.",
        "- When not to modularize: Markdown files, plain text files, bash scripts, "
        "configuration files, environment variables files, etc.",
        "",
    ]


def _paths_section(plans: str, docs: str, reports: str) -> list:
    return [
        "## Paths",
        "Reports: %s | Plans: %s/ | Docs: %s/ | docs.maxLoc: %d"
        % (reports, plans, docs, _DOCS_MAXLOC),
        "",
    ]


def _plan_context_section(reports: str, branch, plan) -> list:
    lines = [
        "## Plan Context",
        "- Plan: %s" % (plan if plan else "none"),
        "- Reports: %s" % reports,
    ]
    if branch:
        lines.append("- Branch: %s" % branch)
    lines.append("")
    return lines


def _naming_section(plans: str, reports: str, stamp: str) -> list:
    return [
        "## Naming",
        "- Report: `%s{type}-%s-{slug}-report.md`" % (reports, stamp),
        "- Plan dir: `%s/%s-{slug}/`" % (plans, stamp),
        "- Replace `{type}` with: descriptive kebab-case purpose, agent handoff, "
        "or workflow context",
        "- Avoid generic report names like `review.md`, `report.md`, or `notes.md`",
        "- Replace `{slug}` with: descriptive-kebab-slug",
    ]


def _team_section(root) -> list:
    """Governance context (merged here instead of a separate hook): the review roster
    that approves hard stages. Reads the tracked team.yaml; an empty or absent roster
    yields no section (fail-open)."""
    try:
        import team_config
        reviewers = team_config.load_team().get("reviewers") or []
    except Exception:
        return []
    if not reviewers:
        return []
    names = ", ".join(str(r).split(":", 1)[-1] for r in reviewers[:5])
    return ["", "## Team", "- Reviewers (approve push/pr/ship): %s" % names]


def build_context(root: Path) -> str:
    """The additionalContext string. PURE given a root (the only I/O is the
    best-effort git-branch + active-plan lookups). Absolute paths anchor every
    reference at the repo root so a deep CWD cannot mislead file placement."""
    root = Path(root)
    plans = str(root / "plans")
    docs = str(root / "docs")
    reports = str(root / "plans" / "reports") + os.sep
    branch = _git_branch(root)
    stamp = _naming_stamp()
    plan = _active_plan(root)

    lines = []
    lines += _session_section()
    lines += [ln.replace("{root}", str(root)) for ln in _rules_section()]
    lines += _rule_routing_section(root)
    lines += _modularization_section()
    lines += _paths_section(plans, docs, reports)
    lines += _plan_context_section(reports, branch, plan)
    lines += _team_section(root)
    lines += _naming_section(plans, reports, stamp)
    lines += _voice_section()
    return "\n".join(lines)


def core(data: dict) -> str:
    return build_context(harness_paths.root())


def _emit_context(text: str) -> None:
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text,
        }
    }))
    sys.stdout.flush()


def run(raw=None) -> None:
    """Telemetry-class + fail-open. Updates the per-cwd cadence state, then emits
    the context block only when the decay signal says to; otherwise a plain
    continue. Disabled or any exception -> plain continue. Never exits 2."""
    data = hook_runtime.read_stdin_json() if raw is None else hook_runtime._parse(raw)
    try:
        if hook_runtime.hook_enabled("inject_prompt_context", "telemetry"):
            event = data.get("hook_event_name") or "UserPromptSubmit"
            scope = data.get("cwd") or os.getcwd()
            state = _load_state()
            current_sig = _context_sig(harness_paths.root())
            should, new_scope = decide(state.get(scope), event, data.get("source"), current_sig)
            state[scope] = new_scope
            _save_state(state)
            if should:
                text = core(data)
                if text:
                    _emit_context(text)
                    return
    except Exception as e:  # noqa: BLE001 - injection must never break the session
        hook_runtime.log_hook_error("inject_prompt_context", e)
    hook_runtime.emit_continue()


def main(raw=None) -> None:
    run(raw=raw)


if __name__ == "__main__":
    main()
