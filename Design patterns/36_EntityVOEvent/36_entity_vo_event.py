"""
Lesson 36 — Entity vs Value Object vs Domain Event
====================================================

Catalog 3 building block của DDD tactical với code minh hoạ:
- Value Object library (Money, Email, PhoneNumber, DateRange, Percentage,
  Coordinate, Score) — frozen + validate + side-effect-free derivation.
- Entity (User, Order) — identity, mutable state, equality by ID.
- Domain Events (UserRegistered, EmailChanged, OrderPlaced V1/V2,
  OrderCancelled) — past-tense, immutable, versioned.
- Decision tree classifier `classify(obj)`.
- 9 demos minh hoạ từng khía cạnh + anti-pattern showcase.

Run: python 36_entity_vo_event.py
"""

from __future__ import annotations

import re
import math
import uuid
from dataclasses import dataclass, field, FrozenInstanceError, fields as dc_fields
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple, NewType, ClassVar


# =============================================================================
# [VALUE OBJECTS]   Frozen, validate at construction, side-effect-free methods
# =============================================================================

@dataclass(frozen=True)
class Money:
    """VO: amount + currency. Side-effect-free arithmetic."""
    amount: Decimal
    currency: str

    ALLOWED_CURRENCIES: ClassVar = frozenset({"USD", "EUR", "VND", "JPY"})

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            # Coerce — but use object.__setattr__ since frozen
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        if self.amount < 0:
            raise ValueError(f"Money.amount must be >= 0, got {self.amount}")
        if self.currency not in Money.ALLOWED_CURRENCIES:
            raise ValueError(f"unsupported currency {self.currency!r}")

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")
        return Money(self.amount + other.amount, self.currency)

    def subtract(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")
        return Money(self.amount - other.amount, self.currency)

    def multiply(self, factor: Decimal) -> "Money":
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"


@dataclass(frozen=True)
class Email:
    """VO: validated email address."""
    value: str

    _EMAIL_RE: ClassVar = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def __post_init__(self) -> None:
        if not Email._EMAIL_RE.match(self.value):
            raise ValueError(f"invalid email format: {self.value!r}")
        # Normalize to lower
        object.__setattr__(self, "value", self.value.lower())

    @property
    def domain(self) -> str:
        return self.value.split("@")[1]


@dataclass(frozen=True)
class PhoneNumber:
    """VO: E.164-style normalized phone."""
    value: str

    def __post_init__(self) -> None:
        # Strip everything except digits and leading +
        cleaned = re.sub(r"[^\d+]", "", self.value)
        if not cleaned.startswith("+"):
            raise ValueError(f"phone must start with country code +, got {self.value!r}")
        if len(cleaned) < 8 or len(cleaned) > 16:
            raise ValueError(f"phone length out of range: {cleaned}")
        object.__setattr__(self, "value", cleaned)


@dataclass(frozen=True)
class DateRange:
    """VO: [start, end] with start < end invariant."""
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(f"start {self.start} must be < end {self.end}")

    def duration(self) -> timedelta:
        return self.end - self.start

    def overlaps(self, other: "DateRange") -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, d: date) -> bool:
        return self.start <= d < self.end

    def merge(self, other: "DateRange") -> "DateRange":
        """Only valid if overlaps OR adjacent."""
        if not (self.overlaps(other) or self.end == other.start or other.end == self.start):
            raise ValueError("ranges are not overlapping or adjacent — cannot merge")
        return DateRange(min(self.start, other.start), max(self.end, other.end))


@dataclass(frozen=True)
class Percentage:
    """VO: 0 ≤ value ≤ 1."""
    value: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.value <= 1.0):
            raise ValueError(f"Percentage out of [0,1]: {self.value}")

    def as_basis_points(self) -> int:
        return int(self.value * 10_000)

    def apply_to(self, amount: Decimal) -> Decimal:
        return amount * Decimal(str(self.value))


@dataclass(frozen=True)
class Coordinate:
    """VO: lat/lng point on Earth."""
    lat: float
    lng: float

    def __post_init__(self) -> None:
        if not (-90 <= self.lat <= 90):
            raise ValueError(f"lat out of range: {self.lat}")
        if not (-180 <= self.lng <= 180):
            raise ValueError(f"lng out of range: {self.lng}")

    def distance_km(self, other: "Coordinate") -> float:
        """Haversine distance."""
        R = 6371.0
        lat1, lat2 = math.radians(self.lat), math.radians(other.lat)
        dlat = lat2 - lat1
        dlng = math.radians(other.lng - self.lng)
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
        return 2 * R * math.asin(math.sqrt(a))


