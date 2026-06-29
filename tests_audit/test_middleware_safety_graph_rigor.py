"""Rigor for middleware/safety/graph/gen_map: pin pass-through branches, jail escapes, node fail-routes, and the MAP generator.

Complements (does not duplicate) tests/test_middleware.py, tests_audit/test_middleware_exact_semantics.py,
tests/test_safety.py, tests_audit/test_security_boundaries.py, and tests/test_graph.py. Every node test drives
the real graph nodes through KernelSession.execute_tool so the kernel chokepoint stays on the path.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.schemas import DelegationResult, TaskEnvelope, ToolRequest
from core.session import SessionFactory
from discipline import Budget
from graph.nodes import (
    agent_node,
    delegation_node,
    fail_node,
    finish_node,
    guard_node,
    tool_node,
)
from graph.state import (
    budget_from_state,
    budget_to_dict,
    decode_session_state,
    encode_session_state,
    new_agent_state,
)
from middleware import BudgetGuard, CondenseResult, PolicyGate, Retry, TimingLog
from safety.policy import (
    SafeToolPort,
    ToolPolicy,
    _argv_escapes_workspace,
    classify_terminal,
)
from safety.sandbox import SandboxError, resolve_in_workspace, workspace_dir


# ---------------------------------------------------------------------------
# middleware/policy.py — the PASS branch (line 21): a non-denied tool calls nxt.
# The deny/short-circuit branch is already pinned in the existing suites; here we
# pin the complementary path so the gate is provably transparent off the deny-list.
# ---------------------------------------------------------------------------


@pytest.mark.audit
def test_policy_gate_passes_through_when_not_denied_and_returns_inner_envelope():
    """A tool absent from the deny-list reaches the inner handler verbatim (policy.py:21)."""
    sentinel = {"ok": True, "data": {"x": 1}}
    seen: list[ToolRequest] = []
    gate = PolicyGate(deny={"forbidden"})
    request = ToolRequest("allowed")

    result = gate(request, lambda req: seen.append(req) or sentinel)

    assert result is sentinel  # untouched envelope passed straight back
    assert seen == [request]  # inner handler invoked exactly once with the same request


@pytest.mark.audit
def test_policy_gate_block_without_on_block_hook_does_not_crash():
    """on_block=None must still short-circuit cleanly (the `if self.on_block` false arm)."""
    gate = PolicyGate(deny={"x"})  # no on_block
    result = gate(ToolRequest("x"), lambda req: pytest.fail("inner reached on a denied tool"))
    assert result["ok"] is False
    assert result["metadata"]["policy_block"] is True
    assert result["error"] == "Blocked by policy: x"


@pytest.mark.audit
def test_policy_gate_default_deny_is_empty_and_lets_everything_through():
    gate = PolicyGate()
    assert gate.deny == set()
    assert gate(ToolRequest("anything"), lambda req: {"ok": True})["ok"] is True


# ---------------------------------------------------------------------------
# middleware/retry.py — retryable classification edges beyond the existing matrix.
# ---------------------------------------------------------------------------


@pytest.mark.audit
def test_retry_attempts_below_one_is_clamped_to_single_call():
    """attempts<=0 must not disable the first call nor loop forever (max(1, attempts))."""
    calls = []
    out = Retry(attempts=0)(ToolRequest("t"), lambda r: calls.append(r) or {"ok": False})
    assert len(calls) == 1 and out["ok"] is False


@pytest.mark.audit
def test_retry_retries_idempotent_effect_but_not_non_idempotent_effect():
    """An effect that is idempotent IS retryable; only idempotent is False blocks the retry."""
    idem = [{"ok": False, "metadata": {"kind": "effect", "idempotent": True}}, {"ok": True}]
    calls_i = []
    res_i = Retry(attempts=5)(ToolRequest("t"), lambda r: calls_i.append(r) or idem.pop(0))
    assert len(calls_i) == 2 and res_i["ok"] is True

    non = [{"ok": False, "metadata": {"kind": "effect", "idempotent": False}}, {"ok": True}]
    calls_n = []
    res_n = Retry(attempts=5)(ToolRequest("t"), lambda r: calls_n.append(r) or non.pop(0))
    assert len(calls_n) == 1 and res_n["ok"] is False  # never re-runs a non-idempotent effect


@pytest.mark.audit
def test_retry_treats_missing_metadata_as_retryable():
    """No metadata key at all => default-retryable read/model behaviour."""
    seq = [{"ok": False}, {"ok": False}, {"ok": True}]
    calls = []
    res = Retry(attempts=3)(ToolRequest("t"), lambda r: calls.append(r) or seq.pop(0))
    assert len(calls) == 3 and res["ok"] is True


@pytest.mark.audit
def test_retry_metadata_none_is_coerced_to_empty_mapping():
    """metadata explicitly None must be treated as {} (the `meta = env.get(...) or {}` arm)."""
    seq = [{"ok": False, "metadata": None}, {"ok": True}]
    calls = []
    res = Retry(attempts=2)(ToolRequest("t"), lambda r: calls.append(r) or seq.pop(0))
    assert len(calls) == 2 and res["ok"] is True


# ---------------------------------------------------------------------------
# middleware/budget.py — block path with and without the hook.
# ---------------------------------------------------------------------------


@pytest.mark.audit
def test_budget_guard_blocks_without_hook_and_keys_on_name_plus_args():
    """Differing args are distinct keys; the same (name,args) trips the limit. No hook => no crash."""
    guard = BudgetGuard(Budget(max_same_tool_calls=1))  # block on the 2nd identical call
    r1 = guard(ToolRequest("e", {"a": 1}), lambda req: {"ok": True})
    r_other = guard(ToolRequest("e", {"a": 2}), lambda req: {"ok": True})  # different args, still ok
    r2 = guard(ToolRequest("e", {"a": 1}), lambda req: pytest.fail("inner reached after block"))
    assert r1["ok"] is True and r_other["ok"] is True
    assert r2["ok"] is False and r2["metadata"]["budget_block"] is True
    assert r2["error"] == "Same-tool budget exceeded."


# ---------------------------------------------------------------------------
# middleware/condense.py — the non-condensable data branch and the no-hook arm.
# ---------------------------------------------------------------------------


@pytest.mark.audit
def test_condense_leaves_non_container_data_untouched():
    """data that is not dict/list/str (e.g. int, None, missing) skips condense entirely."""
    mw = CondenseResult(max_chars=1, on_condense=lambda r: pytest.fail("notified for non-container"))
    for env in ({"ok": True, "data": 12345}, {"ok": True, "data": None}, {"ok": True}):
        out = mw(ToolRequest("tool"), lambda req, e=env: dict(e))
        assert out.get("data", "_missing") == env.get("data", "_missing")


@pytest.mark.audit
def test_condense_shrinks_without_hook_when_on_condense_is_none():
    """The shrink path must work even with on_condense=None (the `and self.on_condense` false arm)."""
    mw = CondenseResult(max_chars=3)  # no hook
    out = mw(ToolRequest("tool"), lambda req: {"ok": True, "data": "abcdefgh"})
    assert out["data"].startswith("abc") and out["data"] != "abcdefgh"


@pytest.mark.audit
def test_condense_skips_llm_namespace_entirely():
    big = {"ok": True, "data": {"content": "z" * 99}}
    mw = CondenseResult(max_chars=5)
    assert mw(ToolRequest("llm.chat"), lambda req: dict(big))["data"]["content"] == "z" * 99


# ---------------------------------------------------------------------------
# middleware/timing.py — no-sink fast path and the None-envelope guard.
# ---------------------------------------------------------------------------


@pytest.mark.audit
def test_timing_without_sink_returns_inner_envelope_unchanged():
    sentinel = {"ok": True, "data": 1}
    assert TimingLog()(ToolRequest("e"), lambda r: sentinel) is sentinel


@pytest.mark.audit
def test_timing_tolerates_none_envelope_from_inner(monkeypatch):
    """`(env or {}).get(...)` must not explode when the inner handler returns None."""
    readings = iter([1.0, 1.001])
    monkeypatch.setattr("middleware.timing.time.perf_counter", lambda: next(readings))
    seen: list[dict[str, Any]] = []
    out = TimingLog(seen.append)(ToolRequest("e"), lambda r: None)
    assert out is None
    assert seen == [{"tool": "e", "ok": None, "ms": 1.0}]


# ---------------------------------------------------------------------------
# safety/policy.py — SafeToolPort wrapper, repair-mode, and the path-resolution
# exception arm (lines 34-35) plus the no-escape return.
# ---------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
def test_safe_tool_port_delegates_to_inner_when_allowed():
    """The allow branch of SafeToolPort.execute must forward to the wrapped executor."""

    class Inner:
        def execute(self, request: ToolRequest) -> dict[str, Any]:
            return {"ok": True, "echo": request.args}

    safe = SafeToolPort("fs_read", Inner(), ToolPolicy())
    out = safe.execute(ToolRequest("fs_read", {"path": "a.txt"}))
    assert out == {"ok": True, "echo": {"path": "a.txt"}}


@pytest.mark.audit
@pytest.mark.security
def test_safe_tool_port_default_policy_is_constructed_when_none_given():
    safe = SafeToolPort("fs_read", object())
    assert isinstance(safe._policy, ToolPolicy)


@pytest.mark.audit
@pytest.mark.security
def test_tool_policy_repair_mode_blocks_whole_file_write_and_inner_never_runs():
    """repair_mode refuses a clobbering whole-file rewrite with the documented code."""

    class Bomb:
        def execute(self, request: ToolRequest) -> dict[str, Any]:
            raise AssertionError("repair-mode write reached the inner executor")

    safe = SafeToolPort("fs_write", Bomb(), ToolPolicy(repair_mode=True))
    out = safe.execute(ToolRequest("fs_write", {"path": "x", "content": "y"}))
    assert out["ok"] is False
    assert out["policy_blocked"] is True
    assert out["policy_code"] == "repair_requires_patch_tool"
    assert out["metadata"]["risk"] == "blocked"


@pytest.mark.audit
@pytest.mark.security
def test_tool_policy_repair_mode_allows_normal_read():
    """repair_mode only constrains whole-file writes; a read still passes."""
    assert ToolPolicy(repair_mode=True).check("fs_read", {"path": "a"}).allowed is True


@pytest.mark.audit
@pytest.mark.security
def test_tool_policy_git_mutation_tool_name_blocked_then_allowed_via_env(monkeypatch):
    monkeypatch.delenv("AGENT_ALLOW_GIT_MUTATIONS", raising=False)
    assert ToolPolicy().check("git_push_branch", {}).code == "git_mutation"
    monkeypatch.setenv("AGENT_ALLOW_GIT_MUTATIONS", "1")
    assert ToolPolicy().check("git_push_branch", {}).allowed is True


@pytest.mark.audit
@pytest.mark.security
def test_argv_escape_swallows_unresolvable_path_and_reports_no_escape(tmp_path, monkeypatch):
    """A NUL-byte path matches the abs-path regex but Path.resolve() raises ValueError.

    That hits the `except (OSError, ValueError): continue` arm (safety/policy.py:34-35):
    an unresolvable token is skipped, so the scan reports *no* escape for that arg alone.
    """
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    assert _argv_escapes_workspace(["python", "/etc/pa\x00ss"]) is False


@pytest.mark.audit
@pytest.mark.security
def test_argv_with_only_program_and_no_absolute_token_is_not_an_escape(tmp_path, monkeypatch):
    """argv[0] is exempt and args with no leading-slash token => no escape (loop falls to return False).

    NOTE the scan is deliberately greedy: a `/`-rooted *substring* anywhere in a later
    arg counts as an absolute token (see the escape test below). So a "safe" arg here
    must carry no `/`-rooted run at all.
    """
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    assert _argv_escapes_workspace(["/usr/bin/python", "-c", "print(1)", "relfile.txt"]) is False


@pytest.mark.audit
@pytest.mark.security
def test_argv_absolute_path_outside_workspace_is_an_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    assert _argv_escapes_workspace(["python", "-c", "open('/etc/passwd')"]) is True
    assert classify_terminal(["python", "-c", "open('/etc/passwd')"]).code == "path_escape"


@pytest.mark.audit
@pytest.mark.security
def test_argv_absolute_path_inside_workspace_is_not_an_escape(tmp_path, monkeypatch):
    ws = (tmp_path / "ws")
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    inside = str(workspace_dir() / "sub" / "file.txt")
    assert _argv_escapes_workspace(["python", inside]) is False


@pytest.mark.audit
@pytest.mark.security
def test_classify_terminal_rejects_non_list_and_empty_argv():
    assert classify_terminal("bash -c id").code == "bad_argv"
    assert classify_terminal([]).code == "bad_argv"
    assert classify_terminal(None).allowed is False


# ---------------------------------------------------------------------------
# safety/sandbox.py — complement (do not duplicate) the security suite's escapes.
# ---------------------------------------------------------------------------


@pytest.mark.audit
@pytest.mark.security
def test_sandbox_root_itself_resolves_and_dot_segments_inside_are_kept(tmp_path, monkeypatch):
    """The `resolved == workspace` allowance: the workspace root and inner `./a/../b` stay legal."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    root = resolve_in_workspace(".")
    assert root == workspace_dir()
    nested = resolve_in_workspace("a/../b/c.txt")
    assert nested.is_relative_to(workspace_dir())


