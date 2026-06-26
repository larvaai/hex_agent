"""solve() decompose path + recursion + DEC-D4 compose. Detectors D2/D4/D8/D10/D12 + F1/F3."""
from __future__ import annotations

from decompose_agent import worker as W
from decompose_agent.budget import RootBudget
from decompose_agent.solve import _close_done_parents, solve
from decompose_agent.journal import Journal
from decompose_agent.tree import load_tree


def _load(tmp_path, text):
    p = tmp_path / "t.yaml"
    p.write_text(text)
    return load_tree(p)


# structural parent (done_when = all_children_done ×2, dwc=2) → decomposes, then completes
STRUCTURAL = (
    "- {id: P, parent: null, kind: work, status: pending, depends_on: [],\n"
    "   done_when: [{check: all_children_done}, {check: all_children_done}]}\n"
)


def test_happy_decompose_then_children_done_then_parent_done(tmp_path):
    tree = _load(tmp_path, STRUCTURAL)
    sw = W.ScriptedWorker(satisfy=tree)  # fails P's leaf (no artifact), synth-splits, satisfies kids
    budget = RootBudget(max_steps=100)
    res = solve(tree, sw, root="P", workspace_root=tmp_path, budget=budget)
    assert res.blocked is None
    assert tree.nodes["P"].status == "decomposed" or tree.nodes["P"].status == "done"
    assert tree.nodes["P"].status == "done"
    kids = tree.children_of("P")
    assert len(kids) >= 2 and all(tree.nodes[k].status == "done" for k in kids)
    assert budget.steps > 3  # F3: parent's K leaf-fails (3) + the decompose call + kids each cost a step


def _metric(ptr, lo, hi, art):
    return {"check": "json_field_in_range", "params": {"ptr": ptr, "min": lo, "max": hi}, "artifact": art}


# substantive-metric parent (dwc=2) that fails its leaf attempts → must decompose
METRIC_PARENT = (
    "- {id: P, parent: null, kind: work, status: pending, depends_on: [],\n"
    "   done_when: [{check: json_field_in_range, params: {ptr: /m, min: 0.8, max: 1.0}, artifact: recall.json},\n"
    "              {check: json_field_in_range, params: {ptr: /n, min: 0.0, max: 1.0}, artifact: recall.json}]}\n"
)


def test_D2_not_smaller_blocks_after_one_redecompose(tmp_path):
    tree = _load(tmp_path, METRIC_PARENT)
    big0 = [{"id": "P.a", "done_when": [_metric("/m", 0.9, 1.0, "a.json"), _metric("/n", 0.1, 0.9, "a.json")]},
            {"id": "P.b", "done_when": [_metric("/m", 0.9, 1.0, "b.json")]}]   # P.a dwc=2, not smaller
    big1 = [{"id": "P.x", "done_when": [_metric("/m", 0.9, 1.0, "x.json"), _metric("/n", 0.1, 0.9, "x.json")]},
            {"id": "P.y", "done_when": [_metric("/m", 0.9, 1.0, "y.json")]}]   # different ids → different sig
    sw = W.ScriptedWorker(scripts={"P": [W.write_action({})]},
                          decompose_scripts={"P": [big0, big1]})
    res = solve(tree, sw, root="P", workspace_root=tmp_path)
    assert tree.nodes["P"].status == "blocked"
    assert res.blocked.reason == "NOT_SMALLER"


def test_D4_identical_redecompose_blocks_stuck_immediately(tmp_path):
    tree = _load(tmp_path, METRIC_PARENT)
    same = [{"id": "P.a", "done_when": [_metric("/m", 0.9, 1.0, "a.json"), _metric("/n", 0.1, 0.9, "a.json")]},
            {"id": "P.b", "done_when": [_metric("/m", 0.9, 1.0, "b.json")]}]   # rejected (not smaller) AND identical twice
    sw = W.ScriptedWorker(scripts={"P": [W.write_action({})]},
                          decompose_scripts={"P": [same, same]})
    res = solve(tree, sw, root="P", workspace_root=tmp_path)
    assert res.blocked.reason == "STUCK_DECOMP"


