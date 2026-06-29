"""test_subagent_init.py — SubagentStart context injector (telemetry, fail-open).

At subagent spawn the hook injects a concise pointer at the harness rule layer +
standards + an ownership reminder, so a delegated subagent operates within harness
conventions even if the orchestrator's prompt was terse. Telemetry posture: never
blocks; any error degrades to no context.
"""
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import subagent_init as si  # noqa: E402


def test_context_points_at_rules_and_standards():
    txt = si.context_text({"agent_type": "hs:developer", "agent_id": "abc"})
    assert "harness/rules" in txt
    assert "harness/standards" in txt


def test_context_mentions_ownership_discipline():
    txt = si.context_text({"agent_type": "claude"})
    assert "ownership" in txt.lower() or "scope" in txt.lower()


def test_context_fail_open_on_empty_payload():
    assert isinstance(si.context_text({}), str)
    assert isinstance(si.context_text(None), str)


def test_hook_class_is_telemetry():
    assert si.HOOK_CLASS == "telemetry"
