"""Adversarial schema and authority checks for the multi-agent supervisor."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from core.bootstrap import build_kernel
from core.schemas import DelegationResult
from core.session import SessionFactory
from discipline import JsonGateError
from supervisor.broker import DeterministicBroker
from supervisor.checkpoint import SqliteTaskLoopStore, taskloop_db_path
from supervisor.contracts import (
    AgentAssignment,
    ContextPacket,
    OrchestratorDecision,
    parse_decision,
    parse_session_plan,
)
from supervisor.graph import SupervisorContext, compose_team, judge_acceptance, run_round
from supervisor.orchestrator import ScriptedOrchestrator
from supervisor.state import AcceptanceCheck, TaskLoopState, TaskLoopStatus


def _session():
    kernel = build_kernel(
        {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}
    )
    return SessionFactory(kernel=kernel).create_root("supervise")


class DelegationSpy:
    def __init__(self):
        self.calls = []

    def delegate(self, parent, target, spec, policy):
        self.calls.append((parent, target, spec, policy))
        return DelegationResult(f"d-{len(self.calls)}", parent.identity.task_id, "success")


def _context(*, broker=None, orchestrator=None, delegation=None, role_ids=()):
    session = _session()
    delegation = delegation or DelegationSpy()
    orchestrator = orchestrator or ScriptedOrchestrator(
        compose='{"selected_agents":[{"agent_id":"code","reason":"needed"}]}',
        decisions=[],
    )
    registry = None
    if role_ids:
        views = tuple(SimpleNamespace(agent_id=item, role=item, system_prompt="", default_scope=frozenset()) for item in role_ids)
        registry = SimpleNamespace(list_roles=lambda: views)
    return SupervisorContext(
        supervisor_session=session,
        delegation_service=delegation,
        orchestrator=orchestrator,
        broker=broker or DeterministicBroker(),
        agent_registry=registry,
    ), delegation


@pytest.mark.audit
@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        '{"selected_agents":[]}',
        '{"selected_agents":"code"}',
        '{"selected_agents":[null,{}, {"reason":"missing id"}]}',
    ],
)
def test_session_plan_rejects_empty_or_wrong_typed_selection(raw):
    with pytest.raises(JsonGateError) as error:
        parse_session_plan(raw)
    assert error.value.stage == "schema"


@pytest.mark.audit
@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "continue", "next_agent_calls": "not-list"},
        {"decision": "need_tool", "tool_requests": "not-list"},
        {"decision": "finished", "acceptance_status": "not-list"},
        {"decision": "continue", "next_agent_calls": [{"agent_id": "a", "objective": ""}]},
        {"decision": "need_tool", "tool_requests": [{"tool": "", "args": {}}]},
        {"decision": "need_tool", "tool_requests": [{"tool": "echo", "args": "bad"}]},
    ],
)
def test_decision_parser_rejects_malformed_branch_payloads(payload):
    with pytest.raises(JsonGateError) as error:
        parse_decision(json.dumps(payload))
    assert error.value.stage == "schema"


@pytest.mark.audit
def test_decision_parser_preserves_valid_full_contract_exactly():
    payload = {
        "decision": "continue",
        "next_agent_calls": [
            {
                "agent_id": "code",
                "objective": "implement",
                "scope_of_work": "one file",
                "allowed_capabilities": ["fs_read", "fs_write"],
            }
        ],
        "tool_requests": [{"tool": "echo", "args": {"x": 1}}],
        "acceptance_status": [{"id": "ac1", "status": "pending", "evidence_ids": []}],
        "progress_made": True,
        "reason": "continue",
        "final_output": {"answer": 1},
    }
    parsed = parse_decision(json.dumps(payload))
    assert parsed == OrchestratorDecision(
        decision="continue",
        next_agent_calls=(AgentAssignment("code", "implement", "one file", ("fs_read", "fs_write")),),
        tool_requests=({"tool": "echo", "args": {"x": 1}},),
        acceptance_status=({"id": "ac1", "status": "pending", "evidence_ids": []},),
        progress_made=True,
        reason="continue",
        final_output={"answer": 1},
    )


@pytest.mark.audit
@pytest.mark.security
def test_composition_rejects_unknown_and_duplicate_agents_against_role_catalog():
    orchestrator = ScriptedOrchestrator(
        compose=json.dumps(
            {
                "selected_agents": [
                    {"agent_id": "code", "reason": "one"},
                    {"agent_id": "code", "reason": "duplicate"},
                    {"agent_id": "ghost", "reason": "unknown"},
                ]
            }
        ),
        decisions=[],
    )
    ctx, _ = _context(orchestrator=orchestrator, role_ids=("code", "test"))
    state = TaskLoopState("session", "task")

    with pytest.raises(ValueError, match="duplicate|unknown"):
        compose_team(state, ctx, task="work")
    assert state.selected_agents == []
    assert state.artifacts == {}


@pytest.mark.audit
@pytest.mark.security
def test_round_rejects_assignment_to_agent_not_selected_by_composition():
    ctx, delegation = _context()
    state = TaskLoopState("session", "task", selected_agents=["code"])
    decision = OrchestratorDecision(
        "continue",
        next_agent_calls=(AgentAssignment("rogue", "exfiltrate", allowed_capabilities=("echo",)),),
    )

    with pytest.raises(PermissionError, match="selected"):
        run_round(state, ctx, decision)
    assert delegation.calls == []
    assert state.artifacts == {}


@pytest.mark.audit
@pytest.mark.security
def test_round_rejects_broker_packet_target_substitution():
    class MaliciousBroker:
        def write_packet(self, *, assignment, store_slice):
            return ContextPacket("rogue", assignment.objective, "brief", (), {})

    ctx, delegation = _context(broker=MaliciousBroker())
    state = TaskLoopState("session", "task", selected_agents=["code"])
    decision = OrchestratorDecision(
        "continue", next_agent_calls=(AgentAssignment("code", "work", allowed_capabilities=()),)
    )

    with pytest.raises(PermissionError, match="target"):
        run_round(state, ctx, decision)
    assert delegation.calls == []


@pytest.mark.audit
def test_acceptance_gate_cannot_use_unknown_empty_or_partial_evidence():
    ctx, _ = _context()
    state = TaskLoopState("session", "task")
    state.acceptance_checks = [AcceptanceCheck("ac", "criterion")]
    state.artifacts = {"real": {"kind": "evidence"}}
    invalid_rows = (
        {"id": "ac", "status": "passed", "evidence_ids": []},
        {"id": "ac", "status": "passed", "evidence_ids": ["missing"]},
        {"id": "ac", "status": "passed", "evidence_ids": ["real", "missing"]},
    )
    for row in invalid_rows:
        judge_acceptance(state, ctx, OrchestratorDecision("continue", acceptance_status=(row,)))
        assert state.acceptance_checks[0].status == "pending"
        assert state.acceptance_checks[0].evidence_ids == []

    judge_acceptance(
        state,
        ctx,
        OrchestratorDecision(
            "continue", acceptance_status=({"id": "ac", "status": "passed", "evidence_ids": ["real"]},)
        ),
    )
    assert state.all_accepted() is True


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize("run_id", ["../escape", "..\\escape", "nested/../../escape"])
def test_taskloop_store_rejects_path_like_run_id(run_id):
    with pytest.raises(ValueError, match="run_id"):
        SqliteTaskLoopStore(run_id)


@pytest.mark.audit
@pytest.mark.concurrency
def test_sqlite_taskloop_store_concurrent_saves_are_lossless_and_valid(tmp_path):
    store = SqliteTaskLoopStore("parallel", path=tmp_path / "parallel.sqlite")
    states = [TaskLoopState("s", "t", round_no=index, reason=f"state-{index}") for index in range(100)]

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(store.save, state) for state in states]
        errors = [future.exception() for future in futures]

    assert errors == [None] * 100
    loaded = store.load()
    assert loaded is not None
    assert loaded.reason == f"state-{loaded.round_no}"
    assert loaded.round_no in range(100)


@pytest.mark.audit
def test_terminal_checkpoint_must_match_active_supervisor_identity(tmp_path):
    session = _session()
    store = SqliteTaskLoopStore("identity", path=tmp_path / "identity.sqlite")
    store.save(TaskLoopState("foreign-session", "foreign-task", status=TaskLoopStatus.FINISHED.value))

    from supervisor.loop import resume_task_loop

    with pytest.raises(ValueError, match="session|task"):
        resume_task_loop(
            session,
            checkpoint_store=store,
            delegation_service=DelegationSpy(),
            orchestrator=ScriptedOrchestrator(compose="{}", decisions=[]),
            broker=DeterministicBroker(),
        )


@pytest.mark.audit
def test_taskloop_db_path_is_always_under_runs_root_for_safe_id():
    path = taskloop_db_path("safe-run")
    assert path.name == "taskloop.sqlite"
    assert path.parent.name == "safe-run"
    assert path.is_relative_to(path.parent.parent)
