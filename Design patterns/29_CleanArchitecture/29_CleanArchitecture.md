# Lesson 29 — Clean Architecture
## Layered Concentric Brain — Brainstem (Entities) ở trong cùng, ngoại vi (Frameworks) ở ngoài cùng. Dependency một chiều: từ ngoài vào trong.

---

## TÓM TẮT MỘT DÒNG

**Clean Architecture** = bố cục hệ thống thành **4 vòng tròn đồng tâm** với một quy tắc duy nhất: **source-code dependency chỉ đi vào trong, không bao giờ đi ra ngoài**. Đây là **DIP scaled lên toàn kiến trúc**.

> Não người là layered concentric system. Trung tâm là **brainstem** (~500 triệu năm tuổi tiến hoá): điều khiển nhịp tim, hô hấp, sleep-wake — *enterprise rules* của sự sống. Bao quanh là **subcortical / limbic system** (~250 triệu năm): emotion, motivation, memory consolidation — *application rules*. Tiếp đến là **cortex** (~50-200 triệu năm): perception, planning, language — *use cases* và *interface adapters*. Cuối cùng là **periphery**: retina, cochlea, da, cơ — *frameworks và drivers*, có thể swap (cochlear implant, retinal prosthesis, prosthetic limb). **Dependency direction**: cortex phụ thuộc brainstem (cortex chết nếu brainstem hỏng), brainstem KHÔNG phụ thuộc cortex (decorticate animal vẫn breathe, sleep, eat reflex). Periphery phụ thuộc cortex; cortex không phụ thuộc periphery cụ thể (sensory substitution work). Dependency rule một chiều — *outer depends on inner, never reverse*. Đó là Clean Architecture sinh học.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Một hệ thống "natural top-down" thường có cấu trúc:

```
main.py
  ↓ imports
controller.py (Flask route)
  ↓ imports
service.py (business logic)
  ↓ imports
repository.py (DB access)
  ↓ imports
sqlite3
```

Bốn vấn đề khi system lớn:

1. **Đổi framework rất đắt**: Flask → FastAPI buộc sửa `controller.py` lan đến `service.py` (nếu service dùng `request` object).
2. **Đổi DB rất đắt**: SQLite → Postgres buộc sửa `repository.py` lan đến `service.py` (nếu service biết SQL syntax).
3. **Test integration-only**: muốn test `service.calculate_score()` phải khởi tạo Flask app + SQLite DB → chậm, fragile.
4. **Business rule khó tìm**: business logic rải khắp controller/service/repo; không có "1 chỗ" để hỏi "luật nghiệp vụ X được implement ở đâu?".

Clean Architecture giải bằng cách **bố cục hệ thống theo *stability* + *dependency direction* nhất quán**. Lõi ổn định nhất, ngoài thay đổi nhanh nhất; ngoài phụ thuộc trong.

### 1.2. Định nghĩa và 4 vòng tròn

**Robert C. Martin 2012** (blog post "Clean Architecture"), expanded trong sách *Clean Architecture: A Craftsman's Guide to Software Structure and Design* (2017):

> *"The overriding rule that makes this architecture work is the **Dependency Rule**. This rule says that source code dependencies can only point INWARDS. Nothing in an inner circle can know anything at all about something in an outer circle."*

**4 vòng tròn (outside-in)**:

```
                ┌───────────────────────────────────────────┐
                │  4. FRAMEWORKS & DRIVERS  (outermost)     │
                │     Web (Flask/FastAPI), DB (SQLite/PG),  │
                │     UI, External services, Devices         │
                │     ┌─────────────────────────────────┐   │
                │     │ 3. INTERFACE ADAPTERS           │   │
                │     │    Controllers, Presenters,      │   │
                │     │    Gateways, Repositories impl   │   │
                │     │    ┌────────────────────────┐   │   │
                │     │    │ 2. USE CASES           │   │   │
                │     │    │   Application Business  │   │   │
                │     │    │   Rules. Orchestrate    │   │   │
                │     │    │   entities to do task X.│   │   │
                │     │    │   ┌──────────────────┐ │   │   │
                │     │    │   │ 1. ENTITIES       │ │   │   │
                │     │    │   │   Enterprise      │ │   │   │
                │     │    │   │   Business Rules. │ │   │   │
                │     │    │   │   Most stable.    │ │   │   │
                │     │    │   └──────────────────┘ │   │   │
                │     │    └────────────────────────┘   │   │
                │     └─────────────────────────────────┘   │
                └───────────────────────────────────────────┘

  ←──── DEPENDENCY DIRECTION (inward only) ────
```

#### Vòng 1 — Entities (innermost)

**"Enterprise Business Rules"** — nguyên tắc của *toàn bộ doanh nghiệp*, áp dụng cho mọi hệ thống bạn build trong domain này. Nếu Ellumm có 5 sản phẩm (Quiz, Course, Live Class, Forum, Marketplace), `User` entity dùng chung. Một `Quiz` entity định nghĩa *gì là quiz*: có questions, có answer key, scorable.

