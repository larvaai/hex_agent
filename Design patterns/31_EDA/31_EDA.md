# Lesson 31 — Event-Driven Architecture (EDA)
## Dopamine RPE Broadcast — VTA bắn 1 spike, striatum + PFC + motor cortex *cùng nhận* và xử lý độc lập. Không ai chờ ai.

---

## TÓM TẮT MỘT DÒNG

**Event-Driven Architecture** = bố cục hệ thống quanh **dòng chảy event**. Producer phát event ("đã xảy ra chuyện X") **không quan tâm ai nghe**. Consumer subscribe và xử lý **bất đồng bộ, độc lập**. Coupling từ *temporal + structural* (Hex/Clean) chuyển sang *event schema only*.

> Wolfram Schultz 1997 — *neuron dopamine ở VTA bắn phasic spike khi reward bất ngờ*. Không có "synapse hard-wire tới cá nhân nào" — dopamine khuếch tán **broadcast** đồng thời tới striatum (học hành vi), PFC (cập nhật kỳ vọng), amygdala (gắn nhãn cảm xúc). Mỗi vùng *interpret cùng 1 spike khác nhau* và xử lý song song. VTA không "biết" ai đang nghe và không chờ. Đó là EDA sinh học. Tonic firing = bus rate; phasic burst = high-priority event; GABA inhibition = backpressure; polysynaptic chain = saga; LTD khi quá tải = dead-letter drop.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Sau Hexagonal (Lesson 30), bạn đã có core thuần + ports + adapters. Nhưng *gọi driven port là synchronous*: app service `notifier.send_receipt(...)` chặn cho đến khi SMTP trả về. Bốn vấn đề khi hệ lớn lên:

1. **Producer latency = sum(consumer latency)**: submit quiz cần `score → save → email → push → leaderboard → analytics`. Mỗi consumer +50 ms → user chờ 250 ms cho 1 click. Tệ.
2. **Producer phải biết tất cả consumer**: thêm 1 feature "trao huy hiệu khi top 10" → sửa `QuizApplicationService` thêm `badge_service.check(...)`. Vi phạm OCP (Lesson 25).
3. **1 consumer fail làm cả request fail**: SMTP timeout → user nhận HTTP 500 dù quiz đã được chấm và lưu. Coupling thất bại.
4. **Không thể scale consumer độc lập**: muốn analytics chạy 10 worker và email chạy 1 worker cùng 1 producer là bất khả thi nếu gắn cứng qua method call.

EDA trả lời tất cả 4 bằng *cùng 1 cơ chế*: **đảo ngược direction of control bằng pub-sub**.

```
TRƯỚC (Hex sync):
  AppService.submit() ─call─▶ Repo.save()
                       ─call─▶ Email.send()
                       ─call─▶ Push.send()
                       ─call─▶ Leaderboard.update()
   (AppService biết và chờ tất cả)

SAU (EDA):
  AppService.submit() ─publish─▶ QuizSubmitted event ─┐
                                                      ├─▶ EmailHandler   (subscribe)
                                                      ├─▶ PushHandler    (subscribe)
                                                      ├─▶ LeaderboardHandler (subscribe)
                                                      └─▶ AnalyticsHandler   (subscribe)
   (AppService chỉ phát; consumer tự xử lý độc lập, có thể parallel)
```

> **Lưu ý quan trọng**: EDA *không thay* Hex/Clean — nó đứng **trên** Hex. Lõi domain vẫn pure, nhưng thay vì gọi driven port "send_email", lõi *publish event* "QuizSubmitted". Bus + handlers là **một adapter mới** kiểu pub-sub.

### 1.2. Định nghĩa và 3 thành phần

**Event** = *bản tin bất biến* mô tả "đã xảy ra X tại thời điểm T". Tên ở thì *quá khứ*: `QuizSubmitted`, `OrderPlaced`, `PaymentRefunded`. Không phải `SubmitQuiz` (đó là **command**).

| | Event | Command |
|---|---|---|
| **Tên** | Past tense (`OrderPlaced`) | Imperative (`PlaceOrder`) |
| **Producer** | "Tôi vừa làm xong" | "Hãy làm" |
| **Consumer** | 0..N (fan-out) | Đúng 1 (request-response) |
| **Hướng** | One-way fire-and-forget | Có thể trả về kết quả |
| **Failure** | Producer success không phụ thuộc consumer | Producer biết được fail |
| **Ngữ nghĩa** | Notification về fact đã xảy ra | Yêu cầu thay đổi state |

