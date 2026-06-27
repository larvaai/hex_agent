# Lesson 37 — Repository + Factory + Specification
## Hippocampus / Neurogenesis / Receptor Binding — 3 supporting pattern hỗ trợ aggregate, mô phỏng 3 cơ chế sinh học nuôi neural object lifecycle.

---

## TÓM TẮT MỘT DÒNG

3 supporting pattern cấu hoàn aggregate (Lesson 35):
- **Repository** = abstraction over persistence — *collection-like API* giấu kỹ thuật lưu trữ. 1 repo cho 1 AR. **Hippocampus** lưu episodic memory; HM 1953 mất HC → không tạo memory mới.
- **Factory** = encapsulate complex aggregate construction. `create()` cho aggregate mới (enforce invariant ban đầu); `reconstitute()` rebuild từ persistence (skip invariant, state đã verified). **Neurogenesis** trong DG: stem cell → neuroblast → mature neuron là factory sinh học multi-step.
- **Specification** = reusable business rule predicate (`is_satisfied_by`), composable AND/OR/NOT. Dùng trong repository query và domain validation. **Receptor binding**: D1/D2/NMDA/AMPA mỗi cái chỉ "satisfy" với certain ligand; agonist (AND), allosteric (compose), antagonist (NOT).

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Aggregate (Lesson 35) cần 3 thứ ngoài chính nó:

1. **Lưu / lấy** aggregate khỏi DB/file/cache — *Repository*.
2. **Tạo** aggregate phức tạp (nhiều step, multi-data source) — *Factory*.
3. **Hỏi/lọc** aggregate theo business rule tái sử dụng — *Specification*.

Không có 3 cái này:

**Vấn đề 1 — Persistence rải**: `repo.save()` ở 1 chỗ, `db.execute("UPDATE...")` ở chỗ khác, ORM mapper ở chỗ thứ 3. Aggregate không biết khi nào nó được persist, khi nào event publish. Bug.

**Vấn đề 2 — Construction lặp**: `Submission(id=..., user_id=..., quiz_id=..., status=..., attempts=..., ...)` xuất hiện 5 nơi với args khác nhau. Khi thêm field mới → sửa 5 chỗ.

**Vấn đề 3 — Rule rải**: "passing = score ≥ 60%" check ở `submission.is_passing()`, check ở `LeaderboardService.filter_passing()`, check ở `ReportGenerator.passing_count()`. 3 phiên bản, lệch khi định nghĩa "passing" thay.

### 1.2. Định nghĩa và 3 thành phần

**(a) Repository** (Evans 2003, refined Vernon):

> *"Provides the illusion of an in-memory collection of all objects of that type."*

5 đặc điểm:
- **1 Repository per Aggregate Root**, không cho internal entity.
- **Collection-like API** (`save/get/remove/find_satisfying`) HOẶC persistence-style (`insert/update/delete/select`).
- **Return AR, never internal entity**.
- **Abstraction (Protocol/Interface)** — concrete impl ở infra layer (Hex).
- **Publish domain events on save** (Lesson 35 outbox pattern).

```python
class ISubmissionRepository(Protocol):
    def save(self, sub: Submission) -> None: ...
    def get(self, sub_id: SubmissionId) -> Optional[Submission]: ...
    def remove(self, sub_id: SubmissionId) -> None: ...
    def find_satisfying(self, spec: ISpecification[Submission]) -> List[Submission]: ...
```

**(b) Factory** (Evans 2003):

> *"A program element whose responsibility is the creation of other objects."*

Khi nào tách Factory (vs static method trong AR):
- Construction multi-step (load config + compute + verify external).
- Multi-source (CSV row vs API payload vs DB row).
- Tách `create()` (new aggregate, enforce invariant) vs `reconstitute()` (rebuild from persisted state, *skip* invariant check vì đã verified).
- Cross-aggregate creation (vd. `OrderFactory.from_cart(cart)` tạo Order từ Cart aggregate).

