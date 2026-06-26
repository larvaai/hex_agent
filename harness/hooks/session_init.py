#!/usr/bin/env python3
"""session_init.py — SessionStart hook (telemetry-class).

Resolves the acting identity once per session and caches it in
state/sessions/<session_id>.json so later hooks in the same session resolve
the SAME actor through resolve_actor(session_id=...) instead of re-reading a
possibly-changed environment. The cache is an optimization, never a
prerequisite: hooks fall back to the env chain when this never ran.

Emits a session_start audit event.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import hook_runtime  # noqa: E402
import trace_log     # noqa: E402

HOOK_CLASS = "telemetry"

# HARNESS_* vars that are normal plumbing (identity, test seams for state &
# log placement), not posture overrides worth an audit event.
_BASELINE_ENV = frozenset({
    "HARNESS_USER", "HARNESS_AGENT", "HARNESS_STATE_DIR",
    "HARNESS_HOOK_LOG_DIR", "HARNESS_ROOT",
})


def _override_names() -> list:
    """Names (never values — values can carry paths/secrets; the audit
    question is only WHICH knobs were set) of HARNESS_* posture overrides
    present at session start. Snapshot semantics: an override exported
    mid-session is not seen — this is start-of-session visibility, not
    continuous monitoring."""
    return sorted(k for k in os.environ
                  if k.startswith("HARNESS_") and k not in _BASELINE_ENV)


def core(data: dict) -> None:
    session_id = data.get("session_id")
    actor = hook_runtime.resolve_actor()  # env chain — this IS the cache fill
    if session_id:
        d = hook_runtime._state_dir() / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        (d / ("%s.json" % session_id)).write_text(
            json.dumps({
                "actor": actor,
                "ts": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    trace_log.append_event(hook="session_init", event="session_start",
                           actor=actor, session=session_id)
    overrides = _override_names()
    if overrides:
        # Audit-class posture data → trace (never rotates); telemetry's 8MB
        # rotation would eventually erase the evidence.
        trace_log.append_event(hook="session_init", event="env_override_seen",
                               actor=actor, session=session_id,
                               note=", ".join(overrides))


def main(raw=None) -> None:
    hook_runtime.run_telemetry_hook("session_init", core, raw=raw)


if __name__ == "__main__":
    main()
