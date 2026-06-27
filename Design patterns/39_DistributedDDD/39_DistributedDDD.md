# Lesson 39 — Distributed DDD: Cross-Context Consistency + Saga
## HPA Axis Hormonal Cascade — 3-step saga sinh học (hypothalamus → pituitary → adrenal) với compensation qua negative feedback. Spinal reflex (choreography) vs cortical motor planning (orchestration).

---

## TÓM TẮT MỘT DÒNG

Khi domain logic vượt ra ngoài 1 aggregate (Lesson 35) hoặc 1 bounded context (Lesson 34), bạn cần **saga** — chuỗi local transactions với compensation khi bước fail. **2 style**: *choreography* (decentralized, event chain, đơn giản nhưng khó trace) vs *orchestration* (centralized process manager, dễ trace nhưng SPOF risk). **Consistency**: cùng aggregate = strong, cross aggregate same BC = eventual within service, cross BC = eventual across services. **Idempotency** ở boundary là bắt buộc. **HPA axis sinh học** dạy đúng pattern: cascade dài, compensation qua feedback, không bao giờ strong consistency tức thời nhưng *robust* qua redundancy.

> Hypothalamus phát CRH (corticotropin-releasing hormone) → vào máu → pituitary nhận, phát ACTH (adrenocorticotropic hormone) → vào máu → adrenal cortex nhận, sản xuất cortisol → đi khắp cơ thể *và* phản hồi ngược về hypothalamus + pituitary để giảm CRH/ACTH (negative feedback = compensation). Đây là **distributed transaction sinh học**: 3 organ riêng biệt, không có atomic commit, mỗi bước tốn 5-20 phút, eventually consistent, compensation tự động qua feedback loop. Stress đến quá nhanh → adrenal nhận signal trực tiếp từ sympathetic nervous system (saga alternative path). Nếu cortisol stuck high → glucocorticoid receptor desensitization (compensation). 500 triệu năm tiến hoá đã chọn distributed > monolith.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Trong các lesson 34-38 bạn đã có:
- 4-6 bounded context (Lesson 34).
- Aggregates với invariants (Lesson 35).
- Repository + Factory + Spec (Lesson 37).
- Domain events (Lesson 31, 36).

Câu hỏi cuối: *khi 1 business action cần đụng nhiều aggregate / nhiều BC, làm sao đảm bảo "tất cả ok hoặc tất cả rollback"?*

Vd: Student submit quiz đòi hỏi:
1. **Auth BC** verify user identity.
2. **Subscription BC** check user có quota.
3. **Submission BC** tạo Submission aggregate + grade.
4. **Leaderboard BC** update Ranking.
5. **Notification BC** send Receipt.
6. **Gamification BC** check + award Badge.

6 bounded context. 6 aggregate (mỗi BC có own aggregate). 1 click user → 6 operation cross-service.

Nếu strong consistency (2PC distributed transaction):
- Lock 6 aggregate cùng lúc.
- Contention cao.
- 1 service slow → toàn bộ slow.
- Network partition → toàn bộ fail.

Nếu eventual consistency:
- 6 step local transactions chuỗi qua event.
- Mỗi step success → publish event.
- Mỗi step failure → compensate previous.
- Cross-BC = events qua message broker.

Đây là *saga*. Câu hỏi tiếp theo: chuỗi đó *làm thế nào*?

### 1.2. Định nghĩa Saga

**Saga** (Garcia-Molina & Salem 1987, *"Sagas"*):

> *"A long lived transaction (LLT) that can be written as a sequence of transactions T1...Tn whose effect cannot be reversed atomically, but where each Ti has a compensating transaction Ci that undoes (semantically) what Ti did."*

5 đặc điểm:
1. **Sequence of local transactions** — mỗi Ti là 1 ACID transaction trong 1 aggregate / 1 service.
2. **Compensating transactions Ci** — semantic rollback (không phải DB rollback).
3. **No global lock** — mỗi step commit local trước khi đi tiếp.
4. **Eventual consistency** — saga complete có thể mất giây, phút, hoặc lâu hơn.
5. **Failure handling** — fail giữa chừng → run Ci backward.

