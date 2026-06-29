# Lesson 33 — Anti-Patterns Catalog
## Pathology Atlas — Học bệnh lý của não để chẩn đoán bệnh lý của codebase. Mỗi anti-pattern có "căn bệnh" tương ứng, có triệu chứng, có chẩn đoán, có phác đồ điều trị (= lesson đã giải).

---

## TÓM TẮT MỘT DÒNG

**Anti-pattern** = một giải pháp **trông có vẻ đúng** nhưng dẫn đến hậu quả tệ về bảo trì, mở rộng, hoặc đúng đắn. Lesson này không dạy *thêm* pattern — nó dạy *con mắt phòng ngự*: nhìn 1 đoạn code 30 giây nói được "smell gì, vi phạm nguyên tắc nào, lesson nào chữa".

> Não khỏe = phân vùng chức năng rõ (V1 chỉ edge, MT chỉ motion), dẫn truyền có topology (6-layer cortex, đường mạch dài có myelin), broadcast có lớp ngắt (GABA inhibition tránh runaway), và pruning có timing (mass synaptic pruning ở puberty *sau khi* basic skill đã học). Não bệnh = mất một trong những nguyên tắc đó: tau tangle Alzheimer phá topology, demyelination MS phá insulation, addiction "mọi reward → dopamine" mất diversity, autism đôi khi là *under-pruning* (giữ quá nhiều synapse), thoái hoá vestigial. Bài học architectural: **mỗi anti-pattern code có một bệnh lý não tương ứng** — học pathology giúp bạn intern intuition rằng "code này đang chết".

---

## MỨC 1 — CONCEPT

### 1.1. Vì sao có lesson "anti-pattern"?

Sau 32 lesson, bạn đã có **vocabulary** (23 GoF) + **grammar** (SOLID) + **style** (Clean / Hex / EDA / CQRS+ES). Đó là *kỹ năng tấn công* — biết tạo cái đẹp. Lesson này là *kỹ năng phòng ngự* — biết phát hiện cái xấu, gọi tên nó, chỉ ra cách chữa.

Tại sao tách riêng?
- **Định danh** sức mạnh hơn ngữ cảm. Nói "function này hơi rối" không tạo hành động; nói "đây là **God Object**, vi phạm SRP, nên tách 3 class theo Lesson 24" là *hành động được*.
- **Code review hiệu quả hơn** khi cả team có vocabulary chung. "Smell" của Fowler 1999 (*Refactoring*) đã chứng minh điều này.
- **Ngăn lan**: khi bạn thấy một anti-pattern xuất hiện và *không sửa*, nó tự nhân bản. Cargo Cult lan như virus.

### 1.2. Bảng phân loại

| Loại | Đặc điểm | Anti-pattern tiêu biểu |
|------|----------|------------------------|
| **Structural** (cấu trúc xấu) | Class/module bố cục sai | God Object, Big Ball of Mud, Anemic Domain |
| **Behavioral** (hành vi xấu) | Control flow / coupling sai | Spaghetti, Shotgun Surgery, Feature Envy |
| **Cognitive** (hiểu lầm khái niệm) | Lập trình viên hiểu sai pattern | Cargo Cult, Golden Hammer, Refused Bequest |
| **Lifecycle** (vòng đời xấu) | Code không được dọn | Lava Flow, Premature Optimization, Magic Numbers |

### 1.3. Neuroscience — bệnh lý não

Bốn principle chung của *bệnh lý não* cũng đúng cho codebase:

**(a) Loss of compartmentalization** — Khi vùng chức năng mất ranh giới, hệ thống collapse.
- Não: tau tangle Alzheimer phá cytoskeleton neuron → đường dẫn truyền lẫn lộn → cognitive decline.
- Code: God Object, Big Ball of Mud — không có boundary giữa concern.

**(b) Loss of insulation** — Khi đường truyền không có lớp cách điện, signal nhiễu.
- Não: demyelination trong Multiple Sclerosis → action potential propagate sai/chậm → motor symptom.
- Code: Shotgun Surgery — đổi 1 yêu cầu lan ra 10 file vì thiếu *encapsulation* (insulation).

