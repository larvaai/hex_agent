# Lesson 24 — SRP (Single Responsibility Principle)
## Functional Specialization — V1 chỉ thấy edge, MT chỉ thấy motion, Broca chỉ nói, Wernicke chỉ hiểu

---

## TÓM TẮT MỘT DÒNG

**SRP** = một class chỉ có **MỘT lý do để thay đổi** — nghĩa là chỉ phục vụ **MỘT actor/stakeholder**. Đây không phải "1 class làm 1 việc nhỏ", mà là "1 class chỉ trả lời cho 1 nhóm người yêu cầu".

> Não bộ phân chia chức năng cực kỳ nghiêm: V1 (primary visual cortex) chỉ trích xuất *edge orientation*, V4 chỉ *color*, MT/V5 chỉ *motion*, FFA chỉ *face*, Broca chỉ *speech production*, Wernicke chỉ *speech comprehension*. Tại sao không gộp một "neuron đa năng" làm hết? Vì **catastrophic interference**: khi cùng synapse cùng neuron tham gia quá nhiều task, weight update của task A đè lên weight task B → cả hai task hỏng. Functional specialization là cách não né interference, đồng thời đạt **graceful degradation** — mất V4 thì hệ thống mất nhận màu nhưng vẫn nhận hình, mất Broca thì mất khả năng nói nhưng còn hiểu (Broca's aphasia khác Wernicke's aphasia rõ rệt). SRP là functional specialization phiên bản code.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Khi một class phình to làm nhiều việc, mỗi lần một stakeholder yêu cầu thay đổi (CFO đổi cách tính lương, DBA đổi schema, Marketing đổi template email), bạn buộc phải mở **cùng một file** → 3 nguy cơ:

1. **Merge conflict liên tục** — 3 team đụng vào 1 file song song.
2. **Regression chéo** — sửa cho marketing vô tình làm sai logic kế toán.
3. **Test phình to** — muốn test 1 tính năng nhỏ phải mock cả DB, email, leaderboard, formatter.

Đây là God Object / God Class — anti-pattern phổ biến nhất trong code base trưởng thành. SRP là *vaccine*.

**Định nghĩa Robert C. Martin (gốc, *Clean Architecture* 2017)**:

> *"A module should be responsible to one, and only one, **actor**."*

Chú ý: là **actor** (người/nhóm yêu cầu thay đổi), không phải "việc". Một class có thể có 5 method, 100 dòng vẫn OK SRP nếu cả 5 method cùng phục vụ một actor — vì khi đó chỉ có một nhóm người ra lệnh thay đổi nó.

### 1.2. Misconception phổ biến (rất hay sai)

| Hiểu sai | Hiểu đúng |
|----------|-----------|
| "Mỗi class chỉ có 1 method" | Có thể nhiều method, miễn cùng actor |
| "Chia càng nhỏ càng tốt" | Chia quá nhỏ → Shotgun Surgery (đổi 1 yêu cầu phải sửa 10 file) |
| "Class to là vi phạm SRP" | Class to không nhất thiết vi phạm; class **đa actor** mới vi phạm |
| "Một class = một thực thể domain" | Một thực thể domain có thể cần tách 2-3 class theo actor (Employee → Pay/Hours/Persistence) |

### 1.3. Neuroscience analogy — Functional Specialization

Não người chia thành **~180 vùng cytoarchitectural** (Glasser et al., 2016, *Nature*) — mỗi vùng có cấu trúc tế bào riêng, kết nối riêng, chức năng riêng. Đây không phải tiến hoá tình cờ; nó là *giải pháp tối ưu* cho 3 vấn đề kỹ thuật của não.

**Vấn đề 1 — Catastrophic interference**: Trong neural network nhân tạo (và sinh học), nếu bạn dùng cùng synapse học task A rồi task B, weight cập nhật cho B sẽ overwrite weight đã học cho A (McCloskey & Cohen, 1989). Não tránh điều này bằng **module hoá** — task A dùng synapse vùng X, task B dùng synapse vùng Y, không đè nhau.

