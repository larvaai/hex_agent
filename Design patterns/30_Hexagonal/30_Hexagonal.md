# Lesson 30 — Hexagonal Architecture (Ports & Adapters)
## Sensory Substitution Cortex — Lõi domain bất biến, giác quan/cơ quan thực thi cắm vào qua port; thay tay bằng chân vẽ vẫn vẽ được.

---

## TÓM TẮT MỘT DÒNG

**Hexagonal Architecture** = bố cục hệ thống thành **một lõi domain ở giữa** + **các adapter cắm vào lõi qua port** ở mọi phía. Hai loại port: **driving** (bên ngoài gọi vào lõi — HTTP, CLI, queue consumer) và **driven** (lõi gọi ra ngoài — DB, email, payment). Triết lý: *lõi không biết và không quan tâm I/O đến từ đâu hay đi về đâu*.

> Bach-y-Rita 1969 — *Tactile-Visual Sensory Substitution* (TVSS): camera → 400 rung tử trên lưng → người mù **"thấy"** không gian 3D. Cortex thị giác chưa từng tiến hoá để xử lý tín hiệu da, vẫn học được. Cochlear implant 1972: âm thanh → 22 kênh điện cực kích thích nhánh thính giác → cortex thính giác **"nghe"**. Argus II 2011: camera → mảng điện cực 60 pixel cấy vào võng mạc → cortex thị giác **"thấy"** ánh sáng. Bài học sinh học: **cortex là core domain pluggable**; mắt/tai/da chỉ là *adapter* cắm vào *port* "abstract sensory format". Khi tay cắt cụt, người ta học vẽ bằng chân — *driven port* vận động đổi adapter, lõi planning vẫn nguyên. Đó là Hexagonal sinh học.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Sau Clean Architecture (Lesson 29) bạn đã có 4 vòng tròn với Dependency Rule "outer → inner". Nhưng Clean có **3 đặc điểm** đôi khi gây nặng cho service vừa và nhỏ:

1. **4 layer đối với 1 microservice là dư**: Entities + Use Cases + Interface Adapters + Frameworks/Drivers. Một service nhỏ có thể chỉ cần 2 vùng: "logic" và "I/O".
2. **Use Case layer dễ phình thành "anemic orchestrator"**: nhiều team dump mọi thứ vào use case class → use case nuốt cả validation lẫn presentation logic.
3. **Asymmetry không rõ giữa input và output**: trong Clean, controller và repository đều ở vòng "Interface Adapters" nhưng vai trò ngược nhau (một dẫn vào, một dẫn ra). Học viên hay nhầm.

**Hexagonal** (Alistair Cockburn, 2005, paper *"Hexagonal architecture"*) trả lời:

> *"Allow an application to equally be driven by users, programs, automated test or batch scripts, and to be developed and tested in isolation from its eventual run-time devices and databases."*

Cách giải: chỉ **2 vùng** (inside / outside), nhưng outside được **tách rõ làm 2 nửa**:
- **Driving side (primary)**: cái bên ngoài *gọi vào* lõi — UI, CLI, test harness, message consumer.
- **Driven side (secondary)**: cái lõi *gọi ra* — DB, email, payment gateway, file system.

Symmetric, dễ vẽ ra giấy: lõi ở giữa, driving bên trái, driven bên phải. Tên "hexagonal" chỉ là vì Cockburn vẽ hình lục giác để có 6 cạnh mà cắm port (không phải con số 6 thiêng liêng — thực tế có thể vẽ hình tròn, vuông, đều được).

### 1.2. Định nghĩa và các thành phần

**Port** = một *interface* (Python: `Protocol` / `ABC`) khai báo *cái lõi cần* hoặc *cái lõi cung cấp*. **Không có implementation, chỉ chữ ký**.

**Adapter** = một *implementation* của port. Mỗi adapter tham chiếu vào *một công nghệ cụ thể* (Flask, SQLAlchemy, SMTP...).

**Hai loại port**:

