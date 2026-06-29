# Lesson 28 — DIP (Dependency Inversion Principle)
## Thalamus Relay — Cortex (high-level) ĐỊNH NGHĨA format, retina (low-level) PHẢI ADAPT

---

## TÓM TẮT MỘT DÒNG

**DIP** = đảo chiều sự phụ thuộc trong source code. Module **cấp cao** (business logic) không phụ thuộc module **cấp thấp** (DB, HTTP, file system); cả hai phụ thuộc một **abstraction**, và abstraction đó được **định nghĩa bởi cấp cao** (consumer-driven).

> Cortex là "high-level brain" — nó chứa business logic của nhận thức. Retina, cochlea, da là "low-level periphery" — chúng chỉ là *sensor hardware*. Trong tự nhiên, chúng không nói chuyện trực tiếp. Mọi sensory pathway (trừ smell) đều đi qua **thalamus** — LGN cho thị giác, MGN cho thính giác, VPL cho da. Thalamus *convert* tín hiệu thô thành "spike train pattern" theo format mà cortex expect: tần số ~30-50 Hz, retinotopic mapping, temporal coding cụ thể. Cortex không biết HOW retina hoạt động — nó chỉ biết *contract của thalamic relay*. Bằng chứng cực mạnh: **sensory substitution** (Bach-y-Rita 1969 — camera → vibrator trên lưng → người mù "thấy"), **cochlear implant** (bypass cochlea hỏng, cấp tín hiệu trực tiếp vào auditory nerve theo format cortex expect), **retinal prosthesis** (Argus II). Tất cả đều work vì cortex phụ thuộc *abstraction* (spike train pattern), không phụ thuộc *concrete sensor*. Đó là DIP sinh học. **Olfactory cortex** — *ngoại lệ duy nhất bỏ qua thalamus* — là minh hoạ ngược: olfaction tightly coupled with periphery, khó substitute, và đó là một trong những hệ giác quan kém flexible nhất.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Tình huống "tự nhiên" khi viết code: `QuizService` cần lưu submission → import `SQLiteRepository` → gọi `repo.save(...)`. Code đọc top-down.

```python
# service.py
from infrastructure.sqlite_repo import SQLiteRepository

class QuizService:
    def __init__(self):
        self.repo = SQLiteRepository("quiz.db")  # ← phụ thuộc cụ thể
    
    def submit(self, user, answers):
        result = self.score(answers)
        self.repo.save(user, result)
```

3 hậu quả khi cần:
1. **Đổi sang Postgres** → sửa `service.py` (vi phạm OCP, tested code bị disturb).
2. **Test unit cho `submit`** → phải khởi tạo SQLite (tempfile, schema, cleanup) → unit test trở thành integration test.
3. **Service phụ thuộc framework** — `service.py` import `sqlite3`, `psycopg2`, `pymongo`, hoặc tệ hơn là `boto3`/`requests`. Business logic bị "ô nhiễm" infrastructure.

**Triệu chứng tổng quát**: business logic không thể test/run/reason độc lập với infrastructure. Mỗi đổi DB/HTTP/queue đều ripple lên use case.

DIP đảo chiều: **business logic định nghĩa abstraction nó cần**; infrastructure *implements* abstraction đó.

### 1.2. Định nghĩa

**Robert C. Martin 1996** (*Object Mentor* article, sau đưa vào *Agile Software Development* 2002):
> *"A. High-level modules should not depend on low-level modules. Both should depend on abstractions.*
> *B. Abstractions should not depend on details. Details should depend on abstractions."*

Hai vế bổ sung nhau:
- **Vế A**: cả high-level và low-level cùng phụ thuộc abstraction. *Hướng* phụ thuộc bị đảo so với "tự nhiên".
- **Vế B**: abstraction không được biết về detail. Detail (concrete impl) là kẻ thực hiện theo abstraction.

Cốt lõi: **ai sở hữu abstraction?** — *cấp cao*. Abstraction là declaration của *what consumer needs*, không phải *what provider offers*.

### 1.3. "Inversion" là gì? — phân tích kỹ

Đây là điểm hay nhầm. Bạn hỏi: "Module A có method gọi module B; runtime thì A → B; điều đó không inverted gì cả?". Đúng — *runtime call direction* không bị đảo. Đảo là **source-code dependency direction**:

