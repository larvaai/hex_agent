"""Node record invariants — a structurally-wrong node cannot exist (lift control/events.py:134-151)."""
from __future__ import annotations

import pytest

from decompose_agent.node import Node

VALID = {
    "id": "ai.rag.corpus",
    "parent": "ai.rag",
    "kind": "work",
    "status": "pending",
    "depends_on": [],
    "max_attempts": 3,
    "done_when": [
        {"check": "row_count_gte", "params": {"n": 200}, "artifact": "corpus.jsonl"},
    ],
}


def test_from_dict_builds_and_roundtrips():
    n = Node.from_dict(VALID)
    assert n.id == "ai.rag.corpus"
    assert n.parent == "ai.rag"
    assert n.kind == "work"
    assert n.status == "pending"
    assert n.max_attempts == 3
    assert len(n.done_when) == 1
    c = n.done_when[0]
    assert (c.check, c.params, c.artifact) == ("row_count_gte", {"n": 200}, "corpus.jsonl")
    d = n.as_dict()
    assert Node.from_dict(d).as_dict() == d


def test_all_children_done_needs_no_artifact():
    n = Node.from_dict(
        {"id": "ai.rag", "kind": "work", "status": "decomposed",
         "done_when": [{"check": "all_children_done"}]}
    )
    assert n.done_when[0].check == "all_children_done"
    assert n.done_when[0].artifact is None
    assert n.done_when[0].params == {}


@pytest.mark.parametrize("bad_key", ["verdict", "passed", "status", "score", "done"])
def test_rejects_verdict_field_in_criterion(bad_key):
    d = dict(VALID)
    d["done_when"] = [{"check": "file_exists", "artifact": "x.json", bad_key: True}]
    with pytest.raises(ValueError) as e:
        Node.from_dict(d)
    assert bad_key in str(e.value)


def test_rejects_missing_check():
    d = dict(VALID)
    d["done_when"] = [{"params": {}, "artifact": "x.json"}]
    with pytest.raises(ValueError):
        Node.from_dict(d)


def test_rejects_data_check_missing_artifact():
    d = dict(VALID)
    d["done_when"] = [{"check": "file_exists", "params": {}}]
    with pytest.raises(ValueError):
        Node.from_dict(d)


@pytest.mark.parametrize("bad", ["/abs/path.json", "../escape.json", "sub/../../x", "~/secret"])
def test_rejects_unsafe_artifact(bad):
    d = dict(VALID)
    d["done_when"] = [{"check": "file_exists", "artifact": bad}]
    with pytest.raises(ValueError):
        Node.from_dict(d)


def test_rejects_bad_status():
    d = dict(VALID)
    d["status"] = "finished"
    with pytest.raises(ValueError):
        Node.from_dict(d)


def test_rejects_bad_kind():
    d = dict(VALID)
    d["kind"] = "reduce"  # fenced OUT this round
    with pytest.raises(ValueError):
        Node.from_dict(d)


def test_frozen_node_cannot_be_mutated():
    n = Node.from_dict(VALID)
    with pytest.raises(Exception):
        n.status = "done"  # type: ignore[misc]
