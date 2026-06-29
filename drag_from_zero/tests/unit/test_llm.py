"""FakeLLM records calls; by_role dispatches scripted responses on ctx['role']."""
from __future__ import annotations

import pytest

from dragzero.llm import FakeLLM, by_role


def test_by_role_returns_scripted_dict():
    responder = by_role({"planner": {"x": 1}})
    assert responder({"role": "planner"}) == {"x": 1}


def test_by_role_invokes_callable_value_with_ctx():
    responder = by_role({"planner": lambda ctx: {"r": ctx["role"]}})
    assert responder({"role": "planner"}) == {"r": "planner"}


def test_by_role_missing_role_no_default_raises_keyerror():
    responder = by_role({"planner": {"x": 1}})
    with pytest.raises(KeyError):
        responder({"role": "worker"})


def test_by_role_default_returned_when_role_absent():
    responder = by_role({"planner": {"x": 1}}, default={"d": 9})
    assert responder({"role": "worker"}) == {"d": 9}


def test_by_role_default_callable_invoked_with_ctx():
    responder = by_role({}, default=lambda ctx: {"role": ctx["role"]})
    assert responder({"role": "ghost"}) == {"role": "ghost"}


def test_fakellm_records_call_and_returns_responder_output():
    out = {"plan": {"ok": True}}
    llm = FakeLLM(lambda ctx: out)
    ctx = {"role": "planner", "task": "t"}
    result = llm.complete(ctx)
    assert result is out
    assert llm.calls == [ctx]


def test_fakellm_calls_starts_empty():
    llm = FakeLLM(lambda ctx: {})
    assert llm.calls == []


def test_fakellm_appends_each_call_in_order():
    llm = FakeLLM(lambda ctx: ctx["role"])
    c1 = {"role": "a"}
    c2 = {"role": "b"}
    llm.complete(c1)
    llm.complete(c2)
    assert llm.calls == [c1, c2]


def test_fakellm_with_by_role_responder():
    llm = FakeLLM(by_role({"planner": {"plan": 1}, "worker": {"work": 2}}))
    assert llm.complete({"role": "planner"}) == {"plan": 1}
    assert llm.complete({"role": "worker"}) == {"work": 2}
    assert llm.calls == [{"role": "planner"}, {"role": "worker"}]
