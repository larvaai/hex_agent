"""
Lesson 28 - Dependency Inversion Principle (DIP)
Neuroscience analogy: thalamus relay (LGN/MGN/VPL) - cortex (high-level) dinh nghia
                      "spike train" abstraction; periphery (low-level) qua thalamus adapt.

Cau truc file:
  PART A - WITHOUT DIP: BadQuizService import sqlite3 + smtplib truc tiep
                        Test phai tao tempfile DB, mock SMTP. Slow + coupled.

  PART B - WITH DIP:
    Domain layer (high-level):
      - Submission, ScoreResult (entity)
      - ISubmissionRepository, INotifier (Protocol - abstraction)
      - QuizSubmissionService (use case - chi import Protocol)

    Infrastructure layer (low-level - import Protocol tu domain):
      - SqliteSubmissionRepository  (production)
      - PostgresSubmissionRepository (gia lap migration target)
      - InMemorySubmissionRepository (fake cho test)
      - EmailNotifier               (production)
      - LogNotifier                 (fake cho test/dev)

  PART C - Composition root: 3 wiring config (production, dev, test).

  PART D - 5 demo:
    1. Without-DIP test: tempfile + SMTP mock, slow
    2. With-DIP test: pure in-memory, fast
    3. Swap infra: Sqlite -> Postgres -> Memory, service KHONG sua
    4. Sensory substitution analogy
    5. Source-code dependency graph: domain KHONG import infra

Chay:
    python 28_dip.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol


# =============================================================================
# Domain Entity (shared - khong infra dependency)
# =============================================================================

@dataclass(frozen=True)
class ScoreResult:
    points: float
    total: float

    @property
    def percent(self) -> float:
        return (self.points / self.total) * 100 if self.total else 0.0


@dataclass(frozen=True)
class Submission:
    sub_id: str
    user_id: str
    score: float
    total: float
    timestamp: str


# =============================================================================
# PART A - WITHOUT DIP: high-level import low-level concrete
# =============================================================================

class BadQuizService:
    """Vi pham DIP: import sqlite3 + smtplib truc tiep.
    High-level (use case) phu thuoc concrete infrastructure."""

    def __init__(self, db_path: str, smtp_outbox: List[str]):
        self.db_path = db_path
        self.smtp_outbox = smtp_outbox  # gia lap smtplib send
        self._init_db()

    def _init_db(self):
        # Use case BIET ve schema SQL - vi pham DIP
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS submissions "
            "(sub_id TEXT, user_id TEXT, score REAL, total REAL, ts TEXT)"
        )
        conn.commit()
        conn.close()

    def submit(self, user_id: str, answers: Dict[str, str],
               answer_key: Dict[str, str]) -> Submission:
        # Score
        points = sum(1.0 for q, c in answer_key.items() if answers.get(q) == c)
        total = float(len(answer_key))

        # PERSIST - SQL hard-coded
        sub = Submission(
            sub_id=f"sub_{int(time.time()*1000)}",
            user_id=user_id,
            score=points,
            total=total,
            timestamp=datetime.now().isoformat(),
        )
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO submissions VALUES (?, ?, ?, ?, ?)",
            (sub.sub_id, sub.user_id, sub.score, sub.total, sub.timestamp),
        )
        conn.commit()
        conn.close()

        # NOTIFY - SMTP hard-coded (gia lap)
        body = f"Hi {user_id}, you scored {points}/{total} ({points/total*100:.0f}%)"
        self.smtp_outbox.append(f"EMAIL {user_id}: {body}")

        return sub


# =============================================================================
# PART B - WITH DIP
# =============================================================================
# DOMAIN LAYER (high-level) - chi co Protocol va use case
# Khong import infrastructure. Khong biet SQLite, SMTP, Redis ton tai.

# --- domain/ports.py (in real project, tach file) ---

class ISubmissionRepository(Protocol):
    """Abstraction OWNED by domain layer - dinh nghia 'what use case needs'.
    Method tu domain language - khong leak SQL/HTTP detail."""

    def save(self, sub: Submission) -> None: ...
    def find_by_user(self, user_id: str) -> List[Submission]: ...


class INotifier(Protocol):
    def notify(self, user_id: str, result: ScoreResult) -> None: ...


# --- domain/use_cases.py ---

class QuizSubmissionService:
    """Use case (high-level). Chi import Protocol tu domain.ports.
    KHONG biet SQLite, SMTP. Pure business logic + orchestration."""

    def __init__(self, repo: ISubmissionRepository, notifier: INotifier):
        # Type-hint la PROTOCOL, khong concrete class
        self.repo = repo
        self.notifier = notifier

    def submit(self, user_id: str, answers: Dict[str, str],
               answer_key: Dict[str, str]) -> Submission:
        # Score
        points = sum(1.0 for q, c in answer_key.items() if answers.get(q) == c)
        total = float(len(answer_key))
        result = ScoreResult(points, total)

        sub = Submission(
            sub_id=f"sub_{int(time.time()*1_000_000)}",
            user_id=user_id,
            score=points,
            total=total,
            timestamp=datetime.now().isoformat(),
        )

        # Goi qua abstraction - khong biet impl la gi
        self.repo.save(sub)
        self.notifier.notify(user_id, result)
        return sub


# --- infrastructure/sqlite_repo.py ---
# Adapter import Protocol tu domain - DIP inversion: low-level depend on high-level abstraction

class SqliteSubmissionRepository:
    """Concrete impl ISubmissionRepository qua SQLite. Production adapter."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS submissions "
            "(sub_id TEXT, user_id TEXT, score REAL, total REAL, ts TEXT)"
        )
        conn.commit()
        conn.close()

    def save(self, sub: Submission) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO submissions VALUES (?, ?, ?, ?, ?)",
            (sub.sub_id, sub.user_id, sub.score, sub.total, sub.timestamp),
        )
        conn.commit()
        conn.close()

    def find_by_user(self, user_id: str) -> List[Submission]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT sub_id, user_id, score, total, ts FROM submissions WHERE user_id=?",
            (user_id,),
        ).fetchall()
        conn.close()
        return [Submission(*r) for r in rows]


