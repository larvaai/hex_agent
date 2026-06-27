"""
Lesson 31 — Event-Driven Architecture (EDA)
============================================

Refactor `quiz` từ Lesson 30 (Hexagonal) lên EDA: thay vì AppService gọi
driven port `INotifier` đồng bộ, ta *publish event* và để handler subscribe.

Cấu trúc (1 file để chạy ngay):
    [DOMAIN]    Events (frozen) + Aggregate + AppService (chỉ publish)
    [BUS]       IEventBus + SyncBus + AsyncBus(ThreadPool) + RetryingBus + DLQ
    [HANDLERS]  Scoring, Leaderboard, Notification, Analytics, Badge, Flaky
    [SAGA]      Choreography (handler chain) + Orchestrator (centralized)
    [OUTBOX]    OutboxRepo (SQLite tx) + OutboxRelay (poll & publish)
    [BOOTSTRAP] Composition root
    [DEMO]      8 demos chứng minh từng aspect

Cách chạy:
    python 31_eda.py
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable, List, Dict, Any, Callable, Type, Optional, Tuple


# =============================================================================
# [DOMAIN — EVENTS]   Immutable, past-tense, có event_id + occurred_at
# =============================================================================

@dataclass(frozen=True)
class Event:
    """Base event — mọi event kế thừa. Frozen ⇒ immutable sau publish."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class QuizSubmitted(Event):
    user_id: str = ""
    answers: Tuple[int, ...] = ()              # tuple để frozen


@dataclass(frozen=True)
class ScoreCalculated(Event):
    user_id: str = ""
    correct_count: int = 0
    total: int = 0
    score: float = 0.0


@dataclass(frozen=True)
class LeaderboardUpdated(Event):
    user_id: str = ""
    rank: int = 0
    score: float = 0.0


@dataclass(frozen=True)
class NotificationSent(Event):
    user_id: str = ""
    channel: str = ""


@dataclass(frozen=True)
class BadgeAwarded(Event):
    user_id: str = ""
    badge: str = ""


# =============================================================================
# [DOMAIN — AGGREGATE & APP SERVICE]
# =============================================================================

@dataclass(frozen=True)
class Question:
    qid: str
    correct_answer: int
    weight: float = 1.0


QUESTIONS = [
    Question("q1", 2, 1.0),
    Question("q2", 0, 1.0),
    Question("q3", 3, 2.0),
    Question("q4", 1, 1.0),
]


# =============================================================================
# [BUS]   Interface + 3 implementations + Decorators
# =============================================================================

EventHandler = Callable[[Event], None]


@runtime_checkable
class IEventBus(Protocol):
    def subscribe(self, event_type: Type[Event], handler: EventHandler) -> None: ...
    def publish(self, event: Event) -> None: ...


# ---- 1) SyncBus — callback list, in-process, default ------------------------

class SyncEventBus:
    """Đơn giản nhất: dispatch ngay trong thread của producer."""

    def __init__(self) -> None:
        self._subs: Dict[Type[Event], List[EventHandler]] = defaultdict(list)
        self.dlq: List[Tuple[Event, str, str]] = []     # (event, handler_name, err)

    def subscribe(self, event_type: Type[Event], handler: EventHandler) -> None:
        self._subs[event_type].append(handler)

    def publish(self, event: Event) -> None:
        # Cũng dispatch cho subscribers của Event base (catch-all).
        targets: List[EventHandler] = []
        for et, handlers in self._subs.items():
            if isinstance(event, et):
                targets.extend(handlers)
        for h in targets:
            try:
                h(event)
            except Exception as e:                       # noqa: BLE001
                # Isolation: 1 handler fail KHÔNG ảnh hưởng handler khác
                self.dlq.append((event, getattr(h, "__name__", repr(h)), str(e)))


# ---- 2) AsyncEventBus — ThreadPool, parallel handler ------------------------

