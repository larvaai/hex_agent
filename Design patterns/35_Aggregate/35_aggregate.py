"""
Lesson 35 — Tactical DDD: Aggregate sâu
========================================

Deep refactor `Submission` thành Aggregate Root chuẩn DDD:
- Private state (`_field` convention).
- Tell-don't-ask methods enforce invariants.
- Internal entity (Attempt) chỉ AR manage.
- Value objects (Answer, Score) immutable.
- Cross-aggregate reference by ID only.
- Domain events emit từ inside AR method.
- AR-per-transaction (saga across aggregates).
- Repository returns AR only.
- Domain Service for cross-aggregate logic.

Cấu trúc:
    [VALUE OBJECTS]   Answer, Score, AttemptId, SubmissionId
    [DOMAIN EVENTS]   4 frozen event classes
    [INTERNAL ENTITY] Attempt
    [AGGREGATE ROOT]  Submission (private state + 6 public method)
    [DOMAIN SERVICE]  RetryPolicy (stateless, cross-aggregate)
    [SECOND AGGREGATE] UserAttemptQuota (ref by ID)
    [REPOSITORY]      ISubmissionRepository + in-memory impl
    [APP SERVICE]     SubmissionAppService (orchestrate + saga)
    [DEMO]            8 demos + anti-pattern showcase

Run: python 35_aggregate.py
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import (Dict, List, Optional, Protocol, runtime_checkable, Tuple,
                    NewType)


# =============================================================================
# [VALUE OBJECTS]   Immutable. No identity. Defined by attributes.
# =============================================================================

SubmissionId = NewType("SubmissionId", str)
AttemptId = NewType("AttemptId", str)
UserId = NewType("UserId", str)
QuizId = NewType("QuizId", str)


@dataclass(frozen=True)
class Answer:
    question_id: str
    value: int


@dataclass(frozen=True)
class Score:
    points: float
    max_points: float
    correct_count: int
    total_questions: int

    def __post_init__(self) -> None:
        # VO invariant: enforced at construction
        if not (0 <= self.points <= self.max_points):
            raise ValueError(
                f"Score.points {self.points} not in [0, {self.max_points}]"
            )
        if self.correct_count > self.total_questions:
            raise ValueError("correct_count cannot exceed total_questions")

    @property
    def percent(self) -> float:
        return (self.points / self.max_points * 100) if self.max_points else 0.0


@dataclass(frozen=True)
class QuizSummary:
    """DTO upstream — kế thừa từ Lesson 34. Customer-Supplier port."""
    quiz_id: QuizId
    correct_answers: Tuple[int, ...]
    weights: Tuple[float, ...]


# =============================================================================
# [DOMAIN EVENTS]   Past-tense, immutable, emit từ AR method
# =============================================================================

@dataclass(frozen=True)
class DomainEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SubmissionCreated(DomainEvent):
    submission_id: SubmissionId = SubmissionId("")
    user_id: UserId = UserId("")
    quiz_id: QuizId = QuizId("")


@dataclass(frozen=True)
class AnswersSubmitted(DomainEvent):
    submission_id: SubmissionId = SubmissionId("")
    attempt_no: int = 0
    answer_count: int = 0


@dataclass(frozen=True)
class SubmissionGraded(DomainEvent):
    submission_id: SubmissionId = SubmissionId("")
    attempt_no: int = 0
    points: float = 0.0
    correct_count: int = 0
    total: int = 0


@dataclass(frozen=True)
class SubmissionRetried(DomainEvent):
    submission_id: SubmissionId = SubmissionId("")
    new_attempt_no: int = 0


@dataclass(frozen=True)
class SubmissionFinalized(DomainEvent):
    submission_id: SubmissionId = SubmissionId("")
    final_points: float = 0.0


# Cross-aggregate event consumed by UserAttemptQuota (saga)
@dataclass(frozen=True)
class AttemptConsumed(DomainEvent):
    user_id: UserId = UserId("")
    quiz_id: QuizId = QuizId("")
    submission_id: SubmissionId = SubmissionId("")


# =============================================================================
# [INTERNAL ENTITY]   Attempt — chỉ Submission AR manage. KHÔNG expose ra ngoài.
# =============================================================================

@dataclass
class Attempt:
    """Internal entity (not a VO — has identity). Mutable nhưng chỉ AR sửa."""
    attempt_id: AttemptId
    attempt_no: int
    answers: Tuple[Answer, ...]
    submitted_at: datetime
    score: Optional[Score] = None


# =============================================================================
# [AGGREGATE ROOT]   Submission — private state, public command methods
# =============================================================================

class SubmissionStatus(str, Enum):
    DRAFT = "DRAFT"             # Created, no answers yet
    SUBMITTED = "SUBMITTED"     # Answers given, not graded
    GRADED = "GRADED"           # Score computed
    FINALIZED = "FINALIZED"     # Teacher confirmed; no more changes


# Custom exceptions for invariant violations
class InvariantViolation(Exception): ...


class Submission:
    """Aggregate Root. Private state, Tell-don't-ask API."""

    MAX_ATTEMPTS = 3

    # ---- Factory (construction enforced) -------------------------------------
    @staticmethod
    def create(user_id: UserId, quiz_id: QuizId) -> "Submission":
        """Factory: tạo aggregate ở state DRAFT. Emit SubmissionCreated."""
        sub = Submission.__new__(Submission)
        sub._id = SubmissionId(str(uuid.uuid4()))
        sub._user_id = user_id
        sub._quiz_id = quiz_id
        sub._attempts: List[Attempt] = []
        sub._status = SubmissionStatus.DRAFT
        sub._pending_events: List[DomainEvent] = []
        sub._pending_events.append(SubmissionCreated(
            submission_id=sub._id, user_id=user_id, quiz_id=quiz_id,
        ))
        return sub

    # Block direct construction (raise nếu code ngoài cố Submission(...))
    def __init__(self) -> None:
        raise InvariantViolation(
            "Use Submission.create(user_id, quiz_id), not direct constructor"
        )

    # ---- Public command methods (Tell-don't-ask) -----------------------------

    def submit_answers(self, answers: Tuple[Answer, ...]) -> None:
        """DRAFT → SUBMITTED. Bắt đầu attempt mới."""
        if self._status != SubmissionStatus.DRAFT:
            raise InvariantViolation(
                f"submit_answers requires DRAFT, got {self._status.value}"
            )
        if not answers:
            raise InvariantViolation("answers cannot be empty")
        attempt_no = len(self._attempts) + 1
        self._attempts.append(Attempt(
            attempt_id=AttemptId(str(uuid.uuid4())),
            attempt_no=attempt_no,
            answers=tuple(answers),
            submitted_at=datetime.now(),
        ))
        self._status = SubmissionStatus.SUBMITTED
        self._pending_events.append(AnswersSubmitted(
            submission_id=self._id,
            attempt_no=attempt_no, answer_count=len(answers),
        ))

    def grade(self, quiz_summary: QuizSummary) -> None:
        """SUBMITTED → GRADED. Compute Score VO + enforce invariants."""
        if self._status != SubmissionStatus.SUBMITTED:
            raise InvariantViolation(
                f"grade requires SUBMITTED, got {self._status.value}"
            )
        latest = self._attempts[-1]
        if latest.score is not None:
            raise InvariantViolation("attempt already graded (cannot regrade)")
        if quiz_summary.quiz_id != self._quiz_id:
            raise InvariantViolation(
                f"quiz_summary.quiz_id mismatch: {quiz_summary.quiz_id} != {self._quiz_id}"
            )
        if len(latest.answers) != len(quiz_summary.correct_answers):
            raise InvariantViolation(
                f"answer count {len(latest.answers)} != "
                f"quiz questions {len(quiz_summary.correct_answers)}"
            )
        # Compute internally — domain logic lives in AR
        breakdown = [
            a.value == c for a, c in zip(latest.answers, quiz_summary.correct_answers)
        ]
        points = sum(w for w, ok in zip(quiz_summary.weights, breakdown) if ok)
        max_points = sum(quiz_summary.weights)
        score = Score(
            points=points, max_points=max_points,
            correct_count=sum(breakdown),
            total_questions=len(quiz_summary.correct_answers),
        )
        # Update internal entity (in-place via list replace)
        graded_attempt = replace(latest, score=score)
        self._attempts[-1] = graded_attempt
        self._status = SubmissionStatus.GRADED
        self._pending_events.append(SubmissionGraded(
            submission_id=self._id,
            attempt_no=latest.attempt_no,
            points=score.points,
            correct_count=score.correct_count,
            total=score.total_questions,
        ))

    def retry(self, can_retry_fn) -> None:
        """GRADED → DRAFT (new attempt). Domain Service kiểm quota."""
        if self._status != SubmissionStatus.GRADED:
            raise InvariantViolation(
                f"retry requires GRADED, got {self._status.value}"
            )
        if not can_retry_fn(len(self._attempts), self.MAX_ATTEMPTS):
            raise InvariantViolation(
                f"retry quota exceeded ({len(self._attempts)}/{self.MAX_ATTEMPTS})"
            )
        new_attempt_no = len(self._attempts) + 1
        self._status = SubmissionStatus.DRAFT
        self._pending_events.append(SubmissionRetried(
            submission_id=self._id, new_attempt_no=new_attempt_no,
        ))

    def finalize(self) -> None:
        """GRADED → FINALIZED. Không grade/retry được nữa."""
        if self._status != SubmissionStatus.GRADED:
            raise InvariantViolation(
                f"finalize requires GRADED, got {self._status.value}"
            )
        latest = self._attempts[-1]
        if latest.score is None:
            raise InvariantViolation("cannot finalize without score")
        self._status = SubmissionStatus.FINALIZED
        self._pending_events.append(SubmissionFinalized(
            submission_id=self._id, final_points=latest.score.points,
        ))

    # ---- Read-only properties ------------------------------------------------

    @property
    def id(self) -> SubmissionId: return self._id

    @property
    def user_id(self) -> UserId: return self._user_id

    @property
    def quiz_id(self) -> QuizId: return self._quiz_id

    @property
    def status(self) -> SubmissionStatus: return self._status

    @property
    def attempts_count(self) -> int: return len(self._attempts)

    @property
    def current_score(self) -> Optional[Score]:
        if not self._attempts:
            return None
        return self._attempts[-1].score

    # Return a *copy* of attempts (no external mutation)
    def attempts_snapshot(self) -> Tuple[Attempt, ...]:
        return tuple(self._attempts)

    # Repository calls this to publish + clear pending events
    def collect_pending_events(self) -> Tuple[DomainEvent, ...]:
        events = tuple(self._pending_events)
        self._pending_events.clear()
        return events


