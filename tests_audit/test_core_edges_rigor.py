"""Edge/boundary rigor for the core runtime: middleware protocol, session lifecycle
error branches, schema contract corners, deep-freeze container kinds, and registry/state/event
edges. Complements tests/test_kernel.py, tests/test_session.py, tests/test_state.py,
tests_audit/test_kernel_registry_adversarial.py and ...contract_roundtrips.py (does not duplicate)."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.events import EventBus
from core.kernel import AgentKernel, _deep_freeze
from core.middleware import ToolHandler
from core.registry import CapabilityRegistry, NullToolPort
from core.schemas import (
    DelegationPolicy,
    DelegationRequest,
    DelegationSpec,
    ToolRequest,
)
from core.session import SessionFactory
from core.state import StateStore

pytestmark = pytest.mark.audit

ECHO = {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}
ENVELOPE_KEYS = {"ok", "capability", "feature", "data", "error", "metadata"}


def _empty_kernel() -> AgentKernel:
    from core.bootstrap import build_kernel

    return build_kernel({"features": {}})


def _echo_kernel() -> AgentKernel:
    from core.bootstrap import build_kernel

    return build_kernel(ECHO)


# --------------------------------------------------------------------------------------
# core/middleware.py — the ToolMiddleware Protocol (lines 2-11) is structurally satisfiable.
# It is NOT runtime_checkable, so we PROVE conformance by USING a minimal class through the
# kernel's middleware chain (which calls __call__(request, nxt)) — exercising the module.
# --------------------------------------------------------------------------------------


class RecordingMiddleware:
    """A minimal structural subtype of ToolMiddleware: only __call__(request, nxt)."""

    def __init__(self) -> None:
        self.pre: list[str] = []
        self.post: list[bool] = []

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict:
        # WHY: act BEFORE (pre), delegate to inner handler, then act AFTER (post).
        self.pre.append(request.name)
        result = nxt(request)
        self.post.append(bool(result.get("ok")))
        result.setdefault("metadata", {})["mw_touched"] = True
        return result


def test_tool_middleware_protocol_is_satisfiable_and_runs_pre_post():
    """A plain class implementing only __call__ is a structural ToolMiddleware and the
    kernel drives it around execute_tool — pins core/middleware.py contract."""
    kernel = _echo_kernel()
    mw = RecordingMiddleware()
    kernel.use(mw)
    result = kernel.execute_tool("echo", {"x": 1})

    assert result["ok"] is True
    assert mw.pre == ["echo"]          # acted before the inner handler
    assert mw.post == [True]           # observed the result after
    assert result["metadata"]["mw_touched"] is True


def test_tool_middleware_can_short_circuit_without_calling_next():
    """The Protocol docstring promises short-circuit: a middleware may return WITHOUT
    calling nxt. The inner tool must then never execute."""
    kernel = _empty_kernel()

    class ExplodingTool:
        name = "must_not_run"

        def execute(self, request):  # pragma: no cover - asserts it is never reached
            raise AssertionError("short-circuited middleware must skip the inner tool")

    kernel.registry.register_tool("guarded", ExplodingTool())

    def short_circuit(request: ToolRequest, nxt: ToolHandler) -> dict:
        return {"ok": False, "capability": request.name, "feature": None,
                "data": {}, "error": "blocked", "metadata": {"short_circuit": True}}

    kernel.use(short_circuit)
    result = kernel.execute_tool("guarded")
    assert result["ok"] is False
    assert result["metadata"]["short_circuit"] is True


def test_tool_middleware_registration_order_is_outer_to_inner():
    """Two middlewares: registration order = outer -> inner. The outer one wraps the inner,
    so its 'pre' runs first and its 'post' runs last (LIFO unwind)."""
    kernel = _echo_kernel()
    order: list[str] = []

    def outer(request: ToolRequest, nxt: ToolHandler) -> dict:
        order.append("outer:pre")
        out = nxt(request)
        order.append("outer:post")
        return out

    def inner(request: ToolRequest, nxt: ToolHandler) -> dict:
        order.append("inner:pre")
        out = nxt(request)
        order.append("inner:post")
        return out

    kernel.use(outer)
    kernel.use(inner)
    kernel.execute_tool("echo", {"a": 1})
    assert order == ["outer:pre", "inner:pre", "inner:post", "outer:post"]


# --------------------------------------------------------------------------------------
# core/session.py — the missing error branches (115-116, 159) + isolation invariants.
# --------------------------------------------------------------------------------------


def test_root_session_unknown_capability_is_rejected_with_sorted_names():
    """session.py 114-116: requesting a capability the registry does not expose raises
    ValueError listing the unknown names (sorted, deterministic)."""
    kernel = _echo_kernel()
    factory = SessionFactory(kernel=kernel)
    with pytest.raises(ValueError, match="unknown capabilities") as exc:
        factory.create_root("x", allowed_capabilities=frozenset({"zzz_unknown", "aaa_unknown"}))
    # sorted -> aaa before zzz, regardless of frozenset iteration order
    assert "['aaa_unknown', 'zzz_unknown']" in str(exc.value)


def test_root_session_partial_unknown_capability_still_rejected():
    """Boundary: one known + one unknown is still a rejection (subset check, not intersection)."""
    kernel = _echo_kernel()
    factory = SessionFactory(kernel=kernel)
    with pytest.raises(ValueError, match="unknown capabilities"):
        factory.create_root("x", allowed_capabilities=frozenset({"echo", "ghost"}))


def test_root_session_exact_available_subset_is_accepted():
    """Off-by-one complement to the rejection: requesting exactly an available subset succeeds
    and the scope is honored verbatim (not widened to all)."""
    kernel = _echo_kernel()
    session = SessionFactory(kernel=kernel).create_root(
        "x", allowed_capabilities=frozenset({"echo"})
    )
    assert session.allowed_capabilities == frozenset({"echo"})


def test_root_session_none_scope_means_all_available():
    """None requested scope inherits every registered capability (line 113 path)."""
    kernel = _echo_kernel()
    session = SessionFactory(kernel=kernel).create_root("x", allowed_capabilities=None)
    assert "echo" in session.allowed_capabilities


def test_create_child_from_inactive_parent_raises():
    """session.py 158-159: a completed/closed parent cannot spawn children."""
    kernel = _echo_kernel()
    factory = SessionFactory(kernel=kernel)
    parent = factory.create_root("parent", allowed_capabilities=frozenset({"echo"}))
    parent.complete_task("done")  # parent is now closed/inactive
    assert parent.is_active is False
    with pytest.raises(RuntimeError, match="inactive parent"):
        factory.create_child(
            parent, delegation_id="d1", target="agent:child", user_request="child"
        )


def test_child_empty_scope_is_deny_all_not_inherit():
    """An explicit empty requested_scope means DENY ALL (must not silently widen to parent).
    Pins the comment-documented invariant at session.py 160-162."""
    kernel = _echo_kernel()
    factory = SessionFactory(kernel=kernel)
    parent = factory.create_root("parent", allowed_capabilities=frozenset({"echo"}))
    child = factory.create_child(
        parent, delegation_id="d1", target="agent:child",
        user_request="child", requested_scope=frozenset(),
    )
    assert child.allowed_capabilities == frozenset()
    blocked = child.execute_tool("echo", {"x": 1})
    assert blocked["ok"] is False
    assert blocked["metadata"]["scope_block"] is True


def test_inactive_session_execute_tool_returns_closed_envelope_not_raise():
    """execute_tool on a closed session returns a well-formed failure envelope (not an
    exception), carrying session_closed=True (session.py 76-84)."""
    kernel = _echo_kernel()
    session = SessionFactory(kernel=kernel).create_root("x")
    session.complete_task("done")
    env = session.execute_tool("echo", {"x": 1})
    assert set(env) == ENVELOPE_KEYS
    assert env["ok"] is False
    assert env["metadata"]["session_closed"] is True
    assert env["error"] == "Session is not active."


def test_complete_task_twice_raises_runtime_error():
    """fail/complete on an already-closed lifecycle is a hard error (idempotency boundary)."""
    kernel = _echo_kernel()
    session = SessionFactory(kernel=kernel).create_root("x")
    session.complete_task("first")
    with pytest.raises(RuntimeError, match="already closed"):
        session.complete_task("second")
    with pytest.raises(RuntimeError, match="already closed"):
        session.fail_task("boom")


def test_fail_task_publishes_task_failed_with_reason():
    """fail_task routes through complete_task(status='failed') and emits task.failed."""
    kernel = _echo_kernel()
    topics: list[str] = []
    kernel.events.subscribe(lambda t, p: topics.append(t))
    session = SessionFactory(kernel=kernel).create_root("x")
    outcome = session.fail_task("nope", code=7)
    assert outcome["status"] == "failed"
    assert outcome["result"] == {"reason": "nope", "code": 7}
    assert "task.failed" in topics
    assert session.is_active is False


def test_sessions_do_not_leak_state_across_lifecycle_and_completion():
    """Per-run state isolation holds even across completion: closing one session leaves the
    other's live task untouched. Complements the threaded isolation test in tests/."""
    kernel = _echo_kernel()
    factory = SessionFactory(kernel=kernel)
    a = factory.create_root("a")
    b = factory.create_root("b")
    a.state.set("secret", [1, 2, 3])
    a.complete_task("done")
    # b never saw a's state and is still active with its own task
    assert b.state.get("secret") is None
    assert b.is_active is True
    assert a.is_active is False
    assert a.state.get("last_result")["status"] == "completed"