**Đặc trưng**:
- Pure domain logic. Pure Python class hoặc dataclass.
- Không import gì ngoài standard library + entities khác.
- Ổn định nhất — nếu rule "a quiz has questions" thay đổi, cả công ty đổi.
- **Không** import use cases, adapters, frameworks.

#### Vòng 2 — Use Cases

**"Application Business Rules"** — nguyên tắc đặc thù của *ứng dụng cụ thể*. Cùng `Quiz` entity, app A có use case "submit quiz lần đầu", app B có "ôn tập quiz cũ" — rule khác nhau dù entity giống.

**Đặc trưng**:
- Một use case = 1 luồng nghiệp vụ. VD: `SubmitQuizUseCase`, `ViewLeaderboardUseCase`, `ExportReportUseCase`.
- Orchestrate entities + định nghĩa input/output port.
- Phụ thuộc **chỉ entities** + Protocol mà use case tự define.
- **Không** import controllers, repositories concrete, frameworks.

#### Vòng 3 — Interface Adapters

**"Adapter layer"** — convert format giữa use cases và frameworks. 

**Đặc trưng và thành phần**:
- **Controllers**: HTTP request → use case input DTO. Parse JSON, validate schema, call use case.
- **Presenters**: use case output DTO → response format (JSON, HTML, XML). Format dữ liệu cho consumer.
- **Repository implementations**: implement Protocol từ use cases. SQL/HTTP/file detail sống ở đây.
- **Gateways**: external API calls (Stripe, Mailchimp, ...).

**Quan trọng**: Adapters import use cases (cần input/output DTO type, cần Protocol để implement). Adapters KHÔNG được tham khảo lẫn nhau xuyên qua use case.

#### Vòng 4 — Frameworks & Drivers

**"Disposable infrastructure"** — Flask, FastAPI, Django; SQLite, Postgres, Mongo; SMTP, SES, SendGrid; React, Vue, native UI.

**Đặc trưng**:
- Library / framework code. *Bạn không control source*.
- Dễ thay nhất, khó nhất để test isolated.
- Import adapters (để wire route → controller, ORM model → repo).
- **Phải có** composition root tại đây hoặc cùng tầng.

### 1.3. Dependency Rule — quy tắc một chiều

> **Source code dependency chỉ đi vào trong**.

Nếu bạn vẽ DAG (directed graph) các `import` statement, mọi mũi tên đi từ vòng ngoài → vòng trong, **không bao giờ ngược**.

Ví dụ cụ thể:
- `entities/quiz.py` import gì? → `dataclasses`, `typing` (stdlib). Hết.
- `use_cases/submit_quiz.py` import gì? → `entities/*`, `use_cases/ports/*`. Không import `adapters/*` hay `frameworks/*`.
- `adapters/quiz_controller.py` import gì? → `use_cases/*`, `entities/*` (DTO). Có thể import `frameworks/web/*` cho type hint nhẹ.
- `frameworks/flask_app.py` import gì? → `adapters/*`, `flask` library, `main.py` composition.

**Test cụ thể**: `grep -r "from frameworks" use_cases/` → phải = 0. Nếu > 0, dependency rule bị vi phạm.

### 1.4. Crossing boundaries — DIP áp dụng systematically

Vấn đề: **runtime call direction** thường đi cả 2 chiều. Use case cần *gửi* output ra controller/presenter; use case cần *gọi* repository để lưu. Làm sao "outward call" mà "inward dependency"?

**Trả lời**: dùng **input port + output port**, cả hai owned by use case.

```
INPUT side:                              OUTPUT side:

Controller   ──calls──►  Use Case        Use Case  ──calls──►  Output Port
                          (input port)              (interface)
                                                          ▲
                          ▲                              │ implements
                          │                              │
                       Use Case  ◄───imports── Presenter (concrete)
                          ▼                              ▲
                       Entities                         imports
                                                          │
                                                       Use Case (port)
```

- **Input port**: interface use case expose để controllers/CLI/scheduler gọi. Method như `submit(input_dto) -> output_dto`.
- **Output port**: interface use case define cho việc *output*. VD: `IQuizPresenter.present(output_dto) -> None`. Use case GỌI nó, nhưng *concrete impl* sống ở adapter layer (Presenter implements port). Source-code dependency: presenter → use case (inward); runtime call: use case → presenter (outward).

Đây là sức mạnh của DIP. Nó cho phép use case "talk outward" mà vẫn "depend inward".

### 1.5. Hiểu sai phổ biến

