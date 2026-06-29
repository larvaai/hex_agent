# Lesson 34 — Strategic DDD: Bounded Context
## Brodmann Parcellation — 52 vùng cortex cùng "chất xám" nhưng mỗi vùng có cytoarchitecture + ngôn ngữ chức năng riêng. "Activation" ở V1 ≠ "activation" ở M1.

---

## TÓM TẮT MỘT DÒNG

**Bounded Context** = một *biên giới ngữ nghĩa* trong đó **mỗi thuật ngữ có đúng 1 nghĩa**. Cùng từ "Customer" có thể là 3 schema khác nhau ở 3 context (Sales / Billing / Support) — và đó là *bình thường, đáng mong muốn*. **Context Map** vẽ ra cách các context kết nối (7 mẫu integration). **Subdomain classification** (Core/Supporting/Generic) quyết định đầu tư đâu.

> Korbinian Brodmann 1909 — *Comparative Cytology of the Cortex*: chia cortex thành 52 vùng giải phẫu dựa trên *cytoarchitecture* (mật độ neuron, độ dày các layer 1-6, tỷ lệ pyramidal/granular). BA17 (V1 — primary visual), BA22 (Wernicke — semantic comprehension), BA4 (M1 — primary motor), BA44/45 (Broca — speech production), BA9 (dlPFC — executive control). Cùng signal "đến axon kích thích" có nghĩa khác hoàn toàn trong vùng khác nhau — *spike trong V1* là edge orientation, *spike trong M1* là motor command, *spike trong BA22* là phoneme parsing. Connection giữa vùng (white matter tracts) chính là **Context Map**: arcuate fasciculus Wernicke→Broca là Customer-Supplier, corpus callosum L↔R là Partnership, thalamic relay là Open Host Service. **Cortex parcellation là bounded context sinh học** — đã chứng minh hiệu quả 500 triệu năm tiến hoá.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Đến Lesson 32, bạn đã có Aggregate (tactical DDD). Nhưng *trước khi* viết Aggregate, có một câu hỏi lớn hơn: **boundary ở đâu? Aggregate này thuộc service nào? Term "User" trong code có nghĩa gì?**

Trong dự án thực, bốn vấn đề phá hệ:

1. **Term overloading**: dev hỏi business "Customer là gì?". Business trả: "phụ thuộc bạn hỏi team nào." Sales nói "Customer = ai chưa mua, tier=lead". Billing nói "Customer = ai có invoice active". Support nói "Customer = ai mở ticket trong 90 ngày". → 1 từ, 3 model. Hệ thống *monolith model* sẽ nhồi mọi field vào 1 class `Customer` 60 field — *anaemic + bloat*.

2. **Coupling lan toàn diện**: thêm field cho Sales làm vỡ test Billing vì cùng class.

3. **Team scaling lock**: 5 team cùng sửa 1 model → merge conflict + sequential release.

4. **Wrong investment**: dành 6 tháng build "advanced auth" trong khi auth là *generic subdomain* (mua Auth0). Lãng phí lực core team.

Strategic DDD trả lời bằng 3 quyết định *trước khi* code:

- **Cắt boundary**: định nghĩa rõ "trong context X, term Y nghĩa Z".
- **Vẽ map**: chỉ ra context nào tương tác context nào, theo mẫu nào.
- **Phân loại priority**: subdomain nào là Core (build), Supporting (build nhẹ), Generic (mua).

### 1.2. Định nghĩa 4 khái niệm chính

**(a) Domain & Subdomain**:
- *Domain* = toàn bộ vấn đề doanh nghiệp giải quyết. Vd: "online education platform".
- *Subdomain* = một sub-vấn đề. Vd của online education: Course Authoring, Quiz Engine, Live Class, Billing, Analytics, Auth.

**(b) Subdomain classification** (Vernon, Evans):

