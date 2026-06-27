# Lesson 21 — Strategy Pattern
## Dual-route fear (LeDoux): Low road vs High road — cùng goal, 2 algorithm

---

## TÓM TẮT MỘT DÒNG

**Strategy** = đóng gói _một họ thuật toán_ (cùng giải 1 bài toán) thành các class riêng biệt, để Context có thể đổi algorithm runtime — đổi strategy = đổi cách giải, không sửa Context.

> Khi mắt bạn thoáng thấy "vật cong dài" trên đường, có hai con đường xử lý song song. **Low road** (LeDoux): thalamus → amygdala, ~12ms — pattern match thô, "có thể là rắn" → freeze. **High road**: thalamus → visual cortex → amygdala, ~300ms — phân tích chi tiết, "à đó là cây gậy". Hai con đường cùng hỏi _"có phải threat không?"_ nhưng dùng **algorithm khác nhau**: tốc độ vs độ chính xác. Não chọn dùng đường nào tuỳ context. Đó là Strategy pattern thuần khiết — và là lý do bạn đôi khi nhảy dựng lên trước khi kịp hiểu mình thấy gì.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Bạn cần giải một bài toán (sort, search, compress, recommend, detect threat, route message...) và có **nhiều cách giải hợp lệ**, mỗi cách có trade-off khác nhau.

**Cách ngây thơ**: nhồi tất cả cách vào 1 class với `if/elif`:
```python
class Sorter:
    def sort(self, items, mode):
        if mode == "bubble":
            # 30 dòng
        elif mode == "quick":
            # 30 dòng
        elif mode == "merge":
            # 30 dòng
```
Vấn đề:
- Class phình to, vi phạm SRP.
- Thêm algorithm mới = sửa Sorter (vi phạm Open/Closed).
- Test khó: phải set up Sorter rồi gọi mode đúng.
- Không reuse algorithm ở context khác.

**Strategy pattern**: tách mỗi algorithm thành 1 class implement cùng interface. Context giữ ref tới strategy hiện tại, gọi `strategy.execute(...)`. Đổi algorithm = thay strategy object — Context không biết.

### 1.2. Neuroscience analogy — Dual-route fear (LeDoux, 1996)

Joseph LeDoux khám phá ra rằng não xử lý threat qua **hai đường dẫn song song**:

| | **Low road** (subcortical) | **High road** (cortical) |
|---|---|---|
| **Đường đi** | Thalamus → Amygdala (LA, BLA) | Thalamus → V1/STG/auditory cortex → Amygdala |
| **Tốc độ** | ~12 ms | ~80–300 ms |
| **Độ chính xác** | Thô, dễ false positive | Chi tiết, có context |
| **Tài nguyên** | Ít neuron, rẻ | Nhiều layers cortical, đắt |
| **Output** | "Có thể threat" — fight/flight prep | "Là threat / không" — eval đúng |
| **Tiến hoá** | Cổ — có ở mọi động vật có amygdala | Mới — phát triển ở mammals |

Cùng input (vật thể trong tầm nhìn), cùng goal (đánh giá threat), nhưng **2 algorithm hoàn toàn khác**:
- **Low road**: pattern match nhanh trên feature thô (shape "long-curved", motion "sudden"). Cost rẻ, latency thấp, accuracy thấp.
- **High road**: process qua nhiều layer cortical, lookup memory (đã từng thấy chưa?), context (đang ở rừng hay phòng tắm?). Cost cao, latency cao, accuracy cao.

Kết quả khi 2 đường mâu thuẫn:
- Low road bảo "rắn!" → cơ thể đã freeze trước.
- 200ms sau, high road bảo "à, cây gậy" → PFC suppress amygdala, cortisol giảm.
- Bạn cảm thấy "tim đập rồi mới hiểu" — đó chính là dấu vân tay của low road thắng cuộc đua.

Đây là **Strategy thuần khiết** vì:
1. **Cùng interface**: cả hai trả về tín hiệu salience cho amygdala.
2. **Cùng input**: thalamus chia tín hiệu cho cả 2.
3. **Khác algorithm**: routing qua cortex hay không.
4. **Có thể chọn**: trong tình huống đời thường, cả 2 chạy. Trong emergency tốc độ cao, low road dominate. Trong analysis bình tĩnh, high road dominate.
5. **Không có state machine giữa 2** — cả 2 độc lập, không kế tiếp nhau (khác State pattern).

#### 5 chiều của analogy