#### Trước DIP (natural top-down):
```
Source code import:  service.py  --imports-->  sqlite_repo.py  --imports--> sqlite3
Runtime call:        service     --calls-->    sqlite_repo     --calls-->   sqlite3
```
→ source-code direction = runtime direction. Service "biết về" SQLite.

#### Sau DIP (inverted):
```
Source code import:  service.py  --imports-->  abstractions.py  (in same high-level package)
                     sqlite_repo.py  --imports-->  abstractions.py
                     
Runtime call:        service     --calls-->    sqlite_repo (concrete instance via DI)
```
→ source-code direction = NGƯỢC chiều với runtime. Service không "biết" SQLite tồn tại; SQLite biết về service's abstraction.

**Hệ quả quan trọng**: package `service/` không có dòng `from infrastructure import ...`. Bạn xoá hẳn folder `infrastructure/`, `service/` vẫn compile (chỉ runtime fail nếu không inject impl). Đó là *true decoupling*.

### 1.4. Hiểu sai phổ biến

| Hiểu sai | Hiểu đúng |
|----------|-----------|
| "DIP = dùng interface" | Một nửa. *Ai sở hữu* interface mới quan trọng. Interface ở provider package = không phải DIP |
| "DIP = dependency injection" | DI là **kỹ thuật** thực thi DIP. DIP là **nguyên tắc** về *direction*. Có thể DI mà vẫn vi phạm DIP (inject concrete) |
| "DIP = inheritance từ abstract base" | Inheritance là một cách. Composition + Protocol cũng đạt DIP |
| "DIP đảo runtime call" | KHÔNG. DIP đảo *source-code dependency*. Runtime call vẫn từ high → low |
| "DIP nghĩa là không có concrete class" | Tất nhiên có. DIP nói cấp cao không *biết* concrete; concrete tồn tại ở cấp thấp |

### 1.5. Neuroscience analogy — Thalamus relay + sensory substitution

#### Cơ chế 1 — Thalamus là "abstraction layer" của não

Não người tổ chức theo *layered architecture*:

```
                    ┌─────────────────────────────┐
                    │  CORTEX (high-level policy) │
                    │  - perception, decision      │
                    │  - depends on:               │
                    │    "spike train pattern"     │ ← abstraction
                    └──────────────┬──────────────┘
                                   ↑ (consume abstract format)
                    ┌──────────────┴──────────────┐
                    │  THALAMUS (relay/adapter)   │
                    │  - LGN (vision)             │
                    │  - MGN (audition)           │
                    │  - VPL (touch)              │
                    │  Convert: peripheral signal │
                    │           → cortical format │
                    └──────────────┬──────────────┘
                                   ↑ (raw sensor stream)
                    ┌──────────────┴──────────────┐
                    │  PERIPHERY (low-level)      │
                    │  - retina photoreceptor     │
                    │  - cochlea hair cell        │
                    │  - skin mechanoreceptor     │
                    └─────────────────────────────┘
```

Cortex không nói chuyện trực tiếp với photoreceptor. Lý do:
- **Format mismatch**: photoreceptor signal chậm, analog, biên độ thay đổi; cortex cần spike train rời rạc, frequency-coded.
- **Spatial reorganization**: retina là 2D analog, cần map sang retinotopic cortical surface.
- **Temporal preprocessing**: thalamus filter, gain control, attention modulation trước khi cortex thấy.

LGN có 6 layer (magnocellular 1-2 cho motion, parvocellular 3-6 cho color/form) — đây là *adapter* convert retina output sang chuẩn V1 expect. Cortex không cần biết retina có bao nhiêu cone, mật độ thế nào — chỉ thấy spike train từ LGN.

#### Cơ chế 2 — Sensory substitution: bằng chứng cortex phụ thuộc *abstraction*, không phụ thuộc *sensor*

Nếu cortex phụ thuộc retina cụ thể, bạn không thể thay retina bằng cảm biến khác. Nhưng thực tế:

**Bach-y-Rita 1969** (*Nature*, "Vision substitution by tactile image projection"): camera → ma trận 400 vibrators trên lưng người mù → sau training, người mù mô tả "thấy" hình dạng. Cortex thị giác (V1) **remap** để xử lý input mới.

**TDU (Tongue Display Unit)** — BrainPort (Wicab Inc., FDA approved 2015): camera → 400-pixel grid điện cực trên lưỡi → người mù điều hướng, đọc chữ in lớn. Lưỡi nhạy hơn lưng → resolution cao hơn.