**Event Bus / Broker** = hạ tầng vận chuyển event. *In-process* (callback list, asyncio queue) hoặc *out-of-process* (Kafka, RabbitMQ, Redis Streams, NATS, AWS SNS/SQS, Google Pub/Sub).

**Producer / Consumer (Subscriber / Handler)**:

```
Producer ──▶ publish(event) ──▶  [BUS]  ──▶ subscribers[Type(event)]
                                              ├─ Handler A
                                              ├─ Handler B
                                              └─ Handler C
```

Producer biết *event type*, không biết *handler nào*. Consumer biết *event type*, không biết *producer nào*. **Coupling chỉ còn là schema event**.

### 1.3. Neuroscience — Dopamine RPE broadcast

Bốn fact sinh học để bạn cảm rõ EDA *là cách não vận hành*:

**(a) Schultz 1997 — *Reward Prediction Error* coding**
- Phasic burst của ~25,000 neuron dopamine ở VTA + SNc bắn ~30-100 ms khi reward (ngon ngọt) hoặc cue dự báo reward.
- Spike *broadcast*: axon dopamine phân nhánh tới ventral striatum, dorsal striatum, PFC, amygdala, hippocampus *cùng lúc*.
- Mỗi vùng *interpret khác nhau*: striatum cập nhật habit weight, PFC cập nhật kỳ vọng, amygdala gắn cảm xúc.
- → Đây là **fan-out pub-sub đa consumer** trong não. VTA = producer; mỗi vùng = subscriber với handler riêng.

**(b) Action potential = sự kiện rời rạc, không có địa chỉ**
- Một AP propagate dọc axon, đến **mọi terminal** mà axon arborize. Không có "địa chỉ neuron đích" — terminal nào có synapse, terminal đó thả neurotransmitter.
- Producer (cell body) **không biết** post-synaptic neuron nào sẽ nghe. Đó là *fire-and-forget*. Nếu post-synaptic không có receptor (= subscriber), tín hiệu rơi.

**(c) GABA inhibition = backpressure**
- Khi producer phát quá nhanh, GABA-A receptor mở Cl⁻ ức chế post-synaptic, *làm chậm* xử lý → cứu mạch khỏi over-saturation.
- Tương đương: rate-limiting / queue capacity / pause subscription khi consumer lag.

**(d) Polysynaptic chain = Saga**
- Reflex withdrawal: nociceptor → spinal interneuron → motor neuron → cơ. Nếu cảm thấy đau lan, brainstem nhận tín hiệu → cortex. Mỗi bước là 1 synapse, mỗi synapse là 1 event.
- Đây là **saga choreography** sinh học: không có "central conductor", mỗi bước trigger bước sau. Đối lập với cortex *orchestration* khi PFC ra "kế hoạch" rõ.

**(e) Long-term depression khi quá tải = Dead Letter**
- Synapse nhận spike quá nhiều thời gian dài → giảm sensitivity (LTD). Tương đương: drop event hoặc move sang DLQ.

### 1.4. So sánh với pattern lân cận

| Pattern | Ngữ cảnh | EDA khác như thế nào |
|---------|----------|-----------------------|
| **Observer (GoF, Lesson 19)** | In-process notification | EDA là *Observer scaled lên kiến trúc*: thêm async, persistence, retry, DLQ, ordering, multi-process |
| **Mediator (GoF, Lesson 17)** | Object talk via central mediator | Mediator là synchronous + 1 mediator object. EDA decouple sâu hơn (bus generic, không biết object cụ thể) |
| **Chain of Responsibility (GoF)** | Handler chain xử lý 1 request | CoR có ordering chặt, mỗi handler có thể *stop chain*. EDA: tất cả handler nhận event, parallel |
| **Hex (Lesson 30)** | Sync ports & adapters | EDA = "thay driven port sync = publish event"; Hex bên trong còn nguyên |
| **CQRS + ES (Lesson 32)** | Tách read/write + lưu event làm source of truth | Lesson 32 *dùng* EDA nhưng thêm: aggregate, event store, projection. EDA thuần không yêu cầu lưu event làm SoT |

