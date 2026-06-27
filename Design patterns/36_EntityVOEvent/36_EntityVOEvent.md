# Lesson 36 — Entity vs Value Object vs Domain Event
## Neuron / Molecule / Action Potential — 3 loại "đối tượng" trong não tương ứng 3 building block của DDD tactical.

---

## TÓM TẮT MỘT DÒNG

**Entity** có *identity* bền vững, mutable, equality theo ID. **Value Object** không có identity, immutable, equality theo attribute. **Domain Event** là *fact đã xảy ra*, immutable, timestamped, broadcast. 3 loại này là *building block* cấu thành mọi aggregate (Lesson 35). Chọn sai = data corruption hoặc design phình to.

> **Neuron** là Entity — một neuron cụ thể trong não bạn có vị trí, ID (nếu ta đánh số), persist qua đời, mutable state (firing rate, synaptic weights thay đổi liên tục bởi LTP/LTD). Hai neuron ở 2 vị trí khác = 2 entity khác, dù cùng loại. **Phân tử dopamine** là Value Object — không có identity, 1 phân tử C₈H₁₁NO₂ ↔ 1 phân tử C₈H₁₁NO₂ khác hoàn toàn interchangeable, immutable (cấu trúc hoá học không đổi), equality theo "structure" (chemical formula). **Action potential** là Domain Event — past-tense fact ("voltage threshold crossed at t=T"), immutable (đã fire không bao giờ "unfire"), timestamped, broadcast tới mọi terminal arborize, có thể carry payload (rate code, temporal code, population code). 3 building block của não = 3 building block của DDD code.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Sau Lesson 35 bạn có Aggregate với private state, public method, invariant. Câu hỏi tiếp theo: *mỗi field trong aggregate nên là gì?* — class với ID? class immutable? hay đơn giản là tuple?

5 sai lầm phổ biến khi không phân biệt rõ:

1. **Mọi thứ thành Entity**: `Money(amount, currency)` được implement với ID. Equality theo ID. Hai `Money(10, USD)` không bằng nhau vì khác ID. → Bug ngay khi compare giá tiền.

2. **Mọi thứ thành VO**: `User(email, name)` immutable. Đổi email = tạo User mới. → ID liên kết của User mất ý nghĩa; foreign key vỡ.

3. **Event với mutable field**: `OrderPlaced(order_id)`. Sau publish, consumer A mutate `event.processed_by = "service1"`. Consumer B đọc event đã bị thay đổi.

4. **VO không validate ở constructor**: `Email("not-an-email")` chấp nhận. Lan rộng. Phát hiện ở DB save sau 3 service.

5. **Entity bị treat như VO**: 2 `Order` cùng `total_amount` được xem là "equal" → merge sai trong cache.

Lesson 36 đóng tất cả bằng *3 phân loại rõ + decision tree*.

### 1.2. Định nghĩa nghiêm ngặt

**(a) Entity** (Evans 2003):

> *"An object that is not fundamentally defined by its attributes, but rather by a thread of continuity and identity."*

5 đặc điểm:
- Có **identity** unique (UUID, surrogate key, hoặc natural key).
- **Mutable** state — field thay đổi qua thời gian.
- **Equality theo ID**, không theo attribute.
- Có **lifecycle**: created → modified → archived/deleted.
- Tham chiếu **bằng object reference** (trong cùng aggregate) hoặc **bằng ID** (cross-aggregate).

```python
@dataclass
class User:                              # Entity
    user_id: UserId                      # IDENTITY
    email: str
    name: str
    def change_email(self, new): self.email = new          # MUTABLE

u1 = User(UserId("u1"), "a@x", "Alice")
u2 = User(UserId("u1"), "a@x", "Alice")
assert u1 == u2     # ✓ same ID

u3 = User(UserId("u2"), "a@x", "Alice")
assert u1 != u3     # ✓ different ID, even same attributes
```

**(b) Value Object** (Evans 2003):

> *"An object that describes some characteristic or attribute but carries no concept of identity."*

