import pytest

from discipline import Budget, JsonGateError, check_finish, condense, parse_action


def test_parse_clean():
    assert parse_action('{"action": "tool", "tool": "echo", "args": {}}')["action"] == "tool"


def test_parse_repairs_fences_and_trailing_comma():
    assert parse_action('```json\n{"action": "final", "message": "ok",}\n```')["action"] == "final"


def test_parse_extracts_embedded_object():
    assert parse_action('action: {"action":"final","message":"x"} thanks')["action"] == "final"


def test_missing_action_raises():
    with pytest.raises(JsonGateError) as ei:
        parse_action('{"tool": "echo"}')
    assert ei.value.stage == "schema"


def test_garbage_raises():
    with pytest.raises(JsonGateError):
        parse_action("not json at all")


def test_condense_truncates():
    out = condense({"text": "x" * 5000}, max_chars=100)
    assert len(out["text"]) < 200
    assert "+4900" in out["text"]


def test_condense_lists():
    out = condense({"items": list(range(50))}, max_list=5)
    assert len(out["items"]) == 6


def test_finish_gate_blocks_unvalidated_code():
    res = check_finish({"code_changed": True, "validation_passed": False}, finish_reason="validated")
    assert res["allowed"] is False


def test_finish_gate_allows_blocker():
    assert check_finish({"code_changed": True, "validation_passed": False}, finish_reason="blocker")["allowed"]


def test_finish_gate_allows_validated():
    assert check_finish({"code_changed": True, "validation_passed": True})["allowed"]


def test_budget_parse_does_not_consume_steps():
    b = Budget(max_steps=3, max_parse_errors=2)
    b.record_parse_error()
    b.record_parse_error()
    assert b.parse_exceeded() is True
    assert b.steps == 0


def test_budget_same_tool():
    b = Budget(max_same_tool_calls=2)
    key = Budget.tool_key("echo", {"a": 1})
    for _ in range(3):
        b.record_tool_call(key)
    assert b.same_tool_exceeded(key) is True
