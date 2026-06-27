"""
Case 05 — AgentRegistry.role_view (Factory Method dạng projection/adapter).

DISTILL TRUNG THỰC TỪ MÃ THẬT:
  - roles/registry.py:69-76   (role_view(name) -> RoleView: chiếu RoleSpec thành RoleView)
  - roles/registry.py:78-79   (list_roles: trả tuple[RoleView] cho orchestrator E10)
  - roles/spec.py:31-39       (RoleView — projection slim mà orchestrator đọc)
  - roles/spec.py:41-63       (RoleSpec — domain object đầy đủ + allowed_tools)

Đây là một BIẾN THỂ của Factory Method: factory không tạo subclass mới, mà tạo
một ADAPTER/VIEW từ domain object sẵn có. role_view nhận tên role, lấy RoleSpec
(đầy đủ), rồi dựng RoleView (chiếu lại đúng các trường orchestrator E10 cần:
agent_id, role, system_prompt, default_scope). Client (orchestrator graph) chỉ
chạm RoleView, KHÔNG bao giờ chạm RoleSpec nội bộ.

Điểm dạy học: Factory Method không chỉ để "chọn subclass". Nó đóng gói "cách
dựng đúng object cho một ngữ cảnh" — ở đây là phép chiếu/biến đổi.

Bản distill dùng stdlib. Lược bỏ: parse YAML, Lens/Skill thật. Giữ nguyên vai
trò: Creator (registry) + factory method (role_view) + product (RoleView) +
phép chiếu từ RoleSpec.
"""
from __future__ import annotations

from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
# Domain object đầy đủ — distill từ RoleSpec (roles/spec.py:41-63)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RoleSpec:
    """Đối tượng nghiệp vụ ĐẦY ĐỦ: nhiều trường nội bộ orchestrator không cần."""

    name: str
    role: str
    department: str
    system_prompt: str
    explicit_tools: tuple[str, ...] = ()
    allowed_skills: tuple[str, ...] = ()
    may_route_to: tuple[str, ...] = ()
    lenses: tuple[str, ...] = ()
    secret_internal_note: str = "chỉ dùng nội bộ — KHÔNG được lộ ra orchestrator"

    def derive_scope(self, core_tools: frozenset[str]) -> frozenset[str]:
        """Distill rút gọn của RoleSpec.allowed_tools: union explicit + core."""
        return frozenset(set(self.explicit_tools) | set(core_tools))


# ─────────────────────────────────────────────────────────────────────────────
# Product: projection slim — distill từ RoleView (roles/spec.py:31-39)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RoleView:
    """View slim mà orchestrator E10 đọc — CHỈ các trường cần cho điều phối."""

    agent_id: str
    role: str
    system_prompt: str
    default_scope: frozenset[str]


# ─────────────────────────────────────────────────────────────────────────────
# Creator (factory) — distill từ AgentRegistry.role_view (roles/registry.py:69-79)
# ─────────────────────────────────────────────────────────────────────────────
class AgentRegistry:
    def __init__(self, *, core_tools: frozenset[str] = frozenset()) -> None:
        self._core_tools = frozenset(core_tools)
        self._roles: dict[str, RoleSpec] = {}

    def register(self, spec: RoleSpec) -> RoleSpec:
        if spec.name in self._roles:
            raise ValueError(f"Role '{spec.name}' is already registered; names must be unique.")
        self._roles[spec.name] = spec
        return spec

    def get(self, name: str) -> RoleSpec:
        try:
            return self._roles[name]
        except KeyError:
            known = ", ".join(sorted(self._roles)) or "(none)"
            raise KeyError(f"Unknown role '{name}'. Known roles: {known}") from None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._roles))

    # ── Factory method (projection): role_view (roles/registry.py:69-76) ──────
    def role_view(self, name: str) -> RoleView:
        """Chiếu RoleSpec -> RoleView cho orchestrator. Đóng gói 'dựng object đúng
        hình dạng cho ngữ cảnh điều phối', ẩn các trường nội bộ của RoleSpec."""
        spec = self.get(name)
        return RoleView(
            agent_id=spec.name,
            role=spec.role,
            system_prompt=spec.system_prompt,
            default_scope=spec.derive_scope(self._core_tools),
        )

    # ── list_roles (roles/registry.py:78-79) ─────────────────────────────────
    def list_roles(self) -> tuple[RoleView, ...]:
        return tuple(self.role_view(name) for name in self.names())


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG: client tự bóc RoleSpec (rò rỉ chi tiết nội bộ)
# ─────────────────────────────────────────────────────────────────────────────
def orchestrate_the_bad_way(registry: AgentRegistry, name: str) -> dict:
    """Anti-pattern: orchestrator chạm thẳng RoleSpec và tự bóc field.

    Hậu quả: (1) orchestrator phụ thuộc TOÀN BỘ shape RoleSpec — đổi RoleSpec là
    vỡ orchestrator; (2) có thể vô tình đọc/lộ field nội bộ (secret_internal_note);
    (3) logic 'derive_scope' bị lặp ở mỗi nơi cần view.
    """
    spec = registry.get(name)  # chạm thẳng domain object
    return {
        "agent_id": spec.name,
        "role": spec.role,
        "system_prompt": spec.system_prompt,
        # quên derive_scope đúng cách, và lỡ tay lôi cả field nội bộ:
        "leaked": spec.secret_internal_note,
    }


