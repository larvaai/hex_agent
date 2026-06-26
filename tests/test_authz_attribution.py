"""Phase 01 — authz≠attribution boundary. Pins the two control-plane authz predicates.

Doctrine: docs/explanation/authz-vs-attribution.md. issued_by/Actor = attribution (self-asserted,
audit); the authz decision is requires_permission resolved at a checkpoint. Permission-edit must
need a human RuntimeCheckpoint even under trust-O — these tests pin the predicates that a future
command_bridge MUST call before applying UpdateAgentPermission.
"""
from __future__ import annotations

from control.authz import command_needs_human_checkpoint, is_permission_escalating
from control.command_registry import load_command_registry
from control.permission import Permission


def test_escalating_when_flag_flips_false_to_true():
    assert is_permission_escalating(Permission(), {"can_modify_permissions": True}) is True


def test_not_escalating_on_downgrade():
    cur = Permission(can_execute_shell=True)
    assert is_permission_escalating(cur, {"can_execute_shell": False}) is False


def test_not_escalating_when_flag_already_held():
    cur = Permission(can_modify_permissions=True)
    assert is_permission_escalating(cur, {"can_modify_permissions": True}) is False


def test_allowed_tools_expansion_is_out_of_predicate_scope():
    # Known gap (doc): boolean can_* only. allowed_tools growth is gated by §1.4
    # (SessionFactory.create_child scope ⊆ parent), NOT by this predicate.
    cur = Permission(allowed_tools=("a",))
    assert is_permission_escalating(cur, {"allowed_tools": ("a", "b")}) is False


def test_command_needs_human_checkpoint_for_permission_edit():
    reg = load_command_registry()
    assert command_needs_human_checkpoint("UpdateAgentPermission", reg) is True


def test_command_does_not_need_human_checkpoint_for_plain_control():
    reg = load_command_registry()
    assert command_needs_human_checkpoint("PauseWorkflow", reg) is False


def test_contract_update_permission_requires_modify_permissions():
    reg = load_command_registry()
    assert reg.requires_permission("UpdateAgentPermission") == "workflow.modify_permissions"