```python
class SubmissionFactory:
    @staticmethod
    def create(user_id: UserId, quiz_id: QuizId) -> Submission:
        # Enforce invariants for fresh aggregate
        sub = Submission.__new__(Submission)
        sub._id = SubmissionId(str(uuid.uuid4()))
        ...
        sub._pending_events.append(SubmissionCreated(...))
        return sub

    @staticmethod
    def reconstitute(state: Dict) -> Submission:
        # SKIP invariants — state was already valid when persisted
        sub = Submission.__new__(Submission)
        sub._id = state["id"]
        sub._attempts = [Attempt(**a) for a in state["attempts"]]
        sub._status = SubmissionStatus(state["status"])
        sub._pending_events = []        # reconstituted: no new events
        return sub
```

> *Tại sao 2 path khác nhau?* Khi load từ DB, state là *fact*, không phải *propose change*. Re-running invariants check (vd "must be DRAFT") sẽ raise (đã ở GRADED). `reconstitute` trust the persisted state.

**(c) Specification** (Evans 2003, Pattern Languages 1997 by Eric Evans + Martin Fowler):

> *"Encapsulates a predicate ... in a domain object that can be combined with other specifications using boolean logic."*

3 dùng chính:
- **Validation**: `passing_spec.is_satisfied_by(sub)` → bool.
- **Selection / Query**: `repo.find_satisfying(passing_spec & recent_spec)`.
- **Construction guidance**: factory dùng spec validate input.

Composable:
```python
high_score = ScoreAboveSpec(60.0)
recent = SubmittedAfterSpec(date.today() - timedelta(days=7))
qualified = high_score & recent                    # AndSpec
top_picks = high_score | LowScoreButImproveSpec()  # OrSpec
banned = ~user_in_bad_list                         # NotSpec
```

### 1.3. Neuroscience — 3 cơ chế sinh học

**(a) Repository = Hippocampus**

- Hippocampus (HC) là **store + retrieve** cho episodic memory ("tôi ăn gì hôm thứ ba").
- HM 1953 (Henry Molaison, bilateral medial temporal lobectomy điều trị epilepsy): HC removed → mất khả năng tạo *new* episodic memory. Old memories còn (đã consolidate). Working memory + procedural memory intact (other repositories).
- → Multiple repository: HC cho episodic, basal ganglia cho habit, cerebellum cho motor skill, neocortex cho semantic. **1 repository cho 1 aggregate type**.
- HC có *collection-like API*: input → encoding → store; query → pattern completion → retrieve. Không expose "neuron level"; chỉ expose memory level (= AR level).
- HM cũng cho thấy *new aggregates không tạo được* nếu repository down → repository là *critical infrastructure*.

**(b) Factory = Neurogenesis**

- Adult neurogenesis trong DG (dentate gyrus) và SVZ (subventricular zone): stem cell → neuroblast → mature granule cell. Multi-step *factory pipeline*.
- Mỗi step có invariant check (BMP signaling, Notch pathway, neurotrophic factors). Cell *fail* check → apoptose (= raise during factory).
- Eriksson 1998 (BrdU labeling in human DG postmortem): chứng minh adult human có tạo new neuron — đó là factory production line.
- *Two paths*: 
  - **Neurogenesis** (new neuron) = `Factory.create()` — enforce invariant từ đầu.
  - **Reactive gliosis** (tái phát triển cell sau injury, ít invariant check) = `Factory.reconstitute()` — restore từ "saved state".

**(c) Specification = Receptor Binding Specificity**

- Mỗi receptor có *ligand specificity*: D1 chỉ bind dopamine/D1-agonist; NMDA chỉ bind glutamate + glycine *cùng lúc* (= AndSpec).
- Composable:
  - **AND**: NMDA cần glutamate + glycine + depolarization (Mg²⁺ block release) — 3 condition đồng thời.
  - **OR**: GABA-A có nhiều subunit composition, các allosteric site (benzo, alcohol, neurosteroid) đều có thể activate → bind điểm A *hoặc* B.
  - **NOT**: Antagonist (naloxone block opioid receptor) = NotSpec.
