# Lesson 32 — CQRS + Event Sourcing
## Memory Consolidation Duality — Hippocampus (write path: episodic, slow encode, durable) ↔ Neocortex (read path: indexed, fast retrieve, semantic). Sleep replay = event replay project lên read model.

---

## TÓM TẮT MỘT DÒNG

**CQRS + Event Sourcing** = tách *write model* và *read model* thành hai cấu trúc khác nhau (CQRS), và lưu **chuỗi events bất biến** thay vì current state (ES). Aggregate xử lý command → emit events → event store append-only → projections chiếu events sang read models tối ưu cho từng query. **State hiện tại = fold(events)**, không phải hàng row trong table.

> Não bạn đã làm điều này 500 triệu năm rồi. Khi bạn học một sự kiện mới (đi sinh nhật bạn ngày 5/5/2026), **hippocampus** ghi nó dưới dạng *episodic event* — chậm, vài ms, durable, có timestamp, không overwrite. Trong giấc ngủ NREM, hippocampus **replay** sequence đó hàng trăm lần với tốc độ nén 20×, và mỗi lần replay neocortex lấy event ấy *project* lên các "read model" semantic: bạn nhớ "Mai thích bánh socola" (UserPreferenceProjection), "tháng 5 là sinh nhật Mai" (CalendarProjection), "công thức bánh kem" (RecipeProjection). Sáng dậy, bạn không phải replay event để biết "Mai thích bánh socola" — bạn query thẳng read model. Nhưng nếu cần (PTSD, recall therapy), bạn vẫn có thể truy event store gốc. **Eventual consistency** chính là cách não thật vận hành: write (HC) và read (neocortex) không strongly consistent — chúng *eventually* sync qua replay.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Trong CRUD truyền thống:
- **Một model duy nhất** (table `submissions` chẳng hạn) phục vụ cả write (insert/update) lẫn read (SELECT cho leaderboard, dashboard, report).
- Khi **write** (1 user submit) và **read** (10K user xem leaderboard) có *shape* và *scale* khác nhau, một schema phải compromise cho cả hai.
- **History bị mất**: UPDATE đè lên row cũ. Câu hỏi "user X submit lúc 10h, score là bao nhiêu, sau đó được điều chỉnh thế nào?" không trả lời được nếu chỉ giữ current state.
- **Audit/compliance khó**: Để audit, người ta thêm `audit_log` table — nhưng đó chỉ là replica của state changes, dễ drift, dễ lost.
- **Read scale**: thêm leaderboard real-time? Phải JOIN nhiều table, thêm index, viết materialized view; mỗi feature read mới là một bài toán SQL tối ưu.
- **Temporal query**: "Top 10 user lúc 9h sáng hôm qua" — gần như không thể nếu chỉ có current state.

CQRS giải bằng cách **tách hoàn toàn write model và read model**: write model tối ưu cho consistency + business rule; mỗi read model là một *materialized view* tối ưu cho 1 nhóm query. ES bổ sung bằng cách **không lưu state** — chỉ lưu **chuỗi events**. State là kết quả của việc *fold* events lại.

### 1.2. Định nghĩa và lịch sử

**CQRS** (Command-Query Responsibility Segregation):
- **Greg Young 2010**, dựa trên **Bertrand Meyer's CQS** (Command-Query Separation, 1988): một method hoặc *command* (mutate state, return void) hoặc *query* (read state, no side-effect), không cả hai.
- CQRS scale CQS từ method-level lên *system-level*: tách hai *model* thay vì hai *method*.

**Event Sourcing** (ES):
- **Martin Fowler 2005** (paper "Event Sourcing"), nhưng concept có từ kế toán đôi (Luca Pacioli 1494) và database transaction log của những năm 1970.
- Insight: state là *derived*; events là *primary*. Event store = ledger append-only.

**CQRS không bắt buộc kèm ES** và **ES không bắt buộc kèm CQRS**, nhưng chúng *cộng hưởng* mạnh:
- Có ES → write model tự nhiên là event stream → cần projection để read efficiently → CQRS xuất hiện.
- Có CQRS → write/read tách → write có thể là event stream (ES) hoặc chỉ command + traditional store.

> *"You're not telling me what to do; you're telling me what happened."* — Greg Young, on event-driven write models.

### 1.3. Neuroscience analogy chi tiết

