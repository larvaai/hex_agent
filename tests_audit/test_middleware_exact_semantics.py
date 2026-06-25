"""Exact callback, ordering and retry semantics for every middleware."""
from __future__ import annotations

import pytest

from core.bootstrap import build_kernel
from core.schemas import ToolRequest
from discipline import Budget
from middleware import BudgetGuard, CondenseResult, PolicyGate, Retry, TimingLog


@pytest.mark.audit
def test_bootstrap_middleware_order_is_outer_to_inner_and_configured_exactly():
    kernel = build_kernel(
        {
            "features": {},
            "middleware": {
                "timing": {"enabled": True},
                "policy": {"enabled": True, "deny": ["blocked"]},
                "retry": {"enabled": True, "attempts": 4},
                "condense": {"enabled": True, "max_chars": 11, "max_list": 2},
            },
        }
    )

    assert [type(item) for item in kernel._middlewares] == [TimingLog, PolicyGate, Retry, CondenseResult]
    assert kernel._middlewares[1].deny == {"blocked"}
    assert kernel._middlewares[2].attempts == 4
    assert (kernel._middlewares[3].max_chars, kernel._middlewares[3].max_list) == (11, 2)


@pytest.mark.audit
def test_timing_emits_one_exact_measurement_and_returns_same_envelope(monkeypatch):
    readings = iter([10.0, 10.012])
    monkeypatch.setattr("middleware.timing.time.perf_counter", lambda: next(readings))
    seen = []
    middleware = TimingLog(seen.append)
    request = ToolRequest("echo")
    envelope = {"ok": True, "data": {"x": 1}}

    returned = middleware(request, lambda actual: envelope)

    assert returned is envelope
    assert seen == [{"tool": "echo", "ok": True, "ms": 12.0}]


@pytest.mark.audit
def test_timing_sink_failure_does_not_turn_successful_tool_into_failure():
    def broken_sink(record):
        raise RuntimeError("metrics backend down")

    envelope = {"ok": True}
    returned = TimingLog(broken_sink)(ToolRequest("echo"), lambda request: envelope)
    assert returned is envelope


@pytest.mark.audit
def test_budget_guard_blocks_only_after_exact_limit_and_calls_hook_once():
    budget = Budget(max_same_tool_calls=2)
    blocked = []
    guard = BudgetGuard(budget, on_block=lambda request: blocked.append(request.request_id))
    request = ToolRequest("echo", {"x": 1})
    calls = []

    first = guard(request, lambda actual: calls.append(actual) or {"ok": True})
    second = guard(request, lambda actual: calls.append(actual) or {"ok": True})
    third = guard(request, lambda actual: calls.append(actual) or {"ok": True})

    assert first["ok"] is True and second["ok"] is True
    assert third["ok"] is False and third["metadata"]["budget_block"] is True
    assert calls == [request, request]
    assert blocked == [request.request_id]


@pytest.mark.audit
def test_policy_gate_never_calls_inner_and_hook_receives_same_request():
    blocked = []
    request = ToolRequest("forbidden")
    gate = PolicyGate(deny={"forbidden"}, on_block=blocked.append)

    result = gate(request, lambda actual: pytest.fail("denied call reached inner handler"))

    assert result["ok"] is False
    assert result["metadata"]["policy_block"] is True
    assert blocked == [request]


@pytest.mark.audit
def test_condense_skips_llm_and_notifies_only_when_value_actually_changes():
    notified = []
    middleware = CondenseResult(max_chars=5, max_list=2, on_condense=notified.append)
    llm = {"ok": True, "data": {"content": "unchanged-long-content"}}
    short = {"ok": True, "data": "abc"}
    long = {"ok": True, "data": "abcdefgh"}

    assert middleware(ToolRequest("llm.chat"), lambda request: llm) is llm
    assert middleware(ToolRequest("short"), lambda request: short)["data"] == "abc"
    assert middleware(ToolRequest("long"), lambda request: long)["data"] != "abcdefgh"
    assert [request.name for request in notified] == ["long"]


@pytest.mark.audit
@pytest.mark.parametrize(
    ("responses", "attempts", "expected_calls", "expected_ok"),
    [
        ([{"ok": True}], 5, 1, True),
        ([{"ok": False}, {"ok": True}], 5, 2, True),
        ([{"ok": False}] * 5, 3, 3, False),
        ([{"ok": False, "metadata": {"policy_block": True}}], 5, 1, False),
        ([{"ok": False, "metadata": {"kind": "effect", "idempotent": False}}], 5, 1, False),
    ],
)
def test_retry_call_count_matrix(responses, attempts, expected_calls, expected_ok):
    queue = list(responses)
    calls = []

    def inner(request):
        calls.append(request)
        return queue.pop(0) if queue else responses[-1]

    result = Retry(attempts=attempts)(ToolRequest("tool"), inner)
    assert len(calls) == expected_calls
    assert result["ok"] is expected_ok


@pytest.mark.audit
def test_retry_does_not_loop_on_non_mapping_inner_result():
    calls = []
    result = Retry(attempts=10)(ToolRequest("tool"), lambda request: calls.append(request) or "bad")
    assert result == "bad"
    assert len(calls) == 1
