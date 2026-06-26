#!/usr/bin/env python3
"""setup_nudge.py — SessionStart onboarding advisory (telemetry-class, fail-open).

Two nudges, injected as additionalContext only when they actually apply:

1. RESTART reminder. Guard/stage posture is ENV-bound
   (HARNESS_GUARD_POLICY / HARNESS_STAGE_POLICY) on purpose: the pre-push hook
   scrubs HARNESS_* so a local override cannot weaken the real-push gate, which
   means a posture change only takes effect on a fresh session. When
   .claude/settings.json wires those env vars but THIS session's environment
   doesn't carry them (the session predates the edit), the running gate is using
   stale posture — tell the user to restart. Terminal voice is file-discovered
   (live, no restart) so it is deliberately NOT checked here.

2. SETUP reminder. An empty reviewer roster means the approval gate cannot
   function → point a fresh install at /hs:setup.

Telemetry-class: default ON, fail-open, never blocks. Emits NOTHING when there is
nothing to nudge — a configured, freshly-restarted session is silent. The emit
logic mirrors voice_inject (additionalContext on SessionStart); hook_runtime is
used read-only (stdin / enabled / continue / audit).
"""

import json
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(str(Path(__file__).resolve().parent.parent / "scripts"))
import hook_runtime  # noqa: E402

HOOK_CLASS = "telemetry"
_NAME = "setup_nudge"

# ENV-bound posture pointers whose change needs a session restart. Terminal voice
# (HARNESS_TERMINAL_VOICE) is intentionally absent — it is discovered live.
_POSTURE_ENV_KEYS = ("HARNESS_GUARD_POLICY", "HARNESS_STAGE_POLICY")


def _root() -> Path:
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("HARNESS_ROOT")
    return Path(raw).resolve() if raw else Path.cwd()


def _settings_env(root: Path) -> dict:
    """The `env` block of .claude/settings.json, or {} on any error (fail-open)."""
    try:
        p = root / ".claude" / "settings.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        env = raw.get("env") if isinstance(raw, dict) else None
        return env if isinstance(env, dict) else {}
    except Exception:  # noqa: BLE001 — a missing/broken settings file just means no nudge
        return {}


def stale_posture_keys(settings_env: dict, environ=None) -> list:
    """Posture env keys that settings.json defines but the running ``environ``
    does not match → the session predates the wiring. Pure + order-preserving."""
    env = os.environ if environ is None else environ
    stale = []
    for key in _POSTURE_ENV_KEYS:
        if key in settings_env and env.get(key) != settings_env[key]:
            stale.append(key)
    return stale


def roster_unset(root: Path) -> bool:
    """True when the reviewer roster is empty (the approval gate cannot work).
    Best-effort: an unreadable team.yaml → False (don't nudge on a state we
    cannot confirm)."""
    try:
        import team_config
        team_path = root / "harness" / "data" / "team.yaml"
        loaded = team_config.load_team(path=team_path if team_path.is_file() else None)
        return not loaded.get("reviewers")
    except Exception:  # noqa: BLE001 — cannot read roster → stay silent
        return False


def build_nudge(stale_keys, roster_unset: bool):
    """Assemble the additionalContext, or None when there is nothing to say."""
    parts = []
    if stale_keys:
        parts.append(
            "[harness setup] Guard/stage posture is env-bound (%s) and "
            ".claude/settings.json wires it, but THIS session's environment does "
            "not match — the gate is reading stale posture. RESTART the session "
            "(or open a new terminal) so the new guard/stage policy takes effect. "
            "(Terminal voice is live-discovered and needs no restart.)"
            % ", ".join(stale_keys))
    if roster_unset:
        parts.append(
            "[harness setup] The reviewer roster is empty, so the approval gate "
            "cannot pass a real review. Run /hs:setup to configure reviewers "
            "(and voice / guard / output language) for this project.")
    return "\n".join(parts) if parts else None


def core(data: dict):
    root = _root()
    return build_nudge(stale_posture_keys(_settings_env(root)), roster_unset(root))


def _emit_context(text: str) -> None:
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }))
    sys.stdout.flush()


def run(raw=None) -> None:
    """Telemetry-class + fail-open. Enabled → build + emit the nudge if any;
    disabled / nothing to nudge / any error → plain continue."""
    data = hook_runtime.read_stdin_json() if raw is None else hook_runtime._parse(raw)
    try:
        if hook_runtime.hook_enabled(_NAME, "telemetry"):
            text = core(data if isinstance(data, dict) else {})
            if text:
                _emit_context(text)
                return
    except Exception as e:  # noqa: BLE001 — a nudge must never break the session
        hook_runtime.log_hook_error(_NAME, e)
    hook_runtime.emit_continue()


def main(raw=None) -> None:
    run(raw=raw)


if __name__ == "__main__":
    main()