| Loại | Đặc điểm | Quyết định | Ví dụ Ellumm |
|------|----------|------------|--------------|
| **Core** | Lợi thế cạnh tranh; là *raison d'être* của business | Build by best engineer | Adaptive scoring algorithm; spaced-repetition |
| **Supporting** | Cần để vận hành nhưng không lợi thế | Build vừa phải hoặc customize off-the-shelf | Quiz authoring UI; reporting |
| **Generic** | Commodity, mọi business có | Mua / dùng SaaS | Auth (Auth0), billing (Stripe), email (SendGrid) |

> Quy tắc 80/20: 80% effort vào Core (20% subdomain). Generic *không bao giờ* deserve in-house team.

**(c) Bounded Context**:

> Eric Evans 2003 — *Domain-Driven Design*: *"A description of a boundary (typically a subsystem, or the work of a particular team) within which a particular model is defined and applicable."*

3 thuộc tính bắt buộc:
1. **Ngôn ngữ thống nhất bên trong** — Ubiquitous Language. Term "Submission" trong Submission Context có 1 nghĩa chính xác.
2. **Model độc lập với context khác** — Submission Context có `User { user_id, score_history }`, Notification Context có `User { user_id, email, sms_preferences }`. Cùng `user_id` nhưng khác model.
3. **Tự deploy được** — bounded context có team riêng, repo riêng (hoặc folder rõ), release riêng.

> ⚠️ Bounded Context **≠** Microservice. Một microservice là **một thực hiện** của bounded context. Bạn có thể có 3 bounded context trong 1 monolith (folder riêng, không cross-import). Đảo lại, 1 bounded context có thể chia 2 microservice nếu performance cần. Tách *physical* (microservice) là quyết định sau, độc lập với tách *logical* (bounded context).

**(d) Ubiquitous Language**:

Term *cùng tên dùng ở code và ở meeting với business*. Không có "translation layer trong đầu" của dev. Nếu business gọi "Submission" thì class tên `Submission`, không phải `QuizAnswerForm`.

Quy tắc: trong scope của 1 bounded context, *không cho phép* hai term cho cùng concept; cũng *không cho phép* hai concept dùng cùng term.

### 1.3. Neuroscience — Cortex parcellation Brodmann

**Korbinian Brodmann 1909** — soi cortex dưới kính hiển vi, dùng nhuộm Nissl. Phân biệt vùng dựa trên:
- *Tỷ lệ neuron pyramidal vs granular* (layer 4 dày = sensory; layer 5 dày = motor).
- *Mật độ neuron* (V1 dày ~25,000 neuron/mm² vs PFC ~10,000).
- *Myelination pattern* (vùng motor myelin nhiều → fast conduction).
- *Có/không stria of Gennari* (vạch trắng layer 4b của V1).

52 vùng. Mỗi vùng là một **bounded context sinh học**:

| Brodmann | Tên | "Subdomain" | Loại |
|----------|-----|-------------|------|
| BA17 | V1 — primary visual | Edge/orientation detection | Core (sensory) |
| BA18-19 | V2/V3/V4 — visual association | Shape, color, motion | Core |
| BA22 | Wernicke | Semantic comprehension | Core (language) |
| BA44/45 | Broca | Speech production | Core (language) |
| BA4 | M1 — primary motor | Direct cortical drive of muscle | Core (motor) |
| BA6 | Premotor / SMA | Motor planning | Supporting |
| BA9/46 | dlPFC | Working memory, executive | Core (cognition) |
| BA8 | Frontal eye field | Saccade control | Supporting |
| BA40/39 | Inferior parietal | Spatial integration | Supporting |
| BA10 | Frontopolar | Most abstract planning | Core (cognition) |

**Khái niệm "spike kích thích neuron" mang nghĩa khác trong từng vùng** — đó là Ubiquitous Language sinh học. Một fMRI activation:
- Tại BA17 → "thấy edge".
- Tại BA22 → "hiểu nghĩa từ".
- Tại BA4 → "ra lệnh co cơ".

Không có **một model "neuron activation" duy nhất** cho cả não — mỗi vùng có *cytoarchitecture + connectivity + behavior* riêng. Tiến hoá hàng triệu năm đã chọn *segmentation*, không phải *uniformity*. Code architect học từ đây: **segmentation > uniformity**.