# --------------------------------------------------------------------------------------
# core/schemas.py — DelegationRequest.as_dict (line 191) + a property round-trip on the
# nested Spec/Policy contracts (those already have from_dict; we pin nesting integrity).
# --------------------------------------------------------------------------------------


def test_delegation_request_as_dict_nests_spec_and_policy_and_is_detached():
    """schemas.py 190-198: as_dict serializes nested spec/policy via their own as_dict, and
    the nested dicts are detached copies (mutating them must not corrupt the source dataclass)."""
    spec = DelegationSpec(
        objective="ship",
        input_context={"k": "v"},
        expected_output_schema={"type": "object"},
        constraints=("no-net",),
    )
    policy = DelegationPolicy(max_steps=5, max_depth=2, allowed_capabilities=frozenset({"echo"}))
    req = DelegationRequest(
        delegation_id="dlg-1",
        parent_session_id="psess",
        parent_task_id="ptask",
        target="agent:worker",
        spec=spec,
        policy=policy,
    )
    out = req.as_dict()
    assert out == {
        "delegation_id": "dlg-1",
        "parent_session_id": "psess",
        "parent_task_id": "ptask",
        "target": "agent:worker",
        "spec": spec.as_dict(),
        "policy": policy.as_dict(),
    }
    # Detachment: mutate the serialized nested payloads, source dataclass unchanged.
    out["spec"]["input_context"]["k"] = "MUTATED"
    out["policy"]["allowed_capabilities"].append("hacked")
    assert spec.input_context == {"k": "v"}
    assert policy.allowed_capabilities == frozenset({"echo"})
    # Stable across repeated calls (no shared mutable identity leaked between snapshots).
    assert req.as_dict()["spec"]["input_context"] == {"k": "v"}


