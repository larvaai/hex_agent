# Case 01 — `SessionFactory`: Factory DDD đa-path (create vs restore)

> Distill từ `core/session.py:104-203` (và `core/session.py:15-101`, `core/state.py:8-27`).
> Đây là ví dụ Factory DDD **2 path** sách giáo khoa: tạo aggregate mới (enforce invariant,
> sinh ID, freeze deps, publish event) vs khôi phục từ state đã persist (trust state, không
> re-check, không emit). Có thêm một **business rule ở tầng factory**: scope của session con
> phải là tập con scope của session cha.

---

## 1. Bối cảnh trong hex_agent

Mỗi lần agent nhận một task (root hoặc một delegation con), runtime cần một `KernelSession` —
aggregate sở hữu state riêng của task đó, trong khi các service nặng (registry tool, event bus)
vẫn dùng chung trên `AgentKernel`. Việc dựng một session đúng đắn không tầm thường:

- Phải sinh `session_id / run_id / task_id` đúng quan hệ (root: run_id = task_id; child: chia sẻ
  run_id với cha, depth + 1).
- Phải kiểm capability yêu cầu có thật trong registry (`core/session.py:110-117`).
- Phải `kernel.freeze()` để khoá registry trước khi session chạy (`core/session.py:141`).
- Phải publish `task.accepted` đúng MỘT lần — lúc tạo mới (`core/session.py:145`).
- Khi resume từ checkpoint, lại tuyệt đối KHÔNG được re-chạy mấy bước trên: state đã persist là
  *sự thật*, không phải đề xuất thay đổi.

Vì vậy `SessionFactory` là **constructor duy nhất** — docstring code thật ghi rõ:
*"The only constructor for root/child sessions; AgentKernel never creates sessions."*
(`core/session.py:105`). Đặc biệt, `create_child` còn enforce một quy tắc bảo mật: scope con
không được vượt scope cha (`core/session.py:163-164`).

---

## 2. Trích đoạn code thật

Path RESTORE — `core/session.py:188-203` (trust state, không re-validate, không emit event):

```python
def restore(
    self,
    *,
    identity: SessionIdentity,
    state: dict[str, Any],
    allowed_capabilities: frozenset[str],
) -> KernelSession:
    self.kernel.freeze()
    if not allowed_capabilities <= self._effective_root_scope(None):
        raise ValueError("Persisted session contains capabilities unavailable in this runtime.")
    store = StateStore()
    store.restore(state)
    session = KernelSession(self.kernel, identity, store, allowed_capabilities)
    if not isinstance(store.get("current_task"), TaskEnvelope):
        session._closed = True
    return session
```

Business rule ở factory — `core/session.py:162-164` (scope con phải là subset cha):

```python
scope = parent.allowed_capabilities if requested_scope is None else requested_scope
if not scope <= parent.allowed_capabilities:
    raise PermissionError("Child capability scope must be a subset of the parent scope.")
```

So với path CREATE — `core/session.py:141-145` (freeze + publish event lúc tạo mới):

```python
self.kernel.freeze()
state = StateStore()
state.set("current_task", task)
session = KernelSession(self.kernel, identity, state, scope)
self.kernel.events.publish("task.accepted", session.call_context().event_fields())
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong pattern | Code thật (hex_agent) | Trong bản distill (`session_factory.py`) |
|-----------------------|-----------------------|------------------------------------------|
| Factory | `SessionFactory` (`core/session.py:104`) | `SessionFactory` |
| Path `create()` (aggregate mới) | `create_root` / `create_child` (119-186) | `create_root` / `create_child` |
| Path `reconstitute()` (load từ persist) | `restore` (188-203) | `restore` |
| Enforce invariant lúc create | `_effective_root_scope` (110-117), `freeze()` (141) | `_effective_root_scope`, `kernel.freeze()` |
| Business rule ở factory | scope con ⊆ cha (163-164) | `create_child` raise `PermissionError` |
| Publish event chỉ khi create | `kernel.events.publish("task.accepted")` (145, 185) | `kernel.publish("task.accepted")` |
| Aggregate Root trả về | `KernelSession` (49-101) | `KernelSession` |
| Value object identity | `SessionIdentity` (15-46) | `SessionIdentity` |
| Repository state (snapshot/restore) | `StateStore` (`core/state.py:8-27`) | `StateStore.snapshot/restore` |

---

## 4. Bản rút gọn chạy được

File: [`session_factory.py`](session_factory.py) — `python3 session_factory.py` (exit 0).

Mô phỏng đầy đủ:
- Hai path factory tách bạch: `create_root/create_child` (enforce + freeze + publish) vs `restore`
  (trust state, không emit). Demo assert: restore **không tăng số event**, và tôn trọng
  `current_task=None` (session khôi phục ở trạng thái closed).
- Business rule subset: child xin capability cha không có → `PermissionError`.
- Phân biệt `requested_scope=None` (kế thừa cha) vs `frozenset()` (deny-all) — đúng comment ở
  code thật `core/session.py:160-162`.
- Repository session-scoped: `StateStore.snapshot()` (deepcopy detached) rồi `restore()`.
- Đối chứng (`naive_restore_rerunning_create`): "khôi phục" sai cách bằng cách gọi lại `create_root`
  → làm sống lại task đã chết và publish event giả. Đây chính là vi phạm B trong bài gốc.

Lược bỏ (không ảnh hưởng vai trò pattern):
- `AgentKernel` thật (registry động, tool execution, event envelope) → `FakeKernel` chỉ giữ
  `list_capabilities / freeze / publish`.
- `uuid.uuid4().hex` → ID đếm tăng (`task-1`, `sess-2`...) để output xác định, dễ assert.
- `TaskEnvelope` (schema phong phú) → một dict `{"user_request": ...}`.
- `call_context()` / `execute_tool()` / event_fields → bỏ, không liên quan tới phần factory.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **2 method phải bảo trì song song.** Mỗi lần thêm field vào aggregate, cả `create` và `restore`
  đều phải cập nhật. Nếu construction chỉ 1 dòng và không có path load → một static `create()` là đủ
  (bài gốc, mục "Khi nào KHÔNG"). Tách factory chỉ đáng khi construction multi-step / multi-source /
  cần phân biệt create vs reconstitute.
- **Rủi ro lẫn lộn 2 path.** Nếu lỡ gọi `create` để "load" (như đối chứng), bạn re-emit event và
  ghi đè state đã persist. Đây là bug khó thấy lúc runtime — chỉ lộ ra khi resume.
- **Business rule ở factory phải là rule *cấu thành*** (vd scope subset enforce lúc dựng). Nếu rule
  có side effect hoặc cần I/O, nó là Domain Service, đừng nhét vào factory.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `restore` KHÔNG được publish `task.accepted`, trong khi `create_root` thì phải? Điều gì
   hỏng nếu mỗi lần resume lại publish event này?
2. `create_child` xử lý `requested_scope=None` khác `requested_scope=frozenset()` thế nào, và tại
   sao xem `frozenset()` là "falsy rồi widen về scope cha" lại là một lỗ hổng bảo mật?
3. Trong bản distill, vì sao `restore` đặt `_closed=True` khi `current_task` là `None`? Liên hệ tới
   định nghĩa "trust the persisted state" của reconstitute trong bài gốc.