def demo() -> None:
    print("=" * 72)
    print("CASE 05 — AgentRegistry.role_view (Factory Method dạng projection)")
    print("Nguồn thật: roles/registry.py:69-79 ; roles/spec.py:31-39")
    print("=" * 72)

    registry = AgentRegistry(core_tools=frozenset({"think"}))
    registry.register(RoleSpec(
        name="code", role="Coder", department="eng", system_prompt="Bạn viết code.",
        explicit_tools=("fs_read", "fs_write"), allowed_skills=("file_edit",),
        may_route_to=("test", "reviewer"), lenses=("correctness",),
    ))
    registry.register(RoleSpec(
        name="test", role="Tester", department="eng", system_prompt="Bạn chạy test.",
        explicit_tools=("terminal_run",),
    ))

    print("\n[1] Client (orchestrator) gọi role_view('code') -> nhận RoleView slim.")
    view = registry.role_view("code")
    print(f"    {view}")
    assert isinstance(view, RoleView)
    assert view.agent_id == "code"
    assert view.default_scope == frozenset({"fs_read", "fs_write", "think"})  # explicit + core

    print("\n[2] Encapsulation: RoleView KHÔNG mang field nội bộ của RoleSpec.")
    assert not hasattr(view, "secret_internal_note")
    assert not hasattr(view, "department")
    assert not hasattr(view, "may_route_to")
    print("    RoleView chỉ có 4 trường điều phối; secret_internal_note bị ẩn khỏi client.")

    print("\n[3] list_roles: dựng view cho mọi role (roles/registry.py:78-79).")
    views = registry.list_roles()
    print(f"    {[v.agent_id for v in views]}")
    assert tuple(v.agent_id for v in views) == ("code", "test")  # sort theo tên
    assert all(isinstance(v, RoleView) for v in views)

    print("\n[4] Decoupling: đổi nội bộ RoleSpec không phá client nếu vẫn đi qua role_view.")
    print("    Client chỉ phụ thuộc 4 trường RoleView, không phụ thuộc shape RoleSpec.")

    print("\n[5] ĐỐI CHỨNG — orchestrator tự bóc RoleSpec (anti-pattern):")
    leaked = orchestrate_the_bad_way(registry, "code")
    print(f"    kết quả: {leaked}")
    print(f"    -> đã LỘ field nội bộ: secret_internal_note = {leaked['leaked']!r}")
    assert "leaked" in leaked, "anti-pattern vô tình lôi field nội bộ ra ngoài"

    print("\n[6] Role lạ -> lỗi rõ ràng (cùng cơ chế get()).")
    try:
        registry.role_view("ghost")
        raise AssertionError("phải báo lỗi role lạ")
    except KeyError as e:
        print(f"    {e}")

    print("\nKẾT LUẬN: role_view là Factory Method ở dạng phép chiếu/adapter — đóng gói")
    print("'dựng đúng object cho ngữ cảnh orchestrator', ẩn chi tiết nội bộ của RoleSpec.")
    print("Factory Method không chỉ để chọn subclass; nó còn để TẠO VIEW/ADAPTER hợp ngữ cảnh.")
    print("\nTẤT CẢ ASSERT ĐỀU PASS.")


if __name__ == "__main__":
    demo()