def test_D10_budget_exhausts_in_recursion_and_F3_decompose_charges(tmp_path):
    tree = _load(tmp_path, STRUCTURAL)
    sw = W.ScriptedWorker(satisfy=tree)
    budget = RootBudget(max_steps=3)  # exactly covers P's 3 leaf attempts; the decompose step trips it
    res = solve(tree, sw, root="P", workspace_root=tmp_path, budget=budget)
    assert res.blocked.reason == "BUDGET"  # F3: decompose() charged a step → exceeded


def test_D8_max_depth_blocks(tmp_path):
    # linear chain of decomposed parents → the leaf sits at depth 7 (> MAX_DEPTH=6)
    lines = []
    for i in range(7):
        parent = "null" if i == 0 else f"n{i-1}"
        lines.append(f"- {{id: n{i}, parent: {parent}, kind: work, status: decomposed, done_when: [{{check: all_children_done}}]}}")
    lines.append("- {id: n7, parent: n6, kind: work, status: pending, depends_on: [], done_when: [{check: file_exists, artifact: o.txt}]}")
    tree = _load(tmp_path, "\n".join(lines) + "\n")
    res = solve(tree, W.ScriptedWorker(satisfy=tree), root="n0", workspace_root=tmp_path)
    assert tree.nodes["n7"].status == "blocked"
    assert res.blocked.reason == "MAX_DEPTH"


def test_child_blocked_propagates_to_parent(tmp_path):
    tree = _load(tmp_path, STRUCTURAL)
    kids = [{"id": "P.bad", "done_when": [{"check": "file_exists", "artifact": "bad.txt"}]},
            {"id": "P.ok", "done_when": [{"check": "file_exists", "artifact": "ok.txt"}]}]
    sw = W.ScriptedWorker(
        scripts={"P": [W.write_action({})], "P.bad": [W.write_action({})], "P.ok": [W.write_action({"ok.txt": "x"})]},
        decompose_scripts={"P": [kids]},
    )
    res = solve(tree, sw, root="P", workspace_root=tmp_path)
    assert tree.nodes["P.bad"].status == "blocked"
    assert tree.nodes["P"].status == "blocked"
    assert res.blocked.reason in ("CHILD_BLOCKED", "UNSOLVABLE_LEAF") or "CHILD_BLOCKED" in tree.nodes["P"].notes


def test_F1_decomposed_parent_with_zero_children_is_not_done(tmp_path):
    tree = _load(tmp_path, "- {id: P, parent: null, kind: work, status: decomposed, done_when: [{check: all_children_done}]}\n")
    journal = Journal(tmp_path, "P")
    _close_done_parents(tree, tmp_path, "P", journal)
    assert tree.nodes["P"].status != "done"  # all([]) is True in Python — must NOT vacuous-done


def test_D12_compose_fail_when_children_done_but_parent_metric_absent(tmp_path):
    tree = _load(tmp_path, METRIC_PARENT)
    kids = [{"id": "P.c0", "done_when": [_metric("/m", 0.9, 1.0, "c0.json")]},   # covers /m, dwc=1
            {"id": "P.c1", "done_when": [_metric("/n", 0.1, 0.9, "c1.json")]}]   # covers /n, dwc=1
    sw = W.ScriptedWorker(
        scripts={"P": [W.write_action({})],
                 "P.c0": [W.write_action({"c0.json": '{"m": 0.95}'})],
                 "P.c1": [W.write_action({"c1.json": '{"n": 0.5}'})]},
        decompose_scripts={"P": [kids]},
    )
    res = solve(tree, sw, root="P", workspace_root=tmp_path)
    # children done (in their own dirs), but recall.json never materializes in P's dir → COMPOSE_FAIL
    assert all(tree.nodes[k].status == "done" for k in tree.children_of("P"))
    assert tree.nodes["P"].status == "blocked"
    assert res.blocked.reason == "COMPOSE_FAIL"