**(c) Loss of diversity** — Khi 1 cơ chế giải mọi vấn đề, system fragility.
- Não: addiction — mọi reward chuyển thành dopamine spike → bỏ qua serotonin/GABA/ACh → behavior collapse.
- Code: Golden Hammer — mọi vấn đề giải bằng cùng 1 pattern.

**(d) Wrong timing** — Khi process đúng nhưng ở thời điểm sai.
- Não: synaptic pruning quá sớm (Williams syndrome) → mất khả năng học sau này.
- Code: Premature Optimization — tối ưu trước khi đo, mất flexibility.

### 1.4. Cách dùng catalog này

Khi review code:
1. Mở Section 2 (catalog 12 anti-pattern).
2. Quét code với checklist heuristics.
3. Tag từng smell phát hiện được với tên anti-pattern.
4. Map tới lesson chữa.
5. Đề xuất refactor cụ thể (không chung chung "code xấu").

> Quy tắc: **không có code production hoàn hảo**. Mọi codebase có 1-2 anti-pattern *chấp nhận được*. Mục tiêu là *nhận biết và quản lý*, không phải "loại bỏ 100%".

---

## MỨC 2 — CATALOG (12 ANTI-PATTERNS)

### 2.1. God Object (Blob / God Class)

| | |
|---|---|
| **Triệu chứng** | 1 class > 500 dòng làm > 5 trách nhiệm; nhiều field; nhiều method dài |
| **Hậu quả** | Không testable; sửa 1 chỗ vỡ chỗ khác; merge conflict liên tục |
| **Neuroscience** | "Neuron toàn năng" không tồn tại — não tránh single-point-of-failure. Một neuron của Aplysia chỉ làm 1 việc. Lý do: entanglement chi phí quá lớn |
| **Phát hiện** | `wc -l class` > 500; method count > 20; >3 lý do để class thay đổi |
| **Chữa** | **Lesson 24 SRP** — tách theo "lý do thay đổi". **Lesson 17 Mediator** nếu cần điều phối |

```python
# BAD
class QuizGod:                     # 600 dòng
    def submit(): ...              # logic submit
    def score(): ...               # logic chấm
    def save_to_db(): ...          # SQL
    def send_email(): ...          # SMTP
    def render_html(): ...         # template
    def export_csv(): ...          # I/O

# GOOD (theo SRP)
class QuizSubmitter: ...
class Scorer: ...
class SubmissionRepo: ...
class Notifier: ...
class HtmlRenderer: ...
class CsvExporter: ...
class QuizService:                 # orchestrator gọi 6 cái trên
    def submit(self, dto): ...
```

### 2.2. Spaghetti Code

| | |
|---|---|
| **Triệu chứng** | Control flow rối; nested if > 4 level; goto-style early return rải rác; biến trạng thái mutable lan rộng |
| **Hậu quả** | Không trace được; test không được vì nhiều branch; dễ bug |
| **Neuroscience** | **Tau tangle** trong Alzheimer — neurofilament protein rối loạn → axon vận chuyển sai → cell chết. Cytoskeleton clean = code clean |
| **Phát hiện** | Cyclomatic complexity > 10; nesting > 4; method > 50 dòng |
| **Chữa** | **Lesson 21 Strategy** (thay if/elif), **Lesson 20 State** (state machine), **Lesson 13 CoR** (chain of handler), **Lesson 22 Template Method** (skeleton) |

```python
# BAD
def process(quiz, user, mode, env):
    if mode == "dev":
        if env.beta:
            if user.tier == "free":
                if quiz.type == "math":
                    if user.attempts < 3:
                        ...

# GOOD (Strategy + early return)
def process(quiz, user, ctx):
    if not _can_attempt(user, ctx): return Reject(...)
    strategy = STRATEGY_REGISTRY[quiz.type]
    return strategy.score(quiz, user)
```

### 2.3. Anemic Domain Model

| | |
|---|---|
| **Triệu chứng** | Entity chỉ có getter/setter; logic ở "Service" class bên ngoài |
| **Hậu quả** | Code procedural đội lốt OO; logic rải; entity không enforce invariant |
| **Neuroscience** | "Skeleton without muscles" — bộ xương có nhưng không vận động. Tetraplegia: tay còn nguyên, không cử động được |
| **Phát hiện** | Class chỉ có `__init__`, getter, setter. Tên class kết thúc bằng `Service` chiếm > 30% |
| **Chữa** | Đem hành vi vào entity. Lesson 32 (CQRS+ES) Aggregate là ví dụ rõ — entity *biết* business rule, không chỉ chứa data |