class AsyncEventBus:
    """Each publish dispatches to all handlers via ThreadPool — parallel."""

    def __init__(self, max_workers: int = 4) -> None:
        self._subs: Dict[Type[Event], List[EventHandler]] = defaultdict(list)
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: List[Future] = []
        self._lock = threading.Lock()
        self.dlq: List[Tuple[Event, str, str]] = []

    def subscribe(self, event_type: Type[Event], handler: EventHandler) -> None:
        self._subs[event_type].append(handler)

    def publish(self, event: Event) -> None:
        targets: List[EventHandler] = []
        for et, handlers in self._subs.items():
            if isinstance(event, et):
                targets.extend(handlers)
        for h in targets:
            fut = self._pool.submit(self._safe_call, h, event)
            with self._lock:
                self._futures.append(fut)

    def _safe_call(self, h: EventHandler, event: Event) -> None:
        try:
            h(event)
        except Exception as e:                           # noqa: BLE001
            with self._lock:
                self.dlq.append((event, getattr(h, "__name__", repr(h)), str(e)))

    def wait_idle(self, timeout: float = 5.0) -> None:
        """Producer dùng để chờ các handler hoàn thành (test only)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                pending = [f for f in self._futures if not f.done()]
            if not pending:
                return
            time.sleep(0.005)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)


# ---- 3) RetryingBus — Decorator wrap any IEventBus với retry + DLQ ----------

class RetryingEventBus:
    """
    Wrap inner bus. Retry mỗi handler max_retries với exponential backoff.
    Fail max → push vào DLQ kèm reason.

    Note: inner bus phải dispatch synchronously để retry semantics đúng.
    """

    def __init__(self, inner: IEventBus, max_retries: int = 3, base_delay_s: float = 0.001) -> None:
        self.inner = inner
        self.max_retries = max_retries
        self.base_delay_s = base_delay_s
        self.dlq: List[Dict[str, Any]] = []
        self.retry_log: List[Tuple[str, int]] = []        # (handler_name, attempts)

    def subscribe(self, event_type: Type[Event], handler: EventHandler) -> None:
        wrapped = self._wrap_handler(handler)
        self.inner.subscribe(event_type, wrapped)

    def publish(self, event: Event) -> None:
        self.inner.publish(event)

    def _wrap_handler(self, handler: EventHandler) -> EventHandler:
        name = getattr(handler, "__name__", repr(handler))

        def wrapped(event: Event) -> None:
            last_err: Optional[Exception] = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    handler(event)
                    self.retry_log.append((name, attempt))
                    return
                except Exception as e:                   # noqa: BLE001
                    last_err = e
                    time.sleep(self.base_delay_s * (2 ** (attempt - 1)))
            self.dlq.append({
                "event": event,
                "handler": name,
                "reason": str(last_err),
                "attempts": self.max_retries,
            })

        wrapped.__name__ = f"retrying({name})"
        return wrapped


# ---- 4) IdempotentHandler — dedup by event_id at consumer side --------------

def make_idempotent(handler: EventHandler, name: str) -> EventHandler:
    """Wrap handler with event_id dedup. Pure function, không state ngoài."""
    seen: set[str] = set()

    def wrapper(event: Event) -> None:
        if event.event_id in seen:
            return
        handler(event)
        seen.add(event.event_id)

    wrapper.__name__ = f"idempotent({name})"
    return wrapper


# =============================================================================
# [HANDLERS]
# =============================================================================

class ScoringHandler:
    """Saga step 1: nhận QuizSubmitted, chấm điểm, publish ScoreCalculated."""

    def __init__(self, bus: IEventBus, questions: List[Question]) -> None:
        self.bus = bus
        self.questions = questions

    def handle(self, event: Event) -> None:
        assert isinstance(event, QuizSubmitted)
        if len(event.answers) != len(self.questions):
            raise ValueError(f"answer count mismatch: {len(event.answers)}")
        breakdown = [
            a == q.correct_answer for a, q in zip(event.answers, self.questions)
        ]
        weighted = sum(
            q.weight for q, ok in zip(self.questions, breakdown) if ok
        )
        self.bus.publish(ScoreCalculated(
            user_id=event.user_id,
            correct_count=sum(breakdown),
            total=len(self.questions),
            score=weighted,
        ))


class LeaderboardHandler:
    """Saga step 2A: nhận ScoreCalculated, update leaderboard, publish LeaderboardUpdated."""

    def __init__(self, bus: IEventBus) -> None:
        self.bus = bus
        self.scores: Dict[str, float] = {}

    def handle(self, event: Event) -> None:
        assert isinstance(event, ScoreCalculated)
        # Cộng dồn — đây CHÍNH là chỗ dễ vi phạm idempotency nếu replay
        self.scores[event.user_id] = self.scores.get(event.user_id, 0) + event.score
        ranked = sorted(self.scores.items(), key=lambda x: -x[1])
        rank = next((i + 1 for i, (u, _) in enumerate(ranked) if u == event.user_id), 0)
        self.bus.publish(LeaderboardUpdated(
            user_id=event.user_id, rank=rank, score=self.scores[event.user_id]
        ))


class NotificationHandler:
    """Saga step 2B: nhận ScoreCalculated, gửi email (mock), publish NotificationSent."""

    def __init__(self, bus: IEventBus) -> None:
        self.bus = bus
        self.sent: List[str] = []

    def handle(self, event: Event) -> None:
        assert isinstance(event, ScoreCalculated)
        self.sent.append(f"email→{event.user_id}: score={event.score}")
        self.bus.publish(NotificationSent(user_id=event.user_id, channel="email"))


class AnalyticsHandler:
    """Catch-all: subscribe Event base, đếm mọi event đi qua bus."""

    def __init__(self) -> None:
        self.counts: Dict[str, int] = defaultdict(int)

    def handle(self, event: Event) -> None:
        self.counts[type(event).__name__] += 1


class BadgeHandler:
    """Thêm SAU — minh hoạ OCP: producer code không sửa khi thêm consumer."""

    def __init__(self, bus: IEventBus, threshold: float = 4.0) -> None:
        self.bus = bus
        self.threshold = threshold
        self.awarded: List[str] = []

    def handle(self, event: Event) -> None:
        assert isinstance(event, ScoreCalculated)
        if event.score >= self.threshold:
            self.awarded.append(event.user_id)
            self.bus.publish(BadgeAwarded(user_id=event.user_id, badge="champion"))


class FlakyHandler:
    """Throw lần đầu, success sau retry — để demo retry + DLQ."""

    def __init__(self, fail_first_n: int = 99) -> None:
        self.fail_remaining = fail_first_n
        self.success_count = 0

    def handle(self, event: Event) -> None:
        if self.fail_remaining > 0:
            self.fail_remaining -= 1
            raise ConnectionError("downstream timeout")
        self.success_count += 1


# =============================================================================
# [APP SERVICE]   Producer — chỉ publish event sau khi commit local state
# =============================================================================

class QuizApplicationService:
    """Producer. Sau Hex (Lesson 30) ta có: repo.save() + notifier.send().
       Bây giờ EDA: repo.save() + bus.publish(QuizSubmitted)."""

    def __init__(self, bus: IEventBus, repo: Optional[Dict[str, list]] = None) -> None:
        self.bus = bus
        self.repo: Dict[str, list] = repo if repo is not None else {}

    def submit_quiz(self, user_id: str, answers: List[int]) -> str:
        # 1) Persist local state
        self.repo.setdefault(user_id, []).append(list(answers))
        # 2) Publish fact
        event = QuizSubmitted(user_id=user_id, answers=tuple(answers))
        self.bus.publish(event)
        return event.event_id


# =============================================================================
# [SAGA — ORCHESTRATOR]   Alternative cho choreography
# =============================================================================

class QuizSagaOrchestrator:
    """Centralized: tự gọi từng step. Easier to trace, easier compensation."""

    def __init__(
        self,
        scoring: ScoringHandler,
        leaderboard: LeaderboardHandler,
        notification: NotificationHandler,
    ) -> None:
        self.scoring = scoring
        self.leaderboard = leaderboard
        self.notification = notification
        self.steps_executed: List[str] = []
        self.compensations: List[str] = []

    def run(self, event: QuizSubmitted) -> None:
        try:
            # Step 1
            self.scoring.handle(event)
            self.steps_executed.append("scoring")
            # Step 2 (lấy ScoreCalculated cuối cùng dispatched từ bus chung;
            # ở orchestrator không có bus thật → reproduce ở đây cho minh hoạ)
            score_event = ScoreCalculated(
                user_id=event.user_id, correct_count=4, total=4, score=5.0
            )
            self.leaderboard.handle(score_event)
            self.steps_executed.append("leaderboard")
            self.notification.handle(score_event)
            self.steps_executed.append("notification")
        except Exception as e:                            # noqa: BLE001
            self.compensations.append(f"compensate after {len(self.steps_executed)} steps: {e}")


# =============================================================================
# [OUTBOX]   Atomicity giữa state save + event publish
# =============================================================================

class OutboxRepo:
    """Submission + outbox event lưu cùng SQLite transaction."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS submissions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT, answers TEXT
            );
            CREATE TABLE IF NOT EXISTS outbox(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE, event_type TEXT,
                payload TEXT, dispatched INTEGER DEFAULT 0
            );
        """)
        self.conn.commit()

    def save_with_event(self, user_id: str, answers: List[int], event: QuizSubmitted) -> None:
        try:
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO submissions(user_id, answers) VALUES (?, ?)",
                (user_id, ",".join(str(a) for a in answers)),
            )
            cur.execute(
                "INSERT INTO outbox(event_id, event_type, payload, dispatched) VALUES (?, ?, ?, 0)",
                (event.event_id, "QuizSubmitted",
                 f"{user_id}|{','.join(str(a) for a in answers)}"),
            )
            self.conn.commit()                            # ATOMIC: cả 2 hoặc không
        except Exception:
            self.conn.rollback()
            raise

    def fetch_undispatched(self) -> List[Tuple[int, str, str, str]]:
        cur = self.conn.execute(
            "SELECT id, event_id, event_type, payload FROM outbox WHERE dispatched=0"
        )
        return cur.fetchall()

    def mark_dispatched(self, row_id: int) -> None:
        self.conn.execute("UPDATE outbox SET dispatched=1 WHERE id=?", (row_id,))
        self.conn.commit()

    def count_dispatched(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM outbox WHERE dispatched=1").fetchone()[0]


class OutboxRelay:
    """Poll outbox và publish lên bus. Real prod: chạy background, mỗi 100 ms."""

    def __init__(self, repo: OutboxRepo, bus: IEventBus) -> None:
        self.repo = repo
        self.bus = bus

    def run_once(self) -> int:
        rows = self.repo.fetch_undispatched()
        for row_id, event_id, event_type, payload in rows:
            user_id, ans_str = payload.split("|")
            answers = tuple(int(a) for a in ans_str.split(","))
            event = QuizSubmitted(
                event_id=event_id, occurred_at=datetime.now(),
                user_id=user_id, answers=answers,
            )
            self.bus.publish(event)
            self.repo.mark_dispatched(row_id)
        return len(rows)


# =============================================================================
# [BOOTSTRAP]   Composition root
# =============================================================================

def build_app_choreography(bus: IEventBus, *, with_badge: bool = False) -> Dict[str, Any]:
    """Wire tất cả handlers theo choreography (handler chain qua bus)."""
    scoring = ScoringHandler(bus, QUESTIONS)
    leaderboard = LeaderboardHandler(bus)
    notification = NotificationHandler(bus)
    analytics = AnalyticsHandler()

    bus.subscribe(QuizSubmitted, scoring.handle)
    bus.subscribe(ScoreCalculated, leaderboard.handle)
    bus.subscribe(ScoreCalculated, notification.handle)
    bus.subscribe(Event, analytics.handle)              # catch-all

    components: Dict[str, Any] = {
        "scoring": scoring, "leaderboard": leaderboard,
        "notification": notification, "analytics": analytics,
    }
    if with_badge:
        badge = BadgeHandler(bus)
        bus.subscribe(ScoreCalculated, badge.handle)
        components["badge"] = badge
    return components


# =============================================================================
# [DEMO]
# =============================================================================

def banner(s: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {s}")
    print("=" * 72)


def demo_1_choreography_happy() -> None:
    banner("DEMO 1 — Saga choreography happy path (1 publish → 5 events fan-out)")
    bus = SyncEventBus()
    comps = build_app_choreography(bus)
    app = QuizApplicationService(bus)

    eid = app.submit_quiz("u1", [2, 0, 3, 1])    # all correct
    print(f"Producer published: QuizSubmitted (event_id={eid[:8]}...)")
    print(f"Analytics counts: {dict(comps['analytics'].counts)}")
    print(f"Leaderboard: {comps['leaderboard'].scores}")
    print(f"Email log:   {comps['notification'].sent}")
    assert comps["analytics"].counts["QuizSubmitted"] == 1
    assert comps["analytics"].counts["ScoreCalculated"] == 1
    assert comps["analytics"].counts["LeaderboardUpdated"] == 1
    assert comps["analytics"].counts["NotificationSent"] == 1
    assert comps["leaderboard"].scores["u1"] == 5.0
    print("  PASS — 1 publish triggered 4 downstream events (saga chain)")


def demo_2_open_closed_add_consumer() -> None:
    banner("DEMO 2 — OCP: thêm BadgeHandler không touch producer code")
    bus = SyncEventBus()
    comps = build_app_choreography(bus, with_badge=True)     # ← chỉ thay flag
    app = QuizApplicationService(bus)
    app.submit_quiz("champ", [2, 0, 3, 1])

    print(f"Badges awarded: {comps['badge'].awarded}")
    assert comps["badge"].awarded == ["champ"]
    assert comps["analytics"].counts["BadgeAwarded"] == 1
    # Producer (QuizApplicationService.submit_quiz) — kiểm tra số dòng "publish"
    import inspect
    src = inspect.getsource(QuizApplicationService.submit_quiz)
    n_publishes = src.count("bus.publish")
    print(f"Producer code 'bus.publish' calls: {n_publishes}")
    assert n_publishes == 1                              # vẫn chỉ 1 publish
    print("  PASS — extension via subscription, zero touch producer")


def demo_3_handler_failure_isolation() -> None:
    banner("DEMO 3 — Handler crash isolation (1 fail không sập others)")
    bus = SyncEventBus()
    comps = build_app_choreography(bus)
    crasher = FlakyHandler(fail_first_n=99)            # luôn fail
    bus.subscribe(ScoreCalculated, crasher.handle)
    app = QuizApplicationService(bus)
    app.submit_quiz("u1", [2, 0, 3, 1])

    print(f"DLQ entries: {len(bus.dlq)}")
    print(f"  → handler={bus.dlq[0][1]}  err={bus.dlq[0][2]}")
    print(f"Leaderboard still updated? {comps['leaderboard'].scores}")
    print(f"Email still sent?           {comps['notification'].sent}")
    assert len(bus.dlq) == 1
    assert "u1" in comps["leaderboard"].scores
    assert len(comps["notification"].sent) == 1
    print("  PASS — failure of FlakyHandler did not block others")


def demo_4_idempotency_replay() -> None:
    banner("DEMO 4 — Idempotency: at-least-once → consumer dedup by event_id")
    bus = SyncEventBus()
    leaderboard = LeaderboardHandler(bus)
    # Wrap idempotent
    bus.subscribe(ScoreCalculated, make_idempotent(leaderboard.handle, "leaderboard"))

    score = ScoreCalculated(user_id="u1", correct_count=4, total=4, score=5.0)
    bus.publish(score)
    bus.publish(score)             # ← REPLAY same event_id
    bus.publish(score)             # ← REPLAY again

    print(f"Score after 3 deliveries (same event_id): {leaderboard.scores['u1']}")
    assert leaderboard.scores["u1"] == 5.0   # NOT 15.0
    print("  PASS — idempotent consumer correctly deduplicated 3 → 1")

    # Counter-example: nếu KHÔNG idempotent
    naive = LeaderboardHandler(SyncEventBus())
    for _ in range(3):
        naive.handle(score)
    print(f"  (Counter-example, naive handler 3x replay): u1={naive.scores['u1']}")
    assert naive.scores["u1"] == 15.0        # bug! triple count
    print("  Confirmed: bus at-least-once requires idempotent consumer")


def demo_5_async_parallel_throughput() -> None:
    banner("DEMO 5 — Async ThreadPool dispatch — parallel handlers")

    def slow_handler_factory(label: str, latency_s: float):
        captured = {"count": 0, "label": label}

        def h(_event: Event) -> None:
            time.sleep(latency_s)        # simulate I/O
            captured["count"] += 1

        h.__name__ = label
        return h, captured

    # 4 handler, mỗi cái 50 ms — sync = 200 ms; async 4-worker ≈ 50 ms
    handlers = [slow_handler_factory(f"h{i}", 0.05) for i in range(4)]

    # Sync
    sync_bus = SyncEventBus()
    for h, _ in handlers:
        sync_bus.subscribe(QuizSubmitted, h)
    t0 = time.perf_counter()
    sync_bus.publish(QuizSubmitted(user_id="u1", answers=(2, 0, 3, 1)))
    sync_dur = (time.perf_counter() - t0) * 1000

    # Async
    async_bus = AsyncEventBus(max_workers=4)
    for h, _ in handlers:
        async_bus.subscribe(QuizSubmitted, h)
    t0 = time.perf_counter()
    async_bus.publish(QuizSubmitted(user_id="u2", answers=(2, 0, 3, 1)))
    async_bus.wait_idle(timeout=2.0)
    async_dur = (time.perf_counter() - t0) * 1000
    async_bus.shutdown()

    print(f"Sync  (4 × 50ms sequential): {sync_dur:7.1f} ms")
    print(f"Async (4 workers parallel) : {async_dur:7.1f} ms")
    print(f"Speedup: {sync_dur/async_dur:.2f}x  (theoretical max ~4x)")
    assert async_dur < sync_dur * 0.6, "async should be much faster"
    print("  PASS — async dispatch concurrent (Amdahl effect ~3x typical)")


def demo_6_retry_then_dlq() -> None:
    banner("DEMO 6 — RetryingBus: 3 attempts then move to DLQ")

    inner = SyncEventBus()
    bus = RetryingEventBus(inner, max_retries=3, base_delay_s=0.001)

    # Handler luôn fail (99 lần)
    permanent_fail = FlakyHandler(fail_first_n=99)
    bus.subscribe(QuizSubmitted, permanent_fail.handle)

    # Handler fail 2 lần đầu, sau đó OK (sẽ pass at attempt 3)
    transient = FlakyHandler(fail_first_n=2)
    bus.subscribe(QuizSubmitted, transient.handle)

    bus.publish(QuizSubmitted(user_id="u1", answers=(2, 0, 3, 1)))

    print(f"DLQ entries: {len(bus.dlq)}")
    for entry in bus.dlq:
        print(f"  - handler={entry['handler']}  attempts={entry['attempts']}  reason={entry['reason']}")
    print(f"Transient handler success_count: {transient.success_count}")
    print(f"Retry log (handler, attempt that succeeded or final): {bus.retry_log}")

    # Permanent → DLQ; transient → recovered
    assert len(bus.dlq) == 1
    assert bus.dlq[0]["attempts"] == 3                  # max_retries reached
    assert transient.success_count == 1
    print("  PASS — transient retried, permanent went to DLQ after 3 attempts")


def demo_7_outbox_atomicity() -> None:
    banner("DEMO 7 — Outbox pattern: state + event in 1 transaction → relay publishes")

    repo = OutboxRepo(":memory:")
    bus = SyncEventBus()
    comps = build_app_choreography(bus)

    # Producer dùng outbox: save state + outbox event ATOMIC
    event = QuizSubmitted(user_id="u1", answers=(2, 0, 3, 1))
    repo.save_with_event("u1", [2, 0, 3, 1], event)
    print("After save_with_event: state committed, event waiting in outbox")
    print(f"  - bus dispatched yet?  analytics counts={dict(comps['analytics'].counts)}")
    assert comps["analytics"].counts.get("QuizSubmitted", 0) == 0   # chưa publish

    # Simulate process restart: nothing in memory, outbox row vẫn còn
    print("\n  [process crash here is safe — outbox row survives in DB]")

    # Relay starts up later, polls outbox
    relay = OutboxRelay(repo, bus)
    n = relay.run_once()
    print(f"\nRelay published {n} pending event(s)")
    print(f"  - analytics counts after relay: {dict(comps['analytics'].counts)}")
    print(f"  - dispatched rows: {repo.count_dispatched()}")
    assert comps["analytics"].counts["QuizSubmitted"] == 1
    assert repo.count_dispatched() == 1

    # Re-run relay — không re-publish (đã marked dispatched)
    relay.run_once()
    assert comps["analytics"].counts["QuizSubmitted"] == 1
    print("  PASS — atomicity guaranteed; re-running relay is safe")


def demo_8_orchestrator_vs_choreography() -> None:
    banner("DEMO 8 — Saga: Orchestrator vs Choreography comparison")

    # Choreography
    chore_bus = SyncEventBus()
    chore = build_app_choreography(chore_bus)
    QuizApplicationService(chore_bus).submit_quiz("u1", [2, 0, 3, 1])
    chore_event_count = sum(chore["analytics"].counts.values())

    # Orchestrator (no bus — direct calls)
    orch_bus = SyncEventBus()
    scoring = ScoringHandler(orch_bus, QUESTIONS)
    leaderboard = LeaderboardHandler(orch_bus)
    notification = NotificationHandler(orch_bus)
    orch = QuizSagaOrchestrator(scoring, leaderboard, notification)
    orch.run(QuizSubmitted(user_id="u2", answers=(2, 0, 3, 1)))

    print(f"Choreography — events on bus: {chore_event_count}")
    print(f"Orchestrator — explicit steps: {orch.steps_executed}")
    print()
    print("Comparison:")
    print(f"  Choreography  | Orchestrator")
    print(f"  ──────────────┼─────────────────────")
    print(f"  decentralized | centralized")
    print(f"  loose coupling| explicit flow")
    print(f"  hard to trace | easy to trace")
    print(f"  no compensate | compensate built-in")
    print(f"  scale: easy   | scale: orchestrator can be SPOF")
    assert orch.steps_executed == ["scoring", "leaderboard", "notification"]
    assert chore_event_count >= 4
    print("  PASS — both approaches valid; choose based on workflow complexity")


# =============================================================================
# RUN ALL
# =============================================================================

def main() -> int:
    demo_1_choreography_happy()
    demo_2_open_closed_add_consumer()
    demo_3_handler_failure_isolation()
    demo_4_idempotency_replay()
    demo_5_async_parallel_throughput()
    demo_6_retry_then_dlq()
    demo_7_outbox_atomicity()
    demo_8_orchestrator_vs_choreography()

    print("\n" + "=" * 72)
    print("  ALL 8 DEMOS PASS — Lesson 31 EDA verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