- Spec composition phản ánh: business rule không phải đơn lẻ; thường là *kết hợp* (passing + recent + non-banned-user).

> 3 cơ chế trên đều có *reusable abstraction over fundamental operation*: store/retrieve (HC), create/reconstitute (neurogenesis), match/predicate (receptor). DDD code đi theo cùng nguyên lý.

### 1.4. So sánh với patterns đã học

| | Pattern lesson trước | Repository / Factory / Spec |
|---|---|---|
| Lesson 6 Adapter | Wrap external | Repository có thể *là* Adapter (Hex driven port + adapter) |
| Lesson 2 Factory Method | Tạo object | DDD Factory đặc biệt cho aggregate, có 2 path |
| Lesson 21 Strategy | Swap algorithm | Spec là Strategy chuyên cho predicate |
| Lesson 30 Hex | Port + adapter | Repository = driven port; impl = adapter |
| Lesson 35 Aggregate | AR boundary | 3 pattern này *hỗ trợ* AR (create, persist, query) |

---

## MỨC 2 — CẤU TRÚC

### 2.1. Repository — 2 style

**(a) Collection-oriented** (Vernon recommend):
- API như Python `set`: `add/remove/contains/...`.
- "Repository là tập hợp" — không expose CRUD verbs.
- Implicit save khi end of unit-of-work.

```python
class ISubmissionRepository:
    def add(self, sub: Submission) -> None: ...
    def remove(self, sub: Submission) -> None: ...
    def get(self, sub_id: SubmissionId) -> Optional[Submission]: ...
```

**(b) Persistence-oriented** (CRUD-style):
- API SQL-like: `save/update/delete`.
- "Repository là DAO" — explicit persistence calls.

```python
class ISubmissionRepository:
    def save(self, sub: Submission) -> None: ...     # insert hoặc update
    def delete(self, sub_id: SubmissionId) -> None: ...
    def get(self, sub_id: SubmissionId) -> Optional[Submission]: ...
```

> Vernon argument: **collection-style** decouple aggregate khỏi persistence semantics; **persistence-style** đơn giản hơn cho ORM-style codebase. Chọn 1, không trộn.

### 2.2. Factory — `create` vs `reconstitute`

```
create(user_input)
   │
   ├─ validate input (raise on bad)
   ├─ generate new ID
   ├─ enforce initial invariants
   ├─ append SubmissionCreated to pending_events
   └─ return new aggregate

reconstitute(persisted_state)
   │
   ├─ trust state (NO invariant re-check)
   ├─ rebuild AR from state dict / row
   ├─ reconstruct internal entities, VOs
   ├─ pending_events = []   (reconstituted: clean)
   └─ return aggregate ready for further commands
```

3 vi phạm phổ biến với factory:

- *Re-run invariants in reconstitute* → state ở GRADED, factory thử "must be DRAFT" → raise → can't load.
- *Emit "Created" event from reconstitute* → mỗi lần load = publish lại event → bug.
- *Direct constructor bypass factory* → invariants không enforce → orphan aggregate.

### 2.3. Specification — composability

```
ISpecification.is_satisfied_by(obj) → bool

AndSpec(a, b).is_satisfied_by(obj) = a.is_satisfied_by(obj) AND b.is_satisfied_by(obj)
OrSpec(a, b).is_satisfied_by(obj) = a.is_satisfied_by(obj) OR b.is_satisfied_by(obj)
NotSpec(a).is_satisfied_by(obj) = NOT a.is_satisfied_by(obj)

Python operator overloading:
    spec_a & spec_b   →  AndSpec(spec_a, spec_b)
    spec_a | spec_b   →  OrSpec(spec_a, spec_b)
    ~spec_a           →  NotSpec(spec_a)
```

Khi nào dùng Specification thay if/else trong code:
- Rule được dùng *> 1 nơi* (repository + domain + report).
- Rule cần combine với rule khác.
- Rule có thể *user-configurable* (admin tạo policy động).
- Rule cần unit test riêng (clean predicate).