> **Quy tắc nhớ**: EDA là *style giao tiếp* (async pub-sub). Event Sourcing (32) là *style lưu trữ* (events as SoT). 2 cái độc lập — có thể có EDA mà không ES (đa số microservice), hoặc ES mà không EDA (single-process aggregate). Tốt nhất: cả hai.

---

## MỨC 2 — CẤU TRÚC

### 2.1. Vai diễn

```
┌────────────────────────────────────────────────────────────────┐
│ 1. PRODUCER                                                    │
│   - App service / Aggregate sau khi commit state               │
│   - Build event object + bus.publish(event)                    │
│   - Không await consumer; không biết consumer count            │
└──────────────────┬─────────────────────────────────────────────┘
                   │ publish(event)
                   ▼
┌────────────────────────────────────────────────────────────────┐
│ 2. EVENT BUS                                                   │
│   - subscribe(EventType, handler)                              │
│   - publish(event) → dispatch to all matching subscribers      │
│   - Sync (callback list) hoặc Async (queue + worker pool)      │
│   - Có thể wrap: Retry, Idempotency, DLQ, Logging              │
└──────────────────┬─────────────────────────────────────────────┘
                   │ dispatch
                   ▼
┌────────────────────────────────────────────────────────────────┐
│ 3. CONSUMERS (= subscribers / handlers)                        │
│   - Mỗi handler 1 trách nhiệm                                  │
│   - Có thể publish event mới (saga step) — chuỗi events        │
│   - Independent failure: A fail không ảnh hưởng B              │
│   - Phải idempotent (xử lý duplicate ổn)                       │
└────────────────────────────────────────────────────────────────┘
```

### 2.2. 4 chế độ delivery

| Chế độ | Mô tả | Khi nào |
|--------|-------|---------|
| **At-most-once** | Mỗi event ≤ 1 lần đến consumer. Có thể mất. | Metric không quan trọng (analytics fast path). |
| **At-least-once** | ≥ 1 lần. **Có thể duplicate**. Consumer phải idempotent. | Default cho hầu hết broker (Kafka, RabbitMQ). |
| **Exactly-once** | Đúng 1 lần. Đắt — cần transactional broker + transactional consumer. | Tài chính, billing. |
| **Ordered** | Cùng 1 partition giữ thứ tự. | Sequential aggregate (đặc biệt khi event cùng entity). |

> Quy tắc thực dụng: **default at-least-once + idempotent consumer**. Đừng cố exactly-once trừ khi quy định bắt buộc.

### 2.3. Idempotency — bắt buộc cho consumer

Một consumer **idempotent** = xử lý cùng event 2 lần ra cùng kết quả. Cách thường:

1. Mỗi event có `event_id` UUID duy nhất.
2. Consumer giữ `processed_event_ids: set` (hoặc table với UNIQUE constraint trên `event_id`).
3. Khi nhận event: nếu `event_id ∈ processed`, skip; ngược lại xử lý + thêm vào set.

```python
class IdempotentConsumer:
    def __init__(self, inner): self.inner = inner; self.processed = set()
    def handle(self, event):
        if event.event_id in self.processed: return         # dedupe
        self.inner.handle(event)
        self.processed.add(event.event_id)
```

### 2.4. Retry + Dead Letter Queue (DLQ)

Một handler có thể fail tạm thời (SMTP timeout) hoặc mãi mãi (bug). Strategy chuẩn:

```
attempt 1 ─fail─▶ wait 1s
attempt 2 ─fail─▶ wait 2s     (exponential backoff)
attempt 3 ─fail─▶ wait 4s
... max_retries reached ─▶ move to DLQ
```

DLQ = "thùng rác có nhãn" — event chứa cả original + lý do fail + stack trace. Operator review DLQ định kỳ (replay sau khi fix bug, hoặc discard).

### 2.5. Saga — multi-step business transaction

EDA đơn vận trên 1 service. **Saga** xử lý transaction qua nhiều service/aggregate khi không có distributed ACID transaction.

**Choreography (decentralized)**:
```
QuizSubmitted ──▶ ScoringHandler  ──publish──▶ ScoreCalculated
                                                     │
                                ┌────────────────────┼────────────────────┐
                                ▼                    ▼                    ▼
                       LeaderboardHandler   NotificationHandler    AnalyticsHandler
                                │                    │
                                ▼                    ▼
                      LeaderboardUpdated     NotificationSent
```