@settings(max_examples=60)
@given(
    objective=st.text(max_size=20),
    steps=st.integers(min_value=0, max_value=10_000),
    depth=st.integers(min_value=0, max_value=50),
    caps=st.frozensets(st.text(min_size=1, max_size=8), max_size=5),
)
def test_delegation_request_as_dict_roundtrips_through_nested_from_dict(
    objective, steps, depth, caps
):
    """Property: DelegationRequest.as_dict's nested spec/policy survive their own from_dict
    rebuild losslessly — pins the serialization contract across arbitrary scalar inputs."""
    spec = DelegationSpec(objective=objective)
    policy = DelegationPolicy(max_steps=steps, max_depth=depth, allowed_capabilities=caps)
    req = DelegationRequest(
        delegation_id="d", parent_session_id="p", parent_task_id="t",
        target="agent:x", spec=spec, policy=policy,
    )
    out = req.as_dict()
    assert DelegationSpec.from_dict(out["spec"]) == spec
    assert DelegationPolicy.from_dict(out["policy"]) == policy
    # Top-level scalar fields are passed through verbatim.
    assert out["delegation_id"] == "d"
    assert out["target"] == "agent:x"


# --------------------------------------------------------------------------------------
# core/kernel.py — _deep_freeze must handle EVERY container kind (line 20 = set/frozenset).
# Driven organically through kernel.freeze() (config with a set value) AND directly.
# --------------------------------------------------------------------------------------


