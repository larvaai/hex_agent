"""
Lesson 29 - Clean Architecture
Neuroscience analogy: layered concentric brain
                      brainstem (entities) <- cortex (use cases) <- periphery (frameworks)
                      Dependency direction: outer depends on inner, never reverse.

Cau truc file:
  ===== VONG 1: ENTITIES (innermost - enterprise rules) =====
    - Quiz, Question, AnswerKey
    - Submission
    - ScoreResult
    Pure dataclass + behavior. KHONG import use case / adapter / framework.

  ===== VONG 2: USE CASES (application rules) =====
    Ports (interfaces owned by use cases - DIP):
      - IQuizRepository, ISubmissionRepository
      - INotifier
      - ISubmitQuizPresenter, ILeaderboardPresenter
    Use cases:
      - SubmitQuizUseCase
      - ViewLeaderboardUseCase
    Import: entities + ports only. KHONG import adapter / framework.

  ===== VONG 3: INTERFACE ADAPTERS =====
    Controllers:
      - QuizController (parse input -> DTO)
    Presenters:
      - JsonSubmitPresenter (output -> JSON)
      - HtmlSubmitPresenter (output -> HTML)
      - LeaderboardJsonPresenter
    Repositories:
      - InMemoryQuizRepository
      - InMemorySubmissionRepository
      - SqliteSubmissionRepository
    Adapters import use cases + entities. KHONG import framework.

  ===== VONG 4: FRAMEWORKS & DRIVERS =====
    - FlaskLikeApp (mock Flask, self-contained - khong cai flask)
    - FastApiLikeApp (mock FastAPI)
    Frameworks import adapters.

  ===== COMPOSITION ROOT =====
    - build_app() wire concrete vao abstract
    - 5 demo

Chay:
    python 29_clean_architecture.py
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Protocol


# =============================================================================
# VONG 1: ENTITIES (innermost - "Enterprise Business Rules")
# =============================================================================
# Pure domain. Stable nhat. Khong I/O, khong framework, khong adapter.
# Chi import stdlib + cac entity khac.

@dataclass(frozen=True)
class Question:
    """Question entity - 1 cau hoi."""
    qid: str
    correct_answer: str
    weight: float = 1.0


@dataclass(frozen=True)
class Quiz:
    """Quiz entity - tap hop questions + ID. Co behavior score_against()."""
    quiz_id: str
    title: str
    questions: List[Question]

    def score_against(self, answers: Dict[str, str]) -> "ScoreResult":
        """Entity behavior - tinh diem (KHONG anemic)."""
        earned = sum(
            q.weight for q in self.questions
            if answers.get(q.qid) == q.correct_answer
        )
        total = sum(q.weight for q in self.questions)
        return ScoreResult(points=earned, total=total)


@dataclass(frozen=True)
class ScoreResult:
    """ScoreResult entity - co percent property (entity behavior)."""
    points: float
    total: float

    @property
    def percent(self) -> float:
        return (self.points / self.total) * 100 if self.total else 0.0


@dataclass(frozen=True)
class Submission:
    """Submission entity - user da nop quiz."""
    sub_id: str
    user_id: str
    quiz_id: str
    score: float
    total: float
    timestamp: str


# =============================================================================
# VONG 2: USE CASES (application rules) + PORTS
# =============================================================================
# Use cases orchestrate entities. Ports (interfaces) owned by use case.
# Import: entities + ports. KHONG import adapter/framework.

# ----- Ports (abstraction owned by use case layer) -----

class IQuizRepository(Protocol):
    def find_by_id(self, quiz_id: str) -> Quiz: ...


class ISubmissionRepository(Protocol):
    def save(self, sub: Submission) -> None: ...
    def find_by_user(self, user_id: str) -> List[Submission]: ...
    def all_submissions(self) -> List[Submission]: ...


class INotifier(Protocol):
    def notify(self, user_id: str, score: ScoreResult) -> None: ...


class ISubmitQuizPresenter(Protocol):
    def present(self, output: "SubmitQuizOutput") -> None: ...


class ILeaderboardPresenter(Protocol):
    def present(self, output: "LeaderboardOutput") -> None: ...


# ----- DTOs (boundary protection) -----

@dataclass(frozen=True)
class SubmitQuizInput:
    user_id: str
    quiz_id: str
    answers: Dict[str, str]


@dataclass(frozen=True)
class SubmitQuizOutput:
    submission_id: str
    user_id: str
    quiz_id: str
    score: float
    total: float
    percent: float
    timestamp: str


@dataclass(frozen=True)
class LeaderboardEntry:
    user_id: str
    best_score: float


@dataclass(frozen=True)
class LeaderboardOutput:
    quiz_id: str
    entries: List[LeaderboardEntry]


# ----- Use cases -----

class SubmitQuizUseCase:
    """Application Business Rule: 'submit quiz' workflow.
    Orchestrate Quiz + Submission entity, repo, notifier, presenter."""

    def __init__(
        self,
        quiz_repo: IQuizRepository,
        sub_repo: ISubmissionRepository,
        notifier: INotifier,
        presenter: ISubmitQuizPresenter,
    ):
        self.quiz_repo = quiz_repo
        self.sub_repo = sub_repo
        self.notifier = notifier
        self.presenter = presenter

    def execute(self, input_dto: SubmitQuizInput) -> None:
        # 1. Get entity from repo
        quiz = self.quiz_repo.find_by_id(input_dto.quiz_id)

        # 2. Use entity behavior - tinh diem
        score = quiz.score_against(input_dto.answers)

        # 3. Build new entity
        sub_id = f"sub_{datetime.now().timestamp()}"
        sub = Submission(
            sub_id=sub_id,
            user_id=input_dto.user_id,
            quiz_id=input_dto.quiz_id,
            score=score.points,
            total=score.total,
            timestamp=datetime.now().isoformat(),
        )

        # 4. Output port: persist
        self.sub_repo.save(sub)

        # 5. Output port: notify
        self.notifier.notify(input_dto.user_id, score)

        # 6. Build output DTO va goi PRESENTER (output port)
        output = SubmitQuizOutput(
            submission_id=sub.sub_id,
            user_id=sub.user_id,
            quiz_id=sub.quiz_id,
            score=sub.score,
            total=sub.total,
            percent=score.percent,
            timestamp=sub.timestamp,
        )
        self.presenter.present(output)


class ViewLeaderboardUseCase:
    """Application Business Rule: 'view leaderboard' for a quiz."""

    def __init__(self, sub_repo: ISubmissionRepository,
                 presenter: ILeaderboardPresenter):
        self.sub_repo = sub_repo
        self.presenter = presenter

    def execute(self, quiz_id: str) -> None:
        all_subs = self.sub_repo.all_submissions()
        # Filter by quiz_id, group by user, take best
        relevant = [s for s in all_subs if s.quiz_id == quiz_id]
        best_by_user: Dict[str, float] = {}
        for s in relevant:
            best_by_user[s.user_id] = max(
                best_by_user.get(s.user_id, 0.0), s.score
            )
        entries = sorted(
            (LeaderboardEntry(user_id=u, best_score=s)
             for u, s in best_by_user.items()),
            key=lambda e: e.best_score,
            reverse=True,
        )
        output = LeaderboardOutput(quiz_id=quiz_id, entries=entries)
        self.presenter.present(output)


# =============================================================================
# VONG 3: INTERFACE ADAPTERS
# =============================================================================
# Convert format giua use case va framework. Import use case + entity.

# ----- Repositories (impl ports) -----

class InMemoryQuizRepository:
    def __init__(self, quizzes: Dict[str, Quiz]):
        self._store = quizzes

    def find_by_id(self, quiz_id: str) -> Quiz:
        return self._store[quiz_id]


class InMemorySubmissionRepository:
    def __init__(self):
        self.saved: List[Submission] = []

    def save(self, sub: Submission) -> None:
        self.saved.append(sub)

    def find_by_user(self, user_id: str) -> List[Submission]:
        return [s for s in self.saved if s.user_id == user_id]

    def all_submissions(self) -> List[Submission]:
        return list(self.saved)


class SqliteSubmissionRepository:
    """Concrete adapter: SQL detail sống ở đây, không leak vào use case."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS submissions "
            "(sub_id TEXT, user_id TEXT, quiz_id TEXT, score REAL, total REAL, ts TEXT)"
        )
        conn.commit()
        conn.close()

    def save(self, sub: Submission) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO submissions VALUES (?, ?, ?, ?, ?, ?)",
            (sub.sub_id, sub.user_id, sub.quiz_id, sub.score, sub.total, sub.timestamp),
        )
        conn.commit()
        conn.close()

    def find_by_user(self, user_id: str) -> List[Submission]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT sub_id, user_id, quiz_id, score, total, ts FROM submissions WHERE user_id=?",
            (user_id,),
        ).fetchall()
        conn.close()
        return [Submission(*r) for r in rows]

    def all_submissions(self) -> List[Submission]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT sub_id, user_id, quiz_id, score, total, ts FROM submissions"
        ).fetchall()
        conn.close()
        return [Submission(*r) for r in rows]