# --- infrastructure/postgres_repo.py (gia lap migration target) ---

class PostgresSubmissionRepository:
    """Gia lap Postgres adapter (su dung dict cho demo).
    Trong production se import psycopg2 / asyncpg - vi du lam SQL Postgres syntax."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        # Trong production: self.conn = psycopg2.connect(dsn)
        self._fake_pg: List[Submission] = []

    def save(self, sub: Submission) -> None:
        # Trong production: cur.execute("INSERT ... VALUES (%s, %s, ...)", (...))
        self._fake_pg.append(sub)

    def find_by_user(self, user_id: str) -> List[Submission]:
        return [s for s in self._fake_pg if s.user_id == user_id]


# --- infrastructure/memory_repo.py ---

class InMemorySubmissionRepository:
    """Fake cho unit test. KHONG persist gi. Pure in-memory."""

    def __init__(self):
        self.saved: List[Submission] = []

    def save(self, sub: Submission) -> None:
        self.saved.append(sub)

    def find_by_user(self, user_id: str) -> List[Submission]:
        return [s for s in self.saved if s.user_id == user_id]


# --- infrastructure/email_notifier.py ---

class EmailNotifier:
    """Production email notifier (gia lap, khong send that)."""

    def __init__(self):
        self.outbox: List[str] = []

    def notify(self, user_id: str, result: ScoreResult) -> None:
        body = f"Hi {user_id}, you scored {result.points}/{result.total} ({result.percent:.0f}%)"
        # Production: smtplib.SMTP(...).send_message(msg)
        self.outbox.append(f"EMAIL {user_id}: {body}")


# --- infrastructure/log_notifier.py ---

class LogNotifier:
    """Fake notifier cho dev / test. Chi log."""

    def __init__(self):
        self.logged: List[str] = []

    def notify(self, user_id: str, result: ScoreResult) -> None:
        self.logged.append(f"[LOG] {user_id} scored {result.points}/{result.total}")


# =============================================================================
# PART C - Composition root: wiring concrete vao abstraction
# =============================================================================

def build_production_service(db_path: str) -> QuizSubmissionService:
    """Production wiring: SQLite + Email."""
    return QuizSubmissionService(
        repo=SqliteSubmissionRepository(db_path),
        notifier=EmailNotifier(),
    )


def build_dev_service() -> QuizSubmissionService:
    """Dev wiring: in-memory repo + log notifier. Khong I/O."""
    return QuizSubmissionService(
        repo=InMemorySubmissionRepository(),
        notifier=LogNotifier(),
    )


def build_postgres_service(dsn: str) -> QuizSubmissionService:
    """Migration wiring: Postgres + Email."""
    return QuizSubmissionService(
        repo=PostgresSubmissionRepository(dsn),
        notifier=EmailNotifier(),
    )


# =============================================================================
# PART D - DEMOS
# =============================================================================

ANSWER_KEY = {"q1": "A", "q2": "B", "q3": "C", "q4": "D"}
ANSWERS = {"q1": "A", "q2": "B", "q3": "X", "q4": "D"}  # 3/4


def demo_1_without_dip_test():
    print("=" * 70)
    print("DEMO 1 - Without DIP: test phai dung tempfile + 'SMTP'")
    print("=" * 70)

    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    smtp_box: List[str] = []

    t0 = time.perf_counter()
    bad = BadQuizService(db, smtp_outbox=smtp_box)
    sub = bad.submit("alice", ANSWERS, ANSWER_KEY)
    t1 = time.perf_counter()

    print(f"  Submission: {sub.user_id} score={sub.score}/{sub.total}")
    print(f"  Setup overhead: tempfile DB + 'SMTP outbox', {(t1-t0)*1000:.2f} ms")
    print(f"  Test code coupled to: sqlite3 module, file system, SMTP")
    print(f"  Email outbox: {smtp_box}")
    os.unlink(db)
    print()


def demo_2_with_dip_test():
    print("=" * 70)
    print("DEMO 2 - With DIP: test pure in-memory, fast")
    print("=" * 70)

    fake_repo = InMemorySubmissionRepository()
    fake_notifier = LogNotifier()

    t0 = time.perf_counter()
    service = QuizSubmissionService(fake_repo, fake_notifier)
    sub = service.submit("alice", ANSWERS, ANSWER_KEY)
    t1 = time.perf_counter()

    print(f"  Submission: {sub.user_id} score={sub.score}/{sub.total}")
    print(f"  Setup overhead: 2 fake objects, {(t1-t0)*1000:.3f} ms")
    print(f"  Test code coupled to: NOTHING (only domain types + fake)")
    print(f"  fake_repo.saved   = {len(fake_repo.saved)} submission")
    print(f"  fake_notifier.logged = {fake_notifier.logged}")
    print()


def demo_3_swap_infrastructure():
    print("=" * 70)
    print("DEMO 3 - Swap infrastructure: Sqlite -> Postgres -> Memory, service KHONG sua")
    print("=" * 70)

    sqlite_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name

    configs: List[Any] = [
        ("Production (SQLite + Email)", build_production_service(sqlite_db)),
        ("Migration (Postgres + Email)", build_postgres_service("dsn=fake")),
        ("Dev (Memory + Log)", build_dev_service()),
    ]

    for label, service in configs:
        sub = service.submit("alice", ANSWERS, ANSWER_KEY)
        repo_type = type(service.repo).__name__
        notifier_type = type(service.notifier).__name__
        print(f"  {label}")
        print(f"    repo:     {repo_type}")
        print(f"    notifier: {notifier_type}")
        print(f"    score:    {sub.score}/{sub.total}")

    print()
    print("  3 config khac nhau, QuizSubmissionService source code: KHONG sua")
    os.unlink(sqlite_db)
    print()


def demo_4_sensory_substitution_analogy():
    print("=" * 70)
    print("DEMO 4 - Sensory substitution analogy")
    print("=" * 70)
    print("  Cortex (V1) khong biet retina la mat sinh hoc hay camera tactile.")
    print("  Cortex chi consume 'spike train pattern' tu LGN.")
    print("  -> Bach-y-Rita 1969: vibrator tren lung -> nguoi mu 'thay'")
    print("  -> Cochlear implant: 22 dien cuc -> nguoi diec nghe")
    print("  -> Argus II: 60 pixel -> retinitis pigmentosa thay anh sang")
    print()
    print("  Tuong tu:")
    print("  QuizSubmissionService khong biet repo la SQLite, Postgres, hay Mongo.")
    print("  Service chi consume ISubmissionRepository (= 'spike train pattern').")
    print()

    service = build_dev_service()  # in-memory
    service.submit("user_blind_1", ANSWERS, ANSWER_KEY)

    # 'Sensor swap' - replace repo runtime
    new_service = QuizSubmissionService(
        repo=PostgresSubmissionRepository("dsn=migration"),
        notifier=service.notifier,
    )
    new_service.submit("user_blind_2", ANSWERS, ANSWER_KEY)

    print(f"  Memory repo saved: {len(service.repo.saved)}")  # type: ignore
    print(f"  Postgres saved:    {len(new_service.repo._fake_pg)}")  # type: ignore
    print()


def demo_5_source_code_graph():
    print("=" * 70)
    print("DEMO 5 - Source-code dependency graph (DIP inversion)")
    print("=" * 70)

    # In a real project (separate files), we would grep:
    #   grep -r 'import sqlite3' domain/    -> 0 (use case khong biet SQLite)
    #   grep -r 'import smtplib' domain/    -> 0
    #   grep -r 'from domain' infrastructure/  -> >= 1 (infra import abstraction)

    # In nay file (1 file), minh hoa qua docstring + comment:
    print("  Domain layer imports:")
    print("    - typing.Protocol")
    print("    - dataclasses (entity)")
    print("    - datetime")
    print("    -> KHONG sqlite3, KHONG smtplib, KHONG psycopg2")
    print()
    print("  Infrastructure layer imports:")
    print("    - sqlite3 (concrete adapter)")
    print("    - smtplib / boto3 (in production)")
    print("    - 'domain.ports' (abstraction = inverted)")
    print()
    print("  Composition root (main.py / build_*_service):")
    print("    - Cong 2 layer lai. Diem DUY NHAT thay cu the va abstract")
    print()
    print("  Source-code direction:")
    print("    domain.use_cases  --import-->  domain.ports")
    print("    infra.sqlite_repo --import-->  domain.ports   <-- INVERTED")
    print("    infra.email_notif --import-->  domain.ports")
    print()
    print("  Runtime call direction:")
    print("    use_case --calls--> repo.save()  --executes--> SQL")
    print("    (use_case is 'consumer' of abstract; concrete impl is provider)")
    print()


def main():
    print()
    print("#" * 70)
    print("# LESSON 28 - Dependency Inversion Principle (DIP)")
    print("# High-level dinh nghia abstraction; low-level adapt theo abstraction")
    print("# Thalamus relay: cortex (V1) <- LGN <- retina; cortex DOES NOT know retina")
    print("#" * 70)
    print()

    demo_1_without_dip_test()
    demo_2_with_dip_test()
    demo_3_swap_infrastructure()
    demo_4_sensory_substitution_analogy()
    demo_5_source_code_graph()

    print("=" * 70)
    print("Tom tat:")
    print("  - DIP dao chieu source-code dependency: low-level depend on high-level abstraction")
    print("  - Abstraction OWNED by consumer (high-level), khong owned by provider")
    print("  - Use case unit test pure: 0.01 ms vs vai ms voi tempfile")
    print("  - Swap infra: SQLite -> Postgres -> Memory, service code KHONG sua")
    print("  - Composition root: 1 diem ket noi 2 layer")
    print("  - Het SOLID! Buoc tiep theo (Lesson 29 Clean Architecture):")
    print("    DIP scaled len system - 4 vong tron + dependency rule one-way")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