| Hiểu sai | Hiểu đúng |
|----------|-----------|
| "4 layer = 4 folder cứng" | 4 layer là *concept* về stability + dependency. Có thể có sub-layer trong cùng folder, miễn dependency rule giữ |
| "Mỗi layer có 1 framework" | Layer là logic boundary, không = framework boundary |
| "Use cases = service class" | Use cases là *use case cụ thể* (1 user-action = 1 use case). Service class có thể nằm trong adapter layer |
| "Entities = ORM model" | Entities là pure domain. ORM model có thể là adapter (mapping từ entity sang DB) |
| "Clean Arch = quá nhiều file" | Đúng có nhiều file. Đổi lại: tự do thay framework, test pure, business logic tập trung |
| "Clean Arch = MVC" | MVC chỉ phân Controller/View/Model. Clean Arch *bao trùm* MVC ở vòng adapter — và cộng thêm dependency rule |

### 1.6. Neuroscience analogy — Layered concentric brain

#### Cơ chế 1 — Evolutionary layering (4 stages)

Não người có 4 layer phát triển qua tiến hoá, mỗi layer có "rules" riêng:

| Layer | Tuổi tiến hoá | Cấu trúc | Chức năng | Tương đương Clean Arch |
|-------|----------------|----------|-----------|-------------------------|
| **Brainstem** (medulla, pons, midbrain) | ~500 triệu năm (động vật có xương sống cổ nhất) | Cluster nhân điều khiển vital signs | Hô hấp, nhịp tim, sleep-wake, swallowing reflex, vestibular | **Entities** — enterprise rules của sự sống |
| **Subcortical / Limbic** (amygdala, hippocampus, hypothalamus, basal ganglia) | ~250 triệu năm (động vật có vú sớm) | Nhân chuyên biệt | Emotion, memory consolidation, motivation, drive, autonomic regulation | **Application Business Rules** — luật cho hành vi sinh tồn |
| **Cortex** (neocortex 6-layer) | ~200 triệu năm (mammal); explosion ở primate | Sheet 2-4 mm dày, gấp khúc, 6 cell layer | Perception, planning, language, abstract reasoning | **Use Cases + Interface Adapters** |
| **Sensory + Motor periphery** (eyes, ears, skin, muscles, glands) | Multi-origin — eyes evolved ≥ 40 lần độc lập | Specialized organs | Transduction signal, motor output | **Frameworks & Drivers** — disposable, swappable |

→ Mỗi layer build *trên* layer trước. Layer trẻ hơn không thay thế layer cũ — bổ sung capability.

#### Cơ chế 2 — Dependency direction trong não

Bằng chứng dependency direction "outer depends on inner, never reverse":

**Brainstem độc lập**:
- **Anencephaly** (sinh không có cortex/cerebrum): trẻ vẫn còn breathe, suck, sleep — brainstem entities work alone. (Tử vong sớm vì các function khác mất.)
- **Decorticate cat** (Sherrington 1898 — thí nghiệm cắt cortex): mèo vẫn breathe, sleep, eat reflex, walk khi đẩy. Cortex bị cắt — brainstem không cần cortex.

**Cortex phụ thuộc brainstem**:
- **Brainstem death** = brain death legal — nếu brainstem chết, cortex không thể survive, kể cả trên ECMO.
- **Encephalitis lethargica** (Oliver Sacks "Awakenings"): bệnh ảnh hưởng substantia nigra (subcortical) — cortex còn nguyên nhưng patient "đông cứng", không initiate movement. Cortex một mình không di chuyển được.

**Periphery dispensable**:
- **Cochlear implant**, **retinal prosthesis**, **prosthetic limb**, **BrainPort tongue** — periphery thay được vì cortex không phụ thuộc loại sensor cụ thể.
- **Sensory substitution**: thay eye = tactile camera, cortex remap → "thấy" qua da. Cortex không sửa.

→ Direction một chiều: outer (periphery) depends on inner (cortex); inner (brainstem) does NOT depend on outer.

#### Cơ chế 3 — Boundaries có "abstraction" rõ

Mỗi cặp layer có *interface format* cố định:

- **Periphery → Cortex**: spike train pattern (qua thalamus). Cortex không thấy biochemistry của photoreceptor; nó thấy "spike rate + topography".
- **Cortex → Subcortical**: action selection signal, attention bias. Subcortical không thấy "concept" của cortex; nó thấy "salience score".
- **Subcortical → Brainstem**: autonomic command, arousal level. Brainstem không thấy emotion; nó thấy "set point change".
- **Brainstem → effector**: motor neuron firing pattern.

Mỗi tầng nói chuyện với tầng kế qua *abstract format*. Đây là DIP áp dụng systematically — chính là Clean Architecture.

#### Cơ chế 4 — Cross-boundary callback (output port analogy)

Cortex (use case layer) cần *output*. Nó không gọi muscle trực tiếp — nó gọi một "output port" (motor cortex M1 → corticospinal tract). M1 *là cortex*, nhưng nó *implement output capability* cho các vùng cortex khác (PFC plan → M1 execute). Tương tự code: use case define output port; presenter (cùng tầng adapter) implement port; runtime use case "call out" qua port.

#### 5 chiều của analogy

