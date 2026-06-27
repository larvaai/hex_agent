# Lesson 19 — Observer Pattern
## Amygdala — Salience broadcast tới N hệ thống độc lập

---

## TÓM TẮT MỘT DÒNG

**Observer** = đặt một quan hệ 1-tới-N giữa Subject và Observers, sao cho khi Subject thay đổi, **tất cả** Observer được notify tự động — Subject **không biết tên cụ thể** Observer là ai, chỉ biết "có người subscribe interface".

> Bạn đang đi đường, đột ngột nghe tiếng còi xe to. Trong ~80ms, **amygdala** đã phát tín hiệu salience cao và **đồng thời** broadcast ra: hypothalamus → HPA axis (cortisol), brainstem (locus coeruleus → noradrenaline + PAG → freezing), insula (interoception — tim đập), basal ganglia (action selection), cerebellum (motor calibration), motor cortex (chuẩn bị fight/flight), sensory cortex (sharpen attention). Amygdala **không gọi từng cái rồi đợi reply** — nó push một cái, mỗi vùng tự phản ứng theo ngữ cảnh riêng. Đó chính là Observer pattern.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Một object (Subject) có state thay đổi. Nhiều object khác (Observers) cần phản ứng với thay đổi đó. Hai cách ngây thơ:

1. **Subject gọi từng observer cụ thể**:
   ```
   when state changes:
       insula.react()
       hpa.react()
       motor.react()
       ...
   ```
   Vấn đề: thêm observer mới = sửa Subject (vi phạm Open/Closed). Subject biết tên 7 observer = 7 dependency.

2. **Observer poll Subject liên tục**:
   ```
   loop:
       if subject.state != last:
           react()
   ```
   Vấn đề: lãng phí CPU, latency cao, race condition.

**Observer pattern**:
- Subject giữ list observer (interface, không phải class cụ thể).
- Observer `subscribe(subject)` để được notify; `unsubscribe()` để rời.
- Khi state đổi, Subject loop list và gọi `observer.update(event)`.
- Subject **không biết** observer là ai cụ thể, chỉ biết có người implement interface.

### 1.2. Neuroscience analogy — Amygdala salience broadcast

**Amygdala** (cluster nhân ở medial temporal lobe, gồm basolateral BLA, central CeA, intercalated cells…) là vùng phát hiện salience: threat, reward, surprise — bất kỳ thứ gì "đáng chú ý". Output của amygdala đi **đồng thời** ra rất nhiều downstream:

| Target downstream | Phản ứng |
|-------------------|----------|
| **Hypothalamus → HPA axis** | Cortisol release (chậm, kéo dài) |
| **Brainstem (PAG)** | Freezing / fight-flight motor program |
| **Locus coeruleus** | Noradrenaline broadcast → arousal toàn cortex |
| **Insula** | Interoception — "gut feeling", tim đập |
| **Basal ganglia / striatum** | Action selection, habit |
| **Cerebellum** | Motor calibration, timing |
| **Motor cortex** | Chuẩn bị action |
| **Sensory cortex** | Sharpen attention vùng đang fixate |
| **Hippocampus** | Encoding episodic (đánh dấu sự kiện này quan trọng) |
| **Prefrontal cortex** | Đánh giá, suppress nếu false alarm |

Đặc điểm Observer chuẩn:
1. **Push, không pull**: amygdala không "đợi insula đọc state" — nó gửi tín hiệu chemical/electrical.
2. **Fire and forget**: amygdala không đợi reply.
3. **Mỗi observer phản ứng theo logic riêng**: HPA chậm hormonal, motor cortex nhanh điện. Subject không quan tâm.
4. **Có thể chain**: locus coeruleus là observer của amygdala, nhưng cũng là Subject — nó broadcast noradrenaline ra cortex (cả cortex nhận → là observer của LC).
5. **Đường nhanh + đường chậm** (LeDoux): low road (thalamus → amygdala, ~12ms, không qua cortex) vs high road (thalamus → cortex → amygdala, ~80–300ms, có context). Hai pipeline chạy song song với cùng kết quả final là salience signal.
6. **Plasticity**: liên kết amygdala → observer thay đổi theo learning (fear conditioning). Đăng ký/huỷ subscriber = synaptic plasticity.

#### 5 chiều của analogy

