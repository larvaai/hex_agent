"""E21 Phase A — S-CONTRACT contract tests. Maps to acceptance.md S21.1–S21.7.

Pure contracts, no I/O: envelope round-trip + validation, the two registries, command
contract + idempotency requirement, checkpoint transition, permission patch, and the
redaction boundary (nested dict + list secrets never leak into ui_payload).
"""
from __future__ import annotations

import pytest

from control import (
    Actor,
    CommandAck,
    ControlContractError,
    IssuedBy,
    Permission,
    Redactor,
    RedactionInfo,
    RuntimeCheckpoint,
    RuntimeCommand,
    RuntimeEvent,
    SessionSeq,
    TraceContext,
    load_command_registry,
    load_event_registry,
    parse_command,
)


def _event(**overrides) -> RuntimeEvent:
    base = dict(
        event_type="agent.before_run",
        session_id="sess_1",
        actor=Actor(type="agent", id="agent_b"),
        trace=TraceContext(trace_id="tr_1", span_id="sp_1"),
        redaction=RedactionInfo(level="ui_safe"),
        payload={"objective": "do X"},
    )
    base.update(overrides)
    return RuntimeEvent(**base)


# ── S21.1 RuntimeEvent envelope ──────────────────────────────────────────────
def test_event_roundtrip_preserves_fields():
    ev = _event(round_no=2, task_id="task_9", payload={"k": "v"})
    again = RuntimeEvent.from_dict(ev.as_dict())
    assert again.as_dict() == ev.as_dict()
    assert again.round_no == 2 and again.task_id == "task_9"


@pytest.mark.parametrize("bad", ["event_type", "session_id"])
def test_event_missing_required_raises(bad):
    with pytest.raises(ControlContractError):
        _event(**{bad: ""})


def test_event_missing_event_id_via_from_dict_raises():
    d = _event().as_dict()
    d["event_id"] = ""
    with pytest.raises(ControlContractError):
        RuntimeEvent.from_dict(d)


def test_actor_and_redaction_levels_validated():
    with pytest.raises(ControlContractError):
        Actor(type="alien", id="x")
    with pytest.raises(ControlContractError):
        RedactionInfo(level="top-secret")


def test_session_seq_monotonic_per_session():
    seq = SessionSeq()
    assert [seq.next("a"), seq.next("a"), seq.next("b"), seq.next("a")] == [1, 2, 1, 3]


# ── S21.2 event-type registry ────────────────────────────────────────────────
def test_event_registry_known_and_unknown():
    reg = load_event_registry()
    reg.assert_known("agent.before_run")
    assert reg.visibility("agent.output.raw") == "internal"
    assert reg.get("agent.token").redact_for_ui is True
    with pytest.raises(ControlContractError):
        reg.assert_known("agent.invented_event")


def test_event_registry_rejects_non_dotted_or_bad_visibility():
    from control import parse_event_registry

    with pytest.raises(ControlContractError):
        parse_event_registry({"event_types": {"nodot": {"visibility": "ui_safe"}}})
    with pytest.raises(ControlContractError):
        parse_event_registry({"event_types": {"a.b": {"visibility": "nope"}}})


# ── S21.3 RuntimeCommand contract ────────────────────────────────────────────
def test_command_roundtrip():
    cmd = RuntimeCommand(
        command_type="AddAgentToLoop",
        session_id="sess_1",
        issued_by=IssuedBy(type="human", user_id="user_1"),
        idempotency_key="user_1:sess_1:add_x:001",
        payload={"agent_id": "agent_x"},
    )
    assert RuntimeCommand.from_dict(cmd.as_dict()).as_dict() == cmd.as_dict()


def test_command_missing_idempotency_or_issuer_rejected():
    good = {
        "command_type": "PauseWorkflow",
        "session_id": "sess_1",
        "issued_by": {"type": "human", "user_id": "u"},
        "idempotency_key": "k1",
    }
    assert parse_command(good).command_type == "PauseWorkflow"
    with pytest.raises(ControlContractError):
        parse_command({**good, "idempotency_key": ""})
    with pytest.raises(ControlContractError):
        parse_command({k: v for k, v in good.items() if k != "issued_by"})


def test_issued_by_human_requires_user_id():
    with pytest.raises(ControlContractError):
        IssuedBy(type="human")


# ── S21.15 CommandAck — the synchronous receipt for POST /api/commands ────────
def test_command_ack_roundtrip():
    ack = CommandAck(command_id="c1", status="received", seq=5)
    assert CommandAck.from_dict(ack.as_dict()).as_dict() == ack.as_dict()
    rej = CommandAck(command_id="c2", status="rejected", rejection_reason="unknown command_type")
    assert CommandAck.from_dict(rej.as_dict()).as_dict() == rej.as_dict()
    assert rej.seq is None  # ACK is a receipt; the applied/accepted seq arrives later via SSE


