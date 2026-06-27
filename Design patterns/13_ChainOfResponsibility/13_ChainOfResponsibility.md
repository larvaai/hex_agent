# Lesson 13 — Chain of Responsibility (Chuỗi trách nhiệm)

> **Một câu chốt:** *Một request đi qua một chuỗi handler; mỗi handler có quyền **handle** (kết thúc), **forward** (chuyển tiếp), hoặc **modulate + forward** — sender KHÔNG biết handler nào sẽ xử lý.*

---

## I. Bản đồ nhanh

| Khía cạnh | Chain of Responsibility (CoR) |
|---|---|
| **Loại** | Behavioral |
| **Vấn đề giải quyết** | Decouple sender khỏi receiver khi có nhiều handler tiềm năng |
| **Nguyên lý cốt lõi** | Mỗi handler tự quyết định: handle / forward / modulate |
| **Anti-pattern thay thế** | Switch-case khổng lồ trong client; if/elif chuỗi 20 nhánh |
| **Ví dụ neuroscience** | Pain pathway: nociceptor → spinal cord → brainstem → thalamus → S1/ACC/Insula |
| **Họ hàng dễ nhầm** | Decorator (cùng cấu trúc), Pipeline (forward 100% không quyết định), Mediator (1 trung tâm) |

---

## II. Three-Level Presentation

### Level 1 — Concept (Vì sao cần CoR?)

**Tình huống đời thật trong não — đường truyền cảm giác đau:**

Bạn chạm tay vào lò nóng. Tín hiệu đi qua **một chuỗi tầng**, mỗi tầng có quyền can thiệp khác nhau:

```
[Nociceptor (da)]              ← phát hiện noxious stimulus, sinh action potential
       |
       v
[Dorsal Horn (tủy sống)]       ← TẦNG 1: có thể TRIGGER REFLEX (rút tay) trước khi não biết
       |                          → handle local (~30ms), nhưng VẪN forward lên trên
       v
[Brainstem (PAG, RVM)]         ← TẦNG 2: có thể MODULATE — descending inhibition
       |                          (giảm pain bằng endorphin nội sinh, "không đau bằng lúc bị thương trong chiến đấu")
       v
[Thalamus (VPL)]               ← TẦNG 3: relay tới cortex
       |
       +---→ [S1 cortex]       ← TẦNG 4a: discriminative — "đau ở vị trí nào, sắc/âm ỉ"
       +---→ [ACC]             ← TẦNG 4b: affective — "khó chịu, sợ, ghét"
       +---→ [Insula]          ← TẦNG 4c: interoceptive — "cảm nhận trên cơ thể mình"
```

**Quan sát quan trọng:**

1. **Sender (nociceptor) không biết** ai sẽ xử lý. Nó chỉ "fire and forget".
2. **Mỗi tầng quyết định độc lập:**
   - Tủy sống: "Cái này nóng quá, tôi rút tay TRƯỚC, không đợi cortex" (reflex).
   - Brainstem: "Đang chiến đấu, ưu tiên sinh tồn, giảm pain signal."
   - Thalamus: "Forward, không xử lý nội dung."
   - Cortex: "Đây là pain ở ngón tay, sắc, từ lò nóng → ghi nhớ."
3. **Có thể có signal bị STOPPED ở giữa chuỗi** (gate control theory: Aβ-fiber kích hoạt → tủy đóng cổng pain).
4. **Có thể MODULATE rồi forward** (giảm cường độ rồi đẩy lên).

> **Insight architect:** CoR là pattern cho **policy-based dispatch** + **early termination** + **chain of filters**. Không phải pipeline (pipeline forward mọi thứ); CoR cho phép **dừng chuỗi ở bất kỳ tầng nào**.

---

### Level 2 — Algorithm (Cấu trúc & 5 Chiều)

```
[Client]
   |
   | request
   v
[Handler A] ── handle? ──→ YES → return result, STOP
   |                       
   | NO/PARTIAL — forward (có thể modulate)
   v
[Handler B] ── handle? ──→ YES → return result, STOP
   |
   v
[Handler C] ── handle? ──→ YES → return result, STOP
   |
   v
[None / fallback]
```

**5 Chiều:**

