# Lesson 27 — ISP (Interface Segregation Principle)
## Receptor Specificity — Mỗi receptor chỉ "nghe" một ligand. Không có "god receptor"

---

## TÓM TẮT MỘT DÒNG

**ISP** = clients không bị ép phụ thuộc vào method họ không dùng. Thay vì 1 interface to với 12 method, tạo **nhiều interface hẹp** đặc thù theo *góc nhìn của từng client*.

> Postsynaptic membrane của một neuron có nhiều loại receptor đặt cạnh nhau — **AMPA** chỉ nghe glutamate (excitation nhanh), **GABA-A** chỉ nghe GABA (inhibition nhanh), **NMDA** nghe glutamate + glycine + voltage trigger, **D1/D2** chỉ nghe dopamine, **mu-opioid** chỉ nghe opioid peptide. Tại sao não tách thế này? Vì một "god receptor" nghe mọi ligand sẽ làm: (a) mất khả năng phân biệt excitation vs inhibition, (b) mọi neurotransmitter cùng tác động → noise, (c) không thể tinh chỉnh selectively. Mỗi receptor là một **role interface hẹp** — neuron chọn lắp receptor nào tại synapse nào tuỳ chức năng. ISP là receptor specificity phiên bản code.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Khi một interface to dần lên (mỗi sprint thêm 1 method theo yêu cầu mới của 1 client), nó bắt mọi implementation phải support tất cả method — kể cả những method client kia không dùng:

```python
class IQuizPlatform(ABC):
    @abstractmethod
    def score(self, answers): ...
    @abstractmethod
    def save_submission(self, sub): ...
    @abstractmethod
    def send_email(self, user, msg): ...
    @abstractmethod
    def update_leaderboard(self, user, score): ...
    @abstractmethod
    def render_pdf_report(self, sub): ...    # client A chỉ cần cái này
    @abstractmethod
    def export_to_csv(self, subs): ...
    @abstractmethod
    def audit_log(self, event): ...
    @abstractmethod
    def schedule_reminder(self, user, when): ...
    @abstractmethod
    def calculate_certificate(self, user): ...
    # ... 4 method nữa
```

3 hậu quả thực tế:

1. **Refused bequest** — subclass đơn giản (chỉ làm scoring) buộc impl 12 method, 11 cái `raise NotImplementedError`. Smell rõ.
2. **Mock test phình** — viết test cho `ScoreCalculatorClient` (chỉ dùng `score()`) phải mock 12 method để dựng `IQuizPlatform`. Test 1 dòng business logic dùng 30 dòng setup.
3. **Recompile / redeploy chéo** — sửa interface (thêm method 13) buộc mọi impl + mọi client *recompile* (Java/C++) hoặc *redeploy* (microservice schema). Đây là vấn đề gốc Bob Martin gặp ở Xerox 1990s — Print client phải rebuild khi Fax client thêm method.

ISP nói: **interface là *góc nhìn của client*, không phải catalog method của implementation**. Tách interface theo client view.

### 1.2. Định nghĩa

**Robert C. Martin 1996** (*The Interface Segregation Principle*):
> *"Clients should not be forced to depend on methods they do not use."*

**Diễn dịch hành động**:
> *"No code should be forced to depend on methods it does not use. ISP splits interfaces that are very large into smaller and more specific ones so that clients will only have to know about the methods that are of interest to them."*

Cốt lõi: interface phải hẹp + role-specific + định nghĩa theo *consumer*, không theo *producer*.

### 1.3. ISP vs SRP — phân biệt

| | SRP (Lesson 24) | ISP (Lesson 27) |
|---|------|------|
| Đối tượng | **Class** | **Interface** |
| Câu hỏi | "Class này phục vụ bao nhiêu actor?" | "Interface này có bao nhiêu client view khác nhau?" |
| Vi phạm | God class (5+ actor cùng kéo) | Fat interface (10+ method, mỗi client dùng 2-3) |
| Khác biệt | Một class có thể impl nhiều ISP-narrow interface mà vẫn chỉ phục vụ 1 SRP-actor | Một interface có thể bị nhiều SRP-actor cùng dùng nếu interface đúng role |

