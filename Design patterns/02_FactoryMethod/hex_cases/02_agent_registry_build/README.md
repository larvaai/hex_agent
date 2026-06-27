# Case 02 — `AgentRegistry.build_agent` (Factory Method + Dependency Injection)

> "Tạo Agent loại nào" do **cấu hình** (RoleSpec) quyết định, không phải if-else trên tên role.

---

## 1. Bối cảnh trong hex_agent

`hex_agent` chạy nhiều **vai trò** (role): `code`, `test`, `business_analyst`, `reviewer`... Mỗi role có system prompt riêng, bộ tool được phép riêng, skill và lens riêng. Cả luồng single-agent (E05) lẫn multi-agent (E10) đều cần dựng một `Agent` từ tên role.

Nếu rải `if name == "code": ...` ở mọi nơi cần dựng Agent thì:
- Thêm role mới = sửa nhiều chỗ (vi phạm Open-Closed).
- Logic suy ra **allowlist** (union explicit tools + skill tools + core tools − forbidden tools) bị lặp và dễ lệch.

hex_agent giải quyết bằng `AgentRegistry`: mỗi role là một `RoleSpec` **first-class** (nạp từ YAML), giữ trong registry. `build_agent(name)` tra `RoleSpec` theo tên rồi dựng `Agent`, đồng thời **tiêm** các registry dùng chung (`skills`, `lenses`, `core_tools`).

- File: `roles/registry.py:60-66` — `build_agent(name) -> Agent`.
- File: `roles/registry.py:18-29` — `__init__` giữ `skills`, `lenses`, `core_tools`.
- File: `roles/spec.py:53-63` — `RoleSpec.allowed_tools`: nơi DUY NHẤT role gặp skill, "forbidden thắng".
- Dùng thật trong test: `tests/test_roles.py:39-44` (`build_agent("code")` ⇒ `{fs_read, fs_write, fs_list}`).

---

## 2. Trích đoạn code thật

```python
# roles/registry.py:60-66
def build_agent(self, name: str) -> Agent:
    return Agent(
        self.get(name),
        skills=self._skills,
        lenses=self._lenses,
        core_tools=self._core_tools,
    )
```

```python
# roles/spec.py:53-63 — allowlist được suy từ role + skill + core, forbidden thắng
def allowed_tools(self, skills, core_tools=frozenset()) -> frozenset[str]:
    union: set[str] = set(self.explicit_tools) | set(core_tools)
    forbidden: set[str] = set()
    for skill_name in self.allowed_skills:
        sk = skills.get(skill_name)
        union |= set(sk.allowed_tools)
        forbidden |= set(sk.forbidden_tools)
    return frozenset(union - forbidden)  # forbidden wins
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò GoF (Factory Method) | Thành phần trong hex_agent |
|------------------------------|----------------------------|
| **Creator** | `AgentRegistry` (`roles/registry.py:18`) — giữ kho RoleSpec + skills/lenses/core_tools |
| **Factory method** | `build_agent(name)` (`roles/registry.py:60`) |
| **Product** | `Agent` (`roles/agent.py`); allowlist suy từ `RoleSpec.allowed_tools` |
| **"Chọn loại nào"** | tra `RoleSpec` theo `name` trong registry (không if-else) |
| **Dependency Injection** | `skills`, `lenses`, `core_tools` được tiêm vào mỗi Agent, không do Agent tự tạo |
| **Client** | E05 single-agent + E10 multi-agent; `tests/test_roles.py:39` |

---

## 4. Bản rút gọn chạy được

File: [`agent_registry_build.py`](./agent_registry_build.py) — chạy `python3 agent_registry_build.py`.

Nó mô phỏng:
- `AgentRegistry.build_agent` tra `RoleSpec` theo tên và tiêm `SkillRegistry` + `core_tools` vào `Agent`.
- Logic allowlist thật: `explicit_tools ∪ core_tools ∪ skill.allowed_tools − skill.forbidden_tools` (forbidden thắng) — tái hiện đúng kết quả của `tests/test_roles.py:39-44` cho role `code`.
- **Đối chứng** `build_agent_with_ifelse`: Simple Factory if-else trên tên role; thêm `reviewer` buộc phải **sửa hàm** (vi phạm Open-Closed), còn registry chỉ cần `register(...)`.

Đã lược bỏ: parse YAML thật, Lens engine, `SkillSpec` đầy đủ. Giữ nguyên vai trò pattern và phép suy allowlist (load-bearing cho assert).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Cần một registry + định dạng cấu hình**: nếu hệ chỉ có 1-2 loại Agent cố định, registry là phức tạp thừa.
- **Lỗi cấu hình dời sang runtime**: gõ sai tên role chỉ vỡ khi gọi `build_agent`, không vỡ lúc compile. Cần test bao phủ cấu hình (như `test_roles.py`).
- **Không thay được cho Strategy**: nếu thứ thay đổi là **hành vi** chạy của agent (không phải "tạo loại nào"), Strategy/Template Method hợp hơn.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao tiêm `SkillRegistry` vào Agent (DI) tốt hơn để Agent tự `import` và tạo skill bên trong?
2. Trong `allowed_tools`, vì sao "forbidden thắng" lại quan trọng cho bảo mật? Cho ví dụ một role lỡ liệt kê `terminal_run` nhưng skill cấm nó.
3. Thêm role `devops` cần những gì với cách dùng registry? Còn với cách if-else thì phải đụng vào đâu?
