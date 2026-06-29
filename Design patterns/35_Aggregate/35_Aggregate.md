# Lesson 35 — Tactical DDD: Aggregate sâu
## Cell as Aggregate — Tế bào là aggregate sinh học hoàn hảo: membrane = consistency boundary; ion homeostasis = invariant; membrane proteins = aggregate root methods; cross-cell signaling = domain events.

---

## TÓM TẮT MỘT DÒNG

**Aggregate** = một *consistency boundary* gồm 1 hoặc nhiều entity + value object, được truy cập **chỉ qua một class duy nhất** (Aggregate Root). AR chịu trách nhiệm enforce **invariant** (luật business luôn đúng), publish **domain event** từ bên trong method, và đảm bảo **1 transaction sửa tối đa 1 aggregate**. Cross-aggregate quan hệ qua **ID, không qua object reference**.

> Một tế bào người là *atomic transactional unit* của sinh học. Bên trong: ion homeostasis nghiêm ngặt — Na⁺ ngoài 145 mM / trong 12 mM, K⁺ ngoài 4 mM / trong 140 mM, Ca²⁺ ngoài 1.8 mM / trong 0.0001 mM (10⁴ ratio). Phá vỡ ratio → cell chết (excitotoxicity). Truy cập cytoplasm từ bên ngoài bị *cấm tuyệt đối* — chỉ qua **membrane proteins** (channels, pumps, receptors), và mỗi protein có quy tắc cụ thể (Na⁺/K⁺ pump tốn 1 ATP đẩy 3 Na⁺ ra + 2 K⁺ vào). Hai tế bào *kế nhau* nhưng *không bao giờ chạm cytoplasm trực tiếp* — giao tiếp qua hormone, neurotransmitter, gap junction (cẩn thận quy định). Tổng hợp organelle bên trong (ER → Golgi → vesicle) như multi-entity coordinate **đồng thời, atomic** — failure 1 bước → unfolded protein response rollback. Đó là Aggregate sinh học: boundary rõ, invariant chặt, public API qua "root", cross-cell qua event/messenger. 3.5 tỷ năm tiến hoá đã chọn nguyên lý này.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Lesson 34 (Bounded Context) cắt boundary giữa các vùng business. Lesson 35 hỏi tiếp: **bên trong một bounded context, làm sao đảm bảo invariant?**

4 vấn đề khi không có Aggregate:

1. **Invariant rải ra service**: "Submission không được grade 2 lần" — viết ở `SubmissionService.grade()`, lặp ở `GradingController`, lặp ở `BackgroundReconciliationJob`. Mỗi nơi 1 phiên bản, lệch — bug.

2. **Object navigation đi xa**: `submission.user.account.billing.last_invoice.amount` — code phụ thuộc 5 tầng object. Đổi `Invoice.amount → total` lan ra 50 file.

3. **Transaction unclear**: PR sửa `Submission.score` + `User.total_xp` + `Leaderboard.rank` trong 1 method. Lock contention. Khi 2 process chạy song song → deadlock hoặc state lệch.

4. **Anaemic exposure**: `submission.finalized = True` ai cũng có thể gọi — bỏ qua "phải có score trước". Invariant phá.

Aggregate đóng 4 cái bằng 4 quy tắc:

1. **Invariant inside aggregate root** — tất cả luật bảo vệ aggregate ở 1 chỗ.
2. **Reference by ID, not by object** giữa aggregates — không có `submission.user.account` graph.
3. **AR-per-transaction** — 1 transaction sửa 1 aggregate. Multi-aggregate dùng saga + eventual consistency.
4. **Tell-don't-ask** — gọi `submission.grade(quiz)`, không phải `submission.score = compute(submission, quiz)`.

### 1.2. Định nghĩa và 5 thành phần

**Aggregate** (Evans 2003):

> *"A cluster of associated objects that we treat as a unit for the purpose of data changes. Each Aggregate has a root and a boundary. The boundary defines what is inside the Aggregate. The root is a single, specific Entity contained in the Aggregate."*

5 thành phần:

| Thành phần | Mô tả | Vd Ellumm |
|------------|-------|-----------|
| **Aggregate Root (AR)** | Entity duy nhất bên ngoài có thể tham chiếu | `Submission` |
| **Internal Entity** | Entity bên trong, chỉ AR có quyền sửa | `Attempt` (lịch sử thử lại) |
| **Value Object (VO)** | Immutable, no identity, định nghĩa bằng attribute | `Score`, `Answer` |
| **Invariant** | Business rule luôn đúng *bên trong* aggregate | "Không grade 2 lần", "Score ∈ [0, max]" |
| **Domain Event** | Past-tense fact publish từ AR method | `SubmissionGraded(submission_id, score)` |