| Chiều      | Trong não                                                                                           | Trong code                                                                |
|------------|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| Cấu tạo    | Amygdala (BLA, CeA) + targets (HPA, insula, BG, motor, sensory, hippocampus, PFC)                  | Subject + N Observers (interface) + Event class                            |
| Vị trí     | Trung tâm salience, có axon đi rộng tới brain-wide targets                                          | Subject là 1 component; observers nằm rải khắp app, không cần biết nhau   |
| Chức năng  | Detect salience → broadcast 1 tín hiệu → mỗi target phản ứng theo logic riêng                       | State change → notify all observers → mỗi observer xử lý theo handler riêng|
| Kết nối    | 1 Subject (amygdala) → N targets (chemical, electrical). Có thể chain (LC observer của amygdala, subject của cortex) | Subject ↔ Observer interface; chain Subject—Observer—Subject là phổ biến |
| Ý nghĩa    | Cho phép response brain-wide không cần routing logic tập trung; thêm vùng não mới chỉ cần "subscribe" | Cho phép thêm Observer mới mà không sửa Subject (Open/Closed)              |

### 1.3. Khi nào DÙNG

- Một sự kiện cần **nhiều bên react độc lập**, mỗi bên có logic riêng.
- Subject **không nên biết** chi tiết observers (loose coupling, plug-in).
- **Số observer động**: thay đổi runtime (subscribe/unsubscribe).
- Cần **broadcast** thay vì routing — không có "đúng người nhận", ai quan tâm thì đăng ký.
- UI: model thay đổi → multiple view update (MVC).
- Domain event: order placed → email, inventory, analytics, audit, recommendation engine cùng react.
- Sensor / IoT data: 1 sensor stream → nhiều consumer.

### 1.4. Khi nào KHÔNG DÙNG

- Có **routing logic phức tạp** (nếu A thì B, nếu C thì D) → **Mediator** đúng hơn.
- Cần **đảm bảo thứ tự** observer reaction nghiêm ngặt → hoặc dùng Mediator, hoặc Reactor pattern với scheduler.
- Cần **transactional all-or-nothing** (1 observer fail → rollback tất cả) → pub/sub không phù hợp; dùng **saga** hoặc 2PC.
- Số observer cố định, đơn giản, ít → gọi trực tiếp có khi rõ hơn.
- Subject + Observer trong **distributed system** với latency lớn → dùng **message broker** (Kafka, RabbitMQ) thay Observer in-process.
- Cần **backpressure** (observer chậm hơn subject) → Reactive Streams (Rx, RSocket, Project Reactor) với protocol kiểm soát flow.

### 1.5. Cảnh báo architect

> **Observer là pattern dễ leak nhất**. Subject giữ reference tới Observer → Observer không bao giờ được GC đến khi unsubscribe. Quên unsubscribe khi component bị destroy = memory leak. Trong UI framework / GUI / Android, đây là loại bug số 1. **Luôn nhớ unsubscribe**, hoặc dùng **weak reference**, hoặc thiết kế lifecycle gắn liền (RxJS `takeUntil(destroy$)`).

> **Observer chain là dao hai lưỡi**. Khi observer là subject của một observer khác, có thể tạo ra **cascade event** rất khó debug. Nếu A → B → C → A → ... = infinite loop. Não có circuit breaker (PFC suppress amygdala khi false alarm) — code cần có cơ chế tương tự.

---

## MỨC 2 — ALGORITHM

### 2.1. Vai diễn

```
┌────────────────────────┐         ┌──────────────────────┐
│       Subject          │ notify  │      Observer        │
│ (also: Publisher)      │────────▶│   (interface)        │
│                        │         │ + update(evt) → void │
│ - observers: List      │         └──────────────────────┘
│ + attach(o)            │                 △
│ + detach(o)            │                 │
│ + notify(event)        │       ┌─────────┴──────────┐
└────────────────────────┘       │                    │
        ▲                  ┌──────────┐       ┌──────────┐
        │ (concrete)       │ ConcrA   │       │ ConcrB   │
┌──────────────────┐       │ + update │       │ + update │
│ ConcreteSubject  │       └──────────┘       └──────────┘
│ - state          │
│ + setState(s)    │
└──────────────────┘
```

