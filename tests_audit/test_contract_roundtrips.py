"""Property tests for every persisted/public data contract."""
from __future__ import annotations

import copy

import pytest
from hypothesis import given, strategies as st

from core.schemas import (
    ArtifactEnvelope,
    CapabilityResult,
    DelegationPolicy,
    DelegationProgress,
    DelegationResult,
    DelegationSpec,
    FeatureDescriptor,
    TaskEnvelope,
    ToolCallContext,
)
from core.session import SessionIdentity
from core.state import StateStore
from control import CommandAck
from control.snapshot import AgentView, TaskLoopSnapshot
from supervisor.state import (
    AcceptanceCheck,
    AgentTurn,
    TaskLoopState,
    decode_taskloop_state,
    encode_taskloop_state,
)

pytestmark = [pytest.mark.audit, pytest.mark.property]

safe_text = st.text(st.characters(blacklist_categories=("Cs",)), max_size=80)
json_scalar = st.none() | st.booleans() | st.integers(-10**9, 10**9) | safe_text
json_value = st.recursive(
    json_scalar,
    lambda children: st.lists(children, max_size=5)
    | st.dictionaries(safe_text, children, max_size=5),
    max_leaves=20,
)
json_object = st.dictionaries(safe_text, json_value, max_size=8)


@given(user_request=safe_text, context=json_object, metadata=json_object, task_id=safe_text.filter(bool))
def test_task_envelope_roundtrip_is_lossless(user_request, context, metadata, task_id):
    task = TaskEnvelope(user_request, context=context, metadata=metadata, task_id=task_id)
    restored = TaskEnvelope.from_dict(task.as_dict())
    assert restored == task
    assert restored.context is not task.context
    assert restored.metadata is not task.metadata


@given(ok=st.booleans(), payload=json_value, raw_meta=json_object, extra_meta=json_object)
def test_capability_result_normalizes_raw_dict_without_losing_payload(ok, payload, raw_meta, extra_meta):
    raw = {"ok": ok, "payload": payload, "metadata": raw_meta}
    result = CapabilityResult.from_raw(
        capability="audit.tool", feature="audit", result=raw, metadata=extra_meta
    ).as_dict()
    assert result["ok"] is ok
    assert result["capability"] == "audit.tool"
    assert result["feature"] == "audit"
    assert result["data"]["payload"] == payload
    assert result["metadata"] == {**raw_meta, **extra_meta, "raw_keys": sorted(raw)}
    if ok:
        assert result["error"] is None
    else:
        assert result["error"] == "Capability execution failed."


def test_capability_result_extra_metadata_wins_over_nested_envelope_metadata():
    raw = {
        "ok": True,
        "capability": "inner",
        "feature": "inner-feature",
        "data": {"x": 1},
        "error": None,
        "metadata": {"request_id": "old", "owner": "inner"},
    }
    normalized = CapabilityResult.from_raw(
        capability="outer",
        feature="outer-feature",
        result=raw,
        metadata={"request_id": "new", "trace": "root"},
    ).as_dict()
    assert normalized == {
        "ok": True,
        "capability": "inner",
        "feature": "inner-feature",
        "data": {"x": 1},
        "error": None,
        "metadata": {"request_id": "new", "owner": "inner", "trace": "root"},
    }


@given(objective=safe_text, context=json_object, schema=json_object, constraints=st.lists(safe_text, max_size=8))
def test_delegation_spec_roundtrip(objective, context, schema, constraints):
    spec = DelegationSpec(objective, context, schema, tuple(constraints))
    assert DelegationSpec.from_dict(spec.as_dict()) == spec


@given(
    max_steps=st.integers(1, 1000),
    max_depth=st.integers(1, 100),
    capabilities=st.sets(safe_text.filter(bool), max_size=10),
)
def test_delegation_policy_roundtrip(max_steps, max_depth, capabilities):
    policy = DelegationPolicy(max_steps, max_depth, frozenset(capabilities))
    assert DelegationPolicy.from_dict(policy.as_dict()) == policy


