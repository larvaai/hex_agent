# Lesson 40 — Ubiquitous Language Case Study
## Wernicke + Broca + Arcuate Fasciculus — Não có 2 vùng cho semantics (Wernicke) + production (Broca) + connection (arcuate). Bilingual brain = mỗi context có UL riêng + code-switching qua ACL.

---

## TÓM TẮT MỘT DÒNG

**Ubiquitous Language** là language chung *giữa business expert và developer*, **strict within a bounded context**. Mỗi BC có *glossary riêng*. Cross-BC dùng *Published Language* (Lesson 34). Rename trong UL không trivial — impact lan ra code, test, DB, event, docs, UI. Lesson này dạy: maintain glossary as code, detect language drift, plan rename migration impact across all touch points.

> Carl Wernicke 1874 (BA22) — semantic understanding; Paul Broca 1861 (BA44/45) — production; Norman Geschwind 1965 — arcuate fasciculus connects them. Conduction aphasia khi đứt arcuate: hiểu được, không lặp lại được. *Bilingual brain* có thể switch giữa 2 UL — tiếng Việt và English — *trong cùng cuộc trò chuyện*, dùng same neural circuits nhưng *toggle context*. Code-switching activates dlPFC + anterior cingulate. Semantic dementia (FTLD, atrophy anterior temporal lobe) — concept gradually loses precision, anomia, semantic drift. Khi *codebase* mất precision về term ("User" nghĩa gì?"), đó là semantic dementia của project. Lesson này dạy giữ vocabulary sharp.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Lesson 34 (Bounded Context) định nghĩa rằng UL có boundary. Lesson 40 hỏi: *thực tế làm sao maintain UL qua thời gian*?

5 vấn đề:

1. **Term overload across BCs**: "User" có nghĩa khác trong Quiz Authoring (Author) vs Submission (Student) vs Notification (Recipient). Lesson 34 đã xử lý — ở đây nhấn vào *glossary management*.

2. **Language drift trong cùng BC**: code dùng `Submission`, test dùng `Attempt`, doc dùng `QuizSession`, meeting dùng `Try`. 4 từ, 1 concept — *semantic dementia của codebase*.

3. **Rename refactoring đắt**: business expert nói "We'll call it Attempt not Submission". Impact:
   - Code: 50+ files (entity class, methods, repository, factory, spec).
   - Test: 30+ test files.
   - DB: table name + column references + migration script.
   - Events: `SubmissionGraded` → `AttemptGraded` — but Published Language event là external contract, downstream BC vẫn dùng tên cũ → cần version transition.
   - Docs: API doc, ADR, glossary, README, comments.
   - UI: button labels, error messages, log fields.
   - Knowledge base: Slack history, Jira tickets, runbook.

4. **No glossary**: term mới được thêm vào code, không thêm vào glossary. 6 tháng sau, new dev không biết "Attempt" khác "Submission" thế nào.

5. **Cross-BC translation invisible**: 2 BC dùng cùng từ "Score" cho 2 nghĩa khác (Submission's score = raw points; Leaderboard's score = ranking value). ACL không document. Bug khi serialize giữa BC.

### 1.2. Định nghĩa Ubiquitous Language

**Eric Evans 2003**, *DDD: Tackling Complexity in the Heart of Software*:

> *"The use of the model as the backbone of a language. Commit the team to exercising that language relentlessly in all communication within the team and in the code. Use the same language in diagrams, writing, and especially speech."*

3 đặc điểm:
1. **Shared between business expert + dev**: không có "tech terms vs business terms" — chỉ 1 vocabulary.
2. **Strict scope = 1 BC**: UL không phải universal — mỗi BC có own.
3. **Lives in code, in docs, in conversation**: cùng từ ở 3 nơi.

### 1.3. Glossary as code

Pattern: maintain glossary là *first-class artifact*, không phải Confluence page bị bỏ quên.

```python
@dataclass
class Term:
    name: str
    definition: str
    since: date            # when entered vocabulary
    until: Optional[date]  # if retired
    bounded_context: str
    synonyms: List[str]    # deprecated alternatives
    used_by: List[str]     # entities/events/methods that use this term
    examples: List[str]

class BCGlossary:
    bc_name: str
    terms: Dict[str, Term]
    add(term)
    deprecate(name, replaced_by)
    rename(old, new)         # tracks history
    drift_check(source_code)
```

Glossary có:
- **Per-BC instance** (UL của BC).
- **Cross-BC translation table** (when terms collide).
- **Versioned** (term thay đổi theo thời gian).
- **Validated against code** (CI: every entity class must have glossary entry).

### 1.4. Rename refactoring impact

Khi business expert đề nghị rename `Submission → Attempt`:

```
IMPACT MATRIX
────────────────────────────────────────────────────────────
LAYER             | OLD                  | NEW
────────────────────────────────────────────────────────────
Code class        | class Submission     | class Attempt
Code methods      | submit_quiz()        | start_attempt()
                  | create_submission()  | start_attempt()
                  | grade_submission()   | grade_attempt()
Repository        | ISubmissionRepository| IAttemptRepository
Factory           | SubmissionFactory    | AttemptFactory
Domain events     | SubmissionGraded     | AttemptGraded
Test names        | test_submission_*    | test_attempt_*
DB table          | submissions          | attempts (migration script)
DB column         | submission_id        | attempt_id
Published Language| SubmissionGradedV1   | SubmissionGradedV1 (kept!) + AttemptGradedV2
                  |                      | (downstream BCs need V1 transition period)
ACL inputs        | SubscriptionGraded   | both V1 + V2 acceptable in 6 months
API endpoint      | POST /submissions    | POST /attempts (with /submissions redirect)
API response      | {"submission_id":..} | {"attempt_id":..} (or both during deprecation)
UI button         | "Submit Quiz"        | "Start Attempt"
Error message     | "Submission failed"  | "Attempt failed"
Log fields        | submission_id        | attempt_id (log search query updates)
Glossary entry    | Submission           | Submission (deprecated) → Attempt
ADR              | (new ADR explaining rename)
Slack channel    | #submissions         | #attempts
────────────────────────────────────────────────────────────
```

Rename trong **1 BC** không nên propagate sang **other BCs** automatically — cross-BC integration qua Published Language event, có versioned schema (Lesson 31).

### 1.5. Neuroscience — Language in brain

**(a) Wernicke (BA22) — semantic understanding**:
- Posterior superior temporal gyrus.
- Damage: Wernicke's aphasia — fluent speech nhưng vô nghĩa ("word salad"); cannot understand.
- Tương đương: business expert mất khả năng *hiểu* requirements → speak fluent code-talk nhưng không nắm domain.

**(b) Broca (BA44/45) — production**:
- Inferior frontal gyrus (left).
- Damage: Broca's aphasia — telegraphic speech, slow, but *understands*.
- Tương đương: dev hiểu domain nhưng cannot articulate clearly to non-tech.

**(c) Arcuate fasciculus — connection**:
- White matter tract from Wernicke to Broca.
- Damage: *conduction aphasia* — hiểu được, nói được tự do, nhưng *không lặp lại được* phrase mới nghe.
- Tương đương: workshop discusses term, dev hears it, dev's code uses different word — connection broken.

**(d) Bilingual brain + code-switching**:
- Bilingual person có 2 mental dictionaries.
- Activates dlPFC + anterior cingulate khi switch language.
- Each language is *contextually triggered* — "speak Vietnamese to mom, English at work".
- Tương đương: developer working with 4 BCs ↔ knows 4 ULs, switches based on which BC editing.

**(e) Semantic dementia (FTLD)**:
- Frontotemporal lobar degeneration, atrophy left anterior temporal.
- Anomia: cannot name objects.
- Semantic drift: "dog" might come out as "animal", "thing", "this one".
- Tương đương: codebase mất precision — new dev hỏi "what's a Submission?", senior dev lúng túng, no glossary, 3 different definitions emerge.

### 1.6. So sánh với patterns đã học

| Pattern | Lesson | Quan hệ với UL |
|---------|--------|-----------------|
| Bounded Context (34) | 34 | UL có boundary = BC boundary |
| Anti-Corruption Layer (34) | 34 | ACL translates UL of BC A → UL of BC B |
| Published Language (34) | 34 | Cross-BC vocabulary, versioned |
| Domain Event (31, 36) | 31, 36 | Event names use UL of producing BC |
| Aggregate (35) | 35 | AR named in UL (Submission, Order) |
| Repository/Factory/Spec (37) | 37 | Each named after AR's UL |
| Event Storming (38) | 38 | Workshop output IS UL discovery |

---

## MỨC 2 — CẤU TRÚC

### 2.1. Glossary structure

```
Per-BC glossary:
   BCName
   ├── Terms[]
   │     ├── name, definition, since, until?
   │     ├── synonyms (deprecated)
   │     ├── used_by (entities/events/methods)
   │     └── examples
   ├── Cross-BC translation
   │     └── For each cross-term: BC_A.term ↔ BC_B.term

Global glossary:
   ├── All BCs
   ├── Term collision detection
   └── Migration history
```

### 2.2. Language drift detection

Heuristic dò *drift* (term inconsistency):
- grep code cho từ deprecated (synonym still present).
- compare class names vs glossary entries.
- find terms used in code but not in glossary (= undefined).
- find terms in glossary but not in code (= orphaned).

### 2.3. Rename migration plan

5 phase rename:

```
PHASE 1: Deprecate old name (week 1)
   - Add new term in glossary as preferred.
   - Mark old term as deprecated.
   - Code still uses old name.
   - ADR documenting rename rationale.

PHASE 2: Dual support (week 2-4)
   - New API endpoints aliasing old.
   - Database column: add new (NULL); backfill; keep old.
   - Event: both V1 (old name) + V2 (new name) published.
   - Update internal code references to new name.
   - Tests updated.

PHASE 3: Migration window (month 2-3)
   - Downstream BCs upgrade consumers V1 → V2.
   - Monitor: which consumers still on V1?
   - UI updates to new term.
   - Log fields updated.

PHASE 4: Remove old (month 4)
   - Drop old API endpoints.
   - Drop old DB columns.
   - Stop publishing V1 events.
   - Remove deprecated synonyms from glossary.

PHASE 5: Cleanup (month 5)
   - Code review for stragglers.
   - Update Slack channels, ticket templates.
   - Glossary marks old term `until=today`.
```

### 2.4. Cross-BC translation table

Khi term nhập 2 BC với nghĩa khác:

| BC A | BC B | Translation |
|------|------|-------------|
| Submission.User (Student) | Notification.User (Recipient) | ACL: to_notification_recipient(student) |
| Submission.Score (raw points) | Leaderboard.Score (ranking value) | ACL: derive ranking_value(raw_points) |
| Quiz.Question (with answer) | Submission.Question (without answer) | ACL: hide_correct_answer() |

ACL implementation responsibility: translate one UL → another. Document trong ACL file + glossary cross-context section.

### 2.5. 5 invariants

1. **Mỗi class/method tên = 1 term trong glossary BC tương ứng**.
2. **Cross-BC term collision phải có translation entry**.
3. **Rename qua ≥ 5 phase, không big-bang**.
4. **Published Language event versioned** trong rename transition.
5. **Glossary commit cùng PR code change** (CI gate).

---

## MỨC 3 — PSEUDOCODE + CASE STUDY

### 3.1. Pseudocode

```
# Glossary as code
@dataclass Term:
    name, definition, since, until?, bounded_context, synonyms[], used_by[], examples[]

class BCGlossary:
    bc_name: str
    terms: Dict[name, Term]
    add(term)
    deprecate(name, replaced_by, until)
    rename(old, new)               # new term inherits definition; old marked deprecated
    drift_check(code_str) → DriftReport
    impact_of_rename(old, new) → ImpactReport

class GlobalGlossary:
    bcs: Dict[name, BCGlossary]
    translations: Dict[(BC_A, term_A), (BC_B, term_B)]
    detect_term_collision() → List[Collision]

# Rename impact analyzer
def analyze_rename_impact(old: str, new: str, bc: str) -> MigrationPlan:
    report = []
    # Layer 1: code files
    affected_files = grep_for(old, in_paths=[f"src/{bc}/"])
    # Layer 2: tests
    affected_tests = grep_for(old, in_paths=[f"tests/{bc}/"])
    # Layer 3: events
    affected_events = find_events_named(old)
    # Layer 4: DB
    affected_columns = find_columns_referencing(old)
    # Layer 5: docs
    affected_docs = grep_for(old, in_paths=["docs/", "api/"])
    # Layer 6: cross-BC (published events)
    cross_bc_consumers = find_consumers_of(old + "_event")
    return MigrationPlan(phases=...)

# Case study: Submission → Attempt
plan = analyze_rename_impact("Submission", "Attempt", bc="Submission Context")
output: 5-phase migration plan with timeline
```

### 3.2. Case study Ellumm

File `40_ubiquitous_language.py` đi kèm chạy:

**Phase 1 — Build 4 BC glossaries** (recap Lesson 34):
- Quiz Authoring: Quiz, Question, Author
- Submission: Submission, Attempt, Score, Student
- Leaderboard: Ranking, Position
- Notification: Recipient, Receipt, Channel

**Phase 2 — Detect cross-BC term collision**:
- "User" appears in 3 BCs với 3 nghĩa khác.
- "Score" appears in 2 BCs với 2 nghĩa khác.

**Phase 3 — Language drift detection**:
- Code snippet với mixed terms (Submission + Attempt + Try).
- Detector flags inconsistency.

**Phase 4 — Rename impact: Submission → Attempt**:
- Affected: 15+ class/method names trong Submission BC.
- 3 published events versioned.
- 2 downstream BCs unaffected (ACL handles).
- Generate 5-phase migration plan.

**Phase 5 — Verify post-rename**:
- Glossary update.
- Drift check passes.
- Cross-BC translation entries updated.

---

## NĂM CHIỀU SO SÁNH (in não vs in code)

| Chiều | Wernicke/Broca + bilingual brain | Ubiquitous Language |
|-------|----------------------------------|---------------------|
| **Cấu tạo** | Wernicke (BA22), Broca (BA44/45), arcuate fasciculus | Per-BC glossary + cross-BC translation + drift detector |
| **Vị trí** | Cortex left hemisphere; bilingual activate dlPFC | Glossary as code file (`.md` or `.yaml`); ACL in adapter folder |
| **Chức năng** | Encode + produce + connect semantic concept | Maintain shared vocabulary; detect drift; manage rename |
| **Kết nối** | Concept network (synonym, hypernym); arcuate connects regions | Cross-BC translation table; event Published Language |
| **Ý nghĩa** | Semantic dementia khi mất; conduction aphasia khi connection vỡ | Codebase mất precision khi không có UL; bugs khi cross-BC term ambiguous |

---

## BA VÍ DỤ

### Ví dụ 1 — Vận hành thường (healthy UL)

Code có:
- Mỗi class name match 1 glossary entry.
- Mỗi entry có definition + since date + used_by.
- Cross-BC translation documented.
- New dev đọc glossary trước khi nhảy vào code.
- Quarterly review of glossary cùng business expert.

Kết quả:
- Onboarding 2 tuần thay vì 6 tuần.
- Bug rate giảm 30% (term ambiguity bugs).
- Business expert tham gia code review (đọc được code names).

### Ví dụ 2 — Hỏng / vi phạm

**Vi phạm A — Term overload không document**:
```python
# BC: Submission
class Score: ...
# BC: Leaderboard
class Score: ...
# Cross-BC event:
@dataclass class SubmissionGraded:
    score: Score              # ← which Score?
```
→ Bug ngay khi serialize.
→ Đúng: explicit naming `SubmissionScore` vs `LeaderboardScore` hoặc ACL translation.

**Vi phạm B — Language drift trong cùng BC**:
```python
class Submission: ...
class AttemptHistory: ...        # ← "Attempt" used as synonym
def begin_quiz_session(): ...    # ← yet another synonym
```
→ New dev confused.
→ Đúng: choose 1 term, deprecate others trong glossary.

**Vi phạm C — Rename big-bang**:
```
Day 0: rename Submission → Attempt in 50 files simultaneously.
Day 0: downstream BCs break because Published Language event renamed.
Day 0: 3-day production fire.
```
→ Đúng: 5-phase với dual-support window.

**Vi phạm D — No glossary**:
```python
class Cohort: ...    # new term, no definition anywhere
# Senior dev: "I think it's a group of students starting same week"
# Junior dev: "I thought it was the quiz batch"
# QA: "Isn't it the leaderboard timeframe?"
```
→ Đúng: glossary entry required với class create.

**Vi phạm E — Glossary out of sync with code**:
```
Glossary: "Submission = the act of submitting answers"
Code: class Submission { state: GRADED, finalized: True, ... }
```
→ Definition stale vs reality.
→ Đúng: CI gate — class field changes require glossary review.

### Ví dụ 3 — Ứng dụng Ellumm

File `40_ubiquitous_language.py` minh hoạ end-to-end:
- Build glossary 4 BCs.
- Detect cross-BC term collision ("User" 3 BCs).
- Run drift detector trên code mixed terms.
- Apply rename `Submission → Attempt` với 5-phase plan.
- Cross-BC ACL không cần thay đổi (Published Language unchanged).

---

## MỨC ARCHITECT — TRADE-OFFS & ANTI-PATTERNS

### Khi nào DÙNG UL discipline

- Team ≥ 3 dev với non-tech business expert.
- Domain phức tạp, term overloading risk.
- Codebase persist > 1 năm (UL drift dài hạn).
- Cross-team handoff (term continuity).

### Khi nào nhẹ

- Solo dev / 2-người team.
- Prototype < 3 tháng.
- Term simple (CRUD app).

### Trade-offs

| Trục | UL discipline được | Mất |
|------|---------------------|------|
| Onboarding | Glossary speeds learning 2-3x | Initial setup of glossary |
| Bug rate | Term ambiguity bugs giảm rõ | Time to maintain glossary |
| Refactor | Rename predictable | Migration plan overhead |
| Business buy-in | Expert involves more (đọc được code) | Need expert time |
| Cross-BC | Translation explicit | ACL coding |

### Anti-patterns thường thấy

| Anti-pattern | Phát hiện |
|--------------|-----------|
| **No glossary** | Ask 3 devs "what's X?" → 3 answers |
| **Glossary in Confluence** | Last edit 2 năm trước |
| **Code uses dev jargon** | "SubmissionDTO", "QuizManager" — not business terms |
| **Term overload undocumented** | Same class name in 2 BCs, no translation |
| **Rename without ADR** | 50 files changed, no rationale doc |
| **Big-bang rename** | Single PR renames everywhere → downstream breaks |
| **Glossary out of sync** | Class definition diverged from glossary entry |
| **Deprecated term still in code** | grep finds 30 references to "old name" |
| **No CI gate** | New class added without glossary update |
| **Cross-BC term swap** | Internal naming leaked to Published Language event |

### Checklist trước khi merge PR

- [ ] New class/method/event has glossary entry?
- [ ] Old term marked deprecated (if renaming)?
- [ ] ADR drafted (if business-level rename)?
- [ ] Migration plan documented (if cross-team impact)?
- [ ] Cross-BC translation updated (if affecting boundary)?
- [ ] Drift check passes (no orphaned terms in code)?
- [ ] Published Language event versioned (if event renamed)?
- [ ] Test names also follow UL?

### So sánh với pattern lân cận

| | Pattern | Relationship to UL |
|---|---------|---------------------|
| Anti-pattern "Magic strings" (33) | Lesson 33 | Magic strings = no glossary entry; promote to UL term |
| Domain Event (36) | 36 | Event name MUST be UL of producing BC |
| ACL (34) | 34 | ACL is *translation layer* between 2 ULs |
| Event Storming (38) | 38 | Workshop output is *UL discovery* |
| Aggregate (35) | 35 | AR name is *cornerstone* of BC's UL |

---

## BÀI TẬP — 4 MỨC

### Mức 1 — Cơ bản (1 giờ)

Take 1 BC từ Ellumm (Lesson 34). Build glossary file with:
- All entities + their definitions.
- All domain events + their meaning.
- All commands.
- Domain services.

Minimum 15 entries.

### Mức 2 — Trung bình (1.5 giờ)

(a) Find 1 term overload across 2 BCs trong Ellumm. Document trong cross-BC translation table.

(b) Run drift detector trên 1 file code Ellumm hiện có. List inconsistencies.

(c) Update glossary entries for any new class added in last sprint.

### Mức 3 — Khó (architect, 3 giờ)

(a) Pick 1 entity in Ellumm (e.g. `Submission`). Plan rename to alternative term (e.g. `Attempt`).

Generate full 5-phase migration plan:
- Phase 1: deprecate old name
- Phase 2: dual support
- Phase 3: migration window
- Phase 4: remove old
- Phase 5: cleanup

For each phase, list:
- Files to change.
- DB migrations.
- Event versioning.
- API deprecation.
- Doc updates.
- Stakeholders to notify.
- Timeline.

(b) Implement automated drift detector script. Run on 1000-line codebase. Output JSON report.

### Mức 4 — Mở rộng neuro (2 giờ tự do)

Đọc 1 chương về Wernicke + Broca + arcuate fasciculus (Kandel chương 18 hoặc Geschwind 1965 paper). Trả lời:

1. **Wernicke's aphasia (fluent + meaningless)**: tương đương trong code review — dev viết code "look fluent" nhưng business logic wrong. How to detect early?

2. **Conduction aphasia (arcuate damage)**: hiểu được, nói được, nhưng không lặp lại được phrase mới. Tương đương: workshop discusses term X, dev writes class X, but X means different thing. ACL? Communication tooling?

3. **Bilingual code-switching activates dlPFC**: cost of switching. Developer working with 4 BCs → 4 ULs. Cognitive load? When to merge BCs vs split?

---

## ĐỒ HOẠ TỔNG KẾT

```
        UBIQUITOUS LANGUAGE management
   ═══════════════════════════════════════════════════════════
   ┌─────────────────────────────────────────────────┐
   │           Per-BC Glossary (UL of BC)            │
   │                                                 │
   │   Quiz Authoring BC:                            │
   │     Quiz, Question, Author, ...                 │
   │                                                 │
   │   Submission BC:                                │
   │     Submission, Attempt, Score (raw), Student   │
   │                                                 │
   │   Leaderboard BC:                               │
   │     Ranking, Position, Score (rank)             │
   │                                                 │
   │   Notification BC:                              │
   │     Recipient, Receipt, Channel                 │
   └─────────────────────────────────────────────────┘
              │                          │
              ▼                          ▼
   Cross-BC translation table   Drift detector + CI gate
   (handle term collision)       (verify code ↔ glossary sync)
              │                          │
              ▼                          ▼
   Published Language events      Rename migration (5-phase)
   (versioned, external contract)

   Brain analog:
   Wernicke (BA22) = semantics
   Broca (BA44/45) = production
   Arcuate fasciculus = connection (= ACL)
   Bilingual code-switching = 4 ULs per developer
   Semantic dementia = codebase mất precision
```

> **Tóm lại**: UL không phải nice-to-have — là *infrastructure* của domain code. Mỗi BC own glossary; cross-BC dùng translation + Published Language. Rename là multi-phase migration. Brain analog: Wernicke + Broca + arcuate là 3 vùng cho semantics + production + connection. Codebase healthy = "brain healthy"; UL drift = semantic dementia.

---

## KẾT THÚC PHASE DDD

Đã hoàn thành 7 lesson DDD:
- ✅ 34 Bounded Context (Brodmann parcellation)
- ✅ 35 Tactical Aggregate (cell membrane homeostasis)
- ✅ 36 Entity/VO/Event (neuron/molecule/AP)
- ✅ 37 Repository/Factory/Spec (hippocampus/neurogenesis/receptor)
- ✅ 38 Event Storming workshop (hippocampal replay)
- ✅ 39 Distributed DDD + Saga (HPA axis + spinal reflex/cortical)
- ✅ 40 Ubiquitous Language (Wernicke/Broca/bilingual)

**Bạn đã có**: vocabulary GoF (23) + grammar SOLID (5) + style Clean/Hex/EDA/CQRS+ES (4) + hygiene Anti-patterns (1) + strategic + tactical DDD (7).

**Lộ trình tiếp theo** (gợi ý đã ghi trong Lesson 33):
- Distributed systems patterns (Saga deep, Outbox+CDC, Circuit Breaker, Bulkhead, Hedge).
- Reliability + SRE (Retry+jitter, Timeout budget, Rate limiting, Load shedding, Chaos eng).
- Reading: Vernon DDD, Fowler PEAA, Newman Microservices, Hohpe EIP, Brown C4.

Bạn cũng có thể *capstone project*: split Ellumm Quiz thành multi-service Docker compose áp dụng tất cả 40 lesson.
