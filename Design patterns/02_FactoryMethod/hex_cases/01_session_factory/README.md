# Case 01 — `SessionFactory.create_root / create_child` (Factory Method)

> Tách quyết định "tạo phiên (session) **loại nào** và **dựng ra sao**" ra khỏi code gọi, dồn vào một Creator duy nhất.

---

## 1. Bối cảnh trong hex_agent

Mỗi lần `hex_agent` nhận một yêu cầu của người dùng, nó phải mở một **phiên làm việc** (`KernelSession`) — nơi giữ trạng thái riêng của task đó (current_task, kết quả, phạm vi capability được phép). Khi một agent **uỷ thác** (delegation) việc cho agent con, lại cần một phiên **con** với phạm vi quyền là **tập con** của cha.

Vấn đề thật: nếu để mỗi nơi trong code tự dựng `KernelSession`, ta sẽ:
- Lặp lại logic cấp `session_id`/`run_id`/`task_id`.
- Dễ **quên** các bước bất biến: `kernel.freeze()`, phát event `task.accepted`, validate phạm vi capability.
- Mở **lỗ hổng nâng quyền**: phiên con vô tình có quyền rộng hơn cha.

Vì vậy hex_agent quy định: `AgentKernel` **không bao giờ** tự tạo session — mọi session phải đi qua `SessionFactory`. Đây là docstring thật của lớp đó (`core/session.py:104-105`):

- File: `core/session.py:104-186` — lớp `SessionFactory` với `create_root` (119-146), `create_child` (148-186).
- File: `core/session.py:188-203` — `restore` (factory method thứ ba: dựng lại phiên từ state đã lưu).
- Dùng thật trong test: `tests/test_lifecycle.py:12` và `tests/test_delegation.py:46`.

---

## 2. Trích đoạn code thật

```python
# core/session.py:104-117
class SessionFactory:
    """The only constructor for root/child sessions; AgentKernel never creates sessions."""

    def __init__(self, *, kernel: "AgentKernel") -> None:
        self.kernel = kernel

    def _effective_root_scope(self, requested: frozenset[str] | None) -> frozenset[str]:
        available = frozenset(item["name"] for item in self.kernel.registry.list_tools())
        if requested is None:
            return available
        if not requested <= available:
            unknown = sorted(requested - available)
            raise ValueError(f"Root session requested unknown capabilities: {unknown}")
        return requested
```

```python
# core/session.py:148-164 — create_child: scope subsetting (chống nâng quyền)
def create_child(self, parent, *, delegation_id, target, user_request,
                 context=None, requested_scope=None):
    if not parent.is_active:
        raise RuntimeError("Cannot create a child from an inactive parent session.")
    # None means "inherit the parent scope"; an explicit empty set means "deny all".
    scope = parent.allowed_capabilities if requested_scope is None else requested_scope
    if not scope <= parent.allowed_capabilities:
        raise PermissionError("Child capability scope must be a subset of the parent scope.")
    ...
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò GoF (Factory Method) | Thành phần trong hex_agent |
|------------------------------|----------------------------|
| **Creator** (đóng gói việc tạo) | `SessionFactory` (`core/session.py:104`) |
| **Factory method** (các biến thể tạo) | `create_root` (119), `create_child` (148), `restore` (188) |
| **Product** | `KernelSession` (`core/session.py:49`) |
| **Template tạo** (các bước chung) | cấp identity → validate scope → `freeze()` → dựng state → dựng session → `publish("task.accepted")` |
| **Client** | `orchestrator/loop.py`, `tests/test_lifecycle.py:12`, `tests/test_delegation.py:46` |
| **Bất biến do factory bảo đảm** | `_effective_root_scope` (110), scope-subset của con (163), phát event |

Lưu ý: đây là Factory Method "đa phương thức" — cùng một Creator có **nhiều** factory method cho các ngữ cảnh tạo khác nhau (root vs. child vs. restore), thay vì subclass hoá.

---

## 4. Bản rút gọn chạy được

File: [`session_factory.py`](./session_factory.py) — chạy `python3 session_factory.py`.

Nó mô phỏng:
- `SessionFactory` với đủ ba factory method `create_root` / `create_child` / `restore`.
- Bất biến **scope-subset** (con không vượt quyền cha) và `freeze()` + phát event.
- Một **đối chứng** `make_session_the_bad_way`: client tự dựng session, **quên** `freeze`, **quên** event, và để con **nâng quyền** lén lút.
- Một **mở rộng Open-Closed** `SessionFactoryWithResume.create_resumable`: thêm biến thể tạo mới mà không sửa `create_root/child` hay client.

Đã lược bỏ (thay bằng fake stdlib): `AgentKernel` thật → `FakeKernel` (chỉ giữ tập capability + log event); `StateStore` → `dict`; `TaskEnvelope`/`ToolCallContext` → dict đơn giản. Giữ nguyên: `uuid` (stdlib) và toàn bộ logic kiểm tra phạm vi.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí gián tiếp**: thêm một lớp `SessionFactory` đứng giữa. Nếu hệ chỉ có **một** cách tạo object đơn giản, factory là thừa — cứ gọi constructor.
- **Nhiều factory method có thể che giấu nhánh điều kiện**: nếu `create_root` và `create_child` chỉ khác nhau một tham số nhỏ, gộp lại có khi đơn giản hơn. Ở hex_agent việc tách là chính đáng vì hai luồng có **validate khác nhau** (scope tổng thể vs. scope-subset).
- **Đừng nhầm với Abstract Factory**: nếu bạn cần tạo **một họ** object khớp nhau (session + checkpoint + event-log cùng kiểu), đó là bài toán Abstract Factory.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao đặt kiểm tra "scope con ⊆ scope cha" **trong** `create_child` lại an toàn hơn là để mỗi nơi gọi tự kiểm tra?
2. `restore` khác `create_root` ở chỗ nào về mặt "tạo product"? Vì sao nó vẫn được coi là một factory method?
3. Nếu cần thêm loại phiên "read-only" (chỉ được gọi tool không ghi), bạn thêm vào đâu để **không** sửa client và **không** sửa `create_root/child`?
