#!/usr/bin/env python3
"""trace.py — append-only AUDIT trace (telemetry-class lib).

One JSONL line per event into state/trace/trace-YYYYMMDD.jsonl. The audit
ledger: skill calls, agent dispatches, hook runs, session starts. It NEVER
rotates or truncates — rotating usage counters live under state/telemetry/;
audit history must survive intact.

Record shape (RECORD_FIELDS): ts, actor, session, hook, event, tool, target,
status, exit, dur_ms, note, payload_hash. `event` is a free verb — new event
kinds (skill_call, subagent_dispatch, front_render) need no schema change.
`payload_hash` = sha256[:12] of tool_input: links the line to the op WITHOUT
storing content, so the mind→voice firewall holds even in the log.

Fail-open: tracing must never break the operation being traced.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))                 # scripts/ → paths
sys.path.insert(0, str(_HERE.parent / "hooks"))  # hooks/ → hook_runtime
import paths  # noqa: E402
import hook_runtime  # noqa: E402  — resolve_actor + fail-open crash log

HOOK_CLASS = "telemetry"

RECORD_FIELDS = (
    "ts", "actor", "session", "hook", "event", "tool", "target",
    "status", "exit", "dur_ms", "note", "payload_hash",
)


def _payload_hash(tool_input) -> "str | None":
    """sha256[:12] of tool_input, or None when not JSON-serializable. Returning
    None (vs letting json.dumps raise) lets the caller drop ONLY this field and
    still write the record — a hashing failure must never erase the event."""
    try:
        blob = json.dumps(tool_input, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def append_event(hook, event, *, actor=None, session=None, tool=None,
                 target=None, status=None, exit_code=None, dur_ms=None,
                 note=None, tool_input=None) -> None:
    """Append one audit event. Every record carries actor + ts. Swallows all
    errors — fail-open by class."""
    try:
        # One instant for ts AND the daily filename: two now() calls can
        # straddle UTC midnight and file a record under a date != its own ts.
        now = datetime.now(timezone.utc)
        rec = {
            "ts": now.isoformat(),
            "actor": actor if actor is not None
            else hook_runtime.resolve_actor(session_id=session),
            "session": session,
            "hook": hook,
            "event": event,
        }
        if tool is not None:
            rec["tool"] = tool
        if target is not None:
            rec["target"] = target
        if status is not None:
            rec["status"] = status
        if exit_code is not None:
            rec["exit"] = exit_code
        if dur_ms is not None:
            rec["dur_ms"] = dur_ms
        if note is not None:
            rec["note"] = note
        if tool_input is not None:
            _h = _payload_hash(tool_input)
            if _h is not None:
                rec["payload_hash"] = _h

        d = paths.trace_dir()
        d.mkdir(parents=True, exist_ok=True)
        fname = "trace-%s.jsonl" % now.strftime("%Y%m%d")
        with open(d / fname, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 — tracing never breaks the traced op
        hook_runtime.log_hook_error("trace", e)