**Connection giữa vùng** = white matter tracts:
- *Arcuate fasciculus* (Wernicke ↔ Broca): bệnh đứt → conduction aphasia, hiểu được nhưng nói lặp lại không được. → **Customer-Supplier**.
- *Corpus callosum* (L hemi ↔ R hemi): 250 triệu axon. Cắt → split-brain. → **Partnership** (symmetric).
- *Thalamic relay* (cortex ↔ thalamus ↔ subcortical): broadcasting protocol. → **Open Host Service**.
- *Cerebellar peduncles* (cortex → cerebellum): cerebellum *re-encode* signals timing & coordination. → **Anti-Corruption Layer**.

**Subdomain classification** trong não:
- Core (visual / motor / language primary): chiếm ~30% cortex, *highly specialized*, không thể outsource.
- Supporting (association cortex, Brodmann 5/7/40): tích hợp.
- Generic (brainstem regulation): mọi mammal đều có; "off-the-shelf" trong tiến hoá.

### 1.4. Khi nào áp dụng / không áp dụng

| Áp dụng khi | Bỏ qua khi |
|-------------|------------|
| ≥ 2 team làm cùng codebase | 1 dev, dự án < 5,000 LOC |
| Term overloading rõ rệt (Customer/User có nhiều nghĩa) | Domain đơn giản (CRUD pure) |
| Plan scale ≥ 5 service | Prototype < 3 tháng |
| Business expert nói language khác dev language | Internal tool đời ngắn |
| Đang refactor từ Big Ball of Mud | Khởi đầu CLI tool |

> Strategic DDD *đắt*: cần workshop với business, vẽ context map nhiều lần, sửa nhiều. Đừng làm cho prototype. Làm khi đầu tư dài hạn.

---

## MỨC 2 — CẤU TRÚC

### 2.1. Context Map — 7 mẫu integration (Vernon enumeration)

Khi 2 bounded context tương tác, *quan hệ team + protocol* được mã hoá thành 1 trong 7 mẫu:

| Mẫu | Quan hệ | Khi dùng | Brain analogy |
|-----|---------|----------|---------------|
| **Partnership** | 2 team đi cùng nhịp, share success/failure | Co-product launch, cross-team dependency cao | Corpus callosum L↔R: symmetric, synchronized |
| **Shared Kernel** | Share 1 phần code/schema nhỏ, joint owned | Khi cost duplicate > cost coordinate | Cerebral commissures: nhỏ, cụ thể, joint-managed |
| **Customer-Supplier** | Downstream phụ thuộc upstream; upstream phải attentive | Có power balance — upstream care về downstream | Wernicke→Broca (arcuate): supplier→customer flow |
| **Conformist** | Downstream chấp nhận upstream model nguyên xi (upstream không care) | Khi upstream là big vendor / không thể negotiate | Cortex → spinal cord: cortex gửi tín hiệu, spinal có protocol cố định, không thay đổi cho cortex |
| **Anti-Corruption Layer (ACL)** | Downstream xây adapter dịch upstream model → model nội bộ | Khi upstream model "bẩn" / sẽ thay / khác triết lý | Cerebellum: nhận cortical signals nhưng *re-encode* hoàn toàn theo cerebellar logic |
| **Open Host Service (OHS)** | Upstream publish 1 protocol/API chuẩn cho mọi downstream | Upstream có nhiều consumer; muốn 1 contract chung | Thalamus → cortex: broadcast format chuẩn; mọi vùng cortex consume cùng signal |
| **Published Language** | Format/protocol formalized, documented (OpenAPI, AsyncAPI, JSON Schema) | Khi cần lasting contract, multi-team, cross-org | Action potential format (Hodgkin-Huxley): "published" protocol mọi neuron tuân thủ |

Ngoài ra còn 3 quan hệ "vô hình":
- **Separate Ways** — 2 context không tích hợp gì với nhau dù cùng domain. Không lãng phí coordinate.
- **Big Ball of Mud** — context bên trong là Big Ball of Mud; outside dùng Conformist hoặc ACL để cô lập.
- **Upstream-Downstream** — chỉ direction, chưa rõ mẫu nào.