Khi *không* nên:
- Rule đơn giản dùng 1 nơi → if đủ.
- Rule có side effect → đó là Domain Service, không Specification.

### 2.4. Bốn invariants

1. **1 Repository ↔ 1 AR**. Không repository cho internal entity.
2. **Repository return AR only, never internal entity**.
3. **Factory.create enforces invariants**; **Factory.reconstitute trusts state**.
4. **Specification pure, side-effect free**.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
# === Repository ===
interface ISubmissionRepository:
    save(sub: Submission)
    get(sub_id) -> Optional[Submission]
    remove(sub_id)
    find_satisfying(spec: ISpec) -> List[Submission]
    count() -> int

class InMemorySubmissionRepository:
    _store: Dict[SubmissionId, Submission]
    _publish: callable(event)
    save(sub):
        _store[sub.id] = sub
        for e in sub.collect_pending_events(): _publish(e)
    get(id): return _store.get(id)
    find_satisfying(spec): return [s for s in _store.values() if spec.is_satisfied_by(s)]

class SqliteSubmissionRepository(...):
    # Implements port using SQLite + serialization

# === Factory ===
class SubmissionFactory:
    @staticmethod
    def create(user_id, quiz_id) -> Submission:
        # Enforce initial invariants + emit SubmissionCreated event
        ...

    @staticmethod
    def reconstitute(state_dict) -> Submission:
        # Skip invariants, rebuild from persisted dict
        ...

# === Specification ===
interface ISpecification[T]:
    def is_satisfied_by(obj: T) -> bool
    def __and__(other): return AndSpec(self, other)
    def __or__(other):  return OrSpec(self, other)
    def __invert__():   return NotSpec(self)

class AndSpec(left, right): is_satisfied_by = left ^ right
class OrSpec(left, right):  is_satisfied_by = left | right
class NotSpec(inner):       is_satisfied_by = not inner

# Domain specs
class ScoreAboveSpec(threshold):       sub.score.percent >= threshold
class SubmittedAfterSpec(cutoff):       sub.submitted_at > cutoff
class FinalizedSpec():                  sub.status == FINALIZED
class UserInSegmentSpec(segment):       sub.user_segment == segment
class AttemptsExceededSpec(max_n):      sub.attempts_count > max_n

# Combine
passing_recent = ScoreAboveSpec(60.0) & SubmittedAfterSpec(yesterday)
high_or_low_improver = ScoreAboveSpec(90) | (ScoreAboveSpec(50) & ImprovedSpec())
clean_users = ~UserInSegmentSpec("banned")

# Use
qualified = repo.find_satisfying(passing_recent & ~banned)
```

### 3.2. Bảng 2x2 nhớ là đủ

|  | **State change** | **Query / predicate** |
|---|---|---|
| **Per instance** | Factory.create / reconstitute | Specification.is_satisfied_by(obj) |
| **Collection** | Repository.save / remove | Repository.find_satisfying(spec) |

4 ô là 3 pattern (Repository chia 2 phía persistence + query) + Factory cho construction.

---

## NĂM CHIỀU SO SÁNH (trong não vs trong code)

| Chiều | Hippocampus / Neurogenesis / Receptor | Repository / Factory / Specification |
|-------|--------------------------------------|--------------------------------------|
| **Cấu tạo** | HC (CA1/CA3/DG layers) + SVZ neural stem cell + receptor protein structure | Repository class + Factory class + Specification class composable |
| **Vị trí** | HC ở medial temporal; SVZ + DG niches; receptor ở synapse post-membrane | Repository ở infra adapter; Factory ở domain; Specification ở domain (predicate) |
| **Chức năng** | HC store/retrieve memory; neurogenesis build new neuron; receptor match ligand | Repository persist AR; Factory build AR; Specification predicate predicate |
| **Kết nối** | HC interact với neocortex (consolidation); SVZ → migration → integration; receptor → channel → signaling cascade | Repository ↔ infra DB; Factory ↔ external data source; Specification ↔ predicate consumers (repo, validation, report) |
| **Ý nghĩa** | Sinh học: lưu trữ + sản xuất + nhận diện đều cần dedicated mechanism | DDD: aggregate cần 3 supporting service riêng — không gộp vào AR |

---

## BA VÍ DỤ

### Ví dụ 1 — Vận hành thường (happy path)

```python
# Composition root wires everything
publisher = lambda e: bus.publish(e)
repo = InMemorySubmissionRepository(publisher)