```python
# BAD — anemic
class Submission:
    def __init__(self, user_id, answers, score=None):
        self.user_id = user_id
        self.answers = answers
        self.score = score
class SubmissionService:
    def calculate_score(self, sub: Submission, questions):
        sub.score = sum(1 for a, q in zip(sub.answers, questions) if a == q.correct)
    def is_valid(self, sub: Submission, questions):
        return len(sub.answers) == len(questions)

# GOOD — rich domain
class Submission:
    def __init__(self, user_id, answers):
        self.user_id = user_id
        self.answers = tuple(answers)              # immutable
        self._score: Optional[float] = None
    def score_against(self, questions) -> float:
        if len(self.answers) != len(questions):
            raise InvariantViolation("answer count")
        self._score = sum(1 for a, q in zip(self.answers, questions) if a == q.correct)
        return self._score
```

### 2.4. Big Ball of Mud

| | |
|---|---|
| **Triệu chứng** | Không có topology rõ; mọi module import mọi module; không layer; không boundary |
| **Hậu quả** | Onboarding 3 tháng; thay đổi sợ; coupling toàn diện |
| **Neuroscience** | **Đám rối không có cytoarchitecture** — đối lập với 6-layer cortex có trật tự. Cortex bệnh lý lissencephaly (smooth brain) thiếu folding → mental disability |
| **Phát hiện** | Vẽ dependency graph → không thấy DAG. Cycle import. `import *` |
| **Chữa** | **Lesson 29 Clean** hoặc **Lesson 30 Hex** — áp đặt boundary và direction |

```python
# BAD — mud
# everything in main.py: 2000 dòng, import nhau qua lại
import db, api, ui, score, email
# tích hợp ngẫu nhiên

# GOOD — Hex
domain/    # core, không import gì
infra/     # adapter, import domain
web/       # driving adapter, import domain
main.py    # composition root
```

### 2.5. Golden Hammer

| | |
|---|---|
| **Triệu chứng** | "Tôi mới học X, áp dụng vào MỌI vấn đề" |
| **Hậu quả** | Pattern không phù hợp gây overhead vô lý; team chán; codebase không cohesive |
| **Neuroscience** | **Cocaine addiction** — mọi reward (food, sex, social) chuyển thành dopamine spike → mất khả năng phân biệt sub-system. Diversity của neurotransmitter bị ép đơn dạng |
| **Phát hiện** | 80% class có cùng suffix (`*Manager`, `*Strategy`, `*Factory`); CQRS cho 1 entity 5 field; microservice cho team 3 người |
| **Chữa** | **Học pattern lithium** (= bao quát). Lesson này (33). Đặt câu hỏi "đây có phải vấn đề pattern X giải quyết không?" trước khi áp dụng |

```python
# BAD — Strategy cho mọi if
class IsPositiveStrategy: ...
class IsNegativeStrategy: ...
class IsZeroStrategy: ...
def strategy_for(n): ...      # quá phức tạp cho `n > 0`

# GOOD — đôi khi if là đúng
def classify(n):
    return "pos" if n > 0 else "neg" if n < 0 else "zero"
```

### 2.6. Premature Optimization

| | |
|---|---|
| **Triệu chứng** | Cache, denormalize, bit-trick *trước khi* benchmark; "tôi nghĩ đoạn này chậm" |
| **Hậu quả** | Mất readability; flexibility chết; thường tối ưu sai chỗ (90% latency là I/O không phải CPU) |
| **Neuroscience** | **Synaptic pruning quá sớm** — Williams syndrome: pruning genome bị xoá 26 gene → mất một số đường có thể cần. Hoặc autism dạng *under-pruning* — giữ quá nhiều synapse, sensory overload |
| **Phát hiện** | Comment "// optimize", hash table thay list 5 phần tử, manual SIMD, bit-tricks |
| **Chữa** | Knuth 1974: *"Premature optimization is the root of all evil."* Trình tự: **(1) làm đúng (2) đo (3) tối ưu hot path** |

