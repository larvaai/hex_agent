# Lesson 12 — Proxy (Đại diện / Người gác cổng)

> **Một câu chốt:** *Proxy đứng cùng interface với RealSubject để **chèn logic** (auth, cache, lazy load, log, remote) **giữa client và real subject**, mà client KHÔNG biết mình đang nói chuyện với proxy.*

---

## I. Bản đồ nhanh

| Khía cạnh | Proxy |
|---|---|
| **Loại** | Structural |
| **Vấn đề giải quyết** | Cần kiểm soát/can thiệp truy cập đến object thật mà không sửa client |
| **Nguyên lý cốt lõi** | Cùng interface với RealSubject + chèn cross-cutting logic |
| **Anti-pattern thay thế** | Client tự kiểm tra auth/cache/load → vi phạm SRP, lan tỏa logic |
| **Ví dụ neuroscience** | Blood-Brain Barrier (BBB) — gateway giữa máu và neuron |
| **Họ hàng dễ nhầm** | Decorator (cùng interface + thêm tính năng) — khác intent: Decorator *enhance*, Proxy *control* |

---

## II. Three-Level Presentation

### Level 1 — Concept (Vì sao cần Proxy?)

**Tình huống đời thật trong não:**

Não cần **glucose, oxygen, amino acid** từ máu để sống. Nhưng máu cũng chứa **độc tố, mầm bệnh, kháng thể, hormone không phù hợp**. Nếu để máu tiếp xúc trực tiếp với neuron → não chết trong vài phút.

**Giải pháp tự nhiên:** Blood-Brain Barrier (BBB) — một lớp tế bào nội mô (endothelial cells) với **tight junction** + được bao bọc bởi **astrocyte end-feet**. BBB:

1. **Lọc theo tính chất phân tử:** chỉ cho qua chất tan trong lipid (O₂, CO₂, ethanol) hoặc có **transporter chuyên biệt** (GLUT1 cho glucose, LAT1 cho amino acid).
2. **Chặn kích thước lớn:** kháng thể, vi khuẩn, hồng cầu — không qua được.
3. **Active transport:** một số chất bị bơm ngược ra (P-glycoprotein đẩy thuốc ra khỏi não).
4. **Lazy loading:** không phải lúc nào cũng giao glucose — chỉ khi neuron cần (qua signal từ astrocyte).
5. **Logging/monitoring:** vi mạch + astrocyte phát hiện viêm → điều chỉnh permeability.

**Đối với neuron**, BBB **trong suốt**: neuron yêu cầu glucose → "có glucose đến". Neuron KHÔNG biết có lớp BBB ở giữa, KHÔNG cần code logic kiểm tra "đây có phải glucose thật không, có lẫn độc tố không".

→ **Đây chính là Proxy pattern.** Neuron = client. Brain (real subject) cần substrate. BBB = proxy đứng giữa, cùng interface (đều "cung cấp substrate"), nhưng chèn logic kiểm soát.

> **Insight architect:** Proxy là cách **đặt cross-cutting concerns (auth, cache, throttle, log, lazy) ở đúng layer biên** — client không bị ô nhiễm, real subject không bị ô nhiễm, logic kiểm soát ở giữa.

---

### Level 2 — Algorithm (Cấu trúc & 5 Chiều)

```
   [Client]
      |
      | calls subject.request()
      v
   [Subject Interface]
      ^                    ^
      |                    |
      |                    |
[RealSubject]         [Proxy]
   request()           request():
                          1. pre-check (auth/cache/log)
                          2. delegate → real_subject.request()
                          3. post-process (cache write/log)
                          4. return result
```

**4 biến thể chính của Proxy (theo GoF):**

| Loại | Mục đích | Ví dụ |
|---|---|---|
| **Virtual Proxy** | Lazy load object đắt | Hình ảnh chỉ load khi scroll tới |
| **Protection Proxy** | Kiểm soát quyền truy cập | BBB chặn độc tố / RBAC trên service |
| **Remote Proxy** | Đại diện cho object ở process/máy khác | RPC stub, gRPC client |
| **Smart Reference** | Thêm hành vi khi access | Reference counting, lazy init, copy-on-write |

