"""
Lesson 27 - Interface Segregation Principle (ISP)
Neuroscience analogy: receptor specificity (AMPA chi nghe glutamate, GABA-A chi nghe GABA).
                      Khong co "god receptor".

Cau truc file:
  PART A - VI PHAM ISP
    - IQuizPlatform fat interface (10 method)
    - FatQuizPlatform impl (full)
    - ReadOnlyQuizPlatform (refused bequest - raise NotImplementedError 7 lan)
    - 4 client phu thuoc fat interface
    - Mock setup count cho test cua client (test bloat)

  PART B - ISP REFACTOR
    - 6 narrow Protocol: Scorable, Notifier, Storable, Rankable, Renderable, Auditable
    - QuizService impl 6 protocol qua structural subtyping
    - 4 client refactor type-hint narrow Protocol
    - Mock setup count moi (giam ro)
    - ReadOnlyQuizService chi impl 2 protocol, bo 7 stub

  PART C - DEMOS
    1. Refused bequest fail
    2. Mock count comparison
    3. Recompile graph
    4. runtime_checkable + isinstance
    5. Composition: build "limited" service tu narrow protocol

Chay:
    python 27_isp.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, runtime_checkable


# =============================================================================
# Domain types
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
    answers: Dict[str, str]
    score: float


# =============================================================================
# PART A - VI PHAM ISP: Fat interface IQuizPlatform
# =============================================================================
# 10 method. 4 client - moi cai chi dung 1-2 method.

class IQuizPlatform(ABC):
    """FAT INTERFACE - vi pham ISP. 10 method goi tu 4 client view khac nhau."""

    @abstractmethod
    def score(self, answers: Dict[str, str]) -> ScoreResult: ...

    @abstractmethod
    def save_submission(self, sub: Submission) -> None: ...

    @abstractmethod
    def get_submission(self, sub_id: str) -> Submission: ...

    @abstractmethod
    def send_email(self, user_id: str, msg: str) -> None: ...

    @abstractmethod
    def send_push(self, user_id: str, msg: str) -> None: ...

    @abstractmethod
    def update_rank(self, user_id: str, score: float) -> None: ...

    @abstractmethod
    def get_rank(self, user_id: str) -> int: ...

    @abstractmethod
    def render_pdf(self, sub: Submission) -> bytes: ...

    @abstractmethod
    def export_csv(self, subs: List[Submission]) -> str: ...

    @abstractmethod
    def audit_log(self, event: str) -> None: ...


class FatQuizPlatform(IQuizPlatform):
    """Impl day du 10 method. Tat ca code cua he thong day day."""

    def __init__(self, answer_key: Dict[str, str]):
        self._answer_key = answer_key
        self._submissions: Dict[str, Submission] = {}
        self._rank: Dict[str, float] = {}
        self.email_outbox: List[str] = []
        self.push_outbox: List[str] = []
        self.audit_outbox: List[str] = []

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        points = sum(1.0 for q, c in self._answer_key.items() if answers.get(q) == c)
        return ScoreResult(points, float(len(self._answer_key)))

    def save_submission(self, sub: Submission) -> None:
        self._submissions[sub.sub_id] = sub

    def get_submission(self, sub_id: str) -> Submission:
        return self._submissions[sub_id]

    def send_email(self, user_id: str, msg: str) -> None:
        self.email_outbox.append(f"EMAIL {user_id}: {msg}")

    def send_push(self, user_id: str, msg: str) -> None:
        self.push_outbox.append(f"PUSH {user_id}: {msg}")

    def update_rank(self, user_id: str, score: float) -> None:
        self._rank[user_id] = max(self._rank.get(user_id, 0.0), score)

    def get_rank(self, user_id: str) -> int:
        if user_id not in self._rank:
            return -1
        sorted_scores = sorted(self._rank.values(), reverse=True)
        return sorted_scores.index(self._rank[user_id]) + 1

    def render_pdf(self, sub: Submission) -> bytes:
        return f"PDF<{sub.sub_id}, score={sub.score}>".encode()

    def export_csv(self, subs: List[Submission]) -> str:
        lines = ["sub_id,user_id,score"]
        for s in subs:
            lines.append(f"{s.sub_id},{s.user_id},{s.score}")
        return "\n".join(lines)

    def audit_log(self, event: str) -> None:
        self.audit_outbox.append(event)


class ReadOnlyQuizPlatform(IQuizPlatform):
    """REFUSED BEQUEST: chi can scoring + lookup, nhung bi ep impl 10 method.
    -> 8 method raise NotImplementedError. Smell ISP ro rang."""

    def __init__(self, answer_key: Dict[str, str], cache: Dict[str, Submission]):
        self._answer_key = answer_key
        self._cache = cache

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        points = sum(1.0 for q, c in self._answer_key.items() if answers.get(q) == c)
        return ScoreResult(points, float(len(self._answer_key)))

    def get_submission(self, sub_id: str) -> Submission:
        return self._cache[sub_id]

    # Refused bequest - 8 method khong support
    def save_submission(self, sub: Submission) -> None:
        raise NotImplementedError("ReadOnlyQuizPlatform cannot save")

    def send_email(self, user_id: str, msg: str) -> None:
        raise NotImplementedError("ReadOnlyQuizPlatform cannot send email")

    def send_push(self, user_id: str, msg: str) -> None:
        raise NotImplementedError("ReadOnlyQuizPlatform cannot send push")

    def update_rank(self, user_id: str, score: float) -> None:
        raise NotImplementedError("ReadOnlyQuizPlatform read-only")

    def get_rank(self, user_id: str) -> int:
        raise NotImplementedError("ReadOnlyQuizPlatform no rank")

    def render_pdf(self, sub: Submission) -> bytes:
        raise NotImplementedError("ReadOnlyQuizPlatform no PDF")

    def export_csv(self, subs: List[Submission]) -> str:
        raise NotImplementedError("ReadOnlyQuizPlatform no export")

    def audit_log(self, event: str) -> None:
        raise NotImplementedError("ReadOnlyQuizPlatform no audit")


# 4 client phu thuoc fat interface
# Moi client chi dung 1-2 method, nhung type-hint TOAN BO interface

class FatScoreCalculatorClient:
    """Chi can: score(). Phu thuoc 10 method (qua type)."""
    def __init__(self, platform: IQuizPlatform):
        self.platform = platform

    def calculate_for_user(self, answers: Dict[str, str]) -> float:
        return self.platform.score(answers).percent


class FatNotificationDispatchClient:
    """Chi can: send_email, send_push. Phu thuoc 10 method."""
    def __init__(self, platform: IQuizPlatform):
        self.platform = platform

    def notify_result(self, user_id: str, percent: float) -> None:
        self.platform.send_email(user_id, f"Score: {percent:.0f}%")
        self.platform.send_push(user_id, f"You scored {percent:.0f}%!")


class FatLeaderboardClient:
    """Chi can: update_rank, get_rank. Phu thuoc 10 method."""
    def __init__(self, platform: IQuizPlatform):
        self.platform = platform

    def record_and_show_rank(self, user_id: str, score: float) -> int:
        self.platform.update_rank(user_id, score)
        return self.platform.get_rank(user_id)


class FatAuditClient:
    """Chi can: audit_log. Phu thuoc 10 method."""
    def __init__(self, platform: IQuizPlatform):
        self.platform = platform

    def record(self, event: str) -> None:
        self.platform.audit_log(event)


# =============================================================================
# PART B - ISP REFACTOR: 6 narrow Protocol
# =============================================================================

class Scorable(Protocol):
    def score(self, answers: Dict[str, str]) -> ScoreResult: ...


class SubmissionStore(Protocol):
    def save_submission(self, sub: Submission) -> None: ...
    def get_submission(self, sub_id: str) -> Submission: ...


class Notifier(Protocol):
    def send_email(self, user_id: str, msg: str) -> None: ...
    def send_push(self, user_id: str, msg: str) -> None: ...


class Rankable(Protocol):
    def update_rank(self, user_id: str, score: float) -> None: ...
    def get_rank(self, user_id: str) -> int: ...


class Renderable(Protocol):
    def render_pdf(self, sub: Submission) -> bytes: ...
    def export_csv(self, subs: List[Submission]) -> str: ...


@runtime_checkable
class Auditable(Protocol):
    def audit_log(self, event: str) -> None: ...


class QuizService:
    """Impl 6 narrow Protocol qua structural subtyping (KHONG inherit).
    Cung implementation as FatQuizPlatform - chi khac type system goc nhin."""

    def __init__(self, answer_key: Dict[str, str]):
        self._answer_key = answer_key
        self._submissions: Dict[str, Submission] = {}
        self._rank: Dict[str, float] = {}
        self.email_outbox: List[str] = []
        self.push_outbox: List[str] = []
        self.audit_outbox: List[str] = []

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        points = sum(1.0 for q, c in self._answer_key.items() if answers.get(q) == c)
        return ScoreResult(points, float(len(self._answer_key)))

    def save_submission(self, sub: Submission) -> None:
        self._submissions[sub.sub_id] = sub

    def get_submission(self, sub_id: str) -> Submission:
        return self._submissions[sub_id]

    def send_email(self, user_id: str, msg: str) -> None:
        self.email_outbox.append(f"EMAIL {user_id}: {msg}")

    def send_push(self, user_id: str, msg: str) -> None:
        self.push_outbox.append(f"PUSH {user_id}: {msg}")

    def update_rank(self, user_id: str, score: float) -> None:
        self._rank[user_id] = max(self._rank.get(user_id, 0.0), score)

    def get_rank(self, user_id: str) -> int:
        if user_id not in self._rank:
            return -1
        sorted_scores = sorted(self._rank.values(), reverse=True)
        return sorted_scores.index(self._rank[user_id]) + 1

    def render_pdf(self, sub: Submission) -> bytes:
        return f"PDF<{sub.sub_id}, score={sub.score}>".encode()

    def export_csv(self, subs: List[Submission]) -> str:
        lines = ["sub_id,user_id,score"]
        for s in subs:
            lines.append(f"{s.sub_id},{s.user_id},{s.score}")
        return "\n".join(lines)

    def audit_log(self, event: str) -> None:
        self.audit_outbox.append(event)


class ReadOnlyQuizService:
    """Chi impl 2 narrow Protocol (Scorable + SubmissionStore-read-only).
    KHONG raise NotImplementedError - khong refuse bequest vi khong bi ep."""

    def __init__(self, answer_key: Dict[str, str], cache: Dict[str, Submission]):
        self._answer_key = answer_key
        self._cache = cache

    def score(self, answers: Dict[str, str]) -> ScoreResult:
        points = sum(1.0 for q, c in self._answer_key.items() if answers.get(q) == c)
        return ScoreResult(points, float(len(self._answer_key)))

    def get_submission(self, sub_id: str) -> Submission:
        return self._cache[sub_id]


# 4 client refactor - type hint narrow Protocol

class ScoreCalculatorClient:
    """Type hint narrow: chi 1 method."""
    def __init__(self, scorer: Scorable):
        self.scorer = scorer

    def calculate_for_user(self, answers: Dict[str, str]) -> float:
        return self.scorer.score(answers).percent


class NotificationDispatchClient:
    def __init__(self, notifier: Notifier):
        self.notifier = notifier

    def notify_result(self, user_id: str, percent: float) -> None:
        self.notifier.send_email(user_id, f"Score: {percent:.0f}%")
        self.notifier.send_push(user_id, f"You scored {percent:.0f}%!")


class LeaderboardClient:
    def __init__(self, ranker: Rankable):
        self.ranker = ranker

    def record_and_show_rank(self, user_id: str, score: float) -> int:
        self.ranker.update_rank(user_id, score)
        return self.ranker.get_rank(user_id)


class AuditClient:
    def __init__(self, auditor: Auditable):
        self.auditor = auditor

    def record(self, event: str) -> None:
        self.auditor.audit_log(event)


# =============================================================================
# PART C - DEMOS
# =============================================================================

def demo_1_refused_bequest():
    print("=" * 70)
    print("DEMO 1 - Refused bequest: ReadOnlyQuizPlatform fail khi caller goi method")
    print("=" * 70)

    cache = {
        "s1": Submission("s1", "alice", {"q1": "A"}, score=1.0),
    }
    ro = ReadOnlyQuizPlatform({"q1": "A"}, cache)

    # Caller hop dong voi IQuizPlatform - tin la moi method work
    def evil_workflow(platform: IQuizPlatform, user: str):
        platform.send_email(user, "Hello")  # ← se fail vi RO impl raise

    print("  Caller goi platform.send_email() voi ReadOnlyQuizPlatform:")
    try:
        evil_workflow(ro, "alice")
    except NotImplementedError as e:
        print(f"    -> NotImplementedError: {e}")

    # In so dong NotImplementedError
    src = open(__file__).read()
    n = src.count("NotImplementedError(\"ReadOnly")
    print(f"  So 'raise NotImplementedError' trong ReadOnlyQuizPlatform: {n}")
    print("  -> Smell ISP. Sau refactor: ReadOnlyQuizService chi impl 2 protocol,")
    print("     KHONG co NotImplementedError nao.")
    print()


def demo_2_mock_count():
    print("=" * 70)
    print("DEMO 2 - Mock count: viet test cho ScoreCalculatorClient")
    print("=" * 70)

    # Test FAT version: phai mock 10 method (kieu unittest.MagicMock auto-mock,
    # nhung de minh hoa bang mock thuc te thi can dinh nghia 10 stub).
    # O day - de minh hoa - tao "MockFatPlatform" stub day du 10 method.

    class MockFatPlatform:
        """Mock stub cho test FatScoreCalculatorClient. Phai stub 10 method."""
        def score(self, answers): return ScoreResult(3.0, 4.0)
        def save_submission(self, sub): pass
        def get_submission(self, sub_id): pass
        def send_email(self, user_id, msg): pass
        def send_push(self, user_id, msg): pass
        def update_rank(self, user_id, score): pass
        def get_rank(self, user_id): return 1
        def render_pdf(self, sub): return b""
        def export_csv(self, subs): return ""
        def audit_log(self, event): pass

    # Test NARROW version: chi can stub 1 method
    class MockScorable:
        def score(self, answers): return ScoreResult(3.0, 4.0)

    fat_client = FatScoreCalculatorClient(MockFatPlatform())  # type: ignore
    narrow_client = ScoreCalculatorClient(MockScorable())  # type: ignore

    print(f"  fat_client.calculate_for_user:    {fat_client.calculate_for_user({}):.0f}%")
    print(f"  narrow_client.calculate_for_user: {narrow_client.calculate_for_user({}):.0f}%")
    print()
    print("  Mock methods needed:")
    print("    FAT (FatScoreCalculatorClient + MockFatPlatform): 10 method stub")
    print("    NARROW (ScoreCalculatorClient + MockScorable):    1 method stub")
    print("  -> Test boilerplate: 30 dong (fat) vs 3 dong (narrow)")
    print()


def demo_3_recompile_graph():
    print("=" * 70)
    print("DEMO 3 - Recompile/redeploy graph khi them method 11")
    print("=" * 70)

    print("  Truoc (vi pham ISP):")
    print("    Them method 'send_sms' vao IQuizPlatform")
    print("    -> Moi impl PHAI add send_sms (FatQuizPlatform, ReadOnlyQuizPlatform,...)")
    print("    -> Moi caller TYPE-HINT IQuizPlatform recompile/recheck")
    print("       (FatScoreCalculatorClient, FatLeaderboardClient, FatAuditClient,...)")
    print("    -> Ban kinh anh huong: ALL clients + ALL impls")
    print()
    print("  Sau (ISP):")
    print("    Them protocol 'SmsCapable' moi (1 method send_sms)")
    print("    Hoac them method send_sms vao Notifier protocol")
    print("    -> Chi class can SMS impl moi method")
    print("    -> Chi caller phu thuoc Notifier/SmsCapable bi anh huong")
    print("    -> Ban kinh anh huong: 1 client view (notification) + impl can SMS")
    print()


def demo_4_runtime_checkable():
    print("=" * 70)
    print("DEMO 4 - runtime_checkable Protocol + isinstance introspection")
    print("=" * 70)

    qs = QuizService({"q1": "A"})
    ro = ReadOnlyQuizService({"q1": "A"}, {})

    # Auditable da @runtime_checkable
    print(f"  isinstance(QuizService,         Auditable): {isinstance(qs, Auditable)}")
    print(f"  isinstance(ReadOnlyQuizService, Auditable): {isinstance(ro, Auditable)}")
    print()
    print("  -> QuizService 'tu nhien' impl Auditable (co audit_log())")
    print("     ReadOnlyQuizService khong co audit_log -> isinstance False")
    print("  -> Type checking + duck typing combo. KHONG can register/inherit.")
    print()


def demo_5_composition():
    print("=" * 70)
    print("DEMO 5 - Composition: build limited service tu narrow protocol")
    print("=" * 70)

    qs = QuizService({"q1": "A", "q2": "B"})

    # Wire client tu cung 1 service - moi client thay narrow view
    score_client = ScoreCalculatorClient(qs)         # thay Scorable
    notify_client = NotificationDispatchClient(qs)   # thay Notifier
    rank_client = LeaderboardClient(qs)              # thay Rankable
    audit_client = AuditClient(qs)                   # thay Auditable

    answers = {"q1": "A", "q2": "X"}
    percent = score_client.calculate_for_user(answers)
    rank = rank_client.record_and_show_rank("alice", percent)
    notify_client.notify_result("alice", percent)
    audit_client.record(f"alice scored {percent:.0f}%, rank {rank}")

    print(f"  Score:  {percent:.0f}%")
    print(f"  Rank:   {rank}")
    print(f"  Email:  {qs.email_outbox}")
    print(f"  Push:   {qs.push_outbox}")
    print(f"  Audit:  {qs.audit_outbox}")
    print()
    print("  Cung 1 'qs' instance, moi client thay narrow view:")
    print("    score_client.scorer  -> Scorable (1 method)")
    print("    notify_client.notifier -> Notifier (2 method)")
    print("    rank_client.ranker   -> Rankable (2 method)")
    print("    audit_client.auditor -> Auditable (1 method)")
    print()
    print("  Test: thay qs bang ReadOnlyQuizService -> chi score_client + 1 phan rank work")

    # Use ReadOnlyQuizService - chi co Scorable + SubmissionStore
    ro = ReadOnlyQuizService({"q1": "A", "q2": "B"}, {})
    score_client_ro = ScoreCalculatorClient(ro)
    print(f"  ReadOnlyQuizService score: {score_client_ro.calculate_for_user(answers):.0f}%")

    # ReadOnlyQuizService KHONG impl Notifier - mypy se cho loi.
    # Runtime: cung khong fail vi co attribute checks, nhung type hint la boundary.
    print("  ReadOnlyQuizService khong impl Notifier -> mypy bao loi truoc khi chay.")
    print()


def main():
    print()
    print("#" * 70)
    print("# LESSON 27 - Interface Segregation Principle (ISP)")
    print("# Receptor specificity: AMPA chi nghe glutamate, GABA-A chi nghe GABA")
    print("# 'God receptor' khong ton tai trong nao - vi co ly do cu the")
    print("#" * 70)
    print()

    demo_1_refused_bequest()
    demo_2_mock_count()
    demo_3_recompile_graph()
    demo_4_runtime_checkable()
    demo_5_composition()

    print("=" * 70)
    print("Tom tat:")
    print("  - Fat interface (10 method) -> 4 client moi cai dung 1-2 method")
    print("  - Refused bequest (8 NotImplementedError) -> smell ISP ro")
    print("  - Tach 6 narrow Protocol theo client view")
    print("  - QuizService impl all 6 qua structural subtyping (Python Protocol)")
    print("  - Mock test 30 dong -> 3 dong")
    print("  - Recompile graph: 1 client thay vi all clients")
    print("  - Buoc tiep theo (Lesson 28 DIP): cap cao phu thuoc abstraction")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
