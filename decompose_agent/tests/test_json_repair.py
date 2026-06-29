"""JSON repair ladder — raw-wins, deterministic-first, total over arbitrary bytes
(lift discipline/json_gate.py:305-394,420-432,483-493)."""
from __future__ import annotations

import pytest

from decompose_agent import json_repair as jr


def test_valid_json_raw_wins_unmutated():
    assert jr.parse_object('{"action": "final", "message": "ok"}') == {
        "action": "final", "message": "ok"
    }


def test_recovers_fenced():
    obj = jr.parse_object('```json\n{"action":"tool","tool":"x","args":{}}\n```')
    assert obj["tool"] == "x"


def test_recovers_prose_wrapped():
    assert jr.parse_object("Sure! Here:\n{\"a\": 1}\nThanks")["a"] == 1


def test_recovers_python_literals():
    assert jr.parse_object('{"ok": True, "no": False, "x": None}') == {
        "ok": True, "no": False, "x": None
    }


def test_recovers_unquoted_keys():
    assert jr.parse_object('{action: "final", message: "hi"}')["action"] == "final"


def test_recovers_single_quoted_dict():
    assert jr.parse_object("{'action': 'final', 'message': 'hi'}")["message"] == "hi"


def test_recovers_truncation():
    assert jr.parse_object('{"a": {"b": 1}')["a"] == {"b": 1}


# ── normalize_action: the three shapes local models actually emit ────────────

def test_normalize_flattened_params_to_args():
    obj = jr.parse_action('{"action":"tool","tool":"fs_write","path":"x","content":"y"}')
    assert obj["action"] == "tool"
    assert obj["args"] == {"path": "x", "content": "y"}


def test_normalize_tool_name_as_action():
    obj = jr.parse_action('{"action":"fs_write","path":"x"}')
    assert obj["action"] == "tool"
    assert obj["tool"] == "fs_write"
    assert obj["args"] == {"path": "x"}


def test_normalize_args_as_string():
    obj = jr.parse_action('{"action":"tool","tool":"x","args":"{\\"path\\":\\"y\\"}"}')
    assert obj["args"] == {"path": "y"}


def test_canonical_action_is_noop():
    obj = jr.parse_action('{"action":"tool","tool":"x","args":{"path":"y"}}')
    assert obj == {"action": "tool", "tool": "x", "args": {"path": "y"}}


# ── retry skeleton differs by call type, embeds a literal, no context re-dump ─

def test_retry_message_propose_vs_decompose():
    p = jr.build_retry_message("propose")
    d = jr.build_retry_message("decompose")
    assert '{"action":"tool"' in p  # propose embeds the action-object skeleton
    assert '[{"id":' in d           # decompose embeds the children-array skeleton
    assert p != d


# ── decompose call returns a children LIST ───────────────────────────────────

def test_parse_children_array_and_wrapped():
    assert [k["id"] for k in jr.parse_children('```json\n[{"id":"c1"},{"id":"c2"}]\n```')] == ["c1", "c2"]
    assert jr.parse_children('{"children":[{"id":"c1"}]}')[0]["id"] == "c1"


# ── totality: each rule swallows its own failure → never raises on junk ───────

FUZZ = [
    "", "   ", "}{", "[[[", '"unterminated', "True", "null", "🙃🙃🙃",
    "{'a':", "\x00\x01", "}" * 50, "{" * 10, "not json at all",
    '{"a":1,}', "[1,2,", "```", "```json```", "{a:b:c}",
]


@pytest.mark.parametrize("s", FUZZ)
def test_repair_rules_never_raise(s):
    jr.light_json_repair(s)
    jr._candidates(s)


@pytest.mark.parametrize("s", FUZZ)
def test_parse_object_only_raises_gate_error(s):
    try:
        jr.parse_object(s)
    except jr.JsonGateError:
        pass