- **Subject**: giữ list observers (`set` thường tốt hơn `list` để tránh duplicate). Có `attach`/`detach`/`notify`.
- **Observer interface**: 1 method `update(event)` (push) hoặc `update(subject)` (pull style).
- **ConcreteSubject**: cài state, gọi `notify` khi state đổi.
- **ConcreteObserver**: cài `update`, có thể giữ ref tới Subject để pull thêm info nếu cần.
- **Event** (option): object data bag, không bắt buộc nhưng giúp type-safe.

### 2.2. Luồng điều khiển

```
External trigger (sensory input)
       │
       ▼
amygdala.detect(stimulus)      (=Subject.setState)
       ├─ self.state = "high salience"
       └─ self.notify(event)
              │
              ├─ for o in observers:
              │     ┌─ HPA.update(event)        → release cortisol
              │     ├─ Insula.update(event)     → interoception spike
              │     ├─ MotorCortex.update(evt)  → prepare action
              │     ├─ LocusCoeruleus.update(e) → broadcast NA (chain!)
              │     │       └─ for cortex_obs in LC.observers:
              │     │             cortex_obs.update(NA_event)
              │     ├─ Hippocampus.update(evt)  → encode episode
              │     └─ PFC.update(evt)          → evaluate, possibly suppress
              ▼
return (fire-and-forget)
```

### 2.3. Biến trạng thái và bất biến

- **Observers list**: mutable (subscribe/unsubscribe). Trong concurrency → cần lock hoặc copy-on-write.
- **Event object**: nên **immutable** (frozen dataclass). Nếu observer A sửa event, observer B nhận event đã bị mutate → bug khó debug.
- **Iteration over observers**: nếu observer subscribe/unsubscribe trong `update()`, list thay đổi giữa iteration. Quy tắc: copy list trước khi iterate, hoặc dùng concurrent-safe collection.
- **Invariant**: Subject **không hold business state của Observer**. Observer **không** modify Subject's state from `update()` (trừ khi pattern cho phép — hiếm).

### 2.4. Biến thể

| Biến thể | Mô tả | Khi nào dùng |
|----------|-------|--------------|
| **Push** | Subject gửi event chứa data đầy đủ | Đơn giản, mặc định |
| **Pull** | Subject chỉ báo "có thay đổi", Observer pull state qua getter | Event size lớn, observer chỉ cần subset |
| **Filtered observer** | Observer subscribe theo filter (topic, predicate) | N observer nhưng chỉ một subset quan tâm |
| **Async observer** | `update()` trả Future / chạy trong worker pool | Observer chậm, không block Subject |
| **Reactive Streams** | Có backpressure protocol (request(n)) | Producer nhanh hơn consumer |
| **Weak observer** | Subject giữ weak reference → tự GC khi observer chết | UI, lifecycle khó kiểm soát |
| **Event Bus (mediator-style)** | Subject không biết observer; cả hai biết bus + topic | Decoupling cực mạnh |
| **Two-phase notify** | Phase 1: `pre_update` (validate, all observer ok mới tiếp); Phase 2: `commit_update` | Cần atomicity |

### 2.5. Push vs Pull — trade-off

| Khía cạnh | Push | Pull |
|-----------|------|------|
| Subject gửi gì | Data đầy đủ | Chỉ "đã đổi" |
| Observer nhận | Sẵn sàng dùng | Phải call back lấy thêm |
| Coupling | Subject biết kích cỡ event | Observer biết Subject's API |
| Bandwidth | Nhiều (data lớn cho mọi observer) | Ít (chỉ ai cần mới fetch) |
| Khi nào tốt | Event nhỏ, observer luôn cần | Event lớn, observer dùng phần khác nhau |

> **Quy tắc architect**: bắt đầu push (đơn giản). Khi observer phình to / event size MB → cân nhắc pull. Hybrid: push event với pointer + observer pull chi tiết.

### 2.6. Mediator vs Observer — phân biệt rõ

(Đã có ở Lesson 17 — nhắc lại để rõ ranh giới):
- **Observer**: 1 Subject → N Observers, không có routing logic; Subject chỉ broadcast.
- **Mediator**: N Colleagues, có Mediator ở giữa với logic _khi A xảy ra → làm B, C, D theo trình tự cụ thể_.
- **Não dùng cả hai**: amygdala ≈ Observer (broadcast salience); thalamus ≈ Mediator (routing có gating).

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
interface Observer:
    update(event: Event) -> void

