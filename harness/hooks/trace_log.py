#!/usr/bin/env python3
"""trace_log.py — append-only AUDIT trace (telemetry-class lib).

One JSONL line per event into state/trace/trace-YYYYMMDD.jsonl. This is the
audit ledger: gate decisions, session starts, approvals, DEC writes.
It NEVER rotates or truncates — usage counters live in telemetry_paths and
rotate there; audit history must survive intact.

Schema (learned from CK hook-logger shape; written new):
  ts, actor, session, hook, event, tool, target, status, exit, dur_ms, note,
  payload_hash (sha256 12-hex of tool_input when given — payload itself is
  NOT stored: hash links the trace line to the op without leaking content).

Fail-open: tracing must never break the operation being traced.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import hook_runtime  # noqa: E402

HOOK_CLASS = "telemetry"


def _trace_dir() -> Path:
    return hook_runtime._state_dir() / "trace"


def _payload_hash(tool_input) -> "str | None":
    """sha256 (first 12 hex) of the tool_input, or None when it is not
    JSON-serializable. Returning None — instead of letting json.dumps raise —
    is what lets the caller drop ONLY this field and still write the audit
    record; a hashing failure must never erase the event itself."""
    try:
        blob = json.dumps(tool_input, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def append_event(hook, event, *, actor=None, session=None, tool=None,
                 target=None, status=None, exit_code=None, dur_ms=None,
                 note=None, tool_input=None) -> None:
    """Append one audit event. Every record carries actor + ts.
    Swallows all errors — fail-open by class."""
    try:
        # One instant for both ts and the daily filename — two separate now()
        # calls can straddle UTC midnight and file a record under a date that
        # disagrees with its own ts.
        now = datetime.now(timezone.utc)
        rec = {
            "ts": now.isoformat(),
            "actor": actor if actor is not None else hook_runtime.resolve_actor(
                session_id=session),
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

        d = _trace_dir()
        d.mkdir(parents=True, exist_ok=True)
        fname = "trace-%s.jsonl" % now.strftime("%Y%m%d")
        with open(d / fname, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 — tracing never breaks the traced op
        hook_runtime.log_hook_error("trace_log", e)
