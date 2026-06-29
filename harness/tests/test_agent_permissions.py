"""Tests for agent_permissions — the pure decision logic behind agent_rbac_guard.

The detector answers: given a role (agent_type, or '_parent' for the top-level
agent), a write target, and a parsed permission table, is the write in-lane?

Additive-skip contract (mirrors ownership_gate): an absent or roleless table
yields None (no decision) so a fresh install never bricks the fleet — the gate is
inert until an operator declares a permission table.
"""
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import agent_permissions as ap  # noqa: E402


# ---------------------------------------------------------------------------
# additive-skip: no table => no decision (inert by default)
# ---------------------------------------------------------------------------

def test_none_config_skips():
    assert ap.decide("general-purpose", "harness/x.py", None) is None


def test_empty_roles_skips():
    assert ap.decide("general-purpose", "harness/x.py", {"roles": {}}) is None


# ---------------------------------------------------------------------------
# in-lane / out-of-lane
# ---------------------------------------------------------------------------

def _cfg(**roles):
    d = {"roles": roles}
    return d


def test_in_lane_allowed():
    cfg = _cfg(**{"general-purpose": ["plans/**", "docs/**"]})
    assert ap.decide("general-purpose", "plans/p/notes.md", cfg) is None


def test_out_of_lane_blocked():
    cfg = _cfg(**{"general-purpose": ["plans/**"]})
    reason = ap.decide("general-purpose", "harness/hooks/x.py", cfg)
    assert reason and "outside" in reason.lower()
    assert "general-purpose" in reason


def test_basename_glob_matches():
    cfg = _cfg(**{"cook": ["*.md"]})
    assert ap.decide("cook", "deep/nested/readme.md", cfg) is None


# ---------------------------------------------------------------------------
# undeclared role: default_deny governs
# ---------------------------------------------------------------------------

def test_undeclared_role_default_deny_blocks():
    cfg = {"roles": {"cook": ["harness/**"]}, "default_deny": True}
    reason = ap.decide("scout", "harness/x.py", cfg)
    assert reason and "scout" in reason


def test_undeclared_role_default_allow_skips():
    cfg = {"roles": {"cook": ["harness/**"]}, "default_deny": False}
    assert ap.decide("scout", "harness/x.py", cfg) is None


def test_default_deny_defaults_true_when_absent():
    # a table that declares roles but omits default_deny denies undeclared roles
    cfg = {"roles": {"cook": ["harness/**"]}}
    assert ap.decide("scout", "harness/x.py", cfg) is not None


# ---------------------------------------------------------------------------
# parent role
# ---------------------------------------------------------------------------

def test_parent_unrestricted_when_undeclared():
    # the top-level agent (_parent) must never be blocked just because a table
    # exists for subagent roles — only an EXPLICIT _parent entry restricts it
    cfg = {"roles": {"cook": ["harness/**"]}, "default_deny": True}
    assert ap.decide(ap.ROLE_PARENT, "anything/at/all.txt", cfg) is None


def test_parent_restricted_when_explicitly_declared():
    cfg = {"roles": {"_parent": ["plans/**"]}, "default_deny": True}
    assert ap.decide(ap.ROLE_PARENT, "plans/ok.md", cfg) is None
    assert ap.decide(ap.ROLE_PARENT, "harness/x.py", cfg) is not None


# ---------------------------------------------------------------------------
# load_permissions
# ---------------------------------------------------------------------------

def test_load_absent_file_is_none(tmp_path):
    assert ap.load_permissions(tmp_path / "nope.yaml") is None


def test_load_empty_roles_is_none(tmp_path):
    p = tmp_path / "perm.yaml"
    p.write_text("roles: {}\n", encoding="utf-8")
    assert ap.load_permissions(p) is None


def test_load_valid_table(tmp_path):
    p = tmp_path / "perm.yaml"
    p.write_text("default_deny: true\nroles:\n  cook: ['harness/**']\n", encoding="utf-8")
    cfg = ap.load_permissions(p)
    assert cfg["roles"]["cook"] == ["harness/**"]
    assert cfg["default_deny"] is True


def test_load_malformed_raises(tmp_path):
    # present-but-broken table → fail-closed (raise), NOT silently inert
    p = tmp_path / "perm.yaml"
    p.write_text("roles: [not, a, mapping]\n", encoding="utf-8")
    import pytest
    with pytest.raises(ap.PermissionsConfigError):
        ap.load_permissions(p)


