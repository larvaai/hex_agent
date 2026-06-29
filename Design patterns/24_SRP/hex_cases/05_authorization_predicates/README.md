# Case 05 — Permission Escalation Detection (SRP)

> Hai predicate thuần, một actor: đội **Security checkpoint (S21.6)**. Một việc: trả lời câu
> hỏi nhị phân yes/no về bảo mật — **không** đổi state, **không** log, **không** emit.

---

## 1. Bối cảnh trong hex_agent

Trước khi áp một permission patch, control plane phải biết hai điều: (a) patch này có **nâng
quyền** (lật cờ `can_*` từ False -> True) không; (b) lệnh này có thuộc loại **chỉnh-sửa-
permission** nên bắt buộc dừng cho human duyệt không.

`control/authz.py` (file `1-50`, đã mở kiểm chứng) đặt đúng hai predicate đó. Docstring
(`authz.py:1-11`) phân biệt rạch ròi **attribution ≠ authz**: `issued_by` chỉ *ghi* ai đã
hành động (tự khai, để audit), KHÔNG phải bằng chứng thẩm quyền; quyết định authz là
`requires_permission` giải tại checkpoint.

Hai hàm này **thuần** (pure): không phụ thuộc đường thực thi nào, không đụng Kernel/Session/
Event. `CAN_FLAGS` được suy ra từ chính dataclass `Permission` (`authz.py:21`) nên thêm một
cờ `can_*` mới sẽ tự được phủ — không phải sửa predicate.

---

## 2. Trích đoạn code thật

`control/authz.py:21-40` — PermissionFieldInspector + EscalationDetector:

```python
# Boolean capability flags on Permission. Derived from the dataclass so a new can_* flag is
# covered automatically (allowed_tools is excluded — see KNOWN GAP below).
CAN_FLAGS = frozenset(f.name for f in fields(Permission) if f.name.startswith("can_"))

...

def is_permission_escalating(current: Permission, patch: dict) -> bool:
    """True if ``patch`` flips any boolean capability flag False->True on ``current``. ..."""
    return any(
        key in CAN_FLAGS and bool(value) and not getattr(current, key)
        for key, value in patch.items()
    )
```

`control/authz.py:43-49` — CommandClassifier (quyết từ registry, không từ lời tự khai):

```python
def command_needs_human_checkpoint(command_type: str, registry: CommandTypeRegistry) -> bool:
    """True if ``command_type`` edits permissions and therefore must pause for a human. ..."""
    return registry.requires_permission(command_type) in PERMISSION_EDIT_PERMISSIONS
```

---

## 3. Ánh xạ vai trò pattern <-> code thật

| Vai trò (SRP) | Thành phần code thật | path:line |
|---|---|---|
| PermissionFieldInspector | `CAN_FLAGS` (suy từ `fields(Permission)`) | `authz.py:21` |
| EscalationDetector | `is_permission_escalating` | `authz.py:29-40` |
| CommandClassifier | `command_needs_human_checkpoint` + `PERMISSION_EDIT_PERMISSIONS` | `authz.py:26, 43-49` |
| Permission contract (đọc bởi inspector) | `@dataclass Permission` các cờ `can_*` | `control/permission.py:21-29` |
| Command registry (đọc bởi classifier) | `CommandTypeRegistry.requires_permission` | `control/command_registry.py:56-57` |

Ba vai, một mục đích: trả lời yes/no cho câu hỏi bảo mật.

---

## 4. Bản rút gọn chạy được

File: [`authorization_predicates.py`](./authorization_predicates.py) — chạy
`python3 authorization_predicates.py`.

**Mô phỏng đúng:** cả hai predicate y nguyên logic gốc; `CAN_FLAGS` vẫn được suy tự động từ
dataclass `Permission` (chứng minh "thêm cờ mới tự phủ"); `PERMISSION_EDIT_PERMISSIONS` giữ
nguyên ý nghĩa.

**Lược bỏ:** `CommandTypeRegistry` nặng (đọc YAML, có `apply_at`, `assert_known`...) được
thay bằng một registry tối thiểu **chỉ phơi `requires_permission(command_type)`** — đúng cái
mà `command_needs_human_checkpoint` cần. `Permission` chỉ giữ các cờ `can_*` liên quan authz.

Demo: escalation khi lật False->True; **không** escalation khi hạ quyền / no-op / sửa
`allowed_tools` (đúng KNOWN GAP trong gốc); classifier nhận diện lệnh sửa-permission cần
human checkpoint; assert bất biến ghép cặp "cấp `can_modify_permissions` vừa escalating vừa
human-gated". Có đối chứng "nếu trộn predicate vào hàm apply (vừa check vừa mutate) thì khó
test, khó audit, dễ sót checkpoint".

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí:** predicate thuần tách riêng nghĩa là phải có một call-site enforcement gọi
  chúng đúng lúc. Docstring gốc (`authz.py:7-10`) thừa nhận call-site đó *chưa tồn tại* trên
  nhánh này — predicate chỉ "pin invariant" trước.
- **Cảnh báo KNOWN GAP:** `is_permission_escalating` chỉ soi cờ boolean `can_*`; nới
  `allowed_tools` KHÔNG bị coi là escalation ở đây (ràng buộc bởi `SessionFactory.create_child`
  ở chỗ khác). Đừng đọc nhầm đây là "full authz".
- **Khi nào KHÔNG tách:** nếu hệ không có khái niệm permission động, hai predicate này vô
  nghĩa.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `CAN_FLAGS` được suy ra từ `fields(Permission)` thay vì viết tay danh sách? Lợi ích
   gì khi thêm một cờ `can_*` mới, và nó liên hệ thế nào với "một lý do để đổi"?
2. Docstring phân biệt attribution (`issued_by`) với authz (`requires_permission`). Vì sao
   `command_needs_human_checkpoint` đọc từ registry chứ KHÔNG đọc từ lời tự khai của issuer?
3. Cả hai hàm đều thuần và không I/O. Điều này giúp gì cho việc test, và vì sao "không đổi
   state" lại là một phần của trách nhiệm-đơn-nhất ở đây?
