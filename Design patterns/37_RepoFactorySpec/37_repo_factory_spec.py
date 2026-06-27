"""
Lesson 37 — Repository + Factory + Specification
==================================================

3 supporting pattern cho aggregate (Lesson 35):
- Repository: collection-style + Memory & Sqlite impl, returns AR only.
- Factory: create() (new + invariants + event) vs reconstitute() (load + trust state).
- Specification: composable AND/OR/NOT, dùng trong repo + validation + report.

Run: python 37_repo_factory_spec.py
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields as dc_fields
from datetime import datetime, date, timedelta
from enum import Enum
from typing import (Any, Callable, Dict, Generic, List, NewType, Optional,
                    Protocol, Tuple, TypeVar, runtime_checkable)


# =============================================================================
# [DOMAIN PRIMITIVES]   IDs + VOs + Events (recap từ Lesson 35-36)
# =============================================================================

SubmissionId = NewType("SubmissionId", str)
AttemptId = NewType("AttemptId", str)
UserId = NewType("UserId", str)
QuizId = NewType("QuizId", str)


class SubmissionStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    GRADED = "GRADED"
    FINALIZED = "FINALIZED"


@dataclass(frozen=True)
class Answer:
    question_id: str
    value: int


@dataclass(frozen=True)
class Score:
    points: float
    max_points: float

    def __post_init__(self) -> None:
        if not (0 <= self.points <= self.max_points):
            raise ValueError(f"Score points {self.points} out of [0, {self.max_points}]")

    @property
    def percent(self) -> float:
        return (self.points / self.max_points * 100) if self.max_points else 0.0


@dataclass
class Attempt:
    """Internal entity within Submission aggregate."""
    attempt_id: AttemptId
    attempt_no: int
    answers: Tuple[Answer, ...]
    submitted_at: datetime
    score: Optional[Score] = None


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
class SubmissionGraded(DomainEvent):
    submission_id: SubmissionId = SubmissionId("")
    points: float = 0.0


@dataclass(frozen=True)
class SubmissionFinalized(DomainEvent):
    submission_id: SubmissionId = SubmissionId("")


# =============================================================================
# [AGGREGATE ROOT]   Submission — recap minimal version
# =============================================================================

class InvariantViolation(Exception): pass


class Submission:
    """Aggregate Root with private state, public command methods."""

    @staticmethod
    def _bare() -> "Submission":
        """Internal helper for Factory — bare allocation, no init."""
        return Submission.__new__(Submission)

    def __init__(self) -> None:
        raise InvariantViolation("Use SubmissionFactory.create() or .reconstitute()")

    # ---- Command methods (state transitions) --------------------------------
    def submit_answers(self, answers: Tuple[Answer, ...]) -> None:
        if self._status != SubmissionStatus.DRAFT:
            raise InvariantViolation(f"submit requires DRAFT, got {self._status}")
        attempt_no = len(self._attempts) + 1
        self._attempts.append(Attempt(
            attempt_id=AttemptId(str(uuid.uuid4())),
            attempt_no=attempt_no, answers=tuple(answers),
            submitted_at=datetime.now(),
        ))
        self._status = SubmissionStatus.SUBMITTED

    def grade(self, correct_answers: Tuple[int, ...], weights: Tuple[float, ...]) -> None:
        if self._status != SubmissionStatus.SUBMITTED:
            raise InvariantViolation(f"grade requires SUBMITTED, got {self._status}")
        latest = self._attempts[-1]
        breakdown = [a.value == c for a, c in zip(latest.answers, correct_answers)]
        points = sum(w for w, ok in zip(weights, breakdown) if ok)
        max_points = sum(weights)
        score = Score(points=points, max_points=max_points)
        self._attempts[-1] = Attempt(
            attempt_id=latest.attempt_id, attempt_no=latest.attempt_no,
            answers=latest.answers, submitted_at=latest.submitted_at, score=score,
        )
        self._status = SubmissionStatus.GRADED
        self._pending_events.append(SubmissionGraded(
            submission_id=self._id, points=score.points,
        ))

    def finalize(self) -> None:
        if self._status != SubmissionStatus.GRADED:
            raise InvariantViolation(f"finalize requires GRADED, got {self._status}")
        self._status = SubmissionStatus.FINALIZED
        self._pending_events.append(SubmissionFinalized(submission_id=self._id))

    # ---- Read properties -----------------------------------------------------
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
    def submitted_at(self) -> Optional[datetime]:
        return self._attempts[0].submitted_at if self._attempts else None
    @property
    def current_score(self) -> Optional[Score]:
        if not self._attempts: return None
        return self._attempts[-1].score

    def collect_pending_events(self) -> Tuple[DomainEvent, ...]:
        evts = tuple(self._pending_events)
        self._pending_events.clear()
        return evts


# =============================================================================
# [FACTORY]   create() (new) vs reconstitute() (load from state)
# =============================================================================

class SubmissionFactory:
    """DDD Factory: 2 distinct paths for aggregate construction."""

    @staticmethod
    def create(user_id: UserId, quiz_id: QuizId) -> Submission:
        """Path 1: new aggregate. Enforce initial invariants + emit Created event."""
        if not user_id:
            raise ValueError("user_id required for new submission")
        if not quiz_id:
            raise ValueError("quiz_id required for new submission")

        sub = Submission._bare()
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

    @staticmethod
    def reconstitute(state: Dict[str, Any]) -> Submission:
        """Path 2: rebuild from persisted state. TRUST state, NO invariant re-check,
        NO event emission."""
        sub = Submission._bare()
        sub._id = SubmissionId(state["id"])
        sub._user_id = UserId(state["user_id"])
        sub._quiz_id = QuizId(state["quiz_id"])
        sub._status = SubmissionStatus(state["status"])
        sub._attempts = [
            Attempt(
                attempt_id=AttemptId(a["attempt_id"]),
                attempt_no=a["attempt_no"],
                answers=tuple(Answer(**ans) for ans in a["answers"]),
                submitted_at=datetime.fromisoformat(a["submitted_at"]),
                score=(Score(**a["score"]) if a.get("score") else None),
            )
            for a in state.get("attempts", [])
        ]
        sub._pending_events = []                 # ← KEY: no events on reconstitute
        return sub

    @staticmethod
    def to_state(sub: Submission) -> Dict[str, Any]:
        """Serialize aggregate to portable dict (for persistence)."""
        return {
            "id": sub.id,
            "user_id": sub.user_id,
            "quiz_id": sub.quiz_id,
            "status": sub.status.value,
            "attempts": [
                {
                    "attempt_id": a.attempt_id,
                    "attempt_no": a.attempt_no,
                    "answers": [{"question_id": ans.question_id, "value": ans.value}
                                for ans in a.answers],
                    "submitted_at": a.submitted_at.isoformat(),
                    "score": (
                        {"points": a.score.points, "max_points": a.score.max_points}
                        if a.score else None
                    ),
                }
                for a in sub._attempts
            ],
        }


# =============================================================================
# [SPECIFICATION]   Composable predicate over any T
# =============================================================================

T = TypeVar("T")


class Specification(Generic[T], ABC):
    """Base class with composition operators."""

    @abstractmethod
    def is_satisfied_by(self, obj: T) -> bool: ...

    def __and__(self, other: "Specification[T]") -> "Specification[T]":
        return AndSpec(self, other)

    def __or__(self, other: "Specification[T]") -> "Specification[T]":
        return OrSpec(self, other)

    def __invert__(self) -> "Specification[T]":
        return NotSpec(self)


class AndSpec(Specification[T]):
    def __init__(self, left: Specification[T], right: Specification[T]):
        self.left, self.right = left, right
    def is_satisfied_by(self, obj: T) -> bool:
        return self.left.is_satisfied_by(obj) and self.right.is_satisfied_by(obj)


class OrSpec(Specification[T]):
    def __init__(self, left: Specification[T], right: Specification[T]):
        self.left, self.right = left, right
    def is_satisfied_by(self, obj: T) -> bool:
        return self.left.is_satisfied_by(obj) or self.right.is_satisfied_by(obj)


class NotSpec(Specification[T]):
    def __init__(self, inner: Specification[T]):
        self.inner = inner
    def is_satisfied_by(self, obj: T) -> bool:
        return not self.inner.is_satisfied_by(obj)


# ---- Domain-specific specifications over Submission --------------------------

class PassingSpec(Specification[Submission]):
    """Score percent ≥ threshold (default 60%)."""
    def __init__(self, min_percent: float = 60.0):
        self.min_percent = min_percent
    def is_satisfied_by(self, sub: Submission) -> bool:
        score = sub.current_score
        return score is not None and score.percent >= self.min_percent


class FinalizedSpec(Specification[Submission]):
    def is_satisfied_by(self, sub: Submission) -> bool:
        return sub.status == SubmissionStatus.FINALIZED


class SubmittedAfterSpec(Specification[Submission]):
    def __init__(self, cutoff: datetime):
        self.cutoff = cutoff
    def is_satisfied_by(self, sub: Submission) -> bool:
        return sub.submitted_at is not None and sub.submitted_at >= self.cutoff


class AttemptsAtLeastSpec(Specification[Submission]):
    def __init__(self, n: int):
        self.n = n
    def is_satisfied_by(self, sub: Submission) -> bool:
        return sub.attempts_count >= self.n


class QuizIdSpec(Specification[Submission]):
    def __init__(self, quiz_id: QuizId):
        self.quiz_id = quiz_id
    def is_satisfied_by(self, sub: Submission) -> bool:
        return sub.quiz_id == self.quiz_id


# =============================================================================
# [REPOSITORY]   Collection-style. Protocol + Memory + Sqlite impl.
# =============================================================================

@runtime_checkable
class ISubmissionRepository(Protocol):
    def save(self, sub: Submission) -> None: ...
    def get(self, sub_id: SubmissionId) -> Optional[Submission]: ...
    def remove(self, sub_id: SubmissionId) -> None: ...
    def find_satisfying(self, spec: Specification[Submission]) -> List[Submission]: ...
    def count(self) -> int: ...


EventPublisher = Callable[[DomainEvent], None]


class InMemorySubmissionRepository:
    """Collection-oriented in-memory repo. Publishes pending events on save."""

    def __init__(self, publisher: Optional[EventPublisher] = None) -> None:
        self._store: Dict[SubmissionId, Submission] = {}
        self._publish = publisher or (lambda e: None)

    def save(self, sub: Submission) -> None:
        self._store[sub.id] = sub
        for e in sub.collect_pending_events():
            self._publish(e)

    def get(self, sub_id: SubmissionId) -> Optional[Submission]:
        return self._store.get(sub_id)

    def remove(self, sub_id: SubmissionId) -> None:
        self._store.pop(sub_id, None)

    def find_satisfying(self, spec: Specification[Submission]) -> List[Submission]:
        return [s for s in self._store.values() if spec.is_satisfied_by(s)]

    def count(self) -> int:
        return len(self._store)


class SqliteSubmissionRepository:
    """SQLite impl. Serializes aggregate via Factory.to_state() ↔ reconstitute()."""

    def __init__(self, db_path: str = ":memory:", publisher: Optional[EventPublisher] = None) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS submissions(
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                quiz_id TEXT NOT NULL,
                status TEXT NOT NULL,
                state_json TEXT NOT NULL
            )
        """)
        self.conn.commit()
        self._publish = publisher or (lambda e: None)

    def save(self, sub: Submission) -> None:
        state = SubmissionFactory.to_state(sub)
        self.conn.execute(
            "INSERT OR REPLACE INTO submissions(id, user_id, quiz_id, status, state_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (sub.id, sub.user_id, sub.quiz_id, sub.status.value, json.dumps(state)),
        )
        self.conn.commit()
        for e in sub.collect_pending_events():
            self._publish(e)

    def get(self, sub_id: SubmissionId) -> Optional[Submission]:
        row = self.conn.execute(
            "SELECT state_json FROM submissions WHERE id=?", (sub_id,)
        ).fetchone()
        if not row:
            return None
        return SubmissionFactory.reconstitute(json.loads(row[0]))

    def remove(self, sub_id: SubmissionId) -> None:
        self.conn.execute("DELETE FROM submissions WHERE id=?", (sub_id,))
        self.conn.commit()

    def find_satisfying(self, spec: Specification[Submission]) -> List[Submission]:
        # Note: in real prod with large tables, translate spec → SQL. Here we load all.
        rows = self.conn.execute("SELECT state_json FROM submissions").fetchall()
        all_subs = [SubmissionFactory.reconstitute(json.loads(r[0])) for r in rows]
        return [s for s in all_subs if spec.is_satisfied_by(s)]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]