> **Quy tắc**: SRP phân chia ai *sở hữu* code. ISP phân chia ai *gọi* code. Hai trục độc lập, có thể vi phạm cái này mà tuân cái kia.

### 1.4. Neuroscience analogy — Receptor specificity

#### Mỗi receptor là một role interface hẹp

Tế bào thần kinh có nhiều loại receptor protein nằm trên màng sau synapse, mỗi cái chỉ "nhận" 1 loại ligand cụ thể:

| Receptor | Ligand | Cơ chế | Hệ quả |
|----------|--------|--------|--------|
| **AMPA** | Glutamate | Ionotropic, mở Na⁺/K⁺ channel | Excitation nhanh (~1 ms) |
| **NMDA** | Glutamate + glycine + post-depolarization | Ionotropic + voltage-gated, Ca²⁺ permeable | Hebbian coincidence detection, LTP induction |
| **GABA-A** | GABA | Ionotropic, mở Cl⁻ channel | Inhibition nhanh (~10 ms) |
| **GABA-B** | GABA | Metabotropic (G-protein) | Inhibition chậm, kéo dài (~100 ms) |
| **nAChR** | Acetylcholine | Ionotropic, Na⁺ | Excitation, neuromuscular junction |
| **mAChR (M1-M5)** | Acetylcholine | Metabotropic | Modulation, parasympathetic |
| **D1/D2** | Dopamine | Metabotropic | D1 excite, D2 inhibit (cùng ligand, khác receptor) |
| **5-HT (14 subtype)** | Serotonin | Cả ionotropic và metabotropic | Mood, sleep, GI |
| **mu/delta/kappa opioid** | Opioid peptide / morphine | Metabotropic | Pain modulation |

Bằng chứng đặc thù:
- **Naloxone** chỉ block opioid receptor (mu/delta/kappa); không ảnh hưởng glutamate, GABA, dopamine. Đó là "single role interface" của thuốc ngủ.
- **Bicuculline** chỉ block GABA-A; không block GABA-B (cùng GABA, khác receptor) → seizure (vì GABA-A là chủ lực inhibition cortex).
- **Dopamine và 2 receptor đối lập**: D1 (Gs, kích thích cAMP) vs D2 (Gi, ức chế cAMP) — cùng ligand, hai role interface ngược nhau ở striatum (direct vs indirect pathway, hệ thống basal ganglia chuyển động).

#### Tại sao không "god receptor"?

Hãy thử một thiết kế "fat receptor": một protein nhận tất cả glutamate + GABA + dopamine + serotonin + ACh, mỗi ligand mở channel khác nhau. Bốn vấn đề ngay:

1. **Selectivity collapse** — neuron không phân biệt được excitation (glutamate) vs inhibition (GABA). Tổng hợp = noise.
2. **Modulation collapse** — không thể "block GABA-A để làm gì đó" mà không đụng glutamate.
3. **Spatial organization** — một synapse chỉ cần 1-2 ligand; "fat receptor" phí năng lượng và protein.
4. **Evolution lock-in** — đột biến 1 vùng receptor sẽ ảnh hưởng mọi ligand → tăng tỷ lệ sai chết.

Không tồn tại "god receptor" trong não vì những lý do này — đó là **bằng chứng tự nhiên rằng ISP work**.

#### Synesthesia — vi phạm ISP cấp não

Synesthesia là hiện tượng cross-wiring: một số người "thấy số ra màu" (V4 + nhân số bị nối nhầm), "nghe nhạc thấy hình". Khoảng 4% dân số có synesthesia ở mức nhẹ. Đây là một loại "fat interface" sinh học: input modality A vô tình kích hoạt cả pathway B.

Hệ quả:
- Đa số synesthete không thấy bệnh (consistent across life), nhưng có người overload — too much sensory mixing.
- Cá nhân synesthete khó tách bạch một stimulus → cognitive load tăng.

Tương tự code: nếu interface "fat", một client thay đổi input có thể vô ý kích hoạt logic của client khác.

#### Co-localization — nhiều receptor ở cùng một synapse là OK