3 thành phần ngoài aggregate (Lesson 35 nhắc, Lesson 37 đào sâu):

| | Mô tả |
|---|---|
| **Repository** | Abstraction over persistence của AR. **1 repo cho 1 AR**, không cho internal entity |
| **Factory** | Tạo AR mới với invariant ban đầu |
| **Domain Service** | Logic không thuộc về aggregate nào (ví dụ tính rate phụ thuộc nhiều aggregate) |

### 1.3. Bốn nguyên tắc Vernon (*Effective Aggregate Design*, 2010)

Vernon 3-paper-series tinh chỉnh Evans bằng 4 rule thực dụng:

**(a) Model true invariants in consistency boundaries**.
Chỉ những rule *transactionally required* mới đặt trong aggregate. Rule eventual-consistent (ví dụ "tổng score user ≤ max_lifetime_score") **không** thuộc aggregate Submission — đó là check sau qua background job.

**(b) Design small aggregates**.
Aggregate nhỏ:
- Ít contention khi concurrent.
- Memory load nhanh (không bị "load 10,000 child entity").
- Persistence transaction ngắn.
- Đại đa số aggregate nên có **1 root entity + few VOs**.

Aggregate to chỉ khi *invariant business thật sự yêu cầu*.

**(c) Reference other aggregates by identity only**.
KHÔNG: `submission.user = user_obj`.
ĐÚNG: `submission.user_id = "u1"`.

Lý do:
- Tránh load lazy chain dài.
- Mỗi aggregate độc lập transactionally.
- Đổi internal model User không phá Submission.
- Sẵn sàng cho cross-context / cross-service.

**(d) Use eventual consistency outside the boundary**.
Sửa 2 aggregate cần *eventual* consistency, không *strong*. Implementation: publish domain event từ aggregate A, handler cập nhật aggregate B trong transaction khác.

### 1.4. Neuroscience — Cell as Aggregate

**Tế bào** là *unit of life* — tiến hoá đã chọn boundary này hơn 3.5 tỷ năm. Cấu trúc tế bào mapping chính xác sang aggregate:

**(a) Plasma membrane = aggregate boundary**.
Phospholipid bilayer + cholesterol + protein dày ~5 nm. Hoàn toàn không cho ion, protein, nucleotide qua *trực tiếp* — phải qua *transport protein* cụ thể. Aggregate boundary cũng vậy: code bên ngoài không được chạm field, chỉ gọi method.

**(b) Ion homeostasis = invariants**.
Nội bào *bắt buộc* duy trì:
- Na⁺ inside: 12 mM (outside 145).
- K⁺ inside: 140 mM (outside 4).
- Cl⁻ inside: 10 mM (outside 110).
- Ca²⁺ inside: 100 nM (outside 1.8 mM) — chênh 10⁴ lần!
- pH: 7.2 (outside 7.4).
- Volume: chống osmotic swell/shrink.

Tổng *energy budget* của tế bào ~70% dùng cho Na⁺/K⁺ pump duy trì invariant này. Phá vỡ → necrosis hoặc apoptosis. Aggregate invariant: "Submission không thể finalize trước khi grade" — code đầu tư đáng kể (ATP của codebase = test + review effort) để enforce.

**(c) Membrane proteins = aggregate root methods**.
4 loại membrane protein, tương ứng 4 loại public method:
- *Channel* (selective ion flow): query method `get_*()`.
- *Pump* (active transport, costs ATP): command method `submit_*()`, `grade_*()`.
- *Receptor* (signal in): event handler.
- *Transporter / exporter* (signal out): emit domain event.

Mỗi protein có *gating rule* cụ thể (voltage-gated, ligand-gated, mechanically-gated) = method có pre-condition (invariant check).

**(d) Cross-cell communication = domain events**.
Tế bào *không bao giờ* chạm cytoplasm tế bào khác. Truyền tin qua:
- *Hormone* (long-range, slow) = async event qua message broker.
- *Neurotransmitter* (short-range, fast) = sync event in-process.
- *Gap junction* (direct cytoplasmic connection, vài tế bào đặc biệt như cardiomyocyte) = shared memory, *anti-pattern* trong code (đối lập aggregate isolation, chỉ dùng khi *performance critical absolute*).