| Khái niệm CQRS+ES | Cấu trúc não | Cơ chế |
|--------------------|--------------|--------|
| **Write path (Aggregate)** | **Hippocampus** (CA3 → CA1) | Encode episodic event: "user 42 submitted quiz 7 with answers [A,C,B] at 10:32". Pattern separation tại DG đảm bảo events không collide. Slow but durable |
| **Event Store** | **Hippocampal trace + theta-rhythm replay sequences** | Append-only sequence, không overwrite. Schaffer collateral lưu trace. CA3 recurrent network = "transaction log" |
| **Event Bus / publish** | **Sharp-wave ripples** (SWR) trong NREM sleep | HC bắn replay sequence lên neocortex 20× nén thời gian |
| **Projection (Read Model)** | **Neocortical semantic memory** | Mỗi vùng cortex chuyên một loại "view": entorhinal lưu spatial, prefrontal lưu social rules, temporal lưu names |
| **Query path** | **Neocortex direct retrieve** | Bypass HC sau consolidation. Fast, indexed, không cần episodic context |
| **Replay (rebuild projection)** | **Sleep-dependent consolidation** | Replay events tăng tốc và project lên cortex, build dần read model |
| **Eventual consistency** | **Lag giữa encode và consolidation** | Bạn nhớ event ngay sau khi xảy ra (HC), nhưng phải vài đêm ngủ mới có "semantic gist" (neocortex). Hai store eventually sync |
| **Snapshot** | **Skill memory / procedural overlearning** | Sau ngàn lần replay, một state-summary được "compiled" → không cần replay lại từ đầu |
| **Idempotent event handler** | **Mỗi neocortex neuron fire một response cố định cho cùng input** | Replay 100× cùng event không tạo 100 memory; chỉ strengthen synapse một cách bounded |
| **Saga (process manager)** | **Polysynaptic chain** | Event A trigger event B trigger event C, mỗi cái có invariants riêng |

**Bằng chứng critical**: bệnh nhân **HM (Henry Molaison)** — mất hippocampus 1953 — không *encode* được episodic memory mới, nhưng skill cũ và semantic memory cũ vẫn nguyên (procedural + neocortical store giữ được). Đó là CQRS in action: read path còn nguyên dù write path hỏng. Ngược lại, **dementia Alzheimer giai đoạn cuối** — neocortex thoái hoá — patient có HC tương đối ổn ở giai đoạn đầu nhưng không thể *retrieve* gì cả: read path hỏng, write path còn (tạm). Hai path thực sự độc lập.

**Sleep replay**: Wilson & McNaughton (1994) ghi multi-unit recording từ HC chuột chạy mê cung; chuột ngủ → cùng spike sequence replay với tốc độ 7-20× nhanh hơn realtime. Skaggs & McNaughton (1996) confirm direction: forward replay khi học, backward replay khi consolidate — cả hai project events lên cortex theo cùng cơ chế ES-projection. Không có gì gần với "Event Sourcing" hơn.

---

## MỨC 2 — ALGORITHM / CẤU TRÚC

### 2.1. Vai diễn (actors)

| Actor | Trách nhiệm | Tương đương não |
|-------|-------------|-----------------|
| **Command** | DTO bất biến: "ý định thay đổi state" (`SubmitQuiz(user, answers)`) | Sensory input + intent từ PFC |
| **Command Handler** | Nhận command, load aggregate, gọi method, append events | DG (dentate gyrus) routing input |
| **Aggregate** | Cluster entities + invariant rules; xử lý command → emit events | CA3 recurrent network — nơi pattern completion + invariant check |
| **Domain Event** | "Đã xảy ra" (past tense): `QuizSubmitted`, `ScoreCalculated` | Episodic memory trace |
| **Event Store** | Append-only DB: stream per aggregate, optimistic concurrency | Hippocampal trace storage |
| **Event Bus / Publisher** | Bắn events đến subscribers async | Sharp-wave ripple broadcast |
| **Projection (Projector)** | Subscribe events → cập nhật read model | Cortical area receiving SWR |
| **Read Model** | Materialized view tối ưu cho query | Cortical semantic store |
| **Query** | DTO request đọc | Recall cue |
| **Query Handler** | Đọc thẳng read model, không qua aggregate | Cortical retrieval |
| **Snapshot** | State summary tại event N để skip replay từ 0 | Procedural memory |
| **Saga / Process Manager** | State machine react events → emit command | Polysynaptic chain |

### 2.2. Luồng điều khiển

**Write path** (1 command):
```
1. Client gửi Command(SubmitQuiz, user_id, quiz_id, answers)
2. CommandHandler.handle(command):
   2a. event_store.load_events(aggregate_id) → [Event1, Event2, ...]
   2b. aggregate = QuizSubmissionAggregate()
   2c. for e in events: aggregate.apply(e)        ← rebuild current state
   2d. new_events = aggregate.handle(command)     ← business logic, return events
   2e. event_store.append(aggregate_id, expected_version, new_events)  ← optimistic lock
   2f. event_bus.publish(new_events)
3. Return command result (typically just the new aggregate id + version)
```

