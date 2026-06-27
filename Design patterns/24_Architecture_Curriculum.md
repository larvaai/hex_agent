# Lộ trình Architecture — Tầng "ngữ pháp + văn phong" của Software Architect

> Sau 23 GoF, bạn đã có **vocabulary** (từ vựng pattern). Phần này dạy **ngữ pháp** (nguyên tắc đặt câu — SOLID) và **văn phong** (kiến trúc tổng thể — Clean / Hexagonal / EDA / CQRS), kèm **anti-patterns** (lỗi văn phạm thường gặp). Đây mới là tầng giúp bạn quyết định: *"Hệ thống này nên trông như thế nào trước khi viết một dòng code đầu tiên."*

---

## Triết lý ba tầng

| Tầng | Tên | Câu hỏi trả lời | Lessons |
|------|-----|-----------------|---------|
| 1 — Vocabulary | **23 GoF Patterns** | "Khi gặp vấn đề X, mẫu chuẩn là gì?" | ✅ 1–23 (đã xong) |
| 2 — Grammar | **SOLID Principles** | "Một class/module phải tuân thủ những luật nào?" | 24–28 |
| 3 — Style | **Architectural Patterns** | "Cả hệ thống tổ chức thế nào?" | 29–32 |
| 4 — Hygiene | **Anti-patterns** | "Những gì tôi *phải tránh*?" | 33 |

Đây không phải chia tầng cứng — chúng đan vào nhau. Một service Hexagonal vẫn cần SOLID bên trong; một Use Case Clean Arch vẫn có thể dùng Strategy/Observer GoF. Curriculum này giúp bạn nhìn **layer** rõ ràng để biết khi review code mình đang đánh giá ở mức nào.

---

## Mini-project xuyên suốt — `Ellumm Quiz Service`

Một service nhỏ làm sợi chỉ đỏ qua tất cả 10 lessons. Mỗi lesson **refactor cùng codebase này** lên một tầng kiến trúc mới — bạn sẽ tận mắt thấy code biến hóa và cảm nhận trade-off khi pattern leo bậc.

**Domain ban đầu** (intentionally tệ — God class, hard-coded, không testable):
- User submit quiz → tính điểm → lưu DB → gửi email → cập nhật leaderboard.
- Một file Python ~200 dòng làm hết, gọi là `quiz_god.py`.

**Hành trình refactor**:
```
quiz_god.py  (Lesson 24, hiện trạng: anti-pattern God Object)
   │
   ├─ 24 SRP   →  tách 5 trách nhiệm
   ├─ 25 OCP   →  thêm loại quiz mới không sửa code cũ
   ├─ 26 LSP   →  mọi loại Question swap được
   ├─ 27 ISP   →  tách interface "chấm điểm" khỏi "render"
   ├─ 28 DIP   →  domain không biết PostgreSQL hay Mongo
   ├─ 29 Clean Arch  →  4 vòng tròn: Entity / UseCase / Adapter / Framework
   ├─ 30 Hexagonal   →  ports & adapters: Web/CLI/Event đều gọi cùng core
   ├─ 31 EDA         →  QuizSubmitted event → analytics, notification, leaderboard
   ├─ 32 CQRS+ES     →  write path (submit) tách read path (leaderboard query)
   └─ 33 Anti-patterns  →  catalog các phiên bản TỆ + cách phát hiện
```

---

## Phần A — SOLID (Lessons 24–28)

5 nguyên tắc do Robert C. Martin tổng hợp (chữ cái đầu: **S**RP, **O**CP, **L**SP, **I**SP, **D**IP). Đây là tầng *micro-design* — luật cho mỗi class, mỗi module, mỗi interface.

| #  | Principle | Định nghĩa ngắn | Neuroscience Analogy |
|----|-----------|-----------------|----------------------|
| 24 | **S**ingle Responsibility (SRP) | Một class chỉ có MỘT lý do để thay đổi | **Functional specialization** — V1 chỉ xử lý edge, MT chỉ xử lý motion. Não không có "neuron đa năng" vì entanglement chi phí quá cao |
| 25 | **O**pen/Closed (OCP) | Mở để mở rộng, đóng để sửa đổi | **Synaptic plasticity** — học cái mới = thêm synapse / điều chỉnh weight, *không* phá hủy circuit cũ. Hippocampus pattern separation chính là OCP sinh học |
| 26 | **L**iskov Substitution (LSP) | Subclass phải thay thế được superclass mà không phá hành vi | **Pyramidal neuron uniformity** — mọi pyramidal neuron (L5, L2/3, hippocampal CA1) tuân thủ "giao diện AP" giống nhau, swap được mà circuit không vỡ |
| 27 | **I**nterface Segregation (ISP) | Client không nên bị ép phụ thuộc method nó không dùng | **Receptor specificity** — một synapse chỉ "cài" GABA-A *hoặc* AMPA *hoặc* NMDA, không có "god receptor" nghe mọi ligand. Tách interface = tách receptor |
| 28 | **D**ependency Inversion (DIP) | Module cấp cao không phụ thuộc module cấp thấp; cả hai phụ thuộc abstraction | **Thalamus relay** — cortex không nói chuyện trực tiếp với photoreceptor; cả hai phụ thuộc "abstract sensory format" do thalamus định nghĩa. Đó là DIP tự nhiên |

