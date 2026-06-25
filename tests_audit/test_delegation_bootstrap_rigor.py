"""Adversarial rigor for delegation bootstrap/manager/policy/registry/store seams.

Complements tests/test_delegation.py and tests_audit/test_session_delegation_state_machine.py:
those pin happy-path persistence and the state machine; here we pin the composition
helper branches, the three manager guard raises, the policy depth limit, registry
ambiguity/no-match/concurrency, and store ordering/idempotency/thread-safety under load.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.bootstrap import build_kernel
from core.schemas import (
    ArtifactEnvelope,
    DelegationPolicy,
    DelegationProgress,
    DelegationRequest,
    DelegationResult,
    DelegationSpec,
)
from core.session import SessionFactory
from delegation.bootstrap import create_delegation_service
from delegation.manager import DelegationManager
from delegation.policy import DelegationPolicyEngine
from delegation.registry import DelegationRegistry
from delegation.store import InMemoryDelegationStore

ECHO = {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}


# ----- shared scaffolding -----------------------------------------------------


class _Handler:
    """Minimal DelegationPort double; prefix-matchers let us force ambiguity."""

    def __init__(self, name, *, matches=None, run=None):
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
    return build_kernel(ECHO)


def _request(delegation_id="d1", sequence_target="agent:test"):
    return DelegationRequest(
        delegation_id=delegation_id,
        parent_session_id="parent-session",
        parent_task_id="parent-task",
        target=sequence_target,
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


def _manager(run=None, *, target="agent:test"):
    kernel = _kernel()
    registry = DelegationRegistry()
    registry.register(_Handler(target, run=run))
    store = InMemoryDelegationStore()
    manager = DelegationManager(
        registry=registry,
        sessions=SessionFactory(kernel=kernel),
        store=store,
    )
    parent = SessionFactory(kernel=kernel).create_root("parent")
    return manager, parent, store


# ----- bootstrap composition helper (lines 14-20) -----------------------------


@pytest.mark.audit
def test_bootstrap_returns_none_when_delegation_disabled_or_section_absent():
    """No delegation section and an explicitly-disabled section both opt out (no side effects)."""
    assert create_delegation_service(build_kernel(ECHO)) is None
    assert create_delegation_service(build_kernel({**ECHO, "delegation": {}})) is None
    assert (
        create_delegation_service(build_kernel({**ECHO, "delegation": {"enabled": False}}))
        is None
    )


@pytest.mark.audit
def test_bootstrap_builds_default_local_target_with_general_fallback():
    """Enabled-but-target-unspecified composes a manager whose single target is agent:general."""
    service = create_delegation_service(build_kernel({**ECHO, "delegation": {"enabled": True}}))
    assert isinstance(service, DelegationManager)
    # Structurally conforms to the DelegationServicePort the rest of the system depends on
    # (the Protocol is not @runtime_checkable, so we duck-type its surface).
    assert callable(service.available_targets) and callable(service.delegate)
    assert service.available_targets() == ("agent:general",)


@pytest.mark.audit
@pytest.mark.parametrize("blank", ["", None])
def test_bootstrap_falls_back_to_general_when_default_target_is_blank(blank):
    """An empty/None default_target must still resolve to the canonical agent:general."""
    config = {**ECHO, "delegation": {"enabled": True, "default_target": blank}}
    service = create_delegation_service(build_kernel(config))
    assert service.available_targets() == ("agent:general",)


@pytest.mark.audit
def test_bootstrap_honours_explicit_custom_default_target():
    config = {**ECHO, "delegation": {"enabled": True, "default_target": "agent:review"}}
    service = create_delegation_service(build_kernel(config))
    assert service.available_targets() == ("agent:review",)
    # The registry the helper built is frozen by the manager — composition is one-shot.
    assert service.registry._frozen is True


@pytest.mark.audit
def test_bootstrap_registry_is_independent_per_call():
    """Two builds must not share registry/store state (no module-level singletons)."""
    config = {**ECHO, "delegation": {"enabled": True}}
    a = create_delegation_service(build_kernel(config))
    b = create_delegation_service(build_kernel(config))
    assert a is not b
    assert a.registry is not b.registry
    assert a.store is not b.store


# ----- manager guard raises (manager.py lines 71, 73, 75) ---------------------


@pytest.mark.audit
def test_manager_rejects_delegation_from_inactive_parent():
    """Line 71: a closed parent cannot spawn children — fail loud, no store/event side effects."""
    manager, parent, store = _manager()
    parent.complete_task({"done": True})
    assert parent.is_active is False

    with pytest.raises(RuntimeError, match="inactive parent"):
        manager.delegate(parent, "agent:test", DelegationSpec("work"))
    # Nothing was persisted: the guard fires before store.start().
    assert store.progress("anything") == ()


@pytest.mark.audit
def test_manager_rejects_empty_target():
    """Line 73: empty target is a programmer error, not a delegated failure."""
    manager, parent, _ = _manager()
    with pytest.raises(ValueError, match="target must not be empty"):
        manager.delegate(parent, "", DelegationSpec("work"))


@pytest.mark.audit
def test_manager_rejects_empty_objective():
    """Line 75: an empty objective is rejected before any session/child is created."""
    manager, parent, _ = _manager()
    with pytest.raises(ValueError, match="objective must not be empty"):
        manager.delegate(parent, "agent:test", DelegationSpec(""))


@pytest.mark.audit
def test_manager_guards_fire_before_any_durable_write_or_event():
    """The three input guards must short-circuit with zero observable side effects."""
    for target, spec in (("", DelegationSpec("x")), ("agent:test", DelegationSpec(""))):
        manager, parent, store = _manager()
        events = []
        parent.kernel.events.subscribe(lambda topic, payload: events.append(topic))
        with pytest.raises(ValueError):
            manager.delegate(parent, target, spec)
        assert not any(e.startswith("delegation.") for e in events)
        assert parent.is_active is True


# ----- policy engine: depth / budget / capability-scope subset ----------------


@pytest.mark.audit
@pytest.mark.security
def test_policy_depth_limit_exceeded_raises_permission_error():
    """policy.py line 24: parent.depth+1 > requested max_depth -> PermissionError."""
    factory = SessionFactory(kernel=_kernel())
    parent = factory.create_root("parent")
    child = factory.create_child(
        parent,
        delegation_id="d1",
        target="agent:child",
        user_request="c",
    )
    assert child.identity.depth == 1
    engine = DelegationPolicyEngine(max_steps=100, max_depth=8)
    # child is at depth 1; request max_depth=1 -> 1+1 > 1 -> depth limit exceeded.
    with pytest.raises(PermissionError, match="depth limit exceeded"):
        engine.validate(child, DelegationPolicy(max_depth=1))


@pytest.mark.audit
@pytest.mark.security
def test_policy_capability_scope_must_be_subset_of_parent():
    """Adversarial: requesting a capability the parent lacks is rejected (no privilege escalation)."""
    parent = SessionFactory(kernel=_kernel()).create_root(
        "parent", allowed_capabilities=frozenset({"echo"})
    )
    engine = DelegationPolicyEngine()
    with pytest.raises(PermissionError, match="capability scope exceeds"):
        engine.validate(parent, DelegationPolicy(allowed_capabilities=frozenset({"echo", "secret"})))


@pytest.mark.audit
def test_policy_scope_defaults_to_parent_when_unspecified():
    """An empty requested scope inherits the parent scope verbatim (frozen, not aliased)."""
    parent = SessionFactory(kernel=_kernel()).create_root(
        "parent", allowed_capabilities=frozenset({"echo"})
    )
    active = DelegationPolicyEngine().validate(parent, DelegationPolicy())
    assert active.allowed_capabilities == frozenset({"echo"})
    assert isinstance(active.allowed_capabilities, frozenset)


@pytest.mark.audit
def test_policy_none_request_is_treated_as_default_policy():
    """validate(parent, None) must not crash — it materialises a default DelegationPolicy."""
    parent = SessionFactory(kernel=_kernel()).create_root("parent")
    active = DelegationPolicyEngine().validate(parent, None)
    assert (active.max_steps, active.max_depth) == (
        DelegationPolicy().max_steps,
        DelegationPolicy().max_depth,
    )


@pytest.mark.audit
@pytest.mark.parametrize(
    ("steps", "depth", "exc", "match"),
    [
        (0, 3, ValueError, "max_steps must be"),
        (101, 3, ValueError, "max_steps must be"),
        (20, 0, ValueError, "max_depth must be"),
        (20, 9, ValueError, "max_depth must be"),
    ],
)
def test_policy_budget_bounds_are_enforced_at_both_edges(steps, depth, exc, match):
    """Budget exhaustion / out-of-range depth caps are rejected at every boundary."""
    parent = SessionFactory(kernel=_kernel()).create_root("parent")
    with pytest.raises(exc, match=match):
        DelegationPolicyEngine(max_steps=100, max_depth=8).validate(
            parent, DelegationPolicy(max_steps=steps, max_depth=depth)
        )


@pytest.mark.audit
@pytest.mark.property
@given(
    steps=st.integers(min_value=1, max_value=100),
    depth=st.integers(min_value=1, max_value=8),
)
def test_policy_property_in_bounds_requests_are_preserved(steps, depth):
    """Any in-bounds request at depth 0 round-trips its caps unchanged."""
    parent = SessionFactory(kernel=_kernel()).create_root(
        "parent", allowed_capabilities=frozenset({"echo"})
    )
    active = DelegationPolicyEngine(max_steps=100, max_depth=8).validate(
        parent,
        DelegationPolicy(max_steps=steps, max_depth=depth, allowed_capabilities=frozenset({"echo"})),
    )
    assert (active.max_steps, active.max_depth) == (steps, depth)
    assert active.allowed_capabilities <= parent.allowed_capabilities


# ----- registry: ambiguity / no-match / freeze / duplicate / concurrency ------


@pytest.mark.audit
def test_registry_ambiguous_target_names_both_matches_explicitly():
    """Two handlers claiming the same target -> LookupError naming the sorted colliding handlers."""
    registry = DelegationRegistry()
    registry.register(_Handler("agent:zeta", matches=lambda t: t.startswith("agent:")))
    registry.register(_Handler("agent:alpha", matches=lambda t: t.startswith("agent:")))
    with pytest.raises(LookupError, match=r"Ambiguous delegation target 'agent:any'"):
        registry.resolve("agent:any")
    # Error message lists names sorted, so the adversary cannot rely on insertion order.
    try:
        registry.resolve("agent:any")
    except LookupError as exc:
        assert "['agent:alpha', 'agent:zeta']" in str(exc)


@pytest.mark.audit
def test_registry_no_match_is_explicit_lookup_error():
    registry = DelegationRegistry()
    registry.register(_Handler("agent:only"))
    with pytest.raises(LookupError, match="No delegation handler registered for target 'ghost'"):
        registry.resolve("ghost")


@pytest.mark.audit
def test_registry_duplicate_name_rejected_and_targets_sorted():
    registry = DelegationRegistry()
    registry.register(_Handler("agent:b"))
    registry.register(_Handler("agent:a"))
    with pytest.raises(ValueError, match="already registered: agent:a"):
        registry.register(_Handler("agent:a"))
    assert registry.targets() == ("agent:a", "agent:b")


@pytest.mark.audit
def test_registry_freeze_blocks_further_registration_and_is_idempotent():
    registry = DelegationRegistry()
    registry.register(_Handler("agent:a"))
    registry.freeze()
    registry.freeze()  # idempotent — second freeze must not raise
    with pytest.raises(RuntimeError, match="frozen"):
        registry.register(_Handler("agent:b"))
    # Resolution still works after freeze.
    assert registry.resolve("agent:a").name == "agent:a"


@pytest.mark.audit
def test_registry_unique_exact_match_resolves_even_amid_non_matching_handlers():
    registry = DelegationRegistry()
    registry.register(_Handler("agent:a"))
    registry.register(_Handler("agent:b"))
    registry.register(_Handler("agent:c"))
    assert registry.resolve("agent:b").name == "agent:b"


@pytest.mark.audit
@pytest.mark.concurrency
def test_registry_concurrent_registration_serialises_without_corruption():
    """Many threads register distinct handlers; the lock guarantees no lost/duplicated entries."""
    registry = DelegationRegistry()
    names = [f"agent:{i:03d}" for i in range(200)]

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda name: registry.register(_Handler(name)), names))

    assert registry.targets() == tuple(sorted(names))


@pytest.mark.audit
@pytest.mark.concurrency
def test_registry_concurrent_duplicate_registration_yields_exactly_one_winner():
    """If many threads race to register the same name, exactly one wins, the rest raise."""
    registry = DelegationRegistry()
    errors = []

    def register():
        try:
            registry.register(_Handler("agent:dup"))
        except ValueError as exc:
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda _: register(), range(16)))

    assert registry.targets() == ("agent:dup",)
    assert len(errors) == 15


# ----- store: ordering / idempotency / thread-safety --------------------------


@pytest.mark.audit
def test_store_progress_is_ordered_and_sequence_strict():
    store = InMemoryDelegationStore()
    store.start(_request())
    store.append_progress(_progress(sequence=1, event_id="e1"))
    store.append_progress(_progress(sequence=2, event_id="e2"))
    store.append_progress(_progress(sequence=3, event_id="e3"))
    assert [p.sequence for p in store.progress("d1")] == [1, 2, 3]
    # A gap (skipping 4 -> 5) is rejected: the store is the ordering source of truth.
    with pytest.raises(ValueError, match="must be 4"):
        store.append_progress(_progress(sequence=5, event_id="e5"))


@pytest.mark.audit
def test_store_duplicate_event_id_is_idempotent_no_op_even_with_wrong_sequence():
    """Re-delivery of a known event_id is dropped before the sequence check (at-least-once safe)."""
    store = InMemoryDelegationStore()
    store.start(_request())
    store.append_progress(_progress(sequence=1, event_id="e1"))
    # Same event_id, wrong sequence -> still a no-op, never an error.
    store.append_progress(_progress(sequence=99, event_id="e1"))
    assert store.progress("d1") == (_progress(sequence=1, event_id="e1"),)


@pytest.mark.audit
def test_store_unknown_delegation_progress_and_finish_raise():
    store = InMemoryDelegationStore()
    with pytest.raises(LookupError, match="Unknown delegation"):
        store.append_progress(_progress())
    with pytest.raises(LookupError, match="Unknown delegation"):
        store.finish(DelegationResult("nope", "parent-task", "success"))
    assert store.progress("nope") == ()
    assert store.result("nope") is None


@pytest.mark.audit
def test_store_duplicate_start_rejected():
    store = InMemoryDelegationStore()
    store.start(_request())
    with pytest.raises(ValueError, match="already exists"):
        store.start(_request())


@pytest.mark.audit
def test_store_finish_is_idempotent_for_equal_results_but_rejects_conflicts():
    store = InMemoryDelegationStore()
    store.start(_request())
    first = DelegationResult("d1", "parent-task", "success")
    store.finish(first)
    store.finish(first)  # identical -> idempotent
    assert store.result("d1") == first
    with pytest.raises(ValueError, match="different result"):
        store.finish(DelegationResult("d1", "parent-task", "failed", error="changed"))


@pytest.mark.audit
@pytest.mark.concurrency
def test_store_concurrent_sequential_then_redelivery_preserves_count_and_order():
    """One logical producer feeds strict-sequence events; many threads re-deliver as no-ops.

    The store enforces a strict next-sequence under its lock, so a single monotonic
    producer is the only valid writer. We then hammer with concurrent re-deliveries of
    already-seen events to prove the idempotency path is also lock-serialised.
    """
    store = InMemoryDelegationStore()
    store.start(_request())
    total = 300

    for seq in range(1, total + 1):
        store.append_progress(_progress(sequence=seq, event_id=f"e{seq}"))

    def redeliver(seq):
        store.append_progress(_progress(sequence=seq, event_id=f"e{seq}"))

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(redeliver, [s for s in range(1, total + 1) for _ in range(3)]))

    items = store.progress("d1")
    assert len(items) == total
    assert [p.sequence for p in items] == list(range(1, total + 1))
    assert len({p.event_id for p in items}) == total


@pytest.mark.audit
@pytest.mark.concurrency
def test_store_concurrent_duplicate_progress_is_idempotent_under_load():
    """Many threads append the SAME progress; exactly one lands (no dup, no error)."""
    store = InMemoryDelegationStore()
    store.start(_request())
    progress = _progress()

    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(lambda _: store.append_progress(progress), range(1000)))

    assert store.progress("d1") == (progress,)


@pytest.mark.audit
def test_store_isolates_progress_streams_per_delegation():
    """Two delegations never bleed into each other's progress log."""
    store = InMemoryDelegationStore()
    store.start(_request("d1"))
    store.start(_request("d2"))
    store.append_progress(_progress("d1", 1, "d1e1"))
    store.append_progress(_progress("d2", 1, "d2e1"))
    assert [p.event_id for p in store.progress("d1")] == ["d1e1"]
    assert [p.event_id for p in store.progress("d2")] == ["d2e1"]


# ----- end-to-end: manager converts policy reject to durable 'rejected' -------


@pytest.mark.audit
@pytest.mark.security
def test_manager_scope_expansion_is_rejected_and_stored_durably():
    """A child demanding capabilities the parent lacks is rejected + recorded, never executed."""
    kernel = _kernel()
    registry = DelegationRegistry()
    ran = []
    registry.register(_Handler("agent:test", run=lambda *_: ran.append(True)))
    store = InMemoryDelegationStore()
    manager = DelegationManager(registry=registry, sessions=SessionFactory(kernel=kernel), store=store)
    parent = SessionFactory(kernel=kernel).create_root("parent", allowed_capabilities=frozenset({"echo"}))

    result = manager.delegate(
        parent,
        "agent:test",
        DelegationSpec("x"),
        DelegationPolicy(allowed_capabilities=frozenset({"echo", "secret"})),
    )
    assert result.outcome == "rejected"
    assert "scope exceeds" in result.error
    assert store.result(result.delegation_id) == result
    assert ran == []  # handler never ran — rejection happens before resolve()
    assert parent.is_active is True
