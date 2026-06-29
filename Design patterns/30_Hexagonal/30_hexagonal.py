"""
Lesson 30 — Hexagonal Architecture (Ports & Adapters)
=====================================================

Refactor `quiz_god.py` từ Lesson 28 (DIP) lên Hexagonal:
    - 1 lõi domain thuần Python (không sqlite, không smtp, không http).
    - 2 driven port: ISubmissionRepository, INotifier, + IClock (giúp test).
    - 1 driving port: IQuizApplicationService — use case của hệ.
    - 3 driving adapter: HTTPController, CLIController, EventConsumer.
    - 5 driven adapter: MemoryRepo, SqliteRepo (in-memory db), LogNotifier,
                       EmailNotifier (mock), RetryNotifier (Decorator wrap).
    - 1 composition root: build_app(env).

Demo (chạy cuối file):
    1. Happy path qua HTTP (Memory + Log).
    2. *Cùng core* qua CLI và qua Event consumer — không sửa 1 dòng domain.
    3. Swap driven adapter Memory ↔ Sqlite — core test không thay đổi.
    4. Decorator wrap: RetryNotifier wrap EmailNotifier flaky.
    5. Test pure (no I/O) so với test integration — đo timing.

Cách chạy:
    python 30_hexagonal.py

Cấu trúc package mô phỏng (cùng 1 file để dễ chạy):
    [DOMAIN]    Pure logic, ports, app service
    [INFRA]     Driven adapters
    [WEB/CLI/EVT] Driving adapters
    [BOOTSTRAP] Composition root
    [DEMO]      5 kịch bản
"""

from __future__ import annotations

import sqlite3
import time
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable, List, Dict, Any, Optional


# =============================================================================
# [DOMAIN] — Lõi thuần Python. KHÔNG import sqlite3/smtplib/flask ở đây.
# (sqlite3 import ở trên file chỉ vì để dùng trong [INFRA] adapter; trong
#  cấu trúc thật là 2 file/package riêng.)
# =============================================================================

# ---- Entities ----------------------------------------------------------------

@dataclass(frozen=True)
class Question:
    qid: str
    correct_answer: int        # đáp án đúng (mock: chỉ số 0-3)
    weight: float = 1.0


@dataclass(frozen=True)
class SubmissionDTO:
    """DTO ngoài-vào — driving adapter parse vào DTO này, không phải Submission."""
    user_id: str
    answers: List[int]         # answers[i] cho question[i]


@dataclass(frozen=True)
class Submission:
    """Entity domain — có submitted_at để snapshot."""
    user_id: str
    answers: List[int]
    submitted_at: datetime


@dataclass(frozen=True)
class ScoreResult:
    score: float
    correct_count: int
    total: int
    breakdown: List[bool] = field(default_factory=list)

    def to_dto(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "correct": self.correct_count,
            "total": self.total,
        }


# ---- Driven ports (do core sở hữu) -------------------------------------------

@runtime_checkable
class ISubmissionRepository(Protocol):
    """Lõi cần persist submission. KHÔNG biết là SQL hay file hay memory."""
    def save(self, submission: Submission) -> int: ...
    def find_by_user(self, user_id: str) -> List[Submission]: ...
    def count(self) -> int: ...


@runtime_checkable
class INotifier(Protocol):
    """Lõi cần báo cho user. KHÔNG biết là email/sms/push/log."""
    def send_receipt(self, user_id: str, score: ScoreResult) -> None: ...


@runtime_checkable
class IClock(Protocol):
    """Lõi cần thời gian. Tách ra để test deterministic được."""
    def now(self) -> datetime: ...


# ---- Domain service (pure) ---------------------------------------------------

class ScoringService:
    """Logic chấm điểm thuần. Không I/O, không thời gian."""

    def __init__(self, questions: List[Question]) -> None:
        self.questions = questions

    def score(self, submission: Submission) -> ScoreResult:
        if len(submission.answers) != len(self.questions):
            raise ValueError(
                f"Expected {len(self.questions)} answers, "
                f"got {len(submission.answers)}"
            )
        breakdown = [
            ans == q.correct_answer
            for ans, q in zip(submission.answers, self.questions)
        ]
        weighted = sum(
            q.weight for q, ok in zip(self.questions, breakdown) if ok
        )
        return ScoreResult(
            score=weighted,
            correct_count=sum(breakdown),
            total=len(self.questions),
            breakdown=breakdown,
        )