@pytest.mark.audit
@pytest.mark.security
def test_sandbox_absolute_path_outside_workspace_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    with pytest.raises(SandboxError, match="outside workspace"):
        resolve_in_workspace(str(tmp_path / "elsewhere" / "secret.txt"))


@pytest.mark.audit
@pytest.mark.security
def test_sandbox_absolute_path_inside_workspace_allowed(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    target = workspace_dir() / "deep" / "ok.txt"
    assert resolve_in_workspace(str(target)) == target


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize("raw", ["..\\win", "C:\\Windows", "c:foo", "dir\\sub"])
def test_sandbox_rejects_windows_syntax_lexically(tmp_path, monkeypatch, raw):
    """Backslash separators and drive-letter prefixes fail closed regardless of host OS."""
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "ws"))
    with pytest.raises(SandboxError, match="outside workspace"):
        resolve_in_workspace(raw)


@pytest.mark.audit
@pytest.mark.security
@given(rel=st.text(alphabet="abcdefghij/._", min_size=0, max_size=40))
def test_sandbox_property_no_backslash_no_drive_resolves_inside(rel, tmp_path_factory, monkeypatch):
    """Property: any pure-POSIX relative string that survives the resolver lands inside the jail."""
    ws = tmp_path_factory.mktemp("ws")
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(ws))
    try:
        resolved = resolve_in_workspace(rel)
    except SandboxError:
        return  # a `..`-escape was correctly rejected — that is the safe outcome
    assert resolved == workspace_dir() or resolved.is_relative_to(workspace_dir())


