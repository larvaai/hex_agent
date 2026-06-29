#!/usr/bin/env python3
"""subagent_init.py — SubagentStart context injector (telemetry, fail-open).

When a subagent is spawned, inject a concise pointer at the harness rule layer, the
standards tree, and an ownership reminder — so a delegated subagent stays inside harness
conventions even when the orchestrator's prompt is terse. This complements (does not
replace) the orchestration-protocol requirement that every delegation prompt carry its
own context; it is the belt to that suspenders.

Posture: telemetry, fail-OPEN — emits at most an additionalContext string and ALWAYS
exits 0. Disabled or any exception → no context, never a blocked subagent.
"""
import json
import os
import sys

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (_HOOKS_DIR, os.path.join(_HOOKS_DIR, "..", "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

HOOK_CLASS = "telemetry"
_HOOK = "subagent_init"


def context_text(payload) -> str:
    """The additionalContext injected into the subagent. Pure; never raises."""
    agent = "subagent"
    try:
        agent = (payload or {}).get("agent_type") or "subagent"
    except Exception:
        pass
    return (
        "[Harness subagent: %s] You are running inside a file-based SDLC harness. "
        "Follow the shared rule layer in harness/rules/ (load on demand; routing in "
        "CLAUDE.md) and the standards in harness/standards/. Stay within your delegated "
        "file ownership and acceptance criteria — report findings rather than mutating "
        "outside your scope unless explicitly tasked. Generated reports follow "
        "harness/data/output.yaml." % agent
    )


def _emit(text: str) -> None:
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": text,
        }
    }))
    sys.stdout.write("\n")


def main() -> None:
    try:
        import hook_runtime
        if not hook_runtime.hook_enabled(_HOOK, HOOK_CLASS):
            sys.exit(0)
        payload = hook_runtime.read_stdin_json()
        _emit(context_text(payload))
    except Exception:
        # fail-open: a broken injector degrades to no context, never blocks a subagent
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
