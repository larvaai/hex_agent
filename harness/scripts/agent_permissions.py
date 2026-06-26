#!/usr/bin/env python3
"""
agent_permissions — pure decision logic for agent_type-keyed write RBAC.

Given a role (the subagent `agent_type` from the PreToolUse payload, or `_parent`
for the top-level agent), a write target, and a parsed permission table, decide
whether the write is in-lane. Pure + deterministic; the `agent_rbac_guard` hook
owns the payload/IO, this owns the rule. One home per fact.

Trust note: `agent_type` is a platform-set ATTRIBUTION label (same tier as
resolve_actor), not a credential — this gate disciplines a cooperative fleet on a
trusted host, it is NOT insider-proof. Hostile multi-tenant authz stays on the
separate server-issued-token path.

De-namespace fallback: the runtime `agent_type` is invocation-path-dependent — a
plugin-qualified spawn arrives `hs:developer`, the bare `/hs-flow:team` spawn of the same
agent arrives `developer` (the agent's frontmatter `name:`). The table is keyed by
the BARE agent name; a namespaced role that is not an exact key resolves to its bare
key (`hs:developer` → `developer`) so both spawn paths land in the same lane. An
EXACT key always wins over the fallback.

Additive-skip contract (mirrors ownership_gate): an ABSENT table, or a table that
declares no roles yet, yields no decision (None) — the gate is inert until an
operator declares a permission table, so a fresh install never bricks the fleet.
A PRESENT-but-MALFORMED table raises PermissionsConfigError; the hook turns that
into a fail-closed block (loud, not silently-off), softened to a warn under the
lenient guard policy.
"""
import fnmatch
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# The role label for the top-level agent (its PreToolUse payload carries no
# agent_type). Restricted only by an EXPLICIT `_parent` entry — never blocked just
# because a table exists for subagent roles.
ROLE_PARENT = "_parent"


class PermissionsConfigError(ValueError):
    """A present-but-malformed permission table — fail-closed at the hook."""


def load_permissions(path) -> Optional[Dict[str, Any]]:
    """Parse the permission table. Returns the normalized dict, or None when the
    table is absent / declares no roles (additive-skip). Raises
    PermissionsConfigError on a present-but-malformed table."""
    p = Path(path)
    if not p.is_file():
        return None
    import yaml
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise PermissionsConfigError("agent-permissions.yaml is not valid YAML: %s" % e)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PermissionsConfigError("agent-permissions.yaml must be a mapping")
    roles = raw.get("roles")
    if roles is None:
        return None
    if not isinstance(roles, dict):
        raise PermissionsConfigError("agent-permissions.yaml 'roles' must be a mapping")
    if not roles:
        return None  # declared-but-empty: nothing to enforce yet (additive-skip)
    return {"roles": roles, "default_deny": bool(raw.get("default_deny", True))}


def _matches(target: str, globs: List[str]) -> bool:
    """True when `target` matches any glob — full POSIX path OR basename. fnmatch
    `*` spans `/`, so a lane glob like `plans/**` matches anything under plans/.

    Caveat (enforced only by convention + the load-time lane width): a SLASH-FREE
    glob (e.g. `*.md`) matches by BASENAME, so it spans the whole tree — it is NOT a
    directory lane. Keep lane globs multi-segment for containment; the shipped table
    does (`harness/**`, `plans/**`)."""
    name = os.path.basename(target)
    for g in globs or []:
        if not isinstance(g, str):
            continue
        if fnmatch.fnmatch(target, g) or fnmatch.fnmatch(name, g):
            return True
    return False


def _resolve_lane(role: str, roles: Dict[str, Any]) -> Optional[List[str]]:
    """The role's declared globs, or None when no key matches.

    Lookup order: (1) the role verbatim — an exact key always wins; (2) the
    de-namespaced bare name (`hs:developer` → `developer`) so a plugin-qualified
    runtime role lands in the bare-keyed table. None ⇒ the role is undeclared (the
    caller applies default_deny / _parent rules)."""
    if role in roles:
        return roles[role]
    if ":" in role:
        bare = role.split(":", 1)[1]
        if bare in roles:
            return roles[bare]
    return None


def is_mapped(role: Optional[str], cfg: Optional[Dict[str, Any]]) -> bool:
    """True when `role` resolves to a declared lane (or is the unrestricted
    `_parent`). The drift selfcheck uses this to catch a runtime role the table does
    NOT cover — a present-but-unmapped role is fail-toward-BRICK under default_deny,
    the mirror of the fail-toward-privilege the presence check guards. An inert
    table (None / no roles) maps nothing and blocks nothing → True."""
    if not cfg:
        return True
    roles = cfg.get("roles") or {}
    if not roles:
        return True
    role = role or ROLE_PARENT
    if role == ROLE_PARENT:
        return True
    return _resolve_lane(role, roles) is not None


def decide(role: Optional[str], target: str, cfg: Optional[Dict[str, Any]]) -> Optional[str]:
    """None ⇒ allow (or no table → skip); a string ⇒ block reason.

    Deterministic: same (role, target, cfg) → same result."""
    if not cfg:
        return None
    roles = cfg.get("roles") or {}
    if not roles:
        return None
    target = str(target).replace("\\", "/")
    role = role or ROLE_PARENT
    globs = _resolve_lane(role, roles)
    if globs is None:
        # role not declared in the table (verbatim or de-namespaced)
        if role == ROLE_PARENT:
            return None  # top-level agent unrestricted unless explicitly declared
        if cfg.get("default_deny", True):
            return "role %r has no declared write lane; '%s' denied." % (role, target)
        return None
    if _matches(target, globs):
        return None
    return "role %r may write only %s; '%s' is outside its lane." % (role, globs, target)