| Chiều | Trong não (layered concentric) | Trong code (Clean Architecture) |
|-------|--------------------------------|---------------------------------|
| **Cấu tạo** | 4 layer evolutionary: brainstem / subcortical / cortex / periphery. Mỗi layer có cytoarchitecture riêng | 4 layer: entities / use cases / adapters / frameworks. Mỗi layer có thư mục riêng |
| **Vị trí** | Concentric: trung tâm não (brainstem) ở sâu; ngoại vi sensors/muscles ở vỏ ngoài | Concentric package: `entities/` ở trung tâm import graph; `frameworks/` ở vỏ |
| **Chức năng** | Brainstem = vital rules; cortex = perception/plan; periphery = transduction | Entities = enterprise rules; use cases = application rules; adapters = format conversion; frameworks = I/O |
| **Kết nối** | Outer depends on inner. Spike train là interface format. Brainstem không "biết" cortex | Source code import chỉ vào trong. Protocol là interface. Entities không "biết" use cases |
| **Ý nghĩa** | Stable core (brainstem ~500M năm); volatile outer (sensors evolved 40+ lần). Replaceable periphery | Stable core (entities); volatile outer (frameworks). Swap framework không phá business rule |

### 1.7. Khi nào DÙNG Clean Architecture nghiêm

- Codebase ≥ 5,000 LOC, lifetime ≥ 1 năm.
- Multi-team (mỗi team own 1 layer hoặc 1 use case set).
- Likely thay đổi infrastructure (cloud migration, vendor swap, monolith → microservice).
- Cần audit business rule riêng biệt với infra (compliance, financial, healthcare).
- Test business rule pure quan trọng (CI fast feedback).

### 1.8. Khi nào KHÔNG dùng (over-engineering)

- Script throwaway, prototype, MVP < 1 tháng.
- Single-dev project < 1,000 LOC.
- CRUD đơn giản không có business logic phức tạp (dùng Active Record / Rails-style nhẹ hơn).
- Thay đổi requirement đến quá nhanh để stable inner layers.
- Team chưa đủ kỷ luật để duy trì dependency rule (sẽ vi phạm dần → tệ hơn monolith).

> **Heuristic**: Clean Architecture tỉ lệ thuận với *lifetime + churn*. Lifetime ngắn = không cần. Churn cao trong infra = rất cần.

---

## MỨC 2 — ALGORITHM / CẤU TRÚC

### 2.1. Project layout chuẩn

```
ellumm_quiz/
├── domain/                          ← Vòng 1+2 (entities + use cases)
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── quiz.py                  (class Quiz, Question, AnswerKey)
│   │   ├── submission.py            (class Submission)
│   │   └── score.py                 (class ScoreResult, scoring logic)
│   ├── use_cases/
│   │   ├── ports/                   ← interfaces owned by use cases
│   │   │   ├── repositories.py      (ISubmissionRepository, IQuizRepository)
│   │   │   ├── notifiers.py         (INotifier)
│   │   │   └── presenters.py        (ISubmitQuizPresenter)
│   │   ├── submit_quiz.py           (class SubmitQuizUseCase)
│   │   ├── view_leaderboard.py
│   │   └── export_report.py
│   └── (NO imports from layers below!)
│
├── adapters/                        ← Vòng 3
│   ├── controllers/
│   │   └── quiz_controller.py       (HTTP → use case input DTO)
│   ├── presenters/
│   │   ├── json_presenter.py        (output DTO → JSON)
│   │   └── html_presenter.py        (output DTO → HTML)
│   ├── repositories/
│   │   ├── sqlite_submission_repo.py  (impl ISubmissionRepository)
│   │   ├── postgres_submission_repo.py
│   │   └── memory_submission_repo.py
│   └── gateways/
│       └── stripe_gateway.py
│
├── frameworks/                      ← Vòng 4
│   ├── web/
│   │   ├── flask_app.py             (Flask routes calling controllers)
│   │   └── fastapi_app.py
│   ├── db/
│   │   └── sqlite_init.py
│   └── cli/
│       └── command_line.py
│
└── main.py                          ← composition root (wire concrete → abstract)
```

### 2.2. Recipe 7 bước áp Clean Architecture

```
INPUT: hệ thống monolith hoặc layered đơn giản, vi phạm dependency rule

step 1: liệt kê business entities
        - Cái gì là "thực thể nghiệp vụ" của domain?
        - VD: Quiz, Submission, User, ScoreResult
        - Tạo classes pure (dataclass), không I/O, không framework
        - Đặt trong domain/entities/

step 2: liệt kê use cases
        - Cái gì là "user-facing action"?
        - VD: SubmitQuiz, ViewLeaderboard, ExportReport
        - Mỗi use case = 1 class với method execute(input) -> output
        - Định nghĩa input DTO + output DTO

step 3: định nghĩa ports (interfaces)
        - Output port: nơi use case "talk outward" (presenter, repository)
        - Input port: signature của use case execute()
        - Đặt trong domain/use_cases/ports/

step 4: viết adapters
        - Controller: parse HTTP/CLI input → input DTO → call use case
        - Presenter: implement output port → format response
        - Repository concrete: implement repo port → SQL/HTTP

step 5: wrap framework code
        - Flask route → call controller (1-line)
        - SQLite init → wire SqliteRepository
        - Configuration loading → wire env vars

step 6: composition root
        - main.py wire all concrete adapters into use cases
        - Đây là điểm DUY NHẤT thấy mọi layer

step 7: test
        - Unit test entities pure
        - Unit test use cases với fake repo + fake presenter
        - Integration test adapter (sqlite repo với SQLite thật)
        - End-to-end test framework + adapter + use case
```