# ---------------------------------------------------------------------------
# shipped table — pins the ratified RBAC lanes (not the synthetic cfgs above).
# Guards against a typo'd glob / dropped _parent / accidental re-inerting of the
# real agent-permissions.yaml the gate enforces.
# ---------------------------------------------------------------------------

_SHIPPED = Path(__file__).resolve().parent.parent / "data" / "agent-permissions.yaml"


def _shipped_cfg():
    cfg = ap.load_permissions(_SHIPPED)
    assert cfg is not None, "shipped agent-permissions.yaml is inert (roles empty) — RBAC not enabled"
    return cfg


def test_shipped_table_is_active_and_deny_by_default():
    cfg = _shipped_cfg()
    assert cfg["default_deny"] is True


def test_shipped_parent_unrestricted():
    cfg = _shipped_cfg()
    assert ap.decide(ap.ROLE_PARENT, "harness/hooks/anything.py", cfg) is None


def test_shipped_reviewer_in_lane_allowed():
    cfg = _shipped_cfg()
    assert ap.decide("hs:code-reviewer", "plans/p/review-decision.json", cfg) is None


def test_shipped_reviewer_out_of_lane_blocked():
    # a read-only reviewer must not write into the product tree
    cfg = _shipped_cfg()
    assert ap.decide("hs:code-reviewer", "harness/hooks/x.py", cfg) is not None


def test_shipped_developer_in_lane_allowed():
    cfg = _shipped_cfg()
    assert ap.decide("hs:developer", "harness/scripts/x.py", cfg) is None


def test_shipped_developer_out_of_lane_blocked():
    cfg = _shipped_cfg()
    assert ap.decide("hs:developer", "plans/p/notes.md", cfg) is not None


def test_shipped_git_manager_writes_nothing():
    cfg = _shipped_cfg()
    assert ap.decide("hs:git-manager", "harness/x.py", cfg) is not None


def test_shipped_unknown_role_denied():
    cfg = _shipped_cfg()
    assert ap.decide("some-unlisted-agent", "harness/x.py", cfg) is not None


# ---------------------------------------------------------------------------
# de-namespace fallback — the runtime agent_type is invocation-path-dependent:
# the plugin-qualified spawn arrives 'hs:developer', the bare /hs-flow:team spawn
# arrives 'developer'. The table is keyed by the bare agent name; a namespaced
# role resolves to its bare key so BOTH spawn paths land in the same lane.
# ---------------------------------------------------------------------------

def test_namespaced_role_resolves_to_bare_key():
    cfg = {"roles": {"developer": ["harness/**"]}, "default_deny": True}
    assert ap.decide("hs:developer", "harness/scripts/x.py", cfg) is None
    assert ap.decide("developer", "harness/scripts/x.py", cfg) is None


def test_namespaced_role_out_of_lane_still_blocked():
    cfg = {"roles": {"developer": ["harness/**"]}, "default_deny": True}
    assert ap.decide("hs:developer", "plans/x.md", cfg) is not None


def test_exact_key_takes_precedence_over_bare_fallback():
    cfg = {"roles": {"hs:developer": ["plans/**"], "developer": ["harness/**"]},
           "default_deny": True}
    assert ap.decide("hs:developer", "plans/x.md", cfg) is None
    assert ap.decide("hs:developer", "harness/x.py", cfg) is not None


def test_is_mapped_resolves_both_forms():
    cfg = {"roles": {"developer": ["harness/**"], "git-manager": []},
           "default_deny": True}
    assert ap.is_mapped("developer", cfg) is True
    assert ap.is_mapped("hs:developer", cfg) is True       # via de-namespace fallback
    assert ap.is_mapped("git-manager", cfg) is True        # declared empty lane is mapped
    assert ap.is_mapped("ghost-agent", cfg) is False       # would be default-denied
    assert ap.is_mapped(ap.ROLE_PARENT, cfg) is True       # top-level always mapped


def test_shipped_table_covers_bare_team_spawn_names():
    # the /hs-flow:team workflow spawns BARE subagent_type names — they must be in-lane
    cfg = _shipped_cfg()
    assert ap.decide("developer", "harness/scripts/x.py", cfg) is None
    assert ap.decide("tester", "harness/tests/test_x.py", cfg) is None
    assert ap.decide("code-reviewer", "plans/p/review.json", cfg) is None
    assert ap.decide("researcher", "plans/p/r.md", cfg) is None
    # and the plugin-qualified form resolves to the same lane
    assert ap.decide("hs:developer", "harness/scripts/x.py", cfg) is None