```python
# BAD
class FastSet:                    # custom hash
    def __init__(self, capacity=1024): ...   # ơ hay sao đoán capacity?
# GOOD
items = set()                     # built-in, đủ nhanh
```

### 2.7. Lava Flow (Dead Code)

| | |
|---|---|
| **Triệu chứng** | Class/method/branch không reachable; comment "TODO 2018"; flag không bao giờ true |
| **Hậu quả** | Onboarding hỏi "code này dùng ở đâu?" và không ai biết. Sửa 1 nơi vỡ vì có path không ai test |
| **Neuroscience** | **Vestigial structures** — appendix, coccyx, plica semilunaris (mí mắt thứ 3). Không hại trực tiếp nhưng đôi khi viêm (appendicitis) → emergency. Code cũng vậy: dead code không hại đến khi nó *unexpectedly* được trigger |
| **Phát hiện** | Coverage tool: branch không bao giờ chạy. `git log -p`: file 5 năm không sửa nhưng không phải lib stable |
| **Chữa** | Xoá. Git nhớ; không cần "comment out" |

```python
# BAD
def submit(...):
    # OLD VERSION — keep for safety  ← 2018
    # def old_submit(...): ... 200 dòng dưới đây
    return new_submit(...)

# GOOD
def submit(...): return new_submit(...)
# (commit dạo old_submit đã ở trong git history)
```

### 2.8. Cargo Cult Programming

| | |
|---|---|
| **Triệu chứng** | Copy idiom/pattern không hiểu lý do. "Tôi thấy senior viết thế nên tôi viết thế." |
| **Hậu quả** | Pattern bị dùng sai context, không enforce gì; codebase ô nhiễm với "ritual" vô nghĩa |
| **Neuroscience** | **Mirror neuron mimicry không hiểu** — autism dạng nặng đôi khi imitate gesture mà không link đến intent. Học vẹt synaptic |
| **Phát hiện** | Hỏi "tại sao có dòng này?" → "vì luôn luôn thế". Singleton cho everything; @abstractmethod nhưng không có subclass |
| **Chữa** | Học rationale của pattern (lesson tương ứng). Yêu cầu *rationale comment* khi review PR áp dụng pattern |

```python
# BAD — Singleton cargo cult
class Logger:                     # tại sao Singleton? để 1 instance? đã có module-level
    _instance = None
    def __new__(cls):
        if cls._instance is None: cls._instance = super().__new__(cls)
        return cls._instance
# (code không thật sự cần Singleton — chỉ vì "logger thường là Singleton")

# GOOD
import logging
logger = logging.getLogger(__name__)
```

### 2.9. Magic Numbers / Strings

| | |
|---|---|
| **Triệu chứng** | `if status == 7`, `score *= 0.85`, `if user_type == "P"` |
| **Hậu quả** | Không ai biết số/chuỗi đó nghĩa gì → thay đổi sợ → bug |
| **Neuroscience** | **Chemical signal không có receptor cố định** — nếu dopamine chỉ là "molecule" không gắn nhãn, post-synaptic không biết cách phản ứng. Cần receptor (D1/D2) là "nhãn" |
| **Phát hiện** | grep regex `[^a-zA-Z_]\d{2,}[^a-zA-Z_]` ngoài math thuần. String literal lặp ≥ 3 lần |
| **Chữa** | `Enum`, `Final`, hằng số module-level |

```python
# BAD
if user.tier == 1: discount = 0.85
elif user.tier == 2: discount = 0.7

# GOOD
class Tier(IntEnum):
    BRONZE = 1; SILVER = 2; GOLD = 3
DISCOUNTS = {Tier.BRONZE: 0.85, Tier.SILVER: 0.70, Tier.GOLD: 0.50}
discount = DISCOUNTS[user.tier]
```

### 2.10. Shotgun Surgery

| | |
|---|---|
| **Triệu chứng** | Thay đổi 1 yêu cầu nghiệp vụ phải sửa ≥ 5 file lan ra hệ thống |
| **Hậu quả** | Onboarding sợ; merge conflict; quên 1 file → bug |
| **Neuroscience** | **Demyelination MS** — myelin nhiều nơi mất cùng lúc → phải replug nhiều đường. Mất *encapsulation* sinh học |
| **Phát hiện** | git log: 1 PR feature thường touches > 7 file không liên quan |
| **Chữa** | Phản đề của SRP (Lesson 24): *gom* trách nhiệm phân tán. Áp dụng Facade (Lesson 10) hoặc Aggregate (Lesson 32) |