@given(
    session_id=safe_text.filter(bool),
    run_id=safe_text.filter(bool),
    task_id=safe_text.filter(bool),
    agent_id=safe_text.filter(bool),
    depth=st.integers(0, 100),
)
def test_session_identity_roundtrip(session_id, run_id, task_id, agent_id, depth):
    identity = SessionIdentity(session_id, run_id, task_id, agent_id, depth=depth)
    assert SessionIdentity.from_dict(identity.as_dict()) == identity


@given(payload=json_object)
def test_state_store_never_leaks_nested_aliases(payload):
    store = StateStore()
    store.set("payload", copy.deepcopy(payload))
    snapshot = store.snapshot()
    public = store.as_dict()
    snapshot["payload"] = {"mutated": True}
    public["payload"] = {"mutated": True}
    assert store.get("payload") == payload

    source = {"payload": copy.deepcopy(payload)}
    store.restore(source)
    source["payload"] = {"mutated": True}
    assert store.get("payload") == payload


def test_tool_call_context_event_fields_excludes_capability_scope():
    context = ToolCallContext(
        run_id="r",
        task_id="t",
        session_id="s",
        parent_session_id="p",
        delegation_id="d",
        actor_id="a",
        allowed_capabilities=frozenset({"secret.tool"}),
    )
    assert context.event_fields() == {
        "run_id": "r",
        "task_id": "t",
        "session_id": "s",
        "parent_session_id": "p",
        "delegation_id": "d",
        "actor_id": "a",
    }


def test_all_schema_as_dict_methods_return_detached_containers():
    artifact = ArtifactEnvelope("a", "kind", {"nested": {"x": 1}})
    progress = DelegationProgress("d", 1, "e", artifact)
    result = DelegationResult("d", "t", "success", (artifact,), {"nested": {"x": 1}})
    feature = FeatureDescriptor("f", capabilities=("x",))

    assert artifact.as_dict() is not artifact.payload
    assert progress.as_dict()["artifact"] == artifact.as_dict()
    assert result.as_dict()["artifacts"] == [artifact.as_dict()]
    assert feature.as_dict()["capabilities"] == ["x"]


def test_command_ack_roundtrip_lossless():
    for ack in (
        CommandAck(command_id="c1", status="received", seq=7),
        CommandAck(command_id="c2", status="rejected", rejection_reason="unknown command_type"),
    ):
        assert CommandAck.from_dict(ack.as_dict()).as_dict() == ack.as_dict()


def test_task_loop_snapshot_roundtrip_preserves_agents_and_nested_type():
    snap = TaskLoopSnapshot(
        session_id="s1",
        status="in_discussion",
        round_no=2,
        orchestrator={"last_decision": "continue", "reason": "route to B"},
        agents=(
            AgentView(agent_id="A", role="planner", status="done", last_output_summary="ok"),
            AgentView(agent_id="B", status="running", context_packet={"briefing": "x"}),
        ),
        pending_agent_calls=({"agent_id": "B", "objective": "build", "target_kind": "agent"},),
        tool_calls=({"tool": "search", "status": "ok", "risk_level": None},),
        acceptance_status=({"id": "ac1", "text": "works", "status": "pending"},),
    )
    restored = TaskLoopSnapshot.from_dict(snap.as_dict())
    assert restored.as_dict() == snap.as_dict()
    assert isinstance(restored.agents[0], AgentView)


def test_taskloop_state_roundtrip_preserves_every_field_and_nested_type():
    state = TaskLoopState(
        session_id="session",
        task_id="task",
        status="in_discussion",
        selected_agents=["code", "test"],
        acceptance_checks=[AcceptanceCheck("ac1", "works", "passed", ["artifact-1"])],
        round_no=3,
        max_rounds=8,
        turns=[AgentTurn(2, "code", "packet-1", "ok", ["artifact-1"])],
        artifacts={"artifact-1": {"kind": "proof", "nested": {"x": 1}}},
        tool_results={"tool-1": {"ok": True, "data": {"x": 1}}},
        final_output={"answer": 42},
        reason="done",
    )
    decoded = decode_taskloop_state(encode_taskloop_state(state))
    assert encode_taskloop_state(decoded) == encode_taskloop_state(state)
    assert isinstance(decoded.acceptance_checks[0], AcceptanceCheck)
    assert isinstance(decoded.turns[0], AgentTurn)
