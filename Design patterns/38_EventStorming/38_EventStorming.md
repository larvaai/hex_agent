# Lesson 38 — Event Storming Workshop (Case Study)
## Hippocampal Replay — Não replay sequence of events nén lại trong slow-wave sleep → neocortex extract pattern → build cognitive map. Event Storming = team replay business events trên tường → architect extract bounded context + aggregate.

---

## TÓM TẮT MỘT DÒNG

**Event Storming** (Alberto Brandolini, 2013) là *kỹ thuật workshop* phát hiện cấu trúc domain qua **sticky notes 7 màu** dán trên tường dài, đi từ **Big Picture** (chỉ event past-tense, chronological) → **Process Modeling** (thêm command/actor/policy) → **Software Design** (cluster thành aggregate/bounded context). Output: glossary + context map + aggregate proposal trong vài giờ, không code. Đây là *bộ não tập thể* discovers domain — tương đương hippocampal replay làm việc với neocortex.

> Wilson & McNaughton 1994 — multi-unit recording trong CA1: chuột chạy maze → đêm sleep → hippocampus *replay sequence* spike đã ghi, nhanh hơn 5-10x. Replay này *training* neocortex extract structure không-thời-gian. Diba & Buzsáki 2007 — replay xảy ra cả *forward* (rehearse) và *reverse* (consolidate goal trajectory). Bài học sinh học: **discovery domain không phải qua nhìn chăm chú 1 lúc, mà qua replay nhiều sequence + extract pattern**. Event Storming chính là *cognitive replay tập thể* — domain expert kể sequence sự kiện (replay), architect cluster + diễn giải (neocortical extraction).

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Bạn có 33 lesson + DDD tactical/strategic. Câu hỏi cuối: *thực tế, làm sao discover bounded context + aggregate cho 1 domain mới?* Lý thuyết nói "talk to business expert" — Event Storming là *kỹ thuật cụ thể* cho cuộc trò chuyện đó.

5 vấn đề nếu skip workshop, nhảy thẳng vào code:

1. **Glossary lệch** — dev viết `Order`, business gọi `Reservation`. Bug lan ở giao tiếp.
2. **Bounded context tự nhặt** — kiến trúc dựa trên "phép phỏng đoán" của 1 architect, không có business buy-in.
3. **Aggregate sai size** — gộp God aggregate hoặc tách quá nhỏ vì không thấy invariant context.
4. **Hot spot bị bỏ qua** — "ai approve refund?" chưa giải xong nhưng code đi tiếp → bug khi launch.
5. **Knowledge silo** — chỉ architect biết domain; team junior không nhập cảnh được.

Event Storming đóng tất cả qua **workshop 4-8 giờ** với:
- 1 phòng + tường dài (real life) hoặc Miro board (remote).
- ~7-15 người: business expert + dev + QA + UX + product owner.
- ~500 sticky notes 7 màu.
- 1 facilitator.

Output: glossary, context map, aggregate proposal, hot spot list, *team alignment*.

### 1.2. Định nghĩa và 3 levels

Brandolini phân chia workshop thành 3 level tăng dần resolution:

**Level 1 — Big Picture**:
- Mục tiêu: discover domain end-to-end qua *event timeline*.
- Chỉ dùng **Orange** sticky (event past-tense).
- Sắp xếp chronological L→R.
- ~50-200 sticky cho 1 domain phức tạp.
- Thời gian: 2 giờ.

**Level 2 — Process Modeling**:
- Mục tiêu: thêm structure quanh event (ai? gì trigger? rule?).
- Thêm:
  - **Blue** (Command — imperative)
  - **Yellow** (Actor)
  - **Pink** (External system)
  - **Purple** (Policy — automated reaction)
  - **Red** (Hot spot, question)
- Thời gian: 2 giờ.

**Level 3 — Software Design**:
- Mục tiêu: tìm aggregate + bounded context.
- Thêm:
  - **Light yellow** (Aggregate — noun, big sticky)
  - **Green** (Read model — view, dashboard)
- Cluster events around aggregate; draw boundaries → bounded context.
- Thời gian: 2-4 giờ.

> Không phải workshop nào cũng làm cả 3 level. Level 1 đủ cho *domain discovery*. Level 2 đủ cho *process improvement*. Level 3 cần khi sắp build software.

### 1.3. 7 màu sticky note — semantic