# =============================================================================
# [STRONG IDs]   VO-like NewType for ID safety
# =============================================================================

UserId = NewType("UserId", str)
OrderId = NewType("OrderId", str)
ProductId = NewType("ProductId", str)


# =============================================================================
# [VALUE OBJECT — Order LineItem]   Inside Order aggregate, no own identity
# =============================================================================

@dataclass(frozen=True)
class LineItem:
    """VO: product + qty + unit price snapshot. Replace whole when qty change."""
    product_id: ProductId
    quantity: int
    unit_price: Money

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")

    def total(self) -> Money:
        return self.unit_price.multiply(Decimal(self.quantity))


# =============================================================================
# [ENTITY — User]   Identity, mutable, equality by ID
# =============================================================================

class User:
    """Entity: User. Equality by user_id; mutable state via methods."""

    def __init__(self, user_id: UserId, email: Email, name: str) -> None:
        self._user_id = user_id
        self._email = email
        self._name = name
        self._registered_at = datetime.now()
        self._pending_events: List[object] = []

    @staticmethod
    def register(email: Email, name: str) -> "User":
        """Factory: create User with new ID + emit UserRegistered."""
        u = User(UserId(str(uuid.uuid4())), email, name)
        u._pending_events.append(UserRegistered(
            user_id=u._user_id, email_value=email.value, name=name,
        ))
        return u

    # ---- Mutation methods ----
    def change_email(self, new: Email) -> None:
        if new == self._email:
            return
        old = self._email
        self._email = new
        self._pending_events.append(EmailChanged(
            user_id=self._user_id, old_email=old.value, new_email=new.value,
        ))

    def rename(self, new_name: str) -> None:
        self._name = new_name

    # ---- Read-only properties ----
    @property
    def user_id(self) -> UserId: return self._user_id

    @property
    def email(self) -> Email: return self._email

    @property
    def name(self) -> str: return self._name

    def collect_pending_events(self) -> Tuple[object, ...]:
        evts = tuple(self._pending_events)
        self._pending_events.clear()
        return evts

    # ---- Equality BY ID, not by attribute ----
    def __eq__(self, other: object) -> bool:
        return isinstance(other, User) and self._user_id == other._user_id

    def __hash__(self) -> int:
        return hash(self._user_id)

    def __repr__(self) -> str:
        return f"User(id={self._user_id!r}, email={self._email.value!r})"


# =============================================================================
# [ENTITY — Order Aggregate Root]   AR contains LineItem VOs
# =============================================================================

class OrderStatus:
    DRAFT = "DRAFT"
    PLACED = "PLACED"
    CANCELLED = "CANCELLED"


class Order:
    """Entity (AR): Order. Identity bền vững, lifecycle: DRAFT → PLACED → CANCELLED."""

    def __init__(self, order_id: OrderId, customer_id: UserId) -> None:
        self._order_id = order_id
        self._customer_id = customer_id
        self._items: List[LineItem] = []
        self._status = OrderStatus.DRAFT
        self._placed_at: Optional[datetime] = None
        self._pending_events: List[object] = []

    @staticmethod
    def start(customer_id: UserId) -> "Order":
        return Order(OrderId(str(uuid.uuid4())), customer_id)

    def add_item(self, item: LineItem) -> None:
        if self._status != OrderStatus.DRAFT:
            raise ValueError(f"cannot add item to {self._status} order")
        self._items.append(item)

    def total(self) -> Money:
        if not self._items:
            return Money(Decimal("0"), "USD")
        currency = self._items[0].unit_price.currency
        total = Money(Decimal("0"), currency)
        for item in self._items:
            total = total.add(item.total())
        return total

    def place(self) -> None:
        if self._status != OrderStatus.DRAFT:
            raise ValueError(f"cannot place {self._status} order")
        if not self._items:
            raise ValueError("cannot place empty order")
        self._status = OrderStatus.PLACED
        self._placed_at = datetime.now()
        self._pending_events.append(OrderPlacedV1(
            order_id=self._order_id,
            customer_id=self._customer_id,
            total=self.total(),
            item_count=len(self._items),
        ))

    def cancel(self, reason: str) -> None:
        if self._status != OrderStatus.PLACED:
            raise ValueError(f"can only cancel PLACED order, got {self._status}")
        self._status = OrderStatus.CANCELLED
        self._pending_events.append(OrderCancelled(
            order_id=self._order_id, reason=reason,
        ))

    # Properties
    @property
    def order_id(self) -> OrderId: return self._order_id

    @property
    def status(self) -> str: return self._status

    @property
    def item_count(self) -> int: return len(self._items)

    def collect_pending_events(self) -> Tuple[object, ...]:
        evts = tuple(self._pending_events)
        self._pending_events.clear()
        return evts

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Order) and self._order_id == other._order_id

    def __hash__(self) -> int:
        return hash(self._order_id)