**Cochlear implant** (>1 triệu user toàn cầu): bypass cochlea hỏng → 12-22 điện cực trực tiếp kích thích auditory nerve theo format A1 expect (tonotopic, frequency-encoded). Người điếc bẩm sinh học nghe.

**Argus II retinal prosthesis** (FDA approved 2013): 60-pixel implant trên retina → kích thích RGC sống sót → tín hiệu qua optic nerve → LGN → V1. Người mù retinitis pigmentosa thấy ánh sáng/hình dạng đơn giản.

**Cortical visual prosthesis** (Orion, Second Sight 2018): bypass cả retina + LGN, cấp tín hiệu trực tiếp vào V1 surface. Cortex *vẫn perceive* — vì input đã có format spike train đúng.

→ Mỗi case: **cortex giữ nguyên, sensor (low-level) thay đổi**. Đây là DIP run trong não. Sensor mới phải implement contract "spike train cortex expect" (tonotopic, retinotopic, temporal pattern); cortex không sửa gì — nó *consume* abstraction.

#### Cơ chế 3 — Olfactory bypass: counter-example coupling chặt

Smell là **giác quan duy nhất** bỏ qua thalamus:
```
Olfactory receptors (mũi)
    ↓
Olfactory bulb
    ↓ (KHÔNG qua thalamus)
Piriform cortex (olfactory cortex)
```

Lý do tiến hoá: olfaction là giác quan cổ nhất (≥ 500 triệu năm), tồn tại trước khi thalamus phân hoá. Olfactory cortex *tightly coupled* với olfactory periphery — direct connection, không có "format conversion" layer.

Hậu quả:
- Olfactory hallucinations cực hiếm (so với vision/audition) — vì cortex không có "abstract slot" để sai loạn.
- **Sensory substitution cho olfaction là một trong những hướng khó nhất** — không có "thalamic format" để adapt sensor mới vào.
- Anosmia (mất smell) khó phục hồi qua prosthesis hơn deafness/blindness.

→ Đây là minh hoạ "natural top-down dependency" trong sinh học: cortex *biết* periphery → tight coupling → khó swap. Vision/audition đảo chiều qua thalamus, olfaction giữ chiều thẳng.

#### Cơ chế 4 — Locus coeruleus / nucleus basalis: hub broadcast neuromodulator

Một số neurotransmitter system khác cũng theo pattern DIP:

- **Locus coeruleus** (LC) là single nucleus trong brainstem (~15,000 neuron) — nó project axon đến *toàn cortex* để release norepinephrine. Cortex không biết LC ở đâu cụ thể; nó chỉ "consume NE level" như abstract param điều chỉnh attention/arousal.
- **Nucleus basalis of Meynert** — hub cholinergic tương tự cho ACh.
- **VTA + substantia nigra** — hub dopamine.

Các hub này là *concrete provider* của abstract param (NE level, ACh level, DA level). Cortex consume — không phụ thuộc identity của hub. Có thể tổn thương 1 phần LC, các neuron LC khác bù — cortex không nhận ra.

#### 5 chiều của analogy