| Màu | Loại | Câu hỏi trả lời | Vd Ellumm |
|-----|------|------------------|-----------|
| **Orange** | Domain Event | "Đã xảy ra X tại T" | `QuizSubmitted`, `ScoreCalculated`, `BadgeAwarded` |
| **Blue** | Command | "Hãy làm Y" | `SubmitQuiz`, `Grade`, `Finalize` |
| **Yellow** | Actor | "Ai thực hiện?" | `Student`, `Teacher`, `Admin`, `AutoScorer` |
| **Pink** | External system | "Hệ ngoài nào gọi vào / được gọi?" | `Auth0`, `SendGrid`, `Stripe` |
| **Purple** | Policy | "Quy tắc tự động: when X then Y" | "When ScoreCalculated → AwardBadge if >= 90" |
| **Green** | Read model | "View/dashboard hiển thị gì?" | `LeaderboardView`, `StudentDashboard` |
| **Red** | Hot spot | "Chỗ còn unresolved" | "Ai approve refund?", "Ngôn ngữ Submission là gì?" |

Convention thêm:
- **Light yellow / cream** (big sticky) = **Aggregate** (noun: Submission, Order).
- **Light green** = **External actor** (vs **yellow** internal).
- Drawn boundary (thick line) = **Bounded Context**.

### 1.4. Workshop choreography

```
SETUP (5 min)
   - Wall lined with paper (real) or Miro board (remote)
   - Sticky note packs distributed
   - Facilitator: business expert + 5-10 dev/PO/QA

LEVEL 1 — BIG PICTURE (60-120 min)
   Phase 1: Chaotic Exploration (20 min)
     - Everyone writes events on orange stickies, sticks on wall
     - No order, just throw events
   Phase 2: Timeline Enforcement (20 min)
     - Move events chronologically L→R
     - Facilitator asks "what comes before X?" "what comes after Y?"
   Phase 3: Pivotal Events (20 min)
     - Identify "phase change" events (e.g. OrderPlaced, PaymentReceived)
     - These often = bounded context boundaries
   Phase 4: Walkthrough (20 min)
     - Business expert tells the story end-to-end using events
     - Team challenges, fills gaps

LEVEL 2 — PROCESS MODELING (60-120 min)
   - Add Blue (commands) BEFORE each event
   - Add Yellow (actor) issuing each command
   - Add Pink (external) where applicable
   - Add Purple (policy) for automated reactions
   - Add Red (hot spot) for unresolved
   - Facilitator runs the timeline like a movie

LEVEL 3 — SOFTWARE DESIGN (60-240 min)
   - Identify nouns repeated across events → aggregate candidates
   - Big sticky for aggregate: "Submission"
   - Group events around aggregate
   - Identify *invariants*: "this rule must always be true within aggregate"
   - Draw bounded context boundaries
   - Map context relationships (Lesson 34 — Partnership, OHS, ACL...)
   - List read models needed

OUTPUT
   - Photograph wall
   - Transcribe to digital glossary
   - Draft context map
   - List of aggregates with invariants
   - List of hot spots (for follow-up workshops)
```

### 1.5. Neuroscience — Hippocampal replay

**Wilson & McNaughton 1994** — Nature paper *"Reactivation of hippocampal ensemble memories during sleep"*:
- Multi-unit recording trong CA1 rat chạy maze.
- Trong sleep (slow-wave + REM), *same neural ensembles fire again* — replay sequence chạy maze, nhưng nén 5-10x.

**Diba & Buzsáki 2007** — forward + reverse replay:
- Forward replay (rehearsal): prepare future action.
- Reverse replay (consolidation): just after reward, replay backward → strengthen path.

**Why does this map to Event Storming?**

| Hippocampus + replay | Event Storming workshop |
|----------------------|--------------------------|
| Episodic memory of "what happened where" | Domain events on wall, chronological |
| Compressed replay 5-10x | Workshop walks domain in hours instead of months observation |
| Neocortex consolidates pattern | Architect extracts bounded contexts + aggregates |
| Sharp wave ripples during replay = compressed information transfer | Sticky note walls *transfer knowledge from business expert → team* |
| Place cells encode "where" | Sticky notes encode "what happened in process timeline" |
| Time cells encode "when in sequence" | Chronological ordering of events L→R |
| Cognitive map emerges from many replays | Domain map emerges from multiple workshop iterations |

