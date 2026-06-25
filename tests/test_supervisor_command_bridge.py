"""Phase 2 — command bridge between Agent O and the E21 control plane. Epic E21.

The bridge is a pure module: it translates O's command intents into validated
RuntimeCommands, queues them (deduped by idempotency_key), and applies the ones
it supports (AddAgentToLoop) at a checkpoint. Nothing here is wired into the loop
yet — these tests exercise the functions directly with a fake ctx.
"""
from __future__ import annotations

import pytest

from control.command_registry import load_command_registry
from control.commands import IssuedBy, RuntimeCommand
from control.errors import ControlContractError
from supervisor.command_bridge import (
    apply_pending_commands,
    enqueue_commands,
    to_runtime_command,
)
from supervisor.contracts import OrchestratorDecision
from supervisor.state import TaskLoopState

REGISTRY = load_command_registry()


class FakeCtx:
    """Records every emitted (topic, payload) so tests can assert on events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, topic: str, payload: dict) -> None:
        self.events.append((topic, payload))

    def topics(self) -> list[str]:
        return [t for t, _ in self.events]


def _add(agent_id: str) -> dict:
    return {"command_type": "AddAgentToLoop", "payload": {"agent_id": agent_id}}


def _state(selected=("code",)) -> TaskLoopState:
    s = TaskLoopState(session_id="sess-1", task_id="t1")
    s.selected_agents = list(selected)
    return s


def _decision(*commands: dict) -> OrchestratorDecision:
    return OrchestratorDecision(decision="continue", commands=tuple(commands))


# ── to_runtime_command ───────────────────────────────────────────────────────
def test_to_runtime_command_is_agent_issued():
    cmd = to_runtime_command(_add("reviewer"), session_id="sess-1")
    assert cmd.issued_by.type == "agent"
    assert cmd.issued_by.agent_id == "orchestrator"


def test_idempotency_key_is_stable_across_calls():
    # Two translations of the same intent must share a key even though each
    # RuntimeCommand gets its own random command_id/created_at.
    a = to_runtime_command(_add("reviewer"), session_id="sess-1")
    b = to_runtime_command(_add("reviewer"), session_id="sess-1")
    assert a.idempotency_key == b.idempotency_key
    assert a.command_id != b.command_id


def test_to_runtime_command_rejects_empty_type():
    with pytest.raises(ControlContractError):
        to_runtime_command({"command_type": "", "payload": {}}, session_id="sess-1")


# ── enqueue_commands (dedup by key) ──────────────────────────────────────────
def test_enqueue_pushes_translated_commands():
    state = _state()
    n = enqueue_commands(state, _decision(_add("reviewer")))
    assert n == 1
    assert len(state.pending_commands) == 1
    assert state.pending_commands[0]["command_type"] == "AddAgentToLoop"


def test_enqueue_dedupes_by_idempotency_key():
    # Same intent twice → only one queued, even though as_dict() differs by command_id.
    state = _state()
    enqueue_commands(state, _decision(_add("reviewer"), _add("reviewer")))
    keys = [c["idempotency_key"] for c in state.pending_commands]
    assert keys == ["AddAgentToLoop:reviewer"]


def test_enqueue_skips_already_applied_key():
    state = _state()
    state.applied_command_keys = ["AddAgentToLoop:reviewer"]
    n = enqueue_commands(state, _decision(_add("reviewer")))
    assert n == 0
    assert state.pending_commands == []


# ── apply_pending_commands ───────────────────────────────────────────────────
def test_apply_adds_agent_in_catalog():
    state = _state()
    enqueue_commands(state, _decision(_add("reviewer")))
    ctx = FakeCtx()
    applied = apply_pending_commands(state, ctx, registry=REGISTRY, catalog={"code", "reviewer"})
    assert applied == 1
    assert "reviewer" in state.selected_agents
    assert "AddAgentToLoop:reviewer" in state.applied_command_keys
    assert "loop.agent_added" in ctx.topics()
    assert state.pending_commands == []          # queue cleared after the pass


def test_apply_is_idempotent_under_repeat():
    state = _state()
    enqueue_commands(state, _decision(_add("reviewer")))
    apply_pending_commands(state, FakeCtx(), registry=REGISTRY, catalog={"code", "reviewer"})
    # O re-issues the same command next round; roster must not grow twice.
    enqueue_commands(state, _decision(_add("reviewer")))      # deduped → nothing queued
    applied = apply_pending_commands(state, FakeCtx(), registry=REGISTRY, catalog={"code", "reviewer"})
    assert applied == 0
    assert state.selected_agents.count("reviewer") == 1


def test_apply_rejects_role_outside_catalog():
    state = _state()
    enqueue_commands(state, _decision(_add("ghost")))
    ctx = FakeCtx()
    applied = apply_pending_commands(state, ctx, registry=REGISTRY, catalog={"code", "reviewer"})
    assert applied == 0
    assert "ghost" not in state.selected_agents
    assert "command.rejected" in ctx.topics()


def test_apply_skips_already_selected_agent():
    # Honoured (key marked) but no roster growth → not counted as progress.
    state = _state(selected=("code",))
    enqueue_commands(state, _decision(_add("code")))
    ctx = FakeCtx()
    applied = apply_pending_commands(state, ctx, registry=REGISTRY, catalog={"code"})
    assert applied == 0
    assert state.selected_agents == ["code"]
    assert "AddAgentToLoop:code" in state.applied_command_keys


def test_apply_rejects_human_issued_command():
    # Trust-O boundary: a human-issued command does NOT mutate the roster here.
    state = _state()
    human_cmd = RuntimeCommand(
        command_type="AddAgentToLoop",
        session_id="sess-1",
        issued_by=IssuedBy(type="human", user_id="u1"),
        idempotency_key="AddAgentToLoop:reviewer",
        payload={"agent_id": "reviewer"},
    )
    state.pending_commands = [human_cmd.as_dict()]
    ctx = FakeCtx()
    applied = apply_pending_commands(state, ctx, registry=REGISTRY, catalog={"code", "reviewer"})
    assert applied == 0
    assert "reviewer" not in state.selected_agents
    assert "command.rejected" in ctx.topics()


def test_apply_skips_known_but_unsupported_command():
    # RemoveAgentFromLoop is a declared type but unsupported in v1 → skipped, no mutation.
    state = _state()
    cmd = to_runtime_command(
        {"command_type": "RemoveAgentFromLoop", "payload": {"agent_id": "code"}},
        session_id="sess-1",
    )
    state.pending_commands = [cmd.as_dict()]
    ctx = FakeCtx()
    applied = apply_pending_commands(state, ctx, registry=REGISTRY, catalog={"code"})
    assert applied == 0
    assert state.selected_agents == ["code"]
    assert "command.skipped" in ctx.topics()


def test_apply_rejects_unknown_command_type_without_crashing():
    # A command type not in the registry must be rejected, not raise out of apply.
    state = _state()
    cmd = to_runtime_command(
        {"command_type": "Frobnicate", "payload": {"agent_id": "code"}},
        session_id="sess-1",
    )
    state.pending_commands = [cmd.as_dict()]
    ctx = FakeCtx()
    applied = apply_pending_commands(state, ctx, registry=REGISTRY, catalog={"code"})
    assert applied == 0
    assert "command.rejected" in ctx.topics()