Postsynaptic neuron thường có **AMPA + NMDA cùng synapse** (co-localized). Nhưng đây không phải "god receptor" — đó là 2 role interface độc lập ngồi cạnh nhau. AMPA fast excite; NMDA giữ vai Hebbian detection. Code analogy: 1 class impl *nhiều narrow Protocol* (AMPA + NMDA) — cả 2 interface hẹp, không gộp thành 1 interface to.

#### 5 chiều của analogy

| Chiều | Trong não (receptor specificity) | Trong code (ISP) |
|-------|-----------------------------------|-------------------|
| **Cấu tạo** | Mỗi receptor là 1 protein cụ thể (subunit composition cố định, ligand-binding pocket đặc) | Mỗi interface là 1 Protocol/abstract class với method set hẹp |
| **Vị trí** | Receptor đặt tại synapse cụ thể; co-localization OK (nhiều receptor cạnh nhau) | Interface declared ở module riêng; class implement nhiều interface OK |
| **Chức năng** | Mỗi receptor = 1 role chuyên biệt (fast excite / slow inhibit / Ca²⁺ gate / modulation) | Mỗi interface = 1 client view chuyên biệt |
| **Kết nối** | Ligand → receptor đặc hiệu; ligand sai không "lừa" receptor | Caller → narrow interface; caller không biết về method ngoài interface |
| **Ý nghĩa** | Selectivity, modular tuning, evolution flexibility | Test isolation, decouple recompile, parallel team work |

### 1.5. Khi nào DÙNG ISP nghiêm

- Interface có ≥ 7-8 method và *các nhóm method khác nhau* được dùng bởi *các client khác nhau*.
- Một implementation đang `raise NotImplementedError` cho method nào đó (refused bequest = smell rõ).
- Mock setup dài 30+ dòng để test 1 dòng logic (chỉ dùng 1-2 method).
- Microservice / library public API: client bên ngoài có thể chỉ cần 1 phần.
- Công ty có nhiều team, mỗi team consume interface khác → tách interface theo team boundary.

### 1.6. Khi nào KHÔNG dùng (over-ISP)

- Interface 2-3 method, 1 client → không cần tách.
- Tách quá nhỏ → mỗi method 1 interface → phình file, navigation nhặng.
- Internal class, không expose qua boundary, 1 caller duy nhất.
- Khi tách nhân tạo: 2 method *thực sự* phục vụ cùng client view, đừng tách.

> **Heuristic**: hãy hỏi "có client nào cần 70-80% method của interface này không?" — nếu *mọi client* đều dùng phần lớn method, interface đúng kích thước. Nếu mỗi client chỉ dùng 30%, đó là fat interface — tách.

---

## MỨC 2 — ALGORITHM / CẤU TRÚC

### 2.1. Vai diễn

```
Trước (vi phạm ISP):

  ScoreClient ──┐
  NotifyClient ─┤   ┌─────────────────────┐
  ExportClient ─┼──▶│  IQuizPlatform      │  ← 12 method, fat
  AuditClient ──┤   │  ─────────────────  │
  ...           │   │  score()            │
                │   │  save()             │
                │   │  notify()           │
                │   │  rank()             │
                │   │  render_pdf()       │
                │   │  export_csv()       │
                │   │  audit_log()        │
                │   │  schedule()         │
                │   │  ...                │
                │   └─────────────────────┘
                │            ↑
                │   ┌────────┴───────┐
                │   │ FatQuizPlatform │  ← phải impl 12, kể cả method client không cần
                │   └─────────────────┘
                │
  Mỗi client phụ thuộc TẤT CẢ 12 method (do interface)
  → recompile chéo, mock phình, refused bequest

Sau (ISP-compliant):

  ScoreClient   ──▶  IScorable     (1 method)
  NotifyClient  ──▶  INotifiable   (1 method)
  ExportClient  ──▶  IExportable   (1 method)
  AuditClient   ──▶  IAuditable    (1 method)
                          ↑↑↑↑
                  ┌───────┴────────────┐
                  │  QuizService impl  │  ← 1 class, impl nhiều narrow interface
                  │  Scorable, Notifi- │
                  │  able, Exportable, │
                  │  Auditable         │
                  └────────────────────┘

  Mỗi client phụ thuộc duy nhất method nó cần
  → recompile cô lập, mock 1-2 method, không refused bequest
```