Mỗi handler "biết bước trước" qua event listen. Không có "conductor". Lợi: simple, decoupled. Hại: khó nhìn tổng thể luồng nghiệp vụ.

**Orchestration (centralized)**:
```
QuizSaga (orchestrator)
   ├─ step 1: scoring_service.score()
   ├─ step 2: leaderboard_service.update()
   ├─ step 3: notification_service.send()
   └─ on any fail: compensate (refund, rollback)
```

Có 1 saga manager rõ ràng. Lợi: dễ trace, dễ thêm compensation. Hại: orchestrator dễ phình thành god class.

> Heuristic: **bắt đầu choreography**, refactor sang orchestration khi luồng > 4 bước hoặc compensation phức tạp.

### 2.6. Outbox pattern — atomicity giữa state + event

Vấn đề: làm sao đảm bảo "state save **và** event publish hoặc cả hai cùng thành công, hoặc cả hai cùng fail"?

**Sai cách (dual write)**:
```python
repo.save(submission)       # commit DB
bus.publish(QuizSubmitted)  # commit Kafka
```
Nếu DB commit OK rồi process crash trước khi publish → **state có nhưng event mất** → projection ngoài không update → bug khó debug.

**Đúng cách (Outbox)**:
```
Trong cùng DB transaction:
   INSERT submissions (...)
   INSERT outbox (event_data, dispatched=false)
COMMIT
   ↓
Relay process (poll hoặc CDC):
   for row in outbox where not dispatched:
       bus.publish(row.event_data)
       UPDATE outbox SET dispatched=true WHERE id=row.id
```

Bây giờ atomicity DB lo. Worst case: relay crash giữa publish và update → event publish 2 lần → consumer phải idempotent (như mục 2.3). Tail-end-consistency.

### 2.7. Invariants

5 quy tắc, vi phạm thì *không phải EDA chính tắc* nữa:

1. **Event là immutable** — không sửa sau khi publish. Cần "đính chính"? Publish event mới (`ScoreCorrected`) không phải sửa cũ.
2. **Producer không await consumer** — fire-and-forget. Cần feedback? Dùng command, không phải event.
3. **Handler chỉ làm 1 việc + idempotent** — không spawn vòng vô tận.
4. **Schema event versioned** — sau 6 tháng schema thay, chưa-upgrade consumer vẫn deserialize được (thêm field optional, tránh remove).
5. **Có DLQ + monitoring** — không có DLQ là không có production-grade EDA.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
# Events (immutable)
class Event { event_id: UUID, occurred_at: datetime }
class QuizSubmitted(Event)        { user_id, answers }
class ScoreCalculated(Event)      { user_id, score, breakdown }
class LeaderboardUpdated(Event)   { user_id, rank }
class NotificationSent(Event)     { user_id, channel }

# Bus
interface IEventBus:
    subscribe(event_type, handler)
    publish(event) -> None         # fire-and-forget

class SyncBus implements IEventBus:
    handlers: Dict[Type, List[Handler]]
    def publish(event):
        for h in handlers[type(event)]:
            try: h(event)
            except: dlq.append(...)

class AsyncBus implements IEventBus:
    queue: BlockingQueue
    workers: ThreadPool(N)
    def publish(event): queue.put(event)
    def worker_loop(): while: e = queue.get(); dispatch(e)

# Decorators (chain pattern, Lesson 9)
class RetryingBus(inner, max_retries=3): retries each handler with backoff
class IdempotentHandler(inner): dedup by event_id

# Handlers
class ScoringHandler:                 # Saga step 1
    bus, scoring_service, repo
    def handle(QuizSubmitted e):
        result = scoring_service.score(e.answers)
        repo.save_score(...)
        bus.publish(ScoreCalculated(user_id=e.user_id, score=result.score))

class LeaderboardHandler:             # Saga step 2 (parallel branch)
    def handle(ScoreCalculated e):
        rank = leaderboard.upsert(e.user_id, e.score)
        bus.publish(LeaderboardUpdated(...))

class NotificationHandler:            # Saga step 2 (parallel branch)
    def handle(ScoreCalculated e):
        email.send_receipt(e.user_id, e.score)
        bus.publish(NotificationSent(...))

class AnalyticsHandler:               # Catch-all metrics
    def handle(any Event e): metrics_counter[type(e).__name__] += 1

