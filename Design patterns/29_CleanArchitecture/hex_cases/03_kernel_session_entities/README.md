# Case 03 — Core Domain Entities (Schemas as Immutable Boundaries)

> **Pattern**: Clean Architecture — *vòng 1 (Entities)*.
> Entities là `frozen dataclass`: pure data, không I/O, không framework. Cùng một schema
> được use case, adapter, và bootstrap tiêu thụ y hệt. Vì thuần, ta tạo/serialize/deserialize
> hàng loạt trong micro-giây mà không cần DB/HTTP — đó là "100% unit-testable".

---

## 1. Bối cảnh trong hex_agent

Mọi dữ liệu băng qua boundary trong hex_agent (task gửi vào, tool request, kết quả delegation, identity của session) đều là **frozen dataclass** ở `core/`. Đây là vòng trong cùng của Clean Architecture: ổn định nhất, không phụ thuộc gì ngoài stdlib.

- `core/schemas.py:1` ghi rõ mục đích file: "Core data contracts". Các entity:
  - `TaskEnvelope` (**`core/schemas.py:11-26`**) — yêu cầu một task, có `as_dict`/`from_dict`.
  - `ToolRequest` (**`core/schemas.py:28-33`**), `FeatureDescriptor` (**`core/schemas.py:114-129`**).
  - `DelegationRequest` (**`core/schemas.py:181-198`**), `DelegationResult` (**`core/schemas.py:235-253`**).
- `core/session.py:15-46` định nghĩa `SessionIdentity` — identity **bất biến** của một run. `KernelSession` (**`core/session.py:49-102`**) tách **identity bất biến** khỏi **state mutable** (`StateStore`).
- `core/kernel.py:76-98` là `AgentKernel` — orchestrator thuần, docstring ghi "Concrete behavior lives behind ports/adapters... cross-cutting behavior lives in middleware". `freeze()` (**`core/kernel.py:91-97`**) đóng băng cấu hình chia sẻ trước session đầu tiên.

Điểm mấu chốt: một `DelegationResult` định nghĩa ở đây được `DelegationManager` (use case) build, adapter serialize, bootstrap deserialize — **cùng một contract**, không ai sở hữu một biến thể riêng.

---

## 2. Trích đoạn code thật

Entity bất biến với serialize đối xứng (`core/schemas.py:11-26`):

```python
@dataclass(frozen=True)
class TaskEnvelope:
    user_request: str
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def as_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "user_request": self.user_request,
                "context": dict(self.context), "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TaskEnvelope":
        return cls(user_request=d.get("user_request", ""), context=dict(d.get("context") or {}),
                   metadata=dict(d.get("metadata") or {}), task_id=d.get("task_id") or uuid.uuid4().hex)
```

Tách identity bất biến khỏi state mutable (`core/session.py:49-61`):

```python
@dataclass
class KernelSession:
    """Owns one task's mutable state; shared services remain on the kernel."""
    kernel: "AgentKernel"
    identity: SessionIdentity            # <- bất biến (frozen)
    state: StateStore                     # <- mutable
    allowed_capabilities: frozenset[str]
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def is_active(self) -> bool:
        return not self._closed and isinstance(self.state.get("current_task"), TaskEnvelope)
```

Orchestrator thuần, đóng băng trước session đầu tiên (`core/kernel.py:91-97`):