```python
# BAD — đổi tax rate VAT 10% → 11% phải sửa ở:
# core/scoring.py:    score = base * 1.10
# infra/invoice.py:   total = subtotal * 1.10
# web/quote.py:       quote *= 1.10
# (3 nơi vì hằng số rải)

# GOOD
# config/tax.py:
VAT_RATE = 0.11
# Mọi nơi: from config.tax import VAT_RATE
```

### 2.11. Refused Bequest

| | |
|---|---|
| **Triệu chứng** | Subclass thừa kế từ class cha nhưng không dùng (hoặc raise NotImplementedError nhiều method) |
| **Hậu quả** | Phá LSP (Lesson 26); polymorphism không an toàn |
| **Neuroscience** | "Tế bào con nhận DNA cha mẹ nhưng không express enzyme cần" — DiGeorge syndrome 22q11 deletion: gene có nhưng không express → thymus thiếu T-cell |
| **Phát hiện** | grep `raise NotImplementedError`; subclass override > 50% method với pass/no-op |
| **Chữa** | **Lesson 27 ISP** (split interface) hoặc **Lesson 6 Adapter** (compose thay inherit) |

```python
# BAD — refused bequest
class ReadOnlyDatabase(Database):
    def write(self, x): raise NotImplementedError
    def delete(self, x): raise NotImplementedError
    def truncate(self): raise NotImplementedError
    def replicate(self): raise NotImplementedError

# GOOD — ISP narrow
class IReadable: def read(...) -> ...
class IWritable: def write(...) -> ...
class FileSystem(IReadable, IWritable): ...
class S3Bucket(IReadable, IWritable): ...
class CDN(IReadable): ...           # không thừa kế Writable nữa
```

### 2.12. Feature Envy

| | |
|---|---|
| **Triệu chứng** | Method của class A truy cập field của class B nhiều hơn của chính mình |
| **Hậu quả** | Trách nhiệm sai chỗ; thay đổi B lan sang A |
| **Neuroscience** | "Neuron quan tâm tới synapse hàng xóm hơn tới mình" — auto-immune: tế bào B-cell tạo antibody tấn công self → lupus, MS |
| **Phát hiện** | grep method dùng `other_obj.field` ≥ 3 lần và `self.field` < 2 lần |
| **Chữa** | Move method sang class B (Lesson 24 SRP); hoặc dùng Visitor (Lesson 23) nếu thật sự need cross-class operation |

```python
# BAD — feature envy
class Invoice:
    def total_for(self, customer):       # Invoice ham field Customer
        if customer.is_premium and customer.country == "US":
            return self.subtotal * customer.discount_rate
        ...
# GOOD — move to Customer
class Customer:
    def discount_for(self, subtotal):
        ...
class Invoice:
    def total_for(self, customer):
        return customer.discount_for(self.subtotal)
```

---

## NĂM CHIỀU SO SÁNH (in não vs in code) — bảng nhanh

| Anti-pattern | Cấu tạo (não) | Vị trí (code) | Chức năng (vấn đề) | Kết nối (lan) | Ý nghĩa (chữa) |
|---|---|---|---|---|---|
| God Object | Hypothetical "neuron toàn năng" — single-point-of-failure | 1 class size khổng lồ | Mọi side-effect | Coupling toàn diện | Lesson 24 SRP |
| Spaghetti | Tau tangle Alzheimer | Function nested if | Control flow rối | Branch lan vô tổ chức | Lesson 21 Strategy / 20 State |
| Anemic | Skeleton without muscles | Entity rỗng + Service phình | Logic rải | Service-class phình | DDD rich domain (32) |
| Big Ball of Mud | Lissencephaly (smooth brain) | Whole project no layer | Topology biến mất | Cycle import | Lesson 29/30 Clean/Hex |
| Golden Hammer | Cocaine: mọi reward → dopamine | Pattern X dùng cho mọi case | Loss of diversity | Naming uniform | Học rộng pattern |
| Premature Opt | Williams syndrome pruning | Hot path pre-cached | Mất flexibility | Optimization rải | Knuth: đo trước |
| Lava Flow | Vestigial structures | Branch không bao giờ chạy | Dead code | Cohabit production | Xoá; git nhớ |
| Cargo Cult | Mirror neuron không hiểu | Pattern dán không lý do | Ritual code | Lan qua copy | Học rationale |
| Magic Numbers | Chemical no receptor label | Literal số/chuỗi | Không meaning | Đổi sợ | Enum/Const |
| Shotgun Surgery | Demyelination MS | Sửa 1 lan 10 file | Mất encapsulation | Cross-file change | Aggregate / Facade |
| Refused Bequest | DiGeorge — gene không express | Subclass NotImpl | Phá LSP | Inheritance sai | Lesson 27 ISP / Adapter |
| Feature Envy | B-cell auto-immune | Method dùng field người khác | Trách nhiệm sai chỗ | Cross-class coupling | Move method (24 SRP) |