### 2.2. Cách vẽ Context Map

Notation (Vernon):
- Hình tròn / oval = bounded context.
- Mũi tên có chữ **U** (upstream) và **D** (downstream).
- Trên mũi tên: tên mẫu (Partnership / Customer-Supplier / ACL...).

Ví dụ Ellumm:

```
                                                ┌──────────────┐
                                                │  Auth (gen.) │
                                                │   Auth0      │
                                                └──────┬───────┘
                                                       │ U  Conformist
                                                       ▼
              ┌──────────────────────────────────────────────┐
              │              Submission Context               │
              │  (CORE — adaptive scoring, attempt rules)    │
              └────┬──────────────────┬─────────────────┬────┘
                   │ U                │ U               │ U
                   │ Customer-Supplier│ OHS+PL          │ OHS+PL
                   │                  │ (event)         │ (event)
                   ▼                  ▼                 ▼
            ┌─────────────┐  ┌────────────────┐  ┌────────────────┐
            │ Quiz Context│  │ Leaderboard ctx│  │ Notification ctx│
            │   (Core)    │  │  (Supporting)  │  │   (Generic)     │
            └─────────────┘  └────────────────┘  └────────────────┘
```

### 2.3. Event Storming — workshop technique

Một kỹ thuật của Alberto Brandolini 2013, dùng để discover bounded context với business expert trong vài giờ. Sticky note màu:

| Màu | Loại | Vd |
|-----|------|-----|
| **Orange** | Domain Event (past tense) | "QuizSubmitted", "ScoreCalculated" |
| **Blue** | Command | "SubmitQuiz", "CalculateScore" |
| **Yellow** | Actor | "Student", "Teacher", "Admin" |
| **Pink** | External system | "Email service", "Payment gateway" |
| **Purple** | Policy / business rule | "When score < 60% → re-attempt allowed" |
| **Green** | Read model | "Leaderboard view", "Student dashboard" |
| **Red** | Hot spot / question | "Còn không rõ cái này" |

Quy trình 3 bước:
1. **Big Picture**: dán event timeline (orange) trên tường dài, chronological.
2. **Process Modeling**: thêm command (blue), actor (yellow), policy (purple).
3. **Software Design**: gom event vào cluster — *mỗi cluster ≈ 1 bounded context*. Vẽ boundary.

Output: context map sơ bộ + danh sách aggregate + ubiquitous language draft.

### 2.4. 4 invariants

1. **Mỗi term có đúng 1 nghĩa trong scope của bounded context**. Vi phạm → quay về Big Ball of Mud về mặt model.
2. **Cross-context communication phải qua protocol explicit** (event / API / RPC), không cross-import code.
3. **Mỗi bounded context có ubiquitous language documented** (glossary).
4. **Subdomain classification phải được quyết định trước investment**. Core ≠ team experiment với architect mới.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
# Ellumm domain phân ra 4 bounded context + 1 generic external

# === Quiz Context (CORE) ===
package quiz_context:
    class Quiz:                     # Aggregate
        id, title, questions[], author
        publish(), retire(), add_question(q)
    class Question:                 # Value Object trong context này
        text, correct_answer, weight
    class User:                     # Mô hình "User" của QUIZ
        user_id, display_name, author_level     # ← chỉ field cần cho authoring

# === Submission Context (CORE) ===
package submission_context:
    class Submission:               # Aggregate
        id, user_id, quiz_id, answers, score, attempts
        submit(), grade(), retry()
    class User:                     # Mô hình "User" của SUBMISSION (khác Quiz)
        user_id, attempt_count, score_history    # ← chỉ field cần
    interface QuizCatalog:          # Cổng tới Quiz Context (Customer-Supplier)
        get_quiz(quiz_id) -> QuizSummary    # DTO nhỏ — không phải Quiz entity