**Vấn đề 2 — Wiring cost**: Não có volume hữu hạn (~1.4 L). Nếu mọi neuron phải nói chuyện với mọi neuron khác, white matter sẽ chiếm hơn 90% thể tích (chỉ còn 10% cho cell body). Phân vùng cho phép **kết nối local mật độ cao** + **kết nối liên vùng thưa** — minh họa kinh điển của *small-world network*.

**Vấn đề 3 — Modular learning**: Mỗi vùng có *learning rule* tối ưu cho loại tín hiệu của nó. V1 dùng *Hebbian + lateral inhibition* để học edge filter; cerebellum dùng *climbing fiber error signal* (LTD) để học motor calibration; basal ganglia dùng *dopamine reward prediction error* để học action value. Một "rule chung" không phù hợp với cả ba.

**Một số ví dụ functional specialization và bằng chứng thiệt hại khi vi phạm**:

| Vùng | Chức năng đơn nhất | Bằng chứng thiệt hại (lesion / disorder) |
|------|---------------------|-------------------------------------------|
| **V1 (calcarine cortex)** | Edge orientation, retinotopic map | Lesion → cortical blindness theo hemifield đối diện. Chỉ mất "hình ảnh có ý thức"; reflex vẫn còn (blindsight) |
| **V4** | Color, form | Achromatopsia mắc phải — thấy hình nhưng đời như TV trắng đen |
| **MT/V5** | Motion | Akinetopsia (Zihl 1983) — patient LM thấy nước rót như "ảnh tĩnh nối tiếp", không thấy đang chảy |
| **FFA (fusiform face area)** | Face recognition | Prosopagnosia — không nhận được mặt người (kể cả người thân), nhưng nhận đồ vật bình thường |
| **Broca (BA 44/45)** | Speech production, syntax | Broca's aphasia — hiểu được câu, nhưng nói không trôi chảy, mất syntax |
| **Wernicke (BA 22)** | Speech comprehension | Wernicke's aphasia — nói trôi chảy nhưng vô nghĩa, không hiểu người khác nói gì |
| **Hippocampus** | Episodic memory encoding | H.M. (Scoville & Milner 1957) — sau cắt hippocampus 2 bên, không thể hình thành ký ức mới (anterograde amnesia), nhưng IQ + ký ức cũ + skill learning vẫn nguyên |

H.M. là minh chứng SRP đẹp nhất: *xoá MỘT module, các module khác vẫn chạy*. Nếu não là God Object, mất hippocampus phải mất luôn IQ + ngôn ngữ + vận động — nhưng không phải vậy. **Đó là power của functional specialization, là power của SRP.**

#### 5 chiều của analogy

| Chiều | Trong não | Trong code |
|-------|-----------|------------|
| **Cấu tạo** | Mỗi vùng có cytoarchitecture riêng (V1 có cell layer 4 dày, MT có nhiều magnocellular, Broca có pyramidal cell L3 đặc trưng) | Mỗi class có state + method tương ứng với 1 axis trách nhiệm |
| **Vị trí** | Vùng có toạ độ giải phẫu cố định (boundary đo được) | Class ở module/package boundary rõ ràng |
| **Chức năng** | Một computation type duy nhất (edge / motion / face / speech production / episodic encoding) | Một actor / stakeholder duy nhất |
| **Kết nối** | White matter tracts có topology định trước (visual stream: V1→V2→V4→IT cho ventral; V1→MT→MST cho dorsal) | Constructor injection / interface boundary; collaborator được khai báo tường minh |
| **Ý nghĩa** | Tránh interference, giảm wiring cost, cho phép graceful degradation | Tránh ripple change, tăng testability, parallel development, lesion (xoá class) không hỏng cả hệ |

### 1.4. Khi nào DÙNG (SRP áp dụng nghiêm)