### 2.2. Recipe 6 bước

```
INPUT:  một interface to có ≥ 7 method được nhiều client dùng

step 1: liệt kê các client (caller) hiện có của interface
        - Với mỗi client, ghi method nào nó thật sự gọi

step 2: nhóm method theo "client view"
        - Method được nhóm client X dùng cùng nhau → 1 interface mới
        - Có thể overlap nhỏ (cùng method ở 2 interface OK nếu thật cần)

step 3: đặt tên role-based cho mỗi interface mới
        - Tên theo "ai gọi và gọi để làm gì"
        - VD: IScorable, INotifiable, IRenderable
        - TRÁNH tên implementation-based: IQuizPlatformPart1, IQuizPlatformPart2

step 4: định nghĩa narrow interface (Python: Protocol class hoặc abstract base)

step 5: implementation class thường impl nhiều narrow interface
        - Không cần tách class - chỉ cần class declare implement N protocol

step 6: client refactor:
        - Đổi type hint từ IQuizPlatform → INarrowInterface
        - Test mock chỉ stub method liên quan

step 7: dọn fat interface cũ
        - Có thể giữ làm composite interface for backward compat
        - Hoặc xoá hẳn nếu không client nào cần
```

### 2.3. Invariants sau refactor ISP

1. **Không có `raise NotImplementedError`** trong code chính (chỉ OK trong abstract base hoặc default test impl).
2. **Mỗi client type-hint một narrow interface duy nhất** — không hint cả fat interface "for safety".
3. **Mock setup**: viết test cho client X chỉ stub method client X gọi — đo bằng số dòng setUp.
4. **Recompile cô lập** (Java/C++): thêm method 13 vào fat interface không buộc Print client recompile.
5. **Implementation đa năng**: 1 class có thể `Scorable + Notifiable + Storable` — đó là tốt; không tách class theo interface (đó là ngược).

### 2.4. Python's superpower — Protocol + structural subtyping

Python từ 3.8 có `typing.Protocol` — interface không cần `register()` hay inheritance, kiểm tra ở mức *structural*:

```python
from typing import Protocol, runtime_checkable

class Scorable(Protocol):
    def score(self, answers: dict) -> ScoreResult: ...

class QuizService:
    """Không kế thừa Scorable. Chỉ cần có method score() đúng signature."""
    def score(self, answers): ...

def calculate(scorer: Scorable, answers):  # type checker chấp nhận QuizService
    return scorer.score(answers)
```

→ `QuizService` "structurally implements" `Scorable` mà không cần khai báo. Đây là *duck typing với type safety*. Bạn có thể có 100 protocol hẹp; `QuizService` chỉ cần "tự nhiên" có những method tương ứng.

`@runtime_checkable` cho phép `isinstance(qs, Scorable)` ở runtime — hữu ích khi cần introspect.

### 2.5. Anti-patterns hay xảy ra cùng ISP

| Anti-pattern | Triệu chứng | Cách tránh |
|--------------|-------------|------------|
| **Fat interface** | 12+ method, mỗi client dùng 30% | Tách theo client view |
| **Refused bequest** | Subclass `raise NotImplementedError` | Smell rõ — tách interface, đừng ép subclass |
| **Header bloat** (C++/Java) | `#include` interface dây chuyền recompile | Forward declaration + narrow header |
| **Test mock explosion** | 30 dòng mock cho 1 dòng logic | Type-hint narrow interface trong client |
| **Interface per method** | 50 interface, mỗi cái 1 method | Quá tay — gộp method cùng client view |
| **Marker interface bloat** | Interface trống chỉ để "đánh dấu" | Dùng metadata (decorator, attribute) thay |
| **God receptor (anti)** | Class to expose mọi capability | Tách theo role, dùng Protocol composition |

### 2.6. Đo bằng metric cụ thể