# =============================================================================
# [DOMAIN EVENTS]   Past-tense, frozen, timestamped, versioned
# =============================================================================

@dataclass(frozen=True)
class UserRegistered:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)
    schema_version: int = 1
    user_id: UserId = UserId("")
    email_value: str = ""
    name: str = ""


@dataclass(frozen=True)
class EmailChanged:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)
    schema_version: int = 1
    user_id: UserId = UserId("")
    old_email: str = ""
    new_email: str = ""


@dataclass(frozen=True)
class OrderPlacedV1:
    """Schema V1."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)
    schema_version: int = 1
    order_id: OrderId = OrderId("")
    customer_id: UserId = UserId("")
    total: Money = field(default_factory=lambda: Money(Decimal("0"), "USD"))
    item_count: int = 0


@dataclass(frozen=True)
class OrderPlacedV2:
    """Schema V2: thêm `channel` (additive, backward-compatible)."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)
    schema_version: int = 2
    order_id: OrderId = OrderId("")
    customer_id: UserId = UserId("")
    total: Money = field(default_factory=lambda: Money(Decimal("0"), "USD"))
    item_count: int = 0
    channel: str = "web"                           # NEW in V2


@dataclass(frozen=True)
class OrderCancelled:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)
    schema_version: int = 1
    order_id: OrderId = OrderId("")
    reason: str = ""


# =============================================================================
# [DECISION TREE]   Heuristic classifier
# =============================================================================

PAST_TENSE_SUFFIXES = ("ed", "Placed", "Created", "Changed", "Cancelled",
                       "Registered", "Submitted", "Refunded", "Graded",
                       "Finalized", "Dispatched", "Sent")


def is_past_tense(name: str) -> bool:
    # Strip version suffix like "V1", "V2" before checking
    stripped = re.sub(r"V\d+$", "", name)
    return any(stripped.endswith(s) for s in PAST_TENSE_SUFFIXES)


def is_frozen_dataclass(cls) -> bool:
    params = getattr(cls, "__dataclass_params__", None)
    return params is not None and params.frozen


def has_id_field(cls) -> bool:
    # Inspect type hints + properties
    hints = getattr(cls, "__annotations__", {})
    for fname in hints:
        if fname.endswith("_id") or fname == "id":
            return True
    # Check for property `id` or `*_id`
    for attr in dir(cls):
        if attr.endswith("_id") or attr == "id":
            obj = getattr(cls, attr, None)
            if isinstance(obj, property):
                return True
    return False


def classify(cls) -> str:
    name = cls.__name__
    frozen = is_frozen_dataclass(cls)
    has_id = has_id_field(cls)
    past = is_past_tense(name)

    if past and frozen:
        return "DOMAIN_EVENT"
    if frozen and not past:
        return "VALUE_OBJECT"
    if not frozen and has_id:
        return "ENTITY"
    return "AMBIGUOUS"


# =============================================================================
# [DEMOS]
# =============================================================================