### 1.3. 3 levels saga

**Level 1 — Within Aggregate (in-process method calls)**:
- 1 transaction, all-or-nothing.
- Strong consistency.
- *Đây không phải saga* — chỉ là sequence of method calls.
- Vd: `Submission.submit_answers() → Submission.grade() → Submission.finalize()` cùng commit.

**Level 2 — Cross-Aggregate Same BC (eventual within service)**:
- 2+ aggregate trong cùng service.
- AR-per-transaction (Lesson 35).
- Saga local — handlers trong cùng process.
- Eventual consistency *trong service* (millisecond delay).
- Vd: `SubmissionGraded` → handler updates `UserAttemptQuota`.

**Level 3 — Cross-BC (eventual across services)**:
- 2+ bounded context, distributed deployment.
- Messages qua broker (Kafka, RabbitMQ).
- Eventual consistency *between services* (second-minute delay).
- Idempotency mandatory (Lesson 31).
- Vd: `SubscriptionActivated` (Subscription BC) → handler in Quiz Authoring BC grants premium access.

### 1.4. 2 saga styles

**(a) Choreography (decentralized)**:
- Mỗi service subscribe events nó care.
- Khi nhận event → local action → publish next event.
- Không có "conductor".
- Lợi: simple, loose coupling, scale dễ.
- Hại: workflow không tập trung visualization; cycle dễ vô tình; compensation phức tạp.

```
SubmissionGraded ─┬─▶ LeaderboardHandler  ─publish─▶ LeaderboardUpdated
                  ├─▶ NotificationHandler ─publish─▶ NotificationSent
                  └─▶ BadgeHandler        ─publish─▶ BadgeAwarded
```

**(b) Orchestration (centralized — Process Manager)**:
- 1 saga orchestrator class.
- State machine với explicit transitions.
- Issues commands to BCs; listens to their events.
- Tracks saga state (started/in_progress/completed/failed).
- Lợi: workflow visualization rõ; compensation explicit; easier monitoring.
- Hại: orchestrator có thể trở thành god class; SPOF nếu single instance.

```
QuizSubmissionSaga state machine:
    STARTED
    → AUTH_VERIFIED
    → QUOTA_CHECKED
    → SUBMISSION_CREATED
    → SCORED
    → LEADERBOARD_UPDATED
    → NOTIFIED
    → COMPLETED

On failure at step K: trigger compensation for steps 1..K-1 in reverse.
```

> Quy tắc: **choreography cho ≤ 3 step**, **orchestration cho ≥ 4 step hoặc complex compensation**. Vernon recommend bắt đầu choreography, refactor sang orchestration khi step tăng.

### 1.5. Compensation patterns

**Compensation** = semantic undo, không phải DB rollback. Mỗi command Ti có compensating command Ci.

| Action Ti | Compensation Ci |
|-----------|------------------|
| `ReserveSeat` | `ReleaseSeatReservation` |
| `ChargePayment` | `RefundPayment` |
| `CreateSubmission` | `DeleteSubmission` (or void) |
| `AwardBadge` | `RevokeBadge` |
| `UpdateLeaderboard` | `ReverseLeaderboard` |
| `SendNotification` | (impossible to un-send — log as void) |

3 properties bắt buộc của compensation:
1. **Idempotent**: chạy 2 lần = chạy 1 lần (network retry safe).
2. **Commutative-like với failure**: compensate có thể run trong any order khi multiple steps fail.
3. **Recorded**: compensation also published as event for audit.

> Một số action **không reversible** — như "send email". Phải design saga để *không có* email send cho đến saga "definitely will succeed" (= sau khi business-critical steps done).

### 1.6. Idempotency at cross-BC boundary

Cross-BC communication qua message broker (Kafka, RabbitMQ) → at-least-once delivery default → cùng event có thể delivered 2+ lần. Consumer phải:

```
def handle(event: SubscriptionActivated):
    if event.event_id in already_processed:
        return  # idempotent — skip
    do_local_action(event)
    already_processed.add(event.event_id)
```

Đã chạm ở Lesson 31. Lesson 39 nhấn: *consumer idempotency là responsibility của downstream BC*, không phải upstream BC. Upstream BC chỉ guarantee "I emit event with unique event_id". Downstream BC guarantee "I dedup by event_id".

### 1.7. Neuroscience — HPA axis + Spinal reflex vs Cortical motor

**(a) HPA axis = 3-step cross-context saga**:

```
Hypothalamus (BC 1)          ← stress signal arrives
   │ command: ReleaseCRH
   ▼ (event: CRHSecreted, ~minutes)
Pituitary anterior (BC 2)
   │ command: ReleaseACTH
   ▼ (event: ACTHSecreted, ~minutes)
Adrenal cortex (BC 3)
   │ command: ReleaseCortisol
   ▼ (event: CortisolReleased, ~minutes)
Body wide (BCs N)             ← raises blood sugar, suppresses immune

Negative feedback loop (compensation):
   Cortisol high → suppresses CRH (Hypothalamus)
                 → suppresses ACTH (Pituitary)
                 → desensitize glucocorticoid receptors
```

- 3 organ ≠ 3 cell type. Mỗi organ là 1 *bounded context* anatomical.
- Messages qua *bloodstream* (= message broker; broadcast với half-life).
- Eventual consistency window: 5-20 phút trước cortisol đạt peak.
- Negative feedback = compensation pattern.
- *Idempotency*: receptor desensitization → repeated signal có effect giảm dần (= consumer dedup at biological level).

Khi stress critical, body bypass HPA via sympathetic nervous system → adrenaline trực tiếp (= express path, shorter saga). Đó là *alternative path* trong distributed system: critical action có thể bypass orchestrator, đi straight to executor.

**(b) Spinal reflex = Choreography**:
- Nociceptor → sensory neuron → spinal interneuron → motor neuron → muscle.
- Không có "conductor".
- Mỗi neuron react với neurotransmitter đến.
- < 50 ms total.
- *Choreography* vì simple linear chain, không cần state machine.

**(c) Cortical motor planning = Orchestration**:
- Prefrontal cortex *plans* movement.
- Sequence commands tới: premotor cortex → primary motor cortex → spinal cord → muscle.
- Cerebellum feedback (= compensation if execution drift).
- Basal ganglia gating (= conditional step).
- 200-500 ms total.
- *Orchestration* vì complex multi-step với feedback.

→ Brain dùng **choreography cho simple reflex** (3 step, ≤ 50 ms), **orchestration cho complex action** (5+ step, feedback). DDD code đi theo nguyên tắc này.

### 1.8. So sánh với patterns đã học

| Pattern | Lesson | Quan hệ với Saga |
|---------|--------|------------------|
| Aggregate (35) | 35 | Saga = chuỗi aggregate transactions |
| Domain Event (31, 36) | 31, 36 | Saga *publish/consume* events |
| Bounded Context (34) | 34 | Cross-BC saga = level 3 |
| Repository (37) | 37 | Each saga step uses repo |
| Specification (37) | 37 | Saga can use spec to decide next step |
| EDA (31) | 31 | Saga via event chain = EDA pattern |
| CQRS+ES (32) | 32 | Saga state = sequence of saga events |

---

## MỨC 2 — CẤU TRÚC

### 2.1. Choreography pattern

```
EventBus is global. Each BC subscribes to events from other BCs.

BC-A processes command → publishes EventA1
   → BC-B subscribed → processes EventA1 → publishes EventA2
      → BC-C subscribed → processes EventA2 → publishes EventA3

Compensation:
   If BC-B fails → publish FailureEvent
      → BC-A subscribed to FailureEvent → run compensation
```

Properties:
- Mỗi handler là *idempotent*.
- *Loose coupling*: BC-A không biết về BC-C tồn tại.
- *Anti-pattern alert*: cycle (A → B → C → A) — must detect at design time.