# ---------------------------------------------------------------------------
# graph/state.py — codec round-trip (line 79 + encode/decode) and budget helpers.
# ---------------------------------------------------------------------------


@pytest.mark.audit
def test_session_state_codec_round_trips_task_envelope():
    """encode->decode reconstructs a TaskEnvelope from its `__task__` primitive."""
    task = TaskEnvelope(user_request="do x", context={"k": "v"})
    encoded = encode_session_state({"current_task": task, "n": 1})
    assert encoded["current_task"] == {"__task__": task.as_dict()}
    decoded = decode_session_state(encoded)
    assert isinstance(decoded["current_task"], TaskEnvelope)
    assert decoded["current_task"].user_request == "do x"
    assert decoded["n"] == 1


@pytest.mark.audit
def test_session_state_codec_passthrough_when_no_task():
    plain = {"current_task": None, "x": 7}
    assert decode_session_state(encode_session_state(plain)) == plain
    assert decode_session_state({"current_task": {"not_task": 1}}) == {"current_task": {"not_task": 1}}


@pytest.mark.audit
def test_budget_helpers_round_trip_and_filter_unknown_keys():
    b = Budget(max_steps=9, steps=4, parse_errors=2)
    d = budget_to_dict(b)
    d["bogus_field"] = "ignored"  # unknown keys must be filtered, not crash the constructor
    rebuilt = budget_from_state({"budget": d})
    assert (rebuilt.max_steps, rebuilt.steps, rebuilt.parse_errors) == (9, 4, 2)
    assert not hasattr(rebuilt, "bogus_field")