**Read path** (1 query):
```
1. Client gửi Query(GetLeaderboard, top_n=10)
2. QueryHandler.handle(query):
   2a. read_model.fetch(query_params)              ← already projected, no aggregate involved
   2b. return DTO list
```

**Projection (background, ai-trigger event mới):**
```
1. Projector subscribe events từ event_bus
2. Khi nhận event:
   2a. Load relevant read model row(s)
   2b. Apply event-specific update
   2c. Save read model
3. Track last_processed_version để recover
```

**Replay (rebuild projection from scratch):**
```
1. Drop read model
2. Stream tất cả events từ store theo thứ tự (global hoặc per aggregate)
3. Apply từng event vào projector
4. Switch traffic sang read model mới
```

### 2.3. Biến trạng thái và invariants

**State** trên Aggregate (transient, rebuild from events mỗi command):
- Aggregate version (số event đã apply)
- Domain state (vd: `QuizSubmission.score`, `.is_finalized`)

**State** trên Event Store (persistent):
- Per-stream event list, mỗi event có: `aggregate_id`, `version`, `event_type`, `payload`, `timestamp`, `correlation_id`

**State** trên Read Model (derived):
- Per-projection table/dict, có `last_processed_event_position` để track lag

**Invariants** (must hold):
1. **Append-only**: events không bao giờ bị update/delete sau khi commit. Sửa lỗi = emit *compensating event* mới.
2. **Optimistic concurrency**: append với expected_version; nếu version trên store ≠ expected → conflict, retry.
3. **Idempotent projection**: applying cùng event 2 lần không phá read model (dùng event_id check hoặc CRDT-friendly state).
4. **Order per aggregate**: events trong cùng aggregate stream được apply đúng order. Cross-aggregate order không guarantee strong.
5. **Aggregate boundary**: command chỉ touch 1 aggregate per transaction. Cross-aggregate = saga.
6. **Events là past-tense fact**: `QuizSubmitted` ✓, `SubmitQuiz` ✗ (đó là command).

### 2.4. Biến thể (variants)

| Biến thể | Mô tả | Khi nào dùng |
|----------|-------|--------------|
| **CQRS without ES** | Tách write/read, nhưng write vẫn dùng traditional state DB (UPDATE) | Read scale là vấn đề chính, không cần audit/temporal |
| **ES without CQRS** | Lưu events, nhưng read cũng từ events (replay-on-demand) | Domain nhỏ, query hiếm và ít cần optimize |
| **ES + CQRS (full)** | Cả hai | Audit + read scale + temporal queries |
| **In-process events** | Bus là callback list trong cùng process | Single-instance app, prototype |
| **Distributed events** | Kafka/RabbitMQ/Pulsar | Multi-service, distributed |
| **Synchronous projection** | Update read model trong cùng transaction với event append | Strong consistency cần thiết, sacrifice scalability |
| **Asynchronous projection** | Background worker | Default, eventual consistency |
| **Snapshot per-N events** | Chụp state mỗi 100 event để skip replay | Aggregate có >1000 events |
| **Multiple read models** | 1 event → 5 projections khác nhau | Mỗi UI/report có một read model riêng |
| **Saga (process manager)** | State machine React events, emit commands cho aggregates khác | Cross-aggregate workflow (đặt hàng → thanh toán → ship) |
| **CQRS-lite** | Tách Command service và Query service, nhưng vẫn cùng DB | Stepping stone trước khi full CQRS |

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```pseudo
# ============ EVENTS ============
event QuizSubmitted(submission_id, user_id, quiz_id, answers, submitted_at)
event ScoreCalculated(submission_id, score, max_score)
event SubmissionFinalized(submission_id, finalized_at)
event ScoreCorrected(submission_id, old_score, new_score, reason)

# ============ COMMANDS ============
command SubmitQuiz(user_id, quiz_id, answers)
command FinalizeSubmission(submission_id)
command CorrectScore(submission_id, new_score, reason)

# ============ AGGREGATE ============
class QuizSubmissionAggregate:
    state:
        submission_id: UUID = None
        user_id: UUID = None
        quiz_id: UUID = None
        answers: list = []
        score: int = None
        is_finalized: bool = False
        version: int = 0

    method apply(event):
        match event.type:
            QuizSubmitted: set submission_id, user_id, quiz_id, answers
            ScoreCalculated: set score
            SubmissionFinalized: set is_finalized = True
            ScoreCorrected: set score = event.new_score
        version += 1

    method handle(command) -> list[Event]:
        match command.type:
            SubmitQuiz:
                require submission_id is None  # invariant: not yet created
                emit QuizSubmitted(...)
                # Calculate score (domain logic)
                score = scorer.score(quiz, answers)
                emit ScoreCalculated(score, max_score)
            FinalizeSubmission:
                require submission_id is not None
                require not is_finalized
                emit SubmissionFinalized(now)
            CorrectScore:
                require is_finalized
                emit ScoreCorrected(old=score, new=cmd.new_score, reason)

# ============ EVENT STORE ============
class EventStore:
    streams: Dict[aggregate_id, list[Event]]

    method load_events(aggregate_id) -> list:
        return streams.get(aggregate_id, [])

    method append(aggregate_id, expected_version, new_events):
        current = streams.get(aggregate_id, [])
        if len(current) != expected_version:
            raise ConcurrencyConflict
        streams[aggregate_id] = current + new_events
        return new_events  # for publish

# ============ COMMAND HANDLER ============
class SubmitQuizHandler:
    method handle(command):
        events = event_store.load_events(command.aggregate_id)
        agg = QuizSubmissionAggregate()
        for e in events: agg.apply(e)
        new_events = agg.handle(command)
        event_store.append(command.aggregate_id, agg.version, new_events)
        for e in new_events:
            agg.apply(e)
            event_bus.publish(e)

# ============ PROJECTIONS ============
class LeaderboardProjection:
    state: Dict[user_id, total_score]

    method on(event):
        match event.type:
            ScoreCalculated: state[event.user_id] += event.score
            ScoreCorrected: state[event.user_id] += (new - old)

class UserStatsProjection:
    state: Dict[user_id, {count, avg, last_quiz_at}]

    method on(event):
        match event.type:
            QuizSubmitted: stats[user_id].count += 1; last_quiz_at = event.submitted_at
            ScoreCalculated: stats[user_id].avg = recompute()

# ============ QUERY ============
class GetLeaderboardQuery:
    method handle(query):
        return leaderboard_proj.top_n(query.n)
```