5 đặc điểm:
- **No identity**.
- **Immutable** (frozen).
- **Equality theo attribute** — 2 VO cùng attribute là 1.
- **No lifecycle** — replace, not modify.
- **Side-effect-free methods** — `money.add(other)` returns *new Money*, không mutate self.

```python
@dataclass(frozen=True)
class Money:                             # VO
    amount: Decimal
    currency: str
    def __post_init__(self):             # validate at construction
        if self.amount < 0: raise ValueError(...)
        if self.currency not in ("USD","EUR","VND"): raise ValueError(...)
    def add(self, other):                # side-effect-free
        if self.currency != other.currency: raise ...
        return Money(self.amount + other.amount, self.currency)

m1 = Money(Decimal("10"), "USD")
m2 = Money(Decimal("10"), "USD")
assert m1 == m2      # ✓ same attribute
m3 = m1.add(m2)
assert m1 == Money(Decimal("10"), "USD")  # ✓ m1 unchanged
assert m3 == Money(Decimal("20"), "USD")  # ✓ new VO
```

**(c) Domain Event** (Evans 2003, expanded by Vernon):

> *"Captures the memory of something interesting which affects the domain."*

5 đặc điểm:
- **Past-tense** name (`OrderPlaced`, không `PlaceOrder`).
- **Immutable** (frozen).
- **Timestamped** (`occurred_at: datetime`).
- Có **event_id** UUID (cho idempotency).
- **Public schema** — versioned (Lesson 31, 34).

```python
@dataclass(frozen=True)
class OrderPlaced:                       # Domain Event
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)
    schema_version: int = 1
    # Payload
    order_id: OrderId = OrderId("")
    customer_id: UserId = UserId("")
    total: Money = Money(Decimal("0"), "USD")
```

### 1.3. Decision tree — chọn cái nào?

```
Câu hỏi 1: Identity có quan trọng không?
   "Cùng attribute nhưng 2 instance phải tách biệt?"
   ├─ CÓ → có thể là Entity. Tiếp tục câu hỏi 2.
   └─ KHÔNG → có thể là VO hoặc Event. Tiếp tục câu hỏi 3.

Câu hỏi 2: Có lifecycle (created → modified → archived)?
   ├─ CÓ → ENTITY
   └─ KHÔNG → Hỏi lại "Identity có thực sự cần?" — nếu vẫn cần thì Entity với immutable

Câu hỏi 3: Mô tả "là cái gì" hay "đã xảy ra"?
   ├─ "là cái gì" (snapshot, value) → VALUE OBJECT
   └─ "đã xảy ra" (fact at time T) → DOMAIN EVENT

Câu hỏi 4 (cho VO): Validate ở constructor được không?
   ├─ CÓ → VO chính tắc với __post_init__
   └─ KHÔNG (cần I/O để validate) → có thể không nên là VO; cân nhắc Entity hoặc Domain Service

Câu hỏi 5 (cho Event): Có thể được publish multiple times an toàn?
   ├─ CÓ (idempotent consumer) → Event chính tắc
   └─ KHÔNG → cần Command, không phải Event
```

### 1.4. Neuroscience — 3 building block của não

Tiến hoá đã chia "đối tượng" trong não thành 3 loại cơ bản, tương ứng chính xác 3 building block DDD:

**(a) Neuron = Entity**

| Đặc điểm | Neuron | Entity |
|----------|--------|--------|
| Identity | Vị trí + connection + lineage (development) | UUID / surrogate key |
| Mutable | Firing rate, synaptic weight (LTP/LTD), dendrite branch | Field thay đổi qua method |
| Equality | "Là neuron N42 trong CA1 trái" — không phải neuron khác cùng loại | By ID, không attribute |
| Lifecycle | Birth (neurogenesis) → maturation → potentially death (apoptosis) | Created → modified → archived |
| Reference | Synapse trỏ tới *specific* neuron (axon target) | Foreign key bằng ID |

Ship-of-Theseus: trong 1 neuron, qua thời gian tất cả protein được thay (turnover ~6 tháng), nhưng *neuron vẫn là neuron đó*. Identity continuity > attribute identity. Đó là Entity.

**(b) Neurotransmitter molecule = Value Object**

