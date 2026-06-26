"""Content-addressed, transactional decomposition store (F4).
Staging file IS the cache; commit attaches children + flips status in ONE os.replace."""
from __future__ import annotations

import yaml

from decompose_agent import store as S
from decompose_agent.tree import load_tree


PARENT_CHILD_SRC = (
    "- {id: P, parent: null, kind: work, status: active, depends_on: [],\n"
    "   done_when: [{check: all_children_done}, {check: all_children_done}]}\n"
)

CHILDREN = [
    {"id": "P.c0", "done_when": [{"check": "file_exists", "artifact": "c0.txt"}]},
    {"id": "P.c1", "done_when": [{"check": "file_exists", "artifact": "c1.txt"}]},
]


def _tree(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(PARENT_CHILD_SRC)
    return load_tree(p)


def test_decomp_id_is_stable(tmp_path):
    tree = _tree(tmp_path)
    a = S.decomp_id(tree.nodes["P"])
    b = S.decomp_id(tree.nodes["P"])
    assert a == b and len(a) == 64  # sha256 hex


def test_get_miss_returns_none(tmp_path):
    cache = S.DecompCache(tmp_path, "P")
    assert cache.get("deadbeef") is None


def test_stage_is_the_cache(tmp_path):
    cache = S.DecompCache(tmp_path, "P")
    did = "abc123"
    cache.stage(did, CHILDREN)
    got = cache.get(did)
    assert got == CHILDREN  # verbatim, read straight from decompositions/<id>.yaml


def test_crash_before_replace_leaves_tree_old_but_cache_hits(tmp_path):
    tree = _tree(tmp_path)
    cache = S.DecompCache(tmp_path, "P")
    did = S.decomp_id(tree.nodes["P"])
    cache.stage(did, CHILDREN)  # staged, but commit() (the tree os.replace) never ran
    assert not cache.tree_state_path.exists()       # on-disk tree untouched
    assert tree.nodes["P"].status == "active"       # in-memory tree untouched
    assert cache.get(did) == CHILDREN               # resume can recover children verbatim → no re-sample


def test_commit_attaches_children_and_flips_status_atomically(tmp_path):
    tree = _tree(tmp_path)
    cache = S.DecompCache(tmp_path, "P")
    did = S.decomp_id(tree.nodes["P"])
    cache.commit(tree, "P", CHILDREN, did)
    # in-memory: parent decomposed, children attached as pending at depth+1
    assert tree.nodes["P"].status == "decomposed"
    assert set(tree.children_of("P")) == {"P.c0", "P.c1"}
    assert tree.nodes["P.c0"].status == "pending" and tree.nodes["P.c0"].depth == 1
    # on-disk: one tree_state.yaml with both the flip and the children present together
    state = yaml.safe_load(cache.tree_state_path.read_text())
    ids = {n["id"]: n for n in state}
    assert ids["P"]["status"] == "decomposed"
    assert "P.c0" in ids and "P.c1" in ids


def test_resume_get_returns_verbatim_without_revalidation(tmp_path):
    cache = S.DecompCache(tmp_path, "P")
    did = "fixedid"
    # children that would FAIL Gate-2 (singleton) — get must NOT re-validate, just return them
    junk = [{"id": "only", "done_when": []}]
    cache.stage(did, junk)
    assert cache.get(did) == junk
