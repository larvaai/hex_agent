# Lesson 22 — Template Method Pattern
## LTP Protocol — Khung cố định, từng synapse có hook riêng

---

## TÓM TẮT MỘT DÒNG

**Template Method** = base class định nghĩa _skeleton_ (thứ tự cố định) của một thuật toán; subclass override các _hook_ (bước có thể thay đổi) — skeleton không đổi, chi tiết bước thì thay đổi.

> Mọi synapse trong não dùng để học (LTP — long-term potentiation) đều theo **một protocol cố định 8 bước**: glutamate release → NMDA receptor mở (khi đồng thời có depolarization) → Ca²⁺ tràn vào → kích hoạt kinase cascade (CaMKII, PKA...) → phosphorylate AMPA receptor → AMPA insertion vào màng → synapse mạnh lên → late-phase: gene transcription + protein synthesis. **Khung này không thay đổi** từ hippocampal CA1 đến cerebellar Purkinje đến cortical pyramidal. Nhưng từng synapse có **subunit khác** (NR2A vs NR2B), **kinase mix khác**, **threshold khác**. Đó chính là Template Method: pipeline cố định, hook tinh chỉnh.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Bạn có **một thuật toán có cấu trúc cố định**, nhưng vài bước cần customize theo loại object. Nếu chỉ có 1 loại — viết thẳng. Khi có nhiều loại với **flow giống** mà **vài bước khác**, có 3 lựa chọn:

1. **Copy-paste** thuật toán cho mỗi loại, sửa vài bước → trùng lặp, sửa skeleton ở nhiều chỗ.
2. **`if/elif` trong skeleton** → 200 dòng nhồi mọi case. Thêm loại = sửa skeleton.
3. **Template Method**: base class viết skeleton 1 lần, expose vài method abstract/hook. Subclass chỉ implement hook → tái sử dụng skeleton, không lặp.

Đặc trưng:
- **Hollywood principle**: "Don't call us, we'll call you" — base class gọi hook của subclass, không phải chiều ngược lại.
- **Skeleton là contract**: subclass không thay đổi thứ tự bước, chỉ chi tiết.
- **Hook vs primitive operation**: primitive (abstract, must implement) vs hook (default, optionally override).

### 1.2. Neuroscience analogy — LTP (Long-Term Potentiation)

LTP là cơ chế **khoa học thần kinh nền tảng của học và nhớ**, được Bliss và Lømo phát hiện 1973 ở hippocampus. Mọi sự kiện học ở mức synapse đều đi qua protocol này:

**Skeleton 8 bước (cố định cho mọi synapse có thể LTP)**:
1. **Pre-synaptic activation**: action potential tới axon terminal → glutamate release vào synapse cleft.
2. **Post-synaptic depolarization**: nếu màng sau synapse cũng đang depolarize → Mg²⁺ block ở NMDA receptor được "tống ra".
3. **NMDA gate opens**: NMDA receptor cho phép Ca²⁺ + Na⁺ chảy vào (chỉ khi 2 điều kiện đồng thời — đây là _Hebbian coincidence detection_).
4. **Ca²⁺ influx**: tăng Ca²⁺ nội bào tới ngưỡng.
5. **Kinase cascade activation**: Ca²⁺ kích hoạt CaMKII (phổ biến nhất) + PKA + PKC.
6. **AMPA receptor phosphorylation**: kinase phosphorylate AMPA → tăng độ dẫn.
7. **AMPA insertion**: vesicle chứa AMPA receptor merge vào màng → tăng số lượng receptor.
8. **Late-phase LTP** (sau giờ): gene transcription (CREB) → protein synthesis → structural change (dendritic spine grow).

Nhưng từng vùng não có **hook riêng**:

| Synapse | Skeleton | Hooks (khác biệt) |
|---------|----------|-------------------|
| **Hippocampal CA1** | 8 bước | NMDA NR2B dominant; CaMKII + PKA; LTP nhanh, mạnh — short-term to intermediate memory |
| **Cerebellar Purkinje** | 8 bước (LTD ngược) | mGluR + voltage-gated Ca²⁺; PKC dominant; **LTD** (depression) nhiều hơn LTP — motor calibration |
| **Cortical pyramidal L5** | 8 bước | NR2A dominant; mix CaMKII + PKC; threshold cao — chỉ học khi salience đủ |
| **Amygdala BLA** | 8 bước | NR2B + L-type Ca²⁺ channel; CaMKII + PKA mạnh; nhanh, lâu dài — fear conditioning |
| **Striatum (NAcc)** | 8 bước | dopamine modulate; D1/D2 receptor là hook — reward learning |

→ Cùng skeleton (NMDA → Ca²⁺ → kinase → AMPA insertion → strengthen), nhưng **NMDA subunit, kinase mix, threshold, dopamine modulation** là _hooks_ tuỳ vùng. Bạn không thể skip step (skeleton fixed), nhưng từng synapse có "tinh chỉnh" để phù hợp với role của nó.

#### 5 chiều của analogy

| Chiều      | Trong não                                                                              | Trong code                                                                  |
|------------|----------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| Cấu tạo    | NMDA → Ca²⁺ → kinase cascade → AMPA insertion (skeleton); subunit composition + kinase mix khác per synapse | Template Method (skeleton) + abstract/hook methods (customizable steps) |
| Vị trí     | Skeleton ở mọi synapse plastic; hooks định bởi loại neuron + vùng não                  | Skeleton trong base class; hooks override trong subclass                    |
| Chức năng  | Cùng outcome (synapse strengthen/weaken) qua cùng pipeline, biến điểm khác             | Cùng kết quả qua cùng flow, hành vi biến điểm tuỳ subclass                  |
| Kết nối    | Bước phụ thuộc bước trước; không skip; thứ tự fixed bởi cơ chế hoá học                 | Skeleton call hook theo thứ tự cố định; subclass không reorder              |
| Ý nghĩa    | Cho phép tiến hoá thêm vùng não mới mà giữ nguyên cơ chế học lõi                       | Cho phép thêm subclass mới với skeleton tái sử dụng                         |

### 1.3. Khi nào DÙNG

- Có **flow cố định** (sequence cụ thể) với vài bước cần customize.
- Có **nhiều biến thể** của cùng thuật toán, chia sẻ phần lớn logic.
- Cần **enforce thứ tự** các bước (subclass không skip / reorder).
- **Framework / library**: cho user extend qua subclass + override hook (Django views, Spring servlets, JUnit setUp/tearDown).
- Workflow / build pipeline với phases có thể custom.
- ETL pipeline: extract → transform → load, với từng nguồn cần transform khác.

### 1.4. Khi nào KHÔNG DÙNG

- Bước có thể thay đổi nhiều thứ tự / skip → không phải Template Method, dùng **Strategy / Pipeline / Chain**.
- Subclass cần thay đổi nhiều skeleton → fragile base class. Dùng **composition / Strategy** thay.
- Đơn giản chỉ cần đổi 1 đoạn nhỏ → **Strategy / closure** đủ, không cần inheritance.
- Khi không có gì thực sự shared giữa các "subclass" — chỉ là interface cho 1 thuật toán → đó là Strategy.
- Khi base class phải biết rất nhiều về subclass (`isinstance` check) → pattern bị phá.

### 1.5. Cảnh báo architect

> **Fragile base class**: thay đổi base class skeleton có thể phá tất cả subclass. Đây là điểm yếu nội tại của Template Method (do dùng inheritance). Khi skeleton chưa stable hoặc team lớn → cân nhắc **Strategy** (composition) thay vì Template Method.

> **Inheritance debt**: deep inheritance hierarchy (3+ level) là code smell. Template Method nên giới hạn 1 base + N concrete subclass, không subclass-of-subclass.

> **"Favor composition over inheritance"** — quy tắc kinh điển. Template Method là một trong số ít trường hợp inheritance vẫn vincit composition: khi skeleton thật sự cố định và hook nhỏ.

