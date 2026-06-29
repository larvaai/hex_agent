#!/usr/bin/env python3
"""nudge_context_inject.py — UserPromptSubmit hook (telemetry-class) re-surfacing
the latest decision-capture observation as additionalContext.

decision_capture_nudge records a `decision_capture_observation` audit event at
turn-end when a session shipped a decision-shaped change without the decision
ledger moving — but it only writes to stderr + the trace, which the model never
re-reads. This hook closes that loop: at a later UserPromptSubmit it reads the
latest same-session observation and injects a one-line additionalContext pointing
at /hs-mem:remember.

Single-shot per observation: each observation is surfaced ONCE (a per-session
marker records the last surfaced ts), so it does not re-nag on every subsequent
prompt. A NEWER observation supersedes the marker and surfaces again.

INTERACTIVE-ONLY by construction. The AFK loop drives `claude -p`
(afk/loop_controller.py), which never fires UserPromptSubmit, so this inject is
inert in an autonomous run — autonomous decision-capture is the bell counter's
job, not this hook's. The docstring/label says so on purpose: this is NOT a
"semi-auto" capture for unattended loops.

Advisory only (telemetry contract): it never blocks. On any error — or when
telemetry is disabled, or no fresh observation exists — it emits no context
(fail-open: a broken inject degrades to "no reminder", never to a blocked
session).
"""

import json
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import hook_runtime  # noqa: E402

HOOK_CLASS = "telemetry"
NAME = "nudge_context_inject"
_EVENT = "decision_capture_observation"
_STATE_SUBDIR = "nudge-inject"


def _trace_dir() -> Path:
    return hook_runtime._state_dir() / "trace"


def latest_observation(session_id, trace_dir=None):
    """The newest decision_capture_observation for `session_id`, or None.

    Scans trace files newest-first (date-named, so filename order is chronological);
    within a file the last matching line wins (append-only). Filters by session so
    a prior run's observation never leaks into a fresh session. Never raises — a
    missing dir or any read/parse error yields None (fail-open)."""
    if not session_id:
        return None
    try:
        d = Path(trace_dir) if trace_dir is not None else _trace_dir()
        if not d.is_dir():
            return None
        for f in sorted(d.glob("trace-*.jsonl"), reverse=True):
            best = None
            try:
                lines = f.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("event") == _EVENT and rec.get("session") == session_id:
                    best = rec  # later line = newer (append-only)
            if best is not None:
                return best
        return None
    except Exception:  # noqa: BLE001 — inject must never break the prompt
        return None


def _safe_id(session_id) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_"
                   for c in (session_id or "_"))


def _marker_path(session_id) -> Path:
    return hook_runtime._state_dir() / _STATE_SUBDIR / ("%s.txt" % _safe_id(session_id))


def _already_surfaced(session_id, ts) -> bool:
    """True if an observation at-or-before `ts` was already surfaced this session
    (single-shot: do not re-nag the same observation). Fail-open: no marker / a
    read error yields False, i.e. surface rather than suppress. ISO-8601 ts strings
    compare lexicographically in chronological order (same format + offset)."""
    if not ts:
        return False
    try:
        p = _marker_path(session_id)
        if not p.is_file():
            return False
        return p.read_text(encoding="utf-8").strip() >= ts
    except OSError:
        return False


def _mark_surfaced(session_id, ts) -> None:
    """Record `ts` as the last surfaced observation. Best-effort; a write error
    never breaks the prompt (worst case: the next prompt re-surfaces once)."""
    try:
        p = _marker_path(session_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(ts or "", encoding="utf-8")
    except OSError:
        pass


def _subjects(note: str) -> str:
    """The subject portion of an observation note ("unrecorded_decision×N — a, b"
    -> "a, b"); the whole note if it carries no separator."""
    if not note:
        return ""
    if "—" in note:
        return note.split("—", 1)[1].strip()
    return note.strip()


def build_context(observation) -> str:
    """One-line additionalContext: name the unrecorded change(s) and point at the
    capture path. Advisory, interactive-only."""
    subjects = _subjects((observation or {}).get("note", ""))
    detail = (": %s" % subjects) if subjects else ""
    return ("[decision-capture] An earlier turn this session shipped "
            "decision-shaped change(s) not yet in the ledger%s. Run /hs-mem:remember "
            "to draft a DEC/memory, or record it by hand. Advisory; interactive "
            "sessions only." % detail)


def core(data):
    """The additionalContext to inject, or None. Single-shot: surfaces an
    observation only once per session (newer observations supersede)."""
    session_id = (data or {}).get("session_id") or ""
    obs = latest_observation(session_id)
    if obs is None:
        return None
    ts = obs.get("ts") or ""
    if _already_surfaced(session_id, ts):
        return None
    _mark_surfaced(session_id, ts)
    return build_context(obs)


def _emit_context(text: str) -> None:
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text,
        }
    }))
    sys.stdout.flush()


def run(raw=None) -> None:
    """Telemetry-class, fail-open. Enabled + a fresh observation exists -> inject;
    disabled / no observation / any error -> plain continue. Never exits 2."""
    data = hook_runtime.read_stdin_json() if raw is None else hook_runtime._parse(raw)
    try:
        if hook_runtime.hook_enabled(NAME, HOOK_CLASS):
            text = core(data)
            if text:
                _emit_context(text)
                return
    except Exception as e:  # noqa: BLE001 — injection must never break the session
        hook_runtime.log_hook_error(NAME, e)
    hook_runtime.emit_continue()


def main(raw=None) -> None:
    run(raw=raw)


if __name__ == "__main__":
    main()