def test_command_ack_rejected_requires_reason_and_valid_status():
    with pytest.raises(ControlContractError):
        CommandAck(command_id="c3", status="rejected")  # rejected must carry a reason
    with pytest.raises(ControlContractError):
        CommandAck(command_id="", status="received")  # command_id required
    with pytest.raises(ControlContractError):
        CommandAck(command_id="c4", status="queued")  # not received|rejected


# ── S21.4 command-type registry ──────────────────────────────────────────────
def test_command_registry_apply_at_and_permission():
    reg = load_command_registry()
    assert reg.apply_at("StopAgentTurn") == "immediate"
    assert reg.apply_at("AddAgentToLoop") == "next_checkpoint"
    assert reg.apply_at("ApproveCheckpoint") == "immediate_if_waiting"
    assert reg.requires_permission("UpdateAgentPermission") == "workflow.modify_permissions"
    with pytest.raises(ControlContractError):
        reg.assert_known("FrobnicateEverything")


def test_command_registry_has_submit_prompt():
    # E21 control-plane UI "Send" maps to SubmitPrompt (F5/D8) — the fake gateway calls
    # assert_known(), so an undeclared SubmitPrompt would 400 the Send path.
    reg = load_command_registry()
    reg.assert_known("SubmitPrompt")
    assert reg.apply_at("SubmitPrompt") == "next_checkpoint"
    assert reg.requires_permission("SubmitPrompt") is None


# ── S21.5 RuntimeCheckpoint contract ─────────────────────────────────────────
def test_checkpoint_starts_waiting_and_resolves_once():
    cp = RuntimeCheckpoint(
        checkpoint_type="before_tool_call", session_id="sess_1", risk_level="high"
    )
    assert cp.is_waiting and cp.status == "waiting"
    approved = cp.with_status("approved")
    assert approved.status == "approved" and approved.resolved_at
    with pytest.raises(ControlContractError):
        approved.with_status("rejected")  # already resolved
    with pytest.raises(ControlContractError):
        cp.with_status("waiting")  # not a resolved status


def test_checkpoint_bad_risk_level_rejected():
    with pytest.raises(ControlContractError):
        RuntimeCheckpoint(checkpoint_type="x", session_id="s", risk_level="catastrophic")


# ── S21.6 Permission contract ────────────────────────────────────────────────
def test_permission_roundtrip_and_patch():
    p = Permission(allowed_tools=("read_file",), effective_from="next_checkpoint")
    assert Permission.from_dict(p.as_dict()).as_dict() == p.as_dict()
    p2 = p.patched({"allowed_tools": ["read_file", "search_code"], "can_write_artifacts": True})
    assert p2.allows_tool("search_code") and p2.can_write_artifacts
    assert not p.can_write_artifacts  # original unchanged
    with pytest.raises(ControlContractError):
        p.patched({"can_fly": True})  # unknown field
    with pytest.raises(ControlContractError):
        Permission(effective_from="whenever")


# ── S21.7 Redaction engine ───────────────────────────────────────────────────
def test_redactor_masks_nested_and_list_secrets():
    redactor = Redactor()
    payload = {
        "api_key": "sk-123",
        "nested": {"authorization": "Bearer z", "ok": "keep"},
        "items": [{"token": "t1"}, {"value": "fine"}],
    }
    ui, fields = redactor.redact(payload)
    assert ui["api_key"] == "[REDACTED]"
    assert ui["nested"]["authorization"] == "[REDACTED]"
    assert ui["nested"]["ok"] == "keep"
    assert ui["items"][0]["token"] == "[REDACTED]"
    assert ui["items"][1]["value"] == "fine"
    assert set(fields) == {"api_key", "nested.authorization", "items[0].token"}
    # original payload untouched
    assert payload["api_key"] == "sk-123"


def test_redactor_apply_fills_ui_payload_and_info():
    ev = _event(payload={"password": "hunter2-secret", "msg": "hi"})
    out = Redactor().apply(ev, level="ui_safe")
    assert out.ui_payload == {"password": "[REDACTED]", "msg": "hi"}
    assert out.redaction.has_secret is True
    assert out.redaction.redacted_fields == ("password",)
    # the secret value never appears in the ui_payload
    assert "hunter2-secret" not in str(out.ui_payload)
    # raw payload preserved on the event
    assert ev.payload["password"] == "hunter2-secret"
