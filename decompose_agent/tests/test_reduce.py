"""Reduce nodes — pure-code compose (no LLM). Closes COMPOSE_FAIL: a node gathers its
siblings' outputs and produces the aggregate artifact its done_when checks."""
from __future__ import annotations

import json

import pytest

from decompose_agent import reduce as R
from decompose_agent.node import Node
from decompose_agent.workspace import node_dir, write_artifact


def _reduce_node(reduce_op, inputs, done_when):
    return Node.from_dict({"id": "P.reduce", "parent": "P", "kind": "reduce", "status": "pending",
                           "reduce_op": reduce_op, "inputs": inputs, "depends_on": ["P.a", "P.b"],
                           "done_when": done_when})


def test_node_accepts_reduce_kind_and_op():
    n = _reduce_node("merge_json", [{"from": "P.a", "artifact": "a.json"}],
                     [{"check": "json_field_exists", "params": {"ptr": "/a"}, "artifact": "out.json"}])
    assert n.kind == "reduce" and n.reduce_op == "merge_json"
    assert n.inputs[0]["from"] == "P.a"
    assert Node.from_dict(n.as_dict()).as_dict() == n.as_dict()  # round-trips


def test_node_rejects_unknown_reduce_op():
    with pytest.raises(ValueError):
        _reduce_node("bogus_op", [], [{"check": "file_exists", "artifact": "o.json"}])


def test_merge_json_deep_merges_sibling_outputs(tmp_path):
    a = Node.from_dict({"id": "P.a", "kind": "work", "done_when": [{"check": "file_exists", "artifact": "a.json"}]})
    b = Node.from_dict({"id": "P.b", "kind": "work", "done_when": [{"check": "file_exists", "artifact": "b.json"}]})
    write_artifact(tmp_path, "P", a, "a.json", json.dumps({"recall_at_5": 0.91}))
    write_artifact(tmp_path, "P", b, "b.json", json.dumps({"queries": list(range(50))}))
    node = _reduce_node("merge_json",
                        [{"from": "P.a", "artifact": "a.json", "as": "report.json"},
                         {"from": "P.b", "artifact": "b.json", "as": "report.json"}],
                        [{"check": "json_field_in_range", "params": {"ptr": "/recall_at_5", "min": 0.8, "max": 1.0}, "artifact": "report.json"},
                         {"check": "json_len_gte", "params": {"ptr": "/queries", "n": 50}, "artifact": "report.json"}])
    R.run_reduce(node, tmp_path, "P")
    out = json.loads((node_dir(tmp_path, "P", "P.reduce") / "report.json").read_text())
    assert out["recall_at_5"] == 0.91 and len(out["queries"]) == 50  # both inputs merged


def test_pick_copies_each_input_to_its_dst(tmp_path):
    a = Node.from_dict({"id": "P.a", "kind": "work", "done_when": [{"check": "file_exists", "artifact": "x.json"}]})
    write_artifact(tmp_path, "P", a, "x.json", json.dumps({"score": 0.95}))
    node = _reduce_node("pick", [{"from": "P.a", "artifact": "x.json", "as": "recall.json"}],
                        [{"check": "json_field_in_range", "params": {"ptr": "/score", "min": 0.8, "max": 1.0}, "artifact": "recall.json"}])
    R.run_reduce(node, tmp_path, "P")
    assert json.loads((node_dir(tmp_path, "P", "P.reduce") / "recall.json").read_text())["score"] == 0.95


def test_manifest_lists_inputs(tmp_path):
    a = Node.from_dict({"id": "P.a", "kind": "work", "done_when": [{"check": "file_exists", "artifact": "a.json"}]})
    write_artifact(tmp_path, "P", a, "a.json", "{}")
    node = _reduce_node("manifest", [{"from": "P.a", "artifact": "a.json"}],
                        [{"check": "json_field_exists", "params": {"ptr": "/inputs"}, "artifact": "manifest.json"}])
    R.run_reduce(node, tmp_path, "P")
    man = json.loads((node_dir(tmp_path, "P", "P.reduce") / "manifest.json").read_text())
    assert man["inputs"][0]["from"] == "P.a" and man["inputs"][0]["exists"] is True


def test_resolve_inputs_points_at_sibling_dirs(tmp_path):
    node = _reduce_node("pick", [{"from": "P.a", "artifact": "a.json", "as": "o.json"}],
                        [{"check": "file_exists", "artifact": "o.json"}])
    resolved = R.resolve_inputs(node, tmp_path, "P")
    assert resolved[0][0] == "o.json"
    assert resolved[0][1] == node_dir(tmp_path, "P", "P.a") / "a.json"


def test_rag_eval_harness_with_reduce_runs_end_to_end(tmp_path, rag_tree_path):
    # the spec's worked example, now runnable: 4 leaves + a reduce that composes the metric report
    import pathlib

    from decompose_agent import worker as W
    from decompose_agent.solve import solve
    from decompose_agent.tree import load_tree

    fixture = pathlib.Path(rag_tree_path).parent / "rag_tree_reduce.yaml"
    tree = load_tree(fixture)
    res = solve(tree, W.ScriptedWorker(satisfy=tree), root="ai.rag", workspace_root=tmp_path)
    assert res.blocked is None
    assert tree.nodes["ai.rag._reduce"].kind == "reduce"
    assert all(n.status == "done" for n in tree.nodes.values())