# === Leaderboard Context (SUPPORTING) ===
package leaderboard_context:
    class Ranking:                  # Aggregate
        user_id, total_score, rank
        update(new_score)
    class User:                     # Lại khác — chỉ user_id + display_name
        user_id, display_name
    # Tích hợp qua Open Host Service + Published Language event
    handler.on(ScoreCalculatedV1)   # subscribe published event schema

# === Notification Context (GENERIC) ===
package notification_context:
    class Recipient:                # NOTE: KHÔNG gọi là User trong context này
        user_id, email, sms_preferences, locale
    class Receipt:
        recipient_id, channel, template, sent_at
    handler.on(ScoreCalculatedV1)

# === Anti-Corruption Layer ===
package acl:
    class AuthACL:
        # Translate Auth0 user model → bounded context user
        def to_quiz_user(auth0_user) -> quiz_context.User
        def to_submission_user(auth0_user) -> submission_context.User
        def to_notification_recipient(auth0_user) -> notification_context.Recipient

# === Published Language (event schema) ===
class ScoreCalculatedV1:            # Versioned. Public contract.
    event_id, occurred_at, schema_version=1
    user_id, quiz_id, score, correct_count, total
```

### 3.2. Bảng 2x2 nhớ là đủ

|  | **Cùng team** | **Khác team** |
|---|---|---|
| **Cùng business goal** | Partnership / Shared Kernel | Customer-Supplier |
| **Khác business goal** | Separate Ways / Conformist (internal) | OHS + Published Language hoặc ACL |

Quyết định context map = trả 2 câu hỏi:
1. *Communication frequency*: cao → Partnership/Customer-Supplier. Thấp → OHS+PL.
2. *Model alignment*: trùng triết lý → Partnership/Conformist. Khác triết lý → ACL.

---

## NĂM CHIỀU SO SÁNH (in não vs in code)

| Chiều | Trong não (Brodmann parcellation) | Trong code (Bounded Context) |
|-------|------------------------------------|-------------------------------|
| **Cấu tạo** | Mỗi vùng có cytoarchitecture: density neuron, layer thickness, myelin pattern riêng | Mỗi context có package/repo, model class riêng, glossary riêng |
| **Vị trí** | Cortex chia thành 52 vùng có tọa độ MNI cụ thể | Folder `quiz/`, `submission/`, `leaderboard/`, `notification/` — boundary file system rõ |
| **Chức năng** | V1 = edge; BA22 = semantic; BA4 = motor → "activation" mang nghĩa khác | "User" model trong Quiz vs Submission vs Notification — cùng từ, schema khác |
| **Kết nối** | Arcuate fasciculus (C-S), corpus callosum (Partnership), thalamic relay (OHS), cerebellum (ACL) | Context map: Customer-Supplier, Partnership, OHS, ACL, Conformist, Shared Kernel, Published Language |
| **Ý nghĩa** | Segmentation tiến hoá → robust, parallel, specialized → có lợi thế chọn lọc | Segmentation kiến trúc → robust, parallel team, focused investment, scale > 5 team |

---

## BA VÍ DỤ

### Ví dụ 1 — Vận hành thường (happy path)

Ellumm Quiz được tách thành 4 bounded context. Student submit quiz:

```
1. Student gọi POST /submissions → SubmissionContext
2. SubmissionContext gọi QuizContext.get_quiz_summary(quiz_id) qua Customer-Supplier API
   (chỉ lấy DTO nhỏ {id, title, correct_answers_count}, không lấy Quiz entity)
3. SubmissionContext aggregate apply rule + persist
4. SubmissionContext publish ScoreCalculatedV1 event (Published Language)
5. LeaderboardContext subscribe → update Ranking aggregate
6. NotificationContext subscribe → send Receipt
7. Cả Leaderboard và Notification dùng AuthACL.to_*_recipient(auth0_user)
   để dịch Auth0 model → recipient model nội bộ
```

Lợi:
- Team Quiz không biết NotificationContext tồn tại.
- Schema `User` ở Submission khác hoàn toàn `Recipient` ở Notification.
- Đổi Auth0 → Okta = chỉ sửa AuthACL, 4 context không touch.

### Ví dụ 2 — Hỏng / vi phạm (failure mode)

**Vi phạm A — Shared model "User" cho mọi context**:
```python
# BAD — 1 class User dùng khắp
class User:
    user_id, email, sms, score_history, author_level, billing_id, ...