# ---- Driving port (use case) -------------------------------------------------

@runtime_checkable
class IQuizApplicationService(Protocol):
    """Driving port — cái mà driving adapter (HTTP/CLI/EVT) gọi vào."""
    def submit_quiz(self, dto: SubmissionDTO) -> Dict[str, Any]: ...
    def get_history(self, user_id: str) -> List[Dict[str, Any]]: ...


# ---- Application service (orchestrator) --------------------------------------

class QuizApplicationService:
    """Implement driving port. Compose driven port + domain service."""

    def __init__(
        self,
        repo: ISubmissionRepository,
        notifier: INotifier,
        scoring: ScoringService,
        clock: IClock,
    ) -> None:
        self.repo = repo
        self.notifier = notifier
        self.scoring = scoring
        self.clock = clock

    def submit_quiz(self, dto: SubmissionDTO) -> Dict[str, Any]:
        sub = Submission(
            user_id=dto.user_id,
            answers=dto.answers,
            submitted_at=self.clock.now(),
        )
        result = self.scoring.score(sub)
        sub_id = self.repo.save(sub)
        self.notifier.send_receipt(dto.user_id, result)
        return {"submission_id": sub_id, **result.to_dto()}

    def get_history(self, user_id: str) -> List[Dict[str, Any]]:
        subs = self.repo.find_by_user(user_id)
        return [
            {
                "user_id": s.user_id,
                "answers": list(s.answers),
                "submitted_at": s.submitted_at.isoformat(),
            }
            for s in subs
        ]


# =============================================================================
# [INFRA] — Driven adapters. Implement port của domain.
# =============================================================================

class MemorySubmissionRepo:
    """In-memory adapter — lý tưởng cho test."""

    def __init__(self) -> None:
        self._store: List[Submission] = []

    def save(self, submission: Submission) -> int:
        self._store.append(submission)
        return len(self._store)

    def find_by_user(self, user_id: str) -> List[Submission]:
        return [s for s in self._store if s.user_id == user_id]

    def count(self) -> int:
        return len(self._store)