# ----- Notifiers -----

class LogNotifier:
    def __init__(self):
        self.logged: List[str] = []

    def notify(self, user_id: str, score: ScoreResult) -> None:
        self.logged.append(f"[LOG] {user_id} scored {score.percent:.0f}%")


# ----- Presenters (output adapters) -----

class JsonSubmitPresenter:
    """Concrete impl ISubmitQuizPresenter -> JSON."""
    def __init__(self):
        self.last_response: Optional[str] = None

    def present(self, output: SubmitQuizOutput) -> None:
        self.last_response = json.dumps({
            "id": output.submission_id,
            "user": output.user_id,
            "quiz": output.quiz_id,
            "score": output.score,
            "total": output.total,
            "percent": round(output.percent, 1),
            "ts": output.timestamp,
        })


class HtmlSubmitPresenter:
    """Concrete impl ISubmitQuizPresenter -> HTML."""
    def __init__(self):
        self.last_response: Optional[str] = None

    def present(self, output: SubmitQuizOutput) -> None:
        self.last_response = (
            f"<div class='result'>"
            f"<h2>{output.user_id} - Quiz {output.quiz_id}</h2>"
            f"<p>Score: {output.score:.1f}/{output.total:.1f} "
            f"({output.percent:.0f}%)</p>"
            f"</div>"
        )