**(e) Endoplasmic reticulum → Golgi → vesicle = multi-step transaction inside aggregate**.
Protein được synthesize, fold, modify, package, ship — **atomic**. Nếu protein misfold ở ER → unfolded protein response → rollback / degrade. Aggregate cũng vậy: 1 method có thể coordinate nhiều internal entity, tất cả thành công hoặc rollback.

**Tóm lại**: cell membrane là "Aggregate Root pattern" của sinh học. Vi phạm → cell chết. Code aggregate vi phạm → bug data corruption.

### 1.5. So sánh với patterns đã học

| | Lesson 24 SRP | Lesson 28 DIP | Lesson 32 CQRS+ES | Lesson 35 Aggregate |
|---|---|---|---|---|
| **Tầm** | Class-level | Class-level | System-level | Cluster-of-entity |
| **Hỏi** | "1 lý do thay đổi?" | "Phụ thuộc abstraction?" | "Read/Write tách?" | "Consistency boundary ở đâu?" |
| **Đảm bảo** | Cohesion | Replaceability | Read scale | Invariant |
| **Quan hệ với Aggregate** | AR có cohesive method | AR dùng port | AR có history qua event store | (Đây) |

> Lesson 32 (CQRS+ES) đã chạm aggregate — Lesson 35 đào sâu *design principles* của aggregate. Một AR tốt → ES tốt → CQRS tốt.

---

## MỨC 2 — CẤU TRÚC

### 2.1. 6 trách nhiệm của Aggregate Root

```
┌──────────────────────────────────────────────────────────────┐
│                  AGGREGATE ROOT (AR)                         │
│                                                              │
│  1. ENFORCE INVARIANTS    "score must be in [0, max]"        │
│  2. EXPOSE PUBLIC API     submit() grade() retry() finalize()│
│  3. HIDE INTERNAL STATE   _answers, _attempts (private)      │
│  4. EMIT DOMAIN EVENTS    self._pending_events.append(...)   │
│  5. REFERENCE BY ID       self._quiz_id  (not self._quiz)    │
│  6. BE FACTORY-CREATED    Submission.create() static method  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
            ▲                                          │
            │ command via method call                  │ emit event
            │                                          ▼
       OUTSIDE WORLD                            EVENT BUS / OUTBOX
       (HTTP, CLI, handler)                     (downstream aggregates)
```

### 2.2. AR-per-transaction rule (đào sâu)

Quy tắc Vernon: **1 transaction được phép sửa tối đa 1 aggregate instance.**

Hậu quả thực tế:
- Submit + Grade + UpdateLeaderboard ≠ 1 transaction. Là 3 transaction nối qua event.
- Lock chỉ giữ 1 aggregate → contention thấp.
- Crash recovery rõ: rollback 1 aggregate đơn giản.

Vi phạm:
```python
# BAD
with db.transaction():
    submission.grade(...)               # ✗ aggregate 1
    user.add_xp(...)                    # ✗ aggregate 2 (User)
    leaderboard.update(...)             # ✗ aggregate 3
```

Đúng:
```python
# GOOD — 1 transaction per aggregate, chuỗi qua event
with db.transaction():
    submission.grade(...)               # 1 aggregate
    submission_repo.save(submission)
    # save() automatically publishes domain events (Outbox - Lesson 31)
# Later async: handler cập nhật User aggregate
# Later async: handler cập nhật Leaderboard aggregate
```

> Ngoại lệ: nếu 2 aggregate *thật sự* cần strong consistency, → có thể chỉ đó là *1 aggregate* (gộp). Câu hỏi: business rule có yêu cầu transactional? Nếu không → tách.

### 2.3. Reference by ID — chi tiết

Aggregate A muốn quan hệ aggregate B → giữ `b_id`, không `B` object.

```python
class Submission:                       # AR
    user_id: str                        # ID, không User
    quiz_id: str                        # ID, không Quiz

# Cần info từ User aggregate? → query through use case service
def get_submission_with_user_view(sub_id):
    sub = sub_repo.get(sub_id)
    user_dto = user_facade.get_basic_info(sub.user_id)    # cross-aggregate query
    return view_model_combine(sub, user_dto)
```