# Outbox pattern (atomicity)
class OutboxRepo:
    save_with_event(state, event)    # 1 transaction
    fetch_undispatched()
    mark_dispatched(id)

class OutboxRelay(repo, bus):
    def run_once():
        for row in repo.fetch_undispatched():
            bus.publish(deserialize(row.event_data))
            repo.mark_dispatched(row.id)

# Orchestration alternative
class QuizSagaOrchestrator:
    def run(QuizSubmitted e):
        try:
            score = scoring.score(e)
            leaderboard.update(e.user_id, score)
            notification.send(e.user_id, score)
        except Exception:
            self.compensate(e)
```

### 3.2. Bảng 2x2 nhớ là đủ

|  | **Sync dispatch** | **Async dispatch** |
|---|---|---|
| **In-process bus** | Callback list. Default cho monolith. Latency 0. Test dễ. | Threadpool / asyncio queue. Concurrent. Test cần await/poll. |
| **Out-of-process bus** | Hiếm — thường is async. RPC + push cũng không gọi là EDA. | Kafka / RabbitMQ / SNS. Distributed real. Persistence + replay. |

In-process EDA là 80% cases. Khi cần scale ra service riêng, swap implementation IEventBus sang Kafka adapter — *chính lý do bạn đặt interface IEventBus*.

---

## NĂM CHIỀU SO SÁNH (in não vs in code)

| Chiều | Trong não (Dopamine RPE / AP broadcast) | Trong code (EDA) |
|-------|------------------------------------------|-------------------|
| **Cấu tạo** | VTA neuron (producer); axon arborization tới striatum/PFC/amygdala (bus path); receptor D1/D2 ở mỗi vùng (subscribers) | Producer (`ApplicationService`); `IEventBus` (broker / queue); Handler functions/classes (subscribers) |
| **Vị trí** | VTA ở midbrain, "bắn" lên trên thông qua medial forebrain bundle. Bus = network of axons | Producer trong domain layer; bus là singleton infra; handler ở handler layer (đăng ký tại bootstrap) |
| **Chức năng** | VTA *phát signal RPE*, vùng đích tự *interpret* khác nhau (hành vi, kỳ vọng, cảm xúc) | Producer *publish fact*, mỗi handler *interpret riêng* (update DB, send email, log analytics) |
| **Kết nối** | One-to-many: 1 spike → multi vùng đồng thời. Không có "đường dây riêng tới striatum" | Pub-sub fan-out. Producer publish event_type; bus dispatch tất cả handler đã subscribe type đó |
| **Ý nghĩa** | Decoupling biological: thêm 1 vùng học behavior mới (ví dụ accumbens shell) **không cần sửa VTA**. Robust khi mất 1 vùng | Decoupling architectural: thêm consumer mới (badge, fraud detect) không sửa producer. 1 consumer fail không sập hệ |

---

## BA VÍ DỤ

### Ví dụ 1 — Vận hành thường (happy path: saga choreography)

User submit quiz → 1 event đẻ chuỗi 4 event:

```
QuizSubmitted (publish bởi ApplicationService)
        │
        ▼
ScoringHandler ──publish──▶ ScoreCalculated
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
       LeaderboardHandler  NotifHandler   AnalyticsHandler
                │               │
                ▼               ▼
       LeaderboardUpdated  NotificationSent
```

Producer **chỉ publish 1 event**. Toàn bộ side-effect (chấm điểm, lưu, leaderboard, email, analytics) tự động xảy ra qua chuỗi handler. Producer code:

```python
def submit_quiz(self, dto):
    submission = Submission(dto.user_id, dto.answers, self.clock.now())
    self.repo.save(submission)
    self.bus.publish(QuizSubmitted(user_id=dto.user_id, answers=dto.answers))
    return {"submission_id": ...}     # return ngay, không chờ scoring
```

3 dòng. Không biết chấm điểm, không biết email, không biết leaderboard. Đó mới là OCP thực sự (Lesson 25).

### Ví dụ 2 — Hỏng / vi phạm (failure mode)

**Vi phạm A — Producer phụ thuộc consumer**:
```python
# BAD
def submit_quiz(self, dto):
    submission = ...
    self.repo.save(submission)
    self.email_service.send(...)         # ✗ producer biết email
    self.leaderboard.update(...)         # ✗ producer biết leaderboard
    self.bus.publish(QuizSubmitted(...))
