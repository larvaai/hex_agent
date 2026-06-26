"""tree.yaml loader: referential integrity + acyclic + DFS cursor (no LLM)."""
from __future__ import annotations

import pytest

from decompose_agent.tree import load_tree


def test_loads_and_next_node_cursor(rag_tree_path):
    tree = load_tree(rag_tree_path)
    assert tree.nodes["ai.rag"].status == "decomposed"
    assert tree.nodes["ai.rag"].depth == 0
    assert tree.nodes["ai.rag.corpus"].depth == 1

    # leftmost pending whose depends_on are all done, by (depth, order)
    assert tree.next_node().id == "ai.rag.corpus"
    tree.set_status("ai.rag.corpus", "done")
    # index + queries both unblock; index declared first → wins the (depth, order) sort
    assert tree.next_node().id == "ai.rag.index"
    tree.set_status("ai.rag.index", "done")
    assert tree.next_node().id == "ai.rag.queries"
    tree.set_status("ai.rag.queries", "done")
    # eval depends on index + queries (now both done)
    assert tree.next_node().id == "ai.rag.eval"
    tree.set_status("ai.rag.eval", "done")
    assert tree.next_node() is None  # nothing pending left


def test_children_derived_from_parent_pointers(rag_tree_path):
    tree = load_tree(rag_tree_path)
    assert set(tree.children_of("ai.rag")) == {
        "ai.rag.corpus", "ai.rag.index", "ai.rag.queries", "ai.rag.eval",
    }
    assert tree.children_of("ai.rag.corpus") == ()


def test_eval_blocked_until_deps_done(rag_tree_path):
    tree = load_tree(rag_tree_path)
    tree.set_status("ai.rag.corpus", "done")
    tree.set_status("ai.rag.index", "done")
    # queries still pending → eval (needs index AND queries) must not be picked
    assert tree.next_node().id == "ai.rag.queries"


def test_rejects_dangling_depends_on(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(
        "- {id: a, parent: null, kind: work, status: pending, "
        "depends_on: [ghost], done_when: [{check: all_children_done}]}\n"
    )
    with pytest.raises(ValueError) as e:
        load_tree(p)
    assert "ghost" in str(e.value)


def test_rejects_dangling_parent(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(
        "- {id: a, parent: nope, kind: work, status: pending, "
        "done_when: [{check: all_children_done}]}\n"
    )
    with pytest.raises(ValueError) as e:
        load_tree(p)
    assert "nope" in str(e.value)


def test_rejects_duplicate_id(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(
        "- {id: a, parent: null, kind: work, status: pending, done_when: [{check: all_children_done}]}\n"
        "- {id: a, parent: null, kind: work, status: pending, done_when: [{check: all_children_done}]}\n"
    )
    with pytest.raises(ValueError) as e:
        load_tree(p)
    assert "a" in str(e.value)


def test_rejects_depends_on_cycle(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(
        "- {id: a, parent: null, kind: work, status: pending, depends_on: [b], done_when: [{check: all_children_done}]}\n"
        "- {id: b, parent: null, kind: work, status: pending, depends_on: [a], done_when: [{check: all_children_done}]}\n"
    )
    with pytest.raises(ValueError):
        load_tree(p)