@pytest.mark.audit
def test_new_agent_state_rejects_inactive_session(kernel_factory):
    """graph/state.py:79 — building state from a session without a TaskEnvelope is a hard error."""
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session = SessionFactory(kernel=kernel).create_root("task")
    session.state.set("current_task", None)  # simulate a closed/inactive session
    with pytest.raises(ValueError, match="inactive session"):
        new_agent_state(session=session, messages=[], budget=Budget())


# ---------------------------------------------------------------------------
# graph/nodes.py — drive the real nodes to hit the 6 uncovered fail-routes.
# Each node still funnels external actions through KernelSession.execute_tool.
# ---------------------------------------------------------------------------


def _root_state(kernel, task: str = "t", *, budget: Budget | None = None):
    session = SessionFactory(kernel=kernel).create_root(task, agent_id="agent:test")
    state = new_agent_state(
        session=session,
        messages=[{"role": "user", "content": task}],
        budget=budget or Budget(),
    )
    return session, state


class _BadJsonLLM:
    """An llm.chat tool whose content never parses, forcing the parse-error path.

    The kernel nests a tool's return under envelope["data"], and agent_node reads
    response["data"]["content"], so content lives at the TOP level of the return
    (mirroring graph.runtime._CallableLLMTool).
    """

    name = "llm.chat"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {"ok": True, "content": "this is not json"}


def _register_llm(kernel, tool) -> None:
    from core.schemas import FeatureDescriptor

    feature = FeatureDescriptor(name="llm_x", capabilities=("llm.chat",))
    kernel.registry.register_feature(feature)
    kernel.registry.register_tool("llm.chat", tool, feature_name=feature.name)


@pytest.mark.audit
def test_agent_node_routes_fail_when_parse_budget_is_exhausted(kernel_factory):
    """graph/nodes.py:69 — once parse_errors hit the cap, the next parse error routes to fail."""
    kernel, _ = kernel_factory(echo=False, toolbox=False)
    _register_llm(kernel, _BadJsonLLM())
    # max_parse_errors=1: a single parse error immediately trips parse_exceeded().
    session, state = _root_state(kernel, budget=Budget(max_parse_errors=1))
    out = agent_node(state, session=session)
    assert out["route"] == "fail"
    assert out["error"] == "too many parse errors"
    assert budget_from_state(out).parse_errors == 1


@pytest.mark.audit
def test_agent_node_parse_error_under_cap_routes_back_to_guard_with_retry_message(kernel_factory):
    """The complementary branch: a recoverable parse error appends a retry prompt and loops to guard."""
    kernel, _ = kernel_factory(echo=False, toolbox=False)
    _register_llm(kernel, _BadJsonLLM())
    session, state = _root_state(kernel, budget=Budget(max_parse_errors=3))
    out = agent_node(state, session=session)
    assert out["route"] == "guard"
    assert out["messages"][-1]["role"] == "user"  # a retry instruction was appended


