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


def test_normalize_flattened_tool_args():
    """The exact shape the live local model emitted: params at the top level, args empty.
    Without normalization fs_write received {} and wrote to the workspace dir."""
    a = parse_action('{"action":"tool","tool":"fs_write","path":"text_stats.py","content":"x=1"}')
    assert a["action"] == "tool" and a["tool"] == "fs_write"
    assert a["args"] == {"path": "text_stats.py", "content": "x=1"}
    assert "path" not in a and "content" not in a  # leftovers moved under args


def test_normalize_action_name_as_action():
    """Tool name used as the 'action' value, params flattened."""
    a = parse_action('{"action":"fs_read","path":"notes.md"}')
    assert a["action"] == "tool" and a["tool"] == "fs_read"
    assert a["args"] == {"path": "notes.md"}


def test_normalize_args_double_encoded_string():
    a = parse_action('{"action":"tool","tool":"fs_list","args":"{\\"path\\":\\".\\"}"}')
    assert a["args"] == {"path": "."}


def test_normalize_leaves_canonical_and_final_untouched():
    canonical = parse_action('{"action":"tool","tool":"echo","args":{"msg":"hi"}}')
    assert canonical == {"action": "tool", "tool": "echo", "args": {"msg": "hi"}}
    final = parse_action('{"action":"final","message":"done","finish_reason":"done"}')
    assert final["action"] == "final" and "args" not in final


def test_budget_resets_consecutive_parse_errors_on_progress():
    """The gate trips on the CONSECUTIVE streak, not the lifetime total. A fumble the model
    recovers from must not count against a later, unrelated fumble."""
    b = Budget(max_parse_errors=2)
    b.record_parse_error()
    assert b.consecutive_parse_errors == 1 and b.parse_exceeded() is False
    b.record_step()  # progress clears the streak
    assert b.consecutive_parse_errors == 0
    b.record_parse_error()  # an isolated later fumble — lifetime total is now 2…
    assert b.parse_errors == 2 and b.parse_exceeded() is False  # …but not 2 in a row
    b.record_parse_error()  # now two in a row
    assert b.parse_exceeded() is True


def test_budget_record_parse_success_clears_streak():
    """The supervisor loop recovers without consuming a step, so it clears the streak explicitly."""
    b = Budget(max_parse_errors=2)
    b.record_parse_error()
    b.record_parse_success()
    assert b.consecutive_parse_errors == 0 and b.parse_errors == 1


def test_budget_same_tool():
    b = Budget(max_same_tool_calls=2)
    key = Budget.tool_key("echo", {"a": 1})
    for _ in range(3):
        b.record_tool_call(key)
    assert b.same_tool_exceeded(key) is True