| Metric | ISP good | ISP bad |
|--------|----------|---------|
| Method per interface | 2-5 | 10+ |
| `% method được mỗi client gọi` | ≥ 60% | ≤ 30% |
| Số `NotImplementedError` raise | 0 | 3+ |
| Số dòng mock cho 1 client test | < 10 | 30+ |
| Recompile graph: thêm method ảnh hưởng bao nhiêu client | 1 (chỉ client của method đó) | tất cả client của fat interface |

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode — recipe áp lên Ellumm

```
Bắt đầu: từ lesson 26, có QuizScorer (Protocol hẹp đã rồi - 1 method).
         Nhưng giả sử team mở rộng tạo IQuizPlatform "tổng hợp":

class IQuizPlatform:
    # methods needed by ScoreClient
    score(answers) -> ScoreResult
    
    # methods needed by SubmissionStore
    save_submission(user, sub)
    get_submission(sub_id)
    
    # methods needed by NotificationService
    send_email(user, msg)
    send_push(user, msg)
    
    # methods needed by LeaderboardClient
    update_rank(user, score)
    get_rank(user)
    
    # methods needed by ReportingClient
    render_pdf(sub)
    export_csv(subs)
    
    # methods needed by AuditClient
    audit_log(event)

→ FatQuizPlatform impl all 10. ScoreClient depend trên cả 10.

Bước 1 - liệt kê client + method:
    ScoreCalculatorClient      → score()
    SubmissionPersistenceClient → save_submission, get_submission
    NotificationDispatchClient  → send_email, send_push
    LeaderboardDisplayClient    → update_rank, get_rank
    ReportingClient             → render_pdf, export_csv
    AuditClient                 → audit_log

Bước 2 - tạo 6 narrow Protocol:
    Scorable        - 1 method
    SubmissionStore - 2 method
    Notifier        - 2 method
    Rankable        - 2 method
    Renderable      - 2 method
    Auditable       - 1 method

Bước 3 - QuizService impl all 6 protocol:
    class QuizService:
        # 10 method, structural subtyping hết 6 protocol

Bước 4 - mỗi client type-hint narrow protocol:
    class ScoreCalculatorClient:
        def __init__(self, scorer: Scorable): ...
    class NotificationDispatchClient:
        def __init__(self, notifier: Notifier): ...
    ...

Bước 5 - test mock:
    # Trước: mock 10 method
    # Sau: ScoreClient test mock 1 method
```

### 3.2. Python — file `27_isp.py`

Cấu trúc trong `27_isp.py`:

1. **Domain types**: `ScoreResult`, `Submission`.
2. **PART A — Vi phạm ISP**: `IQuizPlatform` (abstract base) với 10 method; `FatQuizPlatform` impl đầy đủ; `ReadOnlyQuizPlatform` với 7 method `raise NotImplementedError` (refused bequest).
3. **4 client phụ thuộc fat interface**: `ScoreCalculatorClient`, `NotificationDispatchClient`, `LeaderboardClient`, `AuditClient` — mỗi cái dùng 1-2 method.
4. **Mock setup count**: viết test cho `ScoreCalculatorClient` với fat interface — đếm số method phải mock.
5. **PART B — ISP refactor**: 6 narrow `Protocol` class.
6. **`QuizService`** impl all 6 protocol qua duck typing (Python `runtime_checkable`).
7. **4 client refactor** type-hint narrow Protocol.
8. **Mock setup count**: test mới — đo giảm số method mock.
9. **Demo**:
   - Demo 1: Refused bequest fail (NotImplementedError leak).
   - Demo 2: Mock count comparison (fat vs narrow).
   - Demo 3: Recompile/redeploy graph: thêm method 11.
   - Demo 4: `runtime_checkable Protocol` + `isinstance` introspection.
   - Demo 5: Compose service từ multiple narrow Protocol.

Chạy:
```bash
python 27_isp.py
```

---

## 5 CHIỀU — BẢNG SO SÁNH IN NÃO VS IN CODE