| Chiều      | Trong não                                                                                | Trong code                                                                |
|------------|------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| Cấu tạo    | Thalamus → amygdala (low) vs thalamus → cortex → amygdala (high)                        | Context + Strategy interface + N ConcreteStrategies                        |
| Vị trí     | Hai pipeline song song trong não, hội tụ ở amygdala                                      | Strategy là field/parameter của Context, plug-in từ ngoài                 |
| Chức năng  | Cùng giải bài "có phải threat không?" với 2 algorithm khác trade-off                    | Cùng giải 1 problem (sort, recommend) với N algorithm khác trade-off       |
| Kết nối    | Thalamus broadcast input cho cả 2; amygdala nhận output cả 2; PFC có thể arbitrate      | Client/Context inject Strategy (DI); Context delegate; có thể dùng nhiều strategy đồng thời |
| Ý nghĩa    | Cho phép trade-off speed/accuracy theo context (emergency vs deliberation)              | Cho phép thay algorithm runtime mà không sửa client (Open/Closed)          |

### 1.3. Khi nào DÙNG

- Có **nhiều algorithm hợp lệ** cho cùng problem (sort, search, compress, route, recommend).
- Algorithm phải **chọn được runtime** — config, A/B test, user setting, env-dependent.
- Tách algorithm để **test riêng** mà không cần Context.
- Thuật toán có **trade-off rõ ràng** (memory vs CPU, speed vs accuracy, simple vs precise).
- Cần **plug-in**: 3rd party có thể thêm strategy mới mà không touch core.
- Domain: payment processor (Stripe vs PayPal), compression (gzip vs zstd vs lz4), encryption (AES vs ChaCha20), search ranking (BM25 vs vector vs hybrid).

### 1.4. Khi nào KHÔNG DÙNG

- Chỉ có 1 algorithm và **không thấy trước** sẽ có cái khác → đừng đầu cơ trừu tượng.
- Algorithm thay đổi theo **state nội bộ** (lifecycle) → đó là **State pattern**, không phải Strategy.
- Algorithm khác **chỉ về tham số** (kích thước, threshold) — không khác về logic → dùng tham số/config, không cần class.
- Strategy quá nhỏ (1 dòng code) → **closure / function** đủ. Không cần class formal.
- Algorithm cần **shared mutable state** giữa các "strategy" → đó không phải Strategy đúng nghĩa, dấu hiệu thiết kế sai.

### 1.5. Cảnh báo architect

> **Strategy không miễn phí abstraction**. Mỗi strategy interface là một _hợp đồng_. Khi 2 strategy có signature giống nhau nhưng yêu cầu khác (vd. một cái cần state, một cái không), **interface không truth-telling**. Hậu quả: leak abstraction, "Liskov substitution" bị phá. Trước khi tạo Strategy interface, hãy hỏi: _liệu mọi concrete strategy có thật sự thay thế được nhau ở mọi call site không?_

> **Strategy explosion**: khi mỗi tinh chỉnh nhỏ là 1 class. 50 strategies, mỗi cái 5 dòng — đó là dấu hiệu nên dùng **closure** hoặc **higher-order function**, không phải Strategy class. Pythonic: hàm là first-class object — đừng wrap mỗi function thành class.

---

## MỨC 2 — ALGORITHM

### 2.1. Vai diễn

```
┌──────────────────────┐         ┌──────────────────────┐
│      Context         │ uses    │     Strategy         │
│ (e.g. ThreatDetector)│────────▶│   (interface)        │
│                      │         │ + execute(input)→Out │
│ - strategy: Strategy │         └──────────────────────┘
│ + set_strategy(s)    │                  △
│ + handle(input)      │                  │
└──────────────────────┘     ┌────────────┼─────────────┐
                       ┌──────────┐ ┌──────────┐ ┌──────────┐
                       │ LowRoad  │ │ HighRoad │ │  Hybrid  │
                       │ Strategy │ │ Strategy │ │ Strategy │
                       └──────────┘ └──────────┘ └──────────┘
```

- **Context**: object chính. Giữ ref tới strategy. Public method delegate cho strategy.
- **Strategy interface**: 1 method (thường là `execute` / `apply` / `process`).
- **ConcreteStrategy**: implement algorithm. Nên **stateless** hoặc immutable (singleton dùng được).
- **Client**: chọn strategy và inject vào Context.

### 2.2. Luồng điều khiển