Lợi:
- Submission test pure không cần User instance.
- Đổi User schema không phá Submission.
- Cross-context tự nhiên (Lesson 34): aggregate ở different bounded context cũng chỉ giao tiếp qua ID + event.

> Khi naked ID khó đọc, định nghĩa **strongly-typed ID** (Value Object): `UserId = NewType("UserId", str)`. Đỡ confusion `submission.user_id` vs `submission.author_id`.

### 2.4. Domain Service vs Aggregate Method

Đôi khi logic *không thuộc về* aggregate cụ thể:

```
Q: "Có thể retry quiz không?"
   Dữ liệu cần: submission state + user tier + time since last attempt + global config

→ Không thuộc Submission (cần user tier);
→ Không thuộc User (cần submission state);
→ Domain Service: RetryPolicy.can_retry(submission, user, config) -> bool
```

**Domain Service** đặc điểm:
- *Stateless* (không có field).
- Method nhận nhiều aggregate / VO làm input.
- Return decision hoặc create new entity.
- Thuộc *domain layer*, không infra.

Phân biệt với Application Service (Lesson 30 Hex):
- Domain Service: business logic.
- Application Service: orchestration (transaction, persist, publish event).

### 2.5. Tell-Don't-Ask — anti-anemic

```python
# BAD (anemic — ask)
sub = repo.get(id)
if sub.score is None and sub.attempts < 3:        # logic outside
    new_score = compute(sub.answers, quiz)         # external compute
    sub.score = new_score                          # external write
    sub.graded_at = now()                          # bypass invariant!

# GOOD (rich — tell)
sub = repo.get(id)
sub.grade(quiz_summary)                            # tell aggregate
# Aggregate enforces: attempts < 3, not already graded, compute internally,
# set graded_at, emit SubmissionGraded event
```

Quy tắc: **không expose mutable field**. Mọi state change qua method với pre-condition + invariant check.

### 2.6. 5 invariants của aggregate design

1. **Reference outside → only via AR**. Internal entity không bao giờ leak ra.
2. **Internal entity reference outside → only by ID**.
3. **Invariants enforced inside AR methods**, not in service.
4. **State change emits domain event**.
5. **1 transaction = 1 aggregate instance**.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
# Value Objects (immutable, frozen=True)
@frozen Answer       { question_id, value }
@frozen Score        { points, max_points }  validate 0 ≤ points ≤ max_points
@frozen AttemptId    { value: str }

# Domain Events (immutable)
@frozen SubmissionCreated  { submission_id, user_id, quiz_id, occurred_at }
@frozen SubmissionGraded   { submission_id, score, correct_count, occurred_at }
@frozen SubmissionRetried  { submission_id, attempt_no, occurred_at }
@frozen SubmissionFinalized { submission_id, occurred_at }

# Internal Entity (only AR manages)
class Attempt:
    attempt_id: AttemptId
    answers: Tuple[Answer]
    submitted_at: datetime
    score: Optional[Score]

# AGGREGATE ROOT
class Submission:
    # Private state
    _id, _user_id, _quiz_id, _attempts: List[Attempt], _status, _pending_events

    # Factory (no public constructor in real DDD — Python doesn't fully support)
    @staticmethod
    def create(user_id, quiz_id) -> Submission:
        sub = Submission(_id=new_uuid(), _user_id=user_id, _quiz_id=quiz_id,
                         _attempts=[], _status=DRAFT, _pending_events=[])
        sub._pending_events.append(SubmissionCreated(...))
        return sub

    # Public command method (Tell, not Ask)
    def submit_answers(self, answers: Tuple[Answer]) -> None:
        require self._status == DRAFT, "must be draft"
        require len(answers) > 0,       "answers required"
        attempt = Attempt(new_uuid(), answers, now(), None)
        self._attempts.append(attempt)
        self._status = SUBMITTED

    def grade(self, quiz_summary: QuizSummary) -> None:
        require self._status == SUBMITTED, "must be submitted"
        latest = self._attempts[-1]
        require latest.score is None,   "already graded"
        score = compute_score(latest.answers, quiz_summary)
        latest = replace(latest, score=score)
        self._attempts[-1] = latest
        self._status = GRADED
        self._pending_events.append(SubmissionGraded(self._id, score, ...))

    def retry(self, retry_policy: RetryPolicy, user_quota: int) -> None:
        require self._status == GRADED, "can only retry after grade"
        require retry_policy.can_retry(len(self._attempts), user_quota), "quota exceeded"
        self._status = DRAFT
        self._pending_events.append(SubmissionRetried(self._id, len(self._attempts)+1))

    def finalize(self) -> None:
        require self._status == GRADED, "must grade first"
        self._status = FINALIZED
        self._pending_events.append(SubmissionFinalized(self._id, now()))

    # Read-only properties
    @property id, user_id, quiz_id, status, attempts_count, current_score
    @property pending_events  # tuple, returned + cleared by repo on save

