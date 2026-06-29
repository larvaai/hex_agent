"""Roster lookup — by id/role, precedence, ordering, add/remove lifecycle."""
from dragzero import Agent, Roster


def _agent(id, role):
    return Agent(id, role, llm=None)  # llm is never touched by Roster


def test_by_role_or_id_finds_by_id():
    a = _agent("planner", "thinker")
    r = Roster([a])
    assert r.by_role_or_id("planner") is a


def test_by_role_or_id_finds_by_role_when_no_id_matches():
    a = _agent("a1", "writer")
    r = Roster([a])
    assert r.by_role_or_id("writer") is a


def test_by_role_or_id_unknown_returns_none():
    r = Roster([_agent("a1", "writer")])
    assert r.by_role_or_id("nope") is None


def test_first_returns_first_inserted():
    a, b, c = _agent("a", "x"), _agent("b", "y"), _agent("c", "z")
    r = Roster([a, b, c])
    assert r.first() is a


def test_add_then_get():
    r = Roster()
    a = _agent("a1", "writer")
    r.add(a)
    assert r.get("a1") is a


def test_remove_then_get_is_none():
    a = _agent("a1", "writer")
    r = Roster([a])
    r.remove("a1")
    assert r.get("a1") is None


def test_empty_roster_first_is_none():
    assert Roster().first() is None


def test_empty_roster_all_is_empty_list():
    assert Roster().all() == []


def test_id_takes_precedence_over_role():
    # Agent("dup","x") has id "dup"; Agent("y","dup") has role "dup".
    # Lookup key "dup" must hit the id match, not the role match.
    by_id = _agent("dup", "x")
    by_role = _agent("y", "dup")
    r = Roster([by_id, by_role])
    found = r.by_role_or_id("dup")
    assert found is by_id
    assert found.id == "dup"