### 2.2. Orchestration pattern (Process Manager)

```
QuizSubmissionSaga (Process Manager):
   state: STARTED | AUTH_VERIFIED | ... | COMPLETED | FAILED
   data:  { user_id, quiz_id, attempts, completed_steps: [...] }

   def start(user_id, quiz_id):
       state = STARTED
       command_bus.send(VerifyAuth(user_id))

   def on_AuthVerified():
       state = AUTH_VERIFIED
       command_bus.send(CheckQuota(user_id))

   def on_QuotaChecked():
       state = QUOTA_CHECKED
       command_bus.send(CreateSubmission(...))

   def on_SubmissionCreated():
       state = SUBMISSION_CREATED
       command_bus.send(GradeSubmission(...))

   ... etc

   def on_any_failure(step):
       state = FAILED
       for completed in reversed(completed_steps):
           command_bus.send(compensate_command_for(completed))
```

Saga state cần *persistence* (như aggregate) — restart-safe.

### 2.3. Saga ↔ aggregate boundary

**Quy tắc**: saga state là *separate aggregate*, không phải đi vào aggregate khác.

```
WRONG:
   class Submission:
       saga_state: SagaState   ← cross-concern leak

RIGHT:
   class Submission:
       _state, _attempts, _score   ← only submission concern

   class QuizSubmissionSaga:        ← separate aggregate
       saga_id, state, started_at, completed_steps, failed_step
```

Saga aggregate có riêng repository, events, lifecycle.

### 2.4. Bốn invariants

1. **Saga step = local transaction trong 1 aggregate/BC**.
2. **Mỗi step có compensation defined** (nếu không revertible, document why).
3. **Cross-BC events có event_id**; consumer dedup.
4. **Saga state là aggregate riêng**, persist, restart-safe.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
# === Choreography example ===

class SubscriptionBC:
    def activate(user_id):
        sub = Subscription.create(user_id)
        repo.save(sub)
        bus.publish(SubscriptionActivated(user_id, ...))

class QuizAuthoringBC:
    @subscribe(SubscriptionActivated)
    def on_subscription_activated(event):
        access_repo.grant_premium(event.user_id)
        bus.publish(PremiumAccessGranted(event.user_id))

class NotificationBC:
    @subscribe(SubscriptionActivated)
    def on_subscription_activated(event):
        send_welcome_email(event.user_id)
        bus.publish(WelcomeEmailSent(event.user_id))

# === Orchestration example ===

class QuizSubmissionSaga:
    states: STARTED → AUTH_OK → QUOTA_OK → SUBMITTED → SCORED → ...

    def __init__(self, saga_id, user_id, quiz_id):
        self.id = saga_id
        self.state = "STARTED"
        self.completed_steps = []

    def start(self, command_bus):
        command_bus.send(VerifyAuth(self.user_id))

    @on_event(AuthVerified)
    def proceed_to_quota(self, event):
        self.state = "AUTH_OK"
        self.completed_steps.append("auth")
        command_bus.send(CheckQuota(self.user_id))

    @on_event(QuotaChecked)
    def proceed_to_submit(self, event):
        ...

    @on_event(AnyFailure)
    def compensate(self, event):
        self.state = "FAILED"
        for step in reversed(self.completed_steps):
            command_bus.send(compensation_for(step))

# === Idempotency at boundary ===

class LeaderboardBC:
    _processed_event_ids: Set[str]

    @subscribe(SubmissionGraded)
    def on_graded(event):
        if event.event_id in self._processed_event_ids:
            return  # skip duplicate
        ranking.update(...)
        self._processed_event_ids.add(event.event_id)
        bus.publish(LeaderboardUpdated(...))