```
→ Vô nghĩa: vẫn coupling. Đúng phải đẩy 2 dòng giữa vào *handler*.

**Vi phạm B — Consumer không idempotent + at-least-once delivery**:
```python
class LeaderboardHandler:
    def handle(self, e: ScoreCalculated):
        self.leaderboard[e.user_id] += e.score    # ✗ không dedup
```
→ Bus retry sau timeout → score cộng 2 lần → leaderboard sai.

**Vi phạm C — Saga loop vô hạn**:
```python
class HandlerA: handle(EventX) → publish(EventY)
class HandlerB: handle(EventY) → publish(EventX)   # ← LOOP
```
→ Bus quá tải, system chết. Phòng: *không cho phép cycle trong saga DAG*; dùng correlation ID để detect.

**Vi phạm D — Sửa event sau publish**:
```python
event = QuizSubmitted(...)
bus.publish(event)
event.user_id = "another"     # ✗ event phải immutable
```
→ Handler khác (chưa run) sẽ thấy state mới. Trong Python dùng `@dataclass(frozen=True)`.

### Ví dụ 3 — Ứng dụng Ellumm Quiz

Refactor `quiz_god.py` từ Hex (Lesson 30) lên EDA:

```
domain/
  events.py          # @dataclass(frozen=True) các event
  app_service.py     # publish QuizSubmitted, không gọi email/leaderboard nữa
  ports.py           # IEventBus + driven ports cũ
infra/
  sync_bus.py        # InMemoryEventBus
  async_bus.py       # ThreadPoolEventBus
  retrying_bus.py    # Decorator retry + DLQ
  outbox.py          # OutboxRepo + OutboxRelay
handlers/
  scoring_handler.py
  leaderboard_handler.py
  notification_handler.py
  analytics_handler.py
  badge_handler.py        # ← thêm sau, producer không sửa
saga/
  orchestrator.py    # alternative cho choreography
