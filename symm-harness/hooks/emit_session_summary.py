#!/usr/bin/env python3
"""emit_session_summary.py — on session Stop, roll up the audit trace into one
line at state/telemetry/sessions.jsonl (telemetry-class):
  {ts, session, events, skill_calls, subagents}.

Reads today's append-only trace and tallies this session's events. No transcript
scanning, no release/kit_digest (symm non-goals) — the trace IS the source of
truth, so the rollup just counts it. Summary lands in the rotating telemetry sink
(fine to lose); the audit trace it summarizes is the durable record.

Fail-open + non-blocking + config gate owned by hook_runtime.run_telemetry_hook.
Hook stdin: { session_id, transcript_path? }.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HOOKS_DIR, "..", "scripts"))
if _HOOKS_DIR not in sys.path:
    sys.path.append(_HOOKS_DIR)
import hook_runtime  # noqa: E402
import paths  # noqa: E402

HOOK_CLASS = "telemetry"
_STEM = Path(__file__).stem


def core(data: dict) -> None:
    session = data.get("session_id") or os.environ.get("SYMM_SESSION_ID") or ""
    now = datetime.now(timezone.utc)
    tally = {"events": 0, "skill_calls": 0, "subagents": 0}
    tf = paths.trace_dir() / ("trace-%s.jsonl" % now.strftime("%Y%m%d"))
    if tf.is_file():
        for line in tf.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if session and rec.get("session") != session:
                continue
            tally["events"] += 1
            ev = rec.get("event")
            if ev == "skill_call":
                tally["skill_calls"] += 1
            elif ev == "subagent_outcome":
                tally["subagents"] += 1

    d = paths.telemetry_dir()
    d.mkdir(parents=True, exist_ok=True)
    rec = {"ts": now.isoformat(), "session": session, **tally}
    with open(d / "sessions.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main(raw=None) -> None:
    hook_runtime.run_telemetry_hook(_STEM, core, raw=raw)


if __name__ == "__main__":
    main()