```
→ Sửa field `sms_preferences` cho Notification phá test Quiz Authoring. Field count > 40. Anaemic + bloat. Quay về Big Ball of Mud về mặt model.

**Vi phạm B — Cross-context import code**:
```python
# BAD — Leaderboard import trực tiếp Submission entity
from submission_context.entities import Submission       # ✗ cross-context import
class Ranking:
    def update_from_submission(self, sub: Submission): ...
```
→ Leaderboard giờ phụ thuộc internal model của Submission. Đổi Submission = vỡ Leaderboard. Đúng: chỉ subscribe Published Language event.

**Vi phạm C — Wrong subdomain classification**:
```
Team đầu tư 4 sprint xây hệ thống auth in-house "vì secure hơn"
  → trong khi Auth0/Okta giải xong vấn đề
  → Core team mất 4 sprint không build adaptive scoring (Core thật sự)
```
→ Generic subdomain bị nhầm thành Core. Đối thủ ra trước market với scoring tốt hơn.

**Vi phạm D — Term collision không khai báo**:
```
Sales team gọi "Lead = ai chưa mua".
Marketing team gọi "Lead = ai click ad".
Dev nhồi 2 nghĩa vào 1 class Lead → có 2 boolean is_lead_sales, is_lead_marketing.
```
→ Đúng: 2 bounded context (Sales / Marketing), 2 class Lead riêng, ACL nếu cần dịch.

### Ví dụ 3 — Ứng dụng Ellumm Quiz (refactor)

File `34_bounded_context.py` đi kèm minh hoạ:
- 4 bounded context package: `quiz_ctx`, `submission_ctx`, `leaderboard_ctx`, `notification_ctx`.
- Mỗi context có class `User` (hoặc `Recipient` trong notification) **khác nhau hoàn toàn**.
- `auth_acl` translate `Auth0User` (external generic) sang context-specific user.
- `ScoreCalculatedV1` là Published Language event schema (versioned).
- Customer-Supplier integration: SubmissionContext gọi QuizContext qua adapter port.
- OHS + Published Language: SubmissionContext publish event; Leaderboard/Notification subscribe độc lập.
- Demo cross-context isolation: thay đổi field `Notification.Recipient.sms_preferences` không lan ra `Submission`.

---

## MỨC ARCHITECT — TRADE-OFFS & ANTI-PATTERNS

### Khi nào DÙNG

- Team ≥ 2, dự đoán scale ≥ 5.
- Domain phức tạp với term overloading.
- Đang refactor monolith → microservice.
- Cần khẳng định ownership rõ (1 context = 1 team).

### Khi nào KHÔNG dùng

- Team 1-2 người, dự án < 6 tháng.
- Domain CRUD pure (chỉ table → CRUD UI).
- Prototype / spike.
- Chưa có business expert sẵn sàng workshop.

### Trade-offs

| Trục | Bounded Context được | Bounded Context mất |
|------|----------------------|---------------------|
| **Team autonomy** | Mỗi team own context, release riêng | Cần coordination chuyên trách (architect / product) |
| **Model clarity** | Term 1 nghĩa rõ trong scope | Phải maintain glossary, ACL khi tích hợp |
| **Scale** | Context scale độc lập | Cross-context query khó (eventual consistency) |
| **Learning** | Onboard 1 context nhanh | Onboard architect lâu hơn (phải nắm context map) |
| **Refactor** | Đổi context model an toàn | Đổi *context map* (boundary) đắt — phải migrate data |

### Anti-patterns thường thấy

| Anti-pattern | Mô tả | Phát hiện |
|--------------|-------|-----------|
| **Big Ball of Bounded Contexts** | Boundary có nhưng không thực sự cô lập — code cross-import | grep cross-package import |
| **Universal Model** | 1 schema "User" / "Order" cho tất cả context | Class > 30 field, dùng ở > 3 context |
| **Wrong subdomain** | Build in-house cho Generic | Team Core dành > 30% thời gian cho auth/billing/email |
| **Shared Database** | Nhiều context share 1 DB schema | grep cross-context SQL tables |
| **Conformist cho upstream xấu** | Downstream chấp nhận upstream bẩn thay vì ACL | Field naming inconsistent across contexts |
| **No context map** | "Mọi service nói với mọi service" — không document quan hệ | Hỏi architect → không trả lời được |
| **Anaemic ACL** | ACL chỉ rename field, không translate semantics | ACL < 10 dòng cho upstream phức tạp |
| **Premature boundary** | Tách context khi domain chưa rõ | Phải merge 2 context lại sau 3 tháng |
| **Distributed monolith via contexts** | Context riêng nhưng release đồng bộ | Mọi PR đụng > 3 context |

### Checklist trước khi merge PR (Strategic DDD review)

- [ ] Term mới có trong glossary của bounded context tương ứng?
- [ ] Nếu tích hợp context khác: tên mẫu (C-S / OHS / ACL)?
- [ ] Có cross-context import code không? (cấm)
- [ ] Event publish: có version (V1)?
- [ ] Adapter (ACL) ở folder riêng, không phải trong domain core?
- [ ] Subdomain mới được classify (Core/Supporting/Generic) chưa?
- [ ] Boundary thay đổi: đã thông báo team ảnh hưởng?

### So sánh với pattern lân cận

| Pattern | Tầm | Khác Bounded Context |
|---------|-----|----------------------|
| **Module / Package** | Code organization | Module chỉ là folder. Bounded context là *semantic boundary + ubiquitous language + team*. |
| **Microservice** | Deployment | Microservice là *physical*. Bounded Context là *logical*. 1 context có thể = 1 hoặc N microservice. |
| **Layered Architecture** | Topology | Layer chia theo *technical* (UI/BL/DAL). Bounded context chia theo *business*. Orthogonal. |
| **Hexagonal (30)** | Per-service | Hex áp dụng *bên trong* 1 bounded context. |
| **CQRS (32)** | Per-aggregate | CQRS áp dụng bên trong 1 bounded context. |
| **Bounded Context** | Strategic | Đây là *meta-pattern* quyết định ranh giới của các pattern khác. |

### So sánh 3 thuật ngữ dễ nhầm

| | Subdomain | Bounded Context | Microservice |
|---|-----------|------------------|--------------|
| **Bản chất** | Business concept | Software model boundary | Deployment unit |
| **Câu hỏi** | "Vấn đề business là gì?" | "Model áp dụng phạm vi nào?" | "Process nào chạy?" |
| **Bao nhiêu?** | Cho mỗi sub-vấn đề | Cho mỗi model coherent | Cho mỗi runtime unit |
| **Ai quyết định?** | Business / product | Architect | DevOps + architect |

Quan hệ: 1 Subdomain có thể có nhiều Bounded Context (hiếm). Phổ biến 1:1. Bounded Context có thể chia thành nhiều Microservice (vì performance). Phổ biến 1:1.

---

## BÀI TẬP — 4 MỨC

### Mức 1 — Cơ bản (45 phút)

Lấy code Ellumm Quiz từ Lesson 32 (CQRS+ES). List ra **3 bounded context** bạn nghĩ là hợp lý. Cho mỗi context:
- Tên (1-2 từ).
- 3 entity chính.
- 1 câu định nghĩa "User" *trong context này*.
- Classify Core/Supporting/Generic.

### Mức 2 — Trung bình (1.5 giờ)

Vẽ context map ASCII (hoặc bằng Mermaid) cho Ellumm Quiz với ít nhất 4 bounded context + 1 external system. Trên mỗi edge:
- Tên mẫu (Customer-Supplier / OHS+PL / ACL...).
- Direction (U/D).

Viết 1 đoạn 200 từ giải thích *tại sao chọn mẫu đó* cho mỗi edge.

### Mức 3 — Khó (architect, 3 giờ)

(a) Refactor code Ellumm Quiz: tách thành 4 Python package (`quiz_ctx/`, `submission_ctx/`, `leaderboard_ctx/`, `notification_ctx/`). Yêu cầu:
- Mỗi package có class `User` (hoặc `Recipient`) khác nhau.
- 0 cross-package import code (chỉ qua event hoặc port adapter).
- Viết AuthACL dịch `Auth0User` → mỗi context user.
- Verify bằng dependency graph (Mermaid hoặc pydeps).

(b) Tạo 1 file `glossary.md` cho mỗi bounded context: list tất cả term + định nghĩa 1 dòng. So sánh các term trùng tên qua context (vd "User" 3 lần) — bảng đối chiếu.

### Mức 4 — Mở rộng neuro (2 giờ tự do)

Đọc Brodmann 1909 (tóm tắt Wikipedia hoặc 1 chương Kandel *Principles of Neural Science*). Trả lời:

1. **Cytoarchitectonic difference**: V1 (BA17) có *stria of Gennari* — vạch trắng đặc trưng. Bạn nhận diện V1 qua kính hiển vi. Trong code: làm sao "nhận diện" 1 bounded context khi không có nhãn? Đề xuất 3 dấu hiệu cytoarchitectonic của code.

2. **Cross-boundary plasticity**: sau stroke V1, vùng kế (V2/V3) có thể tiếp quản phần chức năng (cortical remapping). Trong code: khi 1 bounded context "down", context khác có nên gánh? Có và không? Bao nhiêu? Liên hệ tới graceful degradation (Reliability patterns).

3. **Brodmann có 52 vùng, Princeton Atlas hiện nay phân ~180 vùng**: số *boundary* không ngừng tăng theo phương pháp đo. Trong code: dấu hiệu nào nói "cần tách context hơn nữa"? Dấu hiệu nào nói "đang over-split, nên merge"?

---

## ĐỒ HOẠ TỔNG KẾT

```
       STRATEGIC DDD — 3 quyết định trước khi code
   ──────────────────────────────────────────────────────────
   1. SUBDOMAIN CLASSIFY     2. BOUND CONTEXT             3. CONTEXT MAP
   ──────────────────       ──────────────────           ────────────────
   Core    → build best     "Trong context X,           Partnership
   Support → build vừa       term Y có nghĩa Z"         Customer-Supplier
   Generic → buy/SaaS       glossary + UL               OHS + Published Lang
                                                         Anti-Corruption Layer
   Brain:                   Brain:                      Conformist
   Core = V1, M1            BA17 = "edge"               Shared Kernel
   Support = BA40           BA22 = "semantics"          Separate Ways
   Generic = brainstem      BA4 = "motor"
                            (cùng "spike", khác nghĩa)  Brain:
                                                         arcuate (C-S)
                                                         corpus callosum (P)
                                                         thalamic relay (OHS)
                                                         cerebellum (ACL)
```

> **Tóm lại**: Bounded Context là *biên giới ngữ nghĩa*; bên trong term có 1 nghĩa, bên ngoài có thể khác. Context Map vẽ ra quan hệ. Subdomain classification quyết định đầu tư. Não dùng đúng nguyên lý này 500 triệu năm — segmentation > uniformity. Đây là pattern *strategic*, làm trước khi gõ code đầu tiên cho hệ phức tạp. Đắt cho prototype; rẻ và sống còn cho hệ enterprise.

---

## TIẾP THEO (gợi ý lộ trình DDD)

- **Lesson 35 — Tactical DDD: Aggregate sâu** (Aggregate root, invariant, AR-per-transaction, Domain Service, Repository, Specification, Policy).
- **Lesson 36 — Entity vs Value Object vs Domain Event** (khi nào chọn cái nào; immutability; identity).
- **Lesson 37 — Repository pattern + Factory + Specification**.
- **Lesson 38 — Event Storming workshop** (run-through 1 case study end-to-end).
- **Lesson 39 — Distributed DDD**: cross-context consistency, eventual vs strong, Saga inside vs across.
- **Lesson 40 — Ubiquitous Language case study**: rename + glossary management.