```python
def freeze(self) -> None:
    """Freeze shared mutable configuration before the first session starts."""
    if self._frozen:
        return
    self.registry.freeze()
    self.config = _deep_freeze(copy.deepcopy(dict(self.config)))
    self._frozen = True
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Clean Architecture | Thành phần trong hex_agent | File:line |
|---|---|---|
| **Entities / Value Object (vòng 1)** | `TaskEnvelope`, `DelegationResult`, `FeatureDescriptor` (frozen) | `core/schemas.py:11-26, 235-253, 114-129` |
| **Immutable identity** | `SessionIdentity` (frozen) | `core/session.py:15-46` |
| **Application context (vòng 2 state)** | `KernelSession` (identity bất biến + state mutable) | `core/session.py:49-102` |
| **Application orchestrator (vòng 2)** | `AgentKernel`, `freeze()` | `core/kernel.py:76-98` |
| **DTO đối xứng tại boundary** | `as_dict()` / `from_dict()` trên mỗi entity | `core/schemas.py` (rải rác) |
| **Dependency direction** | 0 import từ vòng ngoài (chỉ stdlib + entity khác) | `core/schemas.py:1-6` |

---

## 4. Bản rút gọn chạy được

File: [`kernel_session_entities.py`](kernel_session_entities.py)

Nó **mô phỏng**:
- `TaskEnvelope`, `DelegationResult`, `SessionIdentity` (frozen, có `as_dict`/`from_dict`).
- `KernelSession` tách identity bất biến khỏi `StateStore` mutable; vòng đời `complete_task`.
- `AgentKernel` orchestrator thuần với `freeze()` chặn mutate sau khi session bắt đầu.
- Benchmark tạo 10.000 entity trong vài ms (không I/O) → minh hoạ độ thuần.
- Đối chứng `OrmStyleResult`: một "entity" kiểu ORM mutable, cần `_FakeDBSession`, lazy-load kích hoạt I/O, đóng session → "detached instance" vỡ. Đây chính là hiểu sai "Entities = ORM model" mà bài học gốc cảnh báo.

Nó **lược bỏ** (so với bản thật):
- `_deep_freeze` đệ quy + `MappingProxyType`, `copy.deepcopy` config, event bus, middleware pipeline, `execute_tool` chokepoint (case 01/04 chạm tới những phần khác).
- Nhiều entity khác (`ToolCallContext`, `CapabilityResult`, `DelegationProgress`...) và logic `SessionFactory` tạo child session.
- DB thật → `_FakeDBSession` stdlib + `time.sleep(0.001)` giả lập round-trip.

Chạy:

```bash
python3 kernel_session_entities.py
```

Các `assert` chứng minh: (a) round-trip serialize giữ nguyên dữ liệu; (b) frozen chặn mutate, phải `replace`; (c) entity chỉ-trường-vô-hướng thì hashable (bỏ được vào set), kèm chú thích trung thực rằng entity chứa dict/tuple (như `DelegationResult` thật) thì *không* hashable; (d) `complete_task` đóng session đúng một lần; (e) 10.000 entity không phát sinh query nào (khác ORM lazy-load); (f) `freeze` chặn mutate registry sau khi bắt đầu.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **DTO/entity tách khỏi storage = duplicate + mapping code**: bạn viết `as_dict`/`from_dict` tay, và nếu có DB thì cần thêm một lớp mapper entity ↔ row. Bài học gốc liệt đây là một trade-off của Clean Architecture.
- **Immutability cần `replace()` thay vì mutate**: với object thay đổi state liên tục (ví dụ counter cập nhật hàng nghìn lần/giây), tạo bản mới mỗi lần có thể tốn. hex_agent giải bằng cách tách `StateStore` mutable riêng — entity bất biến, state thì không.
- **Anemic Domain Model risk**: entity thuần dễ tụt thành "chỉ getter" nếu dồn hết logic vào use case. Bài học gốc khuyên để entity có hành vi khi phù hợp; ở hex_agent, các entity chủ yếu là contract nên anemic là chấp nhận được.
- Với prototype nhỏ, dùng thẳng `dict` có thể nhanh hơn — nhưng mất type-safety và immutability.

---

## 6. Câu hỏi tự kiểm tra

1. `core/schemas.py` import những gì (xem `core/schemas.py:1-6`)? Vì sao việc nó **không** import bất cứ thứ gì từ `adapters/`, `features/`, `rag/` chính là định nghĩa của "vòng 1 — entities"?
2. `KernelSession` tách `identity` (frozen) khỏi `state` (mutable `StateStore`). Nếu gộp cả hai vào một mutable object thì mất gì? (Gợi ý: identity có nên đổi giữa chừng một run không?)
3. Vì sao `DelegationResult` (có field `summary: dict`) **không** hashable dù `frozen=True`, trong khi `SessionIdentity` (chỉ str/int) thì hashable? Điều này ảnh hưởng gì khi bạn muốn dùng entity làm key trong dict?