@pytest.mark.audit
def test_delegation_node_fails_when_service_not_configured(kernel_factory):
    """graph/nodes.py:150 — delegate with no service wired is a structured failure, not a crash."""
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel)
    state["last_action"] = {"action": "delegate", "target": "writer", "spec": {"objective": "x"}}
    out = delegation_node(state, session=session, delegation_service=None)
    assert out["route"] == "fail"
    assert out["error"] == "delegation is not configured"


class _FakeDelegationService:
    def __init__(self, *, raises: Exception | None = None, result: DelegationResult | None = None):
        self._raises = raises
        self._result = result
        self.calls: list[Any] = []

    def available_targets(self) -> tuple[str, ...]:
        return ("writer",)

    def delegate(self, parent_session, target, spec, policy=None):
        self.calls.append((target, spec, policy))
        if self._raises is not None:
            raise self._raises
        return self._result


@pytest.mark.audit
@pytest.mark.parametrize(
    "action",
    [
        {"action": "delegate", "target": "", "spec": {"objective": "x"}},  # empty target
        {"action": "delegate", "target": "w", "spec": "not-a-dict"},  # spec not a mapping
        {"action": "delegate", "target": "w", "spec": {}, "policy": "nope"},  # policy not a mapping
    ],
)
def test_delegation_node_rejects_malformed_delegate_action(kernel_factory, action):
    """graph/nodes.py:160 — missing target / non-dict spec / non-dict policy all fail closed."""
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel)
    state["last_action"] = action
    service = _FakeDelegationService(result=None)
    out = delegation_node(state, session=session, delegation_service=service)
    assert out["route"] == "fail"
    assert "target" in out["error"]
    assert service.calls == []  # never reached the boundary


@pytest.mark.audit
def test_delegation_node_rejects_empty_objective(kernel_factory):
    """graph/nodes.py:167 — a well-formed delegate with an empty objective is refused."""
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel)
    state["last_action"] = {"action": "delegate", "target": "writer", "spec": {"objective": ""}}
    service = _FakeDelegationService(result=None)
    out = delegation_node(state, session=session, delegation_service=service)
    assert out["route"] == "fail"
    assert out["error"] == "delegation objective must not be empty"
    assert service.calls == []


@pytest.mark.audit
def test_delegation_node_wraps_boundary_exception_as_fail(kernel_factory):
    """graph/nodes.py:179-180 — an exception from the delegation port becomes a fail route, not a raise."""
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel)
    state["last_action"] = {"action": "delegate", "target": "writer", "spec": {"objective": "ship"}}
    service = _FakeDelegationService(raises=RuntimeError("subagent crashed"))
    out = delegation_node(state, session=session, delegation_service=service)
    assert out["route"] == "fail"
    assert "delegation failed at the application boundary" in out["error"]
    assert "subagent crashed" in out["error"]
    assert len(service.calls) == 1  # the boundary WAS reached, then raised


@pytest.mark.audit
def test_delegation_node_success_appends_observation_and_routes_to_guard(kernel_factory):
    """The happy path: a successful delegate records the observation and loops back to guard."""
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel)
    state["last_action"] = {
        "action": "delegate",
        "target": "writer",
        "spec": {"objective": "draft"},
        "policy": {"max_steps": 5},
    }
    result = DelegationResult(
        delegation_id="d1",
        parent_task_id=session.identity.task_id,
        outcome="success",
        summary={"note": "ok"},
    )
    service = _FakeDelegationService(result=result)
    out = delegation_node(state, session=session, delegation_service=service)
    assert out["route"] == "guard"
    assert out["last_delegation_result"]["outcome"] == "success"
    assert out["active_delegation_id"] is None
    assert out["messages"][-1]["content"].startswith("DELEGATION_RESULT: ")


@pytest.mark.audit
def test_guard_node_blocks_when_step_budget_exhausted(kernel_factory):
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel, budget=Budget(max_steps=0, steps=0))
    out = guard_node(state, session=session)
    assert out["route"] == "fail" and out["error"] == "step budget exceeded"


@pytest.mark.audit
def test_tool_node_runs_external_tool_through_kernel_chokepoint(kernel_factory):
    """Pin that an external action's tool_node call really crosses execute_tool and records history."""
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel)
    state["last_action"] = {"action": "tool", "tool": "echo", "args": {"msg": "hi"}}
    out = tool_node(state, session=session)
    assert out["route"] == "guard"
    appended = out["messages"][-1]["content"]
    assert "echo" in appended and "hi" in appended


@pytest.mark.audit
def test_tool_node_blocks_repeated_identical_tool_call(kernel_factory):
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel, budget=Budget(max_same_tool_calls=0))
    state["last_action"] = {"action": "tool", "tool": "echo", "args": {"x": 1}}
    out = tool_node(state, session=session)
    assert out["route"] == "fail"
    assert out["error"] == "repeated the same tool call too many times"