→ Event Storming là *workshop formalization* của một cơ chế não sẵn có. Đó là lý do workshop "tự nhiên cảm thấy đúng" cho người tham gia: chính bộ não họ đang làm consolidation in real time.

### 1.6. So sánh với patterns đã học

| | Lesson trước | Event Storming |
|---|---|---|
| Lesson 24 SRP | "1 lý do thay đổi" — class-level | Workshop *discover* 1 lý do thay đổi qua replay |
| Lesson 31 EDA | Event bus runtime | Event Storming workshop ở design-time |
| Lesson 32 CQRS+ES | Lưu event làm SoT | Workshop *xác định* event nào quan trọng |
| Lesson 34 Bounded Context | Pattern strategic | Workshop *discover* bounded context |
| Lesson 35 Aggregate | Pattern tactical | Workshop *discover* aggregate |
| Lesson 36 Entity/VO/Event | Định nghĩa | Workshop *gắn nhãn* qua sticky color |
| Lesson 37 Repository/Factory/Spec | 3 supporting | Workshop *propose* (chưa code) |

> Event Storming *không phải* là pattern code — là *kỹ thuật khám phá*. Lesson 38 đặc biệt: workshop output là các *artifact thiết kế*, sau đó dùng Lesson 34-37 để implement.

---

## MỨC 2 — CẤU TRÚC

### 2.1. Data model của workshop

```
Sticky Note:
    id:            UUID
    color:         Color (orange/blue/yellow/pink/purple/green/red)
    text:          str
    position:      (x, y)  -- timeline position
    author:        str
    related_to:    List[StickyId]  -- linked notes

Wall:
    notes:         List[Sticky]
    boundaries:    List[(Polygon, BoundedContextName)]

3-Phase progression:
    Phase 1 (Big Picture): only orange
    Phase 2 (Process):     + blue, yellow, pink, purple, red
    Phase 3 (Software):    + light yellow (aggregate), green (read model), + boundary
```

### 2.2. Heuristics để discover từ wall

**Discovering Aggregate**:
- Nouns repeated trong > 5 event ("Submission" appears in `SubmissionCreated`, `SubmissionGraded`, `SubmissionFinalized`, ...).
- Events có *consistency boundary* (cần atomic).
- Có invariants ("score must be in [0, max]").

**Discovering Bounded Context**:
- Pivotal events (state phase change).
- Cluster of events around same set of nouns.
- Actor change (different team owns).
- Term có nghĩa khác ("User" trong Order context ≠ "User" trong Catalog context).

**Discovering Hot Spot**:
- Question marks "ai làm cái này?".
- Disagreement giữa expert ("teacher có thể override score không?").
- Missing actor (event happen but no actor → automation? policy?).

### 2.3. Anti-patterns workshop

| Anti-pattern | Mô tả | Cách tránh |
|--------------|-------|------------|
| **Mọi sticky là Orange** | Skip command/actor/policy → workshop dừng ở level 1 | Force level 2 sau 1 giờ |
| **Future-tense event** | "WillBeSubmitted" → đó là intent/command, không event | Facilitator gò vào past-tense |
| **Sticky = code class** | Dev viết `SubmissionDTO` thay vì `SubmissionGraded` | Insist on business language |
| **No hot spot** | Mọi câu trả lời "settle" → workshop superficial | Facilitator probe contradictions |
| **Architect dominates** | Business expert chỉ ngồi xem → workshop = solo design | Facilitator chuyển micro |
| **Skip pivotal events** | Không identify state-phase change | Facilitator giơ phase question "what marks transition?" |
| **Workshop 1 lần là xong** | Domain complex cần 3-5 sessions | Plan iteration |
| **No photo + transcript** | Output vanish after wall removed | Photo + glossary export trong 1 giờ sau |

### 2.4. Các invariants của Event Storming output

1. **Event past-tense**, command imperative, policy when-then.
2. **Mỗi command có ít nhất 1 actor** (yellow) hoặc 1 policy (purple).
3. **Mỗi event được trigger bởi command hoặc policy** (không tự phát).
4. **Mỗi aggregate có ≥ 3 events** (nếu < 3, có thể nên merge vào aggregate khác).
5. **Mỗi bounded context có ≥ 1 aggregate + ≥ 1 read model**.

---

## MỨC 3 — PSEUDOCODE + WORKSHOP RUN-THROUGH

### 3.1. Pseudocode