class Subject:
    private observers: Set[Observer]
    
    attach(o: Observer):
        observers.add(o)
    detach(o: Observer):
        observers.discard(o)
    notify(event: Event):
        # iterate over copy để không bị invalidate khi observer sub/unsub
        for o in list(observers):
            try: o.update(event)
            except Exception as e:
                # quyết định: log + tiếp, hay propagate?
                log(e)
                # mặc định không propagate — 1 observer hỏng không kéo cả chain

class ConcreteSubject (Subject):
    state: T
    setState(s: T):
        self.state = s
        self.notify(Event(payload=s))

class ConcreteObserver implements Observer:
    update(event):
        # logic riêng
```

### 3.2. Python — 3 ví dụ

Code chạy được ở `19_observer.py`. Tóm tắt:

#### Ví dụ 1 — Vận hành thường: Amygdala salience broadcast

`AmygdalaSubject` detect salience → notify 6 observer downstream: `HPAAxis`, `Insula`, `MotorCortex`, `LocusCoeruleus`, `Hippocampus`, `PrefrontalCortex`.

Đặc biệt: `LocusCoeruleus` cũng là Subject của riêng nó — broadcast noradrenaline tới `SensoryCortex`, `WorkingMemory`. Đây là **chained observer** — đúng như cascade thần kinh thật.

`PrefrontalCortex` đóng vai **circuit breaker**: nếu đánh giá "false alarm", có thể `unsubscribe` chính nó hoặc gửi suppress signal — analog regulation top-down của PFC lên amygdala.

Đặc điểm code:
- `Event` là `@dataclass(frozen=True)` — immutable, không observer nào sửa được.
- Subject iterate over **copy of list** để observer có thể sub/unsub trong `update()`.
- Exception trong 1 observer **không kéo sập** chain — log + tiếp.

#### Ví dụ 2 — Hỏng / thiếu: 4 failure modes

- **2a — Observer raise exception**: nếu không try/except → observer thứ 4 không bao giờ được gọi.
- **2b — Memory leak**: subject giữ strong ref tới observer → observer không GC được. Demo bằng `gc.collect()` + `weakref`.
- **2c — Infinite loop trong chain observer**: A → B → A → B → ... Demo + cách fix (event ID, depth limit, hoặc loại bỏ cycle).
- **2d — Mutate event giữa chừng**: observer 1 sửa event → observer 2 thấy event sai. Frozen dataclass chống.

#### Ví dụ 3 — Ứng dụng Ellumm: LessonProgress publisher

Khi user hoàn thành 1 lesson, `LessonProgressPublisher` notify:
- `AchievementSystem` — kiểm tra unlock badge.
- `NotificationService` — gửi email/push.
- `AnalyticsCollector` — log event.
- `AdaptiveDifficultyEngine` — recompute độ khó lesson tiếp.
- `SocialFeed` — post lên feed của bạn bè.

Mỗi observer độc lập, có thể fail riêng. Thêm observer mới (ví dụ `WeeklyReportEmail`) chỉ cần `subscribe`, không sửa code Publisher.

Demo 2 chế độ:
- **Sync**: `notify` block đến khi mọi observer xong.
- **Async** (concurrent): mỗi `update` chạy trong thread pool → nếu 1 observer chậm (slow email API), không block các observer khác.

---

## SO SÁNH VỚI PATTERN KHÁC

| Pattern        | Khác biệt với Observer                                                                       |
|----------------|----------------------------------------------------------------------------------------------|
| **Mediator**   | Mediator có routing logic tập trung; Observer chỉ broadcast. Mediator: A → B, C, D theo điều kiện. Observer: A → tất cả. |
| **Pub-Sub / Event Bus** | Pub-Sub: Subject KHÔNG biết observer (qua bus + topic). Observer cổ điển: Subject biết observer (giữ list). Pub-Sub là "Observer + Mediator". |
| **Reactive Streams (Rx)** | Mở rộng Observer với operators (map, filter, debounce, throttle) + backpressure. Đây là Observer "có súng máy". |
| **Chain of Responsibility** | Chain: 1 request đi qua từng handler đến khi 1 cái xử lý. Observer: tất cả observer cùng nhận. Chain = sequential; Observer = parallel/broadcast. |
| **Visitor**    | Visitor: 1 operation đi qua N node. Observer: 1 event tới N observer. Trùng "1 đến N" về cấu trúc nhưng intent khác (Visitor: thêm op vào AST không sửa AST; Observer: phối hợp state change). |
| **Iterator (pull) vs Observer (push)** | Iterator: client kéo. Observer: subject đẩy. Pull-stream vs push-stream. Reactive là push; sync iter là pull. |

> **Insight architect**: Trong ngôn ngữ "reactive programming" hiện đại, gần như mọi pattern stream đều build trên Observer. RxJS `Subject`, `BehaviorSubject`, `ReplaySubject` chính là Observer pattern + thêm semantics. Hiểu Observer trong/ngoài là chìa khoá để hiểu RxJS, Project Reactor, Kotlin Flow, Swift Combine.

---

## ANTI-PATTERNS THƯỜNG GẶP

1. **Memory leak vì quên unsubscribe**.
   - Triệu chứng: heap dump full observer "đã bị destroy" nhưng vẫn hold.
   - Xử lý: unsubscribe khi component lifecycle end. Hoặc dùng **weak reference** (Python `weakref.WeakSet` cho observer list). Trong RxJS: `takeUntil(destroy$)`.

2. **Notify trong critical section / lock**.
   - Triệu chứng: deadlock khi observer cố lock cùng resource.
   - Xử lý: `notify` ngoài lock. Hoặc collect events, drain sau khi release.

3. **Subject biết quá nhiều về Observer cụ thể**.
   - Triệu chứng: `if isinstance(o, EmailObserver): ...`.
   - Xử lý: type-check như vậy = phá pattern. Filter qua interface/predicate, không qua type.

4. **Cascade event không kiểm soát** (chain observer infinite loop).
   - Triệu chứng: stack overflow, app freeze.
   - Xử lý: event có depth field, max depth → drop. Hoặc detect cycle bằng visited set per emit.

5. **Observer chậm block Subject**.
   - Triệu chứng: emit p95 = 1500ms vì 1 observer gọi DB sync.
   - Xử lý: async observer, hoặc đẩy event vào queue → worker pool xử lý.

6. **Lost event**: Subject emit khi chưa observer nào subscribe.
   - Triệu chứng: late subscriber miss event.
   - Xử lý: `BehaviorSubject` (emit last value cho late sub) hoặc `ReplaySubject` (emit last N). Pattern "warm vs cold observable".

7. **Event không type-safe**: dùng dict `{type: "user_signup", ...}`.
   - Triệu chứng: typo, runtime error.
   - Xử lý: dataclass cho mỗi event type. Discriminated union nếu nhiều type.

8. **Observer modify Subject từ trong update()**.
   - Triệu chứng: re-entrant notify, list modified during iteration.
   - Xử lý: defer modification, hoặc dùng queue.

---

## BÀI TẬP

1. **Cơ bản**: Thêm observer `BloodPressureMonitor` vào hệ amygdala (ví dụ 1). Khi salience cao → BP tăng. Đảm bảo không sửa code amygdala.

2. **Trung bình**: Cài `FilteredObserver` wrapper: nhận observer + predicate, chỉ forward event nếu `predicate(event) is True`. Apply: `MotorCortex` chỉ phản ứng với `salience > 0.7`. So sánh với cách filter trong amygdala (chính là phân biệt low salience / high salience trong CeA).

3. **Khó (architect)**: Cài **EventBus** type-safe + async với:
   - `subscribe[T](topic_type: Type[T], handler: Callable[[T], None])`.
   - Async dispatch (asyncio).
   - Backpressure: nếu queue > 1000 → drop event cũ nhất + emit `BackpressureWarning` event.
   - Replay: subscriber đăng ký sau có thể request "replay last N events".
   - Test với 3 producer + 5 consumer concurrent. Verify không lost / duplicate / out-of-order trong cùng topic.

4. **Mở rộng neuro**: Mô phỏng **PFC suppress amygdala**. Khi false alarm (`PrefrontalCortex` đánh giá là sai), nó gửi suppress signal qua một observer ngược chiều (hoặc unsubscribe các response observer). Quan sát: HPA cortisol giảm, motor cortex thư giãn, attention reset. Đây là **top-down regulation** — analog của exception filter / circuit breaker.

   Bonus: thêm "fear extinction" — sau N lần false alarm cùng stimulus, plasticity giảm strength của Subject → Observer link. Tức là: observer dần "không react mạnh nữa". Implement weight cho mỗi subscription, decrease theo log của false alarm count.

---

## PYTHON-NATIVE: Signals/PyDispatcher, asyncio, RxPy, weakref

| Tool | Khi nào dùng |
|------|--------------|
| `weakref.WeakSet` | Observer set tự GC |
| `blinker` / `PyDispatcher` | Signals/slots kiểu Qt — Observer + topic |
| `asyncio.Queue` + tasks | Async observer pattern |
| `RxPy` (`rx`) | Reactive streams đầy đủ (operators, schedulers, backpressure) |
| `Pydantic` / `dataclass(frozen)` | Event types |

Pure-Python Observer minimum:
```python
from typing import Protocol, Set
import weakref

