"""Lifecycle, scope, ordering and idempotency checks for sessions/delegation."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from core.bootstrap import build_kernel
from core.schemas import (
    ArtifactEnvelope,
    DelegationPolicy,
    DelegationProgress,
    DelegationRequest,
    DelegationResult,
    DelegationSpec,
)
from core.session import SessionFactory, SessionIdentity
from delegation.manager import DelegationManager
from delegation.policy import DelegationPolicyEngine
from delegation.registry import DelegationRegistry
from delegation.store import InMemoryDelegationStore


ECHO_CONFIG = {
    "features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}
}


class Handler:
    def __init__(self, name="agent:test", *, matches=None, run=None):
        self.name = name
        self._matches = matches or (lambda target: target == name)
        self._run = run

    def can_handle(self, target):
        return self._matches(target)

    def run(self, request, child, progress):
        if self._run is not None:
            return self._run(request, child, progress)
        return DelegationResult(request.delegation_id, request.parent_task_id, "success")


def _kernel():
    return build_kernel(ECHO_CONFIG)


def _request(delegation_id="d1"):
    return DelegationRequest(
        delegation_id=delegation_id,
        parent_session_id="parent-session",
        parent_task_id="parent-task",
        target="agent:test",
        spec=DelegationSpec("objective"),
        policy=DelegationPolicy(),
    )


def _progress(delegation_id="d1", sequence=1, event_id="e1"):
    return DelegationProgress(
        delegation_id=delegation_id,
        sequence=sequence,
        event_id=event_id,
        artifact=ArtifactEnvelope(f"a-{event_id}", "finding", {"sequence": sequence}),
    )


@pytest.mark.audit
def test_root_session_identity_and_state_are_unique_under_load():
    factory = SessionFactory(kernel=_kernel())
    sessions = [factory.create_root(f"task-{index}", run_id=f"run-{index}") for index in range(250)]

    assert len({item.identity.session_id for item in sessions}) == 250
    assert len({item.identity.task_id for item in sessions}) == 250
    assert [item.identity.run_id for item in sessions] == [f"run-{index}" for index in range(250)]
    assert all(item.is_active for item in sessions)


@pytest.mark.audit
@pytest.mark.security
def test_explicit_empty_child_scope_means_deny_all_not_inherit_all():
    factory = SessionFactory(kernel=_kernel())
    parent = factory.create_root("parent", allowed_capabilities=frozenset({"echo"}))

    child = factory.create_child(
        parent,
        delegation_id="d1",
        target="agent:locked-down",
        user_request="child",
        requested_scope=frozenset(),
    )

    assert child.allowed_capabilities == frozenset()
    denied = child.execute_tool("echo", {"value": "must not run"})
    assert denied["ok"] is False
    assert denied["metadata"]["scope_block"] is True


@pytest.mark.audit
def test_closed_session_rejects_tools_and_second_terminal_transition():
    session = SessionFactory(kernel=_kernel()).create_root("task")
    outcome = session.complete_task({"done": True})

    assert outcome["status"] == "completed"
    assert session.is_active is False
    blocked = session.execute_tool("echo", {"value": 1})
    assert blocked["ok"] is False
    assert blocked["metadata"]["session_closed"] is True
    with pytest.raises(RuntimeError, match="already closed"):
        session.fail_task("late failure")


@pytest.mark.audit
def test_restore_rejects_unknown_capabilities_and_marks_terminal_state_closed():
    factory = SessionFactory(kernel=_kernel())
    identity = SessionIdentity("s", "r", "t", "agent:root")
    with pytest.raises(ValueError, match="unavailable"):
        factory.restore(identity=identity, state={}, allowed_capabilities=frozenset({"missing"}))

    restored = factory.restore(identity=identity, state={"current_task": None}, allowed_capabilities=frozenset())
    assert restored.is_active is False
    assert restored.execute_tool("echo")["metadata"]["session_closed"] is True


@pytest.mark.audit
@pytest.mark.parametrize(
    ("policy", "exception"),
    [
        (DelegationPolicy(max_steps=0), ValueError),
        (DelegationPolicy(max_steps=101), ValueError),
        (DelegationPolicy(max_depth=0), ValueError),
        (DelegationPolicy(max_depth=9), ValueError),
        (DelegationPolicy(allowed_capabilities=frozenset({"missing"})), PermissionError),
    ],
)
def test_delegation_policy_rejects_every_out_of_bounds_dimension(policy, exception):
    parent = SessionFactory(kernel=_kernel()).create_root("parent")
    with pytest.raises(exception):
        DelegationPolicyEngine(max_steps=100, max_depth=8).validate(parent, policy)


@pytest.mark.audit
def test_delegation_policy_boundaries_are_inclusive_and_scope_is_preserved():
    parent = SessionFactory(kernel=_kernel()).create_root("parent", allowed_capabilities=frozenset({"echo"}))
    engine = DelegationPolicyEngine(max_steps=100, max_depth=8)

    low = engine.validate(parent, DelegationPolicy(max_steps=1, max_depth=1, allowed_capabilities=frozenset({"echo"})))
    high = engine.validate(parent, DelegationPolicy(max_steps=100, max_depth=8, allowed_capabilities=frozenset({"echo"})))

    assert (low.max_steps, low.max_depth, low.allowed_capabilities) == (1, 1, frozenset({"echo"}))
    assert (high.max_steps, high.max_depth, high.allowed_capabilities) == (100, 8, frozenset({"echo"}))


@pytest.mark.audit
def test_delegation_registry_duplicate_freeze_missing_and_ambiguity_contracts():
    registry = DelegationRegistry()
    registry.register(Handler("agent:first", matches=lambda target: target.startswith("agent:")))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(Handler("agent:first"))
    registry.register(Handler("agent:second", matches=lambda target: target.startswith("agent:")))
    assert registry.targets() == ("agent:first", "agent:second")
    with pytest.raises(LookupError, match="Ambiguous"):
        registry.resolve("agent:any")
    with pytest.raises(LookupError, match="No delegation handler"):
        registry.resolve("other")
    registry.freeze()
    with pytest.raises(RuntimeError, match="frozen"):
        registry.register(Handler("agent:late"))


@pytest.mark.audit
@pytest.mark.concurrency
def test_store_duplicate_progress_is_idempotent_under_concurrency():
    store = InMemoryDelegationStore()
    store.start(_request())
    progress = _progress()

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda _: store.append_progress(progress), range(500)))

    assert store.progress("d1") == (progress,)


@pytest.mark.audit
def test_store_rejects_unknown_out_of_order_duplicate_start_and_conflicting_result():
    store = InMemoryDelegationStore()
    with pytest.raises(LookupError, match="Unknown delegation"):
        store.append_progress(_progress())
    with pytest.raises(LookupError, match="Unknown delegation"):
        store.finish(DelegationResult("d1", "parent-task", "success"))

    request = _request()
    store.start(request)
    with pytest.raises(ValueError, match="already exists"):
        store.start(request)
    with pytest.raises(ValueError, match="must be 1"):
        store.append_progress(_progress(sequence=2))

    first = DelegationResult("d1", "parent-task", "success")
    store.finish(first)
    store.finish(first)
    assert store.result("d1") == first
    with pytest.raises(ValueError, match="different result"):
        store.finish(DelegationResult("d1", "parent-task", "failed", error="changed"))


def _manager(run):
    kernel = _kernel()
    registry = DelegationRegistry()
    registry.register(Handler(run=run))
    store = InMemoryDelegationStore()
    manager = DelegationManager(
        registry=registry,
        sessions=SessionFactory(kernel=kernel),
        store=store,
    )
    parent = SessionFactory(kernel=kernel).create_root("parent")
    return manager, parent, store


@pytest.mark.audit
@pytest.mark.parametrize("corruption", ["progress_id", "result_id", "parent_task_id", "handler_exception"])
def test_manager_converts_handler_protocol_corruption_to_durable_failure(corruption):
    def run(request, child, progress):
        if corruption == "progress_id":
            progress(_progress(delegation_id="wrong"))
        if corruption == "result_id":
            return DelegationResult("wrong", request.parent_task_id, "success")
        if corruption == "parent_task_id":
            return DelegationResult(request.delegation_id, "wrong", "success")
        if corruption == "handler_exception":
            raise RuntimeError("handler exploded")
        raise AssertionError("unreachable")

    manager, parent, store = _manager(run)
    result = manager.delegate(parent, "agent:test", DelegationSpec("work"))

    assert result.outcome == "failed"
    assert result.error
    assert store.result(result.delegation_id) == result
    assert parent.is_active is True


@pytest.mark.audit
def test_manager_enforces_progress_budget_without_losing_prior_artifacts():
    def run(request, child, progress):
        progress(_progress(request.delegation_id, 1, "one"))
        progress(_progress(request.delegation_id, 2, "two"))
        return DelegationResult(request.delegation_id, request.parent_task_id, "success")

    manager, parent, store = _manager(run)
    result = manager.delegate(
        parent,
        "agent:test",
        DelegationSpec("work"),
        DelegationPolicy(max_steps=1, allowed_capabilities=frozenset({"echo"})),
    )

    assert result.outcome == "failed"
    assert "exceeded max_steps" in result.error
    assert [item.artifact_id for item in result.artifacts] == ["a-one"]
    assert store.result(result.delegation_id) == result