---

## MỨC 2 — ALGORITHM

### 2.1. Vai diễn

```
┌────────────────────────────────────┐
│       AbstractClass                │
│ + template_method() <FINAL>        │  ← skeleton, không override
│   { step1(); step2_hook(); step3();│
│     step4_hook(); step5(); }       │
│ # step1()                          │  ← shared, không hook
│ # step3()                          │  ← shared
│ # step5()                          │  ← shared
│ + step2_hook() <abstract>          │  ← MUST override
│ + step4_hook()                     │  ← optional, có default
└────────────────────────────────────┘
                  △
                  │
         ┌────────┴───────────┐
┌─────────────────┐  ┌─────────────────┐
│ ConcreteClass A │  │ ConcreteClass B │
│ + step2_hook()  │  │ + step2_hook()  │
│ + step4_hook()  │  │  (uses default) │
└─────────────────┘  └─────────────────┘
```

- **template_method**: skeleton, **không** override. Trong Python convention `_template_method` hoặc dùng `@final` (Python 3.8+ typing).
- **Concrete operations**: shared logic, base class implement, không override.
- **Abstract operations** (primitive): subclass **bắt buộc** implement.
- **Hook operations**: có default, subclass optionally override.

### 2.2. Luồng điều khiển

```
client = HippocampalCA1()
client.induce_ltp(stimulus)
       │
       ▼ (template_method)
self.release_glutamate(stim)     ← shared
self.activate_nmda()             ← hook: NR2A vs NR2B subunit
self.calcium_influx()            ← shared (mostly)
self.activate_kinases()          ← hook: CaMKII / PKA / PKC mix
self.phosphorylate_ampa()        ← shared
self.insert_ampa()               ← hook: rate of insertion
self.maybe_late_phase_protein_synthesis()  ← hook: optional, threshold
       │
       ▼
return SynapseStrengthChange(delta=+0.45)
```

### 2.3. Biến trạng thái và bất biến

- Skeleton **không có state nội bộ** ngoài state truyền qua param.
- Subclass có thể có **state riêng** (dopamine level, baseline, last LTP time).
- **Invariant**: thứ tự gọi hook trong template_method **không thay đổi**. Subclass override hook nhưng không reorder.
- Hook **idempotent** trong scope một call. Không có side effect ngầm gọi hook khác.
- **Liskov substitution**: mọi subclass phải hành xử đúng theo contract của base — không phá invariant.

### 2.4. Biến thể

| Biến thể | Mô tả | Khi nào dùng |
|----------|-------|--------------|
| **Pure Template Method** | Skeleton + hooks qua inheritance | Pattern chuẩn |
| **Hook with hook condition** | `if self.should_step3(): step3()` | Bỏ qua bước có điều kiện |
| **Template + Strategy hybrid** | Hook là Strategy injected, không phải method override | Khi cần đổi runtime |
| **Functional Template Method** | Skeleton là function, hooks là callbacks | Pythonic, không cần class |
| **Multi-level template** | Base class có template, subclass có template con (tránh!) | Hệ thống phức tạp; dấu hiệu redesign |

### 2.5. Template Method vs Strategy — phân biệt rõ

| Khía cạnh | Template Method | Strategy |
|-----------|-----------------|----------|
| Cách compose | Inheritance | Composition |
| Khi đổi behavior | Compile-time (chọn class) | Runtime (đổi object) |
| Subclass biết về parent? | Có (inherit) | Không |
| Skeleton ở đâu | Base class fixed | Context có flow nhỏ + delegate |
| Open/Closed | Yếu hơn (fragile base) | Mạnh hơn |
| Pythonic | Trung bình | Tốt (closure, function) |

> **Quy tắc architect**: Bắt đầu với Strategy (composition). Khi nhận thấy skeleton thật sự fixed, có nhiều bước shared, hook ngắn → cân nhắc Template Method. Đừng dùng Template Method chỉ để có 1 hook duy nhất — đó là Strategy disguise.

### 2.6. Hollywood Principle