| Chiều | Não (receptor specificity) | Code (ISP) |
|-------|----------------------------|------------|
| **Cấu tạo** | Mỗi receptor = 1 protein, ligand-binding pocket đặc. AMPA, GABA-A, D1, mu-opioid là 4 protein khác nhau | Mỗi interface = 1 Protocol/abstract class với method set hẹp. Scorable, Notifiable, Storable là 3 interface khác nhau |
| **Vị trí** | Receptor đặt ở synapse cụ thể. Co-localization (nhiều receptor cạnh nhau ở cùng synapse) là chuẩn mực | Interface declared ở module riêng. Class implementing nhiều interface (composition) là chuẩn mực |
| **Chức năng** | Mỗi receptor = 1 role: fast excite / slow inhibit / modulation / etc. | Mỗi interface = 1 client view: scoring, notifying, exporting, auditing |
| **Kết nối** | Ligand → receptor specific. Glutamate không lừa được GABA-A. | Caller → narrow interface specific. Client không "thấy" method ngoài interface |
| **Ý nghĩa** | Selectivity (block 1 không phá khác), modular tuning, evolution flexibility | Test isolation, decouple recompile/redeploy, parallel team work |

---

## 3 LOẠI VÍ DỤ TRONG CODE

### Ví dụ 1 — Vận hành thường (ISP-compliant)

```python
class Scorable(Protocol):
    def score(self, answers: dict) -> ScoreResult: ...

class Notifier(Protocol):
    def send_email(self, user: str, msg: str) -> None: ...
    def send_push(self, user: str, msg: str) -> None: ...

class QuizService:
    """Implements both Scorable and Notifier (structural)."""
    def score(self, answers): ...
    def send_email(self, user, msg): ...
    def send_push(self, user, msg): ...

class ScoreCalculatorClient:
    def __init__(self, scorer: Scorable):  # ← chỉ thấy 1 method
        self.scorer = scorer
    def calculate(self, answers): return self.scorer.score(answers)

class NotificationDispatchClient:
    def __init__(self, notifier: Notifier):  # ← chỉ thấy 2 method
        ...
```

→ `QuizService` cùng instance pass cho cả 2 client. Mỗi client *type-safe see* interface hẹp.

### Ví dụ 2 — Hỏng/thiếu (vi phạm ISP)

```python
# Refused bequest
class ReadOnlyQuizPlatform(IQuizPlatform):
    def score(self, ...): return ScoreResult(...)
    def get_submission(self, ...): return self._cache[id]
    
    # 8 method còn lại - refused
    def save_submission(self, ...): raise NotImplementedError
    def send_email(self, ...): raise NotImplementedError
    def send_push(self, ...): raise NotImplementedError
    def update_rank(self, ...): raise NotImplementedError
    def render_pdf(self, ...): raise NotImplementedError
    def export_csv(self, ...): raise NotImplementedError
    def audit_log(self, ...): raise NotImplementedError
    def get_rank(self, ...): raise NotImplementedError
```

Hậu quả:
- Interface lừa caller — caller hợp đồng `IQuizPlatform.send_email()` works → instance lại raise.
- 8 dòng `NotImplementedError` boilerplate.
- Test mock cho `ReadOnlyQuizPlatform` phải stub 10 method.
- Refactor: tách interface → `ReadOnlyQuizPlatform` chỉ impl `Scorable + SubmissionLookup` (2 narrow), bỏ 8 NotImplementedError.

### Ví dụ 3 — Ứng dụng Ellumm

| Yêu cầu | Vi phạm ISP impl | ISP-compliant impl |
|---------|-------------------|---------------------|
| `ScoreCalculatorClient` chỉ cần score | Type-hint `IQuizPlatform` (10 method) | Type-hint `Scorable` (1 method) |
| Test cho `ScoreCalculatorClient` | Mock 10 method (Scorable + 9 NotImplementedError stub) | Mock 1 method |
| Sửa `IQuizPlatform.audit_log()` signature | Recompile cả 4 client | Chỉ recompile `AuditClient` |
| `ReadOnlyQuizPlatform` (chỉ scoring + lookup) | 8 method refused bequest | Implement chỉ 2 narrow Protocol, bỏ 8 stub |
| Thêm `BillingClient` mới | Phải biết về `IQuizPlatform` to | Định nghĩa `Billable` Protocol mới, `QuizService` thêm method `charge()` — `Scorable` không bị ảnh hưởng |
| Mobile team SDK | Phải distribute cả `IQuizPlatform` | Chỉ ship `Scorable + Notifier`, mobile không biết về `Renderable` (PDF), `Exportable` (CSV)... |

