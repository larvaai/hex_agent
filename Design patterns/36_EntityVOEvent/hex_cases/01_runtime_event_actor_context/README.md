# Case 01 — RuntimeEvent + Actor + TraceContext (Domain Event + composite Value Objects)

> Flagship của Lesson 36 trong hex_agent: một event control-plane **thật, đang chạy production** cho thấy CẢ BA building block DDD (Domain Event, Value Object) làm việc cùng nhau trong một contract.

---

## 1. Bối cảnh trong hex_agent — vấn đề thật

Control plane của hex_agent cần MỘT định dạng event duy nhất để UI, audit, replay và mọi sink đọc cùng một shape. File `control/events.py` (đã mở kiểm chứng) định nghĩa contract đó. Hai vấn đề thật mà nó giải:

1. **Event đã phát thì không được sửa.** Một event đi tới nhiều sink (SSE, audit log, replay). Nếu một sink mutate được event, các sink khác đọc dữ liệu sai — đúng "Vi phạm C" của Lesson 36 (Event với mutable field). Giải pháp: `@dataclass(frozen=True)` + payload metadata bất biến (`redacted_fields` là `tuple`, không `list`).
2. **Event sai KHÔNG được tồn tại.** Docstring của file ghi rõ: *"Validation runs in `__post_init__` so an invalid event can never exist (let alone be published)"* (`control/events.py:5-6`). Đây chính là "validate at construction" của VO/Event trong Lesson 36.

Ngữ cảnh "ai gây ra event" và "đường truy vết" không phải là thực thể có vòng đời — chúng là **giá trị mô tả**, nên được mô hình hoá thành Value Object: `Actor`, `TraceContext`, `RedactionInfo`.

File:line thật:
- `control/events.py:32-50` — `Actor` (Value Object)
- `control/events.py:53-82` — `TraceContext` (Value Object, có `child()` side-effect-free)
- `control/events.py:85-110` — `RedactionInfo` (Value Object, dùng `tuple`)
- `control/events.py:113-190` — `RuntimeEvent` (Domain Event)

---

## 2. Trích đoạn code thật

`control/events.py:32-43` — Value Object `Actor` với validate ở constructor:

```python
@dataclass(frozen=True)
class Actor:
    type: str
    id: str

    def __post_init__(self) -> None:
        if self.type not in ACTOR_TYPES:
            raise ControlContractError(
                f"Actor.type must be one of {sorted(ACTOR_TYPES)}, got {self.type!r}."
            )
        if not self.id:
            raise ControlContractError("Actor.id must be non-empty.")
```

`control/events.py:113-145` — Domain Event `RuntimeEvent` (event_id/created_at auto, schema_version, validate):

```python
@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    session_id: str
    actor: Actor
    trace: TraceContext
    redaction: RedactionInfo
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=utc_now)
    schema_version: int = 1
    seq: int = 0
    ...
    def __post_init__(self) -> None:
        for name in ("event_id", "event_type", "session_id", "created_at", "source"):
            if not getattr(self, name):
                raise ControlContractError(f"RuntimeEvent.{name} is required and must be non-empty.")
        if not isinstance(self.actor, Actor):
            raise ControlContractError("RuntimeEvent.actor must be an Actor.")
        ...
        if self.schema_version < 1:
            raise ControlContractError("RuntimeEvent.schema_version must be >= 1.")
```

`control/events.py:80-82` — `TraceContext.child()` side-effect-free (đặc trưng VO):

```python
def child(self) -> "TraceContext":
    """A child span sharing this trace, parented to the current span."""
    return TraceContext(trace_id=self.trace_id, span_id=uuid.uuid4().hex, parent_span_id=self.span_id)
```

---

## 3. Bảng ánh xạ vai trò pattern ↔ code thật

| Vai trò Lesson 36 | Thành phần code thật | Đặc điểm xác nhận |
|---|---|---|
| **Domain Event** | `RuntimeEvent` (`events.py:113-190`) | frozen; `event_id` (idempotency); `created_at` (timestamp); `schema_version` (versioning); past-tense `event_type` như `"task.completed"`; broadcast tới nhiều sink |
| **Value Object** | `Actor` (`events.py:32-50`) | frozen; không identity; equality by attribute; validate `type ∈ ACTOR_TYPES` ở `__post_init__` |
| **Value Object** | `TraceContext` (`events.py:53-82`) | frozen; `child()` trả VO mới (side-effect-free); validate `trace_id`/`span_id` non-empty |
| **Value Object** | `RedactionInfo` (`events.py:85-110`) | frozen; `redacted_fields: tuple` (không list) → immutable thực sự |
| **Validate-at-construction** | `__post_init__` ở cả 4 class | "an invalid event can never exist" (`events.py:5-6`) |
| **Public schema versioned** | `schema_version` + `as_dict`/`from_dict` | round-trip ổn định cho replay (Lesson 31/34) |

---

## 4. Bản rút gọn chạy được

File: [`runtime_event_actor_context.py`](./runtime_event_actor_context.py) — chạy `python3 runtime_event_actor_context.py`.

**Mô phỏng đúng:** giữ nguyên 4 dataclass (`Actor`, `TraceContext`, `RedactionInfo`, `RuntimeEvent`) với cùng field cốt lõi, cùng `__post_init__` validate, cùng `event_id`/`created_at`/`schema_version`, cùng `as_dict`/`from_dict` round-trip, cùng `child()` side-effect-free. 8 bước demo chứng minh: VO equality by attribute, event_id+timestamp tự sinh, round-trip bảo toàn, frozen chặn mutate, validate-at-construction, versioning, và một **đối chứng** event mutable bị consumer này mutate khiến consumer kia đọc sai.

**Lược bỏ:** `ControlContractError` → `ValueError` (cùng vai trò); `ui_payload`/Redactor/SSE gateway; `SessionSeq` thread-safe allocator; `threading`. Những thứ này là hạ tầng, không thay đổi bản chất pattern.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Immutability có giá ghi.** Mỗi lần "đổi" một VO phải tạo instance mới (vd `trace.child()`). Với object đổi liên tục theo thời gian + cần identity bền vững → đó là **Entity**, không phải Event/VO (xem Case 02).
- **Domain Event ≠ Command.** `RuntimeEvent` là "đã xảy ra". Nếu bạn cần một phản hồi đồng bộ "hãy làm X" thì đó là Command (`RuntimeCommand` trong `control/commands.py`), không phải Event — Lesson 36 phân biệt rõ.
- **Validate-at-construction chỉ hợp khi không cần I/O.** `Actor`/`TraceContext` validate được vì chỉ kiểm tra in-memory. Nếu việc validate cần gọi DB/network thì không nên nhồi vào VO — đó là việc của Domain Service.
- **Boilerplate.** Với object < 5 field không có invariant, frozen dataclass + `as_dict`/`from_dict` có thể là overkill.

---

## 6. Câu hỏi tự kiểm tra

1. `RuntimeEvent` có `event_id`. Vậy nó có phải là Entity không? (Gợi ý: `event_id` dùng để **dedup/idempotency**, không phải để "thread of continuity" — đọc lại bảng 3×3 của Lesson 36 về vai trò của event_id.)
2. Vì sao `RedactionInfo.redacted_fields` là `tuple` chứ không `list`? Điều gì hỏng nếu đổi sang `list` trong một `@dataclass(frozen=True)`?
3. `TraceContext.child()` trả về instance mới thay vì sửa `self`. Nếu một VO có method mutate `self`, nó vi phạm đặc điểm nào của Value Object, và bug thực tế nào sẽ phát sinh khi nhiều nơi cùng giữ một tham chiếu VO đó?