class Observer(Protocol):
    def update(self, event) -> None: ...

class Subject:
    def __init__(self):
        self._obs: Set[Observer] = weakref.WeakSet()
    def attach(self, o): self._obs.add(o)
    def detach(self, o): self._obs.discard(o)
    def notify(self, event):
        for o in list(self._obs):  # copy snapshot
            try:
                o.update(event)
            except Exception as e:
                logging.exception("Observer fail: %s", e)
```

15 dòng code = pattern chuẩn. Nhưng đó là phần dễ. Phần khó là **lifecycle, ordering, async, backpressure, type-safety** — và đó là phần architect phải nghĩ.

---

## CHECKLIST TRƯỚC KHI MERGE PR DÙNG OBSERVER

- [ ] Observer interface có rõ (typed event) không?
- [ ] Subject dùng **WeakSet** hoặc có lifecycle unsubscribe rõ ràng?
- [ ] Iterate over **copy** of observer list khi notify (chống invalidate)?
- [ ] Có **try/except** quanh mỗi `update()` (1 observer hỏng không kéo cả chain)?
- [ ] Event có **immutable** không?
- [ ] Có **backpressure** plan nếu observer chậm hơn subject?
- [ ] Có kiểm soát **chain depth** cho cascade observer (chống infinite loop)?
- [ ] Notify có chạy **trong lock** không (deadlock risk)?
- [ ] Có **unit test** cho: subscribe/unsubscribe, notify với 0/1/N observer, observer raise, late subscribe?
- [ ] Có **observability**: log mỗi notify (event type, observer count, duration)?
- [ ] Async vs sync đã quyết rõ, có timeout cho async observer?

---

## TÓM LẠI BẰNG NEUROSCIENCE

> Amygdala đã giải bài toán "phản ứng brain-wide với một sự kiện salience" bằng broadcast 1-tới-N: 1 detection → đồng thời HPA, motor, sensory, hippocampus, PFC react. **Không có routing logic tập trung**, không có thalamus quyết định ai nhận. Mỗi vùng tự subscribe (qua kết nối axon được hình thành trong development + plasticity), tự phản ứng theo logic riêng. Đó là Observer pattern thuần khiết nhất tự nhiên có.

> Quan trọng nhất: **Observer chain**. Locus coeruleus là observer của amygdala, đồng thời là Subject của cả cortex. Hippocampus nhận event từ amygdala và trở thành Subject phát event consolidation tới prefrontal cortex. Mạng cascade này không có architect ngồi vẽ — nó tự tiến hoá vì Observer là pattern **scale tốt**: thêm vùng não mới chỉ cần "subscribe", không cần sửa amygdala.

> Architect học Observer là để hiểu: khi nào dùng nó (broadcast, loose coupling), khi nào tránh (cần routing, cần atomicity, cần backpressure), và quan trọng nhất — **các pitfall đặc trưng** (leak, cascade, lost event, async ordering). Reactive programming hiện đại (Rx, Project Reactor, Kotlin Flow, Combine) đều build trên Observer. Hiểu Observer rồi học Rx chỉ là "Observer + 100 operator + scheduler".

> Não cũng có **PFC như circuit breaker**: false alarm thì nó suppress amygdala. Architect khôn ngoan luôn xây observer system với suppress / unsubscribe / mute mechanism — vì sự kiện "broadcast cho tất cả" sẽ luôn có ngày bạn muốn nó dừng.

Lesson kế tiếp đề xuất: **20 — State (Sleep stages NREM1→2→3→REM)** — pattern thay đổi behavior theo state nội bộ, đồng nghĩa với "cùng object, hành vi khác". Sleep stages là analog đẹp vì cùng 1 não, 4 hành vi neural khác nhau hoàn toàn.