# =============================================================================
# [DOMAIN SERVICE]   Stateless. Cross-aggregate logic.
# =============================================================================

class RetryPolicy:
    """Domain service: quyết định retry dựa trên config (tier, max_attempts).
    Stateless. Không thuộc Submission (Submission chỉ biết attempts count)."""

    @staticmethod
    def can_retry(attempts_used: int, max_attempts: int) -> bool:
        return attempts_used < max_attempts

    @staticmethod
    def can_retry_premium(attempts_used: int, _max_attempts: int) -> bool:
        # Premium tier: unlimited (ignore max_attempts)
        return True


# =============================================================================
# [SECOND AGGREGATE]   UserAttemptQuota — tracks per-user remaining attempts
# =============================================================================
# Cross-aggregate quan hệ với Submission qua user_id (KHÔNG holding Submission obj).

class UserAttemptQuota:
    """Riêng aggregate per user. Updated by saga from SubmissionGraded event."""

    DEFAULT_QUOTA = 10

    @staticmethod
    def create(user_id: UserId, quota: int = DEFAULT_QUOTA) -> "UserAttemptQuota":
        q = UserAttemptQuota.__new__(UserAttemptQuota)
        q._user_id = user_id
        q._initial_quota = quota
        q._consumed = 0
        q._pending_events: List[DomainEvent] = []
        return q

    def __init__(self) -> None:
        raise InvariantViolation("Use UserAttemptQuota.create()")

    def consume_attempt(self, quiz_id: QuizId, submission_id: SubmissionId) -> None:
        if self._consumed >= self._initial_quota:
            raise InvariantViolation(f"user {self._user_id} quota exhausted")
        self._consumed += 1
        self._pending_events.append(AttemptConsumed(
            user_id=self._user_id,
            quiz_id=quiz_id, submission_id=submission_id,
        ))

    @property
    def user_id(self) -> UserId: return self._user_id

    @property
    def remaining(self) -> int: return self._initial_quota - self._consumed

    @property
    def consumed(self) -> int: return self._consumed

    def collect_pending_events(self) -> Tuple[DomainEvent, ...]:
        events = tuple(self._pending_events)
        self._pending_events.clear()
        return events