> "Don't call us, we'll call you."

Trong Template Method, base class **chủ động** gọi hook của subclass. Subclass thụ động chờ được gọi. Đây ngược lại với Strategy, nơi Context **chủ động** gọi Strategy.

Hệ quả thiết kế:
- Subclass không cần biết flow tổng thể.
- Subclass không thể bypass skeleton (trừ khi cố tình override skeleton — anti-pattern).
- Framework dễ enforce contract.

Đây là tinh thần của hầu hết framework: bạn extend `View`, `TestCase`, `Servlet`, `Component` — và framework gọi method bạn override, không phải bạn gọi framework.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
abstract class SynapticPlasticityProtocol:
    # Skeleton — không override
    def induce_ltp(stim):
        pre_state = self._release_glutamate(stim)        # shared
        if not self._coincidence_detected(pre_state):
            return SynapseUnchanged()                     # guard
        ca = self._activate_nmda(pre_state)               # HOOK
        kinase_state = self._activate_kinases(ca)         # HOOK
        ampa_change = self._modify_ampa(kinase_state)     # shared
        delta = self._strengthen_synapse(ampa_change)     # shared
        if self._should_consolidate(delta):               # HOOK
            self._late_phase_protein_synthesis()          # shared
        return SynapseStrengthChange(delta)
    
    # Shared
    def _release_glutamate(stim): ...
    def _coincidence_detected(state): ...
    def _modify_ampa(kinase): ...
    def _strengthen_synapse(d): ...
    def _late_phase_protein_synthesis(): ...
    
    # Hooks (abstract = must, optional = default ok)
    abstract def _activate_nmda(pre_state)         # NR2A / NR2B
    abstract def _activate_kinases(ca)             # CaMKII / PKA / PKC mix
    def _should_consolidate(delta): return delta > 0.3   # default

class HippocampalCA1 extends Protocol:
    def _activate_nmda(s): ...    # NR2B dominant, fast Ca²⁺
    def _activate_kinases(ca): ... # CaMKII heavy
    # use default _should_consolidate

class CerebellarPurkinje extends Protocol:
    def _activate_nmda(s): ...    # mGluR + voltage Ca²⁺
    def _activate_kinases(ca): ... # PKC heavy → LTD instead of LTP
    def _should_consolidate(d): return d < -0.3   # invert
```

### 3.2. Python — 3 ví dụ

Code chạy được ở `22_template_method.py`. Tóm tắt:

#### Ví dụ 1 — Vận hành thường: SynapticPlasticityProtocol với 3 subclass

3 synapse với cùng skeleton, hook khác:
- **`HippocampalCA1`**: NR2B-dominated NMDA, CaMKII heavy → fast strong LTP, threshold thấp.
- **`CerebellarPurkinje`**: mGluR + voltage Ca²⁺, PKC heavy → LTD (depression) thay vì LTP — same skeleton, ngược dấu.
- **`CorticalLayer5`**: NR2A-dominated, threshold cao — chỉ học khi stimulus mạnh + đồng thời.

Cùng `induce_ltp(stim)` API, kết quả khác hoàn toàn theo subclass. In ra log skeleton step-by-step để thấy cùng flow.

Đặc điểm code:
- `induce_ltp` là **template method** — đánh dấu `Final` (typing) hoặc convention.
- `_activate_nmda` và `_activate_kinases` là **abstract hooks** (must implement).
- `_should_consolidate` là **optional hook** với default.
- Mỗi subclass log ra giá trị NMDA subunit, kinase chính.

#### Ví dụ 2 — Hỏng / thiếu: 3 anti-pattern

- **2a — Subclass override skeleton**: subclass override `induce_ltp` để skip step → contract bị phá. Dùng `@final` (typing) hoặc raise nếu detect override.
- **2b — Fragile base class**: base class thêm step6 vào skeleton → subclass cũ không có hook handler → break. Demo cùng "thay đổi skeleton" và đo blast radius.
- **2c — Hook gọi hook khác / private method của base**: subclass tightly coupled với base internal. Refactor base = phá subclass.

#### Ví dụ 3 — Ứng dụng Ellumm: LessonProcessor template

Pipeline xử lý 1 lesson:
1. `_load_content()` — shared
2. `_preprocess_content()` — **HOOK** (markdown vs video vs interactive)
3. `_validate_prereqs()` — shared
4. `_present_to_user()` — **HOOK** (UI khác per type)
5. `_collect_response()` — **HOOK** (quiz vs reflection vs code submission)
6. `_grade()` — **HOOK** (auto vs manual vs peer)
7. `_save_progress()` — shared

3 subclass: `MarkdownLessonProcessor`, `VideoLessonProcessor`, `CodingLessonProcessor`. Cùng skeleton, hook khác → tái sử dụng load + validate + save.

#### Ví dụ 4 — Functional alternative

```python
def lesson_pipeline(load, preprocess, present, collect, grade, save):
    def run(lesson):
        c = load(lesson)
        c = preprocess(c)
        validate_prereqs(c)
        present(c)
        r = collect(c)
        s = grade(r)
        save(s)
    return run