> **Mẹo nhớ thứ tự**: SRP và DIP là 2 cái quan trọng nhất; OCP là *kết quả* của LSP + ISP + DIP đúng. Nếu chỉ học 2 thứ — học SRP và DIP.

---

## Phần B — Architectural Styles (Lessons 29–32)

Từ "luật cho class" leo lên "topology cho hệ thống". Mỗi kiến trúc trả lời câu hỏi khác nhau:

| #  | Pattern | Câu hỏi cốt lõi | Neuroscience Analogy |
|----|---------|------------------|----------------------|
| 29 | **Clean Architecture** | "Domain logic phải sống được kể cả khi đổi DB / framework / UI" | **Concentric circuits** — brainstem (entities, conserved) ← cortex (use cases) ← thalamus (interface adapters) ← muscles/sensors (frameworks). Mất cortex bạn còn thở; mất brainstem bạn chết. Dependency Rule chỉ một chiều: outer → inner |
| 30 | **Hexagonal (Ports & Adapters)** | "Core domain phải plug-in được mọi loại I/O" | **Sensory substitution** — não học vẽ bằng chân sau khi mất tay; "Tongue display unit" cho người mù. Cortex là core, mỗi giác quan/cơ là adapter pluggable. Driving ports (sensory) ↔ Driven ports (motor) |
| 31 | **Event-Driven Architecture (EDA)** | "Các bộ phận tách rời, react bất đồng bộ qua events" | **Action potential broadcast** — dopamine RPE từ VTA bắn đi → striatum, PFC, motor cortex *cùng lúc nhận* và xử lý độc lập. Bus = neurotransmitter; backpressure = GABA inhibition; saga = polysynaptic chain |
| 32 | **CQRS + Event Sourcing** | "Đường ghi và đường đọc tối ưu khác nhau, nên tách" | **Memory consolidation duality** — hippocampus = write path (chậm, durable, episodic encoding); neocortex = read path (nhanh, indexed, semantic). Sleep replay = event replay project lên read model. Eventual consistency là cách não thật vận hành |

---

## Phần C — Anti-Patterns (Lesson 33)

Một lesson catalog các "lỗi văn phạm" thường gặp + heuristics phát hiện chúng trong code review.

| Anti-pattern | Triệu chứng | Neuroscience Analogy |
|--------------|-------------|----------------------|
| **God Object** | Một class >500 dòng làm mọi thứ | "Neuron toàn năng" không tồn tại — não tránh vì single point of failure |
| **Spaghetti Code** | Control flow rối, không trace được | **Tau tangles** trong Alzheimer — neurofilaments rối loạn → mất chức năng |
| **Anemic Domain Model** | Entities chỉ có getter/setter, logic ở service | "Skeleton without muscles" — cấu trúc có nhưng không hành xử |
| **Big Ball of Mud** | Không có topology rõ ràng | "Đám rối không có cytoarchitecture" — đối lập với 6-layer cortex có trật tự |
| **Golden Hammer** | Mọi vấn đề giải bằng cùng 1 pattern | "Mọi cảm xúc đều giải bằng dopamine" — bỏ qua serotonin, GABA, ACh |
| **Premature Optimization** | Tối ưu trước khi đo | "Synaptic pruning trước khi học xong" — mất đường có thể cần |
| **Lava Flow** | Code chết còn sót lại | "Vestigial structures" — appendix của codebase |
| **Cargo Cult Programming** | Copy pattern không hiểu lý do | "Bắt chước vùng não mà không hiểu chức năng" — học vẹt synaptic |
| **Magic Numbers / Strings** | Hằng số rải khắp code | "Chemical signal không có receptor cố định" — không ai biết số đó nghĩa gì |
| **Shotgun Surgery** | Thay đổi 1 yêu cầu phải sửa 10 file | Phản đề của SRP — trách nhiệm bị scatter |