| Đặc điểm | Phân tử dopamine | Value Object |
|----------|------------------|--------------|
| Identity | KHÔNG — 1 phân tử C₈H₁₁NO₂ ≡ 1 phân tử C₈H₁₁NO₂ khác | KHÔNG |
| Immutable | Cấu trúc hoá học không đổi (cho đến khi degraded) | `@dataclass(frozen=True)` |
| Equality | By chemical structure | By attribute |
| Lifecycle | Synthesized → released → bound → degraded (nhưng molecule "another" thay thế) | Replace, not modify |
| Replacement | Tái tổng hợp ra phân tử "mới" hoàn toàn equivalent | `new_money = old_money.add(...)` |

Khi neuron release 1000 phân tử dopamine, không ai care "phân tử thứ 47" — tất cả interchangeable. Đó là VO.

**(c) Action potential = Domain Event**

| Đặc điểm | Spike (AP) | Domain Event |
|----------|-----------|--------------|
| Past tense | "Voltage threshold crossed at t=T" — đã fire | "OrderPlaced", past tense |
| Immutable | AP đã fire không thể "unfire" hoặc thay đổi | Frozen |
| Timestamped | Có thời điểm cụ thể (đến µs) | `occurred_at` |
| Broadcast | Tới mọi synapse axon arborize | Pub-sub |
| Payload | Rate code, temporal code, population code | Event field carries data |
| Versioning | Action potential có "spike width" thay đổi (myelination, drug) — analog với schema evolution | `schema_version` |

Khác nhau quan trọng: AP **không phải là một object** — nó là một *fact in time*. Bạn không thể "hold an AP" — chỉ có thể *quan sát* nó. Event cũng vậy: không phải state, là *memory of state change*.

**(d) Synapse — tricky case**

Synapse có ID (specific position: pre-neuron A + post-neuron B + spine location) nhưng cũng có thể view như "snapshot weight + neurotransmitter type". Trong não, synapse được treat như **Entity** (có lifecycle: formation, maturation, pruning).

Tương đương trong DDD: nếu object có thuộc tính của cả 2 → ưu tiên Entity nếu cần track *change history*; ưu tiên VO nếu cần *replace as a whole*.

### 1.5. So sánh với patterns đã học

| | Trace lại từ lesson | Lesson 36 view |
|---|---|---|
| Lesson 19 Observer | Pub-sub object | Subject là Entity, Observer là Entity, notification là Domain Event-like |
| Lesson 31 EDA | Event bus | Mọi event đã là Domain Event |
| Lesson 32 CQRS+ES | Event Sourcing | Event store là sequence of Domain Events |
| Lesson 35 Aggregate | AR private state | Aggregate Root là Entity; internal VOs; emit Domain Events |
| Lesson 36 (đây) | — | Định nghĩa rõ 3 loại, decision tree |

---

## MỨC 2 — CẤU TRÚC

### 2.1. Entity — design checklist

```python
class User:                              # AR or internal entity
    # 1. Identity (FIRST FIELD)
    user_id: UserId                      # NewType / VO ID

    # 2. Private state, public method
    _email: str
    _name: str

    # 3. Equality by ID, not by attribute
    def __eq__(self, other):
        return isinstance(other, User) and self.user_id == other.user_id
    def __hash__(self):
        return hash(self.user_id)

    # 4. Mutation only via method (Tell-don't-ask, Lesson 35)
    def change_email(self, new: Email):
        self._email = new.value
        # emit event

    # 5. Lifecycle (created via factory, archived via method)
    @staticmethod
    def register(email: Email, name: str) -> "User":
        return User(user_id=UserId(uuid.uuid4()), _email=email.value, _name=name)
```

### 2.2. Value Object — design checklist

```python
@dataclass(frozen=True)                  # 1. Immutable
class Money:
    # 2. Attribute-based (positional or named)
    amount: Decimal
    currency: str

    # 3. Validate at construction
    def __post_init__(self):
        if self.amount < 0: raise ValueError("non-negative")
        if self.currency not in {"USD","EUR","VND"}: raise ValueError("currency")

    # 4. Side-effect-free methods (derive new VO)
    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency: raise ValueError("currency mismatch")
        return Money(self.amount + other.amount, self.currency)

    def with_currency(self, c: str) -> "Money":
        return Money(self.amount, c)     # convention "with_*" for derivation

    # 5. __eq__ và __hash__ auto từ frozen=True
```