@pytest.mark.audit
def test_tool_node_coerces_non_dict_args_to_empty_dict(kernel_factory):
    """A `tool` action whose args are not a mapping must degrade to {} rather than crash."""
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel)
    state["last_action"] = {"action": "tool", "tool": "echo", "args": ["not", "a", "dict"]}
    out = tool_node(state, session=session)
    assert out["route"] == "guard"  # executed with args={}


@pytest.mark.audit
def test_finish_node_error_reason_routes_to_failed_outcome(kernel_factory):
    """An `error` finish is a terminal failure, surfaced via fail_task with status=failed."""
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel)
    state["last_action"] = {"action": "final", "finish_reason": "error", "message": "adapter gave up"}
    out = finish_node(state, session=session)
    assert out["status"] == "failed" and out["route"] == "end"
    assert out["final"] == "adapter gave up"
    assert out["outcome"]["status"] == "failed"


@pytest.mark.audit
def test_finish_node_blocks_final_when_validation_required(kernel_factory):
    """check_finish gate: code changed without passing validation routes back to guard.

    finish_node restores its working state from state["session_state"], so the
    code_changed flag must live in that snapshot (set it on the session, then
    re-encode) — mutating the session post-snapshot would be clobbered by restore.
    """
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel)
    session.state.set("code_changed", True)  # require validation
    state["session_state"] = encode_session_state(session.state.snapshot())
    state["last_action"] = {"action": "final", "message": "done"}
    out = finish_node(state, session=session)
    assert out["route"] == "guard"
    assert "validation" in out["messages"][-1]["content"].lower()


@pytest.mark.audit
def test_finish_node_completes_clean_run(kernel_factory):
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel)
    state["last_action"] = {"action": "final", "message": "all good"}
    out = finish_node(state, session=session)
    assert out["status"] == "completed" and out["route"] == "end"
    assert out["final"] == "all good"


@pytest.mark.audit
def test_fail_node_closes_run_with_failed_outcome(kernel_factory):
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel)
    state["error"] = "boom"
    out = fail_node(state, session=session)
    assert out["status"] == "failed" and out["route"] == "end"
    assert out["outcome"]["status"] == "failed"


# ---------------------------------------------------------------------------
# tools/gen_map.py — run the generator over a synthesized package tree (lines 43-46, 53).
# We import the module by path and rebind its ROOT to a tmp tree so MAP.md is written
# under tmp_path, never touching the repo's real MAP.md.
# ---------------------------------------------------------------------------


def _load_gen_map_module():
    src = Path(__file__).resolve().parent.parent / "tools" / "gen_map.py"
    spec = importlib.util.spec_from_file_location("_gen_map_under_test", src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.audit
def test_gen_map_emits_module_table_root_files_and_missing_docstring(tmp_path, monkeypatch):
    """gen_map over a tiny synthesized tree: package table, the root-file branch (43-46),
    main() return 0 (53), the missing-docstring placeholder, and __init__.py skipping."""
    gen_map = _load_gen_map_module()

    # Synthesize a minimal "repo": one real package + one denied dir + a root-level file.
    pkg = tmp_path / "feature_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")  # skipped in the table
    (pkg / "documented.py").write_text('"""Does a thing. Epic E99."""\n', encoding="utf-8")
    (pkg / "undocumented.py").write_text("x = 1\n", encoding="utf-8")  # triggers placeholder text
    denied = tmp_path / "tests"  # in DENY -> excluded from packages()
    denied.mkdir()
    (denied / "conftest.py").write_text("# noqa\n", encoding="utf-8")
    (tmp_path / "rootmod.py").write_text('"""Root entry point. Epic root."""\n', encoding="utf-8")

    monkeypatch.setattr(gen_map, "ROOT", tmp_path)

    rc = gen_map.main()  # exercises the root_py branch (43-46) and the `return 0` at 53
    assert rc == 0

    out = (tmp_path / "MAP.md").read_text(encoding="utf-8")
    assert "## feature_pkg/" in out
    assert "| `feature_pkg/documented.py` | Does a thing. Epic E99. |" in out
    assert "thiếu module docstring" in out  # undocumented.py placeholder
    assert "feature_pkg/__init__.py" not in out  # __init__ skipped
    assert "## (root)" in out
    assert "| `rootmod.py` | Root entry point. Epic root. |" in out
    assert "## tests/" not in out  # DENY honoured