# Domain Service (stateless, cross-aggregate logic)
class RetryPolicy:
    def can_retry(attempts_used: int, user_quota: int) -> bool:
        return attempts_used < user_quota

# Repository (returns ONLY AR, never Attempt)
interface ISubmissionRepository:
    save(submission: Submission)
    get(id: SubmissionId) -> Submission
    by_user(user_id: str) -> List[Submission]

# Application Service (Hex driving port — Lesson 30)
class SubmissionAppService:
    def submit(self, user_id, quiz_id, answers):
        with db.transaction():
            sub = Submission.create(user_id, quiz_id)
            sub.submit_answers(answers)
            self.repo.save(sub)             # publishes events via outbox
            return sub.id
```

### 3.2. Bảng 2x2 nhớ là đủ

|  | **Trong aggregate boundary** | **Ngoài aggregate boundary** |
|---|---|---|
| **State mutation** | AR method (strong consistency, transactional) | Saga + domain event (eventual) |
| **Reference** | Direct entity object (chỉ AR thấy internal) | By ID only |

Mọi quyết định aggregate quy về 4 ô này.

---

## NĂM CHIỀU SO SÁNH (in não vs in code)

| Chiều | Trong tế bào | Trong aggregate |
|-------|--------------|------------------|
| **Cấu tạo** | Plasma membrane + cytoplasm + organelles (ribosome, ER, Golgi, vesicle) | AR + internal entities + value objects |
| **Vị trí** | Boundary 5 nm phospholipid bilayer + cholesterol | Boundary tại class methods (Python: convention `_private`) |
| **Chức năng** | Duy trì ion homeostasis (Na/K/Ca/Cl/pH), respond to signal, produce protein | Enforce business invariants, expose public API, emit events |
| **Kết nối** | Membrane proteins (channel/pump/receptor); cross-cell via hormone/neurotransmitter | Aggregate root methods; cross-aggregate via domain event + ID reference |
| **Ý nghĩa** | 3.5 tỷ năm tiến hoá: atomic transactional unit chiến thắng. Cell death khi vỡ invariant | Boundary tốt → code dễ test, scale, refactor. Bad boundary → data corruption, contention |

---

## BA VÍ DỤ

### Ví dụ 1 — Vận hành thường (happy path)

Student submit quiz, sau đó grade, sau đó finalize:

```python
# Application service
def submit_and_grade(self, user_id, quiz_id, answers):
    with self.uow:                                  # unit of work (1 tx)
        sub = Submission.create(user_id, quiz_id)   # event: SubmissionCreated
        sub.submit_answers(answers)                 # state: DRAFT → SUBMITTED
        summary = self.quiz_catalog.get(quiz_id)    # cross-aggregate by ID
        sub.grade(summary)                          # event: SubmissionGraded
        self.repo.save(sub)                         # persist + publish events

# Later, after teacher confirms:
def teacher_finalize(self, sub_id):
    with self.uow:
        sub = self.repo.get(sub_id)
        sub.finalize()                              # event: SubmissionFinalized
        self.repo.save(sub)
```

Mọi state change qua aggregate method. Invariant tự động enforce. Domain event tự động publish. Test:

```python
sub = Submission.create("u1", "q1")
sub.submit_answers((Answer("q1a", 2), Answer("q1b", 0)))
sub.grade(quiz_summary)
assert sub.status == GRADED
assert sub.current_score.points == 5.0
events = sub.collect_pending_events()
assert len(events) == 3   # Created, Submitted (within create+submit), Graded
```

Không cần DB. Không cần service layer. Aggregate test pure 0.x ms.

### Ví dụ 2 — Hỏng / vi phạm (failure mode)

**Vi phạm A — Public mutable field**:
```python
# BAD
class Submission:
    score: Optional[float] = None
    status: str = "DRAFT"

