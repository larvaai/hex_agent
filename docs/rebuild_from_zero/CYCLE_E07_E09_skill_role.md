# Gỡ vòng phụ thuộc E07 ↔ E09 (Skill ↔ Role)

> Quyết định interface để phá soft-cycle trong `01_BUILD_ORDER` ("E07↔E09"). Nguyên tắc repo:
> **định nghĩa hợp đồng trước, nội dung sau**. Đây là contract chốt; E07 và E09 code theo đây.

## Vòng phụ thuộc hiện tại (từ PRD)
- `E07/PRD.md`: Dependencies = E06, **E09** ("role gắn skill"); và "skill khai tool → suy `allowed_tools` của role".
- `E09/PRD.md`: Dependencies = E01, E06, **E07**; role.yaml có `allowed_skills`.
→ E07 cần E09, E09 cần E07 = vòng.

## Cách gỡ: Skill là role-agnostic; Role bind skill
Mấu chốt: **một skill KHÔNG cần biết role nào dùng nó.** Skill chỉ khai *tool theo tên* (E06 / `server.*`).
Việc "suy allowed_tools của role từ skill" là một **phép tính ở phía Role (E09)**, không phải phụ thuộc
ngược về phía Skill. Khi tách trách nhiệm đó về E09, **E07 hết phụ thuộc E09**.

```
Trước:  E06 → E07 ⇄ E09           (vòng)
Sau:    E06 → E07 → E09           (DAG; E09 cũng cần E01)
```

## Hợp đồng chốt

### E07 — SkillSpec (KHÔNG biết role)
```python
@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    triggers: tuple[str, ...]
    allowed_tools: tuple[str, ...]      # tên tool E06 / "server.*"; KHÔNG tham chiếu role
    forbidden_tools: tuple[str, ...]
    steps_md: str                       # body sau "## Steps" (chỉ nạp ở mode=full)
    report_md: str

class SkillRegistry:
    def get(self, name: str) -> SkillSpec: ...
    def render(self, name: str, *, mode: str = "contract") -> str: ...  # contract = cắt trước "## Steps"
```

### E09 — RoleSpec (tham chiếu skill theo TÊN) + phép suy allowlist
```python
@dataclass(frozen=True)
class RoleSpec:
    name: str; role: str; department: str
    system_prompt: str
    explicit_tools: tuple[str, ...]     # tool khai trực tiếp trong role.yaml
    allowed_skills: tuple[str, ...]     # TÊN skill (tham chiếu E07, không import ngược)
    may_route_to: tuple[str, ...]
    test_ownership: dict
    lenses: tuple[str, ...]

    def allowed_tools(self, skills: "SkillRegistry", core_tools: frozenset[str]) -> frozenset[str]:
        """DERIVATION sống ở E09 (đây là chỗ duy nhất chạm cả skill lẫn role)."""
        union = set(self.explicit_tools) | set(core_tools)
        forbidden: set[str] = set()
        for name in self.allowed_skills:
            sk = skills.get(name)
            union |= set(sk.allowed_tools)
            forbidden |= set(sk.forbidden_tools)
        return frozenset(union - forbidden)   # forbidden thắng
```

## Sở hữu type / chống nhân đôi
- `SkillSpec` + `SkillRegistry` ở module **skills/** (E07).
- `RoleSpec` ở module **roles/** (E09); roles **import** skills registry, **không** chiều ngược.
- Phép suy allowlist chỉ tồn tại **một chỗ**: `RoleSpec.allowed_tools(...)` (E09).

## Hệ quả build order
- E07 deps = **E06** (bỏ E09). Code E07 trước.
- E09 deps = **E01, E06, E07** (giữ nguyên). Code E09 sau E07.
- Cập nhật `01_BUILD_ORDER`: bỏ E09 khỏi dòng E07; ghi chú soft-cycle → "đã gỡ".

## Liên kết với E10
`E10/BUILD_PLAN.md §1a` phác `RoleSpec(agent_id, role, system_prompt, default_scope)` — đó là **bản rút gọn
E10 tiêu thụ**. Nguồn thật là `RoleSpec` của E09 ở trên: `agent_id ↔ name`, `default_scope ↔ allowed_tools(...)`.
Khi viết E09, expose đúng để E10 cắm vào không sửa.
