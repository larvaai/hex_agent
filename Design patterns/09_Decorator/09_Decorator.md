# Lesson 09 — Decorator

> **Bọc object bằng một wrapper cùng interface để thêm hành vi runtime, không cần subclass.**

---

## Mức 1 — CONCEPT (Ý tưởng)

### Vấn đề pattern giải quyết

Bạn có một service cốt lõi (vd: `AxonSignal.transmit()`) và muốn thêm các tính năng "cross-cutting":
- Tăng tốc dẫn truyền
- Ghi log mọi lần transmit
- Cache kết quả
- Validate signal trước khi gửi
- Đo latency
- Retry khi fail

**Cách inheritance** (anti-pattern):

```python
# ❌ 2^N subclass cho N feature → bùng nổ kinh hoàng
class AxonSignal: ...
class FastAxonSignal(AxonSignal): ...
class LoggingAxonSignal(AxonSignal): ...
class FastLoggingAxonSignal(FastAxonSignal, LoggingAxonSignal): ...
class FastLoggingCachingAxonSignal(...): ...
class FastLoggingCachingValidatingAxonSignal(...): ...
# 6 feature → cần 64 class cho mọi tổ hợp
# Diamond problem multiple inheritance
# Order không kiểm soát được (FastLogging vs LoggingFast)
```

**Cách Decorator**:

```python
# ✓ Mỗi feature 1 class. Stack runtime.
signal = AxonSignal()
signal = MyelinSheath(signal)              # tăng tốc x100
signal = LoggingDecorator(signal)          # log
signal = CachingDecorator(signal)          # cache
# 6 feature → 6 class, stack tự do, đổi thứ tự dễ
```

Mọi decorator implement cùng interface với component bị wrap → client không phân biệt được. Có thể stack vô hạn, swap runtime, đổi thứ tự bằng cách đảo composition.

### Neuroscience analogy — Myelin Sheath

Axon là "kênh dẫn signal cốt lõi" của neuron. Một axon trần (bare axon) đã đủ truyền tín hiệu — neurotransmitter ra đúng terminal, đúng pattern, đúng neuron đích. Nhưng khoảng 50% axon ở não con người được **bọc myelin** — cấu trúc lipid quấn quanh axon do oligodendrocyte (CNS) hoặc Schwann cell (PNS) tạo ra.

Hiệu quả của myelin sheath:

| Thuộc tính | Axon trần | Axon myelinated |
|------------|-----------|-----------------|
| Tốc độ dẫn truyền | 0.5–2 m/s | 50–120 m/s (nhanh hơn 50-100×) |
| Cơ chế | Continuous AP propagation | Saltatory conduction (nhảy giữa Nodes of Ranvier) |
| Năng lượng | Cao (ion channel active mọi nơi) | Thấp (chỉ active ở node) |
| Đường kính cần thiết | Phải lớn để bù tốc độ | Nhỏ hơn cho cùng tốc độ |
| Signal preservation | Suy giảm dần | Bảo toàn ở khoảng cách dài |

**Quan sát kiến trúc quan trọng**: myelin **không thay đổi signal**. Cùng AP firing pattern, cùng neurotransmitter, cùng target. Myelin chỉ "wrap" axon và thêm tốc độ + efficiency. Tương đương với client gọi `axon.transmit(signal)` — kết quả vẫn đúng signal đó, chỉ nhanh hơn.

Ngoài myelin, có nhiều "decorator sinh học" khác wrap neuron/axon:

| Decorator sinh học | Wraps cái gì | Thêm chức năng gì |
|---------------------|--------------|-------------------|
| **Myelin sheath** | Axon | Tăng tốc dẫn truyền (saltatory) |
| **Perineuronal nets (PNN)** | Cell body + dendrite | Stabilize synapse, hạn chế plasticity (lock learning state) |
| **Glial ensheathment** | Synapse | K+ buffering, glutamate uptake |
| **Tripartite synapse** | Pre-post synapse | Astrocyte modulation thêm vào |