markdown_pipeline = lesson_pipeline(
    load=read_md, preprocess=parse_md,
    present=render_html, collect=quiz_form,
    grade=auto_grade, save=db_save
)
```
Pythonic: hàm thay class. Khi cần state shared giữa step → chuyển sang class.

---

## SO SÁNH VỚI PATTERN KHÁC

| Pattern        | Khác biệt với Template Method                                                          |
|----------------|----------------------------------------------------------------------------------------|
| **Strategy**   | Strategy: composition + injection. Template Method: inheritance + override. Strategy linh hoạt runtime; Template Method cứng nhưng skeleton mạnh. |
| **Builder**    | Builder build object qua các bước (linh hoạt thứ tự). Template Method execute thuật toán (thứ tự cố định). |
| **Factory Method** | Factory Method là một _trường hợp riêng_ của Template Method — base class có template `create_product` + abstract method tạo product cụ thể. |
| **Decorator**  | Decorator bọc thêm hành vi mà không động vào structure. Template Method extend qua subclass. |
| **State**      | State đổi behavior theo state machine. Template Method skeleton cố định, hook khác per subclass. |
| **Visitor**    | Visitor: thêm operation vào hierarchy. Template Method: cấu trúc operation chia sẻ giữa hierarchy. |

> **Insight architect**: Factory Method là Template Method tinh giản (skeleton có 1 hook abstract = create_product). Hook Method (callback) là Template Method ở scale function. Plugin architecture của framework nào cũng là Template Method ở tầng kiến trúc — framework có skeleton, plugin override hooks.

---

## ANTI-PATTERNS THƯỜNG GẶP

1. **Override template method (skeleton)** — subclass override `induce_ltp` để bypass step.
   - Triệu chứng: contract phá, khó maintain.
   - Xử lý: `@typing.final` đánh dấu method không override; hoặc convention `__final__` prefix; hoặc dùng `__init_subclass__` runtime check raise.

2. **Fragile base class** — thay đổi skeleton phá subclass.
   - Triệu chứng: PR đổi base class fail 10 test ở subclass.
   - Xử lý: minimize hook count; document hook contract chặt; cân nhắc chuyển sang Strategy nếu skeleton vẫn evolve.

3. **Hook quá nhiều** — base class có 15 hook → subclass vẫn phải implement gần hết.
   - Triệu chứng: subclass dài bằng base, không tái sử dụng được gì.
   - Xử lý: dấu hiệu sai pattern. Có thể nên dùng Strategy hoặc tách thành nhiều base class nhỏ.

4. **Hook gọi private method của base** — subclass dùng `self._internal_step()`.
   - Triệu chứng: refactor base internal phá subclass.
   - Xử lý: hook chỉ nhận data qua param, return value. Không truy cập internal.

5. **Subclass-of-subclass** — `Hippocampal → CA1Pyramidal → CA1Pyramidal_NR2B_Variant`.
   - Triệu chứng: deep inheritance, diamond problem.
   - Xử lý: flatten — tách thành các flag + composition. Hoặc Strategy.

6. **Template Method nhưng chỉ 1 hook abstract** — đó thực ra là Strategy với extra steps.
   - Triệu chứng: 200 dòng skeleton chỉ để có 1 method override.
   - Xử lý: refactor sang Strategy.

7. **Hook không idempotent** — gọi nhiều lần ra kết quả khác.
   - Triệu chứng: retry skeleton phá state.
   - Xử lý: hook là pure function nếu được; có side effect thì document rõ và đảm bảo idempotent.

---

## BÀI TẬP

1. **Cơ bản**: Thêm `AmygdalaBLA` synapse subclass — NR2B dominant, có hook đặc biệt: `_dopamine_modulate(level)` (hook mới với default no-op). Override để demo fear conditioning có dopamine boost.

2. **Trung bình**: Refactor một báo cáo sinh document có 5 step (load template → fill data → validate → render → save) đang viết kiểu copy-paste cho PDF / Word / HTML thành Template Method. Đo: lines giảm, hook nhận diện rõ.

3. **Khó (architect)**: Cài **HookValidator**:
   - Decorator `@hook(must_implement=True)` đánh dấu abstract hook.
   - `__init_subclass__` runtime check: subclass không override `induce_ltp` (template).
   - Skeleton tự log: bước nào dùng default hook, bước nào dùng override.
   - Test: tạo subclass override skeleton → raise; subclass dùng default consolidation hook → log "default used".
   
   Bonus: thêm `@telemetry` decorator quanh skeleton — auto-log thời gian + outcome mỗi induce_ltp call. Đó là cách production framework (OpenTelemetry, Datadog APM) instrument skeleton.

4. **Mở rộng neuro**: Mô phỏng **synaptic tagging-and-capture** (Frey & Morris). Skeleton của LTP có hook `_should_capture_PRP` (plasticity-related protein). Late-phase protein chỉ tổng hợp ở synapse có "tag" sẵn. Implement: synapse có flag `tagged`, late-phase chỉ ảnh hưởng synapse tagged. Demo 2 synapse stimulate gần nhau cùng lúc — tag-and-capture giải thích tại sao chúng cùng strengthen.

   Bonus: simulate **metaplasticity** — sau N lần LTP, hook `_should_consolidate` raise threshold (BCM rule). Đây là _learning rate decay_ tự nhiên ở synapse. Trong code, đó là Template Method với hook stateful (theo dõi history).

---

## PYTHON-NATIVE: ABC, `@abstractmethod`, `@final`, multiple inheritance

### Chuẩn — ABC + abstractmethod
```python
from abc import ABC, abstractmethod
from typing import final

