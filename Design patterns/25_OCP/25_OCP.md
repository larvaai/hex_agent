# Lesson 25 — OCP (Open/Closed Principle)
## Synaptic Plasticity + Pattern Separation — Học mới bằng cách THÊM, không bằng cách ĐÈ

---

## TÓM TẮT MỘT DÒNG

**OCP** = mở để **mở rộng**, đóng để **sửa đổi**. Khi yêu cầu mới đến, bạn **thêm** code mới (subclass / interface impl / decorator), **không sửa** code cũ đã test.

> Não bộ học cả đời — nhưng khi học lái xe, các circuit "đi xe đạp" cũ vẫn nguyên vẹn. Cơ chế: **structural plasticity** (mọc dendritic spine mới, sprout axon mới) + **pattern separation ở dentate gyrus** (memory mới được "trải" sang pattern orthogonal trong CA3, không đè memory cũ) + **adult neurogenesis** (hippocampus tạo neuron mới suốt đời ở rodent, vẫn còn tranh luận ở human). Đó là OCP sinh học. Khi không có cơ chế này, neural network bị **catastrophic forgetting** — học task B đè weight của task A. Code không có OCP cũng vậy: thêm feature B sửa class A → regression. OCP là vaccine.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Tình huống quen: PM yêu cầu "thêm loại quiz có negative marking". Bạn có 2 con đường:

**Con đường 1 — Sửa code cũ**:
```python
def score(answers, quiz_type):
    if quiz_type == "standard":
        return sum(1 for q,a in answers.items() if a == key[q])
    elif quiz_type == "negative":          # ← case mới
        # ... logic mới ...
    # ... 3 tháng sau, thêm "weighted", "partial_credit", "time_bounded" ...
```
Mỗi PR đụng vào method này → review nặng → regression rủi ro → tested code bị disturb.

**Con đường 2 — Thêm code mới**:
```python
class QuizScorer(ABC):
    @abstractmethod
    def score(self, answers): ...

class StandardScorer(QuizScorer): ...
class NegativeMarkingScorer(QuizScorer): ...      # ← class mới
class WeightedScorer(QuizScorer): ...             # ← thêm sau, 0 đụng class cũ
```
Mỗi variant một file riêng. Class cũ không bao giờ bị "thức dậy" bởi feature mới.

OCP nói: **con đường 2 là default. Con đường 1 chỉ khi bạn đang fix bug, refactor, hoặc đổi requirement của variant đã có.**

### 1.2. Định nghĩa

**Bertrand Meyer 1988** (*Object-Oriented Software Construction*) — định nghĩa gốc, dùng inheritance:
> *"Software entities (modules, classes, functions) should be open for extension, but closed for modification."*

**Robert C. Martin 1996** (reformulation) — *polymorphic OCP*, dùng abstract interface:
> *"The behaviors of the system can be altered by adding new code, rather than changing existing code that already works."*

Cốt lõi: tested code đã đóng. Behavior mới đến qua *extension point* (interface, hook, plugin), không qua việc mổ xẻ code cũ.

### 1.3. 3 hiểu sai phổ biến

| Hiểu sai | Hiểu đúng |
|----------|-----------|
| "OCP = không bao giờ sửa code đã viết" | Sửa khi *fix bug* / *refactor* / *đổi requirement của variant cũ* — OK. OCP nói *thêm variant mới* không đòi sửa class cũ |
| "OCP = abstract hết mọi thứ" | Speculative generality là anti-pattern. Chỉ extract abstraction sau khi thấy ≥ 2 variant thật (rule of 3) |
| "OCP = inheritance" | Inheritance là 1 cách. Composition, decorator, Strategy, registry, configuration — tất cả đều đạt OCP. Robert Martin's reformulation explicitly **thoát khỏi inheritance**, dùng polymorphic interface |

### 1.4. Neuroscience analogy — Pattern separation + structural plasticity