| Loại | Tên khác | Hướng | Ai implement | Ví dụ |
|------|----------|-------|--------------|-------|
| **Driving port** | Primary, Inbound, API port | Ngoài → Lõi | **Lõi** (định nghĩa cái nó làm được) | `IQuizApplicationService` |
| **Driven port** | Secondary, Outbound, SPI port | Lõi → Ngoài | **Adapter** (lõi định nghĩa contract, adapter làm thật) | `ISubmissionRepository`, `INotifier` |

**Hai loại adapter** tương ứng:

| Loại | Vị trí | Vai trò | Ví dụ |
|------|--------|---------|-------|
| **Driving adapter** (Primary) | Bên trái | Dịch input từ thế giới ngoài thành lời gọi vào driving port | Flask controller, CLI parser, Kafka consumer, test driver |
| **Driven adapter** (Secondary) | Bên phải | Dịch lời gọi từ driven port thành thao tác công nghệ ngoài | SqliteRepository, SmtpEmailNotifier, RedisCache |

Hình tổng:

```
                   ┌──────── DRIVING SIDE ────────┐
                   │  (Primary adapters call IN)  │
                   │                              │
   HTTP            │   ┌──────────────────┐       │   DRIVEN SIDE
   Controller ────────▶│ Driving port     │       │   (Lõi calls OUT)
                   │   │ IQuizService     │       │
   CLI         ────────▶│                 │       │   ┌──────────────┐
                   │   │  ┌────────────┐  │       │   │ Driven port  │
   Test driver ────────▶│ │ DOMAIN     │ ─┼───────┼──▶│ IRepository  │ ──▶ Sqlite
                   │   │ │ CORE       │  │       │   └──────────────┘
   Kafka       ────────▶│ │ pure logic │  │       │
   consumer        │   │ └────────────┘  │       │   ┌──────────────┐
                   │   │                 │ ──────┼──▶│ INotifier    │ ──▶ SMTP
                   │   └─────────────────┘       │   └──────────────┘
                   └──────────────────────────────┘
```

### 1.3. Neuroscience analogy — Sensory substitution

Ba thí nghiệm kinh điển dạy ta Hexagonal sinh học là **có thật**, không phải metaphor:

**(a) Bach-y-Rita 1969 — TVSS (Tactile-Visual Sensory Substitution)**
- Người mù bẩm sinh đeo camera trên trán; output 20×20 = 400 rung tử áp vào lưng.
- Sau vài giờ luyện: phân biệt hình khối, sau vài tuần: nhận diện khuôn mặt, đoạt được "tới gần / xa ra".
- Bằng fMRI: **cortex thị giác V1 sáng lên**, mặc dù tín hiệu đi vào qua *da chứ không phải retina*.
- → V1 là **driving port** "abstract spatial pattern". Retina là driving adapter mặc định, da là *adapter thay thế* sau khi train.

**(b) Cochlear implant (Wilson, 1972 → present)**
- 22 điện cực cấy vào ốc tai, kích thích trực tiếp nhánh thính giác (CN VIII).
- Bypass hoàn toàn lông mao trong (hair cells) — thiết bị sinh học bị hỏng.
- Cortex thính giác A1 nhận tín hiệu mới, sau training nghe được lời nói rõ ràng (>80% accuracy người trưởng thành).
- → A1 là driving port "spectral-temporal frequency". Hair cells (adapter sinh học) bị thay bằng chip (adapter điện tử).

**(c) Argus II 2011 — Retinal prosthesis**
- 60 điện cực mảng cấy lên võng mạc; camera mắt kính → wireless → kích thích retina.
- Bệnh nhân *retinitis pigmentosa* (mất tế bào que/nón) "thấy" được phosphene, đường viền đồ vật.
- → V1 là core domain; sensor pluggable.

**(d) Reverse — driven port substitution**
- Người cụt tay học vẽ bằng chân (mouth painters, foot painters): planning cortex (M1, SMA, PFC) là driving port "motor intent"; tay là driven adapter mặc định, chân/miệng là adapter thay thế. Lõi planning **không thay đổi**.

**Bài học architectural**: brain *không* hard-code I/O. Nó định nghĩa **abstract format** ở port, các giác quan/cơ quan là adapters. Đó là *raison d'être* của Hexagonal: lõi business không hard-code I/O.