class SynapticPlasticity(ABC):
    @final
    def induce_ltp(self, stim):
        pre = self._release_glutamate(stim)
        ca = self._activate_nmda(pre)
        ...

    def _release_glutamate(self, stim): ...   # shared

    @abstractmethod
    def _activate_nmda(self, pre): ...        # must override

    def _should_consolidate(self, delta):     # optional hook
        return delta > 0.3
```

`@final` (typing) là HINT cho type checker (mypy) — runtime không enforce. Để runtime enforce:

```python
def __init_subclass__(cls, **kwargs):
    super().__init_subclass__(**kwargs)
    if "induce_ltp" in cls.__dict__:
        raise TypeError(f"{cls} cannot override induce_ltp (template method)")
```

### Multiple inheritance + mixin
Python hỗ trợ MRO (method resolution order). Có thể compose nhiều mixin + base class. Hữu ích khi muốn shared hooks giữa nhiều skeleton. Cẩn thận diamond problem.

### Functional alternative
Python first-class function — Template Method = function nhận callbacks. Không cần class:
```python
def induce_ltp(stim, *, activate_nmda, activate_kinases, should_consolidate=lambda d: d > 0.3):
    pre = _release_glutamate(stim)
    ca = activate_nmda(pre)
    kinase = activate_kinases(ca)
    ampa = _modify_ampa(kinase)
    delta = _strengthen(ampa)
    if should_consolidate(delta):
        _late_phase()
    return delta