---

## BA VÍ DỤ

### Ví dụ 1 — Vận hành thường (codebase healthy)

Codebase healthy hiện rõ qua *signature*:
- `domain/`, `infra/`, `web/` — boundary rõ.
- Mỗi class < 200 dòng, mỗi method < 30.
- Cyclomatic complexity trung bình < 5.
- Hằng số sống trong module `config/`.
- Test coverage ≥ 80% và *test ở mức domain unit*, không integration-only.
- 1 PR feature thường touch ≤ 3 file.
- Naming pattern *đa dạng* (không phải tất cả `*Manager`).

### Ví dụ 2 — Hỏng / nhiều anti-pattern cùng lúc

Một file thực tế (lấy ý tưởng từ `quiz_god.py` ban đầu, gom hết anti-pattern):
- 600 dòng (God Object)
- Nested if 5 level (Spaghetti)
- Số `0.85`, `7`, `"P"` rải (Magic)
- Class `QuizManager` Singleton vô lý (Cargo Cult + Golden Hammer)
- Class `Submission` chỉ có 5 setter (Anemic)
- Method `calc()` của `Invoice` hỏi 8 field của `Customer` (Feature Envy)
- Branch `if False:` quanh code 2018 (Lava Flow)
- Sửa thuế phải qua 3 file (Shotgun Surgery)

→ Refactor: áp dụng SRP, Strategy, Const, Aggregate. Catalog ở section 2 chỉ rõ lesson chữa từng cái.

### Ví dụ 3 — Ứng dụng Ellumm Quiz (capstone)

File `33_antipatterns.py` đi kèm chứa **catalog code thực thi**:
- `bad_quiz.py` (in-file BAD section): 12 anti-pattern hiển thị rõ.
- `good_quiz.py` (in-file GOOD section): refactor cho từng anti-pattern.
- `detect_*` functions: heuristic phát hiện (line count, magic regex, complexity proxy).
- Demo: chạy detector trên BAD vs GOOD, in metric so sánh.

Đây là *capstone* — mọi lesson 24-32 đã học được áp dụng vào 1 file để đối phó với 12 smell.

---

## MỨC ARCHITECT — CHECKLIST CODE REVIEW & TOOLING

### Checklist code review (in 1 trang dán bàn)

**Quick scan (5 phút đọc PR)**:
- [ ] File mới có kích thước hợp lý (< 300 dòng)?
- [ ] Class mới có 1 lý do thay đổi rõ ràng?
- [ ] Tên class/method là **danh từ/động từ business**, không phải kỹ thuật chung chung (`Manager`, `Helper`, `Util`)?
- [ ] Magic number/string nào? Đã có Enum/Const?
- [ ] Method dài nhất bao nhiêu dòng? (limit 50)
- [ ] Nesting sâu nhất? (limit 4)

**Architectural scan (15 phút)**:
- [ ] Dependency direction đúng (domain không import infra)?
- [ ] Có cycle import không?
- [ ] Inheritance: subclass có raise NotImplementedError? (Refused Bequest)
- [ ] Method nào access field người khác > self? (Feature Envy)
- [ ] PR đụng > 5 file cho 1 feature đơn giản? (Shotgun Surgery)
- [ ] Comment "TODO" cũ hơn 6 tháng? Branch `if False:`? (Lava Flow)
- [ ] Pattern X được dùng đâu? Lý do *rationale comment*? (chống Cargo Cult)

