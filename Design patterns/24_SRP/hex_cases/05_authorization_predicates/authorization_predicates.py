"""
SRP case 05 — Permission Escalation Detection (chỉ phục vụ Security-checkpoint team).

Distill TRUNG THỰC từ codebase hex_agent:
  - control/authz.py:1-50
      * CAN_FLAGS (suy ra từ dataclass) -> authz.py:21
      * PERMISSION_EDIT_PERMISSIONS     -> authz.py:26
      * is_permission_escalating (EscalationDetector) -> authz.py:29-40
      * command_needs_human_checkpoint (CommandClassifier) -> authz.py:43-49
  - control/permission.py:21-29  (@dataclass Permission, các cờ can_*)
  - control/command_registry.py:36-57 (CommandTypeRegistry.requires_permission)

Ý NGHĨA SRP:
  Hai predicate THUẦN nằm ngay tim mô hình authorization. Một actor: đội security checkpoint
  (S21.6) — trước khi áp một permission patch, control plane HỎI hai hàm này. Chúng KHÔNG
  sửa state, KHÔNG log, KHÔNG emit. Chỉ trả lời câu hỏi nhị phân yes/no về bảo mật.
  CAN_FLAGS được sinh tự động từ field của Permission: thêm cờ can_* mới -> tự được tính
  (không phải sửa predicate). Đổi luật escalation -> đổi đúng MỘT hàm.

Vai trò pattern:
  - PermissionFieldInspector: CAN_FLAGS = frozenset các field bắt đầu bằng "can_".
  - EscalationDetector       : is_permission_escalating (phát hiện lật False->True).
  - CommandClassifier        : command_needs_human_checkpoint (lệnh có sửa permission không).

Bản distill:
  - Giữ NGUYÊN cả hai predicate y hệt logic gốc.
  - THAY CommandTypeRegistry nặng (đọc YAML) bằng một registry tối thiểu in-memory CHỈ phơi
    requires_permission(command_type), đúng cái mà command_needs_human_checkpoint cần.
  - Chỉ dùng stdlib (dataclasses).
"""
from __future__ import annotations

from dataclasses import dataclass, fields


# ── Stand-in cho control/permission.py:21-29 (chỉ giữ cờ can_* liên quan authz) ──
@dataclass(frozen=True)
class Permission:
    allowed_tools: tuple[str, ...] = ()
    can_write_artifacts: bool = False
    can_call_other_agents: bool = False
    can_execute_shell: bool = False
    can_modify_workflow: bool = False
    can_modify_permissions: bool = False
    effective_from: str = "next_checkpoint"


# ── PermissionFieldInspector ──
# Suy ra từ dataclass: thêm cờ can_* mới được tự động phủ (allowed_tools bị loại — đúng như gốc).
CAN_FLAGS = frozenset(f.name for f in fields(Permission) if f.name.startswith("can_"))

# Tên permission ám chỉ lệnh chỉnh-sửa-permission. Giữ một cái = có thể viết lại capability,
# nên áp dụng nó LUÔN cần một human RuntimeCheckpoint, kể cả dưới trust-O.
PERMISSION_EDIT_PERMISSIONS = frozenset({"workflow.modify_permissions"})


# ── Stand-in tối thiểu cho control/command_registry.py: chỉ phơi requires_permission ──
class CommandTypeRegistry:
    def __init__(self, requires: dict[str, str | None]) -> None:
        self._requires = dict(requires)

    def requires_permission(self, command_type: str) -> str | None:
        if command_type not in self._requires:
            raise KeyError(f"Unknown command_type: {command_type!r}")
        return self._requires[command_type]


# ── EscalationDetector ──
def is_permission_escalating(current: Permission, patch: dict) -> bool:
    """True nếu ``patch`` lật BẤT KỲ cờ boolean nào False->True trên ``current``.

    Hạ quyền và cấp-lại-no-op KHÔNG phải escalation. KNOWN GAP (giống gốc): chỉ soi cờ
    boolean can_* — nới allowed_tools nằm ngoài phạm vi hàm này.
    """
    return any(
        key in CAN_FLAGS and bool(value) and not getattr(current, key)
        for key, value in patch.items()
    )


# ── CommandClassifier ──
def command_needs_human_checkpoint(command_type: str, registry: CommandTypeRegistry) -> bool:
    """True nếu ``command_type`` chỉnh permission nên BẮT BUỘC dừng cho human duyệt.

    Quyết từ requires_permission của registry, KHÔNG từ lời tự khai của issuer.
    """
    return registry.requires_permission(command_type) in PERMISSION_EDIT_PERMISSIONS


