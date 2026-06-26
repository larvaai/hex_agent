#!/usr/bin/env python3
"""voice_inject.py — SessionStart hook (telemetry-class) injecting the resolved
terminal-voice guidance as additionalContext.

The harness had no model-context injection before this: session_init.py only
caches the actor and continues. This is that new plumbing, kept SEPARATE from
session_init (single responsibility, fail-open). It reads the resolved
terminal-voice knobs (voice_prefs.load) and emits a short additionalContext that
POINTS at harness/rules/terminal-voice.md and states the active knob values, so
the voice / coding-level guidance is live for the whole session (and re-fires on
/compact, source=compact — the right cadence for a persistent register).

Advisory only: it never blocks (telemetry contract). On any error — or when
telemetry is disabled — it emits no context (fail-open: a broken voice hook
degrades to "natural voice", never to a blocked session). The emit logic lives
here rather than in the shared hook_runtime so the protected runtime stays
untouched; hook_runtime is used read-only (stdin / enabled / continue / audit).
"""

import json
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(str(Path(__file__).resolve().parent.parent / "scripts"))
import hook_runtime  # noqa: E402
import voice_prefs    # noqa: E402

HOOK_CLASS = "telemetry"

_RULE = "harness/rules/terminal-voice.md"


def _register(level: int) -> str:
    """One-line terminal register descriptor for a voice_level (work-aimed)."""
    if level <= 2:
        return "polite, measured; soften hard news"
    if level <= 4:
        return "direct but courteous"
    if level == 5:
        return "blunt and direct, NO profanity (the default)"
    if level == 6:
        return "sharper - name a bad idea as bad, no hedging"
    if level == 7:
        return "roast the work; vi address form ong/toi or ba/toi"
    if level == 8:
        return "harsher; vi pronouns may/tao permitted"
    return "maximum bluntness; work-aimed profanity permitted (vi: đm/vl-tier)"


def _depth(level: int) -> str:
    return {
        0: "answer only, no explanation",
        1: "answer + one-line why",
        2: "brief reasoning",
        3: "reasoning + key trade-offs",
        4: "thorough reasoning",
        5: "full reasoning, context, and alternatives (the default)",
    }.get(level, "full reasoning, context, and alternatives (the default)")


def build_context(prefs: dict) -> str:
    """The additionalContext string: a POINTER at the rule file + the resolved
    knob values + the two non-negotiables (floor + scope-fence). Deliberately
    NOT a restatement of the whole rule (DRY — terminal-voice.md is the home)."""
    cl = prefs["terminal_voice_level"]
    vl = prefs["voice_level"]
    persona = prefs["persona"]
    no_md = prefs["no_markdown"]
    lines = [
        "[Terminal voice - active session settings]",
        "Authority: %s (the harshness ladder, the universal-harm floor, the "
        "scope-fence, the persona catalog). Apply these to TERMINAL "
        "conversational prose ONLY." % _RULE,
        "voice_level=%d/9 - register: %s." % (vl, _register(vl)),
        "terminal_voice_level=%d/5 - explanation depth: %s." % (cl, _depth(cl)),
    ]
    if persona and persona != "none":
        lines.append(
            "persona=%s - adopt this surface form (catalog in %s); persona sets "
            "the FORM, voice_level sets the harshness inside it." % (persona, _RULE))
    else:
        lines.append("persona=none - natural harness voice.")
    if no_md:
        lines.append(
            "no_markdown=true - answer in plain prose, no markdown formatting.")
    lines.append(
        "Interview rigor (hs:plan / hs-research:discover / hs-think:brainstorm): "
        "interview_rigor=%s (depth of challenge / gap-probing), "
        "action_prompting=%s (density of next-step suggestions), "
        "detail_level=%s (interview/turn verbosity - NOT report length)."
        % (prefs["interview_rigor"], prefs["action_prompting"], prefs["detail_level"]))
    lines.append(
        "Universal-harm floor (NON-removable, holds at every level incl. 9): venom "
        "aimed at the WORK is allowed; anything aimed at WHO the user is - slurs, "
        "threats, sexual content, self-harm, family- or identity-targeted attacks "
        "- is OUT at every level.")
    lines.append(
        "Scope-fence: these knobs change NOTHING in code, generated docs/reports, "
        "commits, evidence (file:line / IDs / SHAs / quotes), or any gate decision; "
        "and they do NOT control an artifact's own designed voice - the "
        "journal-writer keeps its brutal candor and the hs-think:critique report keeps "
        "its neutral tone at every voice_level.")
    osl = prefs.get("output_style")
    prof = voice_prefs.output_style_profile(osl)
    if prof:
        lines.append("[Output style - adapts the DELIVERABLE, NOT scope-fenced]")
        lines.append(
            "output_style=%d/5 (%s): shape prose AND code for this reader - %s. This axis is "
            "the deliberate EXCEPTION to the scope-fence above - it DOES change generated "
            "code/output (comment density, verbosity, examples, analogies). Full profile: %s."
            % (prof["level"], prof["name"], prof["essence"],
               "harness/data/output-styles/coding-level-%d-%s.md" % (prof["level"], prof["name"])))
    return "\n".join(lines)


def core(data: dict):
    return build_context(voice_prefs.load())


def _emit_context(text: str) -> None:
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }))
    sys.stdout.flush()


def run(raw=None) -> None:
    """Telemetry-class + fail-open context injector. Enabled -> build + emit the
    additionalContext; disabled or any exception -> plain continue (no context).
    Never raises, never exits 2."""
    data = hook_runtime.read_stdin_json() if raw is None else hook_runtime._parse(raw)
    try:
        if hook_runtime.hook_enabled("voice_inject", "telemetry"):
            text = core(data)
            if text:
                _emit_context(text)
                return
    except Exception as e:  # noqa: BLE001 - injection must never break the session
        hook_runtime.log_hook_error("voice_inject", e)
    hook_runtime.emit_continue()


def main(raw=None) -> None:
    run(raw=raw)


if __name__ == "__main__":
    main()