### 1.4. So sánh với Lesson 28 (DIP) và Lesson 29 (Clean)

| | Lesson 28 — DIP | Lesson 29 — Clean | Lesson 30 — Hexagonal |
|---|---|---|---|
| **Tầm áp dụng** | Class-level | System-level (4 vòng) | System-level (2 vùng symmetric) |
| **Số layer/vùng** | Không quy định | 4 vòng đồng tâm | 2 vùng (inside / outside), nhưng outside chia 2 phía |
| **Quy tắc cốt lõi** | High-level → abstraction ← Low-level | Outer depends on inner; Dependency Rule | Inside không biết outside; outside chia driving / driven |
| **Symmetry** | Không nhấn | Implicit qua vòng | **Explicit**: driving ≠ driven |
| **Khi nào tốt nhất** | Mọi nơi cần test/swap | Service phức tạp, nhiều use case, team lớn | Service vừa, focus vào *pluggability of I/O* |

> **Mối quan hệ thật**: Hexagonal *là một biến thể đơn giản hoá của Clean Arch* tập trung vào I/O boundary. Clean = Hex + use case layer + entity layer rõ. Onion (Palermo 2008) là biến thể nữa, gần như Hex với tên khác. Trong thực tế, nhiều dự án dùng "Clean inside, Hex naming on the boundary" — không xung đột.

---

## MỨC 2 — CẤU TRÚC

### 2.1. Bốn vai diễn

```
┌─────────────────────────────────────────────────────────┐
│                 1. DOMAIN CORE                          │
│   - Entity (Question, Submission, User)                 │
│   - Domain service (ScoringService, RankingService)     │
│   - Pure Python, không import framework / I/O           │
│   - Định nghĩa các DRIVING PORTS và DRIVEN PORTS        │
└─────────────────────────────────────────────────────────┘
                       ▲                    │
                       │ implements         │ requires
                       │                    ▼
┌─────────────────────────────────────────────────────────┐
│      2. DRIVING PORTS (interfaces lõi cung cấp)         │
│   - IQuizApplicationService                             │
│   - Khai báo: "Tôi có submit_quiz(), get_ranking(),..." │
└─────────────────────────────────────────────────────────┘
              ▲                              │
              │                              │
┌─────────────┴────────┐         ┌───────────┴─────────────┐
│ 3. DRIVING ADAPTERS  │         │ 4. DRIVEN PORTS         │
│   (calls into core)  │         │  (interfaces lõi cần)   │
│                      │         │ - ISubmissionRepository │
│ - HTTPController     │         │ - INotifier             │
│ - CLIController      │         │ - IClock                │
│ - EventConsumer      │         └─────────────────────────┘
│ - TestDriver         │                    ▲
└──────────────────────┘                    │ implements
                                            │
                                ┌───────────┴─────────────┐
                                │ 5. DRIVEN ADAPTERS      │
                                │   (called by core)      │
                                │ - SqliteRepository      │
                                │ - SmtpEmailNotifier     │
                                │ - SystemClock           │
                                └─────────────────────────┘
```

### 2.2. Quy tắc bắt buộc (invariants)

Bốn rule này nếu vi phạm là *không còn* Hexagonal:

1. **Domain core không import** thứ gì từ adapter package (`infra/`, `web/`, `cli/`).
2. **Driving port** được định nghĩa *bởi domain core*. Driving adapter import port từ core, không ngược lại.
3. **Driven port** cũng định nghĩa *bởi domain core*. Driven adapter implement port; *core không bao giờ import adapter cụ thể*.
4. **Composition root** (1 file `main.py` / `bootstrap.py`) là *nơi duy nhất* biết về cả core lẫn adapter cụ thể, để wire.

> Quan trọng: *driven port là contract DO LÕI ĐỊNH NGHĨA, không phải DO ADAPTER ĐỊNH NGHĨA*. Đó là điểm mấu chốt phân biệt Hexagonal đúng nghĩa với "tầng repository ngẫu nhiên". Adapter phải uốn theo lõi, không phải lõi uốn theo SQL/HTTP/MQ. Cockburn gọi đây là "**dependency inversion at the architectural seam**".