# Create new aggregate via Factory
sub = SubmissionFactory.create(UserId("u1"), QuizId("q1"))
sub.submit_answers((...))
sub.grade(quiz_summary)
repo.save(sub)               # persist + publish events

# Later: reconstitute from persisted state
state = serialize_to_dict(sub)
restored = SubmissionFactory.reconstitute(state)
assert restored.status == sub.status     # state preserved
assert len(restored.collect_pending_events()) == 0  # NO event on reconstitute

# Query with Specification
passing = ScoreAboveSpec(60.0)
recent = SubmittedAfterSpec(date.today() - timedelta(days=7))
top = repo.find_satisfying(passing & recent)
print(f"Found {len(top)} passing recent submissions")
```

Mọi pattern *cộng tác*: factory tạo, repo lưu, spec lọc.

### Ví dụ 2 — Hỏng / vi phạm

**Vi phạm A — Repository return internal entity**:
```python
# BAD
class SubmissionRepo:
    def get_attempts(self, sub_id): ...   # ✗ expose Attempt
```
→ Đúng: chỉ `get(sub_id) → Submission`. Truy cập attempt qua `sub.attempts_snapshot()`.

**Vi phạm B — Factory re-run invariants on reconstitute**:
```python
# BAD
class SubmissionFactory:
    @staticmethod
    def reconstitute(state):
        sub = Submission.create(...)              # ✗ calls factory.create
        sub._status = state["status"]              # state có thể là GRADED
        # → SubmissionCreated event published (BUG)
```
→ Đúng: direct rebuild without invariant check; no event emission.

**Vi phạm C — Specification with side effect**:
```python
# BAD
class HighScoreSpec:
    def is_satisfied_by(self, sub):
        self.last_checked = datetime.now()         # ✗ mutates state
        return sub.score > 60
```
→ Spec phải pure. Side-effect = Domain Service.

**Vi phạm D — Spec không composable**:
```python
# BAD — no operator overloading
class HighScoreSpec:
    def check(self, sub): ...                     # different method name