class LeaderboardJsonPresenter:
    def __init__(self):
        self.last_response: Optional[str] = None

    def present(self, output: LeaderboardOutput) -> None:
        self.last_response = json.dumps({
            "quiz": output.quiz_id,
            "leaderboard": [
                {"user": e.user_id, "score": e.best_score}
                for e in output.entries
            ],
        })


# ----- Controllers -----

class QuizController:
    """HTTP request -> use case input DTO. Goi use case."""

    def __init__(self, submit_use_case: SubmitQuizUseCase,
                 leaderboard_use_case: ViewLeaderboardUseCase):
        self.submit_uc = submit_use_case
        self.leaderboard_uc = leaderboard_use_case

    def submit(self, http_payload: dict) -> None:
        """Parse JSON-like dict -> DTO -> call use case."""
        input_dto = SubmitQuizInput(
            user_id=http_payload["user_id"],
            quiz_id=http_payload["quiz_id"],
            answers=http_payload["answers"],
        )
        self.submit_uc.execute(input_dto)

    def leaderboard(self, quiz_id: str) -> None:
        self.leaderboard_uc.execute(quiz_id)


# =============================================================================
# VONG 4: FRAMEWORKS & DRIVERS (mock - khong import flask/fastapi that)
# =============================================================================

class FlaskLikeApp:
    """Mock Flask. Routes -> controller. Khong import flask that de self-contained."""

    def __init__(self, controller: QuizController, presenter: JsonSubmitPresenter,
                 leaderboard_presenter: LeaderboardJsonPresenter):
        self.controller = controller
        self.presenter = presenter
        self.leaderboard_presenter = leaderboard_presenter
        self.framework_name = "Flask"

    def handle_request(self, method: str, path: str, body: Optional[dict] = None) -> str:
        """Simulate Flask routing."""
        if method == "POST" and path == "/quiz/submit":
            self.controller.submit(body or {})
            return self.presenter.last_response or ""
        elif method == "GET" and path.startswith("/quiz/") and path.endswith("/leaderboard"):
            quiz_id = path.split("/")[2]
            self.controller.leaderboard(quiz_id)
            return self.leaderboard_presenter.last_response or ""
        else:
            return "404 Not Found"