### 3.2. Python — xem `32_cqrs_es.py`

File `32_cqrs_es.py` implement đầy đủ:
- 4 events (QuizSubmitted, ScoreCalculated, SubmissionFinalized, ScoreCorrected)
- Aggregate `QuizSubmissionAggregate` với apply + handle
- `EventStore` in-memory với optimistic concurrency
- `EventBus` đơn giản (pub-sub callback)
- 2 projections: `LeaderboardProjection`, `UserStatsProjection`
- 3 command handlers: SubmitQuiz, Finalize, CorrectScore
- 2 query handlers: GetLeaderboard, GetUserStats
- 4 demos: happy path, replay, concurrency conflict, score correction (compensating)

---

## 5 CHIỀU IN-NÃO vs IN-CODE

| Chiều | In code | In não |
|-------|---------|--------|
| **Cấu tạo** | Command/Event DTO + Aggregate (write) + EventStore + EventBus + Projection (read) | Sensory input → DG → CA3/CA1 → SWR → cortical area |
| **Vị trí** | Tầng Domain (aggregate) + Infrastructure (event store, bus) + Read layer (projection) | Hippocampal formation + cortex theo từng modality |
| **Chức năng** | Decouple write từ read; preserve full history; rebuild any read model bất kỳ lúc nào từ event log | Encode rapid + episodic; consolidate slow + semantic; recall qua nhiều "view" specialized |
| **Kết nối** | Command → Aggregate → Event Store → Bus → Projections → Read Models → Query | Sensory → MTL → HC → SWR → cortical → recall cue |
| **Ý nghĩa** | "State là derived. Events là primary. Read model nào mất thì rebuild được." | "Memory không phải file overwrite — là sequence of episodes consolidate dần thành semantic" |

---

## 3 LOẠI VÍ DỤ

### Ví dụ 1 — Vận hành thường (happy path)

User 42 submit quiz 7:
```
1. POST /submissions { user_id=42, quiz_id=7, answers=[A,C,B] }
2. Command SubmitQuiz → SubmitQuizHandler
3. Handler load events cho aggregate id=sub_001 (lần đầu, list empty)
4. Aggregate.handle → emit [QuizSubmitted, ScoreCalculated(score=2)]
5. EventStore.append(sub_001, expected_version=0, [...])
6. Bus.publish:
   - LeaderboardProjection nhận → state[42] += 2 = 2
   - UserStatsProjection nhận → stats[42] = {count: 1, last_quiz_at: now}
7. HTTP 201 trả {submission_id: sub_001, version: 2}
```

User xem leaderboard:
```
8. GET /leaderboard?top=10
9. Query GetLeaderboard → QueryHandler
10. Đọc thẳng leaderboard_proj.top_n(10) — KHÔNG load events
11. Return [{user_id: 42, score: 2}, ...]
```

Latency: write có overhead append (1 ms); read O(top_n) trên dict, ~0.1 ms. So với CRUD JOIN: read 10-50 ms.

### Ví dụ 2 — Hỏng/thiếu (failure modes)

