"""
Lesson 24 - Single Responsibility Principle (SRP)
Neuroscience analogy: functional specialization (V1 edge, MT motion, Broca speech, Wernicke comprehension).

Cau truc file:
  PART 1 - QuizGodService: God Object intentionally violating SRP (~150 dong, 6 actor cung 1 class)
  PART 2 - SRP refactor: 6 collaborator class + 1 thin orchestrator
  PART 3 - Demo 1: cung input -> cung output (refactor preserves behavior)
  PART 4 - Demo 2: change request "negative marking" -> SRP swap scorer, God phai mo file dai
  PART 5 - Demo 3: testability - test scorer co lap, khong can DB/SMTP/leaderboard
  PART 6 - Demo 4: them actor moi (Analytics) khong sua class hien co -> dat nen OCP

Chay:
    python 24_srp.py
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Protocol


# =============================================================================
# PART 1 - QuizGodService: GOD OBJECT (vi pham SRP)
# =============================================================================
# 1 class lam 6 viec, 6 actor cung "keo" no:
#   - Validation (API gateway team)
#   - Scoring rule (Curriculum team)
#   - Persistence (DBA team)
#   - Email notification (Marketing team)
#   - Leaderboard ranking (Product team)
#   - JSON response shape (Frontend team)
# Bom hen gio: moi PR doi 1 actor de bug 5 actor con lai.

class QuizGodService:
    """God Object - intentionally bad. Do NOT copy this style."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.leaderboard: Dict[str, int] = {}  # user_id -> best_score
        self.sent_emails: List[str] = []  # fake "outbox" for demo
        self.analytics_events: List[dict] = []  # fake analytics sink
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS submissions
            (user_id TEXT, score INT, total INT, ts TEXT)"""
        )
        conn.commit()
        conn.close()

    def submit(self, user_id: str, answers: Dict[str, str]) -> str:
        # ----- 1. VALIDATE (Actor: API Gateway team) -----
        if not isinstance(answers, dict):
            raise ValueError("answers must be a dict")
        if not user_id or not isinstance(user_id, str):
            raise ValueError("user_id must be non-empty string")
        for q, a in answers.items():
            if not isinstance(q, str) or not isinstance(a, str):
                raise ValueError("each answer must be str:str")

        # ----- 2. SCORE (Actor: Curriculum team) -----
        # Hard-coded answer key + scoring rule (1 point per correct, 0 for wrong)
        answer_key = {"q1": "A", "q2": "B", "q3": "C", "q4": "D"}
        score = 0
        for q, correct in answer_key.items():
            if answers.get(q) == correct:
                score += 1
        total = len(answer_key)
        percent = (score / total) * 100 if total else 0

        # ----- 3. PERSIST (Actor: DBA team) -----
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO submissions VALUES (?, ?, ?, ?)",
            (user_id, score, total, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        # ----- 4. EMAIL (Actor: Marketing team) -----
        subject = "Your Ellumm Quiz Result"
        body = (
            f"Hi {user_id}!\n\n"
            f"You scored {score}/{total} ({percent:.0f}%).\n\n"
            f"Keep learning with Ellumm.\n"
        )
        # In real life: smtplib.SMTP(...).send_message(msg)
        self.sent_emails.append(f"{user_id} | {subject} | {body[:40]}...")

        # ----- 5. LEADERBOARD (Actor: Product / Gamification team) -----
        prev_best = self.leaderboard.get(user_id, 0)
        if score > prev_best:
            self.leaderboard[user_id] = score
        sorted_scores = sorted(self.leaderboard.values(), reverse=True)
        rank = sorted_scores.index(self.leaderboard[user_id]) + 1

        # ----- 6. RESPONSE FORMAT (Actor: Frontend team) -----
        response = {
            "user": user_id,
            "score": score,
            "total": total,
            "percent": round(percent, 1),
            "rank": rank,
        }
        return json.dumps(response)


# =============================================================================
# PART 2 - SRP REFACTOR: 6 collaborators + 1 thin orchestrator
# =============================================================================

# ----- Domain types (shared) -----
@dataclass(frozen=True)
class ScoreResult:
    points: int
    total: int

    @property
    def percent(self) -> float:
        return (self.points / self.total) * 100 if self.total else 0.0


# ----- Class 1: Validation -----
# Actor: API Gateway / Contract team
# Ly do thay doi: doi schema request, them rule validation moi
class QuizValidator:
    def validate(self, user_id: str, answers: Dict[str, str]) -> None:
        if not user_id or not isinstance(user_id, str):
            raise ValueError("user_id must be non-empty string")
        if not isinstance(answers, dict):
            raise ValueError("answers must be a dict")
        for q, a in answers.items():
            if not isinstance(q, str) or not isinstance(a, str):
                raise ValueError("each answer must be str:str")


# ----- Class 2: Scoring -----
# Actor: Curriculum / Education team
# Ly do thay doi: doi cach tinh diem (weighted, negative marking, partial credit)
# Lam abstract -> mo cho extension (Lesson 25 OCP se dung)
class QuizScorer(ABC):
    @abstractmethod
    def score(self, answers: Dict[str, str]) -> ScoreResult:
        ...


class StandardScorer(QuizScorer):
    """1 point per correct, 0 for wrong. Khong tru diem."""

    def __init__(self, answer_key: Dict[str, str]):
        self.answer_key = answer_key

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        points = sum(
            1 for q, correct in self.answer_key.items()
            if answers.get(q) == correct
        )
        return ScoreResult(points=points, total=len(self.answer_key))


# ----- Class 3: Persistence -----
# Actor: DBA / Data team
# Ly do thay doi: doi schema, doi storage engine
class SubmissionRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS submissions
            (user_id TEXT, score INT, total INT, ts TEXT)"""
        )
        conn.commit()
        conn.close()

    def save(self, user_id: str, result: ScoreResult) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO submissions VALUES (?, ?, ?, ?)",
            (user_id, result.points, result.total, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()


# ----- Class 4: Notification -----
# Actor: Marketing / Comms team
# Ly do thay doi: doi template, them SMS, da ngon ngu
class Notifier(Protocol):
    def notify(self, user_id: str, result: ScoreResult) -> None:
        ...


class EmailNotifier:
    """In-memory outbox de demo. That ra dung smtplib."""

    def __init__(self):
        self.outbox: List[str] = []

    def notify(self, user_id: str, result: ScoreResult) -> None:
        body = (
            f"Hi {user_id}!\n\n"
            f"You scored {result.points}/{result.total} "
            f"({result.percent:.0f}%).\n\nKeep learning with Ellumm.\n"
        )
        self.outbox.append(f"{user_id} | Your Ellumm Quiz Result | {body[:40]}...")


# ----- Class 5: Leaderboard -----
# Actor: Product / Gamification team
# Ly do thay doi: doi cach rank, top-N cutoff, decay theo thoi gian
class LeaderboardService:
    def __init__(self):
        self._best: Dict[str, int] = {}

    def update(self, user_id: str, score: int) -> None:
        prev = self._best.get(user_id)
        if prev is None or score > prev:
            self._best[user_id] = score

    def rank_of(self, user_id: str) -> int:
        if user_id not in self._best:
            raise KeyError(f"user {user_id} not on leaderboard yet")
        sorted_scores = sorted(self._best.values(), reverse=True)
        return sorted_scores.index(self._best[user_id]) + 1


# ----- Class 6: Response formatting -----
# Actor: Frontend team
# Ly do thay doi: doi shape JSON, them field, doi naming convention
class ResponseFormatter:
    def format(self, user_id: str, result: ScoreResult, rank: int) -> str:
        return json.dumps(
            {
                "user": user_id,
                "score": result.points,
                "total": result.total,
                "percent": round(result.percent, 1),
                "rank": rank,
            }
        )


# ----- Orchestrator (Facade) -----
# KHONG co business logic. Chi biet WORKFLOW (thu tu cac buoc).
# Ly do thay doi: chi khi thu tu cac buoc thay doi (rat hiem).
class QuizSubmissionService:
    def __init__(
        self,
        validator: QuizValidator,
        scorer: QuizScorer,
        repo: SubmissionRepository,
        notifier: Notifier,
        leaderboard: LeaderboardService,
        formatter: ResponseFormatter,
    ):
        self.validator = validator
        self.scorer = scorer
        self.repo = repo
        self.notifier = notifier
        self.leaderboard = leaderboard
        self.formatter = formatter

    def submit(self, user_id: str, answers: Dict[str, str]) -> str:
        self.validator.validate(user_id, answers)
        result = self.scorer.score(answers)
        self.repo.save(user_id, result)
        self.notifier.notify(user_id, result)
        self.leaderboard.update(user_id, result.points)
        rank = self.leaderboard.rank_of(user_id)
        return self.formatter.format(user_id, result, rank)


# =============================================================================
# PART 3 - DEMO 1: cung input -> cung output (refactor preserves behavior)
# =============================================================================

def build_srp_service(db_path: str) -> QuizSubmissionService:
    answer_key = {"q1": "A", "q2": "B", "q3": "C", "q4": "D"}
    return QuizSubmissionService(
        validator=QuizValidator(),
        scorer=StandardScorer(answer_key),
        repo=SubmissionRepository(db_path),
        notifier=EmailNotifier(),
        leaderboard=LeaderboardService(),
        formatter=ResponseFormatter(),
    )


def demo_1_behavior_parity():
    print("=" * 70)
    print("DEMO 1 - Behavior parity: God class vs SRP refactor cung output")
    print("=" * 70)

    god_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    srp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name

    god = QuizGodService(god_db)
    srp = build_srp_service(srp_db)

    answers = {"q1": "A", "q2": "B", "q3": "X", "q4": "D"}  # 3/4 correct

    god_out = god.submit("alice", answers)
    srp_out = srp.submit("alice", answers)

    print(f"  God output:  {god_out}")
    print(f"  SRP output:  {srp_out}")
    print(f"  Identical?   {json.loads(god_out) == json.loads(srp_out)}")
    print()


# =============================================================================
# PART 4 - DEMO 2: change request "negative marking" -> Curriculum team yeu cau
# Trong God: phai mo file 150 dong, sua giua method submit()
# Trong SRP: tao 1 NegativeMarkingScorer moi, swap, KHONG sua class hien co
# =============================================================================

class NegativeMarkingScorer(QuizScorer):
    """+1 dung, -0.25 sai (giong SAT cu)."""

    def __init__(self, answer_key: Dict[str, str]):
        self.answer_key = answer_key

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        # Note: ScoreResult(points: int) - de demo gon, lam thanh int round
        # Trong production neu can fractional, doi ScoreResult.points sang float.
        raw = 0.0
        for q, correct in self.answer_key.items():
            given = answers.get(q)
            if given == correct:
                raw += 1.0
            elif given is not None:  # answered wrong (not skipped)
                raw -= 0.25
        # Round half up de int hop ly cho leaderboard
        points = max(0, int(round(raw)))
        return ScoreResult(points=points, total=len(self.answer_key))


def demo_2_change_request():
    print("=" * 70)
    print("DEMO 2 - Change request: Curriculum team doi sang 'negative marking'")
    print("=" * 70)
    print("  Trong God class: phai sua giua submit() ~30 dong, risk regression")
    print("  Trong SRP:       tao NegativeMarkingScorer, swap collaborator, 0 sua class cu")
    print()

    answer_key = {"q1": "A", "q2": "B", "q3": "C", "q4": "D"}
    # 1 dung, 3 sai - chon de standard vs negative khac biet ro
    answers = {"q1": "A", "q2": "X", "q3": "Y", "q4": "Z"}

    standard = StandardScorer(answer_key)
    negative = NegativeMarkingScorer(answer_key)

    print(f"  Standard scorer:         {standard.score(answers).points}/4 points "
          f"(1 dung -> 1 diem)")
    print(f"  Negative marking scorer: {negative.score(answers).points}/4 points "
          f"(1 dung +1.0, 3 sai -0.75 -> 0.25 round = 0)")

    # Swap scorer trong dependency wiring
    db_path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    srp = QuizSubmissionService(
        validator=QuizValidator(),
        scorer=negative,                  # <-- chi dong nay thay
        repo=SubmissionRepository(db_path),
        notifier=EmailNotifier(),
        leaderboard=LeaderboardService(),
        formatter=ResponseFormatter(),
    )
    out = srp.submit("bob", answers)
    print(f"  SRP service voi negative scorer: {out}")
    print()


# =============================================================================
# PART 5 - DEMO 3: testability - test scorer co lap
# =============================================================================

def demo_3_testability():
    print("=" * 70)
    print("DEMO 3 - Testability: test QuizScorer KHONG can DB / SMTP / leaderboard")
    print("=" * 70)

    # Test SRP scorer co lap (5 dong, 0 mock)
    scorer = StandardScorer({"q1": "A", "q2": "B"})
    result = scorer.score({"q1": "A", "q2": "X"})
    assert result.points == 1
    assert result.total == 2
    assert result.percent == 50.0
    print("  [PASS] StandardScorer test (5 dong, 0 mock)")

    # Test negative marking
    neg = NegativeMarkingScorer({"q1": "A", "q2": "B", "q3": "C", "q4": "D"})
    res = neg.score({"q1": "A", "q2": "X", "q3": "Y", "q4": "D"})
    # 2 dung +2.0, 2 sai -0.5, raw=1.5, round=2
    assert res.points == 2, f"expected 2, got {res.points}"
    print("  [PASS] NegativeMarkingScorer test (5 dong, 0 mock)")

    print()
    print("  Voi God class, test cung scoring rule can:")
    print("    - tempfile cho SQLite DB")
    print("    - mock smtplib (hoac chap nhan side effect email)")
    print("    - init leaderboard state")
    print("    - parse JSON output de assert score")
    print("  -> ~30 dong setUp cho 1 dong assert. Test phinh, fragile, cham.")
    print()


# =============================================================================
# PART 6 - DEMO 4: them actor moi (Analytics) khong sua class hien co
# Day la cau noi sang lesson 25 (OCP).
# =============================================================================

class AnalyticsTracker:
    """Actor moi: Data Science team. They want quiz events for Mixpanel/Segment."""

    def __init__(self):
        self.events: List[dict] = []

    def track(self, event_name: str, properties: dict) -> None:
        self.events.append({"event": event_name, "props": properties, "ts": datetime.now().isoformat()})


# Cach 1: Wrap orchestrator (decorator-like). KHONG sua QuizSubmissionService.
class TrackedQuizSubmissionService:
    def __init__(self, inner: QuizSubmissionService, tracker: AnalyticsTracker):
        self.inner = inner
        self.tracker = tracker

    def submit(self, user_id: str, answers: Dict[str, str]) -> str:
        result_json = self.inner.submit(user_id, answers)
        result = json.loads(result_json)
        self.tracker.track("quiz_submitted", {
            "user_id": user_id,
            "score": result["score"],
            "rank": result["rank"],
        })
        return result_json


def demo_4_open_extension():
    print("=" * 70)
    print("DEMO 4 - Them actor moi (Analytics) khong sua class hien co")
    print("=" * 70)

    db_path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    base = build_srp_service(db_path)
    tracker = AnalyticsTracker()
    tracked = TrackedQuizSubmissionService(base, tracker)

    tracked.submit("carol", {"q1": "A", "q2": "B", "q3": "C", "q4": "D"})
    tracked.submit("dave", {"q1": "A", "q2": "X", "q3": "C", "q4": "Y"})

    print(f"  Analytics events: {len(tracker.events)}")
    for e in tracker.events:
        print(f"    {e['event']}: {e['props']}")

    print()
    print("  Files modified to add Analytics actor: 0 (added new class only)")
    print("  --> day la mam mong cua OCP (Lesson 25): mo cho extension, dong cho modification")
    print()


# =============================================================================
# Main
# =============================================================================

def main():
    print()
    print("#" * 70)
    print("# LESSON 24 - Single Responsibility Principle (SRP)")
    print("# Functional specialization: 1 class = 1 actor (ly do thay doi)")
    print("#" * 70)
    print()

    demo_1_behavior_parity()
    demo_2_change_request()
    demo_3_testability()
    demo_4_open_extension()

    print("=" * 70)
    print("Tom tat:")
    print("  - God class: 1 file, 6 actor, moi PR doi 1 actor risk pha 5 actor con lai")
    print("  - SRP:       6 class + 1 orchestrator, moi class < 30 dong, test co lap duoc")
    print("  - Trade-off: file count + boilerplate <-> testability + parallel work")
    print("  - Buoc tiep theo (Lesson 25 OCP): xay tren refactor nay")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