class FastApiLikeApp:
    """Mock FastAPI. Cung interface FlaskLikeApp - chi de demo swap framework."""

    def __init__(self, controller: QuizController, presenter: JsonSubmitPresenter,
                 leaderboard_presenter: LeaderboardJsonPresenter):
        self.controller = controller
        self.presenter = presenter
        self.leaderboard_presenter = leaderboard_presenter
        self.framework_name = "FastAPI"

    def handle_request(self, method: str, path: str, body: Optional[dict] = None) -> str:
        # FastAPI uses async; in mock we keep sync for simplicity
        if method == "POST" and path == "/quiz/submit":
            self.controller.submit(body or {})
            return self.presenter.last_response or ""
        elif method == "GET" and path.startswith("/quiz/") and path.endswith("/leaderboard"):
            quiz_id = path.split("/")[2]
            self.controller.leaderboard(quiz_id)
            return self.leaderboard_presenter.last_response or ""
        else:
            return "404 Not Found"


# =============================================================================
# COMPOSITION ROOT
# =============================================================================

def build_default_quizzes() -> Dict[str, Quiz]:
    return {
        "quiz_001": Quiz(
            quiz_id="quiz_001",
            title="Neuroscience Basics",
            questions=[
                Question("q1", "AMPA", weight=1.0),
                Question("q2", "GABA", weight=1.0),
                Question("q3", "thalamus", weight=2.0),  # cau quan trong
                Question("q4", "hippocampus", weight=1.0),
            ],
        ),
    }


def build_app(framework: str = "flask",
              repo_kind: str = "memory",
              presenter_kind: str = "json"):
    """Composition root. Wire concrete vao abstract.
    Day la diem DUY NHAT thay tat ca layer."""

    # Quiz repo (in-memory voi default quiz)
    quiz_repo = InMemoryQuizRepository(build_default_quizzes())

    # Submission repo
    if repo_kind == "sqlite":
        db_path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        sub_repo = SqliteSubmissionRepository(db_path)
    else:
        sub_repo = InMemorySubmissionRepository()  # type: ignore

    # Notifier
    notifier = LogNotifier()

    # Presenter
    if presenter_kind == "html":
        submit_presenter = HtmlSubmitPresenter()
    else:
        submit_presenter = JsonSubmitPresenter()  # type: ignore

    leaderboard_presenter = LeaderboardJsonPresenter()

    # Use cases
    submit_uc = SubmitQuizUseCase(
        quiz_repo=quiz_repo,
        sub_repo=sub_repo,
        notifier=notifier,
        presenter=submit_presenter,  # type: ignore
    )
    leaderboard_uc = ViewLeaderboardUseCase(
        sub_repo=sub_repo,
        presenter=leaderboard_presenter,
    )

    # Controllers
    controller = QuizController(submit_uc, leaderboard_uc)

    # Framework
    if framework == "fastapi":
        app = FastApiLikeApp(controller, submit_presenter, leaderboard_presenter)  # type: ignore
    else:
        app = FlaskLikeApp(controller, submit_presenter, leaderboard_presenter)  # type: ignore

    return app, sub_repo, notifier, submit_presenter