@pytest.mark.audit
def test_gen_map_first_doc_and_packages_helpers(tmp_path, monkeypatch):
    """first_doc returns the placeholder for an empty docstring and the first line otherwise;
    packages() filters DENY dirs and dirs without .py files."""
    gen_map = _load_gen_map_module()
    monkeypatch.setattr(gen_map, "ROOT", tmp_path)

    doc_file = tmp_path / "a.py"
    doc_file.write_text('"""First line here.\nsecond line."""\n', encoding="utf-8")
    assert gen_map.first_doc(doc_file) == "First line here."

    empty = tmp_path / "b.py"
    empty.write_text("y = 2\n", encoding="utf-8")
    assert "thiếu" in gen_map.first_doc(empty)

    good_pkg = tmp_path / "good"
    good_pkg.mkdir()
    (good_pkg / "m.py").write_text("z = 3\n", encoding="utf-8")
    empty_pkg = tmp_path / "empty_pkg"  # a dir with NO .py -> excluded by `any(p.glob('*.py'))`
    empty_pkg.mkdir()
    (empty_pkg / "README.md").write_text("# hi\n", encoding="utf-8")
    (tmp_path / "var").mkdir()  # DENY dir

    names = gen_map.packages()
    assert "good" in names
    assert "empty_pkg" not in names
    assert "var" not in names


@pytest.mark.audit
def test_gen_map_first_doc_handles_unparseable_source(tmp_path):
    """A file that fails to parse returns a `(parse error: ...)` string, not a raised exception."""
    gen_map = _load_gen_map_module()
    broken = tmp_path / "broken.py"
    broken.write_text("def (:\n  pass\n", encoding="utf-8")  # syntactically invalid
    out = gen_map.first_doc(broken)
    assert out.startswith("(parse error:")


# ---------------------------------------------------------------------------
# Additional coverage: policy on_block hook (policy.py:18), classify_terminal
# success + ToolPolicy terminal route (safety/policy.py), guard happy path and
# the agent_node SUCCESS path (graph/nodes.py:48, 84-103).
# ---------------------------------------------------------------------------


@pytest.mark.audit
def test_policy_gate_invokes_on_block_hook_with_the_request():
    """policy.py:18 — the on_block callback fires exactly once with the blocked request."""
    seen: list[ToolRequest] = []
    gate = PolicyGate(deny={"x"}, on_block=seen.append)
    req = ToolRequest("x")
    gate(req, lambda r: pytest.fail("inner reached on a denied tool"))
    assert seen == [req]


@pytest.mark.audit
@pytest.mark.security
def test_classify_terminal_allows_clean_argv_and_tool_policy_routes_terminal(monkeypatch):
    """classify_terminal returns allowed for a benign argv; ToolPolicy.check routes
    a terminal tool name into classify_terminal (the terminal-name branch)."""
    monkeypatch.delenv("AGENT_ALLOW_GIT_MUTATIONS", raising=False)
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", "/tmp/ws_clean")
    decision = classify_terminal(["python3", "-c", "print(1)"])
    assert decision.allowed is True and decision.risk == "low"

    routed = ToolPolicy().check("terminal_run", {"argv": ["python3", "-c", "print(1)"]})
    assert routed.allowed is True
    blocked = ToolPolicy().check("terminal.run", {"argv": ["bash", "-c", "id"]})
    assert blocked.allowed is False and blocked.code == "shell_exe"


@pytest.mark.audit
@pytest.mark.security
def test_classify_terminal_allows_read_only_git_status(monkeypatch):
    """A non-mutating git subcommand (status) is not in GIT_MUTATIONS, so it passes."""
    monkeypatch.delenv("AGENT_ALLOW_GIT_MUTATIONS", raising=False)
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", "/tmp/ws_git")
    assert classify_terminal(["git", "status"]).allowed is True


@pytest.mark.audit
def test_guard_node_routes_to_agent_when_budget_remains(kernel_factory):
    """graph/nodes.py:48 — with steps left, guard routes forward to the agent node."""
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    session, state = _root_state(kernel, budget=Budget(max_steps=5, steps=0))
    out = guard_node(state, session=session)
    assert out["route"] == "agent"
    assert "session_state" in out


class _ScriptedActionLLM:
    """An llm.chat tool that returns one fixed, valid JSON action string."""

    name = "llm.chat"

    def __init__(self, content: str) -> None:
        self._content = content

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {"ok": True, "content": self._content}


@pytest.mark.audit
@pytest.mark.parametrize(
    ("content", "expected_route"),
    [
        ('{"action":"tool","tool":"echo","args":{"x":1}}', "tool"),
        ('{"action":"delegate","target":"w","spec":{"objective":"o"}}', "delegate"),
        ('{"action":"final","message":"done"}', "finish"),
        ('{"action":"frobnicate"}', "guard"),  # unknown verb -> nudge + back to guard
    ],
)
def test_agent_node_success_path_routes_each_verb(kernel_factory, content, expected_route):
    """graph/nodes.py:84-103 — a parseable action records a step and routes by its verb;
    an unknown verb appends a corrective nudge and loops to guard."""
    kernel, _ = kernel_factory(echo=True, toolbox=False)
    _register_llm(kernel, _ScriptedActionLLM(content))
    session, state = _root_state(kernel, budget=Budget(max_steps=5))
    out = agent_node(state, session=session)
    assert out["route"] == expected_route
    assert out["last_action"]["action"] in {"tool", "delegate", "final", "frobnicate"}
    if expected_route == "guard":
        assert "Unknown" in out["messages"][-1]["content"]
    else:
        # a real verb consumed exactly one step of the budget
        assert budget_from_state(out).steps == 1


