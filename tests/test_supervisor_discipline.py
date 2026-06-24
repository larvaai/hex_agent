"""E10 S10.12 — discipline carried into worker turns.

The finish-gate is the SAME shared module worker turns run through (E05 finish_node
-> check_finish). Repair-mode adds a patch-only policy: a whole-file rewrite after a
failed validation is refused with policy_code=repair_requires_patch_tool.
"""
from __future__ import annotations

from core.bootstrap import build_kernel
from discipline import check_finish
from safety.policy import SafeToolPort, ToolPolicy
from toolbox.filesystem import FsWrite


# ── finish-gate (carried over) ───────────────────────────────────────────────
def test_finish_gate_blocks_unvalidated_change():
    gate = check_finish({"code_changed": True, "validation_passed": False})
    assert gate["allowed"] is False


def test_finish_gate_allows_blocker_handoff():
    gate = check_finish({"code_changed": True, "validation_passed": False}, finish_reason="blocker")
    assert gate["allowed"] is True


def test_finish_gate_allows_validated_change():
    gate = check_finish({"code_changed": True, "validation_passed": True})
    assert gate["allowed"] is True


# ── repair-mode patch-only policy (new) ──────────────────────────────────────
def test_repair_mode_blocks_whole_file_write():
    decision = ToolPolicy(repair_mode=True).check("fs_write", {"path": "a.py", "content": "x"})
    assert decision.allowed is False
    assert decision.code == "repair_requires_patch_tool"


def test_repair_mode_allows_read():
    assert ToolPolicy(repair_mode=True).check("fs_read", {"path": "a.py"}).allowed is True


def test_normal_mode_allows_write():
    assert ToolPolicy(repair_mode=False).check("fs_write", {"path": "a.py", "content": "x"}).allowed is True


def test_repair_policy_blocks_at_tool_chokepoint():
    # the same path a worker turn's fs_write traverses (SafeToolPort -> execute_tool)
    kernel = build_kernel({})
    kernel.registry.register_tool(
        "fs_write", SafeToolPort("fs_write", FsWrite(), ToolPolicy(repair_mode=True))
    )
    env = kernel.execute_tool("fs_write", {"path": "a.py", "content": "x"})
    assert env["ok"] is False
    assert env["data"]["policy_code"] == "repair_requires_patch_tool"