```

> Quy tắc architect: class-based khi có **state per-instance**, **lifecycle**, hoặc **inheritance hierarchy thực sự**. Function-based khi chỉ cần plug-in vài hook không state.

---

## CHECKLIST TRƯỚC KHI MERGE PR DÙNG TEMPLATE METHOD

- [ ] Skeleton có **thực sự cố định** (subclass không bao giờ cần reorder)?
- [ ] Hook có được **đánh dấu rõ** (abstract vs optional default)?
- [ ] Template method có `@final` (typing) hoặc enforcement runtime không?
- [ ] Hook có **chỉ nhận data qua param** (không truy cập `self._private` của base)?
- [ ] Inheritance depth có **<= 2** (base + 1 level concrete)?
- [ ] Hook có **idempotent** (gọi nhiều lần OK)?
- [ ] Có **document contract** mỗi hook (input, output, expected behavior)?
- [ ] Có cân nhắc **Strategy thay** không (Strategy linh hoạt hơn)?
- [ ] Test **mỗi subclass + base** riêng được không?
- [ ] Có **observability** trong skeleton (log skip/use default hook)?

---

## TÓM LẠI BẰNG NEUROSCIENCE

> Não đã giải bài toán "cùng cơ chế học, nhiều biến thể vùng" bằng cách giữ skeleton LTP cố định ở mọi synapse plastic — glutamate → NMDA → Ca²⁺ → kinase → AMPA insertion — nhưng cho từng vùng custom subunit, kinase mix, threshold, dopamine modulation. Hippocampal CA1 học nhanh; cerebellar Purkinje làm LTD ngược dấu để motor calibration; cortical L5 threshold cao chỉ học khi salience đủ; amygdala BLA học fear một lần là nhớ. **Cùng skeleton 8 bước, hooks tinh chỉnh.**

> Đây là Template Method ở tầng tiến hoá: skeleton tốt thì khoản đầu tư hàng triệu năm tiến hoá không cần redo cho mỗi vùng não mới. Chỉ cần variants. Code production tốt cũng nên vậy: framework cung cấp skeleton (request handling, lifecycle, error handling), người dùng implement hooks (business logic).

> Quan trọng cho architect: nhận diện **khi nào skeleton _thật sự_ stable**. Nếu skeleton evolve theo từng release → fragile base class, gãy subclass khắp nơi. Khi đó chuyển sang **Strategy** (composition). Template Method chỉ shine khi skeleton _đã prove stable_ qua thời gian — đó là lý do nó phổ biến trong framework lâu đời (Django, Spring, JUnit) chứ không phổ biến trong startup code đang iterate nhanh.

> Bệnh lý của LTP dạy thêm: **Alzheimer** = NMDA disrupt → entire skeleton hỏng dù synapse cấu trúc còn → "all synapses break". Trong code, đó là tương đương _đột biến skeleton phá tất cả subclass_. **NMDA antibody encephalitis** = NR2B subunit bị tấn công → LTP ở 1 vùng não bị tê liệt nhưng vùng khác (NR2A dominant) vẫn ok. Đó là _hook fail không phá skeleton_ — chính xác là behavior pattern Template Method tốt.

> Tóm lại: Template Method là pattern của _stable framework + customizable detail_. Khi skeleton chưa stable, dùng Strategy. Khi skeleton đã stable nhiều năm và team lớn, Template Method tiết kiệm rất nhiều dòng code và đảm bảo contract — đúng như não tiết kiệm tiến hoá bằng cách dùng cùng cơ chế LTP cho mọi vùng học.

Lesson kế tiếp đề xuất: **23 — Visitor (Microglial scan)** — pattern thêm operation vào hierarchy mà không sửa hierarchy. Microglia đi qua từng neuron và hành xử khác nhau theo loại neuron là analog đẹp.