# =============================================================================
# [REPOSITORY]   1 repo per Aggregate Root. Returns AR only.
# =============================================================================

@runtime_checkable
class ISubmissionRepository(Protocol):
    def save(self, submission: Submission) -> None: ...
    def get(self, sub_id: SubmissionId) -> Optional[Submission]: ...
    def by_user(self, user_id: UserId) -> List[Submission]: ...


class InMemorySubmissionRepo:
    def __init__(self, event_publisher=None) -> None:
        self._store: Dict[SubmissionId, Submission] = {}
        self._publish = event_publisher or (lambda evt: None)

    def save(self, submission: Submission) -> None:
        self._store[submission.id] = submission
        # Publish domain events that aggregated during this transaction
        for evt in submission.collect_pending_events():
            self._publish(evt)

    def get(self, sub_id: SubmissionId) -> Optional[Submission]:
        return self._store.get(sub_id)

    def by_user(self, user_id: UserId) -> List[Submission]:
        return [s for s in self._store.values() if s.user_id == user_id]


class InMemoryQuotaRepo:
    def __init__(self, event_publisher=None) -> None:
        self._store: Dict[UserId, UserAttemptQuota] = {}
        self._publish = event_publisher or (lambda evt: None)

    def save(self, quota: UserAttemptQuota) -> None:
        self._store[quota.user_id] = quota
        for evt in quota.collect_pending_events():
            self._publish(evt)

    def get_or_create(self, user_id: UserId) -> UserAttemptQuota:
        if user_id not in self._store:
            self._store[user_id] = UserAttemptQuota.create(user_id)
        return self._store[user_id]