def test_deep_freeze_of_set_becomes_frozenset_recursively():
    """kernel.py 19-20: a set (and a set-of-tuples) deep-freezes to a frozenset; nested
    containers freeze too. Frozenset is hashable so it cannot be mutated."""
    frozen = _deep_freeze({1, 2, 3})
    assert isinstance(frozen, frozenset)
    assert frozen == frozenset({1, 2, 3})
    nested = _deep_freeze({frozenset({("a", 1)})})
    assert isinstance(nested, frozenset)


def test_deep_freeze_idempotent_and_value_passthrough():
    """Scalars pass through unchanged (line 21); refreezing a frozen structure is stable."""
    assert _deep_freeze(7) == 7
    assert _deep_freeze("s") == "s"
    assert _deep_freeze(None) is None
    once = _deep_freeze({"a": [1, {2}]})
    twice = _deep_freeze(once)
    assert twice == once


def test_kernel_freeze_deep_freezes_set_valued_config_through_session_start():
    """End-to-end: a config carrying a set value is deep-frozen on first session start,
    exercising the set branch via the real freeze() path (not just the private helper)."""
    kernel = AgentKernel(
        registry=CapabilityRegistry(),
        events=EventBus(),
        config={"features": {}, "tags": {"alpha", "beta"}, "nested": {"inner_set": {1, 2}}},
    )
    SessionFactory(kernel=kernel).create_root("x")
    assert isinstance(kernel.config["tags"], frozenset)
    assert kernel.config["tags"] == frozenset({"alpha", "beta"})
    assert isinstance(kernel.config["nested"]["inner_set"], frozenset)
    # frozen mapping is immutable
    with pytest.raises(TypeError):
        kernel.config["tags"] = {"gamma"}


def test_kernel_freeze_is_idempotent():
    """freeze() called twice is a no-op on the second call (early return, line 50-51)."""
    kernel = _echo_kernel()
    kernel.freeze()
    snapshot = dict(kernel.config)
    kernel.freeze()  # must not raise nor re-freeze/re-copy in a way that changes content
    assert dict(kernel.config) == snapshot


def test_execute_tool_without_context_uses_null_lineage():
    """kernel.py 72-79: calling execute_tool with no context still produces a complete
    envelope whose lineage fields are all None (no KeyError, no crash)."""
    kernel = _echo_kernel()
    env = kernel.execute_tool("echo", {"x": 1})  # context=None
    meta = env["metadata"]
    for field in ("run_id", "task_id", "session_id", "parent_session_id",
                  "delegation_id", "actor_id"):
        assert meta[field] is None
    assert meta["request_id"]  # still stamped


# --------------------------------------------------------------------------------------
# core/registry.py — NullToolPort fallback shape + has_tool/list ordering edges.
# --------------------------------------------------------------------------------------


def test_null_tool_port_envelope_names_the_missing_capability():
    """NullToolPort.execute (registry 34-40) returns a missing_capability failure naming the
    requested tool — used when neither exact nor fallback resolves."""
    null = NullToolPort()
    out = null.execute(ToolRequest(name="ghost"))
    assert out["ok"] is False
    assert out["missing_capability"] is True
    assert "ghost" in out["error"]
    assert null.name == "null_tool"


def test_register_tools_bulk_applies_same_descriptor_and_lists_sorted():
    """register_tools fans one executor across many names with a shared descriptor; list_tools
    returns names sorted (deterministic describe_capabilities)."""
    reg = CapabilityRegistry()
    exec_obj = object()
    reg.register_tools(["zebra", "alpha", "mid"], exec_obj, feature_name="f",
                       kind="effect", idempotent=True, risk="high")
    assert [t["name"] for t in reg.list_tools()] == ["alpha", "mid", "zebra"]
    for name in ("zebra", "alpha", "mid"):
        res = reg.resolve_tool(name)
        assert res.executor is exec_obj
        assert res.descriptor.kind == "effect"
        assert res.descriptor.idempotent is True
        assert res.descriptor.risk == "high"
        assert res.feature == "f"
    assert reg.has_tool("alpha") is True
    assert reg.has_tool("absent") is False