bootstrap.py
main.py
```

Lợi:
- Thêm `badge_handler` chỉ cần `bus.subscribe(ScoreCalculated, badge_handler.handle)` ở bootstrap, *zero touch* domain.
- Email fail → DLQ; user vẫn được chấm điểm + lưu OK.
- Test producer chỉ cần `MockEventBus.captured` list — không cần real handler.

---

## MỨC ARCHITECT — TRADE-OFFS, KHI NÀO DÙNG / KHÔNG, ANTI-PATTERNS

### Khi nào DÙNG

- **Có ≥ 3 consumer cho cùng event**: fan-out là điểm bán hàng chính.
- **Producer không cần biết consumer**: extension point cho team khác.
- **Side-effect không critical-path**: analytics, notification, search index sync — async tốt hơn.
- **Microservices**: out-of-process EDA (Kafka) gần như bắt buộc giữa các service.
- **Long-running workflow** (saga > 2 step): chia thành event chain dễ trace hơn distributed transaction.
- **Audit trail cần thiết**: mọi state change phát event, dễ log/replay.

### Khi nào KHÔNG dùng

- **Cần kết quả ngay** (synchronous read after write): user submit form → expect kết quả pop ra ngay. Đừng EDA cho path này — eventual consistency làm UX kém.
- **Single consumer cho mỗi event**: chỉ 1 handler thì gọi method bình thường, không cần bus.
- **Strong consistency required** (banking transfer single account): dùng transaction trực tiếp, không saga.
- **Team chưa có monitoring + DLQ + tracing**: EDA phải có tooling — không có thì debug địa ngục.
- **Codebase < 5,000 LOC**: overkill. Giữ Hex sync, đợi đến khi cần fan-out.

### Trade-offs

| Trục | EDA được | EDA mất |
|------|----------|---------|
| **Coupling** | Producer/consumer độc lập | Schema event trở thành public contract — phá là fail nhiều consumer |
| **Latency** | Producer nhanh (return ngay) | End-to-end "complete" eventual, có lag |
| **Throughput** | Consumer scale độc lập | Throughput tổng = min(producer rate, slowest consumer rate) khi backpressure |
| **Failure isolation** | 1 consumer fail không sập producer | Failure khó trace — không có stack trace xuyên bus |
| **Debug** | Audit trail giàu | Thứ tự event qua bus có thể swap; cần distributed tracing (OpenTelemetry) |
| **Ordering** | Có thể partition để giữ order trong key | Mất ordering toàn cục |
| **Consistency** | Eventual; tolerated | Bug nguy hiểm: consumer A xong nhưng B chưa — UI hiển thị nửa state |

### Anti-patterns thường thấy

| Anti-pattern | Mô tả | Phát hiện |
|--------------|-------|-----------|
| **Distributed monolith via events** | Service A publish → service B publish → service A publish. Vẫn coupling chặt qua chain. | Vẽ event flow graph; nếu không phải DAG đơn giản → red flag |
| **Event soup** | 200 event type không có taxonomy, naming inconsistent | Áp dụng *bounded context* DDD; mỗi context naming riêng |
| **Using event as command** | Event tên `SendEmailRequested` (imperative) → consumer phải làm. Nhầm semantics. | Tên event past-tense; nếu cần command → dùng command bus riêng |
| **Event chứa quá ít data** | Consumer phải callback producer hỏi state → coupling sync trở lại | Event-carried state transfer: gói đủ data cho consumer thường dùng |
| **Event chứa quá nhiều data** | Event 50 field, schema hard to evolve | Chia event nhỏ; chỉ chứa data trực tiếp liên quan |
| **Cycle in event chain** | A→B→A. Loop. | Detection: correlation ID + max depth |
| **Producer cũng là consumer của chính event mình** | Side-effect lan ngược | Tách aggregate boundary |
| **No idempotency** | Replay → state corrupt | UNIQUE constraint trên event_id ở consumer side |
| **No DLQ + retry** | Event lost trong production | Phải có cả 2 trước khi go-live |
| **Sync handler in async bus** | Block worker thread → throughput sụp | Handler phải nhanh (< 100 ms); nặng thì delegate sang job queue khác |
| **No schema versioning** | Đổi field → consumer cũ vỡ | Event versioning + backward compat (chỉ thêm optional field) |

### Checklist trước khi merge PR (EDA review)

- [ ] Mọi event class là `@dataclass(frozen=True)` (immutable).
- [ ] Tên event past-tense (`OrderPlaced`, không `PlaceOrder`).
- [ ] Mỗi event có `event_id` UUID + `occurred_at` datetime.
- [ ] Producer chỉ làm 2 việc: commit local state + publish event.
- [ ] Mỗi handler idempotent (test replay 2x).
- [ ] Có Retry với exponential backoff + max_retries cụ thể.
- [ ] Có DLQ + log đủ context để replay sau khi fix.
- [ ] Saga vẽ DAG được, không cycle.
- [ ] Có test integration cho saga end-to-end.
- [ ] Outbox pattern nếu producer write DB + publish (atomicity).
- [ ] Schema event versioned (v1, v2 hoặc dùng schema registry).

### So sánh kết hợp với pattern lân cận

| Pattern | Vai trò trong EDA |
|---------|-------------------|
| **Observer (Lesson 19)** | Anh em ruột của EDA in-process. EDA = Observer + async + persistence + retry + DLQ |
| **Decorator (Lesson 9)** | Wrap bus: `RetryingBus(LoggingBus(IdempotentBus(real_bus)))` |
| **Command (Lesson 14)** | Command bus song song với event bus — 1 cho action request, 1 cho fact |
| **Mediator (Lesson 17)** | Saga orchestrator chính là Mediator scaled |
| **Strategy (Lesson 21)** | Handler là strategy: swap `EmailHandler` ↔ `SmsHandler` cho event `OrderPlaced` |
| **Hex (Lesson 30)** | EDA bus là một driven port (`IEventBus`); Kafka adapter implement port; tốt cho test |
| **CQRS+ES (Lesson 32)** | EDA *vận chuyển* event từ aggregate → projection. EDA không bắt buộc ES; ES không bắt buộc EDA. Cộng hưởng tốt |

---

## BÀI TẬP — 4 MỨC

### Mức 1 — Cơ bản (45 phút)

Lấy file `30_hexagonal.py`. Thay 1 driven port `INotifier` bằng pub-sub: producer publish `QuizSubmitted`; tách `EmailNotifier` thành `EmailHandler` subscribe vào event. Verify:
- Producer code không còn import `INotifier`.
- Add 1 handler thứ 2 (LogHandler) chỉ cần thêm 1 dòng `bus.subscribe(...)`.

### Mức 2 — Trung bình (1.5 giờ)

(a) Implement saga choreography 3-step: `QuizSubmitted → ScoringHandler → ScoreCalculated → LeaderboardHandler → LeaderboardUpdated`.
(b) Test idempotency: publish cùng `QuizSubmitted` (cùng `event_id`) 2 lần; assert leaderboard không nhân đôi.
(c) Implement `RetryingBus(inner, max=3)` decorator + DLQ. Test với handler flaky 50%.

### Mức 3 — Khó (architect, 3 giờ)

(a) Implement Outbox pattern: `OutboxSubmissionRepo.save(submission, events)` trong cùng SQLite transaction; `OutboxRelay.poll_and_publish()` chạy mỗi 100 ms. Test atomicity: kill process giữa save + publish → restart → relay vẫn publish.

(b) Implement Saga **orchestrator** alternative cho cùng workflow. Compare: số dòng code, số file, dễ trace, dễ thêm compensation step. Viết note 200 từ về khi nào chọn cái nào.

(c) Convert sync bus → async (asyncio hoặc ThreadPool). Đo throughput 10,000 event với 4 handler:
- Sync (sequential): __ events/sec
- Async (4 worker): __ events/sec
- Theo Amdahl, dự đoán speedup 4 worker nhưng thực tế bao nhiêu? Giải thích sự lệch.

### Mức 4 — Mở rộng neuro (2 giờ tự do)

Đọc paper Schultz 1997 *"A neural substrate of prediction and reward"* (1 trang abstract + figure 1) hoặc xem *"Neuroscience of Decision Making"* lecture của Read Montague. Trả lời:

1. **RPE = positive/negative/zero**: tương đương 3 loại event nào trong EDA? (Hint: *expected reward arrived*, *unexpected reward*, *expected reward missed*.) Map xuống code: khi consumer expect event đến mà không đến trong T giây → hành động gì? (Timeout pattern.)

2. **Dopamine encode RPE chứ không phải reward**: tức encode *delta*, không phải *absolute*. Trong code: event nên carry *delta state* (`ScoreIncrementedBy=5`) hay *new state* (`ScoreNowIs=42`)? Trade-off?

3. **Tonic vs phasic firing**: tonic = baseline rate, phasic = burst. Trong bus, đó là 2 loại event nào? (Heartbeat / state-snapshot vs transactional event.) Khi nào team nên design cả 2?

---

## ĐỒ HOẠ TỔNG KẾT

```
            EVENT-DRIVEN ARCHITECTURE
   ┌──────────────────────────────────────────────┐
   │                                              │
   │   PRODUCER ──publish(QuizSubmitted)──┐       │
   │   (returns)                          │       │
   │                                      ▼       │
   │                                   [BUS]      │
   │                                      │       │
   │             ┌────────────────────────┼─────────────────────────┐
   │             ▼                        ▼                         ▼
   │    ScoringHandler ─publish─▶ LeaderboardHandler        NotifHandler
   │             │                        │                         │
   │             ▼                        ▼                         ▼
   │     ScoreCalculated         LeaderboardUpdated         NotificationSent
   │             │                                                   │
   │             ▼                                                   ▼
   │      AnalyticsHandler ◀────────────────────────────── (subscribes to *)
   │                                                                 │
   │             [DLQ] ◀── handler fail max-retries                  │
   │             [Outbox] ── atomicity DB + bus                      │
   │                                                                 │
   └─────────────────────────────────────────────────────────────────┘
        async + idempotent + DLQ + saga + outbox = production EDA
```

> **Tóm lại**: EDA = "publish fact, fan-out tới mọi consumer quan tâm, bất đồng bộ, độc lập failure". Não dùng dopamine RPE broadcast. Code dùng event bus. Cùng 1 nguyên lý: tách producer khỏi consumer chỉ qua *event schema*, mọi thứ khác *swappable*. Đắt cho monitoring; rẻ cho thêm tính năng. ROI cao khi system phức tạp + nhiều side-effect không-critical-path.

---

## TIẾP THEO

- **Lesson 32 — CQRS + Event Sourcing** (đã làm): tách driving port read/write, lưu event làm source of truth, projection rebuild.
- **Lesson 33 — Anti-patterns catalog**: review mọi pattern qua lăng kính phòng ngự.