```

### 3.2. Bảng 2x2 nhớ là đủ

|  | **Same BC** | **Cross BC** |
|---|---|---|
| **Simple (≤3 step)** | Method calls trong aggregate | Choreography via events |
| **Complex (≥4 step)** | Saga local (same process orchestrator) | Process Manager + saga aggregate persistence |

---

## NĂM CHIỀU SO SÁNH (trong não vs trong code)

| Chiều | HPA axis / Spinal reflex / Cortical motor | Distributed Saga |
|-------|-------------------------------------------|------------------|
| **Cấu tạo** | Hypothalamus + pituitary + adrenal (HPA); nociceptor+interneuron+motor (reflex); PFC+premotor+M1+cerebellum (cortical) | Multiple BCs với aggregate + event bus + saga state |
| **Vị trí** | 3 organ separate; spinal cord at vertebrae; cortex+subcortex+spine | 3+ services separate; saga state in 1 BC (choreography distributed; orchestration centralized) |
| **Chức năng** | Stress response cascade; pain withdrawal; voluntary movement | Multi-step business transaction with compensation |
| **Kết nối** | Hormones in blood (HPA); axons (reflex); axons + feedback loops (cortical) | Events on message broker; idempotent dedup at boundary |
| **Ý nghĩa** | Distributed coordination tiến hoá chọn 500M năm; robustness > strong consistency | Code distributed system mirror: scale > strong consistency; eventual + compensation > 2PC |

---

## BA VÍ DỤ

### Ví dụ 1 — Vận hành thường (happy path)

Student submits quiz, saga 6-step:

```
1. AuthBC verifies user → emit AuthVerified
2. SubscriptionBC checks quota → emit QuotaConfirmed
3. SubmissionBC creates Submission + grades → emit SubmissionGraded
4. LeaderboardBC updates ranking → emit LeaderboardUpdated
5. NotificationBC sends receipt → emit ReceiptSent
6. GamificationBC checks badge → emit BadgeAwarded (or skip)

Total: 6 events, 6 local transactions, eventual consistency window ~50-200ms.
```

### Ví dụ 2 — Hỏng / vi phạm

**Vi phạm A — 2PC distributed transaction**:
```python
# BAD — XA transaction
with distributed_tx([auth_db, sub_db, submission_db, leaderboard_db]):
    auth_db.verify(...)
    sub_db.consume_quota(...)
    submission_db.insert(...)
    leaderboard_db.update(...)
```
→ Lock 4 service. 1 service slow → all slow. Network partition → blocked.
→ Đúng: 4 local tx + saga + compensation.

**Vi phạm B — Cycle trong choreography**:
```
BC-A publishes EventX → BC-B handles, publishes EventY
   → BC-C handles, publishes EventZ
      → BC-A handles EventZ, publishes EventX  ← CYCLE
```
→ Hệ loop vô hạn.
→ Đúng: detect at design (event flow DAG); use correlation ID + max depth.

**Vi phạm C — Forgot compensation**:
```python
# BAD — happy path only
saga.start()
saga.step1_charge_payment()
saga.step2_reserve_inventory()  # FAILS
# Payment charged but no inventory reserved → customer angry
```
→ Đúng: step2 fail → trigger step1 compensation (refund).

**Vi phạm D — No idempotency at consumer**:
```python
# BAD
class LeaderboardBC:
    def on_graded(event):
        ranking[event.user_id] += event.score  # ← duplicate event → double count
```
→ Đúng: dedupe by event_id.

**Vi phạm E — Saga state inside business aggregate**:
```python
# BAD
class Submission:
    saga_state: str  # ← saga concern leak into Submission