### 2.3. Invariants sau khi áp Clean Architecture

1. **Dependency rule absolute**: `grep -r "from adapters" domain/` = 0; `grep -r "from frameworks" domain/` = 0; `grep -r "from frameworks" adapters/` = 0.
2. **Entities pure**: 0 import từ outer layers, 0 I/O, < 100 dòng mỗi file.
3. **Use cases pure**: 0 SQL, 0 HTTP, 0 framework call. Chỉ entities + ports.
4. **Test pure**: unit test domain layer < 100 ms total. Không tempfile, không network.
5. **Composition root**: chỉ 1 file (main.py) thấy mọi layer.
6. **Swap test**: thay framework Flask → FastAPI sửa < 100 dòng (chỉ frameworks/ + composition root).

### 2.4. DTO (Data Transfer Object) — boundary protection

Khi data đi qua boundary, **dùng DTO riêng**, không dùng entity trực tiếp.

```python
# domain/use_cases/submit_quiz.py
@dataclass(frozen=True)
class SubmitQuizInput:
    user_id: str
    quiz_id: str
    answers: Dict[str, str]

@dataclass(frozen=True)
class SubmitQuizOutput:
    submission_id: str
    score: float
    total: float
    rank: int

class SubmitQuizUseCase:
    def execute(self, input_dto: SubmitQuizInput) -> SubmitQuizOutput:
        ...
```

**Tại sao không dùng `Submission` entity trực tiếp**:
- Entity có thể có behavior (method) — không nên expose ra ngoài.
- Boundary changes (UI rename field) không buộc đổi entity.
- DTO là *immutable contract* tại boundary.
- Multiple presenter có thể tiêu thụ cùng output DTO khác nhau (JSON, HTML, PDF).

### 2.5. Anti-patterns hay xảy ra cùng Clean Architecture

| Anti-pattern | Triệu chứng | Cách tránh |
|--------------|-------------|------------|
| **Anemic Domain Model** | Entity chỉ getter/setter; logic dồn vào use case | Để entity có hành vi (`Score.compute(...)`, `Submission.is_late()`) |
| **Leaky abstraction** | Repository interface có method `execute_sql(query: str)` | Dùng method theo domain language |
| **Boundary leak** | Use case return SQLAlchemy ORM object trực tiếp | Wrap vào DTO trước khi return |
| **Big-Ball-of-Mud Adapter** | 1 adapter file 2000 dòng làm mọi thứ | Tách theo cohesion (1 adapter = 1 boundary cụ thể) |
| **Framework leakage** | Use case import `from flask import request` | Dùng input DTO; controller parse `request` rồi pass DTO |
| **Speculative layering** | 8 layer cho project 200 dòng | YAGNI; bắt đầu với 2-3 layer, phát triển khi cần |
| **Static call to framework** | Use case gọi `time.now()` trực tiếp | Inject `IClock` port |
| **Rigid framework match** | Mỗi route Flask = 1 file | Adapter = 1 use case, framework call adapter — không 1-1 |

### 2.6. Đo bằng metric cụ thể

| Metric | Clean Arch good | Clean Arch bad |
|--------|------------------|-----------------|
| `grep "from frameworks" domain/` | 0 | > 0 |
| `grep "from adapters" domain/` | 0 | > 0 |
| Time chạy unit test domain | < 100 ms cho > 100 test | giây |
| Số file phải sửa khi thay framework | 5-10 (frameworks/ + main.py) | nhiều |
| Số layer giữa controller và entity | 2 (controller → use case → entity) | 5+ |
| Số dòng main.py composition | 50-200 | > 1000 (god composition) |

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode — workflow cho 1 request

```
1. POST /quiz/submit  (HTTP request)
2. flask_app.py route handler — calls controller
3. quiz_controller.parse(http_request) → SubmitQuizInput DTO
4. quiz_controller calls submit_quiz_use_case.execute(input_dto)
5. SubmitQuizUseCase:
   a. Get Quiz entity from quiz_repo.find_by_id(input.quiz_id)
   b. Score using Quiz.score_against(input.answers) [entity logic]
   c. Build Submission entity
   d. submission_repo.save(submission)
   e. notifier.notify(user_id, score)
   f. Build SubmitQuizOutput DTO
   g. presenter.present(output) ← OUTPUT PORT call
6. JsonPresenter.present(output) → response_json (state stored)
7. quiz_controller returns response_json to flask_app
8. flask_app sends HTTP 200 + JSON

Source-code import direction:
  flask_app  → quiz_controller → submit_quiz_use_case → entities
  flask_app  → json_presenter → submit_quiz_use_case (port)
  json_presenter implements ISubmitQuizPresenter (defined in submit_quiz_use_case)

Runtime call direction:
  flask_app calls quiz_controller calls use_case calls entities
  use_case calls presenter (output port — but presenter imports use case for type)
```

