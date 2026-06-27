# Case 02 — Node (Entity) sở hữu DoneWhen (Value Object)

> Flagship thứ hai của Lesson 36 trong hex_agent: quan hệ cốt lõi **Entity sở hữu Value Object** — một `Node` có id và vòng đời, chứa một tuple các tiêu chí `DoneWhen` bất biến.

---

## 1. Bối cảnh trong hex_agent — vấn đề thật

`decompose_agent/` chia một task lớn thành cây các `Node`. Mỗi node có một tập tiêu chí nghiệm thu `done_when`. Hai ràng buộc thật mà file `decompose_agent/node.py` (đã mở kiểm chứng) phải bảo vệ:

1. **Một node "sai cấu trúc" không được tồn tại.** Docstring đầu file ghi: *"A structurally-wrong node cannot exist — every invariant is enforced at construction"* (`node.py:1-2`). Đây là validate-at-construction của Lesson 36 áp cho cả Entity (`Node`) lẫn Value Object (`DoneWhen`).
2. **Tiêu chí là CÂU HỎI, không phải CÂU TRẢ LỜI.** Worker (thành phần không tin cậy) chỉ được đề xuất tiêu chí `{check, params, artifact}`; nó KHÔNG được tự ghi verdict. Bất kỳ field kiểu `verdict/passed/status/score/done` trên một criterion là "forgery" và bị từ chối (`node.py:7-8`, `node.py:20`, `node.py:75-81`). Đây là lý do `DoneWhen` là một **Value Object có validate phòng thủ**.

`Node` thì khác hẳn: nó có `id` bền vững, có vòng đời `pending → active → done`, và được Navigator sở hữu/tiến hoá. Đó là một **Entity**. `Node` frozen nhưng "mutate" trạng thái qua `dataclasses.replace()` — đúng cách cập nhật một aggregate bất biến (`node.py:104-105`).

File:line thật:
- `decompose_agent/node.py:33-47` — `assert_safe_relpath()` (path-jail, VO defensive check)
- `decompose_agent/node.py:50-99` — `DoneWhen` (Value Object)
- `decompose_agent/node.py:102-176` — `Node` (Entity)

---

## 2. Trích đoạn code thật

`decompose_agent/node.py:50-69` — Value Object `DoneWhen`, validate + path-jail ở constructor:

```python
@dataclass(frozen=True)
class DoneWhen:
    """One acceptance criterion: a question the gate answers. Never an answer."""

    check: str
    params: dict[str, Any] = field(default_factory=dict)
    artifact: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.check, str) or not self.check.strip():
            raise ValueError("done_when criterion is missing a non-empty 'check'")
        if not isinstance(self.params, dict):
            raise ValueError(f"done_when criterion 'params' must be a mapping, got {type(self.params).__name__}")
        if self.artifact is not None:
            object.__setattr__(self, "artifact", assert_safe_relpath(self.artifact))
        elif self.check not in ARTIFACTLESS_CHECKS:
            raise ValueError(f"done_when criterion {self.check!r} requires an 'artifact' path")
```

`decompose_agent/node.py:102-112` — Entity `Node`: có `id`, frozen, sở hữu `tuple[DoneWhen]`:

```python
@dataclass(frozen=True)
class Node:
    """One unit of work on disk. Frozen — status transitions go through dataclasses.replace
    (the Navigator owns the tree; nothing else mutates a node)."""

    id: str
    parent: str | None = None
    kind: str = "work"
    status: str = "pending"
    depends_on: tuple[str, ...] = ()
    done_when: tuple[DoneWhen, ...] = ()
```

`decompose_agent/node.py:75-81` — chống "verdict forgery" trong `DoneWhen.from_dict`:

```python
extra = set(raw) - _CRITERION_KEYS
forged = extra & FORBIDDEN_VERDICT_KEYS
if forged:
    raise ValueError(
        f"done_when criterion must not carry a verdict field {sorted(forged)} — "
        "the gate writes the verdict, not the author"
    )
```

---

## 3. Bảng ánh xạ vai trò pattern ↔ code thật