# Code khác có thể:
sub.score = 99999                        # bypass invariant [0, max]
sub.status = "FINALIZED"                 # bypass state machine
```
→ Đúng: `_score`, `_status` private; method `grade()`/`finalize()` enforce.

**Vi phạm B — Cross-aggregate by reference**:
```python
# BAD
class Submission:
    user: User                           # ✗ direct ref
    quiz: Quiz                           # ✗ direct ref

# Khi load submission, lazy-load User → DB query, có thể Quiz → 2 queries.
# Đổi User schema → vỡ Submission.
```
→ Đúng: `user_id`, `quiz_id`. Cross-aggregate query qua service / facade.

**Vi phạm C — Multi-aggregate trong 1 transaction**:
```python
# BAD
with db.tx():
    sub.grade(...)                        # aggregate 1
    user.total_xp += sub.score            # aggregate 2 — phá AR-per-tx
    leaderboard.bump(user.id, sub.score)  # aggregate 3
```
→ Đúng: chỉ commit Submission; publish event `SubmissionGraded`; handler riêng cập nhật User, Leaderboard trong transaction sau.

**Vi phạm D — Anemic + service-driven**:
```python
# BAD
class Submission:
    user_id, quiz_id, score, status      # data bag

class SubmissionService:
    def grade(self, sub, quiz):
        # logic ở đây — entity rỗng
        if sub.status != "SUBMITTED": raise ...
        sub.score = compute(...)
        sub.status = "GRADED"
        # publish event ở service, không phải entity
```
→ Đúng: logic ở `Submission.grade()`. Service chỉ orchestrate.

**Vi phạm E — Aggregate quá to**:
```python
# BAD
class User:                              # AR
    submissions: List[Submission]        # 10,000+ submissions
    payments: List[Payment]              # 500+ payments
    notifications: List[Notification]    # 100,000+