- Class > 200 dòng và bạn vẫn thấy "còn việc gì đó nó nên làm".
- Có 2+ stakeholder/team tác động vào cùng 1 class (CFO + DBA + Marketing).
- Test 1 method cần mock 4+ collaborator.
- Tên class chứa "And", "Manager", "Helper", "Util", "Service" generic.
- Method có tên kết hợp 2 động từ: `validateAndSave`, `parseAndNotify`.
- File git blame cho thấy 3+ team commit liên tục cùng 1 file 6 tháng qua.

### 1.5. Khi nào KHÔNG DÙNG (SRP quá tay)

- Script throwaway, prototype thử nghiệm < 100 dòng.
- 2 trách nhiệm thật sự cùng 1 actor (ví dụ: `Order.calculateTotal()` và `Order.applyDiscount()` cùng phục vụ team kinh doanh — đừng tách giả tạo).
- Class nhỏ < 30 dòng, cohesion đã cao tự nhiên.
- Tách dẫn đến **anaemic domain model** — entities chỉ còn getter/setter, mọi logic dồn vào service.
- Khi tách làm sửa 1 yêu cầu phải đụng 10 file → đó là **Shotgun Surgery**, đối ngược của SRP nhưng cũng tệ tương đương.

> **Heuristic vàng**: SRP không phải "tách càng nhiều càng tốt". SRP là **chia theo trục actor**. Nếu bạn không nêu được tên actor cụ thể của mỗi class sau refactor, có thể bạn đang chia sai trục.

---

## MỨC 2 — ALGORITHM / CẤU TRÚC

### 2.1. Vai diễn

Một class vi phạm SRP có nhiều **axis of change** đan xen. Refactor SRP là quá trình nhận diện các axis và tách theo từng axis:

```
Trước (vi phạm):                  Sau (tuân thủ):

  ┌─────────────────────┐          ┌──────────────────┐  ← Actor A (Validation team)
  │   QuizService       │          │  QuizValidator   │
  │  (God Class)        │          └──────────────────┘
  │                     │          ┌──────────────────┐  ← Actor B (Curriculum team)
  │  validate()  ←──── A│          │  QuizScorer      │
  │  score()     ←──── B│          └──────────────────┘
  │  save()      ←──── C│  ──→     ┌──────────────────┐  ← Actor C (DBA / Data team)
  │  email()     ←──── D│          │ SubmissionRepo   │
  │  rank()      ←──── E│          └──────────────────┘
  │  format()    ←──── F│          ┌──────────────────┐  ← Actor D (Comms / Marketing)
  └─────────────────────┘          │  EmailNotifier   │
        ↑                          └──────────────────┘
   6 actor cùng kéo                ┌──────────────────┐  ← Actor E (Product / gamification)
   1 class — bom hẹn giờ           │ LeaderboardSvc   │
                                   └──────────────────┘
                                   ┌──────────────────┐  ← Actor F (Frontend)
                                   │ ResponseFormatter│
                                   └──────────────────┘
                                   ┌──────────────────┐  ← Orchestrator (workflow only)
                                   │ QuizSubmissionSvc│  ← biết WORKFLOW, không biết IMPLEMENTATION
                                   └──────────────────┘
```

### 2.2. Luồng điều khiển

Trước (God Class) — workflow **đan vào** logic:
```
QuizService.submit(user, answers):
    [validation logic 20 dòng]
    [scoring logic 30 dòng]
    [SQL hard-coded 25 dòng]
    [SMTP setup + template 20 dòng]
    [leaderboard mutation 15 dòng]
    [JSON formatting 10 dòng]
```
→ Nếu Marketing muốn thêm SMS bên cạnh email, phải mở file này, đụng vào giữa, có nguy cơ phá scoring.

Sau (SRP) — workflow là **một đường thẳng** gọi 6 collaborator:
```
QuizSubmissionService.submit(user, answers):
    validator.validate(answers)
    score_result = scorer.score(answers)
    submission = repo.save(user, score_result)
    notifier.notify(user, score_result)        ← chỉ class này biết về email
    leaderboard.update(user, score_result.points)
    return formatter.format(user, score_result, leaderboard.rank_of(user))
```
→ Marketing muốn SMS: tạo `SmsNotifier` implement cùng interface, swap. Không đụng class khác.

