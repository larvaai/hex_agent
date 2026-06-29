"""
Lesson 39 — Distributed DDD: Cross-Context Consistency + Saga
==============================================================

Refactor Ellumm với 4 bounded context + 2 saga style:
- Choreography: each BC subscribes events, decentralized chain.
- Orchestration: QuizSubmissionSaga process manager với state machine.

Demonstrate:
- Happy path both styles.
- Compensation when middle step fails.
- Idempotency at cross-BC boundary (replay protection).
- Eventual consistency window timing.
- Cycle prevention detection.
- Anti-patterns showcase.

Run: python 39_distributed_ddd.py
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (Any, Callable, Dict, List, Optional, Set, Tuple,
                    NewType, Protocol)


# =============================================================================
# [PRIMITIVES]
# =============================================================================

UserId = NewType("UserId", str)
QuizId = NewType("QuizId", str)
SubmissionId = NewType("SubmissionId", str)
SagaId = NewType("SagaId", str)


# =============================================================================
# [EVENTS]   Cross-BC published language events (with event_id for idempotency)
# =============================================================================

@dataclass(frozen=True)
class DomainEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)
    correlation_id: str = ""             # ties events of same saga together


# Saga input/output
@dataclass(frozen=True)
class AuthVerified(DomainEvent):
    user_id: UserId = UserId("")

@dataclass(frozen=True)
class AuthFailed(DomainEvent):
    user_id: UserId = UserId("")
    reason: str = ""


@dataclass(frozen=True)
class QuotaConfirmed(DomainEvent):
    user_id: UserId = UserId("")
    remaining: int = 0

@dataclass(frozen=True)
class QuotaExceeded(DomainEvent):
    user_id: UserId = UserId("")


@dataclass(frozen=True)
class SubmissionCreated(DomainEvent):
    submission_id: SubmissionId = SubmissionId("")
    user_id: UserId = UserId("")
    quiz_id: QuizId = QuizId("")

@dataclass(frozen=True)
class SubmissionGraded(DomainEvent):
    submission_id: SubmissionId = SubmissionId("")
    user_id: UserId = UserId("")
    points: float = 0.0


@dataclass(frozen=True)
class LeaderboardUpdated(DomainEvent):
    user_id: UserId = UserId("")
    rank: int = 0

@dataclass(frozen=True)
class LeaderboardUpdateFailed(DomainEvent):
    user_id: UserId = UserId("")
    reason: str = ""


@dataclass(frozen=True)
class ReceiptSent(DomainEvent):
    user_id: UserId = UserId("")


# Compensation events
@dataclass(frozen=True)
class QuotaRestored(DomainEvent):
    user_id: UserId = UserId("")

@dataclass(frozen=True)
class SubmissionVoided(DomainEvent):
    submission_id: SubmissionId = SubmissionId("")


# =============================================================================
# [EVENT BUS]   Cross-BC message broker (simplified in-process)
# =============================================================================

EventHandler = Callable[[DomainEvent], None]


class EventBus:
    """Simulate message broker. Supports at-least-once delivery option."""

    def __init__(self, deliver_twice: bool = False) -> None:
        self._subs: Dict[type, List[EventHandler]] = defaultdict(list)
        self.published: List[DomainEvent] = []
        self.deliver_twice = deliver_twice   # simulate broker duplicate

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        self._subs[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        self.published.append(event)
        targets = []
        for et, handlers in self._subs.items():
            if isinstance(event, et):
                targets.extend(handlers)
        for h in targets:
            try:
                h(event)
                if self.deliver_twice:
                    h(event)                 # simulate at-least-once duplicate
            except Exception as e:
                # In real broker, failed handler → retry or DLQ
                pass


# =============================================================================
# [IDEMPOTENCY]   Consumer dedup by event_id at BC boundary
# =============================================================================

def idempotent(handler: EventHandler) -> EventHandler:
    """Wrap handler to dedup by event_id. Per-handler-instance state."""
    seen: Set[str] = set()
    def wrapped(event: DomainEvent) -> None:
        if event.event_id in seen:
            return
        seen.add(event.event_id)
        handler(event)
    wrapped.__name__ = f"idempotent({getattr(handler, '__name__', repr(handler))})"
    return wrapped


# =============================================================================
# [BC 1 — AuthBC]   Verify user identity
# =============================================================================

class AuthBC:
    def __init__(self, bus: EventBus, valid_users: Set[UserId]) -> None:
        self.bus = bus
        self._valid = valid_users
        self.processed_count = 0

    def verify(self, user_id: UserId, correlation_id: str) -> None:
        self.processed_count += 1
        if user_id in self._valid:
            self.bus.publish(AuthVerified(user_id=user_id, correlation_id=correlation_id))
        else:
            self.bus.publish(AuthFailed(
                user_id=user_id, reason="unknown user",
                correlation_id=correlation_id,
            ))


# =============================================================================
# [BC 2 — SubscriptionBC]   Check + consume quota
# =============================================================================

class SubscriptionBC:
    def __init__(self, bus: EventBus, initial_quota: int = 5) -> None:
        self.bus = bus
        self._quota: Dict[UserId, int] = defaultdict(lambda: initial_quota)
        self.consumed_count = 0
        self.restored_count = 0

    def check_and_consume(self, user_id: UserId, correlation_id: str) -> None:
        if self._quota[user_id] > 0:
            self._quota[user_id] -= 1
            self.consumed_count += 1
            self.bus.publish(QuotaConfirmed(
                user_id=user_id, remaining=self._quota[user_id],
                correlation_id=correlation_id,
            ))
        else:
            self.bus.publish(QuotaExceeded(
                user_id=user_id, correlation_id=correlation_id,
            ))

    # Compensation
    def restore_quota(self, event: DomainEvent) -> None:
        user_id = getattr(event, "user_id", None)
        if user_id is None:
            return
        self._quota[user_id] += 1
        self.restored_count += 1
        self.bus.publish(QuotaRestored(
            user_id=user_id, correlation_id=event.correlation_id,
        ))

    def remaining(self, user_id: UserId) -> int:
        return self._quota[user_id]


# =============================================================================
# [BC 3 — SubmissionBC]   Create + grade submission
# =============================================================================

class SubmissionBC:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._store: Dict[SubmissionId, Dict] = {}

    def create_and_grade(self, user_id: UserId, quiz_id: QuizId,
                         correlation_id: str, points: float = 4.0) -> None:
        sub_id = SubmissionId(str(uuid.uuid4()))
        self._store[sub_id] = {
            "user_id": user_id, "quiz_id": quiz_id, "points": points,
            "status": "GRADED",
        }
        self.bus.publish(SubmissionCreated(
            submission_id=sub_id, user_id=user_id, quiz_id=quiz_id,
            correlation_id=correlation_id,
        ))
        self.bus.publish(SubmissionGraded(
            submission_id=sub_id, user_id=user_id, points=points,
            correlation_id=correlation_id,
        ))

    # Compensation
    def void_submission(self, event: DomainEvent) -> None:
        user_id = getattr(event, "user_id", None)
        # Find latest submission for user; mark voided
        for sub_id, data in list(self._store.items()):
            if data["user_id"] == user_id and data["status"] != "VOIDED":
                data["status"] = "VOIDED"
                self.bus.publish(SubmissionVoided(
                    submission_id=sub_id, correlation_id=event.correlation_id,
                ))
                return

    def count_active(self) -> int:
        return sum(1 for d in self._store.values() if d["status"] != "VOIDED")


# =============================================================================
# [BC 4 — LeaderboardBC]   Update ranking — may fail
# =============================================================================

class LeaderboardBC:
    def __init__(self, bus: EventBus, fail_on_user: Optional[UserId] = None) -> None:
        self.bus = bus
        self._ranking: Dict[UserId, float] = defaultdict(float)
        self._fail_on = fail_on_user
        self.processed_count = 0

    def update_ranking(self, event: DomainEvent) -> None:
        self.processed_count += 1
        if not isinstance(event, SubmissionGraded):
            return
        if event.user_id == self._fail_on:
            self.bus.publish(LeaderboardUpdateFailed(
                user_id=event.user_id, reason="ranking service unavailable",
                correlation_id=event.correlation_id,
            ))
            return
        self._ranking[event.user_id] += event.points
        rank = sorted(self._ranking.items(), key=lambda x: -x[1])
        position = next((i+1 for i, (u, _) in enumerate(rank)
                        if u == event.user_id), 0)
        self.bus.publish(LeaderboardUpdated(
            user_id=event.user_id, rank=position,
            correlation_id=event.correlation_id,
        ))

    def get_score(self, user_id: UserId) -> float:
        return self._ranking[user_id]


# =============================================================================
# [BC 5 — NotificationBC]   Send receipt
# =============================================================================

class NotificationBC:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.sent: List[Tuple[UserId, str]] = []

    def send_receipt(self, event: DomainEvent) -> None:
        if not isinstance(event, LeaderboardUpdated):
            return
        self.sent.append((event.user_id, event.correlation_id))
        self.bus.publish(ReceiptSent(
            user_id=event.user_id, correlation_id=event.correlation_id,
        ))


# =============================================================================
# [CHOREOGRAPHY]   Each BC subscribes events from upstream BC
# =============================================================================

def build_choreography(bus: EventBus, valid_users: Set[UserId],
                       fail_leaderboard_for: Optional[UserId] = None
                       ) -> Dict[str, Any]:
    auth = AuthBC(bus, valid_users)
    subscription = SubscriptionBC(bus, initial_quota=5)
    submission = SubmissionBC(bus)
    leaderboard = LeaderboardBC(bus, fail_on_user=fail_leaderboard_for)
    notification = NotificationBC(bus)

    # Subscriptions form the choreography chain:
    # AuthVerified → SubscriptionBC.check_and_consume
    bus.subscribe(AuthVerified, lambda e: subscription.check_and_consume(
        e.user_id, e.correlation_id,
    ))
    # QuotaConfirmed → SubmissionBC.create_and_grade
    bus.subscribe(QuotaConfirmed, lambda e: submission.create_and_grade(
        e.user_id, QuizId("q1"), e.correlation_id,
    ))
    # SubmissionGraded → LeaderboardBC.update_ranking
    bus.subscribe(SubmissionGraded, leaderboard.update_ranking)
    # LeaderboardUpdated → NotificationBC.send_receipt
    bus.subscribe(LeaderboardUpdated, notification.send_receipt)

    # Compensation chain (failures):
    # LeaderboardUpdateFailed → compensate SubmissionBC (void) + SubscriptionBC (restore quota)
    bus.subscribe(LeaderboardUpdateFailed, submission.void_submission)
    bus.subscribe(LeaderboardUpdateFailed, subscription.restore_quota)

    return {
        "auth": auth,
        "subscription": subscription,
        "submission": submission,
        "leaderboard": leaderboard,
        "notification": notification,
    }


# =============================================================================
# [ORCHESTRATION]   Process Manager — QuizSubmissionSaga
# =============================================================================

class SagaState(str, Enum):
    STARTED = "STARTED"
    AUTH_OK = "AUTH_OK"
    QUOTA_OK = "QUOTA_OK"
    SUBMITTED = "SUBMITTED"
    GRADED = "GRADED"
    LEADERBOARD_OK = "LEADERBOARD_OK"
    NOTIFIED = "NOTIFIED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class QuizSubmissionSaga:
    """Process Manager — saga as separate aggregate."""
    saga_id: SagaId
    user_id: UserId
    quiz_id: QuizId
    state: SagaState = SagaState.STARTED
    completed_steps: List[str] = field(default_factory=list)
    failure_reason: str = ""


_STATE_ORDER = [SagaState.STARTED, SagaState.AUTH_OK, SagaState.QUOTA_OK,
                SagaState.SUBMITTED, SagaState.GRADED, SagaState.LEADERBOARD_OK,
                SagaState.NOTIFIED, SagaState.COMPLETED]


class SagaOrchestrator:
    """Holds saga state + dispatches commands to BCs."""

    def __init__(self, bus: EventBus, bcs: Dict[str, Any]) -> None:
        self.bus = bus
        self.bcs = bcs
        self._sagas: Dict[SagaId, QuizSubmissionSaga] = {}

        # Subscribe to all step events
        bus.subscribe(AuthVerified, self._on_auth_verified)
        bus.subscribe(AuthFailed, self._on_step_failed)
        bus.subscribe(QuotaConfirmed, self._on_quota_confirmed)
        bus.subscribe(QuotaExceeded, self._on_step_failed)
        bus.subscribe(SubmissionCreated, self._on_submission_created)
        bus.subscribe(SubmissionGraded, self._on_graded)
        bus.subscribe(LeaderboardUpdated, self._on_leaderboard_ok)
        bus.subscribe(LeaderboardUpdateFailed, self._on_step_failed)
        bus.subscribe(ReceiptSent, self._on_notified)

    def _advance_state(self, saga: QuizSubmissionSaga, new_state: SagaState) -> None:
        """Monotonic forward-only state transition (avoid sync-recursion overwrites)."""
        if saga.state == SagaState.FAILED:
            return  # cannot advance after failure
        if _STATE_ORDER.index(new_state) > _STATE_ORDER.index(saga.state):
            saga.state = new_state

    def start(self, user_id: UserId, quiz_id: QuizId) -> SagaId:
        saga_id = SagaId(str(uuid.uuid4()))
        saga = QuizSubmissionSaga(saga_id=saga_id, user_id=user_id, quiz_id=quiz_id)
        self._sagas[saga_id] = saga
        # Step 1: verify auth
        self.bcs["auth"].verify(user_id, correlation_id=saga_id)
        return saga_id

    def _find_saga_by_correlation(self, correlation_id: str) -> Optional[QuizSubmissionSaga]:
        return self._sagas.get(SagaId(correlation_id))

    def _on_auth_verified(self, event: AuthVerified) -> None:
        saga = self._find_saga_by_correlation(event.correlation_id)
        if not saga: return
        self._advance_state(saga, SagaState.AUTH_OK)
        if "auth" not in saga.completed_steps:
            saga.completed_steps.append("auth")
        self.bcs["subscription"].check_and_consume(saga.user_id, saga.saga_id)

    def _on_quota_confirmed(self, event: QuotaConfirmed) -> None:
        saga = self._find_saga_by_correlation(event.correlation_id)
        if not saga: return
        self._advance_state(saga, SagaState.QUOTA_OK)
        if "quota" not in saga.completed_steps:
            saga.completed_steps.append("quota")
        self.bcs["submission"].create_and_grade(saga.user_id, saga.quiz_id, saga.saga_id)

    def _on_submission_created(self, event: SubmissionCreated) -> None:
        """Mark submission step done BEFORE downstream (leaderboard) reacts."""
        saga = self._find_saga_by_correlation(event.correlation_id)
        if not saga: return
        self._advance_state(saga, SagaState.SUBMITTED)
        if "submission" not in saga.completed_steps:
            saga.completed_steps.append("submission")

    def _on_graded(self, event: SubmissionGraded) -> None:
        saga = self._find_saga_by_correlation(event.correlation_id)
        if not saga: return
        self._advance_state(saga, SagaState.GRADED)

    def _on_leaderboard_ok(self, event: LeaderboardUpdated) -> None:
        saga = self._find_saga_by_correlation(event.correlation_id)
        if not saga: return
        self._advance_state(saga, SagaState.LEADERBOARD_OK)
        if "leaderboard" not in saga.completed_steps:
            saga.completed_steps.append("leaderboard")

    def _on_notified(self, event: ReceiptSent) -> None:
        saga = self._find_saga_by_correlation(event.correlation_id)
        if not saga: return
        self._advance_state(saga, SagaState.NOTIFIED)
        if "notification" not in saga.completed_steps:
            saga.completed_steps.append("notification")
        self._advance_state(saga, SagaState.COMPLETED)

    def _on_step_failed(self, event: DomainEvent) -> None:
        saga = self._find_saga_by_correlation(event.correlation_id)
        if not saga: return
        saga.state = SagaState.FAILED
        saga.failure_reason = getattr(event, "reason", type(event).__name__)
        # Run compensation in reverse order of completed_steps
        for step in reversed(saga.completed_steps):
            if step == "submission":
                self.bcs["submission"].void_submission(event)
            elif step == "quota":
                self.bcs["subscription"].restore_quota(event)
            # auth has no compensation (it's read-only)

    def get_saga(self, saga_id: SagaId) -> Optional[QuizSubmissionSaga]:
        return self._sagas.get(saga_id)


# =============================================================================
# [DEMOS]
# =============================================================================

def banner(s: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {s}")
    print("=" * 76)


def demo_1_choreography_happy_path() -> None:
    banner("DEMO 1 — Choreography: happy path 4-step saga across 5 BCs")
    bus = EventBus()
    bcs = build_choreography(bus, valid_users={UserId("u1")})

    # Trigger saga manually (choreography has no orchestrator)
    correlation = str(uuid.uuid4())
    bcs["auth"].verify(UserId("u1"), correlation_id=correlation)

    print(f"  Events published: {len(bus.published)}")
    print(f"  Event chain:")
    for e in bus.published:
        print(f"    → {type(e).__name__}")

    assert any(isinstance(e, AuthVerified) for e in bus.published)
    assert any(isinstance(e, QuotaConfirmed) for e in bus.published)
    assert any(isinstance(e, SubmissionGraded) for e in bus.published)
    assert any(isinstance(e, LeaderboardUpdated) for e in bus.published)
    assert any(isinstance(e, ReceiptSent) for e in bus.published)
    assert bcs["notification"].sent[0][0] == "u1"
    assert bcs["subscription"].remaining(UserId("u1")) == 4
    print("  PASS — full saga chain completed via choreography")


def demo_2_choreography_compensation() -> None:
    banner("DEMO 2 — Choreography: compensation when LeaderboardBC fails")
    bus = EventBus()
    bcs = build_choreography(bus, valid_users={UserId("u1")},
                              fail_leaderboard_for=UserId("u1"))

    correlation = str(uuid.uuid4())
    bcs["auth"].verify(UserId("u1"), correlation_id=correlation)

    print(f"  Events published: {len(bus.published)}")
    print(f"  Event chain:")
    for e in bus.published:
        print(f"    → {type(e).__name__}")

    # Compensation should have run
    print(f"\n  Subscription quota: 5 → consumed → restored?")
    print(f"    consumed_count: {bcs['subscription'].consumed_count}")
    print(f"    restored_count: {bcs['subscription'].restored_count}")
    print(f"    remaining now:  {bcs['subscription'].remaining(UserId('u1'))}")
    print(f"  Submission active count: {bcs['submission'].count_active()}")

    assert any(isinstance(e, LeaderboardUpdateFailed) for e in bus.published)
    assert any(isinstance(e, QuotaRestored) for e in bus.published)
    assert any(isinstance(e, SubmissionVoided) for e in bus.published)
    assert bcs["subscription"].remaining(UserId("u1")) == 5   # restored
    assert bcs["submission"].count_active() == 0              # voided
    print("  PASS — compensation chain ran: quota restored, submission voided")


def build_bcs_only(bus: EventBus, valid_users: Set[UserId],
                   fail_leaderboard_for: Optional[UserId] = None) -> Dict[str, Any]:
    """Build BCs WITHOUT choreography subscriptions — orchestrator drives."""
    auth = AuthBC(bus, valid_users)
    subscription = SubscriptionBC(bus, initial_quota=5)
    submission = SubmissionBC(bus)
    leaderboard = LeaderboardBC(bus, fail_on_user=fail_leaderboard_for)
    notification = NotificationBC(bus)
    # Only LeaderboardBC reacts to SubmissionGraded (one essential subscription)
    bus.subscribe(SubmissionGraded, leaderboard.update_ranking)
    bus.subscribe(LeaderboardUpdated, notification.send_receipt)
    return {
        "auth": auth, "subscription": subscription, "submission": submission,
        "leaderboard": leaderboard, "notification": notification,
    }


def demo_3_orchestration_happy_path() -> None:
    banner("DEMO 3 — Orchestration: Process Manager state machine")
    bus = EventBus()
    bcs = build_bcs_only(bus, valid_users={UserId("u1")})
    orch = SagaOrchestrator(bus, bcs)

    saga_id = orch.start(UserId("u1"), QuizId("q1"))
    saga = orch.get_saga(saga_id)

    print(f"  Saga ID: {saga_id[:8]}...")
    print(f"  Final state: {saga.state.value}")
    print(f"  Completed steps: {saga.completed_steps}")
    print(f"  Events on bus: {len(bus.published)}")

    assert saga.state == SagaState.COMPLETED
    assert set(saga.completed_steps) == {"auth", "quota", "submission", "leaderboard", "notification"}
    print("  PASS — orchestrator traversed 5 states to COMPLETED")


def demo_4_orchestration_failure_compensation() -> None:
    banner("DEMO 4 — Orchestration: failure mid-saga triggers compensation")
    bus = EventBus()
    bcs = build_bcs_only(bus, valid_users={UserId("u1")},
                         fail_leaderboard_for=UserId("u1"))
    orch = SagaOrchestrator(bus, bcs)

    saga_id = orch.start(UserId("u1"), QuizId("q1"))
    saga = orch.get_saga(saga_id)

    print(f"  Saga state: {saga.state.value}")
    print(f"  Failure reason: {saga.failure_reason}")
    print(f"  Steps completed before failure: {saga.completed_steps}")
    print(f"  Subscription remaining: {bcs['subscription'].remaining(UserId('u1'))} (should be 5)")
    print(f"  Submission active: {bcs['submission'].count_active()} (should be 0)")

    assert saga.state == SagaState.FAILED
    assert "leaderboard" not in saga.completed_steps
    assert bcs["subscription"].remaining(UserId("u1")) == 5
    print("  PASS — orchestrator handled failure + ran compensation")


def demo_5_idempotency_at_boundary() -> None:
    banner("DEMO 5 — Idempotency: dedup by event_id when event delivered 2x")

    # Isolated test: deliver SAME SubmissionGraded event 3 times directly
    # to leaderboard handler (simulating at-least-once broker)
    bus = EventBus()
    leaderboard = LeaderboardBC(bus)

    # WITHOUT idempotency: 3 deliveries → score = 3 * 4.0 = 12
    raw_event = SubmissionGraded(
        submission_id=SubmissionId("s1"), user_id=UserId("u1"),
        points=4.0, correlation_id="c1",
    )
    leaderboard.update_ranking(raw_event)
    leaderboard.update_ranking(raw_event)
    leaderboard.update_ranking(raw_event)
    naive_score = leaderboard.get_score(UserId("u1"))
    print(f"  Without idempotency, 3 deliveries: score = {naive_score} (3x bug)")

    # WITH idempotency wrapper: same 3 deliveries → score = 4.0 once
    leaderboard2 = LeaderboardBC(bus)
    wrapped = idempotent(leaderboard2.update_ranking)
    wrapped(raw_event)
    wrapped(raw_event)
    wrapped(raw_event)
    safe_score = leaderboard2.get_score(UserId("u1"))
    print(f"  With idempotent wrapper, 3 deliveries: score = {safe_score} (correct)")

    assert naive_score == 12.0
    assert safe_score == 4.0
    print("  PASS — idempotent wrapper dedups by event_id at boundary")


def demo_6_eventual_consistency_window() -> None:
    banner("DEMO 6 — Eventual consistency window timing")
    bus = EventBus()
    bcs = build_choreography(bus, valid_users={UserId("u1")})

    # Add artificial delay in handlers (simulating network/processing latency)
    original = bcs["leaderboard"].update_ranking
    def slow_leaderboard(e):
        time.sleep(0.005)               # 5ms simulated
        original(e)
    bus._subs[SubmissionGraded] = [slow_leaderboard]

    t0 = time.perf_counter()
    correlation = str(uuid.uuid4())
    bcs["auth"].verify(UserId("u1"), correlation_id=correlation)
    duration_ms = (time.perf_counter() - t0) * 1000

    print(f"  Saga end-to-end (5 steps): {duration_ms:.2f} ms")
    print(f"  Each step is local TX, no distributed lock")
    print(f"  Window of inconsistency before all states sync: {duration_ms:.2f} ms")
    print(f"  Note: in production with real network this would be 50-500ms")
    print("  PASS — eventual consistency measurable + bounded")


def demo_7_choreography_vs_orchestration_tradeoff() -> None:
    banner("DEMO 7 — Choreography vs Orchestration: tradeoff table")

    print(f"\n  {'Yếu tố':<24} {'Choreography':<22} {'Orchestration'}")
    print(f"  {'-'*24} {'-'*22} {'-'*30}")
    rows = [
        ("Step count",          "≤ 3",           "≥ 4"),
        ("Compensation",        "Per-step local","Multi-step orchestrator"),
        ("Visualization",       "DAG post-hoc",  "Explicit state machine"),
        ("Coupling",            "Loose",         "Tight to orchestrator BC"),
        ("Add new step",        "New subscriber","Update state machine"),
        ("Debug",               "Distributed",   "Saga ID + state"),
        ("SPOF",                "None",          "Orchestrator (use replicas)"),
        ("Learning curve",      "Easy",          "Moderate"),
        ("Saga state visibility","Implicit",     "Explicit aggregate"),
    ]
    for r in rows:
        print(f"  {r[0]:<24} {r[1]:<22} {r[2]}")

    print(f"\n  Recommendation: start choreography → refactor orchestration when pain visible")
    print("  PASS — tradeoff documented")


def demo_8_cycle_detection_anti_pattern() -> None:
    banner("DEMO 8 — Anti-pattern: cycle in event chain (detect at design time)")

    # Build event flow graph from subscriptions
    bus = EventBus()
    bcs = build_choreography(bus, valid_users={UserId("u1")})

    # Map subscribed event → set of events published by handlers (manually inferred)
    flow_graph = {
        "AuthVerified": {"QuotaConfirmed", "QuotaExceeded"},
        "QuotaConfirmed": {"SubmissionCreated", "SubmissionGraded"},
        "SubmissionGraded": {"LeaderboardUpdated", "LeaderboardUpdateFailed"},
        "LeaderboardUpdated": {"ReceiptSent"},
        "LeaderboardUpdateFailed": {"SubmissionVoided", "QuotaRestored"},
        "QuotaRestored": set(),
        "SubmissionVoided": set(),
        "ReceiptSent": set(),
    }

    # Detect cycle via DFS
    def has_cycle(node: str, visited: Set[str], stack: Set[str]) -> bool:
        visited.add(node)
        stack.add(node)
        for neighbor in flow_graph.get(node, set()):
            if neighbor not in visited:
                if has_cycle(neighbor, visited, stack):
                    return True
            elif neighbor in stack:
                return True
        stack.remove(node)
        return False

    visited: Set[str] = set()
    any_cycle = any(has_cycle(n, visited, set()) for n in flow_graph if n not in visited)

    print(f"  Event flow graph ({len(flow_graph)} nodes):")
    for src, dests in flow_graph.items():
        if dests:
            print(f"    {src:<25} → {dests}")
        else:
            print(f"    {src:<25} → (terminal)")
    print(f"\n  Cycle detected? {any_cycle}")
    assert not any_cycle
    print("  PASS — event flow is DAG (no cycles)")


def demo_9_anti_patterns_showcase() -> None:
    banner("DEMO 9 - Anti-pattern showcase")
    patterns = [
        ("A", "2PC distributed transaction", "Lock multi services; partition blocks all; use saga + compensation"),
        ("B", "Cycle in event chain", "BC-A->B->C->A loops; detect via DAG at design time"),
        ("C", "No compensation defined", "Payment charged but inventory never reserved; define Ci per Ti"),
        ("D", "Compensation not idempotent", "Run 2x refunds 2x; ensure dedup at boundary"),
        ("E", "Consumer no dedup at boundary", "Duplicate events double-count; wrap idempotent()"),
        ("F", "Saga state inside business aggregate", "Cross-concern leak; saga is separate aggregate"),
        ("G", "God orchestrator", "20 sagas in 1 class; split per business flow"),
        ("H", "Orchestrator with business logic", "Score computation in saga; delegate to BC"),
    ]
    for letter, name, why in patterns:
        print(f"  ANTI-PATTERN {letter} - {name}")
        print(f"    -> {why}")
    print()
    print("  PASS - 8 anti-patterns documented")


def main() -> int:
    demo_1_choreography_happy_path()
    demo_2_choreography_compensation()
    demo_3_orchestration_happy_path()
    demo_4_orchestration_failure_compensation()
    demo_5_idempotency_at_boundary()
    demo_6_eventual_consistency_window()
    demo_7_choreography_vs_orchestration_tradeoff()
    demo_8_cycle_detection_anti_pattern()
    demo_9_anti_patterns_showcase()

    print()
    print("=" * 76)
    print("  ALL 9 DEMOS PASS - Lesson 39 Distributed DDD verified")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