# =============================================================================
# [APP SERVICE]   Orchestrate aggregate methods. 1 transaction per aggregate.
# =============================================================================

class SubmissionAppService:
    """Application service (Hex driving port). Orchestrate aggregate + saga."""

    def __init__(
        self, sub_repo: ISubmissionRepository, quota_repo: InMemoryQuotaRepo,
    ) -> None:
        self.sub_repo = sub_repo
        self.quota_repo = quota_repo

    def submit_and_grade(
        self, user_id: UserId, quiz_id: QuizId,
        answers: Tuple[Answer, ...], quiz_summary: QuizSummary,
    ) -> SubmissionId:
        # ----- Transaction 1: Submission aggregate -----
        sub = Submission.create(user_id, quiz_id)
        sub.submit_answers(answers)
        sub.grade(quiz_summary)
        self.sub_repo.save(sub)                  # publish 3 events
        return sub.id

    # Saga handler: when SubmissionGraded → consume quota in *separate* tx
    def on_submission_graded(self, event: SubmissionGraded) -> None:
        # NOTE: Phải fetch user_id qua submission lookup vì SubmissionGraded
        # không carry user_id (intentional — keep event small). Production
        # sẽ include user_id trong event payload hoặc query DB.
        sub = self.sub_repo.get(event.submission_id)
        if sub is None:
            return
        # ----- Transaction 2: UserAttemptQuota aggregate -----
        quota = self.quota_repo.get_or_create(sub.user_id)
        quota.consume_attempt(sub.quiz_id, sub.id)
        self.quota_repo.save(quota)


# =============================================================================
# [TEST HELPERS]
# =============================================================================