| Vai trò Lesson 36 | Thành phần code thật | Đặc điểm xác nhận |
|---|---|---|
| **Value Object** | `DoneWhen` (`node.py:50-99`) | frozen; không identity; không lifecycle; equality by `{check, params, artifact}`; validate (kể cả path-jail) ở `__post_init__` |
| **Entity** | `Node` (`node.py:102-176`) | có `id` (`node.py:107`); lifecycle `pending→active→done` qua `status` (`node.py:28`); frozen + tiến hoá bằng `dataclasses.replace()` (`node.py:104-105`); validate invariant ở `__post_init__` |
| **Entity sở hữu VO** | `Node.done_when: tuple[DoneWhen, ...]` (`node.py:112`, `node.py:131`) | Entity chứa một tuple các Value Object; `__post_init__` kiểm `all(isinstance(c, DoneWhen) ...)` |
| **VO defensive validation** | `assert_safe_relpath()` (`node.py:33-47`) | từ chối absolute / `~` / `..` ngay khi construct VO |
| **Tiến hoá bất biến** | `dataclasses.replace()` | "status transitions go through dataclasses.replace" (`node.py:104-105`) |

> Ghi chú trung thực: trong code thật `Node` là `@dataclass(frozen=True)` nên `__eq__` mặc định so theo **mọi field**. Bản distill làm rõ đặc điểm Entity của Lesson 36 bằng cách override `__eq__/__hash__` để **equality theo `id`** — đúng định nghĩa Entity. Đây là điểm nhấn dạy học được nêu rõ trong docstring file `.py`.

---

## 4. Bản rút gọn chạy được

File: [`node_donewhen_value_objects.py`](./node_donewhen_value_objects.py) — chạy `python3 node_donewhen_value_objects.py`.

**Mô phỏng đúng:** giữ `DoneWhen` (frozen VO + validate + path-jail + chống verdict-forgery trong `from_dict`) và `Node` (Entity có id, lifecycle, sở hữu tuple DoneWhen, tiến hoá qua `replace()`). 8 bước demo chứng minh: VO equality by attribute; Entity equality by id (không theo attribute); lifecycle qua `replace()` giữ nguyên id; frozen chặn gán trực tiếp; path-jail; chống verdict-forgery; và **đối chứng** Entity so sánh theo attribute khiến cache đè nhầm.

**Lược bỏ:** toàn bộ tầng gate/runner/filesystem (`gates.py`); các field `reduce_op`/`inputs`/`depth`/`order`/`activated_at`; `from_dict` đầy đủ của `Node`. Phần `assert_safe_relpath` được giữ vì nó là điểm dạy học về VO defensive validation.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Entity tốn chi phí identity.** Phải sinh/quản lý `id`, đảm bảo unique, equality + hash theo id. Với object < 5 field không có vòng đời → dùng VO đơn giản, đừng nhồi id.
- **Frozen + replace() tốn allocation.** Mỗi chuyển trạng thái tạo một instance mới. Với cây node lớn cập nhật rất thường xuyên, cân nhắc Entity mutable thực sự (vd `KernelSession` trong `core/session.py:49-102` là `@dataclass` không frozen).
- **Đừng biến mọi thứ thành Entity.** Nếu `DoneWhen` có id riêng + lifecycle riêng, nó sẽ vỡ nguyên tắc "tiêu chí là câu hỏi bất biến". Nó **đúng** là VO: replace cả tiêu chí, không sửa.
- **Override `__eq__` theo id cần kèm `__hash__`.** Nếu chỉ override một trong hai, Entity sẽ hành xử sai trong set/dict.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `Node` là Entity còn `DoneWhen` là Value Object, dù cả hai đều là `@dataclass(frozen=True)`? (Gợi ý: hỏi "identity có quan trọng không?" và "có lifecycle không?" theo decision tree mục 1.3 của Lesson 36.)
2. `Node` frozen nhưng vẫn "đổi trạng thái" được. Cơ chế nào cho phép điều đó, và vì sao nó vẫn giữ được tính bất biến của bản gốc?
3. Nếu một worker gửi criterion `{"check": "file_exists", "artifact": "out/x.md", "passed": true}`, điều gì xảy ra và tại sao thiết kế lại từ chối field `passed`? Liên hệ với nguyên tắc "Event/criterion không tự chấm verdict".