# =============================================================================
# DEMOS
# =============================================================================

def demo_1_end_to_end_trace():
    print("=" * 70)
    print("DEMO 1 - End-to-end request trace through 4 layers")
    print("=" * 70)

    app, sub_repo, notifier, presenter = build_app()

    # Simulate HTTP POST
    body = {
        "user_id": "alice",
        "quiz_id": "quiz_001",
        "answers": {
            "q1": "AMPA",        # dung
            "q2": "glutamate",   # sai (correct: GABA)
            "q3": "thalamus",    # dung (weight 2)
            "q4": "amygdala",    # sai (correct: hippocampus)
        },
    }
    response = app.handle_request("POST", "/quiz/submit", body)

    print(f"  POST /quiz/submit body={body}")
    print()
    print(f"  Trace:")
    print(f"    [Vong 4 Frameworks]   FlaskLikeApp.handle_request()")
    print(f"    [Vong 3 Adapters]     QuizController.submit() -> SubmitQuizInput DTO")
    print(f"    [Vong 2 Use Cases]    SubmitQuizUseCase.execute()")
    print(f"    [Vong 1 Entities]     Quiz.score_against(answers) -> ScoreResult")
    print(f"    [Vong 2 -> 3 port]    sub_repo.save() (InMemory)")
    print(f"    [Vong 2 -> 3 port]    notifier.notify() (LogNotifier)")
    print(f"    [Vong 2 -> 3 port]    presenter.present() (JsonSubmitPresenter)")
    print(f"    [Vong 4]              FlaskLikeApp returns presenter.last_response")
    print()
    print(f"  HTTP response: {response}")
    print()
    print(f"  Persisted: {len(sub_repo.saved)} submission")
    print(f"  Notification: {notifier.logged}")
    print()


def demo_2_swap_framework():
    print("=" * 70)
    print("DEMO 2 - Swap framework Flask -> FastAPI: business unchanged")
    print("=" * 70)

    body = {"user_id": "bob", "quiz_id": "quiz_001",
            "answers": {"q1": "AMPA", "q2": "GABA", "q3": "thalamus", "q4": "hippocampus"}}

    flask_app, _, _, _ = build_app(framework="flask")
    fastapi_app, _, _, _ = build_app(framework="fastapi")

    flask_resp = flask_app.handle_request("POST", "/quiz/submit", body)
    fastapi_resp = fastapi_app.handle_request("POST", "/quiz/submit", body)

    print(f"  Flask framework:   {flask_app.framework_name}")
    print(f"  FastAPI framework: {fastapi_app.framework_name}")
    print()
    # Compare scores (timestamps differ)
    flask_data = json.loads(flask_resp)
    fastapi_data = json.loads(fastapi_resp)
    print(f"  Flask response score:   {flask_data['score']}/{flask_data['total']} ({flask_data['percent']}%)")
    print(f"  FastAPI response score: {fastapi_data['score']}/{fastapi_data['total']} ({fastapi_data['percent']}%)")
    print()
    print("  -> Cung use case + entities + presenter. Chi framework wrapper khac.")
    print("     Domain code (Vong 1+2) khong sua 1 dong.")
    print()


def demo_3_swap_presenter():
    print("=" * 70)
    print("DEMO 3 - Swap presenter JSON -> HTML: use case unchanged")
    print("=" * 70)

    body = {"user_id": "carol", "quiz_id": "quiz_001",
            "answers": {"q1": "AMPA", "q2": "GABA", "q3": "thalamus", "q4": "hippocampus"}}

    json_app, _, _, _ = build_app(presenter_kind="json")
    html_app, _, _, _ = build_app(presenter_kind="html")

    print(f"  JSON presenter response:")
    print(f"    {json_app.handle_request('POST', '/quiz/submit', body)}")
    print()
    print(f"  HTML presenter response:")
    print(f"    {html_app.handle_request('POST', '/quiz/submit', body)}")
    print()
    print("  -> Use case + entities khong biet output la JSON hay HTML.")
    print("     Goi qua port ISubmitQuizPresenter; concrete impl khac biet.")
    print()


