"""StateStore snapshot/restore round-trip (basis for resume). Epic E07."""
from core.state import StateStore


def test_snapshot_restore_roundtrip():
    s = StateStore()
    s.set("a", 1)
    s.set("b", [1, 2, 3])
    snap = s.snapshot()
    s.set("a", 99)
    s.set("c", "x")
    s.restore(snap)
    assert s.get("a") == 1
    assert s.get("b") == [1, 2, 3]
    assert s.get("c") is None  # restore replaces wholesale


def test_snapshot_not_affected_by_later_set():
    s = StateStore()
    s.set("a", 1)
    snap = s.snapshot()
    s.set("a", 2)
    assert snap["a"] == 1
