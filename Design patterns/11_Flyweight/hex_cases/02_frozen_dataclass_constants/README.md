# Case 02 — Frozen Dataclass Constants: FeatureDescriptor, ToolDescriptor, Schema Envelopes

> Flyweight đơn giản nhất trong `hex_agent`: intrinsic state (cấu trúc + giá trị) được
> định nghĩa MỘT LẦN dưới dạng `@dataclass(frozen=True)` và chia sẻ. Vì bất biến nên
> chúng hashable, an toàn làm dict key, và không bao giờ bị mutate qua nhiều context.

---

## 1. Bối cảnh trong hex_agent

Toàn bộ "data contract" của `hex_agent` được khai báo là frozen dataclass. Ví dụ trong
`core/schemas.py`: `TaskEnvelope` (11-25), `ToolRequest` (28-33), `ToolCallContext`
(36-46), `CapabilityResult` (63-111), `FeatureDescriptor` (114-129)... tất cả đều
`@dataclass(frozen=True)`. Sau khi tạo, chúng không thể sửa.

Có hai dạng "Flyweight constant" rõ rệt:

- `DEFAULT_DESCRIPTOR = ToolDescriptor()` (`core/registry.py:20`): một singleton dùng
  chung cho MỌI tool không khai báo metadata riêng. `resolve_tool` trả đúng instance
  này (`core/registry.py:108,111,112`) thay vì tạo mới.
- `FEATURE = FeatureDescriptor(...)` (`features/example_echo.py:9-13`): định nghĩa ở
  *module level*, không phải trong hàm. Mỗi lần `install(kernel)` (`features/example_echo.py:23-25`)
  tái dùng đúng instance `FEATURE` đó — không tạo lại mỗi lần.

Vấn đề thật được giải: rất nhiều object value-type được truyền qua lại trong vòng
request/response. Nếu chúng mutable, một chỗ sửa `request.args` có thể làm hỏng chỗ
khác đang giữ cùng tham chiếu. `frozen=True` chặn lỗi đó ở mức ngôn ngữ — chính là kỷ
luật immutability mà Flyweight yêu cầu.

---

## 2. Trích đoạn code thật

`ToolDescriptor` frozen + constant singleton — `core/registry.py:10-20`:

```python
@dataclass(frozen=True)
class ToolDescriptor:
    """Capability metadata used by retry/policy. ``kind`` is model|read|effect|tool;
    a non-idempotent effect must not be retried (E10 S10.13)."""

    kind: str = "tool"
    idempotent: bool = False
    risk: str = "low"


DEFAULT_DESCRIPTOR = ToolDescriptor()
```

`ToolRequest` frozen — `core/schemas.py:28-33`:

```python
@dataclass(frozen=True)
class ToolRequest:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    context: "ToolCallContext | None" = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
```

`FEATURE` constant tái dùng qua `install` — `features/example_echo.py:9-13, 23-25`:

```python
FEATURE = FeatureDescriptor(
    name="example_echo",
    capabilities=("echo",),
    description="Trivial echo tool used by smoke tests and as a feature-plugin example.",
)
...
def install(kernel: AgentKernel) -> None:
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tools(FEATURE.capabilities, EchoTool(), feature_name=FEATURE.name)
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Flyweight                          | Thành phần trong hex_agent                                            |
|--------------------------------------------|----------------------------------------------------------------------|
| `Flyweight` (intrinsic: structure + value) | mọi `@dataclass(frozen=True)` trong `core/schemas.py:11-129`          |
| Shared instance (1 đối tượng dùng chung)   | `DEFAULT_DESCRIPTOR` (`core/registry.py:20`), `FEATURE` (`features/example_echo.py:9`) |
| `Client` dùng constant, không nhân bản     | `install()` (`features/example_echo.py:23`), `resolve_tool` (`core/registry.py:103`) |
| Immutability guard                         | `@dataclass(frozen=True)` — chặn `__setattr__` sau `__init__`         |
| Tính hashable để làm cache key             | frozen dataclass tự sinh `__hash__` từ field bất biến                 |

---

## 4. Bản rút gọn chạy được

File: [`frozen_dataclass_constants.py`](./frozen_dataclass_constants.py) — chạy
`python3 frozen_dataclass_constants.py`.

**Mô phỏng đúng:**
- `ToolDescriptor`, `FeatureDescriptor`, `ToolRequest`, `SessionIdentity` đều frozen
  (distill `core/registry.py:10-18`, `core/schemas.py:114-129`, `core/schemas.py:28-33`,
  `core/session.py:15-23`).
- `DEFAULT_DESCRIPTOR` singleton (`core/registry.py:20`) và `FEATURE` module-level
  (`features/example_echo.py:9-13`).
- `install()` tái dùng đúng `FEATURE` — assert `f1 is f2 is FEATURE`.
- frozen → hashable: dùng `ToolRequest` làm dict key; `r1 == r2`, `hash(r1) == hash(r2)`.
- Mutate frozen bị chặn (`FrozenInstanceError`); muốn "đổi" thì `dataclasses.replace`
  tạo bản mới (bản gốc dùng chung giữ nguyên).
- Đối chứng `BadDescriptor` (không frozen): sửa 1 alias → mọi alias đổi theo — đúng bug
  "mutable Flyweight" trong bài học gốc.

**Lược bỏ:** `ToolRequest.args` thật là `dict`; ở đây dùng `tuple` để giữ hashable cho
demo dict-key (chú thích rõ trong code). Bỏ `context`, `request_id`, các method
`as_dict`/`from_dict`, và phần đăng ký tool thật trong kernel.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Mỗi instance thật sự unique:** nếu mọi field đều khác nhau giữa các lần dùng thì
  không có intrinsic để chia sẻ — constant module-level vô nghĩa.
- **Cần mutate thường xuyên:** frozen ép phải tạo bản mới qua `replace()`. Nếu một object
  thay đổi liên tục theo từng bước, chi phí tạo bản mới có thể đáng kể.
- **Hashability đòi field bất biến đệ quy:** một frozen dataclass chứa `dict`/`list`
  *vẫn không hashable*. Muốn dùng làm key phải đảm bảo các field con cũng hashable
  (tuple/frozenset) — đây là lý do nhiều schema trong hex_agent dùng `tuple[...]`.

---

## 6. Câu hỏi tự kiểm tra

1. Cho `t1 = TokenFactory.get("dog")`, `t2 = TokenFactory.get("dog")`, rồi
   `t1.frequency = 100`. Nếu `Token` là frozen dataclass thì dòng cuối xảy ra gì? Nếu
   *không* frozen thì `t2.frequency` bằng bao nhiêu — và đó là feature hay bug?
2. Vì sao `FEATURE` được đặt ở module level chứ không tạo bên trong `install()`? Lợi ích
   Flyweight cụ thể là gì?
3. Một frozen dataclass có field kiểu `dict` thì có hashable không? Hệ quả khi muốn dùng
   nó làm cache key là gì?