```
client = ThreatDetector(strategy=HighRoadStrategy())
result = client.detect(stimulus)
       │
       ▼
  self.strategy.execute(stimulus)
       │
       ▼
HighRoadStrategy.execute(stimulus):
   features = visual_cortex.parse(stimulus)
   memory = lookup_episodic(features)
   context = pfc_evaluate(features, memory)
   return ThreatDecision(level=context.threat_score, confidence=0.9)
```

Đổi strategy:
```python
client.set_strategy(LowRoadStrategy())
result = client.detect(stimulus)
# Cùng interface, kết quả nhanh hơn, less accurate
```

### 2.3. Biến trạng thái và bất biến

- **Strategy nên stateless** hoặc immutable. Cùng strategy instance dùng cho nhiều Context, song song an toàn.
- Nếu strategy cần state (cache, counter), state phải **per-Context**, không share.
- **Strategy không sửa Context** từ trong `execute`. Nếu cần thay state → return value cho Context xử lý.
- **Invariant LSP**: mọi concrete strategy phải thực sự thay thế được nhau ở mọi call. Nếu một cái cần resource ngoài (file, network) → leak abstraction.

### 2.4. Biến thể

| Biến thể | Mô tả | Khi nào dùng |
|----------|-------|--------------|
| **Class-based Strategy** | Mỗi strategy là class implement interface | Pattern chuẩn, OOP-clean |
| **Function/closure as strategy** | Strategy là hàm (Python first-class) | Logic ngắn, không cần state |
| **Strategy registry** | Dict `name → strategy`, chọn theo string | Plug-in, config-driven |
| **Composite/Hybrid strategy** | Strategy bọc nhiều strategy (low road + high road, vote) | Cần kết hợp output |
| **Pipeline of strategies** | Chuỗi strategy, output của cái trước là input cái sau | Stream processing, ML pipeline |
| **Lazy strategy** | Chọn strategy lúc cần, có thể dựa trên input size/type | Adaptive optimization |
| **Strategy + State** | State machine với mỗi state có strategy riêng | UI flow với behavior khác per stage |

### 2.5. Strategy vs State — phân biệt rõ

(Quan trọng vì 2 pattern có cấu trúc giống nhau)

| Khía cạnh | Strategy | State |
|-----------|----------|-------|
| Ai chọn | Client (DI, config) | Object tự, theo lifecycle |
| Đổi tần suất | Hiếm — set ban đầu | Thường xuyên, theo event |
| Có lifecycle? | Không | Có (state machine) |
| Strategies có "biết nhau"? | Không (độc lập) | Có (transitions) |
| Object có ý thức về strategy? | Không (chỉ dùng) | Có (state là identity) |
| Ví dụ não | Low road vs High road (chọn theo context) | Sleep stages (cycle bắt buộc) |

### 2.6. Strategy vs Template Method

| Khía cạnh | Template Method | Strategy |
|-----------|----------------|----------|
| Cách compose | Inheritance — hook method override | Composition — inject object |
| Linh hoạt runtime | Không (fixed lúc class init) | Có (đổi runtime) |
| Cấu trúc skeleton | Cha định nghĩa toàn flow | Strategy có thể tự do bên trong |
| Pythonic? | Vừa | Tốt hơn (hàm/closure) |

> **Quy tắc architect**: "Favor composition over inheritance" — đó là lý do Strategy thường thắng Template Method trong code Python/JS hiện đại. Template Method còn hữu ích khi flow cố định và chỉ vài bước cần override.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
interface ThreatDetectionStrategy:
    execute(stimulus: Stimulus) -> ThreatDecision

class LowRoadStrategy implements ThreatDetectionStrategy:
    execute(stim):
        # Pattern match thô
        if has_feature(stim, "long_curved") or has_feature(stim, "sudden_motion"):
            return ThreatDecision(level=0.8, confidence=0.4, latency_ms=12)
        return ThreatDecision(level=0.0, confidence=0.4, latency_ms=12)

class HighRoadStrategy implements ThreatDetectionStrategy:
    execute(stim):
        features = full_cortical_parse(stim)
        memory = lookup_episodic(features)
        ctx = pfc_evaluate(features, memory)
        return ThreatDecision(level=ctx.threat, confidence=0.95, latency_ms=300)

class HybridStrategy implements ThreatDetectionStrategy:
    def __init__(self, low, high):
        self.low, self.high = low, high
    execute(stim):
        # Low first; if uncertain or high salience -> verify with high
        decision = self.low.execute(stim)
        if decision.level > 0.5:
            return self.high.execute(stim)
        return decision