# ============================================================================
# DEMO
# ============================================================================

def demo() -> None:
    print("=" * 72)
    print("SRP case 05 — Permission Escalation Detection (control/authz.py)")
    print("Actor DUY NHẤT: đội security checkpoint. Chỉ trả lời yes/no, không đổi state.")
    print("=" * 72)

    print(f"\n(0) CAN_FLAGS tự suy từ dataclass Permission: {sorted(CAN_FLAGS)}")
    assert "can_execute_shell" in CAN_FLAGS
    assert "allowed_tools" not in CAN_FLAGS, "allowed_tools KHÔNG phải cờ can_*"

    base = Permission()  # tất cả can_* = False
    print(f"\n(1) Permission gốc: mọi cờ can_* = False")

    # (2) patch lật False->True -> escalation.
    up = {"can_execute_shell": True}
    assert is_permission_escalating(base, up) is True
    print(f"    patch={up} -> escalating? {is_permission_escalating(base, up)} (đúng: True)")

    # (3) patch hạ True->False -> KHÔNG escalation.
    granted = Permission(can_execute_shell=True)
    down = {"can_execute_shell": False}
    assert is_permission_escalating(granted, down) is False
    print(f"    đã cấp shell, patch={down} -> escalating? "
          f"{is_permission_escalating(granted, down)} (đúng: False, đây là hạ quyền)")

    # (4) cấp-lại no-op (đã True, patch lại True) -> KHÔNG escalation.
    noop = {"can_execute_shell": True}
    assert is_permission_escalating(granted, noop) is False
    print(f"    đã có shell, patch lại True -> escalating? "
          f"{is_permission_escalating(granted, noop)} (đúng: False, no-op)")

    # (5) cờ không-phải-can_* (allowed_tools) -> không bị tính là escalation bởi hàm này.
    tools_patch = {"allowed_tools": ("fs_write",)}
    assert is_permission_escalating(base, tools_patch) is False
    print(f"    patch allowed_tools -> escalating? "
          f"{is_permission_escalating(base, tools_patch)} (đúng: False, ngoài phạm vi predicate)")

    # (6) CommandClassifier: lệnh sửa permission luôn cần human checkpoint.
    registry = CommandTypeRegistry({
        "workflow.update_permission": "workflow.modify_permissions",  # sửa permission
        "workflow.send_message": None,                                # vô hại
        "workflow.read_file": "workflow.read",                        # không phải sửa-permission
    })
    assert command_needs_human_checkpoint("workflow.update_permission", registry) is True
    assert command_needs_human_checkpoint("workflow.send_message", registry) is False
    assert command_needs_human_checkpoint("workflow.read_file", registry) is False
    print("\n(6) command_needs_human_checkpoint:")
    print("    workflow.update_permission -> True  (chỉnh permission, phải human-gate)")
    print("    workflow.send_message      -> False")
    print("    workflow.read_file         -> False (yêu cầu permission khác, không phải sửa-permission)")

    # (7) BẤT BIẾN ghép cặp: một patch escalating cờ can_modify_permissions vừa escalating,
    #     vừa thường đi cùng một lệnh phải human-gate.
    esc = is_permission_escalating(base, {"can_modify_permissions": True})
    gate = command_needs_human_checkpoint("workflow.update_permission", registry)
    assert esc and gate
    print("\n(7) [BẤT BIẾN] cấp can_modify_permissions = escalating VÀ lệnh đó human-gated. PASS")

    # ---- ĐỐI CHỨNG: nếu nhét logic authz vào ngay chỗ apply patch (trộn với mutation) ----
    print("\n--- ĐỐI CHỨNG: nếu trộn predicate authz vào hàm apply_patch (vừa check vừa sửa) ---")
    print("  * Test 'phát hiện escalation' phải dựng cả đường ghi state -> nặng, dễ vỡ.")
    print("  * Hàm apply vừa quyết định vừa mutate -> khó audit, dễ bỏ sót checkpoint.")
    print("  Tách predicate thuần: test chỉ cần Permission + dict; đổi luật chỉ đụng 1 hàm.")

    print("\nKẾT: predicate thuần, không I/O, không phụ thuộc Kernel/Session/Event. Thêm cờ")
    print("can_* mới -> CAN_FLAGS tự gồm; đổi luật escalation -> sửa đúng một hàm.")


if __name__ == "__main__":
    demo()