---

## SO SÁNH PATTERN LÂN CẬN

| Pattern / Principle | Đặc điểm | Quan hệ với ISP |
|---------------------|----------|-----------------|
| **SRP** (Lesson 24) | 1 class = 1 actor | Trục khác: SRP về class ownership; ISP về interface from caller view. Có thể vi phạm 1 mà giữ cái kia |
| **OCP** (Lesson 25) | Mở extension, đóng modification | Narrow interface dễ giữ OCP hơn — thêm capability = thêm Protocol mới + thêm method vào impl, không sửa caller |
| **LSP** (Lesson 26) | Subclass giữ contract | LSP áp lên *từng* narrow interface; tách interface giúp LSP dễ thoả vì contract hẹp hơn |
| **DIP** (Lesson 28) | Cấp cao phụ thuộc abstraction | DIP nói "có abstraction"; ISP nói "abstraction ấy phải hẹp đúng client" |
| **Adapter** (GoF) | Đối tượng adapt 1 interface ↔ interface khác | ISP refactor có thể dẫn đến Adapter nếu impl cũ là fat |
| **Facade** (GoF) | 1 class che N class phức tạp | Facade *gộp* nhiều system, ISP *tách* interface — phương ngược nhau |
| **Role-based access control** (security) | Mỗi role thấy capability khác | ISP áp dụng cho code vào hệ thống RBAC |
| **Refused Bequest** (anti) | Subclass raise NotImplementedError | Smell ISP rõ ràng |

**Vai trò trong SOLID**: ISP đảm bảo abstraction "đúng kích thước". OCP cần abstraction (extension point); DIP cần abstraction (depend); LSP cần abstraction có contract. ISP nói abstraction phải *hẹp đúng client*. Ba cái kia hoạt động tốt khi ISP đúng.

---

## TRADE-OFFS

| Trade-off | Chi phí | Lợi ích |
|-----------|---------|---------|
| Nhiều interface hẹp | File count↑, navigation overhead | Recompile cô lập, test ngắn |
| Class impl 5 protocol | Class declaration phình | Mỗi client thấy hẹp |
| Protocol structural (Python) | Type checker phải hỗ trợ (mypy/Pyright) | Không cần inheritance, duck typing safe |
| Tách quá nhỏ | Interface-per-method fragmenting | (Tránh: chờ rule of "client groups together") |
| Bảo trì interface stable | Phải versioning khi thêm method | Recompile graph nhỏ → versioning ít painful |

**Quy tắc**: chấp nhận overhead khi: (a) ≥ 3 client view khác nhau, (b) interface ≥ 7 method, (c) có recompile/redeploy boundary (microservice, public API, mobile SDK). Không đủ → bám flat interface.

---

## CHECKLIST TRƯỚC KHI MERGE PR

- [ ] **Đếm method**: interface > 8 method? Nếu có, có nhóm con method chỉ phục vụ 1 client?
- [ ] **Refused bequest**: có impl nào đang `raise NotImplementedError`? Đó là smell rõ ISP.
- [ ] **Mock setup dài**: test client X cần stub bao nhiêu method? > 5 = nghi vấn.
- [ ] **Type hint client**: client X type-hint cả interface to "for safety"? Hint narrow protocol thay.
- [ ] **Recompile graph**: thêm method N có buộc client K không liên quan recompile?
- [ ] **Naming**: interface tên theo *role/client view* hay theo *implementation*? `Scorable`/`Notifier` ✓; `IQuizPlatformPart3` ✗.
- [ ] **Cohesion**: các method trong narrow interface có thật sự gắn với 1 client view? Đừng nhồi nhét.
- [ ] **Duplicate method**: 2 narrow interface có method trùng tên? OK nếu *cùng signature, cùng contract*. Khác signature = vấn đề.
- [ ] **Composition**: implementation impl nhiều narrow interface cùng lúc — đó là tốt. Đừng tách class theo interface.
- [ ] **Public API**: nếu là library/microservice, cân nhắc *backward compat* — narrow protocol mới giữ lại fat interface alias để client cũ không vỡ.