### 2.3. Biến trạng thái

| State | God class | Sau SRP |
|-------|-----------|---------|
| `db_connection` | Field của class to | Field của `SubmissionRepository` only |
| `leaderboard_dict` | Field của class to | Field của `LeaderboardService` only |
| `answer_key` | Hard-coded trong method | Constructor param của `QuizScorer` |
| `smtp_config` | Hard-coded trong method | Field của `EmailNotifier` only |

→ Mỗi class **sở hữu** state nó cần, không thừa.

### 2.4. Invariants sau refactor

Một refactor SRP đúng phải thoả 4 invariant:

1. **Đặt tên actor**: với mỗi class mới, bạn nêu được câu "Class này thay đổi khi nhóm X yêu cầu" — *nhóm X cụ thể*, không phải "ai đó".
2. **Method cohesion**: mọi public method của class cùng đụng vào ≥ 1 field của class (không phải static helper rải rác).
3. **Test cô lập được**: viết test cho `QuizScorer` không cần khởi tạo DB, SMTP, leaderboard.
4. **Workflow class mỏng**: orchestrator (`QuizSubmissionService`) **không có business logic** — chỉ gọi collaborator theo thứ tự.

### 2.5. Đo cohesion — LCOM ngắn gọn

**LCOM (Lack of Cohesion of Methods)** là metric đếm "method nào dùng field nào". LCOM cao = method không chia sẻ field = class chia làm 2 cluster ngầm = vi phạm SRP.

Cách tính LCOM4 đơn giản:
- Tạo graph: node = method, edge = "2 method cùng dùng ít nhất 1 field hoặc gọi nhau".
- Đếm số connected component.
- LCOM4 = số component. **LCOM4 = 1** là cohesive; **LCOM4 ≥ 2** là dấu hiệu vi phạm SRP.

Ví dụ `QuizService` God:
- `validate()` dùng `answer_key`
- `score()` dùng `answer_key`
- `save()` dùng `db_path`
- `email()` dùng `smtp_config`
- `rank()` dùng `leaderboard_dict`

→ 5 component (validate-score, save, email, rank, format) → LCOM4 = 5 → cảnh báo đỏ.

Sau refactor: mỗi class có LCOM4 = 1.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode — refactor recipe

```
INPUT:  one God class C with methods M1..Mn and fields F1..Fk
OUTPUT: a set of cohesive classes {C1..Cm} + one orchestrator O

step 1: list all stakeholders/actors who could request a change
step 2: assign each method Mi to exactly one actor Aj
        (if a method serves 2 actors, split it)
step 3: for each actor Aj:
            create class Cj
            move methods assigned to Aj into Cj
            move fields used only by those methods into Cj
            promote shared fields to constructor parameters
step 4: identify the workflow that originally lived in C
        create orchestrator O whose only job is to call C1..Cm
        in the right order
step 5: introduce interfaces / abstract base classes for collaborators
        whose implementation might vary (Notifier, Repository...)
step 6: update tests:
            unit tests for each Ci in isolation
            one integration test for O wiring everything together
```

### 3.2. Python — file `24_srp.py`

Code đầy đủ trong `24_srp.py` cùng folder. File chứa:

1. **Phần 1 — `quiz_god.py` style** (intentionally bad): God class `QuizGodService` ~150 dòng làm 6 việc.
2. **Phần 2 — refactor SRP**: 6 class + 1 orchestrator, mỗi class < 30 dòng, mỗi class có docstring nêu *actor*.
3. **Demo 1 — output identical**: cùng input, cùng output JSON, chứng minh refactor không đổi behaviour.
4. **Demo 2 — change request**: đổi scoring rule (negative marking cho câu sai). God class phải sửa giữa method dài; SRP chỉ cần `NegativeMarkingScorer` mới rồi swap.
5. **Demo 3 — testability**: test `QuizScorer` không khởi tạo SQLite, không gửi email, không cần leaderboard. Test God class cần mock cả 4 thứ.
6. **Demo 4 — Ellumm extension (bài tập 4 mức gợi ý)**: thêm `AnalyticsTracker` mới mà *không sửa* class hiện có — đặt nền cho lesson 25 (OCP).