def banner(s: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {s}")
    print("=" * 76)


def demo_1_entity_vs_vo_identity() -> None:
    banner("DEMO 1 — Entity equality by ID vs VO equality by attribute")

    # ENTITY: same data, different IDs → NOT equal
    u1 = User(UserId("u1"), Email("alice@x.com"), "Alice")
    u2 = User(UserId("u2"), Email("alice@x.com"), "Alice")
    print(f"  u1: {u1}")
    print(f"  u2: {u2}")
    print(f"  Same email + name, different IDs → u1 == u2?  {u1 == u2}")
    assert u1 != u2     # different identity

    # ENTITY: same ID even if attributes differ → equal
    u1b = User(UserId("u1"), Email("alice@x.com"), "Alice Renamed")
    print(f"  u1b same ID, different name → u1 == u1b?       {u1 == u1b}")
    assert u1 == u1b    # identity wins

    # VALUE OBJECT: same attributes → equal
    m1 = Money(Decimal("10"), "USD")
    m2 = Money(Decimal("10"), "USD")
    print(f"  m1: {m1}, m2: {m2}, m1 == m2?                 {m1 == m2}")
    assert m1 == m2
    assert m1 is not m2     # different instances but equal value

    # VALUE OBJECT: different attribute → not equal
    m3 = Money(Decimal("10"), "EUR")
    print(f"  m3: {m3} (EUR), m1 == m3?                      {m1 == m3}")
    assert m1 != m3
    print("  PASS — Entity by ID, VO by attribute")


def demo_2_vo_immutability() -> None:
    banner("DEMO 2 — VO immutability: cannot mutate, must replace")

    m = Money(Decimal("10"), "USD")
    print(f"  Original: {m}")

    # Try mutation → raises FrozenInstanceError
    try:
        m.amount = Decimal("9999")
        print("  ERROR: mutation should have raised")
        assert False
    except FrozenInstanceError as e:
        print(f"  Mutation blocked: {type(e).__name__}: {e}")

    # Correct: derive new VO
    m2 = m.add(Money(Decimal("5"), "USD"))
    print(f"  After m.add(5): m={m} (unchanged), m2={m2}")
    assert m == Money(Decimal("10"), "USD")
    assert m2 == Money(Decimal("15"), "USD")
    assert m is not m2
    print("  PASS — VO is immutable; derive new VO via side-effect-free method")


def demo_3_vo_validation_at_construction() -> None:
    banner("DEMO 3 — VO validate at __post_init__")

    cases = [
        ("Money negative",        lambda: Money(Decimal("-1"), "USD")),
        ("Money invalid currency",lambda: Money(Decimal("1"), "XYZ")),
        ("Email malformed",       lambda: Email("not-an-email")),
        ("Email no domain",       lambda: Email("alice@")),
        ("PhoneNumber no country",lambda: PhoneNumber("90123456")),
        ("DateRange reversed",    lambda: DateRange(date(2026, 5, 11), date(2026, 5, 1))),
        ("Percentage out of [0,1]", lambda: Percentage(1.5)),
        ("Coordinate lat>90",     lambda: Coordinate(91.0, 0.0)),
        ("LineItem qty=0",        lambda: LineItem(ProductId("p"), 0, Money(Decimal("1"),"USD"))),
    ]
    for name, ctor in cases:
        try:
            ctor()
            print(f"  [FAIL] {name}: should have raised")
            raise AssertionError
        except ValueError as e:
            print(f"  [PASS] {name}: {str(e)[:60]}")
    print("  PASS — all VOs reject invalid input at construction")


def demo_4_vo_side_effect_free_methods() -> None:
    banner("DEMO 4 — VO side-effect-free methods derive new VOs")

    # Money arithmetic
    m1 = Money(Decimal("10"), "USD")
    m2 = Money(Decimal("3"), "USD")
    m3 = m1.add(m2).subtract(Money(Decimal("1"), "USD")).multiply(Decimal("2"))
    print(f"  m1 + m2 - 1 then *2:           {m3}")
    assert m3 == Money(Decimal("24"), "USD")

    # Currency mismatch → error
    try:
        m1.add(Money(Decimal("5"), "EUR"))
        assert False
    except ValueError as e:
        print(f"  Currency mismatch raised:       {str(e)[:60]}")

    # DateRange merge
    r1 = DateRange(date(2026, 1, 1), date(2026, 2, 1))
    r2 = DateRange(date(2026, 1, 20), date(2026, 3, 1))
    merged = r1.merge(r2)
    print(f"  r1.merge(r2):                  {merged.start} → {merged.end}")
    assert merged.start == date(2026, 1, 1) and merged.end == date(2026, 3, 1)

    # Coordinate distance
    saigon = Coordinate(10.7769, 106.7009)
    hanoi = Coordinate(21.0285, 105.8542)
    d = saigon.distance_km(hanoi)
    print(f"  Saigon ↔ Hanoi distance:       {d:.1f} km")
    assert 1100 < d < 1200
    print("  PASS — all derivation methods return new VO; original unchanged")


def demo_5_event_characteristics() -> None:
    banner("DEMO 5 — Domain Event: past-tense + frozen + timestamped + versioned")

    evt = OrderPlacedV1(
        order_id=OrderId("o42"),
        customer_id=UserId("u1"),
        total=Money(Decimal("99.99"), "USD"),
        item_count=3,
    )
    print(f"  Event: {evt}")
    print(f"  Class name past-tense?  {is_past_tense(type(evt).__name__)}")
    print(f"  Frozen?                 {is_frozen_dataclass(type(evt))}")
    print(f"  Has event_id?           {bool(evt.event_id)} (uuid)")
    print(f"  Has occurred_at?        {evt.occurred_at}")
    print(f"  Schema version:         {evt.schema_version}")

    # Try mutation
    try:
        evt.total = Money(Decimal("0"), "USD")
        assert False
    except FrozenInstanceError as e:
        print(f"  Mutation blocked:        {type(e).__name__}")

    assert is_past_tense("OrderPlacedV1")
    assert is_frozen_dataclass(OrderPlacedV1)
    print("  PASS — event meets all 5 characteristics")


def demo_6_event_versioning() -> None:
    banner("DEMO 6 — Event versioning: V1 vs V2 (additive backward-compatible)")

    v1 = OrderPlacedV1(
        order_id=OrderId("o1"), customer_id=UserId("u1"),
        total=Money(Decimal("50"), "USD"), item_count=2,
    )
    v2 = OrderPlacedV2(
        order_id=OrderId("o2"), customer_id=UserId("u1"),
        total=Money(Decimal("80"), "USD"), item_count=4,
        channel="mobile",
    )

    print(f"  V1 fields:  {[f.name for f in dc_fields(OrderPlacedV1)]}")
    print(f"  V2 fields:  {[f.name for f in dc_fields(OrderPlacedV2)]}")
    print(f"  V2 added:   {set(f.name for f in dc_fields(OrderPlacedV2)) - set(f.name for f in dc_fields(OrderPlacedV1))}")

    # V1-only consumer can still read V2's common fields
    def v1_only_consumer(evt):
        return {
            "order_id": evt.order_id,
            "total": str(evt.total),
        }

    print(f"  V1 consumer reads V1:      {v1_only_consumer(v1)}")
    print(f"  V1 consumer reads V2:      {v1_only_consumer(v2)}")
    print(f"  V2 has channel='mobile':   {v2.channel}")
    print("  PASS — additive evolution; V1 consumers still work")
    print("  Rule: only ADD optional fields. RENAME/REMOVE breaks Published Language.")


def demo_7_classify_decision_tree() -> None:
    banner("DEMO 7 — Decision tree classifier on 14 classes")

    candidates = [
        Money, Email, PhoneNumber, DateRange, Percentage, Coordinate, LineItem,
        User, Order,
        UserRegistered, EmailChanged, OrderPlacedV1, OrderPlacedV2, OrderCancelled,
    ]

    print(f"  {'Class':<22} {'Verdict':<14} {'Reason'}")
    print(f"  {'-'*22} {'-'*14} {'-'*38}")

    expected = {
        "Money": "VALUE_OBJECT", "Email": "VALUE_OBJECT", "PhoneNumber": "VALUE_OBJECT",
        "DateRange": "VALUE_OBJECT", "Percentage": "VALUE_OBJECT",
        "Coordinate": "VALUE_OBJECT", "LineItem": "VALUE_OBJECT",
        "User": "ENTITY", "Order": "ENTITY",
        "UserRegistered": "DOMAIN_EVENT", "EmailChanged": "DOMAIN_EVENT",
        "OrderPlacedV1": "DOMAIN_EVENT", "OrderPlacedV2": "DOMAIN_EVENT",
        "OrderCancelled": "DOMAIN_EVENT",
    }
    correct = 0
    for cls in candidates:
        verdict = classify(cls)
        expected_v = expected[cls.__name__]
        marker = "✓" if verdict == expected_v else "✗"
        frozen = "frozen" if is_frozen_dataclass(cls) else "mutable"
        past = "past-tense" if is_past_tense(cls.__name__) else "noun"
        print(f"  {cls.__name__:<22} {verdict:<14} [{marker}] {frozen} + {past}")
        if verdict == expected_v:
            correct += 1
    print(f"\n  Accuracy: {correct}/{len(candidates)}")
    assert correct == len(candidates)
    print("  PASS — classifier identifies all 14 classes correctly")


def demo_8_entity_with_vo_and_event_flow() -> None:
    banner("DEMO 8 — Full flow: Entity uses VO, emits Event")

    # Register user (Entity created with VO email, emits Event)
    user = User.register(Email("Alice@Ellumm.COM"), "Alice")
    print(f"  Created user: {user}")
    print(f"  Email normalized to lower: {user.email.value}")
    assert user.email.value == "alice@ellumm.com"

    # Build order with line items (VOs)
    order = Order.start(user.user_id)
    order.add_item(LineItem(ProductId("p1"), 2, Money(Decimal("9.99"), "USD")))
    order.add_item(LineItem(ProductId("p2"), 1, Money(Decimal("4.50"), "USD")))
    print(f"  Order total: {order.total()}")
    assert order.total() == Money(Decimal("24.48"), "USD")

    # Place order → emit event
    order.place()
    print(f"  Order status: {order.status}")

    # Collect events from entity
    user_evts = user.collect_pending_events()
    order_evts = order.collect_pending_events()
    print(f"  User events: {[type(e).__name__ for e in user_evts]}")
    print(f"  Order events: {[type(e).__name__ for e in order_evts]}")
    assert isinstance(user_evts[0], UserRegistered)
    assert isinstance(order_evts[0], OrderPlacedV1)
    print("  PASS — Entity-VO-Event composition complete")


def demo_9_anti_patterns_showcase() -> None:
    banner("DEMO 9 — Anti-pattern showcase: what NOT to do")

    print("""
    ANTI-PATTERN A — Mutable VO:
        @dataclass                        # ✗ missing frozen=True
        class Money:
            amount: Decimal
            currency: str
        m = Money(10, "USD")
        m.amount = 9999                   # ✗ mutation slips through

    ANTI-PATTERN B — Entity equality by attribute:
        @dataclass(eq=True)
        class User:
            user_id: str
            email: str                    # eq=True compares ALL fields
        # u1=User("u1","a@x"), u2=User("u2","a@x") → u1 == u2 (BUG)

    ANTI-PATTERN C — Event with mutable list:
        @dataclass(frozen=True)
        class OrderPlaced:
            items: List[str]              # ✗ list is mutable
        evt = OrderPlaced(["a"])
        evt.items.append("b")             # mutates payload despite frozen

    ANTI-PATTERN D — Event with future-tense name:
        @dataclass(frozen=True)
        class PlaceOrder:                 # ✗ imperative = command, not event
            order_id: str
        # Consumer confused: should it execute or react?

    ANTI-PATTERN E — VO without validation:
        @dataclass(frozen=True)
        class Email:
            value: str
            # no __post_init__
        Email("not-an-email")             # accepts! bug at send time

    ANTI-PATTERN F — Stringly-typed IDs:
        class Order:
            user_id: str                  # ✗ bare str
            quiz_id: str                  # easy to swap by accident
        # vs: UserId = NewType("UserId", str)
    """)


# =============================================================================
# [ANSWER KEY — Bài tập 1]   Classification of 10 sample classes
# =============================================================================

EXERCISE_1_ANSWERS = """
Bài tập 1 — Classification:
  1. Money(amount, currency)        VO        — defined by amount+currency, interchangeable
  2. User(id, email, name)          Entity    — id bền vững, mutable email/name, lifecycle
  3. OrderPlaced(order_id, total)   Event     — past-tense fact, frozen, broadcast
  4. Coordinate(lat, lng)           VO        — value pair, no identity
  5. Submission(id, user_id, score) Entity    — id, lifecycle (DRAFT→GRADED→FINALIZED)
  6. EmailAddress(value)            VO        — validated string
  7. Quiz(quiz_id, title, questions) Entity   — id, mutable (publish/retire/add_question)
  8. Color(r, g, b)                 VO        — RGB triplet, immutable
  9. PaymentRefunded(payment_id, amount) Event — past-tense, broadcast
 10. Address(street, city, postal_code) VO    — snapshot of location (default)
"""


# =============================================================================
# RUN ALL
# =============================================================================

def main() -> int:
    demo_1_entity_vs_vo_identity()
    demo_2_vo_immutability()
    demo_3_vo_validation_at_construction()
    demo_4_vo_side_effect_free_methods()
    demo_5_event_characteristics()
    demo_6_event_versioning()
    demo_7_classify_decision_tree()
    demo_8_entity_with_vo_and_event_flow()
    demo_9_anti_patterns_showcase()

    print(EXERCISE_1_ANSWERS)

    print()
    print("=" * 76)
    print("  ALL 9 DEMOS PASS - Lesson 36 Entity / VO / Event verified")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