---

## BÀI TẬP 4 MỨC

### Mức 1 — Cơ bản

Mở `27_isp.py`. Đọc `FatQuizPlatform`. Liệt kê:
- 10 method.
- 4 client (`ScoreCalculatorClient`, `NotificationDispatchClient`, `LeaderboardClient`, `AuditClient`).
- Map mỗi client → method nó dùng.
- Đếm % method mỗi client dùng / tổng method (target: ≤ 30% mỗi client = vi phạm ISP rõ).

### Mức 2 — Trung bình

`ReadOnlyQuizPlatform` đang `raise NotImplementedError` cho 7 method. Refactor:
1. Tạo Protocol `Scorable + SubmissionLookup` (2 narrow).
2. `ReadOnlyQuizPlatform` chỉ impl 2 narrow này, bỏ 7 stub.
3. Update caller: nếu có chỗ caller hint `IQuizPlatform`, đổi sang narrow protocol.

So sánh: số dòng code class trước/sau refactor; số method test mock trước/sau.

### Mức 3 — Khó (architect-level)

Thiết kế: **billing capability** mới cho `Ellumm Quiz Service`. Yêu cầu:
- `BillingClient` cần: `charge(user, amount)`, `refund(user, txn_id)`, `get_balance(user)`.
- Audit team cần: `audit_log(billing_event)` — đã có audit interface.
- Mobile team chỉ cần `get_balance(user)` — không cần charge/refund.

Thiết kế interface:
1. Tách thành mấy narrow Protocol? Tại sao?
2. `QuizService` impl những protocol nào? Có cần class mới không?
3. Vẽ recompile graph: nếu sau này thêm `subscribe(user, plan)` — ai bị ảnh hưởng?
4. Trade-off: vì sao không gộp `charge + refund + get_balance` thành 1 protocol `Billable`?

### Mức 4 — Mở rộng neuroscience

Câu hỏi mở:
1. Tại sao tiến hoá tạo ra cùng ligand (dopamine) nhưng 2 receptor đối lập (D1 stimulate cAMP, D2 inhibit cAMP)? Đây có phải "hai narrow interface trên cùng input channel" không? Liên hệ với code: cùng method name nhưng 2 interface khác behavior?
2. **Pleiotropic drugs** (thuốc đa receptor — vd. clozapine block cả D1, D2, D4, 5-HT2, 5-HT6, 5-HT7, H1, mAChR): tốt hay xấu? Liên hệ: API "convenience method" gọi 5 narrow interface cùng lúc — có vi phạm ISP không?
3. **Receptor downregulation** (sau khi expose ligand quá nhiều): receptor giảm density. Có analogy nào với code khi 1 narrow interface được dùng ở 50 chỗ — có dấu hiệu nó nên tách tiếp?

Trả lời 4–6 câu mỗi mục.

---

## SAU LESSON NÀY

ISP đảm bảo abstraction *đúng kích thước*. Nhưng còn câu hỏi nền tảng: **khi nào nên có abstraction, khi nào dùng concrete class trực tiếp?** Và quan trọng hơn: **ai sở hữu abstraction — module cấp cao hay module cấp thấp?**

Đó là **DIP — Dependency Inversion Principle** (Lesson 28). DIP là cột trụ thứ 5 (cuối) của SOLID — nói rằng cấp cao không phụ thuộc cấp thấp; cả hai phụ thuộc abstraction; abstraction được *định nghĩa bởi cấp cao* (consumer-driven). DIP đảo chiều dependency thông thường, là tâm điểm của Clean Architecture (lesson 29) và Hexagonal (lesson 30).

> **Nhớ một câu**: ISP không phải "tách interface cho nhỏ". ISP là "**interface = client view**, không phải catalog method của implementation".