**5 Chiều:**

1. **Composition:**
   - `Subject` (interface): contract chung.
   - `RealSubject`: implementation thật, "naive" — không biết về proxy.
   - `Proxy`: implement Subject, **giữ reference** đến RealSubject (hoặc lazy create).
   - `Client`: chỉ biết Subject — không biết đang gọi proxy hay real.

2. **Location (Vị trí):**
   - **Boundary layer** — biên giữa client và real subject.
   - Thường ở: API gateway, BBB, ORM lazy loader, image proxy server, gRPC stub.

3. **Function:**
   - Tách cross-cutting concerns ra khỏi business logic.
   - Cho phép swap RealSubject → MockProxy trong testing.
   - Cho phép thêm/bỏ proxy mà client không biết (transparent).

4. **Connections:**
   - **Decorator** giống cấu trúc nhưng khác intent (Decorator add behavior, Proxy controls access).
   - **Adapter** khác interface; Proxy CÙNG interface với RealSubject.
   - **Facade** khác: Facade đơn giản hóa subsystem, Proxy không đơn giản hóa mà control access.
   - **Chain of Responsibility** có thể implement bằng chain of Proxy.

5. **Meaning:**
   - Tách **identity** (real subject) ra khỏi **access control** (proxy).
   - Cho phép thêm tầng kiểm soát mà không vi phạm Open-Closed.

**Pseudocode:**

```
interface Subject:
    request() -> Response

class RealSubject implements Subject:
    request():
        # business logic thật
        return data

class ProtectionProxy implements Subject:
    constructor(real, user):
        self.real = real
        self.user = user
    request():
        if not user.has_permission():
            raise Unauthorized
        return self.real.request()

class CacheProxy implements Subject:
    cache = {}
    constructor(real):
        self.real = real
    request():
        if key in cache: return cache[key]
        result = self.real.request()
        cache[key] = result
        return result

# Stack proxy:
service = ProtectionProxy(CacheProxy(RealSubject()), user)
```

---

### Level 3 — Implementation

#### A. Anti-pattern: Client tự kiểm tra mọi thứ

```python
class Neuron:
    def need_glucose(self, blood):
        # ❌ Neuron tự lo: lọc độc, kiểm tra antibody, transport
        if 'toxin' in blood:
            blood = filter_toxin(blood)
        if 'antibody' in blood:
            blood = remove_antibody(blood)
        if not has_glucose_transporter(blood):
            return None
        return blood['glucose']
```

**Vấn đề:** mỗi neuron đều phải biết về độc, antibody, transporter → 86 tỷ neuron × cùng logic = vi phạm SRP, không scale.

#### B. Pattern đúng: BBBProxy

```python
class IBrainSubstrate(Protocol):
    def request_glucose(self) -> float: ...
    def request_oxygen(self) -> float: ...

class Vasculature(IBrainSubstrate):  # RealSubject
    def request_glucose(self): return self._draw_from_blood('glucose')
    ...

class BBBProxy(IBrainSubstrate):
    def __init__(self, real, astrocyte_signal):
        self.real = real
        self.astrocyte = astrocyte_signal
    def request_glucose(self):
        if not self.astrocyte.demand_high():
            return 0  # lazy: không giao nếu không cần
        if self._detect_inflammation():
            self._tighten_permeability()
        raw = self.real.request_glucose()
        return self._filter_toxins(raw)
```

Neuron chỉ gọi `substrate.request_glucose()` — không biết BBB.

#### C. Stacked Proxy (combo nhiều layer)

```python
service = AuthProxy(LogProxy(CacheProxy(RealService())))
```

Mỗi layer xử lý 1 concern. Order quan trọng (như Decorator).

#### D. Ellumm Application

`MemoryStore` (real) chỉ biết đọc/ghi episode. Stack proxy:
1. `AuthProxy`: kiểm tra user permission.
2. `RateLimitProxy`: chặn flood.
3. `CacheProxy`: cache recall recent.
4. `LazyLoadProxy`: chỉ load embedding khi cần.

