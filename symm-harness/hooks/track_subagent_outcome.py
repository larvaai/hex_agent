#!/usr/bin/env python3
"""track_subagent_outcome.py — SubagentStop hook (telemetry-class).

One trace line per finished reasoning sub-agent (deep-reasoner / consolidator):
  event=subagent_outcome, target=<agent_type>, status=<outcome>, note=<transcript>.

This is the honest S4 unit — every agent dispatch shows up here at completion
with its identity and transcript path. Intra-agent reasoning steps are NOT
line-logged (and must not be — that is the firewall): the transcript path is the
replay handle if the chain is ever needed.

Simplified from harness/hooks/track_subagent_outcome.py: dropped the
subagent_classify transcript-tail inference (the read-time lens framework is a
symm non-goal). outcome = explicit payload enum, else "unknown" — NEVER fabricate
success when the signal is absent.

Fail-open + non-blocking + config gate owned by hook_runtime.run_telemetry_hook.
Hook stdin: { session_id, agent_type|subagent_type, outcome?,
agent_transcript_path?, transcript_path?, agent_id? }.
"""

import os
import sys
from pathlib import Path

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HOOKS_DIR, "..", "scripts"))
if _HOOKS_DIR not in sys.path:
    sys.path.append(_HOOKS_DIR)
import hook_runtime  # noqa: E402
import trace  # noqa: E402

HOOK_CLASS = "telemetry"
_STEM = Path(__file__).stem

_OUTCOMES = {"success", "api_error", "timeout", "blocked", "unknown"}


def _transcript(data: dict):
    direct = data.get("agent_transcript_path")
    if direct:
        return str(direct)
    agent_id = data.get("agent_id") or data.get("agentId") or data.get("subagent_id")
    main_tp = data.get("transcript_path")
    if agent_id and main_tp:
        session_dir = os.path.splitext(str(main_tp))[0]
        return os.path.join(session_dir, "subagents", "agent-%s.jsonl" % agent_id)
    return None


def core(data: dict) -> None:
    outcome = str(data.get("outcome") or "").strip().lower()
    if outcome not in _OUTCOMES:
        outcome = "unknown"  # never fabricate success
    agent_type = str(data.get("agent_type") or data.get("subagent_type") or "unknown")
    trace.append_event(
        _STEM, "subagent_outcome",
        session=data.get("session_id") or os.environ.get("SYMM_SESSION_ID"),
        target=agent_type, status=outcome, note=_transcript(data),
    )


def main(raw=None) -> None:
    hook_runtime.run_telemetry_hook(_STEM, core, raw=raw)


if __name__ == "__main__":
    main()