class ThreatDetector (Context):
    private strategy: ThreatDetectionStrategy
    set_strategy(s): self.strategy = s
    detect(stim): return self.strategy.execute(stim)
```

### 3.2. Python — 3 ví dụ

Code chạy được ở `21_strategy.py`. Tóm tắt:

#### Ví dụ 1 — Vận hành thường: ThreatDetector với 3 Strategy

3 strategy với trade-off đo thực:
- **LowRoadStrategy**: pattern match keyword "snake_shape", "sudden_motion". Mock 12ms latency.
- **HighRoadStrategy**: full feature extraction + memory lookup + PFC evaluation. Mock 300ms latency.
- **HybridStrategy**: chạy low first; nếu kết quả uncertain → escalate sang high. Trade-off cân bằng.

Demo cùng input qua 3 strategy → kết quả khác nhau về (level, confidence, latency).

Đặc biệt thú vị: cho input mơ hồ (vật cong dài, có thể là rắn hoặc cây) — low road false-positive (báo threat dù không phải), high road đúng (không threat), hybrid escalate đúng pattern.

#### Ví dụ 2 — Hỏng / thiếu: 3 anti-patterns

- **2a — Hardcoded selection**: Context tự `if mode == "low" ... elif mode == "high"` thay vì DI strategy. Không testable, không plug-in.
- **2b — Mutable state shared between strategies**: 2 strategy ghi vào cùng counter → race condition + leak.
- **2c — Strategy with side effects**: strategy `execute()` ghi DB / send email. Phá tính idempotent + LSP. Sửa = strategy chỉ return data, Context xử lý side effect.

#### Ví dụ 3 — Ứng dụng Ellumm: LessonRecommendationEngine với 3 strategy

3 strategy thực tế cho recommendation:
- **PopularityStrategy**: trả lesson được học nhiều nhất. Đơn giản, baseline.
- **PersonalizedStrategy** (collaborative-filtering-lite): match user với "user tương tự" và recommend lesson mà họ thích. Cần history.
- **SkillGapStrategy**: phân tích quiz score thấp ở pattern nào → recommend lesson củng cố. Cần performance data.

Cùng `RecommendationEngine` Context, đổi strategy theo:
- **Cold start (user mới)**: PopularityStrategy.
- **Có history nhưng ít skill data**: PersonalizedStrategy.
- **Có nhiều quiz data**: SkillGapStrategy.

Đây là **adaptive selection** — Context có thể tự pick strategy dựa trên input. Đó cũng đúng cách não chọn low/high road theo context (urgency).

#### Ví dụ 4 — Functional alternative: closure as strategy

Khi strategy chỉ là 1 hàm pure → dùng closure thay class:
```python
sorter = lambda items: sorted(items, reverse=True)
detector = ThreatDetector(strategy=lambda stim: ThreatDecision(...))
```
Pythonic, ngắn, đủ dùng cho 80% case.

---

## SO SÁNH VỚI PATTERN KHÁC

| Pattern        | Khác biệt với Strategy                                                                  |
|----------------|------------------------------------------------------------------------------------------|
| **State**      | State đổi theo lifecycle (object tự); Strategy đổi theo client lựa chọn. Cấu trúc giống, intent khác. |
| **Template Method** | Template Method: inheritance + hook override. Strategy: composition + inject. Strategy linh hoạt runtime hơn. |
| **Decorator**  | Decorator bọc thêm hành vi cùng interface. Strategy thay thế hành vi. Decorator stack được; Strategy chọn 1. Có thể combine: Strategy bao quanh bởi Decorator middleware. |
| **Bridge**     | Bridge tách abstraction khỏi implementation (2 chiều orthogonal). Strategy chỉ tách 1 chiều. Bridge = "Strategy + Strategy". |
| **Command**    | Command đóng gói 1 lệnh cụ thể (có thể undo, queue). Strategy đóng gói 1 algorithm dùng nhiều lần. Khác về scope. |
| **Visitor**    | Visitor: 1 op qua N node type. Strategy: N algorithm cho 1 op. Đối xứng. |
| **Factory Method** | Factory tạo Strategy object. Hai pattern thường dùng cùng nhau (Factory để chọn Strategy theo config). |

> **Insight architect**: Strategy là pattern **xương sống của configurable systems**. Mọi feature flag, A/B test, plugin system, payment provider abstraction — đều là Strategy thực hiện trong production. Hiểu Strategy không chỉ là hiểu pattern — là hiểu cách build system có thể evolve mà không cần rewrite.

---

## ANTI-PATTERNS THƯỜNG GẶP

1. **Strategy có shared mutable state** — 2 strategy ghi vào cùng counter / cache.
   - Triệu chứng: race condition, kết quả phụ thuộc thứ tự gọi.
   - Xử lý: state per-strategy hoặc state ở Context. Strategy chỉ nhận input, return output. Không sửa gì ngoài.

2. **Strategy với side effects** — `execute()` gửi email, ghi DB.
   - Triệu chứng: không test được unit; replay = side effect lặp.
   - Xử lý: strategy return _intent_ (vd: `EmailIntent(to=..., body=...)`), Context xử lý side effect tách biệt. Functional core, imperative shell.

3. **Hardcoded strategy selection trong Context** — `if mode == "x" ... elif "y"`.
   - Triệu chứng: bypass DI hoàn toàn, defeat pattern.
   - Xử lý: inject Strategy qua constructor / setter. Selection logic ở Factory/builder ngoài.

4. **Strategy interface không truth-telling** — 1 strategy cần `Connection`, cái khác không.
   - Triệu chứng: try/cast inside, optional fields.
   - Xử lý: tách interface theo capability (ISP — interface segregation). Hoặc cùng interface, dependencies inject vào constructor strategy.

5. **Strategy explosion** — 50 strategies mỗi cái 3 dòng code.
   - Triệu chứng: namespace ngột ngạt, file nhiều hơn class chính.
   - Xử lý: dùng closure/function. `strategies = {"x": lambda i: ..., "y": lambda i: ...}`. Pythonic.

6. **Strategy giữ Context reference** — strategy có ref tới Context để truy cập field.
   - Triệu chứng: circular dependency, strategy không reuse được.
   - Xử lý: strategy nhận data cần qua input parameter. Context tự lấy field rồi truyền vào.

7. **Strategy với async/sync trộn lẫn** — 1 cái sync, 1 cái async; Context không biết.
   - Triệu chứng: `await strategy.execute()` đôi khi raise vì không phải coroutine.
   - Xử lý: chuẩn hoá interface — chọn 1 mode. Hoặc async wrapper (`asyncio.to_thread`) cho strategy sync.

---

## BÀI TẬP

1. **Cơ bản**: Thêm `EmotionPrimedStrategy` vào ThreatDetector — nếu user đang lo (high baseline cortisol), tăng salience bias để low road dominate (mô phỏng anxiety). Test cùng stimulus, 2 baseline khác nhau cho kết quả khác.

2. **Trung bình**: Refactor recommendation function 100 dòng có if/elif (`mode = "popular" / "personal" / "trending"`) thành Strategy + Strategy registry. Dùng decorator `@register("popular")` để auto-add vào registry. Test: thêm strategy mới chỉ cần thêm class với `@register`, không sửa engine.

3. **Khó (architect)**: Cài **CompositeStrategy** + voting:
   - Nhận N strategy, gọi tất cả parallel.
   - Aggregate: average, weighted, majority vote, max-confidence.
   - Có timeout: bỏ qua strategy chậm hơn ngưỡng.
   - Logging: ghi từng strategy thấy gì (debug).
   - Test: 3 strategy bất đồng → vote ra kết quả đúng.
   - Bonus: thêm async version với `asyncio.gather` + `asyncio.wait_for`.

4. **Mở rộng neuro**: Mô phỏng **PFC adaptive arbitration**. Tạo `AdaptiveDualRouteStrategy` chạy cả low + high song song. Output = low ngay (pre-emptive freeze), nhưng nếu high disagree (không phải threat thật) trong 300ms thì gửi suppress signal. Đây là analog của _initial freeze + relaxation_ khi nhận ra cây gậy không phải rắn. Code: dùng asyncio + Future cancellation. Đo độ trễ "thật giả" — kết quả gần với phenomenon thực: tim đập rồi mới hiểu.

   Bonus: simulate **fear extinction** — sau N lần false alarm cùng stimulus, weight của low road giảm cho stimulus đó. Đây là Pavlovian extinction được implement thành Strategy mutable theo lịch sử. Trong code, đó là _online learning_ trong strategy.

---

## PYTHON-NATIVE: callable, closure, functools.partial, Protocol

### Strategy = function (Pythonic mặc định)
```python
ThreatStrategy = Callable[[Stimulus], ThreatDecision]