```
→ Đúng: `QuizSubmissionSaga` is separate aggregate with own repo.

### Ví dụ 3 — Ứng dụng Ellumm

File `39_distributed_ddd.py` đi kèm với:
- 4 BCs: Subscription, Submission, Leaderboard, Notification.
- Choreography implementation: handlers subscribe events.
- Orchestration implementation: `QuizSubmissionSaga` process manager.
- Compensation chain when middle step fails.
- Idempotency wrapper on consumers.
- Eventual consistency window measurement.
- 9 demo + anti-pattern showcase.

---

## MỨC ARCHITECT — TRADE-OFFS & ANTI-PATTERNS

### Khi nào DÙNG saga

- Operation spans ≥ 2 aggregates (cross-aggregate, regardless of BC).
- Operation spans ≥ 2 BCs (distributed).
- Need audit trail step-by-step.
- Eventual consistency acceptable.
- Some steps are external (HTTP API call, payment gateway).

### Khi nào KHÔNG

- Single aggregate ACID transaction sufficient.
- Strong consistency required by business (financial money transfer single account).
- All steps in same DB → single transaction is simpler.
- Step count < 2.

### Choreography vs Orchestration — chọn cái nào?

| Yếu tố | Choreography | Orchestration |
|--------|--------------|---------------|
| **Step count** | ≤ 3 step | ≥ 4 step |
| **Compensation complexity** | Simple, per-step | Multi-step rollback needed |
| **Visualization** | DAG drawing post-hoc | Explicit state machine |
| **Coupling** | Loose (BC self-sufficient) | Tight to orchestrator BC |
| **Failure mode** | Each handler retries locally | Orchestrator tracks + retries |
| **Add new step** | New subscriber, no central change | Update orchestrator state machine |
| **Debugging** | Distributed tracing required | Saga ID + state table |
| **SPOF** | None | Orchestrator (mitigate via replicas) |
| **Learning curve** | Easy | Moderate |

> Vernon: bắt đầu choreography. Refactor orchestration khi pain visible.

### Trade-offs

| Trục | Saga được | Saga mất |
|------|-----------|----------|
| Consistency | Distributed, scale | Eventual, brief inconsistency window |
| Failure isolation | 1 service fail không sập all | Compensation complexity |
| Throughput | Each step independent, parallel | Coordination overhead |
| Debug | Audit per step | Distributed tracing required |
| Onboarding | Easy per-service | Saga semantics need training |

### Anti-patterns thường thấy

| Anti-pattern | Mô tả | Phát hiện |
|--------------|-------|-----------|
| **Distributed monolith** | Tight coupling via synchronous chain | Service A waits for chain of B→C→D to return |
| **2PC across services** | XA distributed transaction | grep "XA" / "two_phase" |
| **No compensation** | Failure path missing | Code review checklist |
| **Compensation not idempotent** | Run 2x = different result | Test replay |
| **No correlation ID** | Cannot trace saga end-to-end | Logs missing trace_id |
| **Saga inside aggregate** | Saga state on business entity | Aggregate has `saga_*` fields |
| **Forget cycle detection** | Event chain loops | Run BFS on event flow graph |
| **Strong consistency expected** | UI shows stale state during eventual | User complaint patterns |
| **Mixed choreography+orchestration** | Confusion which is authoritative | Two flows for same business operation |
| **No idempotency at consumer** | Duplicate events corrupt state | Test event replay |
| **God orchestrator** | 1 orchestrator for 20 sagas | Single file > 1000 LOC |
| **Orchestrator with business logic** | Orchestrator computes scores | Should delegate to BC commands |

### Checklist trước khi merge PR

- [ ] Saga có boundary rõ (cross-aggregate? cross-BC?).
- [ ] Mỗi step có compensation định nghĩa?
- [ ] Compensation idempotent?
- [ ] Event có event_id (cross-BC)?
- [ ] Consumer dedup tại boundary?
- [ ] Saga state là aggregate riêng (orchestration case)?
- [ ] Cycle detection on event chain?
- [ ] Correlation ID propagate qua all steps?
- [ ] Timeout cho stuck saga (retry strategy)?
- [ ] Test failure paths (mỗi step fail)?

### So sánh với patterns đã học

| Pattern | Distributed DDD perspective |
|---------|------------------------------|
| 2PC / XA | Anti-pattern in microservices; saga là alternative |
| TCC (Try-Confirm-Cancel) | Variation of saga; tries first then commits or cancels |
| Outbox (31) | Required to atomically save aggregate + publish saga event |
| CQRS+ES (32) | Saga state ITSELF can be event-sourced |
| Circuit Breaker | Wrap saga step calls to external service |
| Bulkhead | Isolate saga workers per BC |

---

## BÀI TẬP — 4 MỨC

### Mức 1 — Cơ bản (45 phút)

Lấy 1 business operation trong Ellumm cần ≥ 3 step (submit quiz, renew subscription, etc.). Vẽ:
- Saga step diagram (numbered).
- Compensation cho mỗi step.
- Decide choreography hay orchestration.

### Mức 2 — Trung bình (1.5 giờ)

Implement choreography saga 3-step trong code:
- Step 1: AuthBC verify
- Step 2: SubmissionBC create
- Step 3: LeaderboardBC update

Test:
- Happy path.
- Step 2 fail → step 1 compensation.
- Step 3 fail → step 1+2 compensation.

### Mức 3 — Khó (architect, 3 giờ)

(a) Convert choreography (Mức 2) sang orchestration:
- `QuizSubmissionSaga` process manager với state machine.
- Saga aggregate persistence.
- Explicit compensation chain.

So sánh: SLOC, debug ease, performance.

(b) Add idempotency wrapper at each consumer boundary. Replay each saga event 3x → verify no double effect.

(c) Add timeout + retry: nếu LeaderboardBC không respond trong 5s → retry 3x → if still fail → compensation.

### Mức 4 — Mở rộng neuro (2 giờ tự do)

Đọc paper về HPA axis cascade (Sapolsky 2002 *"Endocrinology of the stress-response"*) hoặc spinal reflex (Sherrington 1906 *"Integrative Action"*). Trả lời:

1. **HPA negative feedback compensation**: cortisol high → suppress CRH/ACTH. Trong code: compensation event nên có ảnh hưởng *bao xa upstream*? (Compensate immediately previous step, hay compensate from beginning?)

2. **Sympathetic bypass HPA**: stress critical → adrenaline trực tiếp từ adrenal medulla (skip HPA). Trong code: có nên có "express path" bypass saga cho critical operation? Khi nào?

3. **Glucocorticoid receptor desensitization**: cortisol high lâu → receptor giảm sensitivity = consumer idempotency sinh học. Tại đến mức nào idempotency thành "rate limiting"? Liên hệ Lesson 31 backpressure.

---

## ĐỒ HOẠ TỔNG KẾT

```
        DISTRIBUTED DDD — SAGA + 2 STYLES
   ═══════════════════════════════════════════════════════════
   CHOREOGRAPHY (decentralized)            ORCHESTRATION (Process Manager)
   ──────────────────────────              ──────────────────────────────────
                                                      ┌─────────────┐
                                                      │ SAGA STATE  │
                                                      │ STARTED →   │
                                                      │ AUTH_OK →   │
                                                      │ QUOTA_OK → ...│
   BC-A ─event─▶ BC-B ─event─▶ BC-C                  └──┬──┬──┬──┬──┘
                                                         │  │  │  │
                                                         ▼  ▼  ▼  ▼
   Each BC subscribes events                          BC-A BC-B BC-C BC-D
   from upstream BC                                   (each called by orchestrator)

   Compensation:                                       Compensation:
   BC-C fails → publish FailedEvent                    Orchestrator runs Ci
   → BC-B subscribed → compensate                      in reversed order

   Brain analog:                                       Brain analog:
   Spinal reflex (50 ms, 3 step)                      Cortical motor plan (200-500ms)
                                                       HPA axis cascade
```

> **Tóm lại**: Khi domain vượt 1 aggregate / 1 BC, dùng saga. Choreography cho simple, orchestration cho complex. Compensation idempotent. Idempotency consumer mandatory. Brain analog: HPA axis = orchestration cascade với feedback compensation; spinal reflex = choreography 3-step. Tiến hoá đã chọn distributed > monolith — eventual consistency là natural state của hệ phức tạp.

---

## TIẾP THEO

- **Lesson 40** — Ubiquitous Language case study: rename + glossary management + impact on cross-BC.
