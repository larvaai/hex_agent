"""solve() leaf-attempt path (ScriptedWorker, deterministic): activate→propose→run→gate→
DONE|retry-K|BLOCKED, DFS cursor, all_children_done closure, parse/step budgets."""
from __future__ import annotations

import json

from decompose_agent import worker as W
from decompose_agent.budget import RootBudget
from decompose_agent.journal import Journal
from decompose_agent.solve import solve
from decompose_agent.tree import load_tree


def _load(tmp_path, text):
    p = tmp_path / "t.yaml"
    p.write_text(text)
    return load_tree(p)


ONE_LEAF = (
    "- {id: t.leaf, parent: null, kind: work, status: pending, depends_on: [],\n"
    "   done_when: [{check: file_exists, artifact: out.txt}]}\n"
)

PARENT_CHILD = (
    "- {id: P, parent: null, kind: work, status: decomposed, done_when: [{check: all_children_done}]}\n"
    "- {id: P.c, parent: P, kind: work, status: pending, depends_on: [],\n"
    "   done_when: [{check: file_exists, artifact: out.txt}]}\n"
)


def test_leaf_pass_marks_done_and_stamps_activation(tmp_path):
    tree = _load(tmp_path, ONE_LEAF)
    sw = W.ScriptedWorker({"t.leaf": [W.write_action({"out.txt": "hello"})]})
    solve(tree, sw, root="t", workspace_root=tmp_path)
    assert tree.nodes["t.leaf"].status == "done"
    assert tree.nodes["t.leaf"].activated_at is not None  # activate stamped → artifact fresh


def test_leaf_fail_dwc1_blocks_unsolvable_after_K(tmp_path):
    tree = _load(tmp_path, ONE_LEAF)
    sw = W.ScriptedWorker({"t.leaf": [W.write_action({})]})  # writes nothing → gate FAIL every attempt
    budget = RootBudget(max_steps=100)
    res = solve(tree, sw, root="t", workspace_root=tmp_path, budget=budget)
    assert tree.nodes["t.leaf"].status == "blocked"
    assert res.blocked.reason == "UNSOLVABLE_LEAF"
    assert budget.steps == 5  # K_leaf floor for dwc==1


def test_parse_fumble_does_not_consume_step_then_recovers(tmp_path):
    tree = _load(tmp_path, ONE_LEAF)
    sw = W.ScriptedWorker({"t.leaf": ["{broken json", W.write_action({"out.txt": "ok"})]})
    budget = RootBudget(max_steps=100)
    solve(tree, sw, root="t", workspace_root=tmp_path, budget=budget)
    assert tree.nodes["t.leaf"].status == "done"
    assert budget.steps == 1  # the fumble cost no step; only the good attempt did


def test_step_budget_hard_stop_blocks_budget(tmp_path):
    tree = _load(tmp_path, ONE_LEAF)
    sw = W.ScriptedWorker({"t.leaf": [W.write_action({})]})  # always fails → keeps attempting
    budget = RootBudget(max_steps=1)
    res = solve(tree, sw, root="t", workspace_root=tmp_path, budget=budget)
    assert tree.nodes["t.leaf"].status == "blocked"
    assert res.blocked.reason == "BUDGET"


def test_parent_done_via_all_children_done_closure(tmp_path):
    tree = _load(tmp_path, PARENT_CHILD)
    sw = W.ScriptedWorker({"P.c": [W.write_action({"out.txt": "x"})]})
    solve(tree, sw, root="P", workspace_root=tmp_path)
    assert tree.nodes["P.c"].status == "done"
    assert tree.nodes["P"].status == "done"  # closed only because its one child is done


def test_dfs_cursor_walk_completes_rag_tree(tmp_path, rag_tree_path):
    tree = load_tree(rag_tree_path)
    sw = W.ScriptedWorker(satisfy=tree)  # deterministic: synthesize passing artifacts per node
    res = solve(tree, sw, root="ai.rag", workspace_root=tmp_path)
    assert res.blocked is None
    assert all(n.status == "done" for n in tree.nodes.values())


def test_journal_appends_each_attempt_and_is_readable(tmp_path):
    tree = _load(tmp_path, ONE_LEAF)
    sw = W.ScriptedWorker({"t.leaf": [W.write_action({})]})  # 5 failing attempts
    journal = Journal(tmp_path, "t")
    solve(tree, sw, root="t", workspace_root=tmp_path, journal=journal)
    recs = journal.records("t.leaf")
    attempts = [r for r in recs if r.get("event") == "attempt"]
    assert len(attempts) == 5
    assert all({"node", "action", "verdict"} <= set(r) for r in attempts)


def test_solve_blocks_on_worker_error_without_burning_attempts(tmp_path):
    # a dead LLM is infra failure, not a hard task → block immediately, don't waste K attempts
    tree = _load(tmp_path, ONE_LEAF)

    class _DeadWorker:
        def propose(self, ctx):
            raise W.WorkerError("cannot reach the LLM at http://x; is the server running?")

        def decompose(self, *a, **k):
            raise W.WorkerError("dead")

    budget = RootBudget(max_steps=100)
    res = solve(tree, _DeadWorker(), root="t", workspace_root=tmp_path, budget=budget)
    assert tree.nodes["t.leaf"].status == "blocked"
    assert res.blocked.reason == "WORKER_ERROR"
    assert budget.steps == 0  # never charged a step against the dead endpoint


def test_journal_tail_tolerates_corruption(tmp_path):
    journal = Journal(tmp_path, "t")
    journal.append("t.leaf", {"event": "attempt", "verdict": "FAIL"})
    # simulate a torn final line from a crash mid-write
    with journal._path("t.leaf").open("a", encoding="utf-8") as f:
        f.write('{"event": "attempt", "verd')
    tail = journal.tail("t.leaf", 3)
    assert len(tail) == 1 and tail[0]["verdict"] == "FAIL"  # torn line skipped, not raised
