"""E21 Phase B — B1 EventEmitter tests.

The emitter is the one validated/redacted/sequenced publish path. These prove: registry
gating (unknown rejected), monotonic seq, redaction before any sink sees the event, the
envelope round-trips off the bus, durability via the existing EventLogger, and that
SupervisorContext routes through the emitter when one is wired (opt-in, B1).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from control import (
    Actor,
    ControlContractError,
    RuntimeEvent,
    SessionSeq,
    TraceContext,
    bus_emitter,
)
from core.events import EventBus


def _collector(bus: EventBus) -> list[tuple[str, dict]]:
    captured: list[tuple[str, dict]] = []
    bus.subscribe(lambda topic, payload: captured.append((topic, payload)))
    return captured


def test_emit_publishes_redacted_envelope_with_seq():
    bus = EventBus()
    captured = _collector(bus)
    emitter = bus_emitter(bus, seq=SessionSeq())
    emitter.emit(
        "agent.before_run",
        session_id="s1",
        actor=Actor(type="agent", id="agent_b"),
        trace=TraceContext.new_root(),
        payload={"objective": "do X", "api_key": "sk-secret"},
    )
    assert len(captured) == 1
    topic, env = captured[0]
    assert topic == "agent.before_run"
    assert env["session_id"] == "s1" and env["seq"] == 1
    assert env["actor"] == {"type": "agent", "id": "agent_b"}
    # secret never reaches the sink's ui_payload, and it is flagged
    assert env["ui_payload"]["api_key"] == "[REDACTED]"
    assert env["ui_payload"]["objective"] == "do X"
    assert env["redaction"]["has_secret"] is True
    assert "api_key" in env["redaction"]["redacted_fields"]


def test_unknown_event_type_rejected_and_not_published():
    bus = EventBus()
    captured = _collector(bus)
    emitter = bus_emitter(bus)
    with pytest.raises(ControlContractError):
        emitter.emit(
            "agent.does_not_exist",
            session_id="s1",
            actor=Actor(type="runtime", id="r"),
            trace=TraceContext.new_root(),
        )
    assert captured == []


def test_seq_monotonic_per_session():
    emitter = bus_emitter(EventBus(), seq=SessionSeq())
    actor = Actor(type="runtime", id="r")
    seqs = [
        emitter.emit("state.updated", session_id=s, actor=actor, trace=TraceContext.new_root()).seq
        for s in ("a", "a", "b", "a")
    ]
    assert seqs == [1, 2, 1, 3]


def test_envelope_roundtrips_off_the_bus():
    bus = EventBus()
    captured = _collector(bus)
    emitter = bus_emitter(bus)
    emitter.emit(
        "tool.after_call",
        session_id="s1",
        actor=Actor(type="tool", id="read_file"),
        trace=TraceContext.new_root(),
        payload={"ok": True},
    )
    restored = RuntimeEvent.from_dict(captured[0][1])
    assert restored.event_type == "tool.after_call" and restored.payload == {"ok": True}


def test_emitter_durable_via_event_logger(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_EVENT_LOG", "1")
    from observability import EventLogger, attach_to_bus

    bus = EventBus()
    logger = EventLogger(run_id="emit_test")
    attach_to_bus(logger, bus)
    bus_emitter(bus).emit(
        "agent.after_run",
        session_id="s1",
        actor=Actor(type="agent", id="agent_b"),
        trace=TraceContext.new_root(),
        payload={"summary": "done"},
    )
    text = (tmp_path / "emit_test" / "events.jsonl").read_text(encoding="utf-8")
    assert "agent.after_run" in text


def test_supervisor_context_routes_emit_through_emitter():
    from supervisor.graph import SupervisorContext

    bus = EventBus()
    captured = _collector(bus)
    emitter = bus_emitter(bus)
    session = SimpleNamespace(identity=SimpleNamespace(session_id="s1", task_id="t1"))
    ctx = SupervisorContext(
        supervisor_session=session,
        delegation_service=None,
        orchestrator=None,
        broker=None,
        emitter=emitter,
    )
    ctx.emit("loop.decision", {"round": 1, "decision": "continue"})
    ctx.emit("loop.turn", {"agent_id": "agent_b", "outcome": "success"})
    topics = [t for t, _ in captured]
    assert topics == ["loop.decision", "loop.turn"]
    first = captured[0][1]
    assert first["session_id"] == "s1" and first["task_id"] == "t1"
    assert first["actor"] == {"type": "runtime", "id": "supervisor"}
    assert first["seq"] == 1 and first["ui_payload"] == {"round": 1, "decision": "continue"}
    # both events share one trace (same session), with increasing seq
    assert captured[0][1]["trace"]["trace_id"] == captured[1][1]["trace"]["trace_id"]
    assert captured[1][1]["seq"] == 2