**Failure 2a — Concurrency conflict (race condition giữa 2 command):**
```
T0: Worker A load events cho sub_001, version=2
T1: Worker B load events cho sub_001, version=2
T2: A.handle(FinalizeSubmission) → emit [SubmissionFinalized]
T3: A.append(sub_001, expected=2, [SubmissionFinalized]) ✓ (now version=3)
T4: B.handle(CorrectScore) → emit [ScoreCorrected]
T5: B.append(sub_001, expected=2, [ScoreCorrected]) ✗ ConcurrencyConflict
T6: B retry: load events (now have 3), reapply, emit ScoreCorrected, append expected=3 ✓
```
Hậu quả nếu thiếu optimistic lock: lost update — finalize bị overwrite, score corrected nhưng aggregate state inconsistent. **Optimistic concurrency là bắt buộc.**

**Failure 2b — Non-idempotent projection:**
```
Bus crash sau khi publish event nhưng trước khi commit subscriber offset.
Bus restart → replay event QuizSubmitted lần 2.
LeaderboardProjection NAIVE: state[user_id] += score → score double-counted.
```
Fix: projection track `last_processed_event_id` per stream, skip duplicates.

**Failure 2c — Anaemic event "StateUpdated":**
```
Bad: emit StateUpdated(field="score", old=5, new=7)
Good: emit ScoreCalculated(score=7) hoặc ScoreCorrected(old=5, new=7, reason="grader_review")
```
Hậu quả của bad: events mất *intent* — không biết tại sao thay đổi. Khi audit hoặc rebuild projection theo dimension business, vô dụng. Đó là **anti-pattern "CRUD events"**.

**Failure 2d — Cross-aggregate transaction:**
```
Bad: command UpdateLeaderboardAfterSubmission → handler load 2 aggregate (Submission + Leaderboard) → cross-stream append.
```
Hậu quả: phá invariant "1 aggregate per command", concurrency hell. Fix: emit event từ aggregate Submission, saga react emit command cho aggregate Leaderboard riêng.

### Ví dụ 3 — Ứng dụng Ellumm Quiz (refactor `quiz_v32`)

Trước (`quiz_v31` — sau EDA, vẫn shared state DB):
```python
class QuizService:
    def submit(self, user_id, quiz_id, answers):
        score = self.scorer.score(quiz_id, answers)
        sub = self.repo.save(Submission(user_id, quiz_id, score))
        self.bus.publish(QuizSubmittedEvent(sub.id, user_id, score))  # for analytics
        return sub
```
- Read leaderboard = SQL `SELECT user_id, SUM(score) FROM submissions GROUP BY user_id ORDER BY ...` — chậm khi scale.
- Sửa score = UPDATE submissions SET score=... → mất lịch sử "tại sao sửa".
- Test temporal: "leaderboard tại 9h hôm qua" — không có cách nào.

Sau (`quiz_v32` — full CQRS+ES):
```python
# ===== Write side =====
class QuizSubmissionAggregate:
    def handle_submit(self, cmd) -> list[Event]:
        if self.submission_id is not None:
            raise InvariantViolated("already submitted")
        events = [QuizSubmitted(...)]
        score = self.scorer.score(cmd.quiz_id, cmd.answers)
        events.append(ScoreCalculated(score, max_score))
        return events

# ===== Event store + Bus =====
event_store = InMemoryEventStore()
bus = EventBus()

# ===== Read side =====
leaderboard_proj = LeaderboardProjection()
user_stats_proj = UserStatsProjection()
bus.subscribe(ScoreCalculated, leaderboard_proj.on)
bus.subscribe(ScoreCorrected, leaderboard_proj.on)
bus.subscribe(QuizSubmitted, user_stats_proj.on)

# ===== Query =====
@app.route("/leaderboard")
def get_leaderboard():
    return jsonify(leaderboard_proj.top_n(10))   # 0.1 ms
```

**Kết quả refactor**:
- Sửa score = `CorrectScore` command → emit `ScoreCorrected` event → projection apply diff. **Lịch sử nguyên vẹn**.
- Thêm read model mới (vd: "QuizDifficultyProjection" tính avg score per quiz) = thêm 1 class subscribe events, replay từ store. **Không sửa write side.**
- Temporal query: stream events đến timestamp T, build projection at-T. **Possible.**
- Audit: list events per user. **Built-in.**
- Read scale: shard projection per region; mỗi region cache riêng. **Linear scale.**

Trade-off đã chấp nhận: thêm 4-5 class, eventual consistency 50-200 ms giữa write và read, học event modeling.

---

## SO SÁNH PATTERN LÂN CẬN

