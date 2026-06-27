"""
Lesson 32 — CQRS + Event Sourcing — Memory Consolidation Duality
================================================================

Refactor `quiz_god.py` thành full CQRS+ES architecture:

    Write side (Hippocampus):
        Command  →  CommandHandler  →  Aggregate  →  Event[]  →  EventStore  →  EventBus

    Read side (Neocortex):
        EventBus  →  Projection.on(event)  →  ReadModel
        Query  →  QueryHandler  →  ReadModel  (KHÔNG load events)

State là DERIVED. Events là PRIMARY. Replay = sleep consolidation.

Run:  python 32_cqrs_es.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Protocol
from uuid import UUID, uuid4
import copy
import time


# =========================================================================
# 1. DOMAIN EVENTS (past-tense facts, immutable)
# =========================================================================
# Event là "đã xảy ra"; tên past-tense; frozen dataclass = không bao giờ mutate
# Tất cả events kế thừa DomainEvent để có metadata chung (id, timestamp, version)


@dataclass(frozen=True)
class DomainEvent:
    """Base. Mỗi event có id (idempotency), aggregate_id, version, timestamp."""
    event_id: UUID = field(default_factory=uuid4)
    aggregate_id: UUID = field(default_factory=uuid4)
    aggregate_version: int = 0
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class QuizSubmitted(DomainEvent):
    user_id: UUID = field(default_factory=uuid4)
    quiz_id: UUID = field(default_factory=uuid4)
    answers: tuple = ()      # tuple để frozen-friendly


@dataclass(frozen=True)
class ScoreCalculated(DomainEvent):
    score: int = 0
    max_score: int = 0


@dataclass(frozen=True)
class SubmissionFinalized(DomainEvent):
    finalized_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ScoreCorrected(DomainEvent):
    """Compensating event — không update event cũ, emit event mới ghi rõ lý do."""
    old_score: int = 0
    new_score: int = 0
    reason: str = ""
    corrected_by: str = ""


# =========================================================================
# 2. COMMANDS (intent — present-imperative, also immutable DTO)
# =========================================================================


@dataclass(frozen=True)
class Command:
    aggregate_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True)
class SubmitQuiz(Command):
    user_id: UUID = field(default_factory=uuid4)
    quiz_id: UUID = field(default_factory=uuid4)
    answers: tuple = ()
    correct_answers: tuple = ()    # injected (would normally come from QuizRepository)


@dataclass(frozen=True)
class FinalizeSubmission(Command):
    pass


@dataclass(frozen=True)
class CorrectScore(Command):
    new_score: int = 0
    reason: str = ""
    corrected_by: str = ""


# =========================================================================
# 3. AGGREGATE — Hippocampal CA3 — invariant guard + emit events
# =========================================================================


class InvariantViolated(Exception):
    """Aggregate refuses command vì vi phạm business rule."""


class QuizSubmissionAggregate:
    """
    State (transient — rebuild from events mỗi command):
        submission_id, user_id, quiz_id, answers, score, is_finalized, version

    Pattern: apply() chỉ mutate state; handle() chỉ emit events.
    Mỗi event mới được emit phải apply() cuối cùng để aggregate biết state mới.
    """

    def __init__(self) -> None:
        self.submission_id: UUID | None = None
        self.user_id: UUID | None = None
        self.quiz_id: UUID | None = None
        self.answers: tuple = ()
        self.score: int | None = None
        self.max_score: int | None = None
        self.is_finalized: bool = False
        self.version: int = 0          # số event đã apply

    # ---------- Apply: rebuild state từ events (also dùng cho replay) ----------
    def apply(self, event: DomainEvent) -> None:
        match event:
            case QuizSubmitted():
                self.submission_id = event.aggregate_id
                self.user_id = event.user_id
                self.quiz_id = event.quiz_id
                self.answers = event.answers
            case ScoreCalculated():
                self.score = event.score
                self.max_score = event.max_score
            case SubmissionFinalized():
                self.is_finalized = True
            case ScoreCorrected():
                self.score = event.new_score
        self.version += 1

    @classmethod
    def from_history(cls, events: Iterable[DomainEvent]) -> "QuizSubmissionAggregate":
        agg = cls()
        for e in events:
            agg.apply(e)
        return agg

    # ---------- Handle: command → events (business rule + invariants) ----------
    def handle(self, command: Command) -> list[DomainEvent]:
        match command:
            case SubmitQuiz():
                if self.submission_id is not None:
                    raise InvariantViolated("submission already exists")
                # Calculate score (domain logic — pure, not I/O)
                correct = sum(
                    1 for a, c in zip(command.answers, command.correct_answers) if a == c
                )
                max_score = len(command.correct_answers)
                base_v = self.version
                return [
                    QuizSubmitted(
                        aggregate_id=command.aggregate_id,
                        aggregate_version=base_v + 1,
                        user_id=command.user_id,
                        quiz_id=command.quiz_id,
                        answers=command.answers,
                    ),
                    ScoreCalculated(
                        aggregate_id=command.aggregate_id,
                        aggregate_version=base_v + 2,
                        score=correct,
                        max_score=max_score,
                    ),
                ]

            case FinalizeSubmission():
                if self.submission_id is None:
                    raise InvariantViolated("submission not yet created")
                if self.is_finalized:
                    raise InvariantViolated("already finalized")
                return [
                    SubmissionFinalized(
                        aggregate_id=command.aggregate_id,
                        aggregate_version=self.version + 1,
                    )
                ]

            case CorrectScore():
                if self.submission_id is None:
                    raise InvariantViolated("submission not exists")
                if not self.is_finalized:
                    raise InvariantViolated(
                        "can only correct after finalized (audit policy)"
                    )
                if self.score == command.new_score:
                    raise InvariantViolated("new score equals old — no-op rejected")
                return [
                    ScoreCorrected(
                        aggregate_id=command.aggregate_id,
                        aggregate_version=self.version + 1,
                        old_score=self.score or 0,
                        new_score=command.new_score,
                        reason=command.reason,
                        corrected_by=command.corrected_by,
                    )
                ]

            case _:
                raise InvariantViolated(f"unknown command {type(command).__name__}")


# =========================================================================
# 4. EVENT STORE — append-only ledger với optimistic concurrency
# =========================================================================


class ConcurrencyConflict(Exception):
    """Stream version on disk khác expected — retry hoặc surface."""


class IEventStore(Protocol):
    def load(self, aggregate_id: UUID) -> list[DomainEvent]: ...
    def append(
        self,
        aggregate_id: UUID,
        expected_version: int,
        new_events: list[DomainEvent],
    ) -> None: ...
    def all_events(self) -> list[DomainEvent]: ...


class InMemoryEventStore:
    """
    Per-stream list + global insertion order (cho replay all).
    Append-only — không có method update/delete.
    """

    def __init__(self) -> None:
        self._streams: dict[UUID, list[DomainEvent]] = defaultdict(list)
        self._global: list[DomainEvent] = []     # cho replay all (audit + projection rebuild)

    def load(self, aggregate_id: UUID) -> list[DomainEvent]:
        return list(self._streams[aggregate_id])

    def append(
        self,
        aggregate_id: UUID,
        expected_version: int,
        new_events: list[DomainEvent],
    ) -> None:
        current = self._streams[aggregate_id]
        if len(current) != expected_version:
            raise ConcurrencyConflict(
                f"expected version {expected_version}, "
                f"actual {len(current)} for {aggregate_id}"
            )
        for e in new_events:
            self._streams[aggregate_id].append(e)
            self._global.append(e)

    def all_events(self) -> list[DomainEvent]:
        return list(self._global)


# =========================================================================
# 5. EVENT BUS — in-process pub-sub với idempotency tracking
# =========================================================================


class EventBus:
    """
    Đơn giản: dict[event_class, list[callback]].
    Idempotency: subscriber tự track event_id đã xử lý (xem Projection).
    Production: thay bằng Kafka/RabbitMQ; interface giữ nguyên (DIP).
    """

    def __init__(self) -> None:
        self._subscribers: dict[type, list[Callable[[DomainEvent], None]]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable[[DomainEvent], None]) -> None:
        self._subscribers[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        for h in self._subscribers.get(type(event), []):
            h(event)


# =========================================================================
# 6. PROJECTIONS — Neocortical read models
# =========================================================================


class Projection(ABC):
    """
    Base class. Idempotency: track set event_id đã apply.
    Trong production: persist last_processed_position vào DB và scan-then-apply.
    """

    def __init__(self) -> None:
        self._processed: set[UUID] = set()

    def _seen(self, event: DomainEvent) -> bool:
        if event.event_id in self._processed:
            return True
        self._processed.add(event.event_id)
        return False

    @abstractmethod
    def on(self, event: DomainEvent) -> None: ...

    def reset(self) -> None:
        """Cho replay/rebuild from scratch."""
        self._processed.clear()
        self._reset_state()

    @abstractmethod
    def _reset_state(self) -> None: ...


class LeaderboardProjection(Projection):
    """
    Read model: total_score per user.
    Subscribe ScoreCalculated + ScoreCorrected (incremental update).
    """

    def __init__(self) -> None:
        super().__init__()
        self._scores: dict[UUID, int] = defaultdict(int)
        self._user_of_aggregate: dict[UUID, UUID] = {}    # aggregate_id → user_id

    def on(self, event: DomainEvent) -> None:
        if self._seen(event):
            return
        match event:
            case QuizSubmitted():
                self._user_of_aggregate[event.aggregate_id] = event.user_id
            case ScoreCalculated():
                user = self._user_of_aggregate.get(event.aggregate_id)
                if user is None:
                    return        # event-of-order; in real system: buffer
                self._scores[user] += event.score
            case ScoreCorrected():
                user = self._user_of_aggregate.get(event.aggregate_id)
                if user is None:
                    return
                self._scores[user] += (event.new_score - event.old_score)

    def top_n(self, n: int) -> list[tuple[UUID, int]]:
        return sorted(self._scores.items(), key=lambda x: -x[1])[:n]

    def score_for(self, user_id: UUID) -> int:
        return self._scores.get(user_id, 0)

    def _reset_state(self) -> None:
        self._scores.clear()
        self._user_of_aggregate.clear()


class UserStatsProjection(Projection):
    """
    Read model: số quiz đã submit + last_quiz_at + avg score per user.
    """

    def __init__(self) -> None:
        super().__init__()
        self._stats: dict[UUID, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total_score": 0, "max_score": 0, "last_at": None}
        )
        self._user_of_aggregate: dict[UUID, UUID] = {}

    def on(self, event: DomainEvent) -> None:
        if self._seen(event):
            return
        match event:
            case QuizSubmitted():
                self._user_of_aggregate[event.aggregate_id] = event.user_id
                s = self._stats[event.user_id]
                s["count"] += 1
                s["last_at"] = event.occurred_at
            case ScoreCalculated():
                user = self._user_of_aggregate.get(event.aggregate_id)
                if user is None:
                    return
                s = self._stats[user]
                s["total_score"] += event.score
                s["max_score"] += event.max_score
            case ScoreCorrected():
                user = self._user_of_aggregate.get(event.aggregate_id)
                if user is None:
                    return
                s = self._stats[user]
                s["total_score"] += (event.new_score - event.old_score)

    def for_user(self, user_id: UUID) -> dict[str, Any]:
        s = dict(self._stats[user_id])
        if s["max_score"] > 0:
            s["accuracy"] = round(s["total_score"] / s["max_score"], 3)
        else:
            s["accuracy"] = None
        return s

    def _reset_state(self) -> None:
        self._stats.clear()
        self._user_of_aggregate.clear()


# =========================================================================
# 7. COMMAND HANDLER — orchestrate load → handle → append → publish
# =========================================================================


class CommandHandler:
    """
    Generic — không biết về business logic. Chỉ orchestrate.
    SRP: một class, một trách nhiệm = "execute command".
    """

    def __init__(self, store: IEventStore, bus: EventBus) -> None:
        self.store = store
        self.bus = bus

    def execute(self, command: Command) -> int:
        events = self.store.load(command.aggregate_id)
        agg = QuizSubmissionAggregate.from_history(events)
        new_events = agg.handle(command)
        self.store.append(command.aggregate_id, agg.version, new_events)
        # Apply on aggregate (chỉ cần nếu handler giữ aggregate cache; ở đây không, nhưng giữ pattern)
        for e in new_events:
            agg.apply(e)
            self.bus.publish(e)
        return agg.version


# =========================================================================
# 8. QUERY HANDLER — đọc thẳng read model, KHÔNG qua aggregate
# =========================================================================


@dataclass(frozen=True)
class GetLeaderboard:
    top_n: int = 10


@dataclass(frozen=True)
class GetUserStats:
    user_id: UUID = field(default_factory=uuid4)


class QueryHandler:
    def __init__(
        self,
        leaderboard: LeaderboardProjection,
        user_stats: UserStatsProjection,
    ) -> None:
        self.leaderboard = leaderboard
        self.user_stats = user_stats

    def handle(self, query: Any) -> Any:
        match query:
            case GetLeaderboard():
                return self.leaderboard.top_n(query.top_n)
            case GetUserStats():
                return self.user_stats.for_user(query.user_id)
            case _:
                raise ValueError(f"unknown query {type(query).__name__}")


# =========================================================================
# 9. WIRING (composition root)
# =========================================================================


def build_app() -> dict[str, Any]:
    store = InMemoryEventStore()
    bus = EventBus()

    leaderboard = LeaderboardProjection()
    user_stats = UserStatsProjection()

    # Subscribe — projections nhận events qua bus
    for evt_cls in (QuizSubmitted, ScoreCalculated, ScoreCorrected):
        bus.subscribe(evt_cls, leaderboard.on)
        bus.subscribe(evt_cls, user_stats.on)

    return {
        "store": store,
        "bus": bus,
        "leaderboard": leaderboard,
        "user_stats": user_stats,
        "cmd": CommandHandler(store, bus),
        "qry": QueryHandler(leaderboard, user_stats),
    }


# =========================================================================
# 10. DEMOS
# =========================================================================


def demo_1_happy_path() -> None:
    print("\n" + "=" * 70)
    print("DEMO 1 — Happy path: submit quiz → leaderboard updated")
    print("=" * 70)
    app = build_app()
    user_a = uuid4()
    user_b = uuid4()
    quiz_1 = uuid4()
    correct = ("A", "C", "B", "D", "A")

    # User A: 4/5
    sub_a = uuid4()
    app["cmd"].execute(SubmitQuiz(
        aggregate_id=sub_a, user_id=user_a, quiz_id=quiz_1,
        answers=("A", "C", "B", "D", "B"), correct_answers=correct,
    ))
    # User B: 5/5
    sub_b = uuid4()
    app["cmd"].execute(SubmitQuiz(
        aggregate_id=sub_b, user_id=user_b, quiz_id=quiz_1,
        answers=correct, correct_answers=correct,
    ))

    print(f"  Events stored total       : {len(app['store'].all_events())}")
    print(f"  Leaderboard top 10        : {[(str(u)[:8], s) for u, s in app['qry'].handle(GetLeaderboard(10))]}")
    print(f"  User A stats              : {app['qry'].handle(GetUserStats(user_a))}")
    print(f"  User B stats              : {app['qry'].handle(GetUserStats(user_b))}")
    assert app["leaderboard"].score_for(user_b) == 5
    assert app["leaderboard"].score_for(user_a) == 4
    print("  [PASS] write side and read side eventually consistent")


def demo_2_replay_rebuild() -> None:
    print("\n" + "=" * 70)
    print("DEMO 2 — Drop projection và REPLAY all events từ store")
    print("=" * 70)
    app = build_app()
    correct = ("A", "B", "C")
    users = [uuid4() for _ in range(3)]
    for u in users:
        app["cmd"].execute(SubmitQuiz(
            aggregate_id=uuid4(), user_id=u, quiz_id=uuid4(),
            answers=("A", "B", "X"), correct_answers=correct,
        ))

    before = sum(s for _, s in app["leaderboard"].top_n(100))
    print(f"  Total score before reset  : {before}")

    # Simulate: leaderboard projection bị corrupt → drop và rebuild
    app["leaderboard"].reset()
    app["user_stats"].reset()
    print(f"  After reset (top_n)       : {app['leaderboard'].top_n(100)}  (empty)")

    # Replay tất cả events từ store qua projection (KHÔNG dùng bus, gọi trực tiếp)
    t0 = time.perf_counter()
    for evt in app["store"].all_events():
        app["leaderboard"].on(evt)
        app["user_stats"].on(evt)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    after = sum(s for _, s in app["leaderboard"].top_n(100))
    print(f"  Total score after replay  : {after}  (events replayed in {elapsed_ms:.2f} ms)")
    assert before == after
    print("  [PASS] projection rebuilt from event store identically")


def demo_3_concurrency_conflict() -> None:
    print("\n" + "=" * 70)
    print("DEMO 3 — Optimistic concurrency conflict (2 worker race)")
    print("=" * 70)
    app = build_app()
    correct = ("A",)
    sub = uuid4()
    user = uuid4()
    app["cmd"].execute(SubmitQuiz(
        aggregate_id=sub, user_id=user, quiz_id=uuid4(),
        answers=("A",), correct_answers=correct,
    ))
    app["cmd"].execute(FinalizeSubmission(aggregate_id=sub))

    # Worker A và B đều load events tại version=3 ([Submitted, Calculated, Finalized])
    events_seen_by_A = app["store"].load(sub)
    events_seen_by_B = app["store"].load(sub)
    agg_A = QuizSubmissionAggregate.from_history(events_seen_by_A)
    agg_B = QuizSubmissionAggregate.from_history(events_seen_by_B)

    # A đi trước
    new_A = agg_A.handle(CorrectScore(aggregate_id=sub, new_score=5, reason="grader",
                                       corrected_by="alice"))
    app["store"].append(sub, agg_A.version, new_A)
    print(f"  Worker A append OK at v={agg_A.version}")

    # B vẫn ôm version cũ → conflict
    new_B = agg_B.handle(CorrectScore(aggregate_id=sub, new_score=10, reason="appeal",
                                       corrected_by="bob"))
    try:
        app["store"].append(sub, agg_B.version, new_B)
        raise RuntimeError("expected ConcurrencyConflict")
    except ConcurrencyConflict as exc:
        print(f"  Worker B refused          : {exc}")

    # B retry: reload, reapply, re-handle, re-append
    fresh_events = app["store"].load(sub)
    agg_B_retry = QuizSubmissionAggregate.from_history(fresh_events)
    new_B_retry = agg_B_retry.handle(
        CorrectScore(aggregate_id=sub, new_score=10, reason="appeal", corrected_by="bob")
    )
    app["store"].append(sub, agg_B_retry.version, new_B_retry)
    print(f"  Worker B retry OK at v={agg_B_retry.version}")

    final = QuizSubmissionAggregate.from_history(app["store"].load(sub))
    print(f"  Final aggregate state     : score={final.score} version={final.version}")
    assert final.score == 10
    assert final.version == 5      # 3 original + 2 corrections
    print("  [PASS] optimistic concurrency control + safe retry path")


def demo_4_score_correction_compensating() -> None:
    print("\n" + "=" * 70)
    print("DEMO 4 — Compensating event: ScoreCorrected (audit nguyên vẹn)")
    print("=" * 70)
    app = build_app()
    user = uuid4()
    sub = uuid4()
    correct = ("A", "B", "C")

    # Submit + finalize
    app["cmd"].execute(SubmitQuiz(
        aggregate_id=sub, user_id=user, quiz_id=uuid4(),
        answers=("A", "B", "X"), correct_answers=correct,
    ))
    app["cmd"].execute(FinalizeSubmission(aggregate_id=sub))
    print(f"  Score after submit        : {app['leaderboard'].score_for(user)}  (=2)")

    # Grader phát hiện quiz có 1 câu mơ hồ → correct lên 3
    app["cmd"].execute(CorrectScore(
        aggregate_id=sub, new_score=3,
        reason="câu 3 ambiguous, accept cả X và C", corrected_by="grader_alice",
    ))
    print(f"  Score after correction    : {app['leaderboard'].score_for(user)}  (=3)")

    # Audit trail: in toàn bộ events của submission này
    print("\n  Audit trail (event log):")
    for i, e in enumerate(app["store"].load(sub), 1):
        print(f"    {i}. {type(e).__name__:25s} v={e.aggregate_version}  {_event_summary(e)}")

    assert app["leaderboard"].score_for(user) == 3
    # Original ScoreCalculated event KHÔNG bị xoá — vẫn còn trong log
    types = [type(e).__name__ for e in app["store"].load(sub)]
    assert "ScoreCalculated" in types
    assert "ScoreCorrected" in types
    print("  [PASS] correction = compensating event, original history preserved")


def demo_5_temporal_query() -> None:
    print("\n" + "=" * 70)
    print("DEMO 5 — Temporal query: leaderboard 'AS OF' event N (time-travel)")
    print("=" * 70)
    app = build_app()
    correct = ("A",)
    user = uuid4()
    submissions: list[UUID] = []

    # 5 quiz submissions cùng user
    for _ in range(5):
        sub = uuid4()
        submissions.append(sub)
        app["cmd"].execute(SubmitQuiz(
            aggregate_id=sub, user_id=user, quiz_id=uuid4(),
            answers=("A",), correct_answers=correct,
        ))
        app["cmd"].execute(FinalizeSubmission(aggregate_id=sub))

    print(f"  Score now (after 5 submits): {app['leaderboard'].score_for(user)}")

    # Time-travel: leaderboard sau khi mới có 2 submission đầu?
    # Build 1 projection rỗng, replay events đến hết submission thứ 2
    travel = LeaderboardProjection()
    cutoff_aggregate_ids = set(submissions[:2])
    for evt in app["store"].all_events():
        if evt.aggregate_id not in cutoff_aggregate_ids:
            continue
        travel.on(evt)
    print(f"  Score 'AS OF' first 2 subs : {travel.score_for(user)}")
    assert travel.score_for(user) == 2

    # Hoặc: replay theo timestamp (mọi event trước thời điểm T)
    middle_events = app["store"].all_events()[: len(app["store"].all_events()) // 2]
    travel2 = LeaderboardProjection()
    for evt in middle_events:
        travel2.on(evt)
    print(f"  Score 'AS OF' first half   : {travel2.score_for(user)}")
    print("  [PASS] temporal queries free vì events là primary, state là derived")


def demo_6_invariant_violations() -> None:
    print("\n" + "=" * 70)
    print("DEMO 6 — Aggregate refuses commands vi phạm invariants")
    print("=" * 70)
    app = build_app()
    sub = uuid4()
    user = uuid4()
    correct = ("A",)

    app["cmd"].execute(SubmitQuiz(
        aggregate_id=sub, user_id=user, quiz_id=uuid4(),
        answers=("A",), correct_answers=correct,
    ))

    # Violation 1: submit lần 2 cùng aggregate
    try:
        app["cmd"].execute(SubmitQuiz(
            aggregate_id=sub, user_id=user, quiz_id=uuid4(),
            answers=("A",), correct_answers=correct,
        ))
        raise RuntimeError("expected InvariantViolated")
    except InvariantViolated as e:
        print(f"  Re-submit refused         : {e}")

    # Violation 2: correct trước khi finalize
    try:
        app["cmd"].execute(CorrectScore(aggregate_id=sub, new_score=99, reason="hack",
                                         corrected_by="x"))
        raise RuntimeError("expected InvariantViolated")
    except InvariantViolated as e:
        print(f"  Correct-before-finalize   : {e}")

    # Finalize then try to finalize again
    app["cmd"].execute(FinalizeSubmission(aggregate_id=sub))
    try:
        app["cmd"].execute(FinalizeSubmission(aggregate_id=sub))
        raise RuntimeError("expected InvariantViolated")
    except InvariantViolated as e:
        print(f"  Double-finalize refused   : {e}")

    # No-op correction (new == old)
    current = QuizSubmissionAggregate.from_history(app["store"].load(sub))
    try:
        app["cmd"].execute(CorrectScore(aggregate_id=sub, new_score=current.score or 0,
                                         reason="x", corrected_by="x"))
        raise RuntimeError("expected InvariantViolated")
    except InvariantViolated as e:
        print(f"  No-op correction refused  : {e}")

    print("  [PASS] aggregate guards business invariants before emitting events")


# ---------- helper ----------
def _event_summary(e: DomainEvent) -> str:
    match e:
        case QuizSubmitted():
            return f"user={str(e.user_id)[:8]} answers={e.answers}"
        case ScoreCalculated():
            return f"score={e.score}/{e.max_score}"
        case SubmissionFinalized():
            return f"finalized_at={e.finalized_at.isoformat()[:19]}"
        case ScoreCorrected():
            return f"{e.old_score}->{e.new_score} reason='{e.reason}' by={e.corrected_by}"
        case _:
            return ""


# =========================================================================
# 11. MAIN
# =========================================================================

if __name__ == "__main__":
    demo_1_happy_path()
    demo_2_replay_rebuild()
    demo_3_concurrency_conflict()
    demo_4_score_correction_compensating()
    demo_5_temporal_query()
    demo_6_invariant_violations()
    print("\n" + "=" * 70)
    print("ALL DEMOS PASSED — CQRS+ES end-to-end")
    print("=" * 70)