# ---------------------------------------------------------------------------
# Hook-arm + remaining-branch closers so this file is self-sufficient on its
# targets (budget.py:20, condense.py:27, retry.py:17, timing.py:21-23,
# safety/policy.py:60/62/66, tools/gen_map.py:53 via a subprocess run).
# ---------------------------------------------------------------------------


@pytest.mark.audit
def test_budget_guard_calls_on_block_hook_once(  ):
    """middleware/budget.py:20 — the on_block hook fires on the blocking call."""
    fired: list[str] = []
    guard = BudgetGuard(Budget(max_same_tool_calls=0), on_block=lambda r: fired.append(r.name))
    out = guard(ToolRequest("e", {"a": 1}), lambda r: {"ok": True})
    assert out["ok"] is False and fired == ["e"]


@pytest.mark.audit
def test_condense_notifies_hook_only_when_value_shrinks():
    """middleware/condense.py:27 — on_condense fires once, and only on an actual shrink."""
    fired: list[str] = []
    mw = CondenseResult(max_chars=3, on_condense=lambda r: fired.append(r.name))
    mw(ToolRequest("short"), lambda r: {"ok": True, "data": "ab"})  # no shrink -> no notify
    mw(ToolRequest("long"), lambda r: {"ok": True, "data": "abcdefgh"})  # shrink -> notify
    assert fired == ["long"]


@pytest.mark.audit
def test_retry_does_not_retry_a_policy_block():
    """middleware/retry.py:17 — a policy_block envelope is never retried."""
    calls = []
    env = {"ok": False, "metadata": {"policy_block": True}}
    out = Retry(attempts=5)(ToolRequest("t"), lambda r: calls.append(r) or env)
    assert len(calls) == 1 and out["ok"] is False


@pytest.mark.audit
def test_timing_swallows_sink_exception(monkeypatch):
    """middleware/timing.py:21-23 — a raising sink must not fail an otherwise-ok call."""
    readings = iter([0.0, 0.001])
    monkeypatch.setattr("middleware.timing.time.perf_counter", lambda: next(readings))

    def boom(record):
        raise RuntimeError("metrics down")

    sentinel = {"ok": True}
    assert TimingLog(boom)(ToolRequest("e"), lambda r: sentinel) is sentinel


@pytest.mark.audit
@pytest.mark.security
@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["echo", "a;b"], "shell_token"),  # safety/policy.py:60
        (["rm", "-rf", "x"], "destructive"),  # safety/policy.py:62
        (["git", "commit", "-m", "x"], "git_mutation"),  # safety/policy.py:66
    ],
)
def test_classify_terminal_remaining_block_branches(monkeypatch, argv, code):
    monkeypatch.delenv("AGENT_ALLOW_GIT_MUTATIONS", raising=False)
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", "/tmp/ws_branches")
    decision = classify_terminal(argv)
    assert decision.allowed is False and decision.code == code


@pytest.mark.audit
def test_classify_terminal_git_mutation_allowed_when_env_opt_in(monkeypatch):
    monkeypatch.setenv("AGENT_ALLOW_GIT_MUTATIONS", "1")
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", "/tmp/ws_git_ok")
    assert classify_terminal(["git", "commit", "-m", "x"]).allowed is True


@pytest.mark.audit
def test_gen_map_runs_as_script_entrypoint(tmp_path):
    """tools/gen_map.py:53 — the `if __name__ == '__main__': raise SystemExit(main())` guard.

    Run a COPY of gen_map.py whose ROOT is rebound to a tmp tree as a subprocess so the
    module-as-script path executes without writing the repo's real MAP.md.
    """
    import subprocess
    import sys

    src = (Path(__file__).resolve().parent.parent / "tools" / "gen_map.py").read_text(encoding="utf-8")
    pkg = tmp_path / "demo_pkg"
    pkg.mkdir()
    (pkg / "mod.py").write_text('"""A demo module. Epic demo."""\n', encoding="utf-8")

    script = tmp_path / "gen_map_copy.py"
    # Rebind ROOT to the tmp tree IN PLACE (keeping `from __future__` first) so the
    # module-as-script path runs without touching the repo's real MAP.md.
    rebind = "ROOT = Path(%r)" % str(tmp_path)
    body = src.replace("ROOT = Path(__file__).resolve().parent.parent", rebind)
    assert rebind in body  # the rebind landed
    script.write_text(body, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "wrote" in proc.stdout
    generated = (tmp_path / "MAP.md").read_text(encoding="utf-8")
    assert "## demo_pkg/" in generated
    assert "A demo module. Epic demo." in generated