# =============================================================================
# [DEMO HELPERS]
# =============================================================================

def banner(s: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {s}")
    print("=" * 76)


CORRECT = (2, 0, 3, 1)
WEIGHTS = (1.0, 1.0, 2.0, 1.0)             # max 5.0
PERFECT = tuple(Answer(f"q{i}", v) for i, v in enumerate(CORRECT))
# HALF: get Q0 correct + Q3 correct (miss heavy Q2) → 2.0/5.0 = 40%
HALF = (Answer("q0", 2), Answer("q1", 9), Answer("q2", 9), Answer("q3", 1))
ZERO = tuple(Answer(f"q{i}", 9) for i in range(len(CORRECT)))


def fixture_submission(user_id: str, quiz_id: str, answers: Tuple[Answer, ...] = PERFECT,
                       finalize: bool = False) -> Submission:
    sub = SubmissionFactory.create(UserId(user_id), QuizId(quiz_id))
    sub.submit_answers(answers)
    sub.grade(CORRECT, WEIGHTS)
    if finalize:
        sub.finalize()
    return sub


# =============================================================================
# [DEMOS]
# =============================================================================

def demo_1_repository_crud() -> None:
    banner("DEMO 1 — Repository CRUD (save/get/remove/count)")
    events: List[DomainEvent] = []
    repo = InMemorySubmissionRepository(publisher=lambda e: events.append(e))

    sub = fixture_submission("u1", "q1")
    repo.save(sub)
    print(f"  After save: count={repo.count()}, events published={len(events)}")
    print(f"  Events: {[type(e).__name__ for e in events]}")

    fetched = repo.get(sub.id)
    print(f"  get() returns: {type(fetched).__name__}, status={fetched.status.value}")
    assert fetched is sub or fetched.id == sub.id     # In-memory: same object

    repo.remove(sub.id)
    print(f"  After remove: count={repo.count()}")
    assert repo.count() == 0
    assert repo.get(sub.id) is None
    print("  PASS — Repository CRUD complete")


def demo_2_repo_swap_memory_sqlite_parity() -> None:
    banner("DEMO 2 — Repository abstraction: Memory ↔ Sqlite produce same result")

    def run_with(repo: ISubmissionRepository) -> Dict[str, Any]:
        for i, ans in enumerate([PERFECT, HALF, ZERO, PERFECT, HALF]):
            sub = fixture_submission(f"u{i}", "q1", ans, finalize=(i % 2 == 0))
            repo.save(sub)
        passing = PassingSpec(60.0)
        return {
            "count": repo.count(),
            "passing_count": len(repo.find_satisfying(passing)),
        }

    mem = InMemorySubmissionRepository()
    sql = SqliteSubmissionRepository(":memory:")
    mem_result = run_with(mem)
    sql_result = run_with(sql)

    print(f"  Memory result: {mem_result}")
    print(f"  Sqlite result: {sql_result}")
    assert mem_result == sql_result
    print("  PASS — same code works against both impl (Hex driven port)")


def demo_3_repo_returns_ar_only() -> None:
    banner("DEMO 3 — Repository returns AR only, hides internal Attempt")

    repo = InMemorySubmissionRepository()
    sub = fixture_submission("u1", "q1")
    repo.save(sub)

    pub = [m for m in dir(repo) if not m.startswith("_")]
    print(f"  Public methods on repo: {pub}")
    print(f"  Has get_attempts()? {hasattr(repo, 'get_attempts')}")
    print(f"  Has get_internal()? {hasattr(repo, 'get_internal')}")
    print(f"  Has all_attempts()? {hasattr(repo, 'all_attempts')}")
    assert all(not hasattr(repo, m) for m in ["get_attempts", "get_internal", "all_attempts"])

    fetched = repo.get(sub.id)
    print(f"  Fetched type: {type(fetched).__name__}")
    assert isinstance(fetched, Submission)
    print("  PASS — repo surface exposes only AR-level API")


def demo_4_factory_create_vs_reconstitute() -> None:
    banner("DEMO 4 — Factory.create() vs Factory.reconstitute() — distinct paths")

    # CREATE: emits SubmissionCreated event
    sub = SubmissionFactory.create(UserId("u1"), QuizId("q1"))
    sub.submit_answers(PERFECT)
    sub.grade(CORRECT, WEIGHTS)
    create_events = sub.collect_pending_events()
    print(f"  create() flow events: {[type(e).__name__ for e in create_events]}")
    assert any(isinstance(e, SubmissionCreated) for e in create_events)
    assert any(isinstance(e, SubmissionGraded) for e in create_events)

    # Serialize state
    state = SubmissionFactory.to_state(sub)
    print(f"  Serialized state keys: {list(state.keys())}")
    print(f"  Persisted status: {state['status']}, attempts: {len(state['attempts'])}")

    # RECONSTITUTE: trust state, NO new events
    restored = SubmissionFactory.reconstitute(state)
    restored_events = restored.collect_pending_events()
    print(f"  reconstitute() events emitted: {len(restored_events)} (expected: 0)")
    print(f"  Restored status: {restored.status.value}, score percent: {restored.current_score.percent}%")
    assert len(restored_events) == 0
    assert restored.status == sub.status
    assert restored.id == sub.id
    print("  PASS — create emits events, reconstitute is silent + no invariant check")


def demo_5_factory_reconstitute_skips_invariants() -> None:
    banner("DEMO 5 — Factory.reconstitute bypasses invariants (load FINALIZED directly)")

    # Try to create + finalize via normal flow
    state_finalized = {
        "id": "s1",
        "user_id": "u1",
        "quiz_id": "q1",
        "status": "FINALIZED",                  # ← skip DRAFT/SUBMITTED/GRADED
        "attempts": [{
            "attempt_id": "a1", "attempt_no": 1,
            "answers": [{"question_id": "q0", "value": 2}],
            "submitted_at": datetime.now().isoformat(),
            "score": {"points": 1.0, "max_points": 1.0},
        }],
    }

    # Direct create+submit+grade would FAIL to set FINALIZED without finalize()
    # But reconstitute trusts the persisted state:
    restored = SubmissionFactory.reconstitute(state_finalized)
    print(f"  Reconstituted status: {restored.status.value}")
    print(f"  Score: {restored.current_score}")
    assert restored.status == SubmissionStatus.FINALIZED

    # On the other hand, trying to invoke command method enforces invariants
    try:
        restored.finalize()                     # already FINALIZED
        assert False, "should fail"
    except InvariantViolation as e:
        print(f"  finalize() on already-FINALIZED raises: {e}")
    print("  PASS — reconstitute trusts state; commands still enforce invariants")


def demo_6_specification_basic() -> None:
    banner("DEMO 6 — Specification: simple query via is_satisfied_by")

    repo = InMemorySubmissionRepository()
    repo.save(fixture_submission("u1", "q1", PERFECT, finalize=True))   # 100%
    repo.save(fixture_submission("u2", "q1", HALF, finalize=False))      # 40%
    repo.save(fixture_submission("u3", "q1", ZERO, finalize=False))      # 0%

    passing = PassingSpec(60.0)
    finalized = FinalizedSpec()

    passing_subs = repo.find_satisfying(passing)
    finalized_subs = repo.find_satisfying(finalized)

    print(f"  Passing (≥60%): {len(passing_subs)} → users {[s.user_id for s in passing_subs]}")
    print(f"  Finalized:      {len(finalized_subs)} → users {[s.user_id for s in finalized_subs]}")
    assert len(passing_subs) == 1 and passing_subs[0].user_id == "u1"
    assert len(finalized_subs) == 1 and finalized_subs[0].user_id == "u1"
    print("  PASS — basic specs filter correctly")


def demo_7_specification_composition() -> None:
    banner("DEMO 7 — Specification composition: & | ~ operators")

    repo = InMemorySubmissionRepository()
    yesterday = datetime.now() - timedelta(days=1)
    week_ago = datetime.now() - timedelta(days=7)

    s1 = fixture_submission("u1", "q1", PERFECT, finalize=True)         # 100% + finalized
    s2 = fixture_submission("u2", "q1", HALF)                             # 40% + not finalized
    s3 = fixture_submission("u3", "q2", PERFECT, finalize=True)          # 100% + diff quiz
    s4 = fixture_submission("u4", "q1", PERFECT)                         # 100% + not finalized
    for s in (s1, s2, s3, s4):
        repo.save(s)

    passing = PassingSpec(60.0)
    finalized = FinalizedSpec()
    q1_only = QuizIdSpec(QuizId("q1"))

    # Composition demos
    awarded = passing & finalized & q1_only          # passing AND finalized AND q1
    pending = passing & ~finalized                    # passing but NOT finalized
    any_q1 = q1_only | finalized                      # q1 OR finalized

    print(f"  awarded (passing & finalized & q1): {[s.user_id for s in repo.find_satisfying(awarded)]}")
    print(f"  pending (passing & ~finalized):     {[s.user_id for s in repo.find_satisfying(pending)]}")
    print(f"  any_q1 (q1 | finalized):            {[s.user_id for s in repo.find_satisfying(any_q1)]}")

    assert [s.user_id for s in repo.find_satisfying(awarded)] == ["u1"]
    assert [s.user_id for s in repo.find_satisfying(pending)] == ["u4"]
    # q1 or finalized → u1, u2, u3, u4 (u3 q2 but finalized; rest q1)
    assert len(repo.find_satisfying(any_q1)) == 4
    print("  PASS — &, |, ~ compose specs correctly")


def demo_8_specification_reuse_3_contexts() -> None:
    banner("DEMO 8 — Specification reuse: same predicate in repo + validation + report")

    repo = InMemorySubmissionRepository()
    for i in range(5):
        ans = PERFECT if i < 3 else (HALF if i == 3 else ZERO)
        repo.save(fixture_submission(f"u{i}", "q1", ans, finalize=(i < 2)))

    award_eligible = PassingSpec(60.0) & FinalizedSpec()

    # USE 1: Repository query
    eligible = repo.find_satisfying(award_eligible)
    print(f"  Repo query: {len(eligible)} eligible users")

    # USE 2: Domain validation (single object)
    test_sub = fixture_submission("u_test", "q1", PERFECT, finalize=True)
    is_eligible = award_eligible.is_satisfied_by(test_sub)
    print(f"  Domain validation (u_test): is_award_eligible={is_eligible}")

    # USE 3: Report generation (counts)
    counts = {
        "total": repo.count(),
        "passing": len(repo.find_satisfying(PassingSpec(60.0))),
        "finalized": len(repo.find_satisfying(FinalizedSpec())),
        "award_eligible": len(eligible),
    }
    print(f"  Report:        {counts}")

    assert len(eligible) == 2
    assert is_eligible
    print("  PASS — same Specification used in 3 different contexts (DRY)")


def demo_9_anti_patterns_showcase() -> None:
    banner("DEMO 9 — Anti-pattern showcase")
    print("""
    ANTI-PATTERN A — Repository returns internal entity:
        class SubmissionRepo:
            def get_attempts(self, sub_id): ...      # ✗ exposes Attempt
        # Caller can mutate Attempt → bypass aggregate invariants

    ANTI-PATTERN B — Factory.reconstitute re-runs invariants:
        @staticmethod
        def reconstitute(state):
            sub = Submission.__new__(...)
            sub.status = DRAFT                       # ✗ reset state
            sub.submit_answers(...)                  # ✗ re-execute commands
            sub.grade(...)
        # → emits SubmissionCreated/Graded twice; can't load GRADED state

    ANTI-PATTERN C — Factory.create skips invariants:
        @staticmethod
        def create(uid, qid, status="DRAFT"):
            sub = Submission.__new__(...)
            sub._status = status                     # ✗ caller can inject any status
        # → orphan aggregate state inconsistent with business rule

    ANTI-PATTERN D — Specification with side effect:
        class PassingSpec:
            def is_satisfied_by(self, sub):
                self.eval_count += 1                 # ✗ mutates state
                log.info(...)                        # ✗ side effect
        # Composition breaks (eval order matters)

    ANTI-PATTERN E — Spec not composable (different method name):
        class PassingSpec:
            def check(self, sub): ...                # ✗ not is_satisfied_by
        # Can't combine with other specs

    ANTI-PATTERN F — Rule rải (anti-Specification):
        # In repo:   [s for s in subs if s.score > 60]
        # In policy: if score > 60: ...
        # In report: passing = [s for s in subs if s.score > 60]
        # ✗ 3 copies — when "passing" def changes, fix 3 places

    ANTI-PATTERN G — God Repository (1 repo for many AR):
        class CoreRepository:
            def save_submission(...): ...
            def save_user(...): ...
            def save_quiz(...): ...
        # ✗ couples 3 AR; transaction scope unclear; testing nightmare
    """)


# =============================================================================
# RUN ALL
# =============================================================================

def main() -> int:
    demo_1_repository_crud()
    demo_2_repo_swap_memory_sqlite_parity()
    demo_3_repo_returns_ar_only()
    demo_4_factory_create_vs_reconstitute()
    demo_5_factory_reconstitute_skips_invariants()
    demo_6_specification_basic()
    demo_7_specification_composition()
    demo_8_specification_reuse_3_contexts()
    demo_9_anti_patterns_showcase()

    print("\n" + "=" * 76)
    print("  ALL 9 DEMOS PASS - Lesson 37 Repository + Factory + Specification verified")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