Tất cả các "wrap" này đều có 2 đặc điểm Decorator pattern:
1. Không thay thế component cốt lõi (axon vẫn là axon).
2. Thêm hành vi mới mà client (cell đích) không cần biết.

### Decorator vs các pattern liên quan

| | Decorator | Adapter (06) | Proxy (12) | Composite (08) |
|---|-----------|--------------|------------|-----------------|
| Mục đích | Thêm hành vi | Đổi interface | Kiểm soát truy cập | Tổ chức cây |
| Interface | Giữ nguyên | Khác | Giữ nguyên | Giữ nguyên |
| Số object wrap | 1 (chain được) | 1 | 1 | N children |
| Quan hệ | "is-a" + "has-a" | "has-a" (composition) | "has-a" + auth/lazy | "is-a" + "has-a" children |

Note: Decorator và Composite đều là "is-a + has-a" — đó là lý do Decorator có thể tham gia vào Composite tree (wrap node trong tree).

---

## Mức 2 — ALGORITHM (Thuật toán)

### Cấu tạo (5 chiều theo framework Ellumm)

| Chiều | Nội dung |
|-------|----------|
| **Cấu tạo** | (a) `Component` interface, (b) `ConcreteComponent` (cốt lõi), (c) `Decorator` abstract (wraps Component, implements Component), (d) `ConcreteDecorator` thêm hành vi cụ thể |
| **Vị trí** | Tầng infrastructure / cross-cutting concerns. Domain core không nên biết về Decorator. |
| **Chức năng** | Add behavior runtime, không sửa Component, stackable. |
| **Kết nối** | Client → outermost Decorator → ... → innermost Decorator → ConcreteComponent. |
| **Ý nghĩa** | Cross-cutting concerns (logging, caching, timing, auth, retry, validation) được tách khỏi business logic. |

### Sơ đồ class

```
       ┌─────────────────────┐
       │     Component       │
       │   abstract          │
       │ + transmit(signal)  │
       └──────────┬──────────┘
                  △
        ┌─────────┴─────────┐
        │                   │
  ┌─────┴────────┐    ┌─────┴────────┐
  │ConcreteComp  │    │   Decorator  │  ← cũng implements Component!
  │   (Axon)     │    │ - inner: Comp│  has-a
  │+ transmit(s) │    │+ transmit(s) │     ──────────────►  Component
  └──────────────┘    └──────┬───────┘                          ▲
                             △                                  │ delegate
              ┌──────────────┼──────────────┐                    │
              │              │              │                    │
       ┌──────┴──────┐ ┌─────┴─────┐ ┌──────┴───────┐            │
       │MyelinSheath │ │LogDecorator│ │CacheDecorator│  ─────────┘
       └─────────────┘ └────────────┘ └──────────────┘
```

### Logic vận hành — chain delegation

```
Setup (build chain từ trong ra ngoài):
    bare = Axon()
    fast = MyelinSheath(bare)              ← myelin wrap bare
    logged = LoggingDecorator(fast)         ← log wrap myelinated
    cached = CachingDecorator(logged)       ← cache wrap logged

Client gọi:
    cached.transmit(signal)
        │
        ▼
    CachingDecorator.transmit(signal):
        if signal in cache: return cache[signal]
        result = self._inner.transmit(signal)        ← delegate
                    │
                    ▼
                LoggingDecorator.transmit(signal):
                    log("transmitting", signal)
                    result = self._inner.transmit(signal)    ← delegate
                                │
                                ▼
                            MyelinSheath.transmit(signal):
                                start_time = now()
                                result = self._inner.transmit(signal)  ← delegate
                                            │
                                            ▼
                                        Axon.transmit(signal):
                                            return propagate(signal)
                                speed_up_factor = 100
                                return result with reduced latency
                    log("transmitted in", elapsed)
                    return result
        cache[signal] = result
        return result
```