def test_resolve_unknown_uses_default_descriptor_via_null():
    """An unresolved name returns the NullToolPort with the DEFAULT_DESCRIPTOR (kind=tool)."""
    reg = CapabilityRegistry()
    res = reg.resolve_tool("nope")
    assert res.executor.name == "null_tool"
    assert res.feature is None
    assert res.descriptor.kind == "tool"


def test_setting_fallback_to_none_clears_its_feature():
    """set_fallback_tool_executor(None) wipes the recorded fallback feature (registry 98-101)."""
    reg = CapabilityRegistry()
    reg.set_fallback_tool_executor(object(), feature_name="fb")
    assert reg.resolve_tool("x").feature == "fb"
    reg.set_fallback_tool_executor(None)
    res = reg.resolve_tool("x")
    assert res.executor.name == "null_tool"
    assert res.feature is None


# --------------------------------------------------------------------------------------
# core/state.py — snapshot/restore detachment under deep nesting + alias safety.
# --------------------------------------------------------------------------------------


def test_snapshot_is_detached_mutating_snapshot_does_not_touch_live_state():
    """Mutating a returned snapshot's nested structure must not bleed into live state, and
    vice versa — the round-trip is fully detached (state.py 21-27)."""
    store = StateStore()
    store.set("nested", {"list": [1, [2, 3]]})
    snap = store.snapshot()
    snap["nested"]["list"][1].append(99)
    snap["new"] = "x"
    assert store.get("nested") == {"list": [1, [2, 3]]}  # live untouched
    assert store.get("new") is None
    # Reverse: mutating live after snapshot does not retroactively edit the snapshot.
    store.set("nested", {"list": ["changed"]})
    assert snap["nested"]["list"][0] == 1


def test_restore_replaces_wholesale_and_decouples_from_source():
    """restore() replaces ALL state and deep-copies the source so later edits to the source
    dict don't leak into the store (state.py 25-27)."""
    store = StateStore()
    store.set("keep", "old")
    source = {"only": {"deep": [1]}}
    store.restore(source)
    assert store.get("keep") is None          # wholesale replacement
    assert store.get("only") == {"deep": [1]}
    source["only"]["deep"].append(2)          # mutate the source after restore
    assert store.get("only") == {"deep": [1]}  # store is decoupled


def test_as_dict_returns_independent_deep_copy():
    """as_dict() is a detached deep copy: mutating it leaves the store pristine."""
    store = StateStore()
    store.set("a", {"b": [1]})
    dumped = store.as_dict()
    dumped["a"]["b"].append(2)
    assert store.get("a") == {"b": [1]}


@settings(max_examples=50)
@given(
    payload=st.dictionaries(
        st.text(min_size=1, max_size=6),
        st.recursive(
            st.one_of(st.integers(), st.text(max_size=5), st.booleans(), st.none()),
            lambda children: st.lists(children, max_size=4)
            | st.dictionaries(st.text(min_size=1, max_size=4), children, max_size=4),
            max_leaves=12,
        ),
        max_size=6,
    )
)
def test_snapshot_restore_roundtrip_is_value_lossless_and_alias_free(payload):
    """Property: snapshot then restore reproduces the same VALUE while sharing no nested
    object identity with the original payload (no aliasing leak across resume)."""
    store = StateStore()
    for key, value in payload.items():
        store.set(key, value)
    snap = store.snapshot()
    assert snap == payload

    fresh = StateStore()
    fresh.restore(snap)
    assert fresh.as_dict() == payload

    # Alias-freedom: mutate the original payload's containers; snapshot/store stay intact.
    expected = copy.deepcopy(payload)
    for value in payload.values():
        if isinstance(value, list):
            value.append("LEAK")
        elif isinstance(value, dict):
            value["LEAK"] = True
    assert snap == expected
    assert fresh.as_dict() == expected


# --------------------------------------------------------------------------------------
# core/events.py — subscriber isolation, ordering, and concurrency-safe registration.
# --------------------------------------------------------------------------------------


def test_publish_with_none_payload_delivers_empty_dict():
    """publish(topic) with no payload delivers a fresh empty dict to each subscriber (events 22-25)."""
    bus = EventBus()
    seen: list[dict] = []
    bus.subscribe(lambda t, p: seen.append(p))
    bus.publish("ping")
    assert seen == [{}]


