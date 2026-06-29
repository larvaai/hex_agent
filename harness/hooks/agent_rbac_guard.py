#!/usr/bin/env python3
"""agent_rbac_guard.py — PreToolUse(Write|Edit|MultiEdit) compliance gate keyed on agent_type.

Reads the role straight off the PreToolUse payload (`agent_type` / `subagent_type`
for a subagent tool call; absent for the top-level agent → `_parent`) — NOT via
resolve_actor, which collapses parent/sub because session_id is shared. Two clauses:

  1. ISOLATION floor — a subagent (non-_parent role) may only write UNDER its
     cwd/worktree root (resolve-then-contain; a worktree-isolated subagent is thus
     physically confined). The top-level agent is exempt.
  2. IDENTITY lane — within the root, the target must match the role's declared
     write globs in agent-permissions.yaml.

A violation is BLOCKED fail-closed via run_compliance_hook (exit 2 + reason),
softened to a warn under the lenient guard policy (registered _ENFORCE).

ROLE RESOLUTION: a fully ABSENT attribution is the real top-level agent (`_parent`).
A PRESENT-but-empty/blank attribution is instead a DRIFTED subagent (its agent_type
vanished) — it is mapped to a confined `_drifted` sentinel, NOT `_parent`, so an
attribution glitch fails toward containment (default_deny blocks it), never toward
write-everything. A namespaced role (`hs:developer`) is de-namespaced to its bare
table key inside agent_permissions.

HONESTY (mirrors write_guard/fs_guard): `agent_type` is a platform-set ATTRIBUTION
label, not a credential — this disciplines a cooperative fleet on a trusted host, it
is NOT insider-proof and does NOT judge intent (a hijacked-but-in-role write is
byte-identical at the gate). It sees tool Writes, not Bash-spelled writes
(`echo>`, `sed -i`) — those need the worktree boundary + the git-diff floor.
Hostile multi-tenant authz stays on the separate server-issued-token path.

Additive-skip: an absent / roleless table → inert (pass, no isolation either), so a
fresh install never bricks the fleet. A present-but-malformed table fails closed.
"""
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.join(os.path.dirname(_HERE), "scripts"))

import hook_runtime  # noqa: E402
import trace_log     # noqa: E402

HOOK_CLASS = "compliance"
_HOOK = "agent_rbac_guard"
_WRITE_TOOLS = ("Write", "Edit", "MultiEdit")
_DATA = Path(__file__).resolve().parent.parent / "data"

# A present-but-empty/blank attribution resolves to this sentinel — a confined,
# undeclared role (default_deny blocks it), never the unrestricted `_parent`.
_DRIFTED_ROLE = "_drifted"


def _perm_path() -> Path:
    raw = os.environ.get("HARNESS_AGENT_PERMISSIONS_FILE")
    return Path(raw) if raw else (_DATA / "agent-permissions.yaml")


def _resolve_role(data: dict, parent_role: str) -> str:
    """The write's role. A fully ABSENT attribution → the top-level `parent_role`.
    A PRESENT-but-empty/blank/non-string attribution → the confined `_drifted`
    sentinel (an attribution glitch must not read as the unrestricted parent)."""
    for key in ("agent_type", "subagent_type"):
        if key in data:
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            return _DRIFTED_ROLE  # present-but-empty/blank/non-string → drift
    return parent_role


def _contain(target: str, root: str):
    """Repo-relative POSIX path via resolve-then-contain (symlink-safe; NOT a
    string-prefix). A RELATIVE target is resolved against `root` (the payload cwd),
    NOT the hook process cwd — so a worktree subagent's in-tree write is not
    false-flagged. Returns None when `target` escapes `root` — that None is the
    isolation-floor signal."""
    try:
        t = Path(target)
        if not t.is_absolute():
            t = Path(root) / t
        t = t.resolve()
        r = Path(root).resolve()
        return str(t.relative_to(r)).replace("\\", "/")
    except Exception:  # noqa: BLE001
        return None


def _block(data: dict, role: str, reason: str, target: str) -> str:
    session = data.get("session_id")
    trace_log.append_event(
        hook=_HOOK, event="agent_rbac_block", session=session,
        tool=data.get("tool_name"),
        actor=hook_runtime.resolve_actor(session_id=session),
        status="BLOCKED", note="role=%s %s" % (role, reason),
        target=str(target).replace("\\", "/"))
    return reason


def core(data: dict):
    """None ⇒ pass; string ⇒ block reason (run_compliance_hook contract)."""
    import agent_permissions as ap

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    if data.get("tool_name") not in _WRITE_TOOLS:
        return None
    target = tool_input.get("file_path")
    if not isinstance(target, str) or not target:
        return None

    role = _resolve_role(data, ap.ROLE_PARENT)

    try:
        cfg = ap.load_permissions(_perm_path())
    except ap.PermissionsConfigError as e:
        return "agent-permissions table invalid: %s" % e  # fail-closed (loud)
    if not cfg:
        return None  # additive-skip: no table declared yet (gate fully inert)

    root = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    rel = _contain(target, root)

    # clause 1 — isolation floor: a subagent must stay under its cwd/worktree root
    if rel is None:
        if role == ap.ROLE_PARENT:
            return None  # top-level agent is not containment-confined
        return _block(data, role,
                      "isolation: role %r may not write outside its worktree/cwd "
                      "root; '%s' escapes." % (role, str(target).replace("\\", "/")),
                      target)

    # clause 2 — identity lane: target must match the role's declared globs
    reason = ap.decide(role, rel, cfg)
    if reason:
        return _block(data, role, reason, rel)
    return None


def main() -> None:
    raw = hook_runtime.read_stdin_json()
    # A skipped gate must be VISIBLE in the trace (mirror gate_stage/ownership_guard).
    if not hook_runtime.hook_enabled(_HOOK, HOOK_CLASS):
        trace_log.append_event(
            hook=_HOOK, event="agent_rbac_skip", session=raw.get("session_id"),
            note="disabled via %s" % hook_runtime._config_path())
        hook_runtime.emit_continue()
        sys.exit(0)
    import json
    hook_runtime.run_compliance_hook(_HOOK, core, raw=json.dumps(raw))


if __name__ == "__main__":
    main()
