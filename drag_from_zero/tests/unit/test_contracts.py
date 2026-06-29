"""Contract dataclasses: round-trips, defaults, and str-enum coercion."""
from dragzero.contracts import (
    DelegationDecision,
    DelegationMode,
    PlanSpec,
    PlanStep,
    TaskStatus,
    ToolCall,
)


def test_planstep_roundtrip_and_default_status():
    d = {"id": "s1", "description": "do it"}
    step = PlanStep.from_dict(d)
    assert step.status == "pending"  # default when key absent
    assert step.to_dict() == {"id": "s1", "description": "do it", "status": "pending"}


def test_planstep_explicit_status_preserved():
    step = PlanStep.from_dict({"id": "s2", "description": "x", "status": "done"})
    assert step.status == "done"
    assert step.to_dict()["status"] == "done"


def test_planspec_roundtrip_with_steps_and_next():
    d = {
        "steps": [
            {"id": "s1", "description": "first"},
            {"id": "s2", "description": "second", "status": "done"},
        ],
        "next": "s2",
    }
    spec = PlanSpec.from_dict(d)
    assert spec.next == "s2"
    assert [s.id for s in spec.steps] == ["s1", "s2"]
    assert all(isinstance(s, PlanStep) for s in spec.steps)
    assert spec.to_dict() == {
        "steps": [
            {"id": "s1", "description": "first", "status": "pending"},
            {"id": "s2", "description": "second", "status": "done"},
        ],
        "next": "s2",
    }


def test_planspec_empty_defaults():
    spec = PlanSpec.from_dict({})
    assert spec.steps == []
    assert spec.next is None
    assert spec.to_dict() == {"steps": [], "next": None}


def test_toolcall_dict_args_kept():
    call = ToolCall.from_dict({"tool": "search", "args": {"q": "hi"}})
    assert call.tool == "search"
    assert call.args == {"q": "hi"}
    assert call.to_dict() == {"tool": "search", "args": {"q": "hi"}}


def test_toolcall_nondict_args_coerced_to_empty():
    call = ToolCall.from_dict({"tool": "search", "args": ["x"]})
    assert call.args == {}  # list args -> {}


def test_toolcall_missing_tool_defaults_empty():
    call = ToolCall.from_dict({})
    assert call.tool == ""
    assert call.args == {}


def test_delegation_decision_solo_roundtrip():
    d = {"mode": "solo", "reasoning": "trivial"}
    dec = DelegationDecision.from_dict(d)
    assert dec.mode == DelegationMode.SOLO
    assert dec.target is None
    assert dec.subtask is None
    assert dec.reasoning == "trivial"
    out = dec.to_dict()
    assert out["mode"] == "solo"  # string value, not the enum member
    # `children` (multi-child decompose mode) defaults to [] and round-trips.
    assert out == {"mode": "solo", "target": None, "subtask": None, "reasoning": "trivial", "children": []}


def test_delegation_decision_delegate_roundtrip():
    d = {"mode": "delegate", "target": "worker", "subtask": "do part", "reasoning": "split"}
    dec = DelegationDecision.from_dict(d)
    assert dec.mode == DelegationMode.DELEGATE
    assert dec.target == "worker"
    assert dec.subtask == "do part"
    out = dec.to_dict()
    assert out["mode"] == "delegate"
    assert out == {"mode": "delegate", "target": "worker", "subtask": "do part", "reasoning": "split", "children": []}


def test_delegation_decision_children_roundtrip():
    """decompose mode carries a `children` list (multi-child split) that round-trips."""
    kids = [{"id": "c1", "goal": "part one"}, {"id": "c2", "goal": "part two"}]
    dec = DelegationDecision.from_dict({"mode": "delegate", "target": "team", "children": kids})
    assert dec.children == kids
    assert dec.to_dict()["children"] == kids


def test_delegation_decision_default_reasoning():
    dec = DelegationDecision.from_dict({"mode": "solo"})
    assert dec.reasoning == ""


def test_str_enums_equal_their_string_values():
    assert DelegationMode.SOLO == "solo"
    assert DelegationMode.DELEGATE == "delegate"
    assert TaskStatus.DONE == "done"
    assert TaskStatus.PENDING == "pending"
