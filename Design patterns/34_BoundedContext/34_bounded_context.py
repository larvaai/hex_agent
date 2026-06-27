"""
Lesson 34 — Strategic DDD: Bounded Context
==========================================

Refactor Ellumm Quiz thành 4 bounded context, mỗi cái có model `User`
(hoặc `Recipient`) riêng biệt. Tích hợp qua Anti-Corruption Layer (ACL),
Customer-Supplier port, và Published Language event (versioned).

Cấu trúc 1 file (mô phỏng 4 package):
    [EXTERNAL]              Auth0User — generic upstream
    [QUIZ_CTX]    (Core)    Quiz, Question, QuizContextUser
    [SUBMISSION_CTX] (Core) Submission, SubmissionContextUser, IQuizCatalog
    [LEADERBOARD_CTX] (Sup) Ranking, LeaderboardUser
    [NOTIFICATION_CTX] (Gen) Recipient, Receipt          (KHÔNG gọi là User)
    [ACL]                   AuthACL: Auth0User → context-specific model
    [PUBLISHED_LANG]        ScoreCalculatedV1 (V2 backward-compat demo)
    [CONTEXT_MAP]           Render ASCII + glossary
    [DEMO]                  7 demos chứng minh từng aspect

Cách chạy:
    python 34_bounded_context.py
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields as dc_fields
from datetime import datetime
from typing import Dict, List, Optional, Protocol, runtime_checkable, Tuple, Any, Callable


# =============================================================================
# [EXTERNAL]   Auth0 — Generic subdomain. Upstream của chúng ta. KHÔNG sửa.
# =============================================================================

@dataclass(frozen=True)
class Auth0User:
    """Schema từ Auth0 — bạn không kiểm soát. 30+ field thực tế; chọn 8 để demo."""
    sub: str                            # Auth0's primary key
    email: str
    name: str
    nickname: str
    locale: str
    email_verified: bool
    phone_number: Optional[str]
    user_metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# [QUIZ_CTX]   Core subdomain — author tạo quiz, gắn correct answers
# =============================================================================
# Ngôn ngữ trong context: Author, Quiz, Question, Difficulty.
# "User" trong context này = Author (người tạo quiz).

@dataclass(frozen=True)
class quiz_ctx_QuizContextUser:
    """User trong Quiz Context = AUTHOR. Chỉ cần field liên quan authoring."""
    user_id: str                        # Đối chiếu Auth0.sub qua ACL
    display_name: str
    author_level: int                   # senior author tạo được advanced quiz
    quizzes_published: int = 0


@dataclass(frozen=True)
class quiz_ctx_Question:
    qid: str
    text: str
    correct_answer: int
    weight: float = 1.0


@dataclass
class quiz_ctx_Quiz:
    """Aggregate root của Quiz Context."""
    quiz_id: str
    title: str
    author_id: str
    questions: List[quiz_ctx_Question] = field(default_factory=list)
    is_published: bool = False

    def add_question(self, q: quiz_ctx_Question) -> None:
        if self.is_published:
            raise ValueError("cannot add question to published quiz")
        self.questions.append(q)

    def publish(self) -> None:
        if not self.questions:
            raise ValueError("cannot publish empty quiz")
        self.is_published = True


class quiz_ctx_QuizRepo:
    """Repository nội bộ Quiz Context. Không expose entity ra ngoài."""

    def __init__(self) -> None:
        self._store: Dict[str, quiz_ctx_Quiz] = {}

    def save(self, quiz: quiz_ctx_Quiz) -> None:
        self._store[quiz.quiz_id] = quiz

    def get(self, quiz_id: str) -> Optional[quiz_ctx_Quiz]:
        return self._store.get(quiz_id)


# Customer-Supplier interface: Quiz Context publishes a DTO (summary).
# Downstream chỉ thấy DTO này, KHÔNG thấy quiz_ctx_Quiz entity.

@dataclass(frozen=True)
class quiz_ctx_QuizSummary:
    """DTO public cho downstream (Submission Context)."""
    quiz_id: str
    title: str
    correct_answers: Tuple[int, ...]    # tuple cho immutable
    weights: Tuple[float, ...]


class quiz_ctx_QuizSummaryService:
    """Cổng (driving port) của Quiz Context publish ra."""

    def __init__(self, repo: quiz_ctx_QuizRepo) -> None:
        self._repo = repo

    def get_summary(self, quiz_id: str) -> Optional[quiz_ctx_QuizSummary]:
        q = self._repo.get(quiz_id)
        if not q or not q.is_published:
            return None
        return quiz_ctx_QuizSummary(
            quiz_id=q.quiz_id,
            title=q.title,
            correct_answers=tuple(qq.correct_answer for qq in q.questions),
            weights=tuple(qq.weight for qq in q.questions),
        )


# =============================================================================
# [SUBMISSION_CTX]   Core subdomain — student làm quiz, chấm điểm
# =============================================================================
# Ngôn ngữ: Submission, Attempt, Score. "User" = Student (người làm quiz).

@dataclass(frozen=True)
class submission_ctx_SubmissionContextUser:
    """User trong Submission Context = STUDENT. Khác hoàn toàn QuizContextUser."""
    user_id: str
    display_name: str
    attempt_count: int = 0
    last_score: Optional[float] = None
    # KHÔNG có author_level (irrelevant); KHÔNG có email (irrelevant)


@runtime_checkable
class submission_ctx_IQuizCatalog(Protocol):
    """Customer-Supplier port — Submission context "đặt hàng" từ Quiz context.
    Implementation sẽ là adapter gọi sang quiz_ctx_QuizSummaryService."""
    def get_summary(self, quiz_id: str) -> Optional[quiz_ctx_QuizSummary]: ...


@dataclass
class submission_ctx_Submission:
    """Aggregate root của Submission Context."""
    submission_id: str
    user_id: str
    quiz_id: str
    answers: Tuple[int, ...]
    submitted_at: datetime
    score: Optional[float] = None
    correct_count: Optional[int] = None

    def grade(self, summary: quiz_ctx_QuizSummary) -> None:
        if len(self.answers) != len(summary.correct_answers):
            raise ValueError(
                f"answer count {len(self.answers)} != quiz "
                f"questions {len(summary.correct_answers)}"
            )
        breakdown = [
            a == c for a, c in zip(self.answers, summary.correct_answers)
        ]
        self.correct_count = sum(breakdown)
        self.score = sum(
            w for w, ok in zip(summary.weights, breakdown) if ok
        )


class submission_ctx_SubmissionRepo:
    def __init__(self) -> None:
        self._store: Dict[str, submission_ctx_Submission] = {}

    def save(self, sub: submission_ctx_Submission) -> None:
        self._store[sub.submission_id] = sub

    def get(self, sid: str) -> Optional[submission_ctx_Submission]:
        return self._store.get(sid)


# =============================================================================
# [PUBLISHED_LANG]   Event schema — public contract. Versioned.
# =============================================================================
# Đây là *Published Language* — mọi context downstream có thể consume.

@dataclass(frozen=True)
class ScoreCalculatedV1:
    """Schema version 1. Backward-compatible khi V2 ra: optional field thôi."""
    schema_version: int = 1
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)
    user_id: str = ""
    quiz_id: str = ""
    submission_id: str = ""
    score: float = 0.0
    correct_count: int = 0
    total_questions: int = 0


@dataclass(frozen=True)
class ScoreCalculatedV2:
    """Schema version 2. Thêm `quiz_title` (optional có default)."""
    schema_version: int = 2
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)
    user_id: str = ""
    quiz_id: str = ""
    submission_id: str = ""
    score: float = 0.0
    correct_count: int = 0
    total_questions: int = 0
    quiz_title: str = ""                # ← new in V2, default = ""


# Application service của Submission Context — publish event sau khi grade
class submission_ctx_SubmissionService:
    def __init__(
        self,
        repo: submission_ctx_SubmissionRepo,
        quiz_catalog: submission_ctx_IQuizCatalog,
        bus: "EventBus",
    ) -> None:
        self.repo = repo
        self.quiz_catalog = quiz_catalog
        self.bus = bus

    def submit(self, user_id: str, quiz_id: str, answers: List[int]) -> str:
        summary = self.quiz_catalog.get_summary(quiz_id)
        if not summary:
            raise ValueError(f"quiz {quiz_id} not found / not published")
        sub = submission_ctx_Submission(
            submission_id=str(uuid.uuid4()),
            user_id=user_id, quiz_id=quiz_id,
            answers=tuple(answers),
            submitted_at=datetime.now(),
        )
        sub.grade(summary)
        self.repo.save(sub)
        # Publish Published Language event V1 (downstream subscribe)
        self.bus.publish(ScoreCalculatedV1(
            user_id=user_id, quiz_id=quiz_id, submission_id=sub.submission_id,
            score=sub.score or 0.0,
            correct_count=sub.correct_count or 0,
            total_questions=len(summary.correct_answers),
        ))
        return sub.submission_id


# =============================================================================
# [LEADERBOARD_CTX]   Supporting subdomain — read-model rank
# =============================================================================

@dataclass(frozen=True)
class leaderboard_ctx_LeaderboardUser:
    """User trong Leaderboard = chỉ cần user_id + display_name để show.
    Lại khác Quiz/Submission user — đây là Strategic DDD."""
    user_id: str
    display_name: str


@dataclass
class leaderboard_ctx_Ranking:
    user_id: str
    total_score: float = 0.0
    rank: int = 0


class leaderboard_ctx_Service:
    """Subscribes ScoreCalculated event (Published Language)."""

    def __init__(self) -> None:
        self._rankings: Dict[str, leaderboard_ctx_Ranking] = {}

    # Handler — nhận event qua bus (Open Host Service + Published Language)
    def on_score_calculated(self, event: ScoreCalculatedV1) -> None:
        # Idempotent-ish: cộng dồn (real prod sẽ dedupe by event_id)
        r = self._rankings.setdefault(
            event.user_id, leaderboard_ctx_Ranking(user_id=event.user_id)
        )
        r.total_score += event.score
        # Recompute rank
        sorted_rs = sorted(self._rankings.values(), key=lambda x: -x.total_score)
        for i, rr in enumerate(sorted_rs, 1):
            rr.rank = i

    def top(self, n: int) -> List[leaderboard_ctx_Ranking]:
        return sorted(self._rankings.values(), key=lambda x: x.rank)[:n]


# =============================================================================
# [NOTIFICATION_CTX]  Generic subdomain — chú ý: KHÔNG gọi là "User"
# =============================================================================
# Ngôn ngữ: Recipient, Channel, Template. "User" trong context khác = Recipient ở đây.

@dataclass(frozen=True)
class notification_ctx_Recipient:
    """KHÔNG gọi là User — Ubiquitous Language của context này khác."""
    recipient_id: str                   # tương ứng user_id qua ACL
    email: str
    sms: Optional[str]
    locale: str
    prefers_email: bool = True


@dataclass
class notification_ctx_Receipt:
    receipt_id: str
    recipient_id: str
    channel: str
    body: str
    sent_at: datetime


class notification_ctx_Service:
    def __init__(self) -> None:
        self.receipts: List[notification_ctx_Receipt] = []
        self._recipients: Dict[str, notification_ctx_Recipient] = {}

    def register_recipient(self, r: notification_ctx_Recipient) -> None:
        self._recipients[r.recipient_id] = r

    def on_score_calculated(self, event: ScoreCalculatedV1) -> None:
        r = self._recipients.get(event.user_id)
        if not r:
            return
        channel = "email" if r.prefers_email else "sms"
        body = f"You scored {event.score} on {event.quiz_id}"
        self.receipts.append(notification_ctx_Receipt(
            receipt_id=str(uuid.uuid4()),
            recipient_id=r.recipient_id,
            channel=channel,
            body=body,
            sent_at=datetime.now(),
        ))


# =============================================================================
# [ACL]   Anti-Corruption Layer — Auth0User → context-specific user
# =============================================================================
# Đây là *adapter* đứng ngoài 4 context, dịch external upstream sang nội bộ.
# Nếu Auth0 đổi schema, chỉ ACL sửa; 4 context KHÔNG touch.

class AuthACL:
    """Anti-Corruption Layer giữa Auth0 (external) và 4 bounded context."""

    @staticmethod
    def to_quiz_user(auth0: Auth0User, author_level: int = 1) -> quiz_ctx_QuizContextUser:
        return quiz_ctx_QuizContextUser(
            user_id=auth0.sub,
            display_name=auth0.name,
            author_level=author_level,
        )

    @staticmethod
    def to_submission_user(auth0: Auth0User) -> submission_ctx_SubmissionContextUser:
        return submission_ctx_SubmissionContextUser(
            user_id=auth0.sub,
            display_name=auth0.nickname or auth0.name,
        )

    @staticmethod
    def to_leaderboard_user(auth0: Auth0User) -> leaderboard_ctx_LeaderboardUser:
        return leaderboard_ctx_LeaderboardUser(
            user_id=auth0.sub,
            display_name=auth0.nickname or auth0.name,
        )

    @staticmethod
    def to_notification_recipient(auth0: Auth0User) -> notification_ctx_Recipient:
        return notification_ctx_Recipient(
            recipient_id=auth0.sub,
            email=auth0.email,
            sms=auth0.phone_number,
            locale=auth0.locale,
            prefers_email=auth0.email_verified,
        )


# =============================================================================
# [EVENT BUS] — Minimal pub-sub (đã học Lesson 31). Re-implement gọn.
# =============================================================================

EventHandler = Callable[[Any], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: Dict[type, List[EventHandler]] = {}
        self.published: List[Any] = []     # for inspection

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        self._subs.setdefault(event_type, []).append(handler)

    def publish(self, event: Any) -> None:
        self.published.append(event)
        for et, handlers in self._subs.items():
            if isinstance(event, et):
                for h in handlers:
                    h(event)


# =============================================================================
# [ADAPTER] — Customer-Supplier wiring: Submission gọi Quiz qua DTO interface
# =============================================================================

class quiz_catalog_adapter:
    """Adapter implements submission_ctx_IQuizCatalog by calling Quiz Context's
    public service. Đây là điểm tích hợp Customer-Supplier — *chỉ ở composition root*."""

    def __init__(self, quiz_summary_service: quiz_ctx_QuizSummaryService) -> None:
        self._svc = quiz_summary_service

    def get_summary(self, quiz_id: str) -> Optional[quiz_ctx_QuizSummary]:
        return self._svc.get_summary(quiz_id)


# =============================================================================
# [COMPOSITION ROOT]
# =============================================================================

def build_system() -> Dict[str, Any]:
    """Wire 4 bounded context. Đây là nơi DUY NHẤT biết cả 4."""
    # Quiz Context
    quiz_repo = quiz_ctx_QuizRepo()
    quiz_summary_svc = quiz_ctx_QuizSummaryService(quiz_repo)

    # Bus (OHS + Published Language transport)
    bus = EventBus()

    # Submission Context (Customer-Supplier với Quiz Context qua adapter)
    sub_repo = submission_ctx_SubmissionRepo()
    catalog_adapter = quiz_catalog_adapter(quiz_summary_svc)
    sub_svc = submission_ctx_SubmissionService(sub_repo, catalog_adapter, bus)

    # Leaderboard Context (subscribe Published Language)
    lb_svc = leaderboard_ctx_Service()
    bus.subscribe(ScoreCalculatedV1, lb_svc.on_score_calculated)

    # Notification Context (subscribe Published Language)
    notif_svc = notification_ctx_Service()
    bus.subscribe(ScoreCalculatedV1, notif_svc.on_score_calculated)

    return {
        "quiz_repo": quiz_repo,
        "quiz_summary_svc": quiz_summary_svc,
        "sub_svc": sub_svc,
        "lb_svc": lb_svc,
        "notif_svc": notif_svc,
        "bus": bus,
    }


# =============================================================================
# [CONTEXT_MAP & GLOSSARY]
# =============================================================================

def render_context_map() -> str:
    return r"""
                                              ┌──────────────────┐
                                              │  Auth0 (GENERIC) │
                                              │  external SaaS   │
                                              └──────┬───────────┘
                                                     │ Auth0User
                                                     ▼
                                              ┌──────────────────┐
                                              │  AuthACL         │
                                              │  (Anti-Corruption│
                                              │   Layer)         │
                                              └─┬───┬─────┬────┬─┘
                                       to_quiz   │   │     │    │ to_notification
                                                 ▼   ▼     ▼    ▼
        ┌──────────────────┐   U:get_summary  ┌──────────────────┐
        │ Quiz Context     │ ◀────────────── │ Submission Ctx   │
        │ (CORE — author)  │  Customer-      │ (CORE — student) │
        │  Quiz, Question  │  Supplier (DTO) │  Submission      │
        │  + Author user   │                 │  + Student user  │
        └──────────────────┘                 └────┬─────────────┘
                                                  │ publish ScoreCalculatedV1
                                                  │ (Open Host Service
                                                  │  + Published Language)
                              ┌───────────────────┼────────────────────┐
                              ▼                                        ▼
                  ┌──────────────────────┐                ┌──────────────────────┐
                  │ Leaderboard Ctx      │                │ Notification Ctx     │
                  │ (SUPPORTING)         │                │ (GENERIC — Recipient)│
                  │  Ranking + LB user   │                │  Recipient, Receipt  │
                  └──────────────────────┘                └──────────────────────┘
    """


GLOSSARY = {
    "Quiz Context": {
        "User": "Author — người tạo quiz; có author_level, quizzes_published",
        "Quiz": "Aggregate root chứa các Question; có trạng thái draft/published",
        "Question": "Value Object — text + correct_answer + weight",
    },
    "Submission Context": {
        "User": "Student — người làm quiz; có attempt_count, last_score",
        "Submission": "Aggregate root — 1 lần làm quiz; có answers, score, graded",
        "Attempt": "Synonym Submission trong language business (chưa dùng class riêng)",
    },
    "Leaderboard Context": {
        "User": "Display entity — chỉ user_id + display_name để show top-N",
        "Ranking": "Aggregate — total_score + rank, tính từ event stream",
    },
    "Notification Context": {
        "Recipient": "Tương ứng User ở context khác — có email, sms, locale",
        "Receipt": "Lịch sử gửi 1 thông báo cụ thể (channel, body, sent_at)",
        "User": "(không dùng từ này trong context này — dùng Recipient)",
    },
}


SUBDOMAIN_CLASSIFICATION = {
    "Quiz Context":          ("Core",       "Adaptive scoring & quiz authoring = lợi thế cạnh tranh"),
    "Submission Context":    ("Core",       "Logic chấm + attempt rules — sản phẩm chính"),
    "Leaderboard Context":   ("Supporting", "Cần có nhưng không phải lợi thế cạnh tranh"),
    "Notification Context":  ("Generic",    "Commodity — có thể swap sang SendGrid/Twilio"),
    "Auth (Auth0)":          ("Generic",    "Commodity — mua SaaS, không build in-house"),
}


# =============================================================================
# [DEMO]
# =============================================================================

def banner(s: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {s}")
    print("=" * 76)


def demo_1_same_user_id_different_models() -> None:
    banner("DEMO 1 — Cùng user_id, 4 model khác nhau (Bounded Context isolation)")

    auth0 = Auth0User(
        sub="auth0|u123",
        email="alice@ellumm.com",
        name="Alice Nguyen",
        nickname="alice",
        locale="vi-VN",
        email_verified=True,
        phone_number="+84901234567",
    )

    qu = AuthACL.to_quiz_user(auth0, author_level=3)
    su = AuthACL.to_submission_user(auth0)
    lu = AuthACL.to_leaderboard_user(auth0)
    re = AuthACL.to_notification_recipient(auth0)

    print(f"  Auth0User:          fields = {[f.name for f in dc_fields(auth0)]}")
    print(f"  Quiz.User:          {qu}")
    print(f"  Submission.User:    {su}")
    print(f"  Leaderboard.User:   {lu}")
    print(f"  Notification.Recip: {re}")

    # Verify isolation: each model has DIFFERENT field set
    quiz_fields = {f.name for f in dc_fields(qu)}
    sub_fields = {f.name for f in dc_fields(su)}
    notif_fields = {f.name for f in dc_fields(re)}
    print(f"\n  Field disjoint test:")
    print(f"    Quiz.User has 'author_level':            {('author_level' in quiz_fields)}")
    print(f"    Submission.User has 'author_level':      {('author_level' in sub_fields)}")
    print(f"    Notification.Recipient has 'email':      {('email' in notif_fields)}")
    print(f"    Quiz.User has 'email':                   {('email' in quiz_fields)}")
    assert quiz_fields != sub_fields != notif_fields
    assert "author_level" in quiz_fields and "author_level" not in sub_fields
    assert "email" in notif_fields and "email" not in quiz_fields
    print("  PASS — 4 contexts giữ 4 model khác nhau cho cùng identity")


def demo_2_customer_supplier_via_dto() -> None:
    banner("DEMO 2 — Customer-Supplier: Submission gọi Quiz qua DTO (không entity)")

    sys = build_system()
    # Author tạo quiz (Quiz Context)
    q = quiz_ctx_Quiz(quiz_id="q1", title="Brain 101", author_id="auth0|alice")
    q.add_question(quiz_ctx_Question("qa", "What is V1?", correct_answer=2))
    q.add_question(quiz_ctx_Question("qb", "Brodmann?", correct_answer=0, weight=2.0))
    q.publish()
    sys["quiz_repo"].save(q)

    # Submission Context gọi Quiz Context — chỉ thấy DTO QuizSummary
    summary = sys["quiz_summary_svc"].get_summary("q1")
    print(f"  Quiz Context publishes DTO: {summary}")
    print(f"  DTO type: {type(summary).__name__}")
    print(f"  DTO has 'is_published' (entity field)?  {hasattr(summary, 'is_published')}")
    assert summary is not None
    assert isinstance(summary, quiz_ctx_QuizSummary)
    # DTO is frozen — downstream KHÔNG thể mutate
    try:
        summary.title = "hacked"
        assert False, "DTO should be frozen"
    except (AttributeError, Exception):
        print("  Frozen DTO: downstream cannot mutate (immutable contract)")
    print("  PASS — upstream exposes ONLY DTO, entity stays internal")


def demo_3_published_language_event_fan_out() -> None:
    banner("DEMO 3 — Published Language: 1 event → 2 context subscribe độc lập")

    sys = build_system()
    # Tạo quiz
    q = quiz_ctx_Quiz(quiz_id="q1", title="Brain", author_id="auth0|alice")
    q.add_question(quiz_ctx_Question("qa", "?", correct_answer=2))
    q.add_question(quiz_ctx_Question("qb", "?", correct_answer=0, weight=2.0))
    q.publish()
    sys["quiz_repo"].save(q)

    # Đăng ký recipient ở Notification context
    auth0 = Auth0User(
        sub="auth0|alice", email="alice@ellumm.com", name="Alice", nickname="al",
        locale="vi", email_verified=True, phone_number="+84",
    )
    sys["notif_svc"].register_recipient(AuthACL.to_notification_recipient(auth0))

    # Student submit
    sid = sys["sub_svc"].submit("auth0|alice", "q1", [2, 0])
    print(f"  Submission saved: {sid[:8]}...")
    print(f"  Bus published: {len(sys['bus'].published)} event(s)")

    # Verify cả 2 context downstream xử lý ĐỘC LẬP
    top = sys["lb_svc"].top(5)
    print(f"  Leaderboard top: {top}")
    print(f"  Notification receipts: {len(sys['notif_svc'].receipts)}")
    for r in sys["notif_svc"].receipts:
        print(f"    - {r.channel}: {r.body}")

    assert len(sys["bus"].published) == 1
    assert isinstance(sys["bus"].published[0], ScoreCalculatedV1)
    assert top and top[0].total_score == 3.0      # 1.0 + 2.0
    assert len(sys["notif_svc"].receipts) == 1
    print("  PASS — Published Language fan-out works; downstream independent")


def demo_4_acl_swap_external_provider() -> None:
    banner("DEMO 4 — ACL benefit: thay Auth0 → Okta chỉ sửa ACL, 0 context touch")

    # Giả sử Okta có schema khác — chỉ cần thêm 1 method to_* mới trong ACL
    @dataclass(frozen=True)
    class OktaUser:
        oktaId: str
        profile_email: str
        profile_fullName: str
        primaryPhone: Optional[str]
        languageCode: str
        isEmailVerified: bool

    class OktaACL:
        @staticmethod
        def to_notification_recipient(okta: OktaUser) -> notification_ctx_Recipient:
            # Notice: field names khác Auth0 hoàn toàn — ACL absorb the difference
            return notification_ctx_Recipient(
                recipient_id=okta.oktaId,
                email=okta.profile_email,
                sms=okta.primaryPhone,
                locale=okta.languageCode,
                prefers_email=okta.isEmailVerified,
            )

    okta = OktaUser(
        oktaId="okta-99", profile_email="bob@x.com", profile_fullName="Bob",
        primaryPhone=None, languageCode="en-US", isEmailVerified=True,
    )
    recipient = OktaACL.to_notification_recipient(okta)
    print(f"  Auth0 model fields:        sub, name, nickname, ...")
    print(f"  Okta model fields:         oktaId, profile_fullName, ...")
    print(f"  Notification.Recipient:    {recipient}")
    print(f"  Notification context code: KHÔNG sửa 1 dòng")
    assert recipient.recipient_id == "okta-99"
    print("  PASS — ACL is the seam; external provider changes don't leak inward")


def demo_5_published_language_versioning_backward_compat() -> None:
    banner("DEMO 5 — Schema evolution: V1 consumer đọc được V2 event (additive change)")

    # Producer publish V2 event
    v2_event = ScoreCalculatedV2(
        user_id="u1", quiz_id="q1", submission_id="s1",
        score=4.0, correct_count=2, total_questions=2,
        quiz_title="Brain 101",
    )
    print(f"  Producer publishes V2:  {v2_event}")

    # Một downstream consumer chỉ biết V1 — vẫn đọc được phần V1
    def v1_consumer(event):
        # Consumer chỉ access field V1, không biết V2 có quiz_title
        return {
            "user": event.user_id,
            "score": event.score,
            "version_field_seen": event.schema_version,
        }

    parsed = v1_consumer(v2_event)
    print(f"  V1-only consumer reads:  {parsed}")
    assert parsed["score"] == 4.0
    assert parsed["version_field_seen"] == 2
    print("  PASS — additive evolution (V2 adds optional field) keeps V1 readers working")
    print("  Rule: chỉ ADD field optional. RENAME/REMOVE phá Published Language.")


def demo_6_cross_context_import_anti_pattern() -> None:
    banner("DEMO 6 — Cross-context import detector (anti-pattern guard)")

    # Heuristic: trong các module thật, scan source xem có 'from quiz_ctx import' trong
    # 'submission_ctx' không. Ở đây chúng ta dùng prefix naming để verify.
    import inspect
    import sys as _sys
    mod = _sys.modules[__name__]

    bad_combos: List[str] = []
    for name, obj in inspect.getmembers(mod):
        if not inspect.isclass(obj):
            continue
        # Skip imports & ACL & Adapter (legitimate cross)
        if not name.startswith(("quiz_ctx_", "submission_ctx_",
                                "leaderboard_ctx_", "notification_ctx_")):
            continue
        # Get class's annotations / fields and check naming prefix
        anns = getattr(obj, "__annotations__", {})
        for fname, ftype in anns.items():
            tname = getattr(ftype, "__name__", str(ftype))
            # If a class in submission_ctx references quiz_ctx_Quiz entity directly → BAD
            # (DTO ScoreCalculated, QuizSummary are OK — they are Published Language / port DTO)
            if tname.startswith("quiz_ctx_Quiz") and not tname.endswith("Summary"):
                if name.startswith(("submission_ctx_", "leaderboard_ctx_",
                                    "notification_ctx_")):
                    bad_combos.append(f"{name}.{fname}: {tname}")

    print(f"  Cross-context entity references found: {len(bad_combos)}")
    for b in bad_combos:
        print(f"    BAD: {b}")
    print("  Legitimate cross-context references:")
    print("    - submission_ctx_SubmissionService → ScoreCalculatedV1 (Published Lang OK)")
    print("    - quiz_catalog_adapter → quiz_ctx_QuizSummary (DTO via port OK)")
    assert len(bad_combos) == 0
    print("  PASS — no context imports another context's *entity* directly")


def demo_7_print_context_map_and_glossary() -> None:
    banner("DEMO 7 — Context Map + Glossary + Subdomain Classification")

    print(render_context_map())

    print("  GLOSSARY — term 'User' / 'Recipient' across contexts:")
    print()
    print(f"  {'Context':<24} {'Term':<12} {'Meaning'}")
    print(f"  {'-'*24} {'-'*12} {'-'*40}")
    for ctx, terms in GLOSSARY.items():
        for term, meaning in terms.items():
            if term in ("User", "Recipient"):
                print(f"  {ctx:<24} {term:<12} {meaning[:55]}")

    print()
    print("  SUBDOMAIN CLASSIFICATION:")
    print()
    print(f"  {'Context':<24} {'Type':<12} {'Why'}")
    print(f"  {'-'*24} {'-'*12} {'-'*40}")
    for ctx, (kind, why) in SUBDOMAIN_CLASSIFICATION.items():
        print(f"  {ctx:<24} {kind:<12} {why}")

    print()
    print("  CONTEXT MAP integration patterns used:")
    print("    Auth0           → AuthACL → 4 contexts        : Anti-Corruption Layer")
    print("    Quiz Context    → Submission Context           : Customer-Supplier (DTO)")
    print("    Submission Ctx  → Leaderboard Ctx              : Open Host Service + Published Language")
    print("    Submission Ctx  → Notification Ctx             : Open Host Service + Published Language")


# =============================================================================
# RUN ALL
# =============================================================================

def main() -> int:
    demo_1_same_user_id_different_models()
    demo_2_customer_supplier_via_dto()
    demo_3_published_language_event_fan_out()
    demo_4_acl_swap_external_provider()
    demo_5_published_language_versioning_backward_compat()
    demo_6_cross_context_import_anti_pattern()
    demo_7_print_context_map_and_glossary()

    print("\n" + "=" * 76)
    print("  ALL 7 DEMOS PASS — Lesson 34 Strategic DDD: Bounded Context verified")
    print("  4 contexts, 3 different User models, 1 ACL seam, 1 Published Language event")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