---

## III. Failure Cases

### Sinh học: BBB Breakdown

Khi BBB hỏng (multiple sclerosis, stroke, traumatic brain injury, glioma):
- Antibody, fibrinogen, T cell xâm nhập → viêm não
- Demyelination (xem Lesson 09)
- Kháng thể tự miễn → tấn công myelin (MS) hoặc receptor (anti-NMDA receptor encephalitis)

**Bài học:** Proxy hỏng = real subject bị tấn công trực tiếp.

### Code: "Bypass the proxy"

```python
class Service:
    def __init__(self):
        self.real = RealService()
        self.proxy = AuthProxy(self.real)
    def public_api(self, req): return self.proxy.handle(req)
    def internal_call(self, req): return self.real.handle(req)  # ❌ bypass

# Attacker tìm internal_call → bypass auth
```

**Bug đặc trưng:** Để **một** đường truy cập trực tiếp đến RealSubject = vô hiệu hóa Proxy. Phải đảm bảo MỌI access đi qua proxy (encapsulation).

### Code: Lazy proxy gây N+1 query

```python
class LazyProxy:
    def get_data(self):
        if not self._loaded:
            self._data = expensive_load()  # query DB
            self._loaded = True
        return self._data

# Loop:
for user in users:
    print(user.profile.bio)  # Mỗi iteration trigger 1 query
```

**Bài học:** Lazy proxy + loop = N+1 query disaster. Cần batch loading (DataLoader pattern).

---

## IV. So sánh Decorator vs Proxy vs Adapter

| Pattern | Cùng interface? | Intent | Có biết về wrapped object? |
|---|---|---|---|
| **Adapter** | KHÁC | Convert interface | Có (translate) |
| **Decorator** | CÙNG | Add behavior dynamically | Có (delegate + add) |
| **Proxy** | CÙNG | Control access | Có (gate-keep) |
| **Facade** | KHÁC | Simplify subsystem | Có (orchestrate) |

> **Bẫy:** Decorator và Proxy giống về CẤU TRÚC. Khác về **INTENT**: code review có thể dùng cả hai cấu trúc giống nhau, nhưng đặt tên class theo intent (ImageDecorator vs ImageProxy) giúp đọc.

---

## V. Self-test (5 câu)

1. **Vì sao BBB là Proxy chứ không phải Adapter?**
   *(Hint: interface có thay đổi không?)*

2. **Phân biệt Virtual Proxy và Cache Proxy.**

3. **Khi nào dùng Proxy thay vì Decorator?**

4. **Tại sao "bypass proxy" là vulnerability nghiêm trọng — ví dụ trong API gateway?**

5. **Cho code:**
   ```python
   class LazyImage:
       def render(self):
           if not self.loaded: self._load()
           return self.pixels
   ```
   *Hỏi: Đây là Virtual Proxy hay không? Có thể cải thiện thế nào để client thực sự không biết về lazy?*

---

## VI. Tóm tắt cho architect

> *"Proxy là interface ở biên giới. Khi bạn thấy cross-cutting concern (auth, cache, log, throttle, retry, lazy load) — đừng nhét vào client hoặc real subject. Đặt Proxy giữa. Mỗi proxy 1 concern. Stack chúng lại. Test mỗi proxy độc lập."*

**Checklist:**
- [ ] Proxy có cùng interface với RealSubject?
- [ ] Mỗi proxy chỉ làm 1 concern (SRP)?
- [ ] Có đảm bảo MỌI access đều đi qua proxy (không có bypass route)?
- [ ] Order các proxy hợp lý (auth trước cache, log ngoài cùng)?
- [ ] Có metric/log để biết proxy hoạt động (cache hit rate, auth deny count)?

---

**Tiếp theo: Lesson 13 — Chain of Responsibility** (chuỗi xử lý reflex pathway: nociceptor → spinal cord → thalamus → cortex; mỗi tầng quyết định xử lý hoặc forward).