### 3.2. Python — file `29_clean_architecture.py`

Cấu trúc trong `29_clean_architecture.py`:

1. **Domain layer (Vòng 1+2)**:
   - Entities: `Quiz`, `Submission`, `ScoreResult`
   - Use cases: `SubmitQuizUseCase`, `ViewLeaderboardUseCase`
   - Ports: `IQuizRepository`, `ISubmissionRepository`, `INotifier`, `ISubmitQuizPresenter`, `ILeaderboardPresenter`
2. **Adapter layer (Vòng 3)**:
   - Controllers: `QuizController` (parse input)
   - Presenters: `JsonSubmitPresenter`, `HtmlSubmitPresenter`, `LeaderboardJsonPresenter`
   - Repositories: `InMemoryQuizRepository`, `InMemorySubmissionRepository` (test); `SqliteSubmissionRepository` (prod)
3. **Framework layer (Vòng 4)**:
   - `FlaskLikeApp` (mock Flask, không import flask để self-contained)
   - `FastApiLikeApp` (mock FastAPI)
4. **Composition root** + builder functions
5. **5 demo**:
   - Demo 1: End-to-end request trace through 4 layers
   - Demo 2: Swap framework Flask → FastAPI, business unchanged
   - Demo 3: Swap presenter JSON → HTML, use case unchanged
   - Demo 4: Swap repository Memory → SQLite, use case unchanged
   - Demo 5: Source-code dependency graph showing one-way

Chạy:
```bash
python 29_clean_architecture.py
```

---

## 5 CHIỀU — BẢNG SO SÁNH IN NÃO VS IN CODE

| Chiều | Não (layered concentric: brainstem ← cortex ← periphery) | Code (Clean Architecture: entities ← use cases ← adapters ← frameworks) |
|-------|-----------------------------------------------------------|---------------------------------------------------------------------------|
| **Cấu tạo** | 4 layer evolutionary, mỗi layer có cytoarchitecture riêng | 4 layer (entities/use cases/adapters/frameworks), mỗi layer thư mục riêng |
| **Vị trí** | Concentric: brainstem ở trung tâm não; periphery ở vỏ ngoài | Concentric package: entities ở center import graph; frameworks ở vỏ |
| **Chức năng** | Brainstem = vital rules; subcortical = drive; cortex = plan/perceive; periphery = transduction | Entities = enterprise rules; use cases = app rules; adapters = format conversion; frameworks = I/O |
| **Kết nối** | Outer depends on inner. Brainstem hoạt động không cần cortex (decorticate cat). Spike train là interface | Source code import một chiều inward. Entities import được mà không có use cases/adapters/frameworks. Protocol là interface |
| **Ý nghĩa** | Stable core (~500M năm); periphery evolved 40+ lần. Sensory substitution work | Stable core (entities); framework volatile. Swap Flask/SQLite không touch business |

---

## 3 LOẠI VÍ DỤ TRONG CODE

### Ví dụ 1 — Vận hành thường (Clean Architecture đầy đủ)

Workflow: User submit quiz qua Flask:

```
1. Flask route POST /quiz/submit
2. Controller parses JSON → SubmitQuizInput
3. SubmitQuizUseCase.execute(input):
   - Quiz quiz = quiz_repo.find_by_id(input.quiz_id)    [domain entity]
   - ScoreResult score = quiz.score_against(input.answers)  [entity behavior]
   - Submission sub = Submission(...)  [entity]
   - submission_repo.save(sub)         [output port → adapter SQLite]
   - notifier.notify(user_id, score)   [output port → adapter Email]
   - SubmitQuizOutput out = SubmitQuizOutput(...)
   - presenter.present(out)            [output port → adapter JsonPresenter]
4. Controller returns JSON to Flask
5. Flask returns HTTP response
```

Mỗi cấp phụ thuộc cấp trong qua *interface*. Đổi Flask sang FastAPI = đổi router, business logic không thay.

### Ví dụ 2 — Hỏng/thiếu (vi phạm dependency rule)

```python
# domain/use_cases/submit_quiz.py
from flask import request, jsonify    # ← VI PHẠM: import framework
import sqlite3                          # ← VI PHẠM: import driver

class SubmitQuizUseCase:
    def execute(self):
        data = request.json             # ← biết về Flask
        conn = sqlite3.connect("app.db")  # ← biết về SQLite
        ...
        return jsonify({"score": ...})  # ← biết về Flask response
```

