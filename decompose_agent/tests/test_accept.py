"""Gate-2 — accept_decomposition: a PURE structural gate run BEFORE any tree mutation.
μ = done_when_count, strict shrink (DEC-D1); coverage by implication, not artifact-name (F5)."""
from __future__ import annotations

import pytest

from decompose_agent.accept import MAX_FANOUT, Accept, Reject, accept_decomposition, mu
from decompose_agent.node import Node


def parent(done_when=None, depends_on=()):
    dw = done_when or [
        {"check": "json_field_in_range", "params": {"ptr": "/m", "min": 0.8, "max": 1.0}, "artifact": "recall.json"},
        {"check": "file_exists", "artifact": "log.txt"},
    ]
    return Node.from_dict({"id": "P", "kind": "work", "status": "active",
                           "depends_on": list(depends_on), "done_when": dw})


COVERING = [
    {"id": "P.c0", "done_when": [{"check": "json_field_in_range", "params": {"ptr": "/m", "min": 0.9, "max": 1.0}, "artifact": "a.json"}]},
    {"id": "P.c1", "done_when": [{"check": "file_exists", "artifact": "b.txt"}]},
]


def test_mu_is_done_when_count():
    assert mu(parent()) == 2


def test_accept_clean_returns_topo_children():
    v = accept_decomposition(parent(), [dict(c) for c in COVERING])
    assert isinstance(v, Accept) and v.ok
    assert {c["id"] for c in v.children} == {"P.c0", "P.c1"}


def test_reject_singleton():
    v = accept_decomposition(parent(), [dict(COVERING[0])])
    assert isinstance(v, Reject) and "SINGLETON" in v.reason


def test_reject_fanout():
    kids = [{"id": f"P.c{i}", "done_when": [{"check": "file_exists", "artifact": f"f{i}.txt"}]} for i in range(MAX_FANOUT + 1)]
    assert "FANOUT" in accept_decomposition(parent(), kids).reason


def test_reject_child_equals_parent():
    kids = [{"id": "P", "done_when": [{"check": "file_exists", "artifact": "a.txt"}]},
            {"id": "P.c1", "done_when": [{"check": "file_exists", "artifact": "b.txt"}]}]
    assert not accept_decomposition(parent(), kids).ok


def test_reject_dup_id():
    kids = [{"id": "P.x", "done_when": [{"check": "file_exists", "artifact": "a.txt"}]},
            {"id": "P.x", "done_when": [{"check": "file_exists", "artifact": "b.txt"}]}]
    assert "dup id" in accept_decomposition(parent(), kids).reason.lower()


def test_reject_not_smaller_mu():
    # child dwc == parent dwc (2) → μ did not strictly shrink (D2 / DEC-D1)
    big = [{"id": "P.c0", "done_when": [
        {"check": "file_exists", "artifact": "a.txt"},
        {"check": "file_exists", "artifact": "a2.txt"}]},
        {"id": "P.c1", "done_when": [{"check": "file_exists", "artifact": "b.txt"}]}]
    assert "NOT_SMALLER" in accept_decomposition(parent(), big).reason


def test_reject_empty_done_when_prose_child():
    kids = [{"id": "P.c0", "done_when": []},
            {"id": "P.c1", "done_when": [{"check": "file_exists", "artifact": "b.txt"}]}]
    assert "PROSE_CHILD" in accept_decomposition(parent(), kids).reason


def test_reject_unknown_check():
    kids = [{"id": "P.c0", "done_when": [{"check": "bogus", "artifact": "a.txt"}]},
            {"id": "P.c1", "done_when": [{"check": "file_exists", "artifact": "b.txt"}]}]
    assert "unknown check" in accept_decomposition(parent(), kids).reason.lower()