Mỗi decorator có thể chèn hành vi **trước** hoặc **sau** delegation. Cú pháp Python `@decorator` (function decorator) là biến thể đơn giản của pattern này.

### Vấn đề thứ tự — quan trọng

Stack thứ tự **rất quan trọng**:

```python
# A: log THẤY cache hit
LoggingDecorator(CachingDecorator(Axon()))

# B: log CHỈ THẤY cache miss (vì cache wrap log từ ngoài)
CachingDecorator(LoggingDecorator(Axon()))
```

Sai thứ tự = sai semantic. Architect phải hiểu rõ thứ tự khi design chain. Quy ước phổ biến:
- Outermost = sớm nhất "gặp" call (auth, rate-limit, cache).
- Innermost = gần component nhất (timing, retry).

Trong sinh học, thứ tự cũng quan trọng: myelin nằm trong perineuronal net → nếu PNN bị remove (vd: dùng chondroitinase ABC), neuron mới có thể remyelinate; nếu myelin bị remove trước (MS), PNN không bù được tốc độ.

### Transparent decoration — interface giữ nguyên

```python
def use_signal(component: Component):
    component.transmit(signal)        # không quan tâm có bao nhiêu decorator wrap
```

Client không phân biệt được component bare vs decorated. Đây là sức mạnh của Liskov Substitution: decorated luôn substitute cho non-decorated.

### Nguyên lý liên quan

- **Open-Closed**: thêm decorator mới = thêm class mới, không sửa Component.
- **Single Responsibility**: mỗi decorator chỉ chịu trách nhiệm 1 cross-cutting concern.
- **Liskov Substitution**: decorated component substitute cho non-decorated transparent với client.
- **Composition over inheritance**: cốt lõi của Decorator.

---

## Mức 3 — PSEUDOCODE + PYTHON

### Pseudocode

```
abstract class Component:
    abstract function transmit(signal: Signal) -> Result

class Axon extends Component:                          # ConcreteComponent
    function transmit(signal):
        return propagate_along(signal, speed=1.0 m/s)

abstract class Decorator extends Component:
    field _inner: Component

    constructor(inner: Component):
        self._inner = inner

class MyelinSheath extends Decorator:
    function transmit(signal):
        result = self._inner.transmit(signal)
        result.speed *= 100                            # saltatory conduction
        return result

class LoggingDecorator extends Decorator:
    function transmit(signal):
        log("about to transmit", signal)
        result = self._inner.transmit(signal)
        log("transmitted, latency=", result.latency)
        return result

class CachingDecorator extends Decorator:
    field _cache: dict

    function transmit(signal):
        if signal in self._cache: return self._cache[signal]
        result = self._inner.transmit(signal)
        self._cache[signal] = result
        return result
```

### Python (xem file `09_decorator.py`)

File code triển khai:
1. **Anti-pattern inheritance explosion** — minh họa cần 2^N class nếu dùng inheritance.
2. **Component & ConcreteComponent**: `AxonSignal` interface + `BareAxon`.
3. **Abstract Decorator**: `AxonDecorator` wraps `AxonSignal`.
4. **4 ConcreteDecorator sinh học**: `MyelinSheath`, `PerineuronalNet`, `GlialEnsheathment`, `NodalTightening`.
5. **Demo stacking**: bare → +myelin → +PNN → +glia, đo latency từng bước.
6. **Demo MS**: remove myelin từ chain → conduction velocity rớt 10-20 lần.
7. **Demo thứ tự**: stack myelin trước/sau logging cho semantic khác nhau.
8. **Ellumm version**: `StorageBackend` với chain `AuthDecorator → RateLimitDecorator → CachingDecorator → LoggingDecorator → ProfilingDecorator → SQLiteStorage`.
9. **Python @decorator syntax**: phụ lục so sánh GoF Decorator vs Python function decorator.