Quy tắc nhỏ:
- **Naming**: ưu tiên tên *concept business* (`Money`, `Email`, `Address`), không kỹ thuật (`StringWrapper`, `IntValue`).
- **Reuse across context**: cùng `Money` có thể dùng trong Billing và Refund — đó là VO chia sẻ; nhưng nếu semantic khác (Billing.Money vs Tax.Money với rule khác), tách 2 VO.

### 2.3. Domain Event — design checklist

```python
@dataclass(frozen=True)                  # 1. Immutable
class OrderPlaced:
    # 2. Meta fields (event_id, occurred_at, schema_version)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)
    schema_version: int = 1

    # 3. Payload (data the consumer needs)
    order_id: OrderId = OrderId("")
    customer_id: UserId = UserId("")
    total: Money = field(default_factory=lambda: Money(Decimal("0"), "USD"))

    # 4. Naming: past-tense business fact
    # GOOD: OrderPlaced, PaymentReceived, ShipmentDispatched
    # BAD:  PlaceOrder (command), OrderInfo (data), OrderEvent (vague)
```

### 2.4. Bốn invariants

1. **Entity equality by ID** — never by attribute.
2. **VO immutability strict** — `frozen=True` + no internal mutable container.
3. **Event past-tense + carries enough payload** — consumer không cần callback producer.
4. **Each has clear ownership** — Entity owns its state; VO is owned by Entity; Event is published by Entity, owned by no one (consumed by N).

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
# === VALUE OBJECTS ===
@frozen Money       (amount, currency)              + validate + add() + with_currency()
@frozen Email       (value)                         + validate format
@frozen PhoneNumber (value)                         + normalize "+84..."
@frozen DateRange   (start, end)                    + invariant start <= end + duration()
@frozen Percentage  (value)                         + invariant 0 <= value <= 1
@frozen Coordinate  (lat, lng)                      + distance_to()
@frozen Score       (points, max_points)            (Lesson 35)

# === ENTITIES ===
class User                                          # AR
    id, email: Email, name, _registered_at
    change_email(new) → emit EmailChanged
    rename(new)        → emit Renamed

class Order                                         # AR
    id, customer_id, _items: List[LineItem], _status
    add_item(line), submit() → emit OrderPlaced
    cancel() → emit OrderCancelled

# LineItem: trong Order, không có lifecycle riêng → VO
@frozen LineItem (product_id, quantity, unit_price: Money)
    + total() → Money

# === DOMAIN EVENTS ===
@frozen UserRegistered    (user_id, email, occurred_at)
@frozen EmailChanged      (user_id, old_email, new_email, occurred_at)
@frozen OrderPlaced       (order_id, customer_id, total, items, occurred_at)
@frozen OrderCancelled    (order_id, reason, occurred_at)

# Versioning
@frozen OrderPlacedV1     (order_id, customer_id, total, items)
@frozen OrderPlacedV2     (order_id, customer_id, total, items, channel="web")  # additive

# === DECISION TREE in code ===
def classify(obj):
    has_id        = hasattr(obj, "id") or hasattr(obj, "_id")
    is_frozen     = getattr(obj.__class__, "__dataclass_params__", None) and obj.__class__.__dataclass_params__.frozen
    name_past_tense = is_past_tense(obj.__class__.__name__)
    if name_past_tense and is_frozen: return "EVENT"
    if has_id and not is_frozen:      return "ENTITY"
    if is_frozen and not has_id:      return "VALUE_OBJECT"
    return "AMBIGUOUS"