def test_each_subscriber_gets_its_own_detached_payload_copy():
    """Mutating the payload in one subscriber must not affect the payload a later subscriber
    receives — every delivery is an independent deep copy (events 26-28)."""
    bus = EventBus()
    received: list[dict] = []
    bus.subscribe(lambda t, p: p["nested"].__setitem__("v", "first-mutated"))
    bus.subscribe(lambda t, p: received.append(copy.deepcopy(p)))
    bus.publish("topic", {"nested": {"v": "orig"}})
    assert received == [{"nested": {"v": "orig"}}]


def test_subscriber_added_during_publish_does_not_receive_current_event():
    """publish snapshots the subscriber list under lock BEFORE delivery, so a subscriber that
    registers mid-dispatch is not invoked for the in-flight event (events 23-24)."""
    bus = EventBus()
    late_calls: list[str] = []

    def late(topic, payload):  # pragma: no cover - must NOT fire for this publish
        late_calls.append(topic)

    def adder(topic, payload):
        bus.subscribe(late)

    bus.subscribe(adder)
    bus.publish("first", {})
    assert late_calls == []      # 'late' not called for the event it was added during
    bus.publish("second", {})
    assert late_calls == ["second"]  # but it does receive the next event


def test_concurrent_subscribe_and_publish_never_corrupts_registry():
    """Concurrency: interleaving subscribe() and publish() across threads must not crash nor
    drop the lock invariant. We assert every publish completes and the count is monotonic."""
    bus = EventBus()
    counter = {"n": 0}

    def observer(topic, payload):
        counter["n"] += 1  # GIL-atomic increment; we only assert it does not crash

    def worker(i):
        bus.subscribe(observer)
        bus.publish("t", {"i": i})

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(worker, range(120)))

    # Each of the 120 publishes ran without an exception escaping the bus.
    assert counter["n"] >= 120


# --------------------------------------------------------------------------------------
# core/bootstrap.py — middleware wiring edges and config-load corners (idempotent/inert).
# --------------------------------------------------------------------------------------


def test_middleware_section_absent_is_inert():
    """build_kernel with no 'middleware' section installs zero middleware (bootstrap 28-33)."""
    kernel = _empty_kernel()
    assert kernel._middlewares == []


def test_middleware_disabled_subsections_install_nothing():
    """Each subsection guarded by enabled=False must wire nothing (bootstrap 34-53 false paths)."""
    from core.bootstrap import build_kernel

    config = {
        "features": {},
        "middleware": {
            "timing": {"enabled": False},
            "policy": {"enabled": False, "deny": ["x"]},
            "retry": {"enabled": False, "attempts": 5},
            "condense": {"enabled": False},
        },
    }
    kernel = build_kernel(config)
    assert kernel._middlewares == []


def test_enabled_middleware_chain_installs_in_declared_order():
    """All four built-ins enabled -> exactly four middlewares wired, outer->inner:
    timing, policy, retry, condense (bootstrap 34-53 true paths)."""
    from core.bootstrap import build_kernel
    from middleware import CondenseResult, PolicyGate, Retry, TimingLog

    config = {
        "features": {},
        "middleware": {
            "timing": {"enabled": True},
            "policy": {"enabled": True, "deny": ["danger"]},
            "retry": {"enabled": True, "attempts": 3},
            "condense": {"enabled": True, "max_chars": 100, "max_list": 4},
        },
    }
    kernel = build_kernel(config)
    types = [type(mw) for mw in kernel._middlewares]
    assert types == [TimingLog, PolicyGate, Retry, CondenseResult]


def test_load_config_missing_file_returns_empty_features(tmp_path):
    """load_config of a non-existent path returns the inert {'features': {}} default
    (bootstrap 18-19) — complements the missing/empty/non-mapping test in the adversarial suite
    by pinning the *return value* default-shape independently."""
    from core.bootstrap import load_config

    assert load_config(tmp_path / "does_not_exist.yaml") == {"features": {}}


def test_load_config_dict_without_features_key_gets_default(tmp_path):
    """A valid mapping lacking 'features' is augmented with an empty features map (bootstrap 24)."""
    from core.bootstrap import load_config

    path = tmp_path / "cfg.yaml"
    path.write_text("other: 1\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg["features"] == {}
    assert cfg["other"] == 1