### 2.3. Biến thể

| Biến thể | Khác biệt | Khi dùng |
|----------|-----------|----------|
| **Classic Hex (Cockburn)** | 2 vùng, port/adapter | Default |
| **Onion (Palermo)** | Nhiều vòng đồng tâm gần Clean | Khi muốn nhấn entity-vs-service |
| **Clean (Martin)** | 4 vòng + Dependency Rule | Hệ lớn, nhiều use case riêng biệt |
| **Functional Core, Imperative Shell (G. Bernhardt)** | Core = pure functions, shell = side effects | Khi domain dễ functional (calc, parser) |
| **Domain-Driven Hex** | Hex + DDD aggregates/bounded contexts | Domain phức tạp, ngôn ngữ nghiệp vụ giàu |

Tất cả 5 cùng *cùng tinh thần* — domain trung lập với I/O. Khác biệt chủ yếu là *nomenclature* và *mức độ chia layer bên trong core*.

### 2.4. Luồng điều khiển khi 1 request đi qua hệ

```
1. HTTP request POST /submissions arrive
2. Driving adapter (FlaskController) parse JSON → SubmissionDTO
3. FlaskController call → driving port: app_service.submit_quiz(dto)
4. Application service (in core) orchestrate:
     - call domain service: scoring_service.score(submission)
     - call driven port:  repo.save(submission)
     - call driven port:  notifier.send_receipt(user, score)
5. App service return result DTO
6. Driving adapter serialize → HTTP 200 with JSON body
```

Lõi *không biết* HTTP. Đổi adapter sang CLI: bước 1-2 và 6 thay; bước 3-5 nguyên xi.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
package domain:
    entity Submission { user_id, answers, submitted_at }
    entity ScoreResult { score, breakdown }

    interface ISubmissionRepository:    # driven port
        save(submission) -> id
        find_by_user(user_id) -> List[Submission]

    interface INotifier:                # driven port
        send_receipt(user_id, score)

    interface IClock:                   # driven port (testability)
        now() -> datetime

    class ScoringService:               # domain logic, pure
        def score(submission) -> ScoreResult: ...

    interface IQuizApplicationService:  # driving port (use case)
        submit_quiz(dto) -> ScoreDTO
        get_history(user_id) -> List[ScoreDTO]

    class QuizApplicationService implements IQuizApplicationService:
        def __init__(repo: ISubmissionRepository,
                     notifier: INotifier,
                     scoring: ScoringService,
                     clock: IClock): ...
        def submit_quiz(dto):
            sub = Submission(dto, clock.now())
            score = scoring.score(sub)
            repo.save(sub)
            notifier.send_receipt(sub.user_id, score)
            return ScoreDTO(score)

package infra:                          # driven adapters
    class SqliteSubmissionRepo implements ISubmissionRepository
    class MemorySubmissionRepo implements ISubmissionRepository
    class SmtpNotifier implements INotifier
    class LogNotifier implements INotifier
    class SystemClock implements IClock
    class FixedClock(t) implements IClock      # test

package web:                            # driving adapter
    class FlaskController:
        def __init__(app_service: IQuizApplicationService): ...
        @route POST /submissions: app_service.submit_quiz(...)

package cli:                            # driving adapter
    class CLIController:
        def __init__(app_service: IQuizApplicationService): ...
        def main(argv): app_service.submit_quiz(...)

package events:                         # driving adapter
    class KafkaConsumer:
        def __init__(app_service: IQuizApplicationService): ...
        on_message(msg): app_service.submit_quiz(...)

package bootstrap:                      # composition root
    def build_production_app():
        repo = SqliteSubmissionRepo("prod.db")
        notifier = SmtpNotifier(...)
        clock = SystemClock()
        scoring = ScoringService()
        app_service = QuizApplicationService(repo, notifier, scoring, clock)
        return FlaskController(app_service)

    def build_test_app(fixed_now):
        repo = MemorySubmissionRepo()
        notifier = LogNotifier()
        clock = FixedClock(fixed_now)
        ...