```
class StickyNote:
    color: Color (orange/blue/yellow/pink/purple/green/red)
    text: str
    position: (x, y)
    related_to: List[StickyId]

class Wall:
    notes: List[StickyNote]
    add(note)
    chronological(): List[StickyNote sorted by x]
    by_color(c): List[StickyNote where color=c]
    cluster_events_by_aggregate(): Dict[Aggregate, List[Event]]
    detect_bounded_contexts(): List[Boundary]
    hot_spots(): List[StickyNote where color=Red]

# 3-phase progression
def run_workshop(domain_name):
    wall = Wall()

    # Phase 1
    big_picture(wall)        # only orange
    enforce_timeline(wall)
    identify_pivotal(wall)

    # Phase 2
    process_modeling(wall)   # + blue, yellow, pink, purple, red
    walk_through_movie(wall)

    # Phase 3
    software_design(wall)    # + aggregate, read model, boundary
    cluster_aggregate(wall)
    draw_context_map(wall)

    return WorkshopOutput(
        glossary=...,
        context_map=...,
        aggregates=...,
        hot_spots=...,
    )

# Analyzer
def discover_aggregates(wall):
    nouns = extract_nouns(wall.events)
    candidates = nouns where appearances >= 3
    return [(noun, events_for(noun)) for noun in candidates]

def discover_bounded_contexts(wall):
    pivotal = wall.pivotal_events()
    clusters = cluster_events_by_actor_similarity(wall)
    return propose_boundaries(pivotal, clusters)
```

### 3.2. Case study Ellumm — preview

File `38_event_storming.py` đi kèm chạy 1 workshop hoàn chỉnh:

**Phase 1 — Big Picture**: 20+ event sticky notes chronological.

```
Account → QuizPublished → QuizPreviewed → SubmissionStarted →
AnswersSubmitted → ScoreCalculated → BadgeAwarded → ReceiptSent →
LeaderboardUpdated → SubscriptionRenewed → TeacherFlagged →
ScoreCorrected → SubmissionFinalized
```

**Phase 2 — Process**: thêm commands, actors, policies, hot spots.

```
Student issues SubmitQuiz → AnswersSubmitted (event)
Policy: "When ScoreCalculated AND score >= 90 → AwardBadge"
External: SendGrid (pink)
Hot spot (red): "Can teacher override AutoScorer?"
Hot spot (red): "What is 'finalize' — auto after 24h or manual?"
```

**Phase 3 — Software Design**: cluster vào aggregate + bounded context.

```
Bounded Context: Quiz Authoring
  Aggregate: Quiz (events: Created, Published, Retired)
  
Bounded Context: Submission
  Aggregate: Submission (events: Started, AnswersSubmitted, Graded, Finalized)
  Aggregate: Attempt (internal entity Lesson 35)
  
Bounded Context: Leaderboard
  Read model: LeaderboardView (event consumed: ScoreCalculated)
  
Bounded Context: Notification
  Aggregate: Recipient (Lesson 34)
  Read model: Receipt history
  
Bounded Context: Subscription
  Aggregate: Subscription (events: Started, Renewed, Cancelled)
```

Output từ Python sẽ:
- Hiển thị wall state mỗi phase.
- Detect aggregate candidates.
- Propose bounded contexts.
- List hot spots cần follow-up.
- Generate glossary.

---

## NĂM CHIỀU SO SÁNH (trong não vs trong workshop)

| Chiều | Hippocampal replay | Event Storming workshop |
|-------|---------------------|--------------------------|
| **Cấu tạo** | CA1 place cells + CA3 pattern completion + DG pattern separation | Sticky notes 7 màu trên tường + facilitator + diverse team |
| **Vị trí** | Trong hippocampus + entorhinal during sleep | Tường dài 5-10m, 4-8 giờ, team họp |
| **Chức năng** | Compress + replay sequence để consolidate vào neocortex | Compress business knowledge + cluster vào aggregate/BC |
| **Kết nối** | HC → neocortex sharp-wave ripples; bidirectional dialogue | Business expert ↔ dev ↔ architect; sticky note exchange |
| **Ý nghĩa** | Khám phá structure không qua observation mà qua replay | Domain discovery qua tập thể, không qua solo architect |

---

## BA VÍ DỤ

### Ví dụ 1 — Vận hành thường (happy path workshop)

Workshop Ellumm 4 giờ với 8 người:
- 1 product owner.
- 1 senior teacher (business expert).
- 2 dev senior.
- 1 architect (facilitator).
- 1 QA.
- 1 UX.
- 1 customer support.