Não phải giải quyết bài toán **stability-plasticity dilemma** (Grossberg 1980): vừa giữ ký ức cũ ổn định, vừa học liên tục. Mở rộng vô hạn → mất ổn định (catastrophic forgetting). Khoá hoàn toàn → không học. Não dùng 3 cơ chế phối hợp; cả 3 đều là OCP sinh học.

#### Cơ chế 1 — Hippocampus pattern separation (dentate gyrus)

Dentate gyrus (DG), gateway của hippocampal memory circuit, có 2 đặc tính kỳ lạ:

1. **Mật độ cao bất thường** — số granule cell ở DG (~1.2 triệu mỗi bên) gấp ~10× số neuron CA3 nhận input từ chúng.
2. **Sparse activity** — chỉ 2–4% granule cell active tại 1 thời điểm bất kỳ (Jung & McNaughton 1993; Treves & Rolls 1992).

Kết hợp = **expansion recoding**: input từ entorhinal cortex (EC) được "trải" sang không gian biểu diễn rộng + thưa, biến 2 input gần nhau (đỗ xe sáng nay vs hôm qua, tầng 3 vs tầng 4) thành 2 pattern *cực kỳ khác nhau* trong DG. CA3 nhận 2 pattern orthogonal → store 2 ký ức độc lập → recall không nhầm.

Đây là **pattern separation**: thêm ký ức mới mà không đè ký ức cũ. Bằng chứng:
- Yassa & Stark 2011 (fMRI): DG/CA3 selective cho pattern separation, không phải pattern completion.
- McHugh et al. 2007 (mouse, NR1 KO ở DG): mất NMDA ở DG → mất khả năng phân biệt 2 context gần giống → confuse, generalize quá mức.