# Không combine với spec khác trừ khi cùng API
```
→ Đúng: Protocol `is_satisfied_by` thống nhất + `__and__/__or__/__invert__`.

**Vi phạm E — Multiple repository per AR**:
```python
# BAD
class SubmissionReadRepo: ...
class SubmissionWriteRepo: ...
class SubmissionAdminRepo: ...
# 3 repository = lock semantics phân tán
```
→ CQRS đúng cách (Lesson 32) là tách *read model projection* khỏi write side, không "3 repo cùng AR".

### Ví dụ 3 — Ứng dụng Ellumm

File `37_repo_factory_spec.py` đi kèm với:
- **Repository**: InMemory + Sqlite implementations, collection-style API, find_satisfying().
- **Factory**: SubmissionFactory với 2 methods (create + reconstitute), phân biệt rõ.
- **Specification**: 5 domain spec (ScoreAbove, SubmittedAfter, Finalized, UserInSegment, AttemptsExceeded) + composable AndSpec/OrSpec/NotSpec + Python operator overloading.
- **Demo**: 8 case + anti-pattern showcase + cross-implementation parity (Memory vs Sqlite).

---

## MỨC ARCHITECT — TRADE-OFFS & ANTI-PATTERNS

### Khi nào DÙNG

| Pattern | Dùng khi |
|---------|----------|
| Repository | Aggregate persist (luôn cần khi AR có > 1 lifecycle event) |
| Factory tách | Construction multi-step / multi-source / cần create + reconstitute distinct |
| Specification | Rule reuse > 1 nơi; composable; user-configurable |

### Khi nào KHÔNG

| Pattern | Bỏ qua khi |
|---------|------------|
| Repository | Aggregate ephemeral (compute & discard) |
| Factory tách | Construction 1 dòng (`Submission.create(...)` static method đủ) |
| Specification | Rule đơn giản dùng 1 chỗ (if-else đủ) |

### Trade-offs

| Trục | Được | Mất |
|------|------|-----|
| Repository abstraction | Test in-memory, swap DB, decouple infra | Boilerplate Protocol + impl |
| Factory split | Clear create vs load semantics | 2 method maintain |
| Specification | Reusable predicate, combinable | Boilerplate class + operator overload |

### Anti-patterns thường thấy

| Anti-pattern | Phát hiện |
|--------------|-----------|
| Repository return internal entity | grep `repo.get_attempt` / `repo.get_*_inside` |
| Repository expose ORM session | `repo.session` / `repo.db` public |
| Factory.reconstitute emit Created event | grep event append in reconstitute |
| Factory bypass invariants in create | grep direct `Submission.__new__` without invariant |
| Specification with state | grep `self._something = ` in is_satisfied_by |
| Specification not composable | Method name khác `is_satisfied_by` |
| God Repository | Single repo cho 5 AR |
| Implicit save (auto-flush) bypass repo | ORM auto-flush without `repo.save()` |
| Wrong impl in domain code | Sqlite/HTTP imports in domain |
| Spec re-implemented as filter | `[s for s in subs if s.score > 60]` (rule rải) |

### Checklist trước khi merge PR

- [ ] Repository cho 1 AR duy nhất?
- [ ] Repository return AR (not internal)?
- [ ] Repository có Protocol/Interface (test in-memory)?
- [ ] Repository.save publish domain events?
- [ ] Factory.create enforce invariants, emit Created event?
- [ ] Factory.reconstitute *skip* invariants, *no* event emission?
- [ ] Specification có `is_satisfied_by` method?
- [ ] Specification compose `& | ~`?
- [ ] Spec pure (no side effect, no state mutation)?
- [ ] Spec dùng trong > 1 nơi (repo + validation + report)?

### So sánh 3 supporting pattern với pattern khác

| Pattern | Khác | Relationship |
|---------|------|--------------|
| Repository vs DAO | DAO = persistence-only, no domain semantic; Repository = collection of AR with domain knowledge | DAO is implementation detail of Repository |
| Repository vs Active Record | Active Record: entity self-persists. Repository: separate concern | AR = anti-pattern in DDD (couples to infra) |
| Factory (DDD) vs Factory Method (Lesson 2) | DDD: 2 path create/reconstitute; GoF: deferred class choice | DDD factory often uses Factory Method internally |
| Specification vs Strategy (21) | Strategy is algorithm; Specification is predicate | Specification *is* a Strategy specialized for `bool` return |
| Specification vs Query Object | Query Object = persistence-level (SQL builder); Spec = domain-level | Repository converts Spec → Query Object internally |

---

## BÀI TẬP — 4 MỨC

### Mức 1 — Cơ bản (45 phút)

Lấy code Lesson 35 (`Submission` aggregate). Identify:
- Có repository chưa? Implementation type?
- Có factory tách không? Hay chỉ static method?
- Có specification chưa? Hoặc filter rải?

Bổ sung *missing* pattern nào cần, hoàn thiện.

### Mức 2 — Trung bình (1.5 giờ)

(a) Implement `SqliteSubmissionRepository` lưu Submission qua serialize JSON columns. Verify *cross-implementation parity*: same operations cho cùng kết quả với InMemoryRepo.

(b) Add `reconstitute(state_dict)` cho `SubmissionFactory`. Test:
- Round-trip: `state = serialize(sub); restored = reconstitute(state)` → `restored == sub` (semantically).
- Reconstitute does NOT emit `SubmissionCreated`.

### Mức 3 — Khó (architect, 3 giờ)

(a) Define 5 specs cho Ellumm:
- `PassingSpec(min_percent)` 
- `RecentSpec(days)`
- `FinalizedSpec()`
- `UserTierAtLeastSpec(tier)`
- `AttemptsExceededSpec(max_n)`

Compose:
- `Award eligibility` = Passing(60) & Recent(30) & Finalized()
- `Bonus tier` = (Passing(90) | (Passing(70) & UserTierAtLeast(GOLD)))
- `Flag for review` = ~Finalized() | AttemptsExceeded(3)

Apply trong:
- `repo.find_satisfying(award_eligible)` — query
- `domain validation` — chặn finalize nếu bị flag
- `report generator` — count cases mỗi loại

(b) Anti-pattern challenge: refactor 1 file hiện có với code có 3 anti-pattern (god repo, factory invariants leak, spec rải). Đo cyclomatic complexity trước/sau.

### Mức 4 — Mở rộng neuro (2 giờ tự do)

Đọc 1 chương về *hippocampal memory consolidation* (Kandel chương 64 hoặc Eichenbaum *Hippocampus Book*). Trả lời:

1. **HM 1953**: HC removed → no new declarative memory. Old memories còn (consolidated, đã ở neocortex). Procedural memory intact. Tương đương trong code: nếu repository "down" (DB unavailable), những aggregate "in flight" có còn dùng được không? Bao lâu là chấp nhận được?

2. **Long-term potentiation (LTP)**: tạo memory không phải "save row" — là *strengthen synaptic weight*. Khác với "INSERT INTO memories". Tương đương: Repository có phải "INSERT INTO submissions"? Hay là *projection of event stream* (Lesson 32 ES)? Khi nào nên cái nào?

3. **Pattern separation in DG**: similar memories được encode thành *orthogonal* patterns ở DG để tránh interference. Tương đương: trong Specification composition, làm sao tránh "rule collision" (2 spec dùng cùng tên nhưng nghĩa khác)? Liên hệ tới Ubiquitous Language (Lesson 40 — coming).

---

## ĐỒ HOẠ TỔNG KẾT

```
        AGGREGATE + 3 SUPPORTING PATTERNS
   ═══════════════════════════════════════════════════════════
              ┌──────────────────────────┐
              │     AGGREGATE ROOT       │
              │  (Lesson 35)             │
              └──────────────────────────┘
                  ▲          │
                  │          │ emits
                  │ create() │ events
                  │          ▼
       ┌─────────────────┐  ┌─────────────────┐
       │    FACTORY      │  │  REPOSITORY     │
       │ create()        │  │ save() get()    │
       │ reconstitute()  │  │ find_satisfying │
       └─────────────────┘  └─────────────────┘
                                     │ uses
                                     ▼
                            ┌─────────────────┐
                            │  SPECIFICATION  │
                            │  & | ~          │
                            │  is_satisfied_by│
                            └─────────────────┘

   Brain analogy:
   - Aggregate     = cell (Lesson 35)
   - Factory       = neurogenesis (DG/SVZ stem cell → mature neuron)
   - Repository    = hippocampus (episodic store, HM 1953)
   - Specification = receptor binding (D1/NMDA/GABA specificity)
```

> **Tóm lại**: 3 supporting pattern hoàn thiện aggregate. Factory tạo (2 path: create + reconstitute); Repository lưu/lấy (collection-style preferred, 1 per AR, returns AR only); Specification predicate (composable, reusable). 3 pattern này không phải GoF reuse — chúng là *DDD-flavored* abstractions trên các cơ chế hạ tầng. Brain analogy: cell + neurogenesis + hippocampus + receptor = aggregate + factory + repository + specification. Sinh học đã chọn phân tách này.

---

## TIẾP THEO

- **Lesson 38** — Event Storming workshop: workshop run-through phát hiện bounded context + aggregate qua sticky note.
- **Lesson 39** — Distributed DDD: cross-context consistency, Saga inside vs across BC.
- **Lesson 40** — Ubiquitous Language case study.