---

## Format mỗi lesson (giữ nguyên chuẩn 23 GoF)

Mỗi lesson trong phần này vẫn theo cấu trúc đã validate ở 23 GoF cũ:

**3 mức Ellumm**:
1. **Concept** — vấn đề kiến trúc giải quyết, neuroscience analogy.
2. **Algorithm / Cấu trúc** — vai diễn, dependency rule, biến trạng thái, invariants.
3. **Pseudocode + Python chạy được** — refactor mini-project Ellumm.

**5 chiều**:
- cấu tạo — thành phần nào (class, module, layer).
- vị trí — đặt ở đâu trong hệ thống / vòng tròn nào.
- chức năng — làm gì.
- kết nối — gọi ai, ai gọi.
- ý nghĩa — *tại sao* design như vậy.

**3 loại ví dụ**:
- Vận hành thường (happy path).
- Hỏng/thiếu (vi phạm nguyên tắc → hậu quả cụ thể).
- Ứng dụng Ellumm (refactor `quiz_god.py` lên tầng tương ứng).

**Mức architect**:
- Khi nào DÙNG / KHÔNG DÙNG.
- So sánh pattern lân cận (VD: SRP vs ISP, Clean vs Hexagonal, EDA vs CQRS).
- Trade-offs (boilerplate vs flexibility, eventual vs strong consistency...).
- Checklist trước khi merge PR.
- Bài tập 4 mức (cơ bản → mở rộng neuro).

---

## Quy ước thư mục

```
D:\Claude code\Claude Cowork prj\Design patterns\
├── 00_Curriculum.md                  ← 23 GoF
├── 24_Architecture_Curriculum.md     ← file này
├── 24_SRP\
│   ├── 24_SRP.md                     ← lesson
│   └── 24_srp.py                     ← code chạy được (refactor quiz_god)
├── 25_OCP\
│   └── ...
├── ...
└── 33_AntiPatterns\
    └── ...
```

**Lưu ý đặc biệt**: vì là mini-project xuyên suốt, file `24_srp.py` sẽ tạo ra `quiz_god.py` baseline; các lesson 25–32 mỗi cái có file `quiz_v25.py`, `quiz_v26.py`... để bạn diff được. Lesson 33 (anti-patterns) sẽ ghép thành 1 catalog với "before / after" snippets ngắn.

---

## Thứ tự học khuyên dùng

```
SRP (24)   ← bắt đầu đây, dễ, gây nghiện
   ↓
OCP (25)   ← ngay sau SRP, hai cái này đi cặp
   ↓
DIP (28)   ← nhảy cóc xuống D vì D + S là 2 cột trụ
   ↓
LSP (26) → ISP (27)   ← bổ sung cho hoàn chỉnh SOLID
   ↓
Clean Architecture (29)   ← áp dụng SOLID lên tầm hệ thống
   ↓
Hexagonal (30)   ← variation của Clean, gọn hơn cho service
   ↓
EDA (31)   ← bước nhảy lớn: từ sync sang async
   ↓
CQRS + ES (32)   ← đỉnh cao distributed, build trên EDA
   ↓
Anti-patterns (33)   ← review lại với con mắt phòng ngự
```

> **Tại sao nhảy cóc S → D → L → I**: SRP và DIP là 2 cái thường vi phạm và gây thiệt hại lớn nhất. Học SRP xong, làm DIP ngay sẽ cho bạn phản xạ "abstract trước, concrete sau" — đây là phản xạ then chốt của software architect. LSP và ISP tinh tế hơn, đi sau dễ tiêu hóa.

---

## Sau lesson 33

Phần này hoàn tất, lộ trình tiếp theo (nếu bạn muốn) có thể là:
- **Distributed systems patterns**: Saga, Outbox, Idempotency, Circuit Breaker, Bulkhead.
- **Domain-Driven Design** (DDD): Bounded Context, Aggregate, Ubiquitous Language.
- **Reliability patterns**: Retry với backoff, Dead Letter Queue, Compensating transaction.
- **Reading list**: Fowler *Patterns of Enterprise Application Architecture*; Vernon *Implementing DDD*; Newman *Building Microservices*; Hohpe & Woolf *Enterprise Integration Patterns*.

Nhưng đó là khi bạn cần — 10 lessons trong file này đã đủ giúp bạn ngồi vào vai architect ở 95% công ty.