class SqliteSubmissionRepo:
    """SQLite adapter (in-memory db để demo). Bind cùng port."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS submissions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                answers TEXT NOT NULL,
                submitted_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def save(self, submission: Submission) -> int:
        cur = self.conn.execute(
            "INSERT INTO submissions(user_id, answers, submitted_at) VALUES (?,?,?)",
            (
                submission.user_id,
                ",".join(str(a) for a in submission.answers),
                submission.submitted_at.isoformat(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def find_by_user(self, user_id: str) -> List[Submission]:
        cur = self.conn.execute(
            "SELECT user_id, answers, submitted_at FROM submissions WHERE user_id=?",
            (user_id,),
        )
        return [
            Submission(
                user_id=row[0],
                answers=[int(x) for x in row[1].split(",") if x],
                submitted_at=datetime.fromisoformat(row[2]),
            )
            for row in cur.fetchall()
        ]

    def count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM submissions")
        return cur.fetchone()[0]


class LogNotifier:
    """Capture-in-list notifier (silent, test-friendly)."""

    def __init__(self) -> None:
        self.sent: List[Dict[str, Any]] = []

    def send_receipt(self, user_id: str, score: ScoreResult) -> None:
        self.sent.append({"user_id": user_id, "score": score.score})


class EmailNotifier:
    """Mock SMTP — in real life sẽ smtplib.SMTP(...). Có thể flaky."""

    def __init__(self, *, fail_first_n: int = 0) -> None:
        self._fail_remaining = fail_first_n
        self.sent: List[str] = []

    def send_receipt(self, user_id: str, score: ScoreResult) -> None:
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise ConnectionError("SMTP timeout")
        self.sent.append(f"to={user_id} score={score.score}")


class RetryNotifier:
    """
    Decorator (Lesson 9) wrap any INotifier — retry on exception.
    Bản thân nó cũng là 1 INotifier → có thể chain.
    """

    def __init__(self, inner: INotifier, max_retries: int = 3) -> None:
        self.inner = inner
        self.max_retries = max_retries
        self.attempts: int = 0

    def send_receipt(self, user_id: str, score: ScoreResult) -> None:
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            self.attempts += 1
            try:
                self.inner.send_receipt(user_id, score)
                return
            except Exception as e:                        # noqa: BLE001
                last_err = e
        raise RuntimeError(
            f"RetryNotifier failed after {self.max_retries} attempts: {last_err}"
        )


class SystemClock:
    def now(self) -> datetime:
        return datetime.now()


class FixedClock:
    """Test clock — deterministic."""
    def __init__(self, t: datetime) -> None:
        self._t = t

    def now(self) -> datetime:
        return self._t


# =============================================================================
# [WEB] — Driving adapter cho HTTP.  *Mock*: không spawn Flask thật để demo
#         dependency-free. Trong production đây là Flask/FastAPI route.
# =============================================================================

class HTTPController:
    """Driving adapter — chỉ dịch JSON ↔ DTO + map status code."""

    def __init__(self, app_service: IQuizApplicationService) -> None:
        self.app_service = app_service

    def handle_post_submission(self, body: Dict[str, Any]) -> Dict[str, Any]:
        # Parse: ngoài → DTO
        try:
            dto = SubmissionDTO(
                user_id=body["user_id"],
                answers=list(body["answers"]),
            )
        except KeyError as e:
            return {"status": 400, "error": f"missing field {e}"}

        # Call driving port
        try:
            result = self.app_service.submit_quiz(dto)
        except ValueError as e:
            return {"status": 422, "error": str(e)}

        # Format: result → JSON
        return {"status": 201, "body": result}

    def handle_get_history(self, user_id: str) -> Dict[str, Any]:
        return {
            "status": 200,
            "body": {"history": self.app_service.get_history(user_id)},
        }


# =============================================================================
# [CLI] — Driving adapter cho command-line. Cùng app, khác cửa.
# =============================================================================

class CLIController:
    """Argv-style. Parse minimal."""

    def __init__(self, app_service: IQuizApplicationService) -> None:
        self.app_service = app_service

    def main(self, argv: List[str]) -> str:
        # CLI form:  submit <user_id> <a1,a2,a3>
        if len(argv) != 3 or argv[0] != "submit":
            return "usage: submit <user_id> <a1,a2,...>"
        user_id = argv[1]
        answers = [int(x) for x in argv[2].split(",")]
        result = self.app_service.submit_quiz(
            SubmissionDTO(user_id=user_id, answers=answers)
        )
        return f"OK submission_id={result['submission_id']} score={result['score']}"


# =============================================================================
# [EVENTS] — Driving adapter cho message queue / event bus (mock).
# =============================================================================

class EventConsumer:
    """Mock Kafka consumer. on_message dispatch vào driving port."""

    def __init__(self, app_service: IQuizApplicationService) -> None:
        self.app_service = app_service
        self.processed: int = 0

    def on_message(self, msg: Dict[str, Any]) -> None:
        if msg.get("type") != "QuizSubmitted":
            return
        dto = SubmissionDTO(
            user_id=msg["user_id"],
            answers=list(msg["answers"]),
        )
        self.app_service.submit_quiz(dto)
        self.processed += 1


# =============================================================================
# [BOOTSTRAP] — Composition root: nơi DUY NHẤT biết về cả core lẫn infra.
# =============================================================================

QUESTIONS_FIXTURE = [
    Question("q1", correct_answer=2, weight=1.0),
    Question("q2", correct_answer=0, weight=1.0),
    Question("q3", correct_answer=3, weight=2.0),     # bonus
    Question("q4", correct_answer=1, weight=1.0),
]


def build_app(
    *,
    repo: Optional[ISubmissionRepository] = None,
    notifier: Optional[INotifier] = None,
    clock: Optional[IClock] = None,
) -> QuizApplicationService:
    """
    Composition root. Wire mọi thứ. Default = pure-memory + log.
    Production: gọi build_app(repo=SqliteSubmissionRepo(...), notifier=...).
    """
    repo = repo or MemorySubmissionRepo()
    notifier = notifier or LogNotifier()
    clock = clock or SystemClock()
    scoring = ScoringService(QUESTIONS_FIXTURE)
    return QuizApplicationService(
        repo=repo, notifier=notifier, scoring=scoring, clock=clock
    )


# =============================================================================
# [DEMO] — 5 kịch bản. Chạy `python 30_hexagonal.py`.
# =============================================================================

def banner(s: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {s}")
    print("=" * 72)


def demo_1_happy_path_http() -> None:
    banner("DEMO 1 — Happy path qua HTTP adapter (Memory + Log)")
    repo = MemorySubmissionRepo()
    notifier = LogNotifier()
    clock = FixedClock(datetime(2026, 5, 6, 10, 0, 0))
    app = build_app(repo=repo, notifier=notifier, clock=clock)
    http = HTTPController(app)

    resp = http.handle_post_submission(
        {"user_id": "u1", "answers": [2, 0, 3, 1]}     # tất cả đúng
    )
    print(f"HTTP response: {resp}")
    assert resp["status"] == 201
    assert resp["body"]["correct"] == 4
    assert resp["body"]["score"] == 5.0                # 1 + 1 + 2 + 1
    assert repo.count() == 1
    assert notifier.sent == [{"user_id": "u1", "score": 5.0}]

    # GET history qua *cùng app*
    hist = http.handle_get_history("u1")
    print(f"GET /history: {hist}")
    assert hist["body"]["history"][0]["user_id"] == "u1"
    print("  PASS")


def demo_2_same_core_via_cli_and_event() -> None:
    banner("DEMO 2 — *Cùng core* được gọi qua HTTP, CLI và Event — domain unchanged")
    repo = MemorySubmissionRepo()
    notifier = LogNotifier()
    clock = FixedClock(datetime(2026, 5, 6, 10, 0, 0))
    app = build_app(repo=repo, notifier=notifier, clock=clock)

    # 1) HTTP
    HTTPController(app).handle_post_submission(
        {"user_id": "u1", "answers": [2, 0, 3, 1]}
    )
    # 2) CLI
    cli_out = CLIController(app).main(["submit", "u2", "2,0,3,1"])
    print(f"CLI output: {cli_out}")
    # 3) Event
    consumer = EventConsumer(app)
    consumer.on_message({
        "type": "QuizSubmitted",
        "user_id": "u3",
        "answers": [2, 0, 3, 1],
    })

    print(f"Repo count: {repo.count()}")
    print(f"Notify count: {len(notifier.sent)}")
    assert repo.count() == 3
    assert len(notifier.sent) == 3
    assert consumer.processed == 1
    # Tất cả 3 user dùng *cùng instance* QuizApplicationService.
    print("  PASS — driving adapter swapped without touching core")


def demo_3_swap_driven_adapter_memory_to_sqlite() -> None:
    banner("DEMO 3 — Swap driven adapter (Memory → Sqlite). Core test không sửa.")

    def run_with(repo: ISubmissionRepository) -> tuple[int, int]:
        notifier = LogNotifier()
        clock = FixedClock(datetime(2026, 5, 6, 11, 0, 0))
        app = build_app(repo=repo, notifier=notifier, clock=clock)
        http = HTTPController(app)
        for u in ("u1", "u2", "u1"):
            http.handle_post_submission(
                {"user_id": u, "answers": [2, 0, 3, 1]}
            )
        return repo.count(), len(app.get_history("u1"))

    mem_total, mem_u1 = run_with(MemorySubmissionRepo())
    sql_total, sql_u1 = run_with(SqliteSubmissionRepo(":memory:"))

    print(f"Memory:   total={mem_total}, u1_history={mem_u1}")
    print(f"Sqlite:   total={sql_total}, u1_history={sql_u1}")
    assert (mem_total, mem_u1) == (sql_total, sql_u1) == (3, 2)
    print("  PASS — adapter pluggable, core test reused 100%")


def demo_4_decorator_retry_notifier() -> None:
    banner("DEMO 4 — Decorator wrap: RetryNotifier(EmailNotifier flaky)")

    flaky = EmailNotifier(fail_first_n=2)              # fail 2 lần đầu
    retry = RetryNotifier(flaky, max_retries=3)
    repo = MemorySubmissionRepo()
    clock = FixedClock(datetime(2026, 5, 6, 12, 0, 0))
    app = build_app(repo=repo, notifier=retry, clock=clock)

    # Submit 1 quiz — RetryNotifier sẽ thử lại đến khi pass
    HTTPController(app).handle_post_submission(
        {"user_id": "u1", "answers": [2, 0, 3, 1]}
    )
    print(f"Retry attempts: {retry.attempts}")
    print(f"Email sent log: {flaky.sent}")
    assert retry.attempts == 3            # 2 fail + 1 success
    assert len(flaky.sent) == 1
    assert flaky.sent[0].startswith("to=u1")

    # Test phần fail mãi — retry exhaust
    flaky2 = EmailNotifier(fail_first_n=99)
    retry2 = RetryNotifier(flaky2, max_retries=3)
    app2 = build_app(repo=MemorySubmissionRepo(), notifier=retry2, clock=clock)
    try:
        HTTPController(app2).handle_post_submission(
            {"user_id": "u2", "answers": [2, 0, 3, 1]}
        )
        assert False, "should have raised"
    except RuntimeError as e:
        print(f"Exhausted (expected): {e}")
    print("  PASS — port chấp nhận decorator chain mà core không biết")


def demo_5_pure_test_vs_integration_timing() -> None:
    banner("DEMO 5 — Test pure (no I/O) vs integration (Sqlite). Timing.")

    def pure_test_run() -> None:
        repo = MemorySubmissionRepo()
        notifier = LogNotifier()
        clock = FixedClock(datetime(2026, 5, 6, 13, 0, 0))
        app = build_app(repo=repo, notifier=notifier, clock=clock)
        for _ in range(100):
            app.submit_quiz(SubmissionDTO("u1", [2, 0, 3, 1]))
        assert repo.count() == 100

    def integration_test_run() -> None:
        repo = SqliteSubmissionRepo(":memory:")
        notifier = LogNotifier()
        clock = FixedClock(datetime(2026, 5, 6, 13, 0, 0))
        app = build_app(repo=repo, notifier=notifier, clock=clock)
        for _ in range(100):
            app.submit_quiz(SubmissionDTO("u1", [2, 0, 3, 1]))
        assert repo.count() == 100

    t0 = time.perf_counter()
    pure_test_run()
    t_pure = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    integration_test_run()
    t_int = (time.perf_counter() - t0) * 1000

    print(f"Pure (Memory):       {t_pure:8.3f} ms / 100 submits")
    print(f"Integration (Sqlite):{t_int:8.3f} ms / 100 submits")
    print(f"Speedup pure vs int: {t_int / t_pure:.1f}x")
    print("  PASS — pure core test rất nhanh, không cần file/network")


def demo_6_anti_pattern_what_NOT_to_do() -> None:
    banner("DEMO 6 — Anti-pattern showcase (chỉ in giải thích, không chạy)")

    print("""
    ANTI-PATTERN A — Leaky core:
        # domain/scoring.py
        import sqlite3                      # ✗ domain biết driver
        class ScoringService:
            def score(self, sub):
                conn = sqlite3.connect(...) # ✗
        --> Hậu quả: đổi DB phải sửa domain. Test cần file SQLite.

    ANTI-PATTERN B — Adapter định nghĩa contract:
        # infra/repo.py
        class SqliteRepository:             # concrete, không phải port
            def save(...): ...
        # domain/app_service.py
        from infra.repo import SqliteRepository    # ✗ domain biết Sqlite
        class AppService:
            def __init__(self, repo: SqliteRepository): ...
        --> Sai chiều dependency. Đổi adapter = sửa core.

    ANTI-PATTERN C — Smart driving adapter:
        @app.post("/submissions")
        def submit():
            score = sum(...)                # ✗ business logic ở controller
            db.execute("INSERT...")         # ✗ HTTP layer chạm DB
        --> Khi đổi sang CLI phải copy logic. Không testable không-Flask.

    ANTI-PATTERN D — Mock library thay adapter:
        # test
        repo = mock.Mock()                  # ✗ không tuân port contract
        repo.save.return_value = 1
        --> Test green nhưng adapter thực có thể vi phạm port shape.
        Đúng cách: dùng MemorySubmissionRepo (real adapter, in-memory).

    Code đúng đã thấy ở demo 1-5: core thuần, ports trong domain,
    adapters cắm vào, swap không sửa core.
    """)


# =============================================================================
# RUN ALL
# =============================================================================

def main() -> int:
    demo_1_happy_path_http()
    demo_2_same_core_via_cli_and_event()
    demo_3_swap_driven_adapter_memory_to_sqlite()
    demo_4_decorator_retry_notifier()
    demo_5_pure_test_vs_integration_timing()
    demo_6_anti_pattern_what_NOT_to_do()

    print("\n" + "=" * 72)
    print("  ALL 5 DEMOS PASS — Hexagonal lesson 30 verified")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