def demo_4_swap_repository():
    print("=" * 70)
    print("DEMO 4 - Swap repository Memory -> SQLite: use case unchanged")
    print("=" * 70)

    body = {"user_id": "dave", "quiz_id": "quiz_001",
            "answers": {"q1": "AMPA", "q2": "GABA", "q3": "thalamus", "q4": "hippocampus"}}

    mem_app, mem_repo, _, _ = build_app(repo_kind="memory")
    sql_app, sql_repo, _, _ = build_app(repo_kind="sqlite")

    mem_app.handle_request("POST", "/quiz/submit", body)
    sql_app.handle_request("POST", "/quiz/submit", body)

    print(f"  Memory repo type:  {type(mem_repo).__name__}")
    print(f"    saved count:     {len(mem_repo.saved)}")
    print(f"  SQLite repo type:  {type(sql_repo).__name__}")
    print(f"    saved count:     {len(sql_repo.all_submissions())}")
    print()
    print("  -> Cung SubmitQuizUseCase orchestrate, chi adapter implementation khac.")
    print("     Use case code khong biet co SQLite.")
    print()


def demo_5_dependency_graph():
    print("=" * 70)
    print("DEMO 5 - Source-code dependency graph (one-way inward)")
    print("=" * 70)

    print("""
  Layer imports (theo file 1 file nay - trong project that chia thu muc):

    [Vong 1] Entities (Quiz, Question, ScoreResult, Submission):
        imports: dataclasses, typing
        KHONG import: use cases, adapters, frameworks

    [Vong 2] Use Cases (SubmitQuizUseCase, ViewLeaderboardUseCase):
        imports: entities + ports (Protocol) + DTOs
        KHONG import: adapters, frameworks

    [Vong 3] Adapters:
        Repositories:  imports entities + ports
        Presenters:    imports use cases (DTO type) + ports
        Controllers:   imports use cases + DTOs
        KHONG import: frameworks

    [Vong 4] Frameworks (FlaskLikeApp, FastApiLikeApp):
        imports: adapters + (in real: flask/fastapi library)

    Composition root (build_app):
        imports: ALL layers - day la diem DUY NHAT.

  Dependency direction:

      Frameworks ─┐
                  ▼
              Adapters ─┐
                        ▼
                    Use Cases ─┐
                               ▼
                            Entities

  Khong co mui ten nguoc (Entities -> Use Cases hay Use Cases -> Adapters).
""")


def main():
    print()
    print("#" * 70)
    print("# LESSON 29 - Clean Architecture")
    print("# 4 vong tron + Dependency Rule one-way")
    print("# Brainstem (entities) <- cortex (use cases) <- periphery (frameworks)")
    print("#" * 70)
    print()

    demo_1_end_to_end_trace()
    demo_2_swap_framework()
    demo_3_swap_presenter()
    demo_4_swap_repository()
    demo_5_dependency_graph()

    print("=" * 70)
    print("Tom tat:")
    print("  - 4 layer: Entities <- Use Cases <- Adapters <- Frameworks")
    print("  - Dependency rule: source code import chi vao trong, khong bao gio ra ngoai")
    print("  - DTO o boundary: framework/HTTP type khong leak vao use case")
    print("  - Output port: use case 'goi outward' qua interface, depend stays inward")
    print("  - Composition root: 1 noi wire concrete vao abstract")
    print("  - Buoc tiep theo (Lesson 30 Hexagonal): variant don gian hon - 2 region")
    print("    core domain + adapters; tap trung port-driven design")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