```

### 3.2. Hai trục chính cần nắm

**Trục 1 — Vertical (driving / driven)**: bên trái cắm vào, bên phải lõi cắm ra. *Không có cái thứ ba*.

**Trục 2 — Horizontal (port / adapter)**: port là *abstraction* (do core sở hữu), adapter là *implementation* (do infra sở hữu). Đảo ngược → leaky.

Mọi quyết định kiến trúc kiểu Hex đều có thể quy về 1 trong 4 ô của bảng 2x2 này:

|  | Driving | Driven |
|---|---|---|
| **Port** | `IQuizApplicationService` | `ISubmissionRepository`, `INotifier` |
| **Adapter** | `FlaskController`, `CLIController` | `SqliteRepository`, `SmtpNotifier` |

---

## NĂM CHIỀU SO SÁNH (in não vs in code)

| Chiều | Trong não (Sensory substitution) | Trong code (Hexagonal) |
|-------|----------------------------------|-------------------------|
| **Cấu tạo** | V1, A1, M1 cortex (lõi); retina, cochlea, da, cơ (adapters); abstract sensory/motor format (port) | `domain/` package (core + ports); `infra/`, `web/`, `cli/` (adapters); `Protocol` / `ABC` (port) |
| **Vị trí** | Cortex ở trung tâm não; sense organs ngoại vi | `domain/` ở folder gốc, không import gì ngoài std-lib; adapter folder ở ngoài, import từ `domain/` |
| **Chức năng** | Cortex *xử lý* tín hiệu abstract; cơ quan *dịch* tín hiệu môi trường ↔ format abstract | Domain *thực thi business rule*; adapter *dịch* HTTP/SQL/SMTP ↔ method call thuần |
| **Kết nối** | Sense → V1 qua thalamic relay; M1 → cơ qua spinal cord | Driving adapter → driving port → app service; app service → driven port → driven adapter |
| **Ý nghĩa** | Lõi tiến hoá ổn định, ngoại vi pluggable → robust khi mất giác quan, học sense substitution | Lõi business stable, I/O thay đổi → đổi DB/UI/MQ không sửa logic; test core không cần real DB |

---

## BA VÍ DỤ

### Ví dụ 1 — Vận hành thường (happy path)

User submit quiz qua HTTP → core scoring → save vào memory + log notify.
Sau đó cùng lõi đó được gọi qua CLI và qua event message — *không thay đổi 1 dòng* trong domain core.

```python
# composition root chọn adapters
repo = MemorySubmissionRepo()
notifier = LogNotifier()
clock = SystemClock()
app = QuizApplicationService(repo, notifier, ScoringService(), clock)

# 1) qua HTTP
http_ctrl = HTTPController(app)
http_ctrl.handle_post("/submissions", body={...})

# 2) qua CLI — cùng app
cli_ctrl = CLIController(app)
cli_ctrl.main(["submit", "--user", "u1", "--answers", "1,2,3"])

# 3) qua Event consumer — cùng app
consumer = EventConsumer(app)
consumer.on_message({"user_id": "u1", "answers": [1,2,3]})
```

### Ví dụ 2 — Hỏng / vi phạm (failure mode)

**Vi phạm A — Lõi import sqlite3 trực tiếp** (leaky core):

```python
# BAD — domain/scoring_service.py
import sqlite3   # ← cấm tuyệt đối
class ScoringService:
    def score(self, sub):
        conn = sqlite3.connect("quiz.db")
        ...
```

→ Hậu quả: muốn đổi Postgres phải sửa domain → mất pluggability. Test phải có file SQLite. Đây là *anti-pattern Anemic Adapter* (logic ở wrong place).

**Vi phạm B — Adapter định nghĩa contract**:

```python
# BAD — infra/repo.py
class SqliteRepository:
    def save(self, sub): ...
    def find_by_user(self, user_id): ...

# domain/app_service.py — phụ thuộc concrete class
from infra.repo import SqliteRepository       # ← sai chiều
class QuizApplicationService:
    def __init__(self, repo: SqliteRepository): ...