1. **Composition:**
   - `Handler` (interface): `handle(request) → Optional[Result]`, `set_next(handler)`.
   - `BaseHandler`: implement `set_next` + skeleton `handle` (gọi `next.handle` nếu chưa xong).
   - `ConcreteHandler`: override `handle` — quyết định handle/forward/modulate.
   - `Client`: build chain (Handler1.set_next(Handler2).set_next(...)) rồi gọi `Handler1.handle(req)`.

2. **Location:**
   - Middleware HTTP (Express, ASP.NET, Django middleware).
   - Event handler (DOM bubbling), exception propagation, GUI tool tip resolution.
   - Logging level filters.
   - Approval workflow (manager → director → VP → CEO theo amount).

3. **Function:**
   - Decouple sender ↔ receiver.
   - Cho phép **runtime configuration** của chain (thêm/bỏ handler).
   - Mỗi handler có **single responsibility**.

4. **Connections:**
   - **Decorator** giống cấu trúc (wrap object), nhưng Decorator add behavior cho MỌI call; CoR chỉ chọn 1 handler.
   - **Pipeline / Pipes & Filters**: pipeline luôn forward, CoR có thể dừng.
   - **Strategy**: Strategy chọn 1 algorithm tại 1 điểm; CoR chọn handler dọc 1 chuỗi.
   - **Mediator**: Mediator có 1 coordinator trung tâm; CoR phân tán.

5. **Meaning:**
   - Embodies **"don't tell me how, ask my chain"** — sender thả request, chain xử.
   - Hỗ trợ **policy layering** — quyền cao xử lý sau cùng.

**Pseudocode:**

```
class Handler:
    next = None
    def set_next(h):
        self.next = h
        return h  # ← cho phép chain fluent: a.set_next(b).set_next(c)
    def handle(req):
        if can_handle(req): return process(req)
        if next: return next.handle(req)
        return None  # fallback

# Build chain
chain = SpinalReflex()
chain.set_next(BrainstemModulator()).set_next(ThalamicRelay()).set_next(CorticalProcessor())

# Use
result = chain.handle(pain_signal)
```

---

### Level 3 — Implementation

#### A. Anti-pattern: Mega switch-case

```python
def handle_pain(signal):
    # ❌ Tất cả logic trong 1 hàm — vi phạm SRP, khó test, khó extend
    if signal.intensity > 9 and signal.source == 'spinal':
        return spinal_reflex(signal)
    elif signal.intensity > 7 and combat_mode_active():
        return brainstem_inhibit(signal)
    elif ...
```

#### B. Pattern đúng

```python
class PainHandler(ABC):
    def __init__(self): self._next = None
    def set_next(self, h):
        self._next = h
        return h
    def handle(self, sig):
        result = self._handle(sig)
        if result.terminated: return result
        if self._next: return self._next.handle(result.signal)
        return result
    @abstractmethod
    def _handle(self, sig): ...

class SpinalReflex(PainHandler):
    def _handle(self, sig):
        if sig.intensity > 9 and sig.fiber_type == 'A_delta':
            sig.reflex_triggered = True  # rút tay
        return Outcome(signal=sig, terminated=False)  # vẫn forward để não biết

class BrainstemModulator(PainHandler):
    def _handle(self, sig):
        if combat_mode():
            sig.intensity *= 0.3  # descending inhibition
        return Outcome(signal=sig, terminated=False)

class GateControl(PainHandler):
    def _handle(self, sig):
        if sig.A_beta_active:  # touch input gates pain
            return Outcome(signal=sig, terminated=True)  # STOP
        return Outcome(signal=sig, terminated=False)
```

#### C. Demo extension (Open-Closed)

Thêm handler mới (e.g., `OpioidGate` cho thuốc giảm đau): không sửa client, chỉ insert vào chain.

#### D. Ellumm Application

Stimulus processing chain trong Ellumm:
```
SensoryInput → NoveltyFilter → EmotionalSalience → SemanticParser → MemoryEncoder → ActionPlanner
```
Mỗi handler quyết định: "đáng quan tâm? → forward; không → drop". Tiết kiệm CPU, mimic não thật.

---

## III. Failure Cases

### Sinh học: Phantom limb pain

