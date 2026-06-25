"""Phase 1 — data contracts for O-issued commands + department targeting. Epic E21.

These tests pin the *shape* of the new fields only. Nothing here applies a
command or expands a department yet — that arrives in later phases. The whole
point of Phase 1 is that the new fields are inert and backward-compatible:
old decisions parse with empty defaults, and old checkpoints decode without
KeyError.
"""
from __future__ import annotations

import json

import pytest

from discipline import JsonGateError
from supervisor.contracts import parse_decision
from supervisor.state import (
    TaskLoopState,
    decode_taskloop_state,
    encode_taskloop_state,
)


def _decision(**kw) -> str:
    """Build a raw decision JSON string (parse_decision takes text, not a dict)."""
    return json.dumps({"decision": "continue", **kw})


# ── OrchestratorDecision.commands ────────────────────────────────────────────
def test_parse_decision_reads_commands_list():
    raw = _decision(
        commands=[{"command_type": "AddAgentToLoop", "payload": {"agent_id": "reviewer"}}]
    )
    decision = parse_decision(raw)
    # commands is a tuple of plain dicts; Phase 1 only validates their shape.
    assert len(decision.commands) == 1
    assert decision.commands[0]["command_type"] == "AddAgentToLoop"


def test_parse_decision_rejects_command_without_type():
    # A command dict missing 'command_type' is structurally invalid → json-gate error.
    raw = _decision(commands=[{"payload": {}}])
    with pytest.raises(JsonGateError):
        parse_decision(raw)


def test_parse_decision_rejects_non_dict_command():
    raw = _decision(commands=["AddAgentToLoop"])
    with pytest.raises(JsonGateError):
        parse_decision(raw)


def test_old_decision_has_empty_commands():
    # Backward-compat: a decision that predates this feature has no 'commands' key.
    decision = parse_decision(_decision(reason="just continue"))
    assert decision.commands == ()


# ── AgentAssignment.target_kind ──────────────────────────────────────────────
def _call(**kw) -> dict:
    base = {"agent_id": "engineering", "objective": "build it"}
    base.update(kw)
    return base


def test_assignment_target_kind_department():
    raw = _decision(next_agent_calls=[_call(target_kind="department")])
    decision = parse_decision(raw)
    assert decision.next_agent_calls[0].target_kind == "department"


def test_assignment_target_kind_defaults_to_agent():
    raw = _decision(next_agent_calls=[_call()])
    decision = parse_decision(raw)
    assert decision.next_agent_calls[0].target_kind == "agent"


def test_assignment_target_kind_rejects_unknown_value():
    raw = _decision(next_agent_calls=[_call(target_kind="squad")])
    with pytest.raises(JsonGateError):
        parse_decision(raw)


# ── TaskLoopState command queues round-trip ──────────────────────────────────
def test_state_command_queues_round_trip():
    state = TaskLoopState(session_id="s1", task_id="t1")
    state.pending_commands = [{"command_type": "AddAgentToLoop", "idempotency_key": "k1"}]
    state.applied_command_keys = ["k0"]

    decoded = decode_taskloop_state(encode_taskloop_state(state))

    assert decoded.pending_commands == state.pending_commands
    assert decoded.applied_command_keys == state.applied_command_keys


def test_decode_old_checkpoint_without_command_keys():
    # An old checkpoint dict has neither new key; decode must default to empty lists.
    old = encode_taskloop_state(TaskLoopState(session_id="s1", task_id="t1"))
    old.pop("pending_commands", None)
    old.pop("applied_command_keys", None)

    decoded = decode_taskloop_state(old)

    assert decoded.pending_commands == []
    assert decoded.applied_command_keys == []