---

## 3 LOẠI VÍ DỤ

### Ví dụ 1 — Vận hành thường

Bạn vô tình chạm tay vào ấm nước nóng. Quy trình thần kinh:
1. Receptor đau (TRPV1) trên fingertip kích hoạt → spike.
2. Spike đi qua **2 loại fiber song song**:
   - **Aδ-fiber** (heavily myelinated): tốc độ ~30 m/s. Bạn cảm nhận đau "nhói, sắc" trong ~50ms.
   - **C-fiber** (unmyelinated, bare axon): tốc độ ~1 m/s. Bạn cảm nhận đau "âm ỉ, rát" trong ~1-2 giây sau.
3. Reflex withdrawal được trigger qua Aδ-fiber → tay rút khỏi ấm trong < 100ms (nhờ myelin decorator!). Nếu chỉ có C-fiber, bỏng nặng hơn vì withdraw chậm 20×.

Cùng signal "đau", cùng nguồn, cùng đích. Khác biệt chỉ ở việc axon có myelin decorator hay không. Đây là Decorator áp dụng vào sinh học có **hậu quả sống còn**: phản xạ rút tay nhanh chỉ tồn tại nhờ "Aδ-fiber là MyelinSheath(BareAxon)".

### Ví dụ 2 — Hỏng / Thiếu

**Trường hợp sinh học — Multiple Sclerosis (MS)**: hệ miễn dịch tấn công myelin trong CNS. Cùng axon, cùng neurotransmitter, cùng đích — nhưng **myelin decorator bị remove**:

| Triệu chứng | Cơ chế |
|-------------|--------|
| Yếu cơ, mất phối hợp | Conduction velocity giảm 10-20× → motor command không đến đúng thời điểm |
| Optic neuritis (mờ mắt) | Demyelination ở optic nerve → visual signal trễ và phân tán |
| Mệt mỏi (fatigue) | Tốn năng lượng hơn để propagate AP qua axon trần |
| Conduction block | Demyelination nặng → AP không thể propagate qua đoạn không có myelin |

Đây là minh chứng đời thực rằng "remove decorator" gây regression nghiêm trọng dù core component (axon, neuron, synapse) còn nguyên.

**Charcot-Marie-Tooth disease**: myelin peripheral hỏng → cảm giác và sức tay/chân giảm. Cùng pattern: decorator hỏng, component cốt lõi nguyên.

**Trường hợp code — Sai thứ tự stack**:

```python
# Bug: log không thấy cache hit
storage = LoggingDecorator(
    CachingDecorator(
        SQLiteStorage()
    )
)
# Khi cache hit, LoggingDecorator KHÔNG được gọi — log thiếu
# Programmer debug 3 ngày tự hỏi tại sao log không khớp số request
```

Sửa:

```python
# Đúng: cache wrap log → log thấy mọi request, kể cả cache hit
storage = CachingDecorator(
    LoggingDecorator(
        SQLiteStorage()
    )
)
```

Loại bug này phổ biến đến mức nhiều framework (Express, ASP.NET) bắt buộc declare middleware order tường minh.

### Ví dụ 3 — Ứng dụng Ellumm

Trong Ellumm, mỗi `MemoryStorage` operation cần nhiều cross-cutting concerns. Ngây thơ:

```python
# ❌ Mọi method trong Storage đều có boilerplate
class SQLiteStorage:
    def get(self, key):
        log("get", key)                    # logging
        if not authorized(): raise          # auth
        if rate_limit_exceeded(): wait      # rate limit
        if cached(key): return cache[key]   # cache
        start = time.now()                  # profiling
        result = self._db.get(key)
        log("get done", time.now() - start)
        cache[key] = result
        return result
    # ... duplicate cho put, query, ...
```

Decorator chain:

```python
storage = AuthDecorator(
    RateLimitDecorator(
        CachingDecorator(
            ProfilingDecorator(
                LoggingDecorator(
                    SQLiteStorage()
                )
            )
        )
    )
)

storage.get(key)        # tất cả 5 concern chạy đúng thứ tự
```

Lợi ích cụ thể:
1. **SQLiteStorage chỉ 30 dòng**, tập trung vào logic thật.
2. Mỗi decorator **độc lập, test riêng được** với mock component.
3. **Stack runtime**: dev mode dùng `LoggingDecorator + SQLiteStorage`, prod thêm `AuthDecorator + RateLimitDecorator + CachingDecorator`.
4. **Thêm concern mới** (vd: `EncryptionDecorator`) = thêm 1 class, không sửa storage hay decorator khác.
5. **Order tường minh**: chain composition cho thấy thứ tự execution rõ ràng.

Khi switch backend (SQLite → Postgres), chain decorator giữ nguyên, chỉ swap innermost. Khi disable feature (rate limit) → bỏ 1 decorator khỏi chain.

---

## TÓM LẠI

Decorator = **wrap object cùng interface để thêm hành vi runtime, stackable, không sửa component cốt lõi**. Trong não, myelin sheath là Decorator tự nhiên — wrap axon để tăng tốc dẫn truyền 50-100× qua saltatory conduction. MS là minh chứng "remove decorator gây regression dù core component nguyên". Aδ-fiber vs C-fiber cùng truyền pain signal nhưng khác myelin → thời gian phản ứng khác 20× → ảnh hưởng sống còn.

Dấu hiệu cần Decorator:
- Có cross-cutting concerns (logging, caching, auth, timing, retry, validation, encryption).
- Đang dùng inheritance và class explosion theo tổ hợp feature.
- Cần thêm/bớt feature runtime, hoặc theo môi trường (dev/staging/prod).
- Có nhiều method với boilerplate giống nhau ở đầu/cuối.

Cặp pattern thường đi cùng:
- **Decorator + Strategy** (lesson 21): decorator có thể wrap nhiều strategy.
- **Decorator + Composite** (lesson 08): decorator có thể nằm trong tree (vì cùng implement Component).
- **Decorator + Factory Method** (lesson 02): factory tạo chain decorator phù hợp với context.
- **Decorator + Chain of Responsibility** (lesson 13): chain decorator cũng là chain xử lý — overlap conceptually.

### Python @decorator syntax — phân biệt

Python có cú pháp `@decorator` cho function. Đây là biến thể của pattern Decorator nhưng cho function thay vì object:

```python
@cached
@logged
@profiled
def transmit(signal):
    ...
```

Tương đương:
```python
def transmit(signal): ...
transmit = profiled(transmit)
transmit = logged(transmit)
transmit = cached(transmit)
```

Cùng tinh thần "wrap to add behavior", nhưng:
- GoF Decorator: object pattern, thường dùng cho stateful service.
- Python @decorator: function pattern, dùng cho stateless transform hoặc light wrapper.

Khi decorator cần state phức tạp hoặc multiple methods, GoF Decorator (class-based) phù hợp hơn. Khi chỉ wrap 1 function với hành vi đơn giản, `@decorator` syntax gọn hơn.

### Câu hỏi tự kiểm tra

1. Tại sao Decorator phải implement Component interface (chứ không chỉ "có" Component)? Nếu không, hậu quả gì?
2. Trong não, myelin được "lắp" trong quá trình development (~6 tháng → 25 tuổi). Trong code, có nên cho phép thêm/bỏ decorator động (sau khi object đã được tạo) không? Trade-off là gì?
3. Trong Ellumm, nếu có 6 cross-cutting concerns nhưng chỉ 3 cần áp cho mỗi method (3 cho `get()`, 3 khác cho `put()`), bạn xử lý sao? (Gợi ý: factory + per-method chain, hoặc Aspect-Oriented Programming)