| Pattern / Style | Đặc điểm | Quan hệ với CQRS+ES |
|-----------------|----------|----------------------|
| **CRUD + ORM** | Single model write/read, UPDATE state | Đối lập. CRUD overwrite; CQRS+ES append |
| **CQRS không ES** | Tách model, write vẫn UPDATE | Step nhỏ hơn — có read scale, không có temporal/audit free |
| **ES không CQRS** | Có event log, read replay-on-demand | Khả thi nếu query rất hiếm; thường chậm |
| **EDA (Lesson 31)** | Services giao tiếp qua events | EDA là *substrate*; CQRS+ES dùng EDA để publish events ra ngoài. Nhưng CQRS+ES có thể chỉ in-process — không bắt buộc EDA |
| **Outbox pattern** | DB write + event publish trong 1 transaction qua outbox table | Giải bài toán "publish reliability". Compatible với CQRS+ES — outbox là kỹ thuật impl event store |
| **Change Data Capture (CDC)** | Stream DB log (binlog) thành events | Reverse direction: từ state → events. Dùng khi không thể refactor sang ES nhưng cần event stream |
| **Materialized View** | DB-level pre-computed query | Read model trong CQRS chính là materialized view, nhưng ngoài DB và update bởi events |
| **Saga / Process Manager** | State machine cross-aggregate | Build trên CQRS+ES tự nhiên. Saga = "stateful subscriber" |
| **Memento (GoF, Lesson 18)** | Snapshot state cho undo | Snapshot trong ES tương đương; nhưng ES có cả history tuần tự, Memento chỉ point-in-time |
| **Observer (GoF, Lesson 19)** | Pub-sub trong process | EventBus trong CQRS+ES = Observer scaled lên. Khác chỗ events trong CQRS là *domain events* (past-tense facts) |
| **Iterator (GoF, Lesson 16)** | Traverse collection | Replay = iterate event store. Có thể implement bằng Iterator. |
| **Audit log table** | Trigger ghi mọi UPDATE | "ES nửa vời" — events là log technical, không phải domain language |
| **Bitemporal database** | Lưu cả valid-time và transaction-time | Một dạng ES có schema. CQRS+ES general hơn |

**Vai trò trong SOLID**:
- **SRP**: Aggregate chỉ chịu trách nhiệm invariants; projection chỉ chịu trách nhiệm 1 read view; command handler chỉ orchestrate.
- **OCP**: Thêm projection mới = thêm class subscribe, không sửa aggregate. Maximally OCP.
- **LSP**: Mọi event subclass của `DomainEvent`; mọi projection subclass của `Projection`.
- **ISP**: Projection chỉ subscribe events nó care, không bị ép handle event lạ.
- **DIP**: Aggregate phụ thuộc abstract `IEventStore` Protocol, không SQL/Kafka cụ thể.

---

## TRADE-OFFS

| Trade-off | Chi phí | Lợi ích |
|-----------|---------|---------|
| **Eventual consistency** giữa write và read | UI có thể hiển thị data lag 50ms-vài giây; user vừa submit chưa thấy ngay trên leaderboard | Read scale linear; cache friendly |
| **Event modeling** (past-tense, domain language) | Học cách đặt tên, chia aggregate đúng — khó nhất của ES | Audit trail miễn phí, business analyst đọc được event log |
| **Schema evolution** (event versioning) | Phải versioning events; upcaster để translate v1 → v2 | Backward compat — old events vẫn replay được |
| **Replay cost** | Aggregate có 10K events → load 200 ms | Snapshot mỗi 100 events giảm replay; rebuild projection = downtime nếu không có shadow projection |
| **Storage size** | Events grow forever; 10× CRUD | Disk rẻ; archive cold events |
| **Operational complexity** | Cần monitoring lag projection, replay tooling, snapshot strategy | Một khi setup, audit + temporal + scale free |
| **Cross-aggregate workflow** | Phải dùng saga, không dùng cross-aggregate transaction | Saga có failure mode rõ ràng (compensating events) |
| **Debug khó** | "User thấy score sai" → trace events qua nhiều stream | Trace chi tiết hơn CRUD log |
| **Boilerplate** | Mỗi feature: command + event + handler + projection | Template hoá được; framework EventStoreDB / Axon giảm boilerplate |
| **Testability** | Aggregate test cực sạch (given events → when command → then events) | Format `given/when/then` chuẩn industry |

**Quy tắc dùng**:
- ✅ DÙNG khi: domain có audit/regulatory (banking, medical, voting), temporal queries quan trọng (time-travel report), read >> write 100×, multiple read views khác nhau, business invariants phức tạp cần nguồn truth duy nhất.
- ❌ KHÔNG DÙNG khi: CRUD đơn giản (admin panel), team không có ai từng làm ES (learning curve 3-6 tháng), strong consistency yêu cầu (banking transaction trong ngày — dùng RDBMS), prototype < 6 tháng lifetime.