| Chiều | Trong não (thalamus + sensory substitution) | Trong code (DIP) |
|-------|----------------------------------------------|-------------------|
| **Cấu tạo** | LGN 6 layer (magno + parvo); MGN tonotopic; VPL somatotopic — adapter chuyên biệt cho từng sense | Abstract interface ở high-level package; adapter (concrete impl) ở infrastructure package |
| **Vị trí** | Thalamus ở giữa periphery và cortex — geometric center | Interface declared ở high-level (consumer); adapter ở low-level (provider) |
| **Chức năng** | Convert raw signal → spike train pattern cortex consume | Adapter convert low-level format → high-level abstraction; high-level chỉ thấy abstraction |
| **Kết nối** | Periphery depends on thalamic format (or doesn't connect to cortex). Cortex defines format. | Low-level depends on (implements) interface. High-level OWNS interface. Source code direction inverted |
| **Ý nghĩa** | Cortex remap khi sensor thay đổi → flexibility. Olfactory bypass = tight coupling = khó substitute | Test high-level không cần infrastructure. Swap DB/HTTP/queue không sửa business logic. Olfactory analog = anti-pattern monolith |

### 1.6. Khi nào DÙNG DIP nghiêm

- Boundary giữa **business logic** và **infrastructure** (DB, HTTP client, message queue, file system, external API).
- Public library — consumer định nghĩa contract, library impl.
- Plugin / extension architecture (3rd-party impl interface bạn define).
- Khi muốn **unit test high-level pure** (không I/O, không network).
- Khi system có potential thay đổi infrastructure (cloud migration, vendor swap).

### 1.7. Khi nào KHÔNG dùng (over-DIP)

- Internal helper class, không cross boundary nào.
- Stable, single-impl dependency (vd: `math` module — không ai abstract `math.sin`).
- Script throwaway, prototype.
- Tách abstraction trên trục sai → wrong abstraction (Sandi Metz). Inline lại nếu chưa rõ axis.
- DI container 5 layer cho 1 use case — speculative gen.

> **Heuristic**: hỏi "code này có ranh giới infrastructure / business / I/O không?" — nếu CÓ, đặt DIP ở ranh giới. Nếu KHÔNG (mọi thứ là pure logic), DIP không kích hoạt.

---

## MỨC 2 — ALGORITHM / CẤU TRÚC

### 2.1. Vai diễn

```
Package layout DIP-compliant:

app/
├── domain/                    ← high-level (business)
│   ├── models.py              (Entity: Submission, ScoreResult)
│   ├── ports.py               ← ABSTRACTIONS sống ở đây (ISubmissionRepo, INotifier)
│   └── use_cases.py           (QuizSubmissionService — IMPORT TỪ ports.py only)
├── infrastructure/            ← low-level (technical)
│   ├── sqlite_repo.py         (impl ISubmissionRepo — IMPORT domain.ports)
│   ├── postgres_repo.py       (impl ISubmissionRepo)
│   ├── email_notifier.py      (impl INotifier)
│   └── memory_repo.py         (in-memory fake cho test)
└── main.py                    ← composition root (wire concrete vào abstract)


Source-code import direction:
  domain.use_cases   ──imports──▶  domain.ports
  infra.sqlite_repo  ──imports──▶  domain.ports   ← inverted (low-level depend on high-level abstraction)
  infra.email_notifier ──imports──▶  domain.ports
  main               ──imports──▶  domain.use_cases + infra.*  (wiring layer only)
```

**Quan trọng**: `domain/` package KHÔNG có dòng `from infrastructure import ...`. Bạn `rm -rf infrastructure/`, `domain/` vẫn import được, vẫn unit test được với fake/mock.

### 2.2. Recipe 5 bước áp DIP

```
INPUT: một use case (high-level) đang phụ thuộc concrete infrastructure (low-level)

step 1: nhận diện cross-boundary points
        - Mỗi điểm use case touch I/O (DB, HTTP, file, queue, time, random) là 1 boundary

step 2: cho mỗi boundary, định nghĩa narrow Protocol/abstract base
        - Đặt trong package high-level (domain/ports.py)
        - Tên theo "what use case needs", không theo "what infra provides"
        - VD: ISubmissionRepository (domain ngôn ngữ), không SQLiteWrapper

step 3: use case chỉ import abstraction
        - Constructor accept abstraction (DI)
        - Method gọi qua abstraction

step 4: infrastructure adapter implement abstraction
        - File trong infra/ package, import abstraction từ domain/
        - Concrete logic (SQL, HTTP call) sống ở đây

step 5: composition root (main.py / entrypoint)
        - Khởi tạo concrete (SQLiteRepo, EmailNotifier, ...)
        - Inject vào use case constructor
        - Đây là điểm DUY NHẤT thấy cả 2 layer

step 6: test
        - Unit test use case với fake (InMemoryRepo, FakeNotifier) — pure, fast
        - Integration test riêng cho concrete adapter (test SQLiteRepo với SQLite thật)
```

### 2.3. Invariants sau refactor DIP

1. **Source-code direction**: high-level *không* `import` low-level. Đo bằng grep `from infrastructure` trong `domain/` — phải = 0.
2. **Abstraction sống ở high-level package**, không ở infra.
3. **Composition root** là *điểm duy nhất* biết cả 2 layer.
4. **Use case unit test**: chỉ pure objects + fake, < 50 ms. Không có tempfile, không SQLite, không HTTP.
5. **Swap infrastructure**: thêm Postgres adapter chỉ cần thêm file mới, 0 sửa use case (cầu OCP).

### 2.4. Anti-patterns hay xảy ra cùng DIP

| Anti-pattern | Triệu chứng | Cách tránh |
|--------------|-------------|------------|
| **Service Locator pattern** | Use case gọi `Locator.get(SqliteRepo)` → vẫn biết về concrete | Inject qua constructor explicit |
| **Concrete inject** | Inject `SqliteRepo` thay vì `ISubmissionRepository` | Type-hint abstraction |
| **Abstraction in wrong package** | `ISubmissionRepository` ở `infrastructure/abstract.py` → low-level "share" abstraction | Move to `domain/ports.py` |
| **Leaky abstraction** | Method abstract chứa SQL detail (vd: `def find_by_query(sql_str)`) | Abstract theo domain language: `def find_by_user(user_id)` |
| **God interface** | Abstract base 20 method (vi phạm ISP) | Tách theo client view — DIP + ISP đi đôi |
| **DI container abuse** | Magic decorator, hard-to-debug wiring | Manual constructor wiring trong `main.py` đủ rõ |

### 2.5. Đo bằng metric cụ thể

| Metric | DIP good | DIP bad |
|--------|----------|---------|
| `grep -r "from infrastructure" domain/` | 0 | > 0 |
| Time chạy unit test use case | < 50 ms | > 1s (vì I/O) |
| Số file phải sửa khi đổi DB | 1-2 (adapter mới + composition) | nhiều |
| Số adapter cùng impl 1 abstraction | ≥ 2 (sqlite + memory + ...) | 1 (probably no DIP needed) |
| Composition root size | tập trung 1 file | rải khắp |

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode — refactor recipe áp lên Ellumm

```
Bắt đầu: lesson 24 đã có QuizSubmissionService với SubmissionRepository concrete
         (SQLite hard-coded). Service IMPORT trực tiếp infrastructure.

Bước 1 - tách package:
    domain/ports.py:       ISubmissionRepository, INotifier
    domain/use_cases.py:   QuizSubmissionService (import từ ports only)
    infra/sqlite_repo.py:  SqliteSubmissionRepository (impl ISubmissionRepository)
    infra/memory_repo.py:  InMemorySubmissionRepository (fake cho test)
    infra/email_notifier.py: EmailNotifier
    infra/log_notifier.py: LogNotifier (fake)
    main.py:               wire concrete vào abstract

Bước 2 - định nghĩa abstraction theo domain language:
    class ISubmissionRepository(Protocol):
        def save(self, sub: Submission) -> None: ...
        def find_by_user(self, user_id: str) -> List[Submission]: ...
    
    KHÔNG: def execute_sql(query: str) → đó là leaky

Bước 3 - service pure:
    class QuizSubmissionService:
        def __init__(self, repo: ISubmissionRepository, notifier: INotifier):
            self.repo = repo
            self.notifier = notifier
        
        def submit(self, user_id, answers):
            ...
            self.repo.save(submission)
            self.notifier.notify(user_id, result)

Bước 4 - test:
    fake_repo = InMemorySubmissionRepository()
    fake_notifier = LogNotifier()
    service = QuizSubmissionService(fake_repo, fake_notifier)
    service.submit("alice", {...})
    assert len(fake_repo.saved) == 1   # < 10 ms, no I/O

Bước 5 - swap infra:
    main.py:
        # production
        service = QuizSubmissionService(SqliteSubmissionRepository("prod.db"),
                                         EmailNotifier(smtp_config))
        
        # development / sensory substitution
        service = QuizSubmissionService(InMemorySubmissionRepository(),
                                         LogNotifier())
        
        # giai đoạn migrate sang Postgres
        service = QuizSubmissionService(PostgresSubmissionRepository(pg_config),
                                         EmailNotifier(smtp_config))
        
    QuizSubmissionService - 0 sửa qua mọi config trên.
```

### 3.2. Python — file `28_dip.py`

Cấu trúc trong `28_dip.py`:

1. **PART A — Without DIP**: `BadQuizService` import `sqlite3` trực tiếp. Test phải tạo tempfile DB.
2. **PART B — With DIP**:
   - Domain layer: `ISubmissionRepository`, `INotifier` Protocol.
   - Use case: `QuizSubmissionService` chỉ depend Protocol.
   - Infrastructure: `SqliteSubmissionRepository`, `InMemorySubmissionRepository`, `EmailNotifier`, `LogNotifier`.
3. **PART C — Composition root** demo wiring ba config: production (SQLite + Email), dev (Memory + Log), test (fake).
4. **PART D — Demos**:
   - Demo 1: Without-DIP test cần tempfile, slow.
   - Demo 2: With-DIP test pure in-memory, fast.
   - Demo 3: Swap SqliteRepo → PostgresRepo (giả lập) → MemoryRepo — service code unchanged.
   - Demo 4: Sensory substitution analogy — same service, swap "sensor" (repo).
   - Demo 5: Source-code import graph: `grep` show `domain.use_cases` không import `infrastructure`.

Chạy:
```bash
python 28_dip.py
```

---

## 5 CHIỀU — BẢNG SO SÁNH IN NÃO VS IN CODE

| Chiều | Não (thalamus + sensory substitution) | Code (DIP) |
|-------|----------------------------------------|------------|
| **Cấu tạo** | LGN/MGN/VPL = adapter layer; cortex = consumer; periphery = provider | Abstraction (Protocol) ở domain package; adapter ở infrastructure; use case = consumer |
| **Vị trí** | Thalamus là *single hub* giữa periphery và cortex; abstraction nằm gần consumer | Abstraction trong domain/ports.py (cùng package use case); adapter trong infrastructure/ |
| **Chức năng** | Convert raw sensor signal → spike train pattern cortex expect | Convert concrete I/O (SQL, HTTP) → method call abstract use case expect |
| **Kết nối** | Cortex KHÔNG nói chuyện trực tiếp periphery. Periphery → thalamus → cortex (1-way) | High-level KHÔNG import low-level. Source-code direction: low-level → abstraction ← high-level |
| **Ý nghĩa** | Sensor swappable (cochlear implant, BrainPort) — cortex stays same | Infrastructure swappable (SQLite → Postgres → Mongo) — use case stays same |

---

## 3 LOẠI VÍ DỤ TRONG CODE

### Ví dụ 1 — Vận hành thường (DIP-compliant)

```python
# domain/ports.py
class ISubmissionRepository(Protocol):
    def save(self, sub: Submission) -> None: ...
    def find_by_user(self, user_id: str) -> List[Submission]: ...

# domain/use_cases.py
from domain.ports import ISubmissionRepository, INotifier

class QuizSubmissionService:
    def __init__(self, repo: ISubmissionRepository, notifier: INotifier):
        self.repo = repo
        self.notifier = notifier
    
    def submit(self, user_id, answers):
        ...
        self.repo.save(submission)
        self.notifier.notify(user_id, result)

# infrastructure/sqlite_repo.py
from domain.ports import ISubmissionRepository  # ← infra depends on domain

class SqliteSubmissionRepository:
    def save(self, sub): ...  # SQL implementation
    def find_by_user(self, user_id): ...

# main.py (composition root)
service = QuizSubmissionService(
    repo=SqliteSubmissionRepository("prod.db"),
    notifier=EmailNotifier(smtp_config),
)
```

→ `domain/use_cases.py` không có `from infrastructure import ...`. Pure business logic.

### Ví dụ 2 — Hỏng/thiếu (vi phạm DIP)

```python
# bad: high-level import low-level concrete
import sqlite3
import smtplib

class BadQuizService:
    def __init__(self, db_path: str, smtp_host: str):
        self.conn = sqlite3.connect(db_path)
        self.smtp = smtplib.SMTP(smtp_host)
    
    def submit(self, user_id, answers):
        ...
        self.conn.execute("INSERT INTO submissions ...")
        self.smtp.sendmail(...)
```

Hậu quả:
- Test unit `BadQuizService.submit()` → phải tempfile DB, mock SMTP server. Test 30 dòng setUp.
- Đổi sang Postgres → mở `BadQuizService`, sửa SQL syntax (`%s` thay `?`, đổi connection lib).
- Đổi sang SES (AWS) → sửa import `smtplib` → `boto3`.
- Mỗi vendor migration → diff toàn bộ business logic.

### Ví dụ 3 — Ứng dụng Ellumm

| Yêu cầu | Without DIP | With DIP |
|---------|-------------|----------|
| Unit test `submit()` | Tempfile DB + mock SMTP, 30 dòng setUp, < 5/s | Pure fake, 5 dòng setUp, > 1000/s |
| Migrate SQLite → Postgres | Sửa `BadQuizService` (~50 dòng) | Thêm `PostgresSubmissionRepository`, đổi 1 dòng `main.py` |
| Add Mongo cho document quizzes | Refactor `BadQuizService` huge | Thêm `MongoSubmissionRepository` |
| Local development không có DB thật | Đắp DB local (docker, etc.) | Inject `InMemorySubmissionRepository` |
| Disaster recovery: dump submission queue | Phải hiểu SQL của `BadQuizService` | `BackupRepository` impl interface, log to JSON |
| Mobile SDK: stub server | Mock cả `BadQuizService` | Thay repo impl, business logic giữ |

---

## SO SÁNH PATTERN LÂN CẬN

| Pattern / Principle | Đặc điểm | Quan hệ với DIP |
|---------------------|----------|-----------------|
| **SRP** (Lesson 24) | 1 class = 1 actor | DIP cần SRP: nếu class đa actor, abstraction sẽ bị "fat" trộn nhiều trục |
| **OCP** (Lesson 25) | Mở extension, đóng modification | DIP bạn có abstraction → extension mới = adapter mới = OCP đạt |
| **LSP** (Lesson 26) | Subclass giữ contract | Mỗi adapter LSP-compliant với abstraction; không, caller phải `isinstance` |
| **ISP** (Lesson 27) | Interface narrow per client view | DIP + ISP: abstraction phải narrow đúng client (use case) |
| **Hexagonal Architecture** (Lesson 30) | Ports & Adapters | **Hexagonal là DIP áp dụng systematic**: port = abstraction; adapter = concrete |
| **Clean Architecture** (Lesson 29) | Concentric layers, dependency rule | **Dependency rule** = DIP scaled lên cả hệ: outer → inner only, never reverse |
| **Service Locator** (anti) | Component lookup global registry | Vi phạm DIP: component vẫn biết "có Locator"; thay constructor inject |
| **Dependency Injection** (technique) | Inject dependency qua constructor / setter | DI là *kỹ thuật* impl DIP. DIP là *nguyên tắc direction* |

**Vai trò trong SOLID**: DIP là cột trụ thứ 5 (cuối). Bốn cột trước (S/O/L/I) định hình *micro-design* (class, interface). DIP định hình *macro-architecture* (package, layer). Đây là cây cầu sang Clean Architecture (lesson 29) và Hexagonal (lesson 30) — cả hai đều là *systematic application của DIP*.

---

## TRADE-OFFS

| Trade-off | Chi phí | Lợi ích |
|-----------|---------|---------|
| Tách package domain/infra | File count, navigation overhead | Decouple business / infrastructure |
| Abstraction layer | 1 file Protocol per boundary | Test pure, swap infra dễ |
| Composition root file dài | Wiring 10+ adapter ở `main.py` | Tập trung, dễ refactor |
| DI container | Magic, debug khó | Auto-wire (đôi khi cần khi 100+ class) |
| Naming overhead | `IRepo`, `IService` prefix lan tràn | (Trade-off: tránh "I" prefix nếu Python convention dùng plain `Repo`) |
| Wrong abstraction risk | Refactor abstraction painful | Chờ rule of 3 (≥ 2 adapter) trước khi extract |

**Quy tắc**: chấp nhận overhead khi có boundary rõ giữa business / infrastructure, codebase ≥ 1000 dòng, > 1 dev. Với script throwaway, DIP overkill.

---

## CHECKLIST TRƯỚC KHI MERGE PR

- [ ] **Source-code direction**: `domain/` package có `import infrastructure` không? Phải = 0.
- [ ] **Abstraction location**: interface ở `domain/ports.py` (high-level) hay `infrastructure/contracts.py`?
- [ ] **Use case unit test**: chạy < 50 ms? Không tempfile, không network, không SQLite?
- [ ] **Type hint**: use case nhận `ISubmissionRepository` hay `SqliteSubmissionRepository`?
- [ ] **Abstraction language**: method name theo domain (`save_submission`, `find_by_user`) hay theo infra (`execute_query`)?
- [ ] **Adapter ≥ 2**: có ít nhất 1 production impl + 1 fake/in-memory? Nếu chỉ 1, DIP có thể chưa cần (nhưng thường nên có fake cho test).
- [ ] **Composition root**: `main.py` (hoặc bootstrap.py) là *điểm duy nhất* import cả `domain` lẫn `infrastructure`?
- [ ] **Naming**: `IRepository` vs `Repository` — chọn convention và stick với nó.
- [ ] **Leaky abstraction**: method abstract có expose SQL/HTTP detail không? Nếu có, refactor lên ngôn ngữ domain.
- [ ] **Cyclic import**: domain ports được infra import; ports không import infra. Verify với linter (eg. `import-linter`).

---

## BÀI TẬP 4 MỨC

### Mức 1 — Cơ bản

Mở `28_dip.py`. So sánh `BadQuizService` và `QuizSubmissionService`:
- List import statements của mỗi class.
- Đếm dòng setUp test cho mỗi class.
- Vẽ source-code dependency graph (mũi tên import) cho từng version.

### Mức 2 — Trung bình

Yêu cầu mới: cache submission gần nhất trong Redis cho 5 phút (performance).

Hướng 1 — vi phạm DIP: thêm `import redis` vào use case, `self.redis.set(...)` trực tiếp.

Hướng 2 — DIP-compliant: thêm `ICache` Protocol; `RedisCache` adapter; inject vào use case.

Implement hướng 2. Đo:
- Số file thêm.
- Số file sửa (target: 0 trừ composition root).
- Test pure: `InMemoryCache` fake để test use case không cần Redis.

### Mức 3 — Khó (architect-level)

Tình huống: domain logic cần *current time* để timestamp submission. Lựa chọn:

1. Use case gọi `datetime.now()` trực tiếp. Vi phạm DIP? Tại sao test khó?
2. Inject `IClock` Protocol → `RealClock` (production), `FakeClock` (test, có thể `set_now()`).
3. Pass `now` làm parameter mỗi method (functional style).

Phân tích trade-off mỗi cách. Implement hướng 2 trong code lesson. Test: với `FakeClock(now=datetime(2026, 5, 6))`, submission timestamp đúng deterministic.

### Mức 4 — Mở rộng neuroscience

Câu hỏi mở:
1. **Olfactory cortex bypass thalamus** — thiết kế "anti-DIP" này có *tradeoff* gì? (Hint: latency cực thấp — smell phản ứng nhanh nhất.) Liên hệ với code: khi nào *vi phạm DIP intentionally* để giảm latency / overhead?
2. **Cochlear implant resolution thấp** (12-22 channel vs ~3500 hair cell ở cochlea bình thường): tại sao vẫn work? Liên hệ với "compressed abstraction" — interface đơn giản hơn impl thực tế (lossy, nhưng đủ thông tin).
3. **V1 plasticity** sau lesion: nếu một phần V1 bị tổn thương, vùng kế cận remap để xử lý input. Đây có phải là phiên bản "swap impl behind abstraction" không? Liên hệ với "graceful degradation" trong DIP-compliant system.

Trả lời 4–6 câu mỗi mục.

---

## SAU LESSON NÀY — KẾT THÚC SOLID

5 nguyên tắc SOLID đã đủ tay:

- **SRP** — class = 1 actor (functional specialization V1/MT/Broca)
- **OCP** — open/closed (synaptic plasticity, pattern separation)
- **LSP** — subclass giữ contract (Hodgkin-Huxley universal AP)
- **ISP** — interface narrow per client (receptor specificity AMPA/GABA-A)
- **DIP** — high-level định nghĩa abstraction (thalamus relay)

Quan hệ:
- **SRP + DIP** là 2 cột trụ chính. Khoảng 70% giá trị architecture đến từ chúng.
- **OCP** là *kết quả* của 4 nguyên tắc kia áp dụng đúng.
- **LSP + ISP** tinh chỉnh, đảm bảo abstraction usable.

Tiếp theo — Phần B (Architectural Styles):

**Lesson 29 — Clean Architecture**: SOLID scaled lên *toàn hệ thống*. 4 vòng tròn đồng tâm (Entities, Use Cases, Interface Adapters, Frameworks); dependency rule one-way. Đây là *DIP applied systematically*. Neuroscience analogy: brainstem (entities) ← cortex (use cases) ← thalamus (interface adapters) ← muscles/sensors (frameworks).

> **Nhớ một câu**: DIP không phải "dùng interface". DIP là "**high-level định nghĩa interface; low-level đến để thực hiện** — source-code dependency direction *đảo ngược* runtime call direction".