Hậu quả:
- **Test impossible**: muốn test phải chạy Flask app, có request context, có SQLite file.
- **Đổi framework rất đắt**: Flask → FastAPI buộc sửa file này.
- **Business rule khó tìm**: scoring logic embedded giữa Flask + SQLite code.
- **Dependency graph sai**: domain/use_cases import từ frameworks/ → vi phạm rule.

### Ví dụ 3 — Ứng dụng Ellumm Quiz (4-layer mini)

| Layer | File | Import | Export |
|-------|------|--------|--------|
| Entities | `domain/entities/quiz.py` | stdlib only | `Quiz`, `Question`, `AnswerKey` |
| Use cases | `domain/use_cases/submit_quiz.py` | `entities/*`, `ports/*` | `SubmitQuizUseCase`, `SubmitQuizInput`, `SubmitQuizOutput` |
| Adapters | `adapters/presenters/json_presenter.py` | `use_cases/ports/*`, `use_cases/submit_quiz` | `JsonSubmitPresenter` |
| Adapters | `adapters/repositories/sqlite_repo.py` | `use_cases/ports/*`, `entities/*`, `sqlite3` | `SqliteSubmissionRepository` |
| Frameworks | `frameworks/web/flask_app.py` | `adapters/*`, `flask` | `FlaskApp` |
| Composition | `main.py` | mọi layer | `build_app()` |

**Test scenarios**:
- Domain layer test: import `entities/`, `use_cases/`, fake repo/notifier/presenter. Chạy < 100 ms cho 100 test.
- Integration test: import `adapters/sqlite_repo.py`, test SQL với SQLite thật.
- E2E test: import `main.py`, simulate HTTP request, kiểm response.

---

## SO SÁNH PATTERN LÂN CẬN

| Pattern / Style | Đặc điểm | Quan hệ với Clean Architecture |
|-----------------|----------|---------------------------------|
| **Hexagonal (Lesson 30)** | Ports & Adapters | Cùng tinh thần. Hex chỉ 2 region (core + adapter); Clean có 4 layer rõ hơn (entities vs use cases). Có thể coi Hex là "Clean simplified" |
| **Layered Architecture** (3-tier presentation/business/data) | Tầng trên gọi tầng dưới | Khác chỗ Clean *đảo* dependency direction tại boundary. Layered truyền thống business → data; Clean business defines port, data implements |
| **Onion Architecture** (Jeffrey Palermo) | 4 vòng tròn rất giống | Gần như đồng nghĩa với Clean. Onion older, Clean popularize qua Bob Martin |
| **DDD (Domain-Driven Design)** | Bounded context, aggregate, domain event | Clean Arch = *technical layout*; DDD = *modeling approach*. Hai cái thường đi cùng |
| **MVC** | Model/View/Controller | MVC nằm ở vòng 3 (Adapters) của Clean. Controller, presenter là MVC components |
| **Microservices** | Service boundary | Mỗi service có thể có Clean Arch riêng. Inter-service = adapter layer gọi gateway |
| **Vertical Slice Architecture** (Jimmy Bogard) | 1 feature = 1 slice từ UI đến DB | Clean horizontal layer; Slice vertical. Có thể kết hợp |
| **Big Ball of Mud** (anti) | Không có architecture | Phản đề. Clean Arch là vaccine |

**Vai trò trong SOLID**: Clean Architecture là *DIP scaled lên*. Mỗi boundary giữa layer là DIP. SRP áp lên class trong từng layer. OCP/LSP/ISP áp lên port giữa layers.

---

## TRADE-OFFS

| Trade-off | Chi phí | Lợi ích |
|-----------|---------|---------|
| 4-layer cấu trúc | File count, navigation overhead, learning curve | Dependency direction rõ ràng, swap framework dễ |
| DTO ở boundary | Duplicate giữa entity và DTO; mapping code | Boundary stable, framework không leak |
| Composition root tập trung | main.py có thể dài | 1 nơi thay config |
| Port/adapter | Indirection mỗi cross-boundary call | Test pure, decoupled |
| Discipline | Team phải hiểu và respect dependency rule | Sau 6 tháng codebase vẫn clean |
| Onboarding | Dev mới phải hiểu 4 layer | Code dễ navigate sau khi hiểu |

**Quy tắc**: chấp nhận overhead khi project ≥ 5K LOC + lifetime ≥ 1 năm + multi-team. Với prototype < 1K LOC, dùng simpler architecture (3-layer hoặc thậm chí monolith well-organized).

---

## CHECKLIST TRƯỚC KHI MERGE PR

