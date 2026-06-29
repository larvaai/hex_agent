#!/usr/bin/env python3
"""track_skill_invocation.py — one trace line per skill call (telemetry-class).

Fires on two events (both wired in settings.json):
  - PreToolUse tool_name "Skill"  → tool_input.skill | tool_input.name
    (the model invoking a skill via the Skill TOOL).
  - UserPromptExpansion            → command_name (the user typing /mind:reason).

Writes to the append-only audit trace via scripts/trace.py. Fail-open +
non-blocking + config gate are owned by hook_runtime.run_telemetry_hook.

Ported from harness/hooks/track_skill_invocation.py, simplified: no rotating
telemetry sink, no per-minute dedup — the append-only ledger keeps both event
signals (distinguished by `note=<via>`), which is what an audit wants.
"""

import os
import re
import sys
from pathlib import Path

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HOOKS_DIR, "..", "scripts"))  # paths, trace
if _HOOKS_DIR not in sys.path:
    sys.path.append(_HOOKS_DIR)
import hook_runtime  # noqa: E402
import trace  # noqa: E402

HOOK_CLASS = "telemetry"
_STEM = Path(__file__).stem


def extract_skill(data: dict):
    """Return (skill_name, via_label) from the hook payload."""
    if data.get("tool_name") == "Skill":
        inp = data.get("tool_input") or {}
        return str(inp.get("skill") or inp.get("name") or ""), "PreToolUse:Skill"
    if (data.get("command_name") or data.get("command")
            or data.get("hook_event_name") == "UserPromptExpansion"):
        raw = str(data.get("command_name") or data.get("command") or "").strip().lstrip("/")
        return (re.split(r"\s+", raw)[0] if raw else ""), "UserPromptExpansion"
    return "", ""


def core(data: dict) -> None:
    skill, via = extract_skill(data)
    if not skill:
        return
    trace.append_event(
        _STEM, "skill_call",
        session=data.get("session_id") or os.environ.get("SYMM_SESSION_ID"),
        tool="Skill", target=skill, note=via,
    )


def main(raw=None) -> None:
    hook_runtime.run_telemetry_hook(_STEM, core, raw=raw)


if __name__ == "__main__":
    main()