**Outcome sau 4 giờ**:
- 87 sticky notes total (45 events, 22 commands, 8 actors, 4 policies, 8 hot spots).
- 4 bounded context proposal: Quiz Authoring, Submission, Notification, Subscription.
- 6 aggregate proposal với invariant list.
- 8 hot spot cần follow-up workshop (2 buổi nữa).
- Glossary 50+ term.
- Photo + Miro export.

Team chuyển sang code với *alignment* — không có ai hiểu lầm "what Submission means".

### Ví dụ 2 — Hỏng / vi phạm (failure modes)

**Vi phạm A — Skip workshop, architect tự thiết kế**:
```
Architect designs 5 bounded contexts solo.
2 sprint sau: business says "wait, Order ≠ Reservation".
Refactor 8 sprint.
```
→ ROI workshop âm 1000% so với chi phí 4 giờ.

**Vi phạm B — Workshop 1 lần là xong**:
```
4 giờ workshop, "done"
Implement 6 tháng → discover Submission có sub-state "TeacherReview"
chưa được model. Aggregate sai.
```
→ Plan 3-5 iteration workshops với increasing resolution.

**Vi phạm C — Architect dominates**:
```
Architect ghi 80% sticky. Business expert ngồi nodding.
Output = architect's bias, không phải domain reality.
```
→ Facilitator monitor talk-time + force expert speak.

**Vi phạm D — No transcription**:
```
Wall thrown away after workshop. 2 tuần sau, dev quên rule purple "if score >= 90".
```
→ Photo trong 1 giờ. Glossary export trong 1 ngày.

**Vi phạm E — Future-tense events**:
```
Sticky: "PaymentWillBeReceived", "OrderShouldBeShipped"
→ Đó là intent, không phải event. Workshop bị blur giữa state machine và process.
```
→ Facilitator enforce "đã xảy ra" past-tense.

### Ví dụ 3 — Ứng dụng Ellumm (file kèm)

`38_event_storming.py` simulate 1 workshop end-to-end với 20+ event, 10 command, 5 actor, 3 policy, 4 hot spot. Output:
- Phase progression visual.
- Aggregate discovery automatic.
- Bounded context proposal.
- Hot spot follow-up list.
- Glossary draft.

---

## MỨC ARCHITECT — TRADE-OFFS & ANTI-PATTERNS

### Khi nào DÙNG Event Storming

- Domain mới, team chưa nắm.
- Refactor monolith → cần discover boundary.
- Domain expert ≠ dev (cần align language).
- Migrating từ system legacy.
- Onboarding senior team mới cho domain phức tạp.

### Khi nào KHÔNG

- Domain trivial (CRUD pure).
- Team đã domain expert (architect = business expert).
- Prototype < 1 tuần.
- Khi không có business expert nào sẵn sàng đầu tư 4 giờ.

### Trade-offs

| Trục | Được | Mất |
|------|------|-----|
| **Time** | Save 8-12 sprint sai design | 4-12 giờ workshop + facilitation prep |
| **Team alignment** | Ai cũng hiểu cùng | Cần coordinate calendar 8 người |
| **Visibility** | Hot spot, contradiction visible | Có thể uncover bug-có-thật trong current process |
| **Documentation** | Glossary, context map output | Cần transcribe/digitize |
| **Iteration** | Easy update với new workshop | Cần buy-in để rerun |

### Tools

| Tool | Use case |
|------|----------|
| **Miro / Mural / FigJam** | Remote workshop |
| **Real sticky on wall** | In-person, prefer khi possible |
| **Whimsical** | Lite version với template |
| **Plant UML / Mermaid** | Post-workshop diagram |
| **EventModeling.org tool** | Direct mapping sticky → event store |

### Checklist trước workshop

- [ ] Có business expert sẵn sàng dành 4 giờ?
- [ ] Có dev + QA + UX + PO tham gia?
- [ ] Có facilitator độc lập (không phải designer của hệ)?
- [ ] Tường / Miro board sẵn?
- [ ] Sticky note 7 màu chuẩn bị?
- [ ] Đã giải thích 3-level + 7 màu cho team trước workshop?
- [ ] Có camera / export plan?

### Checklist sau workshop

