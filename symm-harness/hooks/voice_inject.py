#!/usr/bin/env python3
"""voice_inject.py — SessionStart hook (telemetry-class) injecting the resolved
symm-harness voice knobs as additionalContext (S3).

Reads data/voice.yaml (voice_resolve.load) and emits a short additionalContext
that POINTS at rules/psych-front.md, states the active knob values, and restates
the two non-negotiables (universal-harm floor + scope-fence). It does NOT restate
the whole doctrine — psych-front.md is the home (DRY).

Advisory only (telemetry contract): never blocks. On any error or when telemetry
is disabled it emits no context — a broken voice hook degrades to "natural voice",
never to a blocked session. Ported/trimmed from harness/hooks/voice_inject.py:
no output_style axis, no interview-rigor triad — symm's S2 front already covers
"don't overwhelm".
"""

import json
import os
import sys
from pathlib import Path

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HOOKS_DIR, "..", "scripts"))
if _HOOKS_DIR not in sys.path:
    sys.path.append(_HOOKS_DIR)
import hook_runtime  # noqa: E402
import voice_resolve  # noqa: E402

HOOK_CLASS = "telemetry"

_RULE = "symm-harness/rules/psych-front.md"

_REGISTER = {
    "soft": "warm, cushioned; soften hard news",
    "blunt": "direct, no cushioning, NO profanity",
    "off": "neutral, no register shaping",
}
_DEPTH = {
    1: "answer + one-line why",
    2: "answer + brief reasoning",
    3: "answer + reasoning sketch",
}


def build_context(prefs: dict) -> str:
    reg = prefs["register"]
    depth = prefs["explanation_depth"]
    persona = prefs["persona"]
    lines = [
        "[symm-harness voice — active session settings]",
        "Authority: %s (front-stage doctrine + scope-fence). Applies to "
        "voice:render's USER-FACING prose ONLY." % _RULE,
        "register=%s — %s." % (reg, _REGISTER.get(reg, _REGISTER["off"])),
        "explanation_depth=%d/3 — %s." % (depth, _DEPTH.get(depth, _DEPTH[2])),
    ]
    if persona and persona != "none":
        lines.append(
            "persona=%s — adopt this surface FORM; register sets the directness "
            "inside it." % persona)
    else:
        lines.append("persona=none — natural voice.")
    if prefs["no_markdown"]:
        lines.append("no_markdown=true — plain prose, no markdown formatting.")
    lines.append(
        "Universal-harm floor (non-removable, every register): venom may aim at "
        "the WORK, never at WHO the user is — no slurs, threats, sexual content, "
        "self-harm, or identity-targeted attacks.")
    lines.append(
        "Scope-fence: these knobs change NOTHING in conclusion.json substance — no "
        "number, ID, file:line anchor, quote, or the verdict moves. Wording and "
        "register only.")
    return "\n".join(lines)


def core(data: dict) -> str:
    return build_context(voice_resolve.load())


def _emit_context(text: str) -> None:
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }))
    sys.stdout.flush()


def run(raw=None) -> None:
    """Telemetry-class + fail-open injector. Enabled → build + emit; disabled or
    any exception → plain continue (no context). Never raises, never exits 2."""
    data = hook_runtime.read_stdin_json() if raw is None else hook_runtime._parse(raw)
    try:
        if hook_runtime.hook_enabled("voice_inject", "telemetry"):
            text = core(data)
            if text:
                _emit_context(text)
                return
    except Exception as e:  # noqa: BLE001 — injection must never break the session
        hook_runtime.log_hook_error("voice_inject", e)
    hook_runtime.emit_continue()


def main(raw=None) -> None:
    run(raw=raw)


if __name__ == "__main__":
    main()