Chạy:
```bash
python 24_srp.py
```

Sẽ in ra lần lượt 4 demo với heading rõ ràng.

---

## 5 CHIỀU — BẢNG SO SÁNH IN NÃO VS IN CODE

| Chiều | Não (functional specialization) | Code (SRP) |
|-------|----------------------------------|------------|
| **Cấu tạo** | Một vùng = một loại tế bào chiếm ưu thế + cytoarchitecture đặc trưng (V1 cell L4 dày, FFA pyramidal đặc) | Một class = một bộ field + method phục vụ một axis trách nhiệm |
| **Vị trí** | Vùng có boundary giải phẫu rõ (đo bằng cytoarchitecture, connectivity, function) | Class ở module / package boundary tường minh; import list hẹp |
| **Chức năng** | Một computation type (edge orientation, color, motion, face, speech production...) | Một actor / lý do thay đổi (CFO, DBA, Marketing, Frontend...) |
| **Kết nối** | White matter tract có topology cố định; ventral stream vs dorsal stream tách bạch | Collaborator inject qua constructor; interface định ranh giới; không gọi class khác qua import động |
| **Ý nghĩa** | Tránh catastrophic interference, giảm wiring cost, graceful degradation (lesion 1 vùng, vùng khác còn chạy) | Tránh ripple change, parallel development, test cô lập, replace 1 class không sập hệ |

---

## 3 LOẠI VÍ DỤ TRONG CODE

### Ví dụ 1 — Vận hành thường (happy path)

`QuizSubmissionService` orchestrate 6 collaborator. User submit → validate → score → save → notify → update rank → format. Mỗi bước **gọi 1 method, 1 dòng**, không có business logic ở orchestrator.

```python
def submit(self, user_id, answers):
    self.validator.validate(answers)
    score = self.scorer.score(answers)
    self.repo.save(user_id, score)
    self.notifier.notify(user_id, score)
    self.leaderboard.update(user_id, score.points)
    rank = self.leaderboard.rank_of(user_id)
    return self.formatter.format(user_id, score, rank)
```

→ Workflow đọc như **văn xuôi**: ai cũng hiểu nó làm gì, không cần biết chi tiết bất kỳ collaborator.

### Ví dụ 2 — Hỏng/thiếu (vi phạm SRP, hậu quả cụ thể)

God class:
```python
def submit(self, user_id, answers):
    # Marketing muốn đổi email template → mở file này
    # CFO muốn đổi scoring rule → mở file này
    # DBA muốn đổi schema → mở file này
    # Frontend muốn đổi response format → mở file này
    ... 150 dòng lẫn lộn ...
```

Hậu quả thực tế đo được:
- **Merge conflict**: 4 PR đổi 4 actor cùng tuần đụng nhau ở vùng 50–80 của method.
- **Test phình**: viết test cho rule scoring mới phải patch `sqlite3.connect`, `smtplib.SMTP`, init `leaderboard_dict` — 30 dòng setUp cho 1 dòng assert.
- **Regression chéo**: PR đổi email template thay đổi format string `"%d/%d"` → format response đầu ra cũng cùng format string → frontend bể.
- **Onboard chậm**: dev mới mở file thấy 150 dòng, không biết đường nào trước đường nào sau, đọc 30 phút mới hiểu.

### Ví dụ 3 — Ứng dụng Ellumm (refactor mini-project)

`quiz_god.py` baseline (intentionally bad) → refactor thành 6 class theo trục actor:

| Class | Actor | Lý do thay đổi điển hình |
|-------|-------|--------------------------|
| `QuizValidator` | API Gateway / Contract team | Đổi định dạng request, validation rule mới |
| `QuizScorer` | Curriculum / Education team | Đổi cách tính điểm (weighted question, negative marking, partial credit) |
| `SubmissionRepository` | DBA / Data team | Đổi schema, đổi storage engine (SQLite → Postgres → Mongo) |
| `EmailNotifier` | Marketing / Comms team | Đổi template, thêm SMS, đa ngôn ngữ |
| `LeaderboardService` | Product / Gamification team | Đổi cách tính rank, top-N cutoff, decay |
| `ResponseFormatter` | Frontend team | Đổi shape JSON, thêm field mới |
| `QuizSubmissionService` | (không actor — chỉ workflow) | Chỉ đổi khi *thứ tự bước* đổi (rất hiếm) |

→ Ánh xạ team ↔ class 1-1. PR review router của bạn (CODEOWNERS) cũng cấu hình theo class này.

---

## SO SÁNH PATTERN LÂN CẬN

| Pattern | Đặc điểm | Khi gặp |
|---------|----------|---------|
| **SRP** | 1 class = 1 actor (lý do thay đổi) | Class to, đa stakeholder |
| **ISP** (Lesson 27) | 1 interface = 1 client perspective | Class lớn ép client phụ thuộc method thừa |
| **Cohesion (high cohesion principle)** | Method dùng chung field | Diễn đạt khác của SRP, đo được bằng LCOM |
| **God Object** (anti-pattern) | Cực điểm vi phạm SRP | Class > 500 dòng, > 20 method, đụng vào 5+ actor |
| **Shotgun Surgery** (anti-pattern) | Phản đề: tách quá nhiều, đổi 1 yêu cầu phải đụng 10 file | Khi SRP áp quá tay sai trục |
| **Anaemic Domain Model** (anti-pattern) | Tách logic ra hết khỏi entity, entity chỉ còn field | Khi SRP áp dụng làm domain mất hành vi |
| **Facade** (GoF) | 1 class che N class phức tạp | Khi cần entry point đơn giản — orchestrator của ta gần Facade |
| **Strategy** (GoF) | Swap thuật toán | Sau SRP, từng class (Scorer, Notifier) thường implement Strategy interface |

**Quan hệ trong SOLID**:
- **SRP** + **DIP** = 2 cột trụ chính. SRP nói "tách theo actor"; DIP nói "domain phụ thuộc abstraction, không phụ thuộc concrete". Áp dụng cùng → architecture sạch đáng kể.
- **OCP** là *kết quả* của SRP đúng + LSP đúng + ISP đúng + DIP đúng. SRP đặt nền cho OCP: thêm actor mới = thêm class mới, không sửa class cũ.

---

## TRADE-OFFS

| Trade-off | Chi phí | Lợi ích |
|-----------|---------|---------|
| File count↑ | 1 file → 7 file (+ 6 dependency wiring) | Test cô lập, parallel work |
| Boilerplate constructor | 6 param trong `__init__` của orchestrator | Dependency tường minh, dễ mock |
| Cognitive load đầu tiên | Dev mới phải hiểu nhiều class | Mỗi class nhỏ, đọc < 30s/class |
| Indirection | Để hiểu workflow phải nhảy qua 6 file | Workflow ở orchestrator đọc như văn xuôi |
| Performance (rất nhỏ) | Vài extra method call | Negligible cho hầu hết domain |
| Risk over-SRP | Tách quá nhỏ → Shotgun Surgery | Cần dừng lại khi tên actor không rõ ràng |

**Quy tắc**: chấp nhận trade-off này khi project có 2+ team đụng codebase + lifetime > 6 tháng. Với prototype < 1 tháng + 1 dev, SRP nhẹ tay (gộp 2-3 axis OK).

---

## CHECKLIST TRƯỚC KHI MERGE PR