---

## CHECKLIST TRƯỚC KHI MERGE PR

- [ ] **Event đặt tên past-tense**: `QuizSubmitted` ✓, `SubmitQuiz` ✗.
- [ ] **Event có business intent**: `ScoreCorrected(reason)` ✓, `FieldUpdated(field, value)` ✗.
- [ ] **Event immutable**: dataclass `frozen=True`, không setter.
- [ ] **Event có version**: hoặc payload có schema_version, hoặc class name có suffix `_v2`.
- [ ] **Aggregate có invariants check**: command handler raise nếu invariant violated trước khi emit event.
- [ ] **Optimistic concurrency**: append có expected_version; conflict thì retry hoặc surface error.
- [ ] **Projection idempotent**: cùng event apply 2 lần không corrupt state. Track last_processed_event_id.
- [ ] **Aggregate boundary clear**: 1 command touch 1 aggregate. Cross = saga.
- [ ] **Event store append-only**: không có code path nào UPDATE/DELETE event.
- [ ] **Snapshot strategy**: nếu aggregate >100 events lifetime, có snapshot logic.
- [ ] **Projection rebuild script**: có thể drop + replay all để rebuild.
- [ ] **Read model không feedback vào write**: query không trigger command (trừ saga, có infrastructure riêng).
- [ ] **Eventual consistency được giải thích cho UI/UX**: user hiểu lag, hoặc UI optimistic update.
- [ ] **Test format Given-When-Then**:
  ```
  GIVEN events: [QuizSubmitted, ScoreCalculated(5)]
  WHEN command: CorrectScore(new=7, reason="...")
  THEN events: [ScoreCorrected(old=5, new=7, reason="...")]
  ```

---

## BÀI TẬP 4 MỨC

### Mức 1 — Cơ bản

Mở `32_cqrs_es.py`, đọc và trả lời:
1. Liệt kê tất cả events. Mỗi event chứa data gì?
2. Tại sao `ScoreCalculated` là 1 event riêng, không gộp vào `QuizSubmitted`?
3. Khi rebuild projection từ scratch, code phần nào chạy?
4. Tìm chỗ optimistic concurrency được enforce. Nếu xoá check đó, hậu quả gì?

### Mức 2 — Trung bình

Thêm feature: "Kỳ thi ôn tập" — user có thể *retake* quiz đã submit. Chỉ lần submit cuối tính điểm leaderboard, nhưng giữ history.

Implement:
1. Command `RetakeQuiz(submission_id, new_answers)`.
2. Event `QuizRetaken(submission_id, new_answers, attempt_number, scored_at)`.
3. Aggregate handler — invariant: chỉ retake nếu `is_finalized=False` HOẶC retake_allowed=True.
4. `LeaderboardProjection` update: dùng *latest* score per user_id+quiz_id, không sum tất cả.
5. Test Given-When-Then: GIVEN [QuizSubmitted, ScoreCalculated(5), QuizRetaken, ScoreCalculated(8)] → leaderboard show 8.

Đo:
- Số file cần sửa write side: bao nhiêu? (Target: aggregate + 1 event class.)
- Số file cần sửa read side: bao nhiêu? (Target: 1 projection.)
- Có sửa file storage/bus không? (Target: 0.)

### Mức 3 — Khó (architect-level)

Tình huống: Ellumm có 5M users, 50M submissions/năm. Leaderboard query 10K req/s. Yêu cầu:
1. **Snapshot strategy**: aggregate `QuizSubmissionAggregate` có thể có ~100 events (retake, correct nhiều lần). Khi nào snapshot? Kích thước snapshot? Storage where?
2. **Projection rebuild without downtime**: cần chuyển read model schema (vd: thêm column "rank_change_24h"). Vẽ blue-green projection deploy.
3. **Eventual consistency UI**: user vừa submit, redirect tới /leaderboard, *không thấy mình*. Giải pháp: optimistic update? Read-your-writes trick? Versioned read?
4. **Multi-region**: events publish global; mỗi region có projection cache riêng. Khi region A và B receive events theo order khác (network), state khác nhau. Acceptable không? CRDT cần không?
5. **GDPR right-to-erasure**: events là append-only, nhưng user request xoá data. Crypto-shredding? Tombstone events? Trade-off với "audit immutable"?

Trả lời 5 câu trên + design 3 quyết định concrete.

### Mức 4 — Mở rộng neuroscience

