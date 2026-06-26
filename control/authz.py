"""Authz predicates — attribution≠authz boundary for the control plane. Epic E21.

Doctrine: ``docs/explanation/authz-vs-attribution.md``. ``issued_by``/``Actor`` only *record*
who acted (self-asserted, audit) — they are NOT proof of authority. The authz decision is
``requires_permission`` resolved against the *holder's* ``Permission`` at a checkpoint boundary.

These are pure predicates with no dependency on an enforcement path. The enforcement call-site
does not exist yet (``command_bridge`` is absent on this branch — DEC-7); when it lands it MUST
call these before applying a permission-editing command. Until then they pin the invariant:
permission escalation is detectable, and permission-edit is human-gated even under trust-O.
"""
from __future__ import annotations

from dataclasses import fields

from control.command_registry import CommandTypeRegistry
from control.permission import Permission

# Boolean capability flags on Permission. Derived from the dataclass so a new can_* flag is
# covered automatically (allowed_tools is excluded — see KNOWN GAP below).
CAN_FLAGS = frozenset(f.name for f in fields(Permission) if f.name.startswith("can_"))

# requires_permission values that name a permission-editing command. Holding one means the
# issuer could rewrite capability — so applying it always needs a human RuntimeCheckpoint,
# even under trust-O (an O-issued command otherwise bypasses requires_permission).
PERMISSION_EDIT_PERMISSIONS = frozenset({"workflow.modify_permissions"})


def is_permission_escalating(current: Permission, patch: dict) -> bool:
    """True if ``patch`` flips any boolean capability flag False→True on ``current``.

    Downgrades and no-op re-grants are not escalation. KNOWN GAP: only boolean ``can_*`` flags
    are inspected — widening ``allowed_tools`` is out of scope here; that path is constrained by
    §1.4 (``SessionFactory.create_child`` forces child scope ⊆ parent). Do not read this as
    "full authz".
    """
    return any(
        key in CAN_FLAGS and bool(value) and not getattr(current, key)
        for key, value in patch.items()
    )


def command_needs_human_checkpoint(command_type: str, registry: CommandTypeRegistry) -> bool:
    """True if ``command_type`` edits permissions and therefore must pause for a human.

    Resolved from the command-type registry's ``requires_permission``, not from any issuer
    claim. Unknown command types raise (registry contract) — callers pass declared types.
    """
    return registry.requires_permission(command_type) in PERMISSION_EDIT_PERMISSIONS