- [ ] **Đặt tên actor**: cho mỗi class mới/sửa, viết comment "Actor: {team/role cụ thể}". Không viết được = chưa hiểu trục tách.
- [ ] **Class < 200 dòng** (rule of thumb). Nếu > 200, có lý do gì giữ to?
- [ ] **Mỗi public method dùng ≥ 1 instance field** — nếu không dùng field nào, nó là static helper, có thể tách module riêng.
- [ ] **Không có method tên `xxxAndYyy`** — dấu hiệu 2 trách nhiệm trong 1.
- [ ] **Tên class không generic** — tránh "Manager", "Helper", "Util", "Service" trừ khi có prefix đặc thù (`QuizSubmissionService` OK, `Service` không).
- [ ] **Test cô lập**: viết được test cho class mà chỉ mock 0–1 collaborator. Mock 4+ = nghi vấn.
- [ ] **Constructor < 5 dependency**. > 5 = có thể class đang là orchestrator, hoặc thừa actor.
- [ ] **Git blame 6 tháng**: file < 3 team commit. > 3 team = cảnh báo đỏ.
- [ ] **CODEOWNERS** ánh xạ 1-1 class ↔ team. Nếu 2 team đều owner cùng class → split.
- [ ] **Không Shotgun Surgery**: requirement test tưởng tượng "thêm loại quiz mới" — phải sửa bao nhiêu file? > 5 = tách quá manh mún.

---

## BÀI TẬP 4 MỨC

### Mức 1 — Cơ bản
Mở `24_srp.py`, đọc `QuizGodService`. List 6 actor mỗi method phục vụ. So sánh list của bạn với phần SRP refactor và giải thích bất kỳ chỗ nào khác.

### Mức 2 — Trung bình
Thêm yêu cầu: "Mọi submission phải đẩy event vào hệ analytics (Mixpanel-style)" — đại diện cho team Analytics. Trong cả phiên bản God và phiên bản SRP, làm thế nào để thêm? Đo:
- Số dòng phải sửa trong class hiện có (target: 0 cho phiên bản SRP)
- Số class mới
- Số test phải đổi

### Mức 3 — Khó (architect-level)
Cho 3 method khó phân loại sau, identify actor và quyết định đặt vào class nào (hoặc tách class mới):
1. `bulkRecalculateScores(date_range)` — recompute điểm cho tất cả submission trong khoảng. Curriculum team yêu cầu vì đổi rule. *Hint: actor là Curriculum, nhưng có operational concern về batch processing.*
2. `exportToCSV(submissions)` — xuất report cho external partner. *Hint: actor mới — Reporting / BI team. Đừng nhét vào ResponseFormatter (Frontend).*
3. `notifyAdminIfFailRateHigh()` — kích hoạt alert khi fail rate > 30%. *Hint: actor là Operations / SRE team, không phải Marketing dù dùng email/Slack channel.*

Viết tên class mới + comment Actor cho mỗi method.

### Mức 4 — Mở rộng neuroscience
Trong não người có "vùng" gọi là **Default Mode Network (DMN)** — bật khi không làm task cụ thể nào (mind-wandering, tự reflection). DMN gồm: medial PFC, posterior cingulate, angular gyrus, hippocampus.

Câu hỏi: DMN có vi phạm functional specialization không? (Tức là có phải God Region không?) Tranh luận:
- Một mặt: nó tham gia mọi loại "mind-wandering, prospection, theory of mind, memory recall" → có vẻ đa năng.
- Mặt khác: tất cả những việc đó có cùng trục — *internally-generated cognition* (suy nghĩ không bám stimulus ngoài) → đó có thể là **một actor duy nhất**.

Áp dụng định nghĩa SRP của Robert Martin (1 actor): DMN có vi phạm SRP không? Trả lời ngắn 4–6 câu. Liên hệ với câu hỏi trong code: "khi tôi gặp một class giống `DefaultModeService` trông đa năng, làm sao biết nó đang vi phạm SRP hay là cohesive?"

---

## SAU LESSON NÀY

Lesson 25 (OCP) sẽ dùng nguyên kết quả refactor của lesson này (`quiz_v24.py`) làm điểm xuất phát. Sau khi đã tách actor (SRP), câu hỏi tiếp là: *thêm actor mới có sửa class cũ không?* — đó là OCP. Hai lesson đi cặp như SRP + DIP.

> **Nhớ một câu**: SRP không phải "làm 1 việc". SRP là "**ai có quyền yêu cầu đổi class này?**" — câu trả lời phải có **đúng MỘT tên team**.