```

### 3.2. Bảng 3x3 cheat-sheet

|  | **Identity** | **Mutability** | **Equality** | **Lifecycle** | **Past/Future** |
|---|---|---|---|---|---|
| **Entity** | YES | mutable | by ID | YES | timeless (current state) |
| **Value Object** | NO | immutable | by attribute | NO | timeless (snapshot) |
| **Domain Event** | event_id (for dedup) | immutable | by event_id | NO (consumed N times) | PAST |

Mọi quyết định quy về dòng nào fit.

### 3.3. Common confusions decision

| Object | Verdict | Tại sao |
|--------|---------|---------|
| **Money** | VO | Không identity. $10 USD == $10 USD bất kể instance |
| **Email** | VO | Defined by string + format |
| **PhoneNumber** | VO | Normalize ở constructor |
| **Address** | VO (thường) | Snapshot of "where". Entity nếu cần track history riêng |
| **DateRange** | VO | Invariant: start < end |
| **OrderLineItem** | VO (thường, trong Order) | Replace cả Order khi đổi qty. Entity nếu cần ID/lifecycle riêng |
| **User** | Entity | ID bền vững; mutable (change email, name) |
| **Order** | Entity (AR) | ID bền vững; lifecycle (placed → fulfilled → archived) |
| **Product** | Entity | Catalog item, persist với SKU |
| **Score** | VO | Snapshot điểm |
| **AccountBalance** | VO inside Entity | Account = Entity; balance = VO snapshot |
| **Coordinate** | VO | (lat, lng) point in space |
| **Color** | VO | RGB or hex |
| **Currency** | VO | "USD" — identifier |
| **OrderPlaced** | Event | Past tense, time-stamped fact |
| **OrderPlaceCommand** | Command (≠ Event) | Imperative, request to do |

> Quy tắc nhanh: nếu mô tả "**X is Y**" (X *là* gì) → VO. Nếu mô tả "**X has happened**" (X *đã* xảy ra) → Event. Nếu mô tả "**X exists with id Z**" → Entity.

---

## NĂM CHIỀU SO SÁNH (trong não vs trong code)

| Chiều | Neuron / Entity | Molecule / VO | AP / Event |
|-------|------------------|---------------|-------------|
| **Cấu tạo** | Cell body + dendrites + axon + synapses | C₈H₁₁NO₂ (dopamine) — phân tử bền vững | Voltage waveform: depol → repol → hyperpolar |
| **Vị trí** | Cố định trong não (CA1, V1...) | Khắp synaptic cleft (interchangeable) | Propagate dọc axon từ soma đến terminal |
| **Chức năng** | Tính toán + lưu trữ; identity persist | Carry signal *value* giữa neuron | Phát signal *fact* "đã có spike tại T" |
| **Kết nối** | Synapse tới neuron khác (object ref) | Bind receptor (VO consume bởi entity) | Broadcast tới mọi terminal arborize |
| **Ý nghĩa** | Object có identity = Entity | Replaceable signal carrier = VO | Time-stamped fact = Event |

---

## BA VÍ DỤ

### Ví dụ 1 — Vận hành thường (happy path)

Domain Ellumm subscription:

```python
# Value Objects
email = Email("alice@ellumm.com")
phone = PhoneNumber("+84 90 123 4567")     # normalize → "+84901234567"
subscription_period = DateRange(start, end)
monthly_fee = Money(Decimal("9.99"), "USD")

# Entity
user = User.register(email, "Alice")       # creates with new ID
user.change_email(Email("alice@new.com"))  # mutate (event: EmailChanged)

# Domain Event
event = UserRegistered(
    user_id=user.id,
    email_value=email.value,
)
event_bus.publish(event)
# Later: Notification context subscribes UserRegistered → send welcome email
```

Mỗi loại object có *vai trò rõ*. Test pure, không nhầm lẫn.

### Ví dụ 2 — Hỏng / vi phạm

**Vi phạm A — Mutable VO**:
```python
# BAD
class Money:                              # không frozen
    def __init__(self, amount, currency):
        self.amount = amount
        self.currency = currency

m = Money(10, "USD")
m.amount = 99999                          # ✗ mutate VO
# Bug: 1 m chia cho 2 service → 1 mutate → cả 2 thấy giá trị mới
```
→ Đúng: `@dataclass(frozen=True)`.

**Vi phạm B — Entity equality by attribute**:
```python
# BAD
@dataclass
class User:
    user_id: str
    email: str
    def __eq__(self, other):
        return self.email == other.email   # ✗ identity by attribute