low_road = lambda s: ThreatDecision(0.8, 0.4, 12) if has_curve(s) else ThreatDecision(0, 0.4, 12)
high_road = lambda s: full_cortical_parse(s)

class ThreatDetector:
    def __init__(self, strategy: ThreatStrategy):
        self.strategy = strategy
    def detect(self, s): return self.strategy(s)
```
Không cần class formal — function là first-class.

### `functools.partial` cho strategy có config
```python
import functools
sort_desc = functools.partial(sorted, reverse=True)
sort_by_score = functools.partial(sorted, key=lambda x: x.score)
```

### Protocol cho type-safety
```python
from typing import Protocol

class ThreatStrategy(Protocol):
    def __call__(self, stim: Stimulus) -> ThreatDecision: ...

# Cả class lẫn function đều satisfy protocol
```

### Khi nào vẫn cần class Strategy?
- Strategy có **state per-instance** (model ML đã train).
- Strategy có **lifecycle** (init resource, close).
- Strategy có **multi-method API** (predict + explain + log).
- Cần **inheritance** (hierarchy strategy).

> Quy tắc architect: function strategy cho 80% case. Class strategy khi có lifecycle/state/multi-method. Chuyển từ function sang class chỉ khi cần — đừng over-engineer.

---

## CHECKLIST TRƯỚC KHI MERGE PR DÙNG STRATEGY

- [ ] Có thực sự **nhiều algorithm** với trade-off rõ ràng không?
- [ ] Strategy có thực sự **interchangeable** ở mọi call site (LSP)?
- [ ] Strategy có **stateless / immutable** không (concurrency-safe)?
- [ ] Strategy có **không có side effect** (pure function nếu được)?
- [ ] Có **inject Strategy qua constructor** (DI), không hardcode trong Context?
- [ ] Strategy quá ngắn → đã cân nhắc **closure/function** chưa?
- [ ] Có **registry** hoặc **factory** để chọn strategy theo config?
- [ ] Test strategy **riêng lẻ** không cần Context được không?
- [ ] Async vs sync đã quyết rõ, có timeout cho async strategy?
- [ ] Có **observability** (log strategy được dùng + latency + outcome)?

---

## TÓM LẠI BẰNG NEUROSCIENCE

> LeDoux đã mô tả một sự thật hoá thiết kế đẹp đẽ: cùng một câu hỏi "có phải threat không?", não tiến hoá ra **hai algorithm độc lập** — fast/crude và slow/accurate — chạy song song qua hai đường dẫn. Đây là Strategy pattern ở quy mô tiến hoá: cùng interface, cùng goal, hai implementation với trade-off khác nhau, có thể chọn theo context.

> Khi bạn thoáng thấy "vật cong dài" và nhảy lùi, rồi 200ms sau nhận ra là cây gậy → bạn vừa trải nghiệm Strategy pattern thật. Low road đã execute trước (fight/flight), high road execute sau (correction). PFC arbitrate, suppress amygdala. Đó cũng đúng là thiết kế production của một CompositeStrategy: chạy strategy nhanh trước cho responsive, strategy chậm cho đúng đắn, có override mechanism khi mâu thuẫn.

> Architect học Strategy là để biết: khi nào pattern thực sự cần thiết (nhiều algorithm trade-off rõ), khi nào nên dùng closure thay class (Pythonic, 80% case), khi nào kết hợp Strategy + State (state machine với behavior per-stage), khi nào dùng Strategy + Decorator (middleware chain), và khi nào nên cảnh giác (strategy có side effect, mutable state shared, hardcoded selection). Đây là pattern của configurable systems — tất cả feature flag, A/B test, plugin, payment provider đều là Strategy ngầm.

> Não dạy thêm một insight: **Strategy không cần singular**. Não chạy cả low + high road song song, không bao giờ "chọn 1". Production code khôn ngoan cũng vậy — _ensemble_ strategy (chạy nhiều, vote) thường mạnh hơn _switch_ strategy (chọn 1). Đó là cốt lõi của ML model ensemble, là cách Stripe + PayPal cùng được dùng cho retry, là lý do bạn không bao giờ trust một anti-fraud algorithm duy nhất.

Lesson kế tiếp đề xuất: **22 — Template Method (LTP protocol)** — pattern skeleton + hook, đối xứng với Strategy nhưng dùng inheritance. LTP (long-term potentiation) ở synapse là analog đẹp: cùng skeleton (NMDA → Ca²⁺ → kinase cascade → AMPA insertion), nhưng từng synapse có "hook" riêng tinh chỉnh.