- [ ] **Dependency rule check**: `grep -r "from adapters\|from frameworks" domain/` phải = 0.
- [ ] **Entity purity**: entities có import gì ngoài stdlib + sibling entities không?
- [ ] **Use case purity**: use case có import framework/driver code (Flask, SQLite, requests) không?
- [ ] **Port location**: interfaces (Protocol/abstract base) ở `domain/use_cases/ports/` chứ không ở `adapters/`?
- [ ] **DTO at boundary**: input/output dùng DTO frozen dataclass, không entity raw?
- [ ] **Composition root single**: chỉ 1 file (main.py) wire concrete vào abstract?
- [ ] **Test layer separation**: domain unit test < 100 ms, không I/O? Adapter integration test riêng?
- [ ] **Anemic domain check**: entity có behavior hay chỉ getter/setter? Push business logic vào entity nếu phù hợp.
- [ ] **Leaky abstraction**: port method theo domain language hay technical language? `find_by_user(id)` ✓; `execute_sql(q)` ✗.
- [ ] **Framework leak**: controller/presenter có để framework type leak ngược vào use case không? Use case nhận DTO; framework type stays in adapter+ outer.

---

## BÀI TẬP 4 MỨC

### Mức 1 — Cơ bản

Mở `29_clean_architecture.py`. Identify 4 layer trong file:
- Liệt kê class thuộc mỗi layer.
- Vẽ dependency graph: vòng nào import vòng nào? (Mũi tên 1 chiều inward.)
- Confirm: entity có import use case/adapter/framework không? (Phải = 0.)
- Confirm: use case có import adapter/framework? (Phải = 0.)

### Mức 2 — Trung bình

Yêu cầu: thêm "PDF report" tính năng — user request `/quiz/report.pdf`, system generate PDF với submission detail.

Implement:
1. Use case `GenerateReportUseCase` — nhận `user_id`, return `ReportOutput`.
2. Output port `IReportPresenter`.
3. Adapter `PdfReportPresenter` — concrete impl tạo PDF (giả lập với bytes).
4. Framework: route `/quiz/report.pdf` → controller → use case → presenter.

Đo:
- Số file thêm vào mỗi layer (target: 1 file mỗi layer).
- Domain (entities + use cases) sửa bao nhiêu? (Target: 0 entity, +1 use case.)

### Mức 3 — Khó (architect-level)

Tình huống: existing app dùng Flask + SQLAlchemy ORM. Refactor sang Clean Architecture. Khó:
1. SQLAlchemy ORM model có cả schema lẫn behavior — entity hay adapter?
2. Flask request global → use case không nên thấy. Adapter parse `request.json` → DTO?
3. SQL relationship (one-to-many) — entity có expose collection không hay lazy-load qua repo?
4. Migrating data từ SQLAlchemy session → in-memory entity → repo save lại — performance tradeoff?

Trả lời 4 câu trên + design migration plan 5 bước.

### Mức 4 — Mở rộng neuroscience

Câu hỏi mở:
1. **Anencephaly** (born without cortex): trẻ vẫn breathe/suck/sleep — chứng minh brainstem độc lập với cortex. Liên hệ: nếu xoá `frameworks/` directory, `domain/` của Clean Arch vẫn import được, vẫn unit-testable. Đó là "anencephaly test" của architecture. Mô tả cụ thể.
2. **Encephalitis lethargica** (Sacks "Awakenings"): substantia nigra hỏng → cortex còn nguyên nhưng patient không initiate movement. "Use cases" còn nhưng "drive layer" hỏng → system frozen. Liên hệ: nếu inject `None` vào port nào trong Clean Arch sẽ làm hệ "frozen"?
3. **Cortex plasticity** (sensory substitution + cortical remap): cortex remap khi sensor thay đổi. Liên hệ: Clean Arch cho phép "cortex" (use cases) "remap" khi adapter mới đến — nhưng chỉ nếu port được giữ stable. Tương đương "interface stability" trong code.
4. **Triune brain model** (MacLean) có overly simplistic — não thực tế phức tạp hơn 3 lớp. Liên hệ: Clean Arch 4-layer cũng simplified — practical project có sub-layer / module bên trong. Khi nào cần vẽ thêm layer? Khi nào gộp?

Trả lời 4–6 câu mỗi mục.

---

## SAU LESSON NÀY

Clean Architecture đã đặt 4 vòng tròn + dependency rule. Lesson 30 (**Hexagonal Architecture / Ports & Adapters**, Alistair Cockburn 2005) là *biến thể đơn giản hơn* tập trung vào *core domain ↔ adapters*. Hex thường được prefer cho microservice (đơn vị nhỏ); Clean cho monolith lớn. Nhiều project gọi "Hexagonal" nhưng implement Clean — hai cái có overlap rộng.

Sau Hex (lesson 30), chuyển sang **EDA — Event-Driven Architecture** (lesson 31): từ synchronous request-response sang asynchronous event publish-subscribe. Đó là bước nhảy lớn về *temporal decoupling* — không chỉ structural decoupling như Clean/Hex.

> **Nhớ một câu**: Clean Architecture không phải "4 folder cố định". Clean Architecture là "**source-code dependency một chiều, từ outer (volatile) vào inner (stable)** — và mỗi boundary có một interface owned by inner".