**Production-readiness scan (architect-level)**:
- [ ] EDA: idempotency consumer? DLQ? schema versioned?
- [ ] CQRS+ES: optimistic concurrency? projection idempotent?
- [ ] Hex: composition root duy nhất? mỗi driven port có in-memory adapter?
- [ ] Clean: dependency rule rule một chiều?
- [ ] SOLID: tách interface theo client (ISP), abstraction trước concrete (DIP).

### Tooling

| Tool | Phát hiện | Khi dùng |
|------|-----------|----------|
| `radon` (Python) | Cyclomatic complexity, MI | CI gate complexity > 10 |
| `pylint` / `ruff` | Magic numbers, dead code, naming | Pre-commit hook |
| `pydeps` / `pyreverse` | Dependency graph | Visual review của Big Ball of Mud |
| `vulture` | Dead code phân tích | Quarterly cleanup |
| `wily` | Complexity trend over time | Health metric |
| Coverage | Branch chưa từng chạy = Lava Flow candidate | Quarterly |
| `git log --oneline FILE` | Hot file (changed many times) → SRP violation | When investigating |

### Heuristic số liệu (rule of thumb)

| Metric | Healthy | Cảnh báo | Smell |
|--------|---------|----------|-------|
| File length (LOC) | < 300 | 300-500 | > 500 (God) |
| Class methods | < 15 | 15-25 | > 25 (God) |
| Method length | < 30 | 30-50 | > 50 (Spaghetti) |
| Cyclomatic complexity | < 5 | 5-10 | > 10 (Spaghetti) |
| Nesting depth | < 3 | 3-4 | > 4 (Spaghetti) |
| PR file count | 1-3 | 4-7 | > 7 (Shotgun) |
| Inheritance depth | 1-2 | 3 | > 3 (Yo-yo) |
| Direct field access | < 1 cross-class | 2-3 | > 3 (Feature Envy) |
| Magic literal density | < 5% | 5-15% | > 15% (Magic) |

> **Đừng cứng nhắc về số**. Mục tiêu là *trigger conversation*, không reject PR mechanically. Số chỉ là gợi ý "đáng nhìn kỹ".

### So sánh với nguyên lý đã học

Tất cả 12 anti-pattern map vào lesson SOLID hoặc architecture đã học:

| Anti-pattern | Vi phạm chính |
|--------------|---------------|
| God Object | SRP (24) |
| Spaghetti | Strategy/State (21/20), CoR (13) |
| Anemic Domain | DDD principle, được thấy qua Aggregate (32) |
| Big Ball of Mud | Clean (29) / Hex (30) — không có boundary |
| Golden Hammer | Meta-principle: pattern lithium |
| Premature Optimization | Knuth principle |
| Lava Flow | YAGNI (You Aren't Gonna Need It) |
| Cargo Cult | Hiểu rationale; mọi lesson 1-32 |
| Magic Numbers | Domain language clarity (DDD) |
| Shotgun Surgery | SRP (24) inverse + Aggregate (32) |
| Refused Bequest | LSP (26) + ISP (27) |
| Feature Envy | SRP (24) — wrong owner of behavior |

---

## BÀI TẬP — 4 MỨC

### Mức 1 — Cơ bản (45 phút)

Lấy file `33_antipatterns.py` đính kèm. Chạy `python 33_antipatterns.py`. Đọc output detector. Match từng smell với section 2. Trả lời: *Anti-pattern X được fix bằng lesson nào?* (cho 12 cái).

### Mức 2 — Trung bình (1.5 giờ)

Tìm 1 file thật (open source hoặc của bạn) > 300 dòng. Áp dụng checklist code review section 4.1. List ít nhất 5 anti-pattern phát hiện được, kèm:
- Số dòng cụ thể.
- Tên anti-pattern.
- Lesson chữa.
- Đề xuất refactor cụ thể (≤ 3 câu mỗi cái).

### Mức 3 — Khó (architect, 3 giờ)

(a) Refactor file `bad_quiz.py` (BAD section của capstone) thành codebase clean. Yêu cầu:
- Tách thành ≥ 5 module với boundary rõ.
- Tất cả magic literal thành Enum/Const.
- Subclass không raise NotImplementedError.
- Cyclomatic complexity giảm < 5 mọi method.
- Coverage ≥ 90%.

(b) Viết detector `detect_smells.py` (script độc lập) với 5 heuristic:
- File > 500 dòng.
- Class > 20 method.
- `raise NotImplementedError` trong subclass.
- Magic number trong nested block.
- Cycle import.

Run trên repo của bạn. Output JSON với location.

### Mức 4 — Mở rộng neuro (2 giờ tự do)

Đọc 1 chương về *neurodegenerative disease* (Alzheimer hoặc MS). Trả lời:

1. **Tau tangle phá cytoskeleton**: bệnh nhân Alzheimer mất *episodic memory* trước, *procedural* sau (HM ngược). Map sang code: Spaghetti phá tầng nào trước (test? domain? infra?)? Tại sao?

2. **Demyelination MS**: pattern không liên tục (relapsing-remitting). Tương tự Shotgun Surgery: sửa 5 file lan ra theo bursts khi 1 yêu cầu nghiệp vụ thay. Câu hỏi: tại sao MS có *remission* (tự lành) nhưng codebase Shotgun thì không?

3. **Dopamine hyperactivity (schizophrenia, addiction)**: D2 receptor hyper-active → *salience attribution* sai (gán ý nghĩa cho noise). Map sang Cargo Cult: cố hiểu lý do pattern khi không có lý do thật → tự nghĩ ra. Bạn đã thấy người (hoặc chính mình) "rationalize" pattern không cần thiết bao giờ chưa? Mô tả 1 case.

---

## ĐỒ HOẠ TỔNG KẾT

```
   ANTI-PATTERNS (lăng kính phòng ngự)
   ═══════════════════════════════════════════════════════════
   STRUCTURAL          BEHAVIORAL          COGNITIVE          LIFECYCLE
   ─────────────       ─────────────       ─────────────      ─────────────
   God Object          Spaghetti           Cargo Cult         Lava Flow
   Big Ball of Mud     Shotgun Surgery     Golden Hammer      Premature Opt
   Anemic Domain       Feature Envy        Refused Bequest    Magic Numbers
        │                    │                   │                   │
        ▼                    ▼                   ▼                   ▼
     SRP/Aggr.       Strategy/State      Học rationale       Xoá / Đo / Const
     Clean/Hex       SRP / Move method   Pattern lithium     YAGNI / Enum
     (24/29/30/32)   (24/21/20/13/23)    (lesson 1-33)       (cleanup quarterly)
```

> **Tóm lại**: 32 lesson trước dạy *xây* — lesson 33 dạy *chẩn đoán*. Mỗi anti-pattern là một bệnh lý có triệu chứng, có nguyên nhân, có phác đồ. Architect senior phân biệt được "code đẹp khác lạ" vs "code đẹp đúng nguyên lý" vs "code có smell" — và chỉ cần 30 giây/file. Đó là *con mắt* mà 33 lesson này hướng tới.

---

## SAU LESSON 33 — KẾT LỘ TRÌNH

Bạn đã hoàn thành 4-tầng curriculum:
- ✅ Vocabulary: 23 GoF
- ✅ Grammar: SOLID (24-28)
- ✅ Style: Clean / Hex / EDA / CQRS+ES (29-32)
- ✅ Hygiene: Anti-patterns catalog (33)

**Lộ trình tiếp theo (gợi ý)**:
- **DDD** — Bounded Context, Aggregate sâu, Ubiquitous Language, Strategic Design.
- **Distributed systems patterns** — Saga, Outbox (đã chạm), Idempotency (đã chạm), Circuit Breaker, Bulkhead, Compensating transaction.
- **Reliability** — Retry với jitter, Dead Letter, Backoff, Timeout budget, Hedge requests.
- **Reading**:
  - Fowler — *Patterns of Enterprise Application Architecture*.
  - Vernon — *Implementing Domain-Driven Design*.
  - Newman — *Building Microservices*.
  - Hohpe & Woolf — *Enterprise Integration Patterns*.
  - Brown — *Software Architecture for Developers* (C4 model).

Nhưng đó là khi bạn cần. Với 33 lesson đã hoàn thành, bạn **đã có đủ tư duy để ngồi vào ghế architect ở 95% công ty**.