@pytest.mark.parametrize("crit", [
    {"check": "file_exists"},                                   # missing artifact
    {"check": "file_exists", "artifact": "../escape.txt"},      # unsafe artifact
    {"check": "file_exists", "artifact": "a.txt", "passed": True},  # verdict field
])
def test_reject_bad_criterion(crit):
    kids = [{"id": "P.c0", "done_when": [crit]},
            {"id": "P.c1", "done_when": [{"check": "file_exists", "artifact": "b.txt"}]}]
    assert not accept_decomposition(parent(), kids).ok


def test_reject_self_dependency():
    kids = [{"id": "P.c0", "depends_on": ["P.c0"], "done_when": [{"check": "file_exists", "artifact": "a.txt"}]},
            {"id": "P.c1", "done_when": [{"check": "file_exists", "artifact": "b.txt"}]}]
    assert "self-dep" in accept_decomposition(parent(), kids).reason.lower()


def test_reject_unknown_dependency():
    kids = [{"id": "P.c0", "depends_on": ["ghost"], "done_when": [{"check": "file_exists", "artifact": "a.txt"}]},
            {"id": "P.c1", "done_when": [{"check": "file_exists", "artifact": "b.txt"}]}]
    assert "ghost" in accept_decomposition(parent(), kids).reason


def test_reject_dependency_cycle():
    kids = [{"id": "P.c0", "depends_on": ["P.c1"], "done_when": [{"check": "file_exists", "artifact": "a.txt"}]},
            {"id": "P.c1", "depends_on": ["P.c0"], "done_when": [{"check": "file_exists", "artifact": "b.txt"}]}]
    assert not accept_decomposition(parent(), kids).ok


def test_reject_undercover():
    # neither child implies the parent's /m metric → UNDERCOVER (F5: by implication, not name)
    kids = [{"id": "P.c0", "done_when": [{"check": "file_exists", "artifact": "a.txt"}]},
            {"id": "P.c1", "done_when": [{"check": "file_exists", "artifact": "b.txt"}]}]
    assert "UNDERCOVER" in accept_decomposition(parent(), kids).reason


def test_coverage_is_by_implication_not_artifact_name():
    # child covers the /m metric with a DIFFERENT artifact name + a tighter range — must accept (F5)
    p = parent(done_when=[{"check": "json_field_in_range", "params": {"ptr": "/m", "min": 0.8, "max": 1.0}, "artifact": "recall.json"},
                          {"check": "row_count_gte", "params": {"n": 10}, "artifact": "rows.jsonl"}])
    kids = [{"id": "P.c0", "done_when": [{"check": "json_field_in_range", "params": {"ptr": "/m", "min": 0.95, "max": 1.0}, "artifact": "RENAMED.json"}]},
            {"id": "P.c1", "done_when": [{"check": "row_count_gte", "params": {"n": 20}, "artifact": "more.jsonl"}]}]
    assert accept_decomposition(p, kids).ok


# ── termination proof as a property: every ACCEPTED decomposition strictly shrinks μ ──

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    _crit = st.fixed_dictionaries({
        "check": st.just("file_exists"),
        "artifact": st.from_regex(r"[a-z]{1,6}\.txt", fullmatch=True),
    })
    _child = st.builds(
        lambda i, dw: {"id": f"P.k{i}", "done_when": dw},
        st.integers(0, 20),
        st.lists(_crit, min_size=0, max_size=5),
    )

    @settings(max_examples=200, deadline=None, derandomize=True)
    @given(st.lists(_child, min_size=0, max_size=10))
    def test_property_accepted_decomposition_strictly_shrinks_mu(children):
        # dedup ids so we exercise the μ rule, not the dup-id rule
        seen, uniq = set(), []
        for c in children:
            if c["id"] not in seen:
                seen.add(c["id"])
                uniq.append(c)
        p = parent(done_when=[{"check": "file_exists", "artifact": "x.txt"},
                              {"check": "file_exists", "artifact": "y.txt"},
                              {"check": "file_exists", "artifact": "z.txt"}])  # dwc=3
        v = accept_decomposition(p, uniq)
        if v.ok:
            assert all(len(c["done_when"]) < mu(p) for c in v.children)
except ImportError:  # pragma: no cover
    pass