```
→ Load aggregate User = load 110,000 object. Đúng: User, Submission, Payment, Notification là 4 aggregate riêng, link by ID.

### Ví dụ 3 — Ứng dụng Ellumm Quiz

File `35_aggregate.py` đi kèm refactor Submission Context từ Lesson 34 lên tactical DDD chuẩn:
- `Submission` aggregate root, private state, 6 public method.
- `Attempt` internal entity (chỉ AR manage).
- `Answer`, `Score`, `AttemptId` value objects (frozen).
- 4 domain event publish từ inside method.
- `RetryPolicy` domain service (cross-aggregate logic).
- `UserAttemptQuota` aggregate riêng (per-user attempts).
- `ISubmissionRepository` returns AR only.
- 7 demo + 1 anti-pattern showcase.

---

## MỨC ARCHITECT — TRADE-OFFS & ANTI-PATTERNS

### Khi nào DÙNG aggregate explicit

- Có business invariant rõ ("score ≤ max", "không grade 2 lần").
- Multi-entity coordinate atomic (Submission + Attempts + Score).
- Cần audit trail (event-driven).
- Scale > 1 team, > 5 service.

### Khi nào KHÔNG cần

- CRUD pure (form → row → form, không có rule).
- Single field entity (Tag, Label).
- Read-only projection (Lesson 32 — projection không phải aggregate).
- Prototype/POC ngắn.

### Trade-offs

| Trục | Được | Mất |
|------|------|-----|
| **Invariant enforcement** | Tập trung 1 chỗ, không thể bypass | Boilerplate (private + method + event) |
| **Concurrency** | AR-per-tx → contention thấp | Cross-aggregate consistency = eventual (UI có thể flash) |
| **Test** | Pure unit test 0.x ms | Cần học cú pháp event collection + replay |
| **Onboarding** | Domain expert đọc được method names | Junior dev cần học DDD vocabulary |
| **Refactor** | Aggregate boundary đổi rất đắt | Đúng từ đầu = save tháng sau |

### Anti-patterns thường thấy

| Anti-pattern | Mô tả | Phát hiện |
|--------------|-------|-----------|
| **God Aggregate** | 1 aggregate bao mọi entity, load chậm | `load()` mất > 100 ms cho 1 AR |
| **Anemic Aggregate** | Entity rỗng + Service phình | Lớp Aggregate có < 3 method ngoài getter |
| **Cross-aggregate direct ref** | `sub.user = user_obj` | grep type annotation cross-aggregate |
| **2 AR per transaction** | 1 tx commit nhiều aggregate | Code review repo.save() đa AR |
| **Aggregate expose internal** | `sub.attempts` returns mutable list | Mutation từ ngoài không qua method |
| **Public mutable field** | `sub.status = "X"` không có method | grep direct field assignment |
| **Eventual misused** | Tách aggregate khi business require strong consistency | Bug report "thấy state lệch" |
| **Aggregate as DTO** | Aggregate dùng trong API response → expose internal | Serialize aggregate ra JSON đầy đủ |
| **Missing factory** | `Submission(...)` gọi trực tiếp với 12 arg → invariant không enforce ban đầu | grep direct constructor |
| **Event leak from service** | Event publish ở service layer, không phải aggregate | Event không kèm aggregate state change |
| **Repository returns internal** | `repo.get_attempts()` returns Attempt entities | API surface của repo |
| **Aggregate root with no events** | Method change state nhưng không emit event | Audit trail không có |

### Checklist trước khi merge PR (Aggregate review)

- [ ] Class có rõ AR? Internal entity và VO listed?
- [ ] Tất cả mutation qua method có pre-condition check?
- [ ] Internal field tất cả là `_private`?
- [ ] Cross-aggregate reference dùng ID, không object?
- [ ] 1 transaction = 1 aggregate? Multi-aggregate via event?
- [ ] Domain event emit từ AR method, không service?
- [ ] Repository return AR thôi, không expose internal entity?
- [ ] Test: aggregate có thể test mà không cần DB?
- [ ] Factory `create()` cho aggregate với complex init?
- [ ] Domain service stateless, đặt ở domain layer (không infra)?

### So sánh với pattern lân cận

| Pattern | Khác Aggregate | Khi nào nào dùng cùng |
|---------|----------------|------------------------|
| **Bounded Context (34)** | Strategic boundary | Aggregate sống trong 1 BC |
| **Hexagonal (30)** | Cấu trúc input/output | Aggregate ở domain core của Hex |
| **CQRS (32)** | Read/Write tách | Write side dùng aggregate; read side projection |
| **Event Sourcing (32)** | Lưu event làm SoT | Aggregate rebuilt by replay events |
| **Repository pattern** | Persistence abstraction | 1 repo cho 1 AR |
| **Specification (37 — sau)** | Reusable predicate | Filter aggregate query |
| **Observer (19)** | In-process pub-sub | Domain event là Observer scaled lên architecture |

### Aggregate size heuristic

| Aggregate có | Có thể OK | Cảnh báo | Smell (cần tách) |
|--------------|-----------|----------|-------------------|
| Entity nội bộ | 0-3 | 4-6 | > 6 |
| Object instance loaded | < 50 | 50-500 | > 500 |
| Field ở AR | < 10 | 10-15 | > 15 |
| Method ở AR | < 8 | 8-12 | > 12 |
| Có collection unbounded | Không | Có (với pagination) | Có (load all) |

> Rule of thumb: **nếu aggregate phải load nhiều hơn ~50 object** → suy nghĩ tách.

---

## BÀI TẬP — 4 MỨC

### Mức 1 — Cơ bản (45 phút)

Lấy code `Submission` từ Lesson 32 (CQRS+ES). Identify:
- AR là gì?
- Internal entity nào (hoặc chưa có)?
- VO nào?
- 5 invariant nào aggregate enforce?

Viết bảng. Đối chiếu với file `35_aggregate.py` đính kèm.

### Mức 2 — Trung bình (1.5 giờ)

(a) Thêm 1 invariant mới vào `Submission`: "không retry quá 3 lần". Implement:
- Trong AR method `retry()`.
- Trong domain service `RetryPolicy.can_retry()`.

So sánh: cách nào "đặt rule" đúng hơn? Vì sao?

(b) Trong code aggregate, viết 3 unit test:
- Happy path grade.
- Vi phạm: grade twice → raise.
- Vi phạm: finalize without grade → raise.

Verify chạy < 10 ms tổng cộng.

### Mức 3 — Khó (architect, 3 giờ)

(a) Refactor `User` (hiện nay 1 class) thành 4 aggregate riêng:
- `UserIdentityAggregate` (auth-related).
- `UserProfileAggregate` (display info).
- `UserAttemptQuotaAggregate` (quiz attempts).
- `UserSubscriptionAggregate` (billing tier).

Mỗi aggregate own ~3 field, không cross-reference object. Vẽ Mermaid diagram quan hệ ID.

(b) Implement saga: khi `Submission.grade()` xảy ra → cập nhật `UserAttemptQuotaAggregate.consume_attempt()`. **Bắt buộc** 2 transaction riêng. Demo with timing.

(c) Thử *cố tình* viết God Aggregate (gộp 4 user aggregate trên + Submission + Quiz vào 1 class) → đo:
- Load time với 1000 submission.
- Lock contention với 10 concurrent grade.
- Test isolation.

So sánh số với version 4-aggregate riêng. Viết 200-word reflection.

### Mức 4 — Mở rộng neuro (2 giờ tự do)

Đọc 1 chương về *cellular homeostasis* (Alberts *Molecular Biology of the Cell* chương 11). Trả lời:

1. **Resting membrane potential −70 mV được duy trì bởi 3 mechanism**: Na/K pump, K leak channels, Na/K diffusion balance. Map sang aggregate: nếu aggregate có 3 invariant cùng phải enforce, nên — (a) 1 method check cả 3, (b) 3 method riêng, (c) cấu trúc state machine với precondition? Liên hệ Tell-Don't-Ask.

2. **Calcium signaling**: Ca²⁺ intracellular cực thấp (100 nM) so với extracellular (1.8 mM) = chênh lệch *10⁴*. Action potential cho phép Ca²⁺ tràn vào trong vài microsec → trigger neurotransmitter release → Ca²⁺ pump 5 sec đuổi ra. Tại sao Ca²⁺ ratio cao như vậy *quan trọng cho signaling*? Tương đương trong code: domain event nên carry *delta* hay *new state*? Trade-off?

3. **Apoptosis vs necrosis**: tế bào chết "có kiểm soát" (apoptosis, caspase pathway) vs "vỡ ra ngoại bào" (necrosis, gây viêm). Tương đương: aggregate fail "controlled" (rollback transaction, publish failure event) vs "uncontrolled" (uncaught exception, partial commit). Strategy nào nên default? Vì sao?

---

## ĐỒ HOẠ TỔNG KẾT

```
        AGGREGATE — consistency boundary
   ═══════════════════════════════════════════════════════════
                  ┌────────────────────────────────────────┐
                  │   AGGREGATE ROOT (public API)          │
                  │   submit() grade() retry() finalize()  │
                  │   ───────────────────────────────────  │
                  │   _status _attempts _score (private)   │
                  │                                        │
                  │   ┌──────────────────────────────┐     │
                  │   │  INTERNAL ENTITY: Attempt    │     │
                  │   │   _id, _answers, _score      │     │
                  │   └──────────────────────────────┘     │
                  │   ┌──────────────────────────────┐     │
                  │   │  VALUE OBJECT: Score, Answer │     │
                  │   │   immutable, frozen          │     │
                  │   └──────────────────────────────┘     │
                  │   ───────────────────────────────────  │
                  │   PENDING EVENTS (emitted on save):    │
                  │     SubmissionGraded, SubmissionRetried│
                  └────────────────────────────────────────┘
                          ▲                       │
                          │ tell                  │ emit
                          │                       ▼
                  ┌────────────────────┐  ┌────────────────┐
                  │ Application Service│  │ Domain Events  │ ──▶ Other aggregates
                  │ (orchestrate)      │  └────────────────┘     (by ID, eventual)
                  └────────────────────┘
                              │
                              ▼
                  ┌────────────────────┐
                  │ Repository (1 per  │   AR-per-transaction
                  │  aggregate root)   │
                  └────────────────────┘

   Cross-aggregate: chỉ qua ID + domain event (eventual consistency).
   Trong tế bào: cytoplasm isolated; cell-cell qua hormone/neurotransmitter.
```

> **Tóm lại**: Aggregate là *tế bào* của domain code. Boundary rõ, invariant chặt, public API qua "root", cross-cell qua event. Vi phạm = data corruption. Tuân thủ = test pure, scale dễ, ý nghĩa business rõ rệt cho cả dev và business expert.

---

## TIẾP THEO

- **Lesson 36 — Entity vs Value Object vs Domain Event**: khi nào chọn cái nào; identity, immutability, lifecycle.
- **Lesson 37 — Repository + Factory + Specification**: 3 supporting pattern cho aggregate.
- **Lesson 38 — Event Storming workshop**: workshop thực tế discover bounded context + aggregate.
- **Lesson 39 — Distributed DDD**: cross-context consistency, Saga inside vs across.
- **Lesson 40 — Ubiquitous Language case study**.
