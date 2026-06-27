# Case 05 — `AgentRegistry.role_view` (Factory Method dạng projection / adapter)

> Factory Method không chỉ để "chọn subclass" — nó còn để **dựng đúng object (view/adapter) cho một ngữ cảnh**.

---

## 1. Bối cảnh trong hex_agent

Orchestrator đa-agent (Epic E10) cần một bản chiếu **gọn** của mỗi role để điều phối graph — chỉ cần `agent_id`, `role`, `system_prompt`, `default_scope`. Nó **không** nên (và không muốn) chạm vào `RoleSpec` đầy đủ, vì `RoleSpec` còn nhiều trường nội bộ (`department`, `test_ownership`, `may_route_to`, `lenses`...) mà orchestrator không cần và không nên phụ thuộc.

`AgentRegistry.role_view(name)` lấy `RoleSpec` rồi **chiếu** ra một `RoleView` đúng hình dạng orchestrator cần. Đây là một **biến thể** của Factory Method: factory không tạo một subclass mới, mà tạo một **adapter/view** từ domain object sẵn có. Điểm dạy học: Factory Method đóng gói "**cách dựng object phù hợp ngữ cảnh**" — chọn subclass chỉ là một dạng; phép chiếu/biến đổi cũng là một dạng.

- File: `roles/registry.py:69-76` — `role_view(name) -> RoleView`.
- File: `roles/registry.py:78-79` — `list_roles()` trả `tuple[RoleView]` cho orchestrator.
- File: `roles/spec.py:31-39` — `RoleView` (projection slim).
- File: `roles/spec.py:41-63` — `RoleSpec` (domain object đầy đủ).

---

## 2. Trích đoạn code thật

```python
# roles/registry.py:69-79
def role_view(self, name: str) -> RoleView:
    spec = self.get(name)
    return RoleView(
        agent_id=spec.name,
        role=spec.role,
        system_prompt=spec.system_prompt,
        default_scope=spec.allowed_tools(self._skills, self._core_tools),
    )

def list_roles(self) -> tuple[RoleView, ...]:
    return tuple(self.role_view(name) for name in self.names())
```

```python
# roles/spec.py:31-39 — view slim mà orchestrator E10 đọc
@dataclass(frozen=True)
class RoleView:
    """The slim role projection E10's orchestrator reads (BUILD_PLAN §1a)."""
    agent_id: str
    role: str
    system_prompt: str
    default_scope: frozenset[str]
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò | Thành phần trong hex_agent |
|---------|----------------------------|
| **Creator** | `AgentRegistry` (`roles/registry.py:18`) |
| **Factory method (projection)** | `role_view(name)` (`roles/registry.py:69`) |
| **Product** | `RoleView` (`roles/spec.py:31`) |
| **Nguồn để chiếu** | `RoleSpec` (`roles/spec.py:41`) — đầy đủ, nhiều trường nội bộ |
| **Phép biến đổi** | trích `name → agent_id`, giữ `role`/`system_prompt`, tính `default_scope = allowed_tools(...)` |
| **Client** | orchestrator graph E10 (chỉ đọc `RoleView`, không chạm `RoleSpec`) |

---

## 4. Bản rút gọn chạy được

File: [`role_view_factory.py`](./role_view_factory.py) — chạy `python3 role_view_factory.py`.

Nó mô phỏng:
- `RoleSpec` đầy đủ (có thêm `secret_internal_note` để minh hoạ field nội bộ) và `RoleView` slim 4 trường.
- `role_view` chiếu `RoleSpec → RoleView`, tính `default_scope` từ `derive_scope` (rút gọn của `allowed_tools`).
- `list_roles` dựng view cho mọi role.
- **Đối chứng** `orchestrate_the_bad_way`: orchestrator chạm thẳng `RoleSpec` và vô tình **lộ** `secret_internal_note` — cho thấy giá trị của lớp view.

Đã lược bỏ: parse YAML, Lens/Skill engine. Giữ nguyên vai trò pattern và tính bao đóng (RoleView không mang field nội bộ — có assert kiểm chứng).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Trùng lặp shape**: `RoleView` lặp lại vài trường của `RoleSpec`; khi domain object đổi, có thể phải đồng bộ view.
- **Quá sớm**: nếu chỉ một nơi dùng và shape giống hệt domain object, thêm view là thừa — cứ truyền `RoleSpec`.
- **Có thể tách thành lớp riêng**: phép chiếu này cũng có thể đặt trong một class `RoleViewMapper` độc lập; gom vào registry chỉ hợp lý khi muốn giữ "logic liên quan role ở một chỗ".

---

## 6. Câu hỏi tự kiểm tra

1. `role_view` "tạo" cái gì? Vì sao vẫn gọi nó là một dạng Factory Method dù không sinh subclass mới?
2. Lớp `RoleView` bảo vệ orchestrator khỏi rủi ro gì khi `RoleSpec` thay đổi nội bộ?
3. Khi nào nên tách phép chiếu thành một `RoleViewMapper` riêng thay vì để trong `AgentRegistry`?
