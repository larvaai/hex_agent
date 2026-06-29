"""
Case 02 — AgentRegistry.build_agent (Factory Method + Dependency Injection).

DISTILL TRUNG THỰC TỪ MÃ THẬT:
  - roles/registry.py:60-66   (build_agent(name) -> Agent)
  - roles/registry.py:18-29   (AgentRegistry.__init__: giữ skills, lenses, core_tools)
  - roles/registry.py:32-39   (register / load_file: nạp RoleSpec vào registry)
  - roles/spec.py:41-63       (RoleSpec + allowed_tools: nơi role ∪ skill ∪ core - forbidden)
  - tests/test_roles.py:39-44 (test_build_agent_from_config -> build_agent("code"))

Ở hex_agent, "tạo Agent loại nào" KHÔNG quyết định bằng if-else trên tên role.
Mỗi role là một RoleSpec (cấu hình first-class, nạp từ YAML). build_agent(name)
tra RoleSpec theo tên rồi dựng Agent, đồng thời TIÊM (inject) các registry dùng
chung (skills, lenses, core_tools) vào Agent. Client gọi build_agent("code") mà
không cần biết chữ ký Agent.__init__ hay cách suy ra allowlist.

Bản distill chỉ dùng stdlib. Lược bỏ: parse YAML thật, Lens engine, SkillSpec
đầy đủ. Giữ nguyên vai trò pattern: Creator (registry) + Product (Agent) +
quyết định theo config (RoleSpec) + dependency injection (skills/core_tools).
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Cấu hình first-class — distill từ RoleSpec / SkillSpec
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SkillSpec:
    """Distill từ skills/spec (chỉ giữ phần ảnh hưởng allowlist)."""

    name: str
    allowed_tools: frozenset[str] = frozenset()
    forbidden_tools: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RoleSpec:
    """Distill từ roles/spec.py:41-63. Đây là 'config quyết định tạo gì'."""

    name: str
    role: str
    system_prompt: str
    explicit_tools: tuple[str, ...] = ()
    allowed_skills: tuple[str, ...] = ()
    lenses: tuple[str, ...] = ()

    def allowed_tools(self, skills: "SkillRegistry", core_tools: frozenset[str]) -> frozenset[str]:
        """Nơi DUY NHẤT role gặp skill (roles/spec.py:53-63). forbidden thắng."""
        union: set[str] = set(self.explicit_tools) | set(core_tools)
        forbidden: set[str] = set()
        for skill_name in self.allowed_skills:
            sk = skills.get(skill_name)
            union |= set(sk.allowed_tools)
            forbidden |= set(sk.forbidden_tools)
        return frozenset(union - forbidden)


class SkillRegistry:
    """Distill từ skills/registry.py (chỉ giữ get)."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillSpec] = {}

    def register(self, spec: SkillSpec) -> SkillSpec:
        self._skills[spec.name] = spec
        return spec

    def get(self, name: str) -> SkillSpec:
        try:
            return self._skills[name]
        except KeyError:
            raise KeyError(f"Unknown skill '{name}'.") from None


# ─────────────────────────────────────────────────────────────────────────────
# Product — distill từ roles/agent.py (Agent)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Agent:
    """Sản phẩm do factory tạo. allowed_tools suy ra từ spec + skills + core_tools."""

    spec: RoleSpec
    skills: SkillRegistry
    core_tools: frozenset[str] = frozenset()
    allowed_tools: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        # Agent thật suy allowlist từ spec.allowed_tools(...) — ta giữ đúng logic.
        self.allowed_tools = self.spec.allowed_tools(self.skills, self.core_tools)