**Liên hệ OCP**: interface `QuizScorer` đóng vai DG — mỗi `Scorer` implementation chiếm "namespace" riêng, không đè lên namespace của impl khác. Polymorphic dispatch (Python's MRO) làm việc của CA3 — nhận pattern, gọi đúng impl.

#### Cơ chế 2 — Structural plasticity (mọc spine mới, sprout axon)

Khi bạn học cái gì mới *quan trọng*, neuron không chỉ chỉnh weight (LTP) — nó còn **mọc dendritic spine mới** (structural plasticity, Yang Gan 2009 *Nature*: trong 1 giờ sau motor learning, mouse cortex mọc spine mới ở vùng tương ứng). Spine cũ vẫn nguyên — chỉ thêm mới.

Cùng cơ chế: axon có thể *sprout* nhánh mới đến mục tiêu mới mà không cắt nhánh cũ. Đó là cách brain "mở rộng" capacity: **cộng**, không **thay**.

**Liên hệ OCP**: thêm class mới = mọc spine mới. Class cũ (đã test, đã chạy production 6 tháng) = spine cũ — không đụng vào.

#### Cơ chế 3 — Adult neurogenesis (sinh neuron mới suốt đời)

Eriksson et al. 1998 (*Nature Medicine*): hippocampal dentate gyrus của người tạo neuron mới suốt đời (rodent confirmed; human contested — Sorrells 2018 *Nature* nói không có; Boldrini 2018 *Cell Stem Cell* nói có. Vẫn debate). Rodent: 700 neuron mới/ngày ở DG.

Neuron mới *integrate vào circuit hiện có* mà không phá circuit cũ. Aimone et al. 2011: neuron non-trẻ (4–6 tuần tuổi) hyperexcitable, đóng góp đặc biệt vào pattern separation cho ký ức mới.

**Liên hệ OCP**: plugin / registry pattern — runtime đăng ký impl mới vào hệ thống đang chạy mà không stop & redeploy.

#### Catastrophic forgetting — phản đề

Neural network nhân tạo *không có DG, không có structural plasticity, không có neurogenesis*. Train task A xong train task B → weight cập nhật cho B đè lên weight đã học cho A → A bị forget hoàn toàn (McCloskey & Cohen 1989; Goodfellow et al. 2013).

Solution trong AI: **Complementary Learning Systems (CLS)** — McClelland, McNaughton & O'Reilly 1995. Hippocampus encode nhanh, replay during sleep, từ từ consolidate vào neocortex (slow, distributed, không catastrophic). Đây là cơ sở sinh học cho experience replay trong reinforcement learning (DQN 2015) và continual learning.

**Liên hệ code**: nếu bạn cứ "sửa class cũ để thêm feature" mà không có pattern separation (interface), bạn sẽ regression chéo — feature B làm vỡ test của feature A. OCP là CLS phiên bản code: tách *plasticity layer* (interface + concrete impls thay đổi liên tục) khỏi *stable core* (orchestrator, contract).

#### 5 chiều của analogy

| Chiều | Trong não (DG + structural plasticity + neurogenesis) | Trong code (OCP) |
|-------|-------------------------------------------------------|-------------------|
| **Cấu tạo** | DG sparse expansion + dendritic spine mọc thêm + adult-born granule cell | Interface (abstraction) + concrete impls + decorator + plugin registry |
| **Vị trí** | DG ở gateway giữa EC input và CA3 storage | Abstraction ở boundary giữa caller (orchestrator) và behavior variants |
| **Chức năng** | Separate gần thành xa, store thêm mà không đè | Polymorphic dispatch: caller chọn đúng impl, mỗi impl độc lập |
| **Kết nối** | Mossy fibers DG→CA3 không "rewrite" CA3; spine mới không xoá spine cũ | Concrete impl wire vào qua DI; class cũ không bị mở ra để sửa |
| **Ý nghĩa** | Tránh catastrophic forgetting; preserve old memories | Tránh regression; preserve tested code; cho phép parallel feature dev |

### 1.5. Khi nào DÙNG OCP nghiêm

- Bạn đã thấy ≥ 2 variant của cùng axis (Rule of 3: chờ đến variant thứ 3 mới extract interface — variant 2 có thể là noise).
- Stakeholder explicit: "sẽ có thêm loại X nữa".
- Code hiện có *if/elif chain trên type tag* (smell rõ).
- Plugin / 3rd-party / customer custom — extension point bắt buộc.
- Phải release variant mới nhanh (hotfix kiểu config-driven).

### 1.6. Khi nào KHÔNG dùng (over-OCP / speculative)

- Speculative generality: 5 tầng abstract hierarchy, có 1 concrete impl.
- "Maybe có ngày dùng" → YAGNI (You Aren't Gonna Need It).
- Wrong abstraction: extract interface trên trục sai (Sandi Metz 2014 — "duplication is far cheaper than the wrong abstraction").
- Class internal < 100 dòng, 1 dev sở hữu, không có 3rd-party.
- Variant tiếp theo không bao giờ đến (đo bằng git log: 6 tháng không thêm variant → có thể không cần OCP ở đây).

> **Heuristic vàng**: "Don't make it abstract until you have the second use case. Don't generalize until you have the third." — chờ đến lúc bạn có **đủ 2 variant cụ thể trong tay** mới extract interface; nếu rút ra abstraction từ 1 variant, 80% xác suất bạn rút sai trục.

---

## MỨC 2 — ALGORITHM / CẤU TRÚC

### 2.1. 7 cơ chế kỹ thuật để đạt OCP

| # | Cơ chế | Khi áp | GoF Lesson liên quan |
|---|--------|--------|----------------------|
| 1 | **Strategy** — interface + multiple impl, swap qua DI | Variant đi kèm với 1 axis duy nhất (scoring rule, sorting algo) | Lesson 21 |
| 2 | **Template Method** — base class skeleton + override hook | Variant chia sẻ flow nhưng vài bước khác | Lesson 22 |
| 3 | **Decorator** — wrap object hiện có để thêm cross-cutting concern | Logging, retry, caching, time penalty (orthogonal to core) | Lesson 9 |
| 4 | **Observer** — attach listener mới mà không đụng publisher | Notification fan-out, audit trail | Lesson 19 |
| 5 | **Visitor** — thêm operation mới lên hierarchy class hiện có | Khi hierarchy data ổn định, operation đa dạng | Lesson 23 |
| 6 | **Plugin / Registry** — register impl runtime, load by name | 3rd-party extension, config-driven | — |
| 7 | **Configuration / Data-driven** — đẩy điều kiện vào data (rule engine, JSON config) | Quá nhiều variant nhỏ, biến variant thành data | — |

→ **OCP không phải 1 pattern, mà là 1 *kết quả* đạt được qua nhiều pattern**. Mỗi axis of change cần 1 cơ chế phù hợp.

### 2.2. Recipe 6 bước

```
INPUT:  một class hoặc method có if/elif growing trên type tag
        OR một class chuẩn bị nhận yêu cầu thêm variant

step 1: nhận diện axis of change
        - liệt kê các "loại" hiện có
        - dự đoán hoặc xác nhận với stakeholder các "loại" sẽ thêm
        - nếu < 2 loại thật: STOP. Không OCP. Code thẳng.

step 2: chọn cơ chế (Strategy / Decorator / ... — bảng 7 trên)

step 3: định nghĩa interface
        - signature ổn định, đóng — nếu sau này phải đổi signature, đó là crack
        - tên method theo *what*, không *how*

step 4: chuyển variant hiện tại thành 1 concrete impl của interface
        - giữ behavior nguyên vẹn (hành vi snapshot)

step 5: thay thế if/elif (hoặc dispatch table) bằng polymorphic call

step 6: thêm variant mới = thêm class mới impl interface
        - 0 file cũ thay đổi
        - test cũ pass không đổi
```

### 2.3. Invariants sau refactor OCP

1. **Không còn `if/elif/match` trên type tag** trong code chính. (Có thể còn ở edge — factory/registry — chấp nhận được.)
2. **Thêm variant mới = thêm file mới + 0 sửa file cũ**. Đo bằng `git diff --stat`.
3. **Test cũ pass không sửa**. Test mới chỉ cho variant mới.
4. **Caller phụ thuộc abstraction, không concrete** (cầu nối sang DIP — lesson 28).
5. **Liskov: mọi impl giữ contract của interface** (cầu nối sang LSP — lesson 26). Ví dụ: `score()` không bao giờ raise exception ngoài tài liệu, return value đúng type, không có side effect ngoài advertise.

### 2.4. Anti-patterns hay xảy ra cùng OCP

| Anti-pattern | Triệu chứng | Cách tránh |
|--------------|-------------|------------|
| **Speculative Generality** | 5-tầng abstract, 1 impl | Chờ rule of 3 |
| **Wrong Abstraction** | Interface extract sai trục → impl phải ép cong | Sandi Metz: thà duplicate còn hơn abstraction sai. Inline lại, chờ pattern rõ hơn |
| **Open for ALL extension** | Mọi method virtual, mọi class extensible → spaghetti | Open theo *axis cụ thể*, không open vô hạn |
| **Frozen interface trap** | Interface đóng quá sớm, sau cần thêm param chung | Bắt đầu với *narrow* signature, mở rộng có chủ đích qua versioning |
| **OCP without LSP** | Subclass impl interface nhưng vi phạm contract → caller phải `isinstance` check | Lesson 26 sẽ giải |
| **Plugin abuse** | Mọi thứ thành plugin, debug khó, hot-reload sai | Plugin chỉ cho 3rd-party hoặc config thật cần thiết |

### 2.5. Đo bằng metric cụ thể

| Metric | OCP good | OCP bad |
|--------|----------|---------|
| `git diff --stat` khi thêm variant mới | Files changed: 0 hoặc 1 (registry) | Files changed: 5+ |
| Số `if isinstance(...)` trong code chính | 0 | > 3 |
| Số `match`/`switch` trên type tag | 0 ở core, OK ở factory | nhiều ở core |
| Số virtual method override per class | 1–2 | > 5 (Frankenstein) |
| Test regression khi thêm variant mới | 0 (chỉ test mới) | nhiều (regression chéo) |

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode — refactor recipe áp lên Ellumm Quiz

```
Bắt đầu: lesson 24 đã có
    QuizScorer(ABC) + StandardScorer + NegativeMarkingScorer

Thêm yêu cầu (Curriculum team):
    - WeightedScorer: mỗi câu có weight khác nhau (câu cuối quan trọng hơn)
    - PartialCreditScorer: multi-select; cho điểm tỉ lệ # đáp án đúng

Bước 1 — kiểm interface QuizScorer còn phù hợp không:
    score(answers) -> ScoreResult
    Phù hợp. Không cần đổi signature.

Bước 2 — viết WeightedScorer + PartialCreditScorer là class MỚI:
    class WeightedScorer(QuizScorer):
        __init__(questions: List[Question])  # Question có .weight
        score(answers): tổng weight của câu đúng

    class PartialCreditScorer(QuizScorer):
        __init__(answer_keys: Dict[qid, Set[option]])
        score(answers: Dict[qid, Set[option]]):
            for each q: ratio = |chosen ∩ correct| / |correct|
            sum ratios

Bước 3 — DEMO: orchestrator KHÔNG SỬA:
    QuizSubmissionService(scorer=weighted_scorer)  ← chỉ đổi DI

Bước 4 — yêu cầu ngang (Marketing): "thêm SMS notification, đôi khi cùng email":
    class SmsNotifier: notify(...)
    class PushNotifier: notify(...)
    class CompositeNotifier: notify(...) → fanout

Bước 5 — yêu cầu cross-cutting (Curriculum): "trừ 1 điểm/phút trễ":
    class TimePenaltyDecorator(QuizScorer):
        __init__(inner: QuizScorer, time_taken_sec, max_sec, penalty_per_min)
        score(answers): inner.score(answers) - penalty
    
    Wrap: TimePenaltyDecorator(inner=NegativeMarkingScorer(...))

Bước 6 — yêu cầu config-driven: "load scorer theo string từ config":
    @ScorerRegistry.register("standard")
    class StandardScorer(...): ...
    
    scorer = ScorerRegistry.create("weighted", questions=...)
```

### 3.2. Python — file `25_ocp.py`

Cấu trúc file chi tiết trong `25_ocp.py`:

1. **Domain types** (`Question`, `ScoreResult`).
2. **Abstract `QuizScorer`** + 2 impl từ lesson 24 (Standard, NegativeMarking).
3. **3 impl mới**: `WeightedScorer`, `PartialCreditScorer`.
4. **Decorator pattern**: `TimePenaltyDecorator` (cross-cutting, áp lên bất kỳ scorer nào).
5. **Notifier hierarchy**: `EmailNotifier`, `SmsNotifier`, `PushNotifier` + `CompositeNotifier` (fanout).
6. **Anti-example** — `OcpViolationScorer` dùng if/elif trên `quiz_type` string. Mỗi yêu cầu mới = sửa giữa method, đo bằng số dòng.
7. **Plugin Registry** — `ScorerRegistry` decorator-based registration, runtime lookup.
8. **5 demo**:
   - Demo 1 — Add 2 scorer mới: 0 dòng class cũ thay đổi.
   - Demo 2 — Decorator chain: `TimePenalty(NegativeMarking)` + `TimePenalty(Standard)`.
   - Demo 3 — Anti-example đối chiếu: file count + diff khi thêm variant.
   - Demo 4 — Composite notifier fanout: Email + SMS + Push một call.
   - Demo 5 — Registry: load scorer từ config string.

Chạy:
```bash
python 25_ocp.py
```

---

## 5 CHIỀU — BẢNG SO SÁNH IN NÃO VS IN CODE

| Chiều | Não (DG pattern separation + structural plasticity + neurogenesis) | Code (OCP qua Strategy + Decorator + Plugin) |
|-------|---------------------------------------------------------------------|----------------------------------------------|
| **Cấu tạo** | DG sparse coding (~10× neuron, 2-4% active) + dendritic spine mọc thêm khi học + adult-born granule cell | Interface (`QuizScorer`) + concrete impls + decorator + registry. Mỗi variant một "namespace" riêng |
| **Vị trí** | DG ở gateway EC→CA3, không nằm xuyên suốt — chỉ ở điểm vào | Abstraction nằm tại *boundary* giữa orchestrator và behavior variants — không phải mọi nơi |
| **Chức năng** | Tách 2 input gần thành 2 pattern xa, store thêm mà không đè | Polymorphic dispatch: caller chọn đúng impl, mỗi impl độc lập, thêm impl mới không đè impl cũ |
| **Kết nối** | Mossy fibers DG→CA3 *không rewrite* CA3 weight; spine mới *không xoá* spine cũ | Class mới *wire vào* qua constructor injection / registry; class cũ *không bị mở ra* để sửa |
| **Ý nghĩa** | Tránh catastrophic forgetting; preserve old memories; expand capacity tuyến tính | Tránh regression chéo; preserve tested code; thêm feature parallel không block |

---

## 3 LOẠI VÍ DỤ TRONG CODE

### Ví dụ 1 — Vận hành thường (happy path)

Lesson 24 đã có `QuizScorer(ABC)` + 2 impl. Lesson 25 thêm `WeightedScorer` và `PartialCreditScorer`:

```python
# Class mới — 0 file cũ thay đổi
class WeightedScorer(QuizScorer):
    def __init__(self, questions: list[Question]):
        self.questions = questions
    def score(self, answers):
        earned = sum(q.weight for q in self.questions if answers.get(q.qid) == q.correct_answer)
        total = sum(q.weight for q in self.questions)
        return ScoreResult(points=earned, total=total)

# Wiring — chỉ đổi DI 1 dòng
service = QuizSubmissionService(scorer=WeightedScorer(questions), ...)
```

→ Orchestrator không biết "weighted" tồn tại; nó chỉ biết `QuizScorer`. **Đó là OCP**.

### Ví dụ 2 — Hỏng/thiếu (vi phạm OCP)

```python
# Anti-pattern: if/elif trên quiz_type
def score(quiz_type, answers, key, weights=None, ...):
    if quiz_type == "standard":
        return sum(1 for q,a in answers.items() if a == key[q])
    elif quiz_type == "negative":
        # ... 8 dòng ...
    elif quiz_type == "weighted":          # mới thêm → SỬA method này
        # ... 10 dòng ...
    elif quiz_type == "partial_credit":    # tiếp → lại SỬA
        # ... 12 dòng ...
    else:
        raise ValueError(f"Unknown quiz type: {quiz_type}")
```

Hậu quả thực tế:
- Mỗi PR thêm variant mới đụng *cùng method* → merge conflict liên tục.
- Test variant cũ phải re-run vì shared method có thể bị break.
- Method phình lên 100+ dòng, đọc khó, dev mới sợ.
- Câu lệnh `else: raise ValueError` không có compile-time check — sai typo "weigted" chỉ phát hiện runtime.
- Param signature phình theo `weights=None, time_limit=None, partial_credit_map=None` — nhiều param không relevant cho mỗi case.

### Ví dụ 3 — Ứng dụng Ellumm

| Yêu cầu nghiệp vụ | OCP-compliant impl | Files modified | Files added |
|-------------------|--------------------|-----------------|-------------|
| Thêm `WeightedScorer` | Class mới impl `QuizScorer` | 0 | 1 |
| Thêm `PartialCreditScorer` | Class mới impl `QuizScorer` | 0 | 1 |
| Thêm trừ điểm theo thời gian | `TimePenaltyDecorator` wrap scorer | 0 | 1 |
| Thêm SMS notification | `SmsNotifier` impl `Notifier` Protocol | 0 | 1 |
| Gửi cùng lúc Email + SMS + Push | `CompositeNotifier(emailN, smsN, pushN)` | 0 | 1 |
| Load scorer từ config string | `ScorerRegistry.create("weighted", ...)` | 0 (registry decorator vào class mới) | 1 |
| Đổi scoring rule của `StandardScorer` (bug fix, không phải feature mới) | Sửa `StandardScorer` chính | 1 | 0 |

→ Hàng cuối là *không* vi phạm OCP — đó là *fix variant cũ*, không phải *thêm variant mới*. OCP chỉ ràng buộc trường hợp thứ hai.

---

## SO SÁNH PATTERN LÂN CẬN

| Pattern / Principle | Đặc điểm | Quan hệ với OCP |
|---------------------|----------|-----------------|
| **SRP** (Lesson 24) | 1 class = 1 actor | SRP đặt nền: nếu class đa actor, OCP không cứu — sửa cho actor A vẫn ảnh hưởng actor B trong cùng class |
| **LSP** (Lesson 26) | Subclass thay thế superclass mà không phá hành vi | OCP không có LSP = trap. Caller phải `isinstance()` check vì subclass vi phạm contract → if/elif quay lại |
| **ISP** (Lesson 27) | Interface không ép client phụ thuộc method thừa | ISP đảm bảo interface đủ hẹp để impl mới không phải implement method không liên quan |
| **DIP** (Lesson 28) | Cấp cao phụ thuộc abstraction | DIP là *điều kiện cấu trúc* để OCP khả thi. Thiếu DIP, caller hard-code concrete → không thể swap |
| **Strategy** (GoF, Lesson 21) | Interface + multiple impl, runtime swap | Cơ chế #1 đạt OCP cho axis "thuật toán" |
| **Template Method** (GoF, Lesson 22) | Base skeleton + hook | OCP cho "flow giống nhau, vài bước khác" |
| **Decorator** (GoF, Lesson 9) | Wrap object thêm chức năng | OCP cho cross-cutting concerns (logging, retry, time penalty) |
| **Observer** (GoF, Lesson 19) | Publisher + listener fan-out | OCP cho extension qua subscription |
| **Visitor** (GoF, Lesson 23) | Operation mới lên hierarchy ổn định | OCP cho axis "operation" thay vì "type" |

**Vai trò OCP trong SOLID**: OCP là **kết quả** của SRP + LSP + ISP + DIP đúng. Bạn không "viết OCP code" trực tiếp — bạn viết SRP (chia trách nhiệm), DIP (phụ thuộc abstraction), LSP (subclass đúng contract), ISP (interface hẹp); kết hợp đúng → OCP tự đạt.

---

## TRADE-OFFS

| Trade-off | Chi phí | Lợi ích |
|-----------|---------|---------|
| Thêm interface trước khi có 2nd impl | Speculative gen, sai trục | (Thường âm — đừng làm) |
| Thêm interface sau khi có 2nd impl | 1 file abstract + DI wiring | Variant 3+ không sửa class cũ |
| Decorator chain | Hiểu khó hơn (phải trace qua wrapper) | Cross-cutting concern không nhồi vào core |
| Plugin registry | Magic, debug khó (impl load runtime) | 3rd-party extension không rebuild |
| Polymorphic dispatch | Indirect call (nano-second overhead) | Negligible cho hầu hết domain |
| Nhiều file nhỏ | Navigation overhead | Test isolation, parallel work |

**Quy tắc**: chấp nhận overhead khi axis thật sự *mở*. Nếu axis chỉ có 1 variant mãi mãi (ví dụ: payment processor toàn dùng Stripe duy nhất 5 năm qua), inline là đúng — đừng OCP cho hư cấu.

---

## CHECKLIST TRƯỚC KHI MERGE PR

- [ ] **Có if/elif/match trên type tag không?** Nếu có ở core (không phải factory), đó là smell rõ ràng.
- [ ] **Thêm variant này có phải variant thứ 2 hay 3?** Nếu là thứ 2, có thể *chưa cần* extract abstraction (rule of 3). Nếu thứ 3+, *bắt buộc* extract.
- [ ] **Test cũ pass không sửa không?** Có phải sửa test cũ → có gì đó disturb code cũ.
- [ ] **`git diff --stat` khi thêm variant**: file count phải ≤ 1–2 (chỉ class mới + có thể wiring).
- [ ] **Abstraction match real axis of change?** Liệt kê 3 variant đã có và kiểm xem chúng *thật sự* cùng axis, hay là forced fit.
- [ ] **Liskov check**: subclass mới giữ contract của base? Không raise exception ngoài tài liệu? Không có side effect ngoài advertise?
- [ ] **Speculative gen check**: số impl hiện có ≥ 2? Nếu chỉ 1, đừng abstract.
- [ ] **Plugin registry**: nếu dùng, có verify impl hợp lệ tại register time? (Compile-time > runtime fail.)
- [ ] **Wrong abstraction risk**: 6 tháng tới nếu requirement variant đi theo *trục khác hoàn toàn*, abstraction này có ép cong không?

---

## BÀI TẬP 4 MỨC

### Mức 1 — Cơ bản

Mở `25_ocp.py`. Thêm `BonusQuestionScorer` — giống `StandardScorer` nhưng có 1 câu bonus value 2 điểm (qid = `"bonus"`). Yêu cầu: 0 file cũ thay đổi. Đếm lines added và lines modified.

### Mức 2 — Trung bình

`OcpViolationScorer` trong file dùng if/elif. Refactor về OCP. Đo:
- Số dòng method `score()` cũ
- Số class mới sau refactor
- Số dòng mỗi class

So sánh với phiên bản cũ về test isolation: viết test cho "weighted" trong cả 2 phiên bản — phiên bản nào test ngắn hơn, vì sao?

### Mức 3 — Khó (architect-level)

Yêu cầu mới: "Một số quiz cần *adaptive scoring* — điểm phụ thuộc vào số submission trước đó của user (penalize repeat attempts)". 

Thiết kế:
1. Đây có phải variant của axis "scoring rule" không, hay là axis mới?
2. Nếu cùng axis: impl thẳng `AdaptiveScorer(QuizScorer)` — nhưng `score(answers)` không có history. Thay đổi interface signature?
3. Nếu axis mới: thêm tham số `Context` chứa history → áp dụng cho mọi scorer (vi phạm OCP nếu sửa interface đã đóng).
4. Lựa chọn 3rd: dùng Decorator `HistoryAwareDecorator(inner_scorer, history_repo)` — wrap, không đổi interface.

Phân tích trade-off mỗi cách. Pick 1 và implement. Note: lựa chọn của bạn nên ưu tiên *không sửa interface đã đóng*. Nếu bạn buộc phải sửa interface, hãy giải thích vì sao.

### Mức 4 — Mở rộng neuroscience

Nghiên cứu **Hippocampal pattern separation** chi tiết hơn:
- Bakker et al. 2008 (*Science*): Behavioral Pattern Separation Task — fMRI cho thấy CA3/DG selective cho lure detection.
- Yassa & Stark 2011 review.

Câu hỏi:
1. Vì sao não cần *expansion recoding* (DG có 10× neuron)? Tại sao không dùng cùng số neuron và "tinh chỉnh" weight (như NN truyền thống)?
2. Liên hệ với code: vì sao OCP cần *abstraction layer* (thêm 1 tầng indirection)? Tại sao không dùng cùng 1 class và "thêm method"?
3. **Catastrophic forgetting trong NN**: tại sao Adam optimizer alone không giải được? Liên hệ: tại sao "convention" và "code review" alone không giải OCP — cần *mechanism* (interface + DI)?

Trả lời 4–6 câu cho mỗi câu, liên kết neuro ↔ code.

---

## SAU LESSON NÀY

Lesson 25 đã đặt mọi thứ vào polymorphic dispatch. Nhưng có 1 cạm bẫy: nếu một subclass *vi phạm contract của interface* (raise exception lạ, return type khác, side effect khác), caller buộc phải `isinstance()` check → OCP collapse, if/elif quay lại.

Đó là vấn đề **LSP — Liskov Substitution Principle** — Lesson 26. LSP là điều kiện *behavioral* để OCP không vỡ. SRP đặt nền cấu trúc, OCP đặt nền extension, LSP đảm bảo extension không *lừa* caller.

> **Nhớ một câu**: OCP không phải "đừng sửa code". OCP là "**axis of change** đã rõ → đặt extension point đúng nơi → variant mới đến qua extension point, không qua mổ xẻ**".