1. **Replay direction** — Diba & Buzsáki (2007): hippocampus replay *forward* khi đang học (encode time order), *reverse* khi đang consolidate (causal credit assignment). Liên hệ: trong ES, có lý do nào replay reverse? (Hint: compensating event, "what if" simulation.) Mô tả use case.
2. **Pattern completion vs separation** — DG (dentate gyrus) tạo *unique sparse code* cho mỗi event (separation), CA3 *recurrent* cho phép *completion* (cue 1 phần, recall full). Liên hệ với Aggregate ID: aggregate_id phải unique (separation = idempotency key); load events from store reconstruct full state (completion). Mô tả tương đồng kỹ thuật.
3. **HM (Henry Molaison)** sau khi mất 2 hippocampus 1953: *không* nhớ event mới (write path hỏng), *vẫn* có skill cũ (read model "compiled"). Liên hệ: nếu bạn xoá event store nhưng giữ projection, hệ thống còn chạy được không? Read OK; write nào trigger được? Mô tả "anaemic CQRS".
4. **Sleep deprivation và memory consolidation**: thiếu ngủ → events không được project sang neocortex → lag tăng → tỉnh dậy không nhớ. Liên hệ: nếu bạn pause projection workers vài giờ, hậu quả lên read model? Replay catch-up bao lâu? Có lost data không (chỉ lost *current snapshot*, events nguyên vẹn)?
5. **Reconsolidation** (Nader 2000): mỗi lần recall, memory trace *temporarily labile* và có thể bị modify trước khi re-store. Liên hệ: trong CQRS+ES, có analog không? *Snapshot-based* corrections — load snapshot, mutate, persist as new events? Hay đó là anti-pattern trong ES?
6. **Hippocampal compass** (place cells, grid cells): HC encode "where" qua sparse population. Liên hệ với event correlation_id và causation_id: làm sao trace 1 user submission flow qua nhiều aggregate? Vẽ event graph như "place field map".

Trả lời 4-6 câu mỗi mục.

---

## SAU LESSON NÀY

CQRS + ES là *điểm cao nhất* trong tầng architectural styles của curriculum này — bạn đã đi từ Clean Architecture (4 vòng tròn dependency rule) qua Hexagonal (ports & adapters) qua EDA (events + async) lên đến CQRS+ES (state là derived).

**Kế tiếp — Lesson 33**: **Anti-patterns catalog**. Sau khi học cách build đúng, học *nhận diện* sai. Lesson 33 sẽ catalog: God Object, Spaghetti Code, Anaemic Domain Model, Big Ball of Mud, Golden Hammer, Premature Optimization, Lava Flow, Cargo Cult, Magic Numbers, Shotgun Surgery — mỗi cái có triệu chứng + neuroscience analogy + cách phát hiện trong code review.

Sau Lesson 33, lộ trình open: DDD (Bounded Context, Aggregate properly), Distributed Systems Patterns (Saga, Outbox, Idempotency, Circuit Breaker, Bulkhead — chính là extension tự nhiên của CQRS+ES khi đi distributed), Reading list (Vernon *Implementing DDD*, Young *Versioning in an Event Sourced System*, Hohpe *Enterprise Integration Patterns*).

> **Nhớ một câu**: CQRS+ES không phải "thay SQL bằng event log". CQRS+ES là **"state là derived; events là primary; mọi read view đều rebuild được; nothing is ever truly lost"** — đúng như não bạn đã làm 500 triệu năm.

---

## GHI CHÚ — VÌ SAO BẠN NÊN QUAY LẠI LESSON 31 (EDA)

Bạn đã làm Lesson 29 (Clean Arch) và Lesson 30 (Hexagonal) — nền *structural decoupling* đã vững. Nhưng bạn nhảy thẳng tới Lesson 32, **bỏ qua Lesson 31 (Event-Driven Architecture)**.

CQRS+ES in-process (như file `32_cqrs_es.py` này) chạy được mà không cần EDA — vì bus chỉ là callback list. Nhưng khi bạn deploy production distributed (Kafka, multi-service, multi-region), những thứ Lesson 31 dạy là **bắt buộc**:

- **At-least-once delivery** + idempotency: bus thực có thể publish event 2 lần khi crash → projection phải tolerate. Trong code này tôi mock bằng `_processed: set[event_id]`, nhưng EDA thật yêu cầu strategy phức tạp hơn (offset commit, exactly-once stream với Kafka transactions).
- **Dead-letter queue (DLQ)**: event mà projection xử lý fail → đưa vào DLQ, không block stream.
- **Backpressure**: write rate > projection rate → buffer/throttling/batching.
- **Saga / process manager**: nhiều aggregate liên kết qua events.
- **Eventual consistency UX**: read-your-writes, optimistic UI, version-on-response.

Khuyên: **làm Lesson 31 (EDA)** trước khi đưa CQRS+ES vào production. Trong scope học, Lesson 32 in-process này đủ giúp bạn hiểu full conceptual model — đó cũng là cách hầu hết tutorial dạy.