# ─────────────────────────────────────────────────────────────────────────────
# Creator (factory) — distill từ AgentRegistry (roles/registry.py)
# ─────────────────────────────────────────────────────────────────────────────
class AgentRegistry:
    """Creator: giữ kho RoleSpec + các registry dùng chung, và build_agent."""

    def __init__(self, *, skills: SkillRegistry, core_tools: frozenset[str] = frozenset()) -> None:
        self._skills = skills
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

    # ── Factory method: build_agent (roles/registry.py:60-66) ─────────────────
    def build_agent(self, name: str) -> Agent:
        """Quyết định 'tạo Agent nào' = tra RoleSpec theo tên (không if-else).
        Tiêm skills + core_tools vào Agent (dependency injection)."""
        return Agent(
            self.get(name),
            skills=self._skills,
            core_tools=self._core_tools,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG: Simple Factory if-else (anti-pattern bài học cảnh báo)
# ─────────────────────────────────────────────────────────────────────────────
def build_agent_with_ifelse(name: str, skills: SkillRegistry, core_tools: frozenset[str]) -> Agent:
    """Anti-pattern: tên role hard-code trong if-else. Thêm role = sửa hàm này.

    Vi phạm Open-Closed: mỗi role mới buộc đụng vào hàm chung, dễ gây regression,
    và logic dựng Agent bị lặp lại. (Đối lập với build_agent dựa registry.)
    """
    if name == "code":
        spec = RoleSpec("code", "Coder", "Bạn viết code", explicit_tools=("fs_read", "fs_write"),
                        allowed_skills=("file_edit",), lenses=("correctness",))
    elif name == "test":
        spec = RoleSpec("test", "Tester", "Bạn chạy test", explicit_tools=("terminal_run",))
    elif name == "business_analyst":
        spec = RoleSpec("business_analyst", "BA", "Bạn phân tích", explicit_tools=("fs_read",))
    else:
        raise ValueError(f"Unknown role {name!r}")
    return Agent(spec, skills=skills, core_tools=core_tools)


def demo() -> None:
    print("=" * 72)
    print("CASE 02 — AgentRegistry.build_agent (Factory Method + DI)")
    print("Nguồn thật: roles/registry.py:60-66 ; roles/spec.py:41-63")
    print("=" * 72)

    # Cấu hình skills dùng chung (sẽ được tiêm vào mọi Agent).
    skills = SkillRegistry()
    skills.register(SkillSpec("file_edit", allowed_tools=frozenset({"fs_read", "fs_write", "fs_list"}),
                              forbidden_tools=frozenset({"terminal_run"})))

    registry = AgentRegistry(skills=skills, core_tools=frozenset())

    # Các role là CONFIG first-class — nạp vào registry, không nằm trong code dựng.
    registry.register(RoleSpec("code", "Coder", "Bạn viết code",
                               explicit_tools=("fs_read", "fs_write"),
                               allowed_skills=("file_edit",), lenses=("correctness",)))
    registry.register(RoleSpec("test", "Tester", "Bạn chạy test", explicit_tools=("terminal_run",)))
    registry.register(RoleSpec("business_analyst", "BA", "Bạn phân tích", explicit_tools=("fs_read",)))

    print("\n[1] Client chỉ gọi build_agent(<tên role>). Không if-else, không biết Agent.__init__.")
    code_agent = registry.build_agent("code")
    test_agent = registry.build_agent("test")
    ba_agent = registry.build_agent("business_analyst")
    print(f"    code  -> allowed_tools = {sorted(code_agent.allowed_tools)}")
    print(f"    test  -> allowed_tools = {sorted(test_agent.allowed_tools)}")
    print(f"    ba    -> allowed_tools = {sorted(ba_agent.allowed_tools)}")

    # Phản chiếu tests/test_roles.py:39-44: role 'code' = fs_* và forbid terminal_run.
    assert code_agent.allowed_tools == {"fs_read", "fs_write", "fs_list"}
    assert "terminal_run" not in code_agent.allowed_tools, "skill file_edit cấm terminal_run -> forbidden thắng"
    assert code_agent.spec.lenses == ("correctness",)
    print("    (khớp test_build_agent_from_config: file_edit thêm fs_*, cấm terminal_run)")

    print("\n[2] Cùng MỘT factory trả Agent KHÁC NHAU tuỳ tên role (quyết định theo config).")
    assert type(code_agent) is type(test_agent) is Agent  # cùng product interface
    assert code_agent.allowed_tools != test_agent.allowed_tools  # khác nội dung
    print("    cùng kiểu Agent, khác allowlist -> đúng tinh thần Factory Method.")

    print("\n[3] Dependency Injection: skills được TIÊM vào, Agent không tự tạo skill.")
    assert code_agent.skills is skills, "Agent dùng chung SkillRegistry do registry tiêm vào"
    print("    code_agent.skills IS registry.skills -> dùng chung, không nhân bản.")

    print("\n[4] Role không tồn tại -> lỗi rõ ràng, liệt kê role đã biết.")
    try:
        registry.build_agent("ghost")
        raise AssertionError("phải báo lỗi role lạ")
    except KeyError as e:
        print(f"    {e}")

    print("\n[5] MỞ RỘNG: thêm role 'reviewer' chỉ bằng register(...) — KHÔNG sửa build_agent.")
    registry.register(RoleSpec("reviewer", "Reviewer", "Bạn review", explicit_tools=("fs_read",),
                               allowed_skills=("file_edit",)))
    reviewer = registry.build_agent("reviewer")
    print(f"    reviewer -> allowed_tools = {sorted(reviewer.allowed_tools)}  (0 dòng code dựng sửa đổi)")
    assert "fs_write" in reviewer.allowed_tools  # đến từ skill file_edit

    print("\n[6] ĐỐI CHỨNG — Simple Factory if-else:")
    a = build_agent_with_ifelse("code", skills, frozenset())
    print(f"    if-else build('code') ra cùng kết quả: {sorted(a.allowed_tools)}")
    print("    NHƯNG để thêm 'reviewer' phải SỬA hàm build_agent_with_ifelse (vi phạm Open-Closed).")
    try:
        build_agent_with_ifelse("reviewer", skills, frozenset())
        raise AssertionError("if-else chưa biết 'reviewer'")
    except ValueError as e:
        print(f"    if-else không biết role mới cho tới khi sửa code: {e}")

    print("\nKẾT LUẬN: 'Tạo Agent nào' được quyết định bằng CONFIG (RoleSpec trong registry),")
    print("không phải if-else. build_agent là factory method + nơi tiêm dependency. Thêm")
    print("role mới = thêm cấu hình, không đụng code dựng.")
    print("\nTẤT CẢ ASSERT ĐỀU PASS.")


if __name__ == "__main__":
    demo()