```

→ Đảo ngược dependency. Đổi adapter = đổi import + sửa type hint trong core. *Dependency Rule* bị phá. (So sánh: Lesson 28 DIP đã giảng đúng cách — port phải ở `domain/ports.py`).

**Vi phạm C — Driving adapter chứa logic**:

```python
# BAD — web/controller.py
@app.post("/submissions")
def submit():
    body = request.json
    # tính điểm tại đây
    score = sum(1 for a in body["answers"] if a == correct)   # ← BUSINESS RULE Ở SAI CHỖ
    return {"score": score}
```

→ Logic không testable trừ khi spawn Flask. Khi đổi sang CLI phải copy-paste. *Anti-pattern God Controller*.

### Ví dụ 3 — Ứng dụng Ellumm Quiz

Refactor `quiz_god.py` từ Lesson 28 lên Hexagonal:

```
domain/
  entities.py          # Submission, Question, ScoreResult
  scoring.py           # ScoringService (pure)
  ports.py             # ISubmissionRepository, INotifier, IClock
  app_service.py       # IQuizApplicationService + impl
infra/
  memory_repo.py
  sqlite_repo.py
  log_notifier.py
  email_notifier.py
  system_clock.py
  fixed_clock.py
web/
  http_controller.py   # driving adapter
cli/
  cli_controller.py    # driving adapter
events/
  event_consumer.py    # driving adapter
bootstrap/
  composition_root.py  # wire mọi thứ
main.py                # entry point
```

Test pure (không khởi động framework, không file DB):

```python
def test_submit_quiz_calculates_score():
    repo = MemorySubmissionRepo()
    notifier = LogNotifier()
    clock = FixedClock(datetime(2026, 5, 6))
    app = QuizApplicationService(repo, notifier, ScoringService(), clock)

    result = app.submit_quiz(SubmissionDTO(user_id="u1", answers=[1, 0, 1]))

    assert result.score == 2
    assert len(repo.list_all()) == 1
    assert notifier.last_sent[0] == "u1"
