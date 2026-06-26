"""E21 Phase 1 — TaskLoopSnapshot read-model tests. Maps to acceptance.md S21.9.

The snapshot is what the UI Graph/Inspector render. It is FOLDED from the ``loop.*``
events the supervisor already emits (red-team F1: not ``agent.*`` — nobody emits those
yet), and it must never carry a raw secret — it reads each event's redacted
``ui_payload``, never the raw ``payload`` (S21.9 / red-team F2).
"""
from __future__ import annotations

import json

import pytest

from control import (
    Actor,
    ControlContractError,
    RedactionInfo,
    Redactor,
    RuntimeEvent,
    TraceContext,
)
from control.snapshot import AgentView, TaskLoopSnapshot, build_snapshot


def _ev(event_type: str, payload: dict, **over) -> RuntimeEvent:
    base = dict(
        event_type=event_type,
        session_id="s1",
        actor=Actor(type="runtime", id="supervisor"),
        trace=TraceContext(trace_id="tr", span_id="sp"),
        redaction=RedactionInfo(level="ui_safe"),
        payload=payload,
    )
    base.update(over)
    return RuntimeEvent(**base)


# ── S21.9 — Graph derives A=done / B=running / C=pending from loop.* events ────
def test_build_snapshot_status_graph():
    """A real loop sequence: team [A,B,C] composed, A takes a turn, then O routes to B.
    The snapshot must show A done, B running, C still pending — the S21.9 scenario."""
    events = [
        _ev("loop.team_composed", {"selected": ["A", "B", "C"]}, round_no=0),
        _ev("loop.turn", {"agent_id": "A", "outcome": "drafted plan"}, round_no=1),
        _ev(
            "loop.decision",
            {
                "round": 1,
                "decision": "continue",
                "reason": "A done, route to B",
                "next_agent_calls": [{"agent_id": "B", "objective": "build it"}],
            },
            round_no=1,
        ),
    ]
    snap = build_snapshot(events, session_id="s1")

    by = {a.agent_id: a for a in snap.agents}
    assert by["A"].status == "done"
    assert by["A"].last_output_summary == "drafted plan"
    assert by["B"].status == "running"
    assert by["C"].status == "pending"
    assert snap.orchestrator["last_decision"] == "continue"
    assert snap.orchestrator["reason"] == "A done, route to B"
    assert [c["agent_id"] for c in snap.pending_agent_calls] == ["B"]
    assert snap.session_id == "s1"
    assert snap.round_no == 1


# ── S21.9 / F2 — snapshot reads ui_payload (redacted), never raw payload ───────
def test_build_snapshot_no_raw_secret():
    """An event carries a secret in its raw payload but is redacted (as the fake server
    does via Redactor().apply) before folding. The secret value must never appear in the
    snapshot, and free-form context must come from the redacted ui_payload."""
    raw = _ev(
        "loop.turn",
        {
            "agent_id": "A",
            "outcome": "ok",
            "context_packet": {"briefing": "call the api", "api_key": "sk-LEAK"},
        },
    )
    redacted = Redactor().apply(raw)  # ui_payload.context_packet.api_key -> [REDACTED]

    snap = build_snapshot(
        [_ev("loop.team_composed", {"selected": ["A"]}), redacted], session_id="s1"
    )

    blob = json.dumps(snap.as_dict())
    assert "sk-LEAK" not in blob
    assert redacted.ui_payload["context_packet"]["api_key"] == "[REDACTED]"
    by = {a.agent_id: a for a in snap.agents}
    # context_packet is taken from the redacted ui_payload — not the raw payload.
    assert by["A"].context_packet.get("api_key") == "[REDACTED]"


# ── F6 — permission.changed binds a permission onto the agent's Inspector view ─
def test_build_snapshot_folds_permission_changed():
    perm = {"allowed_tools": ["read_file", "search_code"], "can_write_artifacts": True}
    events = [
        _ev("loop.team_composed", {"selected": ["B"]}),
        Redactor().apply(_ev("permission.changed", {"agent_id": "B", "permission": perm})),
    ]
    snap = build_snapshot(events, session_id="s1")
    b = {a.agent_id: a for a in snap.agents}["B"]
    assert b.permission == perm
    assert b.allowed_tools == ("read_file", "search_code")


# ── C1 (review): an un-redacted event must NOT leak its raw payload into the snapshot ─
def test_build_snapshot_never_folds_raw_payload_dicts():
    """If an event reaches build_snapshot un-redacted (ui_payload is None), the fold must
    still not copy a raw free-form dict (checkpoints / acceptance_status) — those could carry
    secret keys. Whitelist scalars; take free-form payload only from the redacted ui_payload."""
    raw_checkpoint = _ev(
        "checkpoint.reached",
        {"agent_id": "B", "checkpoint_id": "cp1", "status": "waiting",
         "api_key": "sk-SECRET-LEAK", "token": "bearer-xyz"},
    )  # ui_payload is None (never redacted)
    raw_decision = _ev(
        "loop.decision",
        {"decision": "continue", "acceptance_status": [{"id": "ac1", "text": "ok", "status": "pending", "api_key": "sk-AC-LEAK"}]},
    )
    snap = build_snapshot([raw_checkpoint, raw_decision], session_id="s1")
    blob = json.dumps(snap.as_dict())
    assert "sk-SECRET-LEAK" not in blob
    assert "bearer-xyz" not in blob
    assert "sk-AC-LEAK" not in blob
    # the safe scalar fields still surface (the Approval modal needs them)
    assert snap.checkpoints[0]["checkpoint_id"] == "cp1"
    assert snap.checkpoints[0]["status"] == "waiting"
    assert snap.acceptance_status[0]["id"] == "ac1"


# ── contract hygiene: snapshot round-trips losslessly + validates ─────────────
def test_snapshot_roundtrip_and_agentview_validation():
    snap = build_snapshot(
        [_ev("loop.team_composed", {"selected": ["A"]})], session_id="s1"
    )
    assert TaskLoopSnapshot.from_dict(snap.as_dict()).as_dict() == snap.as_dict()
    with pytest.raises(ControlContractError):
        AgentView(agent_id="")  # agent_id is required
    with pytest.raises(ControlContractError):
        AgentView(agent_id="A", status="teleporting")  # not a known status
