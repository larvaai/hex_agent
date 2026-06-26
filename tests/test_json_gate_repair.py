"""Deterministic JSON repair-rule pipeline — one case per rule + combined messes. Epic E02."""
from __future__ import annotations

import pytest

from discipline.json_gate import (
    JsonGateError,
    convert_single_quoted_values,
    extract_largest_json_region,
    parse_action,
    parse_json_object,
    quote_unquoted_keys,
    replace_python_literals,
)


def test_valid_json_is_returned_unchanged():
    assert parse_json_object('{"action": "final", "k": 1}') == {"action": "final", "k": 1}


def test_value_containing_triple_backticks_is_not_corrupted():
    # raw-first candidate must win before any fence stripper runs
    assert parse_json_object('{"action": "x", "code": "```py```"}')["code"] == "```py```"


def test_markdown_fenced_object():
    assert parse_action("```json\n{\"action\": \"plan\"}\n```")["action"] == "plan"


def test_prose_wrapped_object_is_extracted():
    raw = "Sure, here is the action:\n{\"action\": \"final\", \"answer\": 42}\nHope that helps!"
    assert parse_action(raw) == {"action": "final", "answer": 42}


def test_trailing_comma_repaired():
    assert parse_action('{"action": "final", "items": [1, 2,],}')["items"] == [1, 2]


def test_python_literals_coerced():
    obj = parse_json_object('{"action": "x", "ok": True, "bad": False, "none": None}')
    assert obj["ok"] is True and obj["bad"] is False and obj["none"] is None


def test_unquoted_keys_quoted():
    obj = parse_json_object('{action: "x", count: 3}')
    assert obj == {"action": "x", "count": 3}


def test_single_quoted_tokens_converted():
    obj = parse_json_object("{'action': 'x', 'list': ['a', 'b']}")
    assert obj == {"action": "x", "list": ["a", "b"]}


def test_missing_closing_brace_balanced():
    assert parse_json_object('{"action": "x", "nested": {"a": 1}')["nested"] == {"a": 1}


def test_apostrophe_inside_double_quoted_string_is_preserved():
    obj = parse_json_object('{"action": "x", "msg": "it\'s fine"}')
    assert obj["msg"] == "it's fine"


def test_combined_mess_local_model_style():
    raw = "```\n{action: 'tool', name: 'fs_read', args: {path: 'a.py',}, done: False,}\n```"
    obj = parse_action(raw)
    assert obj["action"] == "tool"
    assert obj["name"] == "fs_read"
    assert obj["args"] == {"path": "a.py"}
    assert obj["done"] is False


@pytest.mark.parametrize("blob", ['[1, 2, 3]', '"just a string"', "42", "true", "null"])
def test_valid_non_mapping_json_is_rejected(blob):
    with pytest.raises(JsonGateError):
        parse_json_object(blob)


def test_unparseable_text_raises_domain_error():
    with pytest.raises(JsonGateError):
        parse_json_object("this is not json at all <<<")


def test_rule_helpers_are_total_on_garbage():
    # the rules must never throw on arbitrary text (gate-never-leaks guarantee)
    for fn in (replace_python_literals, quote_unquoted_keys, convert_single_quoted_values, extract_largest_json_region):
        fn("{'a: [unbalanced \" \\ True None }{][")