Sau cắt cụt chi: nociceptor không còn, nhưng các tầng sau vẫn "fire" do **central sensitization** — handler trong chain "tự tạo" signal mà không có input. Bệnh nhân **thấy đau ở chân không tồn tại**.

**Bài học:** CoR có thể có handler stateful → nếu handler "memorize" signal sai, sẽ trigger sai mãi. Stateful handler = nguy hiểm, cần reset cơ chế.

### Sinh học: CIPA (Congenital Insensitivity to Pain with Anhidrosis)

Mutation gene SCN9A → nociceptor không generate Na⁺ current → **chuỗi không bao giờ start**. Bệnh nhân không cảm thấy đau, dễ bị thương nặng mà không biết.

**Bài học:** Nếu sender chết, chain vô dụng. Cần monitoring: "Có request nào đi vào chain không?"

### Code: Quên forward → request bị nuốt

```python
class BadHandler(PainHandler):
    def _handle(self, sig):
        if sig.intensity < 5:
            return  # ❌ return None, không Outcome → terminate vô tình
```

**Bug đặc trưng:** Handler không gọi `next.handle` và không trả về Outcome rõ ràng → request "rơi vào hư vô". Phải định nghĩa CONTRACT: `_handle` luôn trả Outcome.

### Code: Chain tuần hoàn (cycle)

```python
a.set_next(b)
b.set_next(c)
c.set_next(a)  # ❌ vòng lặp
chain.handle(req)  # → infinite recursion → stack overflow
```

**Bài học:** Chain phải acyclic. Validate khi build chain.

### Code: Performance — chain quá dài

Chuỗi 50 handler, request đi hết tới fallback → 50 lần dispatch. Trong não, pain pathway chỉ ~5-7 tầng. Giữ chain ngắn hoặc dùng lookup table thay CoR khi N lớn.

---

## IV. So sánh

| Pattern | Có forward? | Chỉ 1 handler? | Có trung tâm? |
|---|---|---|---|
| **Chain of Responsibility** | Có (tùy ý) | 1 hoặc nhiều | Không |
| **Decorator** | Luôn forward | Tất cả handle | Không |
| **Pipeline** | Luôn forward | Tất cả xử lý sequential | Không |
| **Strategy** | Không forward | 1 (đã chọn trước) | Không |
| **Mediator** | Không forward | Mediator routes | Có |

---

## V. Self-test (5 câu)

1. **Tại sao spinal reflex là CoR chứ không phải Strategy?** *(Hint: ai quyết định, khi nào)*

2. **Phân biệt CoR và Pipeline với ví dụ middleware HTTP:** Auth middleware có thể trả 401 trước khi vào logic — đó là CoR hay Pipeline?

3. **Cho 5 handler trong chain. Handler #3 luôn modulate signal × 0.5 nhưng không terminate. Handler #4 chỉ handle khi intensity > 5. Khi intensity gốc = 8, có vào handler #4 không?** Trace.

4. **Vì sao stateful handler trong CoR nguy hiểm? Cho ví dụ phantom limb.**

5. **Khi nào nên thay CoR bằng dict lookup `{type: handler}`?** *(Hint: khi nào quyết định không phụ thuộc thứ tự?)*

---

## VI. Tóm tắt cho architect

> *"CoR khi bạn cần policy layering với khả năng early-exit. Pipeline khi mọi tầng phải chạy. Strategy khi chỉ chọn 1 lần. Mediator khi nhiều bên cần phối hợp. Đừng dùng CoR cho dispatch lookup — dict nhanh hơn và rõ hơn."*

**Checklist:**
- [ ] Chain acyclic?
- [ ] Mỗi handler có contract rõ ràng (luôn trả Outcome)?
- [ ] Có fallback khi không handler nào handle?
- [ ] Có log/metric: request đi qua handler nào, dừng ở đâu?
- [ ] Chain có thể config runtime (add/remove handler)?
- [ ] Stateful handler có reset mechanism?

---

**Tiếp theo: Lesson 14 — Command** (motor program / action plan: encapsulate hành động thành object, đẩy vào queue để thực thi/undo/replay — như supplementary motor area lập kế hoạch trước khi M1 thực hiện).