```

Không Flask, không Postgres, không SMTP. Chạy 0.x ms. Đây mới là điểm bán hàng thực sự của Hexagonal.

---

## MỨC ARCHITECT — TRADE-OFFS, KHI NÀO DÙNG / KHÔNG, ANTI-PATTERNS

### Khi nào DÙNG

- Service có **>= 2 driving adapter** (HTTP + CLI, hoặc HTTP + event consumer): symmetry trả về tiền lập tức.
- Service có **>= 2 driven adapter alternatives** (Sqlite cho dev, Postgres cho prod, Memory cho test).
- Domain logic phức tạp đáng test in-process (>5 unit case logic thuần).
- Bạn dự đoán **đổi DB / đổi UI framework** trong vòng 2-3 năm tới.
- Team muốn **TDD theo domain trước**, để I/O quyết định sau.

### Khi nào KHÔNG dùng (hoặc dùng nhẹ)

- **Service CRUD-only**: 80% endpoint là "select * + JSON serialize". Hex đặt ra port-adapter cho mỗi field là vô nghĩa.
- **Prototype / spike < 200 LOC**: boilerplate port khiến iter chậm.
- **Domain rất đơn giản** (calculator, converter): functional core đủ.
- **Stateless lambda 1 hàm**: không có gì để hex hoá.
- Khi bạn hoặc team **chưa nắm SOLID** — Hex sẽ chỉ là vỏ ngoài, bên trong vẫn god class.

> Tôn chỉ: **độ phức tạp domain + số adapter alternatives** quyết định ROI của Hex. Service nhỏ, ít alternative → bỏ qua. Service vừa-lớn, > 1 driving + > 1 driven → *vô cùng đáng*.

### Trade-offs

| Trục | Hex được | Hex mất |
|------|----------|---------|
| **Boilerplate** | Test pure, không I/O thật | Mỗi entity 1 port + 1+ adapter |
| **Curve học** | Onboard người mới có map rõ | 2 tuần đầu hỏi "port để ở đâu?" |
| **Đổi I/O** | Sub-second swap (DI) | 1 lần initial setup composition root tốn 1-2 ngày |
| **Performance** | Domain pure → CPU-bound | 1-2 lớp gọi hàm thừa (negligible <1µs) |
| **Test** | Unit test chạy 1000x nhanh hơn | Cần test riêng cho mỗi adapter (integration) |

### Anti-patterns thường thấy

| Anti-pattern | Mô tả | Cách phát hiện |
|--------------|-------|----------------|
| **Leaky core** | Domain import sqlite3, requests, smtplib | grep `domain/` cho từ "import sqlite\|requests\|smtplib\|kafka" — phải rỗng |
| **Anemic core** | Logic ở adapter, core chỉ là pass-through | Đếm dòng code domain vs adapter — domain < 20% là red flag |
| **Smart adapter** | Adapter có nhánh `if`/`else` về business rule | Adapter chỉ được phép có logic *mapping* và *error translation* |
| **Hexagon stew** | Có port nhưng adapter gọi nhau qua port → vòng lẩn quẩn | Vẽ dependency graph — phải DAG outside → port ← inside |
| **Port quá to** | 1 port với 30 method | Áp dụng ISP (Lesson 27): tách thành nhiều port nhỏ |
| **Port quá nhỏ** | Mỗi method 1 port → 50 file | Gom port theo *role* không phải *method* |
| **Composition root rò ra ngoài** | Nhiều file biết về wiring | 1 nơi duy nhất import cả core lẫn infra concrete |
| **Mock thay adapter trong test** | Mock lib mà chính adapter là mock | Test core dùng *real adapter in-memory* (`MemoryRepo`), không `mock.Mock()` |

### Checklist trước khi merge PR (Hex review)

- [ ] `domain/` không import `infra/`, `web/`, `cli/` (grep verify).
- [ ] Mọi driven dependency của app service được inject qua `__init__`.
- [ ] Có ít nhất 1 in-memory adapter cho mỗi driven port (test).
- [ ] Driving adapter chỉ làm 3 việc: parse input → call port → format output.
- [ ] Composition root duy nhất, không scatter.
- [ ] Driving port có ít nhất 1 unit test thuần (no I/O).
- [ ] Adapter có ít nhất 1 contract test ép tuân port (Liskov, Lesson 26).
- [ ] Đổi adapter (Sqlite ↔ Memory) không cần sửa domain test.

### So sánh với pattern lân cận

| Pattern | Tầm áp dụng | Quy tắc | Khác biệt với Hex |
|---------|-------------|---------|-------------------|
| **DIP (Lesson 28)** | Class | Phụ thuộc abstraction | Hex = DIP nâng lên *kiến trúc*, định nghĩa thêm khái niệm port/adapter và driving/driven |
| **Clean (Lesson 29)** | System | 4 vòng + Dependency Rule | Hex đơn giản hơn, 2 vùng; Clean nhấn use case layer riêng. Hex symmetry input/output rõ hơn |
| **Onion (Palermo 2008)** | System | Vòng đồng tâm domain ở giữa | Tương đương Hex; tên khác, nhấn entity vs service |
| **Layered (n-tier)** | System | UI → BL → DAL một chiều | Asymmetric, dễ leak (BL biết SQL). Hex symmetric, lõi *không* biết I/O |
| **Functional Core / Imperative Shell** | Module | Pure core + side-effect shell | Hex chấp nhận core có state (entity); FC/IS đẩy state ra ngoài hoàn toàn |
| **DDD Bounded Context** | Sub-system | Mỗi context có ngôn ngữ riêng | Trực giao với Hex — dùng được cùng (Hex *trong* mỗi context) |

### Kết hợp với GoF patterns

Hex **không thay** GoF; nó là *nơi để dán GoF*. Một số kết hợp tự nhiên:

- **Factory (Lesson 2)** trong composition root để build adapter family theo env.
- **Strategy (Lesson 21)** chính là driven port: `IScoringStrategy`, swap implementation.
- **Adapter (Lesson 6)** literal — driven adapter hay là Adapter pattern dán nhãn API ngoài về port.
- **Decorator (Lesson 9)** wrap port: `LoggingNotifier(real_notifier)`, `RetryRepository(real_repo)`.
- **Observer (Lesson 19)** + **Mediator (Lesson 17)** thường nằm *trong* core domain để event hoá.
- **Command (Lesson 14)** đóng gói lời gọi vào driving port → dễ queue, retry, undo.

---

## BÀI TẬP — 4 MỨC

### Mức 1 — Cơ bản (45 phút)

Lấy `quiz_god.py` baseline. Tách thành 3 file: `domain.py`, `infra.py`, `main.py`. Định nghĩa 1 driven port `ISubmissionRepository`, implement bằng `MemorySubmissionRepo`. Đảm bảo `domain.py` không import gì ngoài `dataclasses` và `typing`. Verify bằng `grep`.

### Mức 2 — Trung bình (1.5 giờ)

Thêm 1 driving adapter thứ hai (CLI nếu đã có HTTP, ngược lại). Cùng app service phục vụ cả hai. Viết test pure cho app service không khởi động Flask/argparse. Đo thời gian test trước và sau.

### Mức 3 — Khó (architect, 3 giờ)

(a) Thêm `INotifier` driven port với 2 adapter: `LogNotifier`, `EmailNotifier`. Wrap `EmailNotifier` bằng `RetryNotifier(adapter, max=3)` (Decorator). Test pure không SMTP.

(b) Thêm `IClock` port để control thời gian trong test. So sánh test fragility trước/sau.

(c) Vẽ dependency graph (Mermaid) cho project sau khi xong. Verify không có vòng từ `domain/` ra `infra/`.

### Mức 4 — Mở rộng neuro (2 giờ, tự do)

Đọc paper Bach-y-Rita 1969 (1 trang đầu) hoặc xem TED talk *"Sensory Substitution"* của David Eagleman 2015. Trả lời 3 câu:

1. *Plasticity* nào của cortex cho phép sense substitution? (Hint: Hebbian + competition.) Áp dụng trong code: lúc nào core mới *thực sự* "không biết" adapter — và lúc nào nó vô tình biết qua type leak / exception leak?

2. Cochlear implant ban đầu chỉ có 4 điện cực, sau đó tăng lên 22. Đó là tăng *resolution* của adapter, *không* tăng port. Tương tự trong code: khi nào nên thêm method vào port hiện tại vs tách port mới? Liên hệ ISP.

3. Argus II chỉ cho 60 phosphene — *information bottleneck* tại port. Trong service Hex, port quá hẹp (DTO thiếu field) gây vấn đề gì? Quá rộng (DTO chứa cả ORM object) gây vấn đề gì? Tự nghĩ một heuristic chọn DTO width.

---

## ĐỒ HOẠ TỔNG KẾT

```
                    HEXAGONAL ARCHITECTURE
       ┌──────────────────────────────────────────────────┐
       │                                                  │
  HTTP─┤                  ┌────────────────┐              │
       │ driving          │                │ driven       │ ─► SQLite
  CLI ─┤ adapters         │   DOMAIN CORE  │  adapters    │
       │     ─►ports─►    │   ScoringSvc   │ ─►ports─►    │ ─► SMTP
  EVT ─┤                  │   AppService   │              │
       │                  │                │              │ ─► Redis
  TEST─┤                  └────────────────┘              │
       │                                                  │
       └──────────────────────────────────────────────────┘
              ↑                  ↑                ↑
              "ai gọi vào"    "logic thuần"    "lõi gọi ra"
              symmetric, pluggable, swap-without-touching-core
```

> **Tóm lại**: Hexagonal = "lõi domain pure + ports do lõi sở hữu + adapters cắm vào". Brain analogy là sensory substitution — đổi adapter (mắt → da → camera điện cực) mà cortex vẫn hoạt động. Trong code: đổi DB / UI / MQ mà domain logic vẫn nguyên. Đó là *tự do kiến trúc*.

---

## TIẾP THEO

- **Lesson 31 — EDA (Event-Driven Architecture)**: thay vì gọi driven port đồng bộ, *publish event*. Adapter đăng ký subscriber. Bước nhảy lớn từ sync sang async.
- **Lesson 32 — CQRS + Event Sourcing**: tách driving port write khỏi driving port read; lưu *chuỗi event* thay vì state.