u1 = User("u1", "a@x")
u2 = User("u2", "a@x")
assert u1 == u2                            # ✗ different users compared equal
# Bug: cache by email collision; foreign key vỡ
```
→ Đúng: equality by ID.

**Vi phạm C — Event với mutable field**:
```python
# BAD
@dataclass                                 # không frozen
class OrderPlaced:
    order_id: str
    items: List[str]                       # mutable list

evt = OrderPlaced("o1", ["a"])
consumer_A.process(evt)
evt.items.append("b")                      # ✗ mutate event
consumer_B.process(evt)                    # ← thấy ["a", "b"], không phải nguyên thuỷ
```
→ Đúng: frozen + tuple cho list.

**Vi phạm D — VO không validate**:
```python
# BAD
@dataclass(frozen=True)
class Email:
    value: str
    # ← không validate format

bad = Email("not-an-email")                # accepted!
user = User.register(bad, "Alice")
# Later: send email fails. Bug lan rộng.
```
→ Đúng: validate ở `__post_init__`.

**Vi phạm E — Future-tense event name**:
```python
# BAD
@dataclass(frozen=True)
class PlaceOrder:                          # ✗ imperative
    order_id: str

# Consumer phải làm gì? Cảm thấy có "command" nghĩa
```
→ Đúng: tên past-tense (`OrderPlaced`). Command bus dùng class riêng cho "PlaceOrder".

### Ví dụ 3 — Ứng dụng Ellumm

File `36_entity_vo_event.py` đi kèm với:
- **VO library**: `Money`, `Email`, `PhoneNumber`, `DateRange`, `Percentage`, `Coordinate`, `Score`.
- **Entity**: `User` (rich, with method to change email), `Order` (AR with line items as VO).
- **Domain Events**: `UserRegistered`, `EmailChanged`, `OrderPlaced` (V1 & V2 demo evolve), `OrderCancelled`.
- **Decision tree**: function `classify(obj) -> "ENTITY"|"VO"|"EVENT"` heuristic.
- **Demo**: 8 case + anti-pattern showcase.

---

## MỨC ARCHITECT — TRADE-OFFS & ANTI-PATTERNS

### Khi nào DÙNG mỗi loại

| Loại | Dùng khi |
|------|----------|
| **Entity** | Có ID bền vững; lifecycle (CRUD); 2 instance cùng attribute phải tách biệt |
| **VO** | Mô tả "là gì" (snapshot); interchangeable; replace > modify |
| **Domain Event** | "Đã xảy ra X tại T"; broadcast; consumer 0..N |

### Khi nào KHÔNG

| Loại | Tránh khi |
|------|-----------|
| Entity | Object < 5 field không có lifecycle (overhead boilerplate) |
| VO | Object cần I/O để construct/validate (ví dụ check DB) — đó là responsibility của Domain Service |
| Domain Event | Cần synchronous response (đó là Command, không Event) |

### Trade-offs

| Trục | Entity | VO | Event |
|------|--------|----|---|
| **Identity overhead** | ID generation, unique constraint | None | event_id for dedup |
| **Immutability** | mutable (need to manage) | immutable | immutable |
| **Reuse cross-context** | Hard (each context own own User) | Easy (Money valid everywhere) | Easy (Published Language) |
| **Test isolation** | Cần factory | Trivial (no setup) | Trivial |
| **Persistence** | Repository + ORM/event store | Inline trong Entity row | Event store |

### Anti-patterns thường thấy

| Anti-pattern | Mô tả | Phát hiện |
|--------------|-------|-----------|
| **Mutable VO** | Forget `frozen=True` | grep `class.*VO.*:` without `@dataclass(frozen=True)` |
| **Anemic VO** | VO chỉ container, không có method derivative | VO < 3 method |
| **Entity equality by attribute** | Override `__eq__` to compare fields | Two `User` with same data compared equal |
| **Event future-tense** | `PlaceOrder` thay vì `OrderPlaced` | grep event class names |
| **Event with mutable list** | `items: List` thay vì `Tuple` | grep `List[` in `@dataclass(frozen=True)` events |
| **VO with identity** | UUID trong VO field | UUID trong frozen dataclass |
| **Reused ID across contexts** | Cùng UUID dùng cho User trong 4 BC | Cross-context query với same ID expecting same object |
| **Event leak from entity** | Entity mutate but no event | State change without `_pending_events.append(...)` |
| **Stringly-typed ID** | `user_id: str` thay vì `UserId = NewType("UserId", str)` | Mixing up user_id/quiz_id silently |
| **Event without occurred_at** | Missing timestamp → cannot replay temporal | Event class without datetime |

### Checklist trước khi merge PR

- [ ] Mỗi class mới được tag rõ là **Entity / VO / Event** trong docstring?
- [ ] Entity có `__eq__` + `__hash__` by ID?
- [ ] VO là `@dataclass(frozen=True)`?
- [ ] VO validate ở `__post_init__` nếu có invariant?
- [ ] VO method side-effect-free (return new VO)?
- [ ] Event past-tense + frozen + có `event_id` + `occurred_at` + `schema_version`?
- [ ] Event payload là immutable (`Tuple` thay `List`)?
- [ ] ID dùng NewType / VO ID, không bare string?
- [ ] Cross-aggregate reference by ID, không object?

### So sánh 3 loại — bảng nhanh

| | Entity | VO | Event |
|---|---|---|---|
| **Identity** | UUID/key (bền vững) | None | event_id (dedup only) |
| **Mutability** | mutable via method | immutable | immutable |
| **Equality** | by ID | by attribute | by event_id |
| **Naming** | Noun (User, Order) | Noun describing value (Money, Email) | Past-tense (UserRegistered) |
| **Lifecycle** | created → modified → archived | replace whole | published once, consumed N |
| **Examples (Ellumm)** | Submission, User, Quiz | Score, Answer, Email, Money | SubmissionGraded, OrderPlaced |
| **Python** | class + private state + method | `@dataclass(frozen=True)` | `@dataclass(frozen=True)` past-tense |
| **Brain** | Neuron | Neurotransmitter molecule | Action potential |

### Subtle case: Identity vs Equality

Một misunderstanding phổ biến:
- **Identity** (Python `is`): cùng object trong memory.
- **Equality** (Python `==`): same value.
- **Domain identity**: cùng business identity (User u1).

VO: `m1 == m2` (equal), nhưng `m1 is m2` thường False (khác instance). Domain identity không applicable.
Entity: `u1 == u2` chỉ true khi cùng ID. `u1 is u2` chỉ true cùng instance.

3 layer độc lập. Lesson 36 chủ yếu về *domain identity*.

---

## BÀI TẬP — 4 MỨC

### Mức 1 — Cơ bản (45 phút)

Lấy 10 class sau, classify Entity / VO / Event và giải thích 1 câu mỗi cái:

1. `Money(amount, currency)`
2. `User(id, email, name)`
3. `OrderPlaced(order_id, total)`
4. `Coordinate(lat, lng)`
5. `Submission(id, user_id, score)`
6. `EmailAddress(value)`
7. `Quiz(quiz_id, title, questions)`
8. `Color(r, g, b)`
9. `PaymentRefunded(payment_id, amount)`
10. `Address(street, city, postal_code)`

(Trả lời ở cuối file `36_entity_vo_event.py`.)

### Mức 2 — Trung bình (1.5 giờ)

(a) Cho codebase Ellumm hiện có (Lesson 35), audit tất cả class. Cho mỗi class:
- Verdict (Entity/VO/Event/Other).
- Nếu sai → propose refactor.

(b) Implement `DateRange` VO với:
- Invariant `start < end`.
- Methods: `duration()`, `overlaps(other)`, `contains(date)`, `merge(other)` if adjacent.
- Test: 6 case (valid, invalid, overlap, no-overlap, adjacent merge, non-adjacent merge raise).

### Mức 3 — Khó (architect, 3 giờ)

(a) Implement schema evolution: `OrderPlacedV1 → V2 → V3` với rules:
- V2 thêm field `channel = "web"` (default).
- V3 đổi `Total` từ `float` sang `Money` (breaking? — cách handle).
- Viết Upcaster class chuyển V1 → V2 → V3 khi replay event store.
- Test: replay 100 events trộn V1/V2/V3.

(b) Identity scope across bounded context (Lesson 34): cùng `user_id="u1"` xuất hiện trong 4 BC. Mỗi BC có Entity User riêng với schema khác. Câu hỏi:
- Identity của "u1" là chia sẻ hay riêng từng BC?
- Implement `AuthACL` translate `Auth0User` → mỗi BC entity (đã thấy Lesson 34).
- Khi 1 BC change email, các BC khác có biết? Implement event `EmailChanged` propagation.

(c) Hard call: phân biệt `Attempt` (Lesson 35 internal entity) có nên là VO hay Entity?
- Argument cho Entity: có attempt_id, có submitted_at, có history.
- Argument cho VO: chỉ valid trong context Submission, replace cả Attempt khi grade.
- Quyết định + 200-word reflection.

### Mức 4 — Mở rộng neuro (2 giờ tự do)

Đọc 1 chương về *neural identity persistence* (Kandel *Principles* chương 4 hoặc *In Search of Memory*). Trả lời:

1. **Ship of Theseus neural**: tất cả protein trong neuron được turn over qua ~6 tháng. Vậy "memory" được lưu ở đâu? Hint: synaptic structure (spine + receptor count). Tương đương trong code: nếu mọi field của Entity đều thay đổi, ID có còn meaning không? Khi nào Entity *thật sự là cùng Entity*?

2. **Glutamate vs GABA**: 2 phân tử khác nhau, ảnh hưởng excitatory vs inhibitory. Đều VO. Nếu code có `Glutamate` và `GABA` cùng kế thừa từ `Neurotransmitter`, đó có là design tốt? Hay tạo 1 VO `Neurotransmitter(type, structure)`? So với 2 class riêng?

3. **AP propagation failure** (demyelination MS): AP đôi khi "fail to propagate" — fire ở soma nhưng terminal không nhận. Tương đương: domain event publish nhưng consumer không nhận (bus down, network partition). Bao nhiêu *"loss of AP"* là chấp nhận được? Code implication cho idempotency + retry?

---

## ĐỒ HOẠ TỔNG KẾT

```
        DDD TACTICAL — 3 BUILDING BLOCKS
   ═══════════════════════════════════════════════════════════
                ┌──────────────┐
                │   ENTITY     │  identity bền vững, mutable
                │              │  Neuron — cell N42 ở CA1
                │  User u1     │  equality by ID
                │  ──────────  │
                │  ↓ contains  │
                │  ┌────────┐  │
                │  │   VO   │  │  no identity, immutable
                │  │ Email  │  │  Neurotransmitter molecule
                │  │ Money  │  │  equality by attribute
                │  │ Score  │  │  validate at __post_init__
                │  └────────┘  │
                └──────┬───────┘
                       │ emits
                       ▼
                ┌──────────────┐
                │   EVENT      │  past-tense fact, immutable
                │              │  Action potential — spike at t=T
                │ OrderPlaced  │  broadcast, idempotent consumers
                │ EmailChanged │  versioned schema
                └──────────────┘

   Decision tree:
   - Identity quan trọng + lifecycle?       → Entity
   - "Là cái gì" + interchangeable?         → Value Object
   - "Đã xảy ra X tại T"?                   → Domain Event
```

> **Tóm lại**: 3 building block của DDD tactical = 3 building block của não. Neuron-Entity (identity), Molecule-VO (value), Spike-Event (fact). Phân loại đúng = aggregate dễ test, dễ scale, dễ refactor. Phân loại sai = boilerplate vô lý hoặc data corruption.

---

## TIẾP THEO

- **Lesson 37 — Repository + Factory + Specification**: 3 supporting pattern hoàn thiện aggregate.
- **Lesson 38 — Event Storming workshop**: discover bounded context + aggregate qua sticky note.
- **Lesson 39 — Distributed DDD**: cross-context consistency.
- **Lesson 40 — Ubiquitous Language case study**.