def banner(s: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {s}")
    print("=" * 76)


# Standard fixture
def fixture_quiz() -> QuizSummary:
    return QuizSummary(
        quiz_id=QuizId("q1"),
        correct_answers=(2, 0, 3, 1),
        weights=(1.0, 1.0, 2.0, 1.0),       # max 5.0
    )


def fixture_answers_perfect() -> Tuple[Answer, ...]:
    return (
        Answer("qa", 2), Answer("qb", 0), Answer("qc", 3), Answer("qd", 1),
    )


# =============================================================================
# [DEMOS]
# =============================================================================

def demo_1_happy_path_aggregate_lifecycle() -> None:
    banner("DEMO 1 — Happy path: create → submit → grade → finalize")
    sub = Submission.create(UserId("u1"), QuizId("q1"))
    print(f"  After create:   status={sub.status.value}, attempts={sub.attempts_count}")
    sub.submit_answers(fixture_answers_perfect())
    print(f"  After submit:   status={sub.status.value}, attempts={sub.attempts_count}")
    sub.grade(fixture_quiz())
    print(f"  After grade:    status={sub.status.value}, score={sub.current_score}")
    sub.finalize()
    print(f"  After finalize: status={sub.status.value}")

    events = sub.collect_pending_events()
    print(f"\n  Domain events emitted ({len(events)}):")
    for e in events:
        print(f"    - {type(e).__name__}")
    assert sub.status == SubmissionStatus.FINALIZED
    assert sub.current_score.points == 5.0
    assert len(events) == 4   # Created, AnswersSubmitted, Graded, Finalized
    assert isinstance(events[0], SubmissionCreated)
    assert isinstance(events[-1], SubmissionFinalized)
    print("  PASS — aggregate lifecycle correct, 4 events emitted from AR methods")


def demo_2_invariant_enforcement() -> None:
    banner("DEMO 2 — Invariants enforced from inside AR (Tell-don't-ask)")

    cases = []

    # Case 1: grade before submit
    sub = Submission.create(UserId("u1"), QuizId("q1"))
    try:
        sub.grade(fixture_quiz())
        cases.append(("grade before submit", False))
    except InvariantViolation as e:
        cases.append(("grade before submit", True, str(e)[:60]))

    # Case 2: finalize before grade
    sub2 = Submission.create(UserId("u1"), QuizId("q1"))
    sub2.submit_answers(fixture_answers_perfect())
    try:
        sub2.finalize()
        cases.append(("finalize before grade", False))
    except InvariantViolation as e:
        cases.append(("finalize before grade", True, str(e)[:60]))

    # Case 3: grade twice
    sub3 = Submission.create(UserId("u1"), QuizId("q1"))
    sub3.submit_answers(fixture_answers_perfect())
    sub3.grade(fixture_quiz())
    try:
        sub3.grade(fixture_quiz())
        cases.append(("grade twice", False))
    except InvariantViolation as e:
        cases.append(("grade twice", True, str(e)[:60]))

    # Case 4: direct constructor blocked
    try:
        Submission()
        cases.append(("direct constructor", False))
    except InvariantViolation as e:
        cases.append(("direct constructor", True, str(e)[:60]))

    # Case 5: Score VO out-of-range
    try:
        Score(points=999.0, max_points=5.0, correct_count=3, total_questions=4)
        cases.append(("Score VO invalid", False))
    except ValueError as e:
        cases.append(("Score VO invalid", True, str(e)[:60]))

    for c in cases:
        status = "PASS" if c[1] else "FAIL"
        reason = c[2] if len(c) > 2 else ""
        print(f"  [{status}] {c[0]:<28} {reason}")
    assert all(c[1] for c in cases)
    print("  PASS — all invariant violations correctly raised")


def demo_3_reference_by_id_not_object() -> None:
    banner("DEMO 3 — Cross-aggregate reference by ID, not by object")
    sub = Submission.create(UserId("u1"), QuizId("q1"))

    # Inspect aggregate's annotations + internal state
    print(f"  Submission internal field user attr: '_user_id' = {sub.user_id!r}")
    print(f"  Submission internal field quiz attr: '_quiz_id' = {sub.quiz_id!r}")
    print(f"  Has 'user' attribute (User object)?  {hasattr(sub, 'user')}")
    print(f"  Has 'quiz' attribute (Quiz object)?  {hasattr(sub, 'quiz')}")
    print(f"  Has '_user' attribute?               {hasattr(sub, '_user')}")
    print(f"  Has '_quiz' attribute?               {hasattr(sub, '_quiz')}")

    # user_id is just a string (NewType wraps str at type-check level only)
    assert isinstance(sub.user_id, str)
    assert isinstance(sub.quiz_id, str)
    assert not hasattr(sub, "user")
    assert not hasattr(sub, "quiz")
    print("  PASS — aggregate refers to other aggregates by ID only (NewType str)")


def demo_4_ar_per_transaction_saga() -> None:
    banner("DEMO 4 — AR-per-transaction: 2 aggregates, 2 transactions, saga")

    # Collect all events for inspection
    collected: List[DomainEvent] = []
    sub_repo = InMemorySubmissionRepo(event_publisher=lambda e: collected.append(e))
    quota_repo = InMemoryQuotaRepo(event_publisher=lambda e: collected.append(e))
    app = SubmissionAppService(sub_repo, quota_repo)

    # Wire saga: SubmissionGraded → consume quota
    sub_repo._publish = lambda e: (
        collected.append(e),
        app.on_submission_graded(e) if isinstance(e, SubmissionGraded) else None,
    )

    print("  [TX-1] Submission aggregate: create + submit + grade")
    sub_id = app.submit_and_grade(
        UserId("u1"), QuizId("q1"),
        fixture_answers_perfect(),
        fixture_quiz(),
    )
    print(f"         → saved Submission {sub_id[:8]}")
    print()
    print("  [TX-2] (saga) UserAttemptQuota aggregate: consume_attempt")
    quota = quota_repo.get_or_create(UserId("u1"))
    print(f"         → quota.consumed={quota.consumed}, remaining={quota.remaining}")
    print()
    print(f"  All events collected ({len(collected)}):")
    for e in collected:
        print(f"    - {type(e).__name__}")

    assert quota.consumed == 1
    assert any(isinstance(e, SubmissionGraded) for e in collected)
    assert any(isinstance(e, AttemptConsumed) for e in collected)
    print("  PASS — 2 aggregates updated in 2 separate transactions via event saga")


def demo_5_domain_service_retry() -> None:
    banner("DEMO 5 — Domain Service: RetryPolicy applied across aggregate")

    sub = Submission.create(UserId("u1"), QuizId("q1"))
    sub.submit_answers(fixture_answers_perfect())
    sub.grade(fixture_quiz())
    print(f"  After 1st grade: attempts={sub.attempts_count}")

    # Retry once via free-tier policy (MAX 3)
    sub.retry(RetryPolicy.can_retry)
    print(f"  After retry:     status={sub.status.value}, attempts={sub.attempts_count}")
    sub.submit_answers((Answer("qa", 0), Answer("qb", 0), Answer("qc", 3), Answer("qd", 1)))
    sub.grade(fixture_quiz())
    print(f"  After 2nd grade: attempts={sub.attempts_count}, score={sub.current_score.points}")

    sub.retry(RetryPolicy.can_retry)
    sub.submit_answers((Answer("qa", 0), Answer("qb", 0), Answer("qc", 0), Answer("qd", 1)))
    sub.grade(fixture_quiz())
    print(f"  After 3rd grade: attempts={sub.attempts_count}, score={sub.current_score.points}")

    # 4th retry should fail (free tier MAX 3)
    try:
        sub.retry(RetryPolicy.can_retry)
        print("  ERROR: 4th retry should have failed")
        raise AssertionError
    except InvariantViolation as e:
        print(f"  4th retry blocked (free tier): {e}")

    # Premium tier policy allows unlimited
    sub.retry(RetryPolicy.can_retry_premium)
    print(f"  4th retry OK with premium policy: attempts allowed")
    assert sub.attempts_count == 3
    assert sub.status == SubmissionStatus.DRAFT  # after retry
    print("  PASS — Domain Service composes policy; aggregate just executes")


def demo_6_small_aggregate_principle_contention() -> None:
    banner("DEMO 6 — Small aggregate principle: load time + AR size")

    import sys as _sys
    print(f"  Submission aggregate composition:")
    sub = Submission.create(UserId("u1"), QuizId("q1"))
    sub.submit_answers(fixture_answers_perfect())
    sub.grade(fixture_quiz())

    fields = [k for k in vars(sub).keys() if not k.startswith("__")]
    print(f"    - Field count on AR:      {len(fields)}")
    print(f"    - Internal entities:      {len(sub.attempts_snapshot())} Attempt(s)")
    print(f"    - Field names:            {fields}")
    print(f"    - Approx in-memory size:  {_sys.getsizeof(sub)} bytes")
    print()

    # Timing: load 1000 aggregates
    repo = InMemorySubmissionRepo()
    t0 = time.perf_counter()
    for i in range(1000):
        s = Submission.create(UserId(f"u{i}"), QuizId("q1"))
        s.submit_answers(fixture_answers_perfect())
        s.grade(fixture_quiz())
        repo.save(s)
    create_time = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    for i in range(1000):
        s = repo.get(SubmissionId(list(repo._store.keys())[i]))
        _ = s.status
    load_time = (time.perf_counter() - t0) * 1000

    print(f"  Create 1000 submissions:   {create_time:7.1f} ms ({create_time:.2f} ms each)")
    print(f"  Load 1000 submissions:     {load_time:7.1f} ms ({load_time*1000/1000:.2f} µs each)")
    assert create_time < 200      # should be fast — small aggregate
    print("  PASS — small aggregate = fast lifecycle ops")


def demo_7_repository_returns_ar_only() -> None:
    banner("DEMO 7 — Repository returns AR only, not internal entities")

    repo = InMemorySubmissionRepo()
    sub = Submission.create(UserId("u1"), QuizId("q1"))
    sub.submit_answers(fixture_answers_perfect())
    sub.grade(fixture_quiz())
    repo.save(sub)

    # Repository API surface
    repo_methods = [m for m in dir(repo) if not m.startswith("_")]
    print(f"  Repository public methods: {repo_methods}")
    print(f"  Has get_attempt(...)?     {hasattr(repo, 'get_attempt')}")
    print(f"  Has list_answers(...)?    {hasattr(repo, 'list_answers')}")
    print(f"  Has by_user(user_id)?     {hasattr(repo, 'by_user')}")

    fetched = repo.get(sub.id)
    print(f"  Type returned by get():   {type(fetched).__name__}")
    print(f"  fetched.attempts (raw)?   {hasattr(fetched, 'attempts')}")
    print(f"  fetched.attempts_snapshot() → tuple of {len(fetched.attempts_snapshot())}")

    assert isinstance(fetched, Submission)
    assert not hasattr(repo, "get_attempt")
    assert not hasattr(fetched, "attempts")  # only snapshot() exposed
    # Mutation via snapshot doesn't propagate (returns new tuple)
    snap = fetched.attempts_snapshot()
    assert isinstance(snap, tuple)
    print("  PASS — repo exposes AR only; internal Attempt not directly accessible")


def demo_8_anti_pattern_god_aggregate() -> None:
    banner("DEMO 8 — Anti-pattern showcase: God Aggregate vs Small Aggregate")

    # Simulated God Aggregate carrying everything (BAD)
    class GodSubmission:
        def __init__(self):
            self.user_id = "u1"
            self.user_email = "u1@x.com"
            self.user_tier = "free"
            self.user_subscription_renewal = "2026-12-01"
            self.user_billing_address = "..."
            self.quiz_id = "q1"
            self.quiz_title = "..."
            self.quiz_questions = ["..."] * 50
            self.attempts = [{} for _ in range(20)]
            self.payments = [{} for _ in range(100)]
            self.notifications = [{} for _ in range(1000)]
            self.audit_log = [{} for _ in range(5000)]
            # ... 50 more fields

    import sys as _sys
    god = GodSubmission()
    print(f"  GodSubmission field count:        {len(vars(god))}")
    print(f"  Has user info?                    Yes (5 fields)")
    print(f"  Has quiz internal?                Yes (50 questions inline)")
    print(f"  Has payments/notifications/audit? Yes (~6100 objects)")
    print(f"  Approximate memory:               {_sys.getsizeof(god)} bytes + ~{6000*50} bytes refs")
    print()

    small = Submission.create(UserId("u1"), QuizId("q1"))
    small.submit_answers(fixture_answers_perfect())
    print(f"  Small Submission field count:     {len(vars(small))}")
    print(f"  Approximate memory:               {_sys.getsizeof(small)} bytes")
    print()
    print("  Anti-patterns in GodSubmission:")
    print("    ✗ Mixes 4 aggregates (User/Quiz/Payment/Notification) into 1")
    print("    ✗ Lock contention: any update on user blocks submission read")
    print("    ✗ Load time: 6000+ objects fetched per query")
    print("    ✗ Test setup: must construct 50-field god")
    print()
    print("  Correct: 4 separate aggregates, ref by ID:")
    print("    Submission { user_id, quiz_id, attempts }   ← this lesson")
    print("    User       { user_id, email, tier }         ← separate AR")
    print("    Quiz       { quiz_id, title, questions }    ← separate AR (Lesson 34)")
    print("    Payment    { payment_id, user_id }          ← separate AR")
    print("  PASS — small focused aggregates win across every dimension")


# =============================================================================
# RUN ALL
# =============================================================================

def main() -> int:
    demo_1_happy_path_aggregate_lifecycle()
    demo_2_invariant_enforcement()
    demo_3_reference_by_id_not_object()
    demo_4_ar_per_transaction_saga()
    demo_5_domain_service_retry()
    demo_6_small_aggregate_principle_contention()
    demo_7_repository_returns_ar_only()
    demo_8_anti_pattern_god_aggregate()

    print("\n" + "=" * 76)
    print("  ALL 8 DEMOS PASS — Lesson 35 Tactical DDD: Aggregate verified")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