- [ ] Photo wall 4-5 góc?
- [ ] Glossary transcribe trong 24h?
- [ ] Context map draft trong 48h?
- [ ] Hot spot list assigned owner?
- [ ] Next workshop scheduled nếu cần?

---

## BÀI TẬP — 4 MỨC

### Mức 1 — Cơ bản (1 giờ)

Lấy 1 domain bạn quen (Ellumm hoặc work của bạn). Tự ngồi viết **30 sticky orange (event past-tense)** chronological cho 1 user journey end-to-end. Không cần command/actor — chỉ event.

Output: timeline event 30 sticky.

### Mức 2 — Trung bình (2 giờ)

Chạy *self-event-storming* phase 2 trên timeline mức 1:
- Thêm blue command trước mỗi event.
- Thêm yellow actor.
- Thêm pink external.
- Thêm purple policy (where applicable).
- Thêm red hot spot.

Output: phase 2 wall + danh sách hot spot (≥ 3).

### Mức 3 — Khó (architect, 4 giờ)

Tự chạy *full workshop self* với 3-5 đồng nghiệp / bạn thật, 1 domain "nhỏ" (todo app, recipe site, etc.):
- 1 giờ phase 1.
- 1 giờ phase 2.
- 2 giờ phase 3.

Output deliverables:
- Photo wall hoặc Miro export.
- Glossary 30+ term.
- Context map proposal 3+ BC.
- Aggregate proposal mỗi BC.
- Hot spot list assigned owner.

Reflection 500 word: "what surprised you?"

### Mức 4 — Mở rộng neuro (2 giờ tự do)

Đọc paper Wilson-McNaughton 1994 (Nature abstract + figure 1) hoặc Diba-Buzsáki 2007. Trả lời:

1. **Forward vs reverse replay**: hippocampus replay maze cả 2 chiều. Tương đương Event Storming: có nên *cũng* "reverse walk" timeline (từ goal-state đi ngược về initial-state)? Khi nào hữu ích?

2. **Sharp-wave ripple compression 5-10x**: replay nhanh hơn awake experience. Trong workshop, có nên *force compression* — yêu cầu kể domain trong 5 phút trước khi vào sticky? Lợi/hại?

3. **Sleep deprivation impair consolidation**: chuột không ngủ → không nhớ maze. Trong code: dev không có "time to consolidate" giữa workshop và code (deadline ép) → output workshop có lan vào code đúng không? Implication cho project planning.

---

## ĐỒ HOẠ TỔNG KẾT

```
              EVENT STORMING — 3 LEVELS
   ═══════════════════════════════════════════════════════════
   LEVEL 1 — BIG PICTURE        chronological events only
                                ▼
   ┌────────────────────────────────────────────────────┐
   │  Orange Orange Orange Orange Orange Orange Orange  │
   │   (events past-tense, L→R chronological)            │
   └────────────────────────────────────────────────────┘

   LEVEL 2 — PROCESS MODELING   + commands, actors, policies
                                ▼
   ┌────────────────────────────────────────────────────┐
   │  Yellow → Blue → Orange    Yellow → Blue → Orange  │
   │  Actor   Cmd     Event     Actor   Cmd     Event   │
   │              ↑Purple Policy              ↑Red Hot  │
   │              ↓Pink External                         │
   └────────────────────────────────────────────────────┘

   LEVEL 3 — SOFTWARE DESIGN    + aggregates, bounded contexts
                                ▼
   ┌──────── Bounded Context: Submission ──────────┐
   │  ┌─ Aggregate: Submission ──────────────────┐ │
   │  │  Created → Submitted → Graded → Finalized│ │
   │  └──────────────────────────────────────────┘ │
   │  Read Model: SubmissionDashboard (green)       │
   └────────────────────────────────────────────────┘

   Output: glossary + context map + aggregate proposal + hot spots
   Brain analog: hippocampal replay → neocortical consolidation
```

> **Tóm lại**: Event Storming là *discovery technique* bằng workshop, không phải pattern code. 3 level tăng resolution. 7 màu sticky encode semantic. Output là *artifact thiết kế* để team build. Brain analog: hippocampal replay làm consolidation domain → đó là cơ chế tự nhiên ta đang formalize trong workshop. Workshop tốt = 80% solo work của architect tránh được.

---

## TIẾP THEO

- **Lesson 39** — Distributed DDD: cross-context consistency + Saga inside vs across BC.
- **Lesson 40** — Ubiquitous Language case study: glossary management + rename refactoring.
