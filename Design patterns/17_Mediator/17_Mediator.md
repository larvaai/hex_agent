# Lesson 17 — Mediator Pattern
## Thalamus — Trạm trung chuyển chống N-to-N coupling

---

## TÓM TẮT MỘT DÒNG

**Mediator** = đặt một object trung gian giữa N colleague để chúng không tham chiếu trực tiếp lẫn nhau, biến `N×(N-1)/2` connection thành `N` connection — và toàn bộ logic _cách chúng tương tác_ tập trung tại 1 chỗ.

> Ngoại trừ khứu giác, **mọi tín hiệu cảm giác đều phải qua thalamus** trước khi vào cortex. Cortex thị giác không "nói" trực tiếp với võng mạc, không "nói" trực tiếp với cortex thính giác. Nó nói với LGN, MGN, pulvinar — các thalamic nuclei. Nếu mỗi cortical area kết nối trực tiếp với 200 area khác, bộ não sẽ là một nồi cháo dây thần kinh không thể tiến hoá. Thalamus chính là **Mediator**.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Giả sử bạn có 5 component UI: `Button`, `Dropdown`, `TextField`, `Checkbox`, `Label`. Khi user click button → dropdown phải reset, textfield phải clear, checkbox phải uncheck, label phải đổi text.

**Cách ngây thơ**: button có 4 reference tới 4 component khác, gọi method trên chúng. Sau đó dropdown change cũng phải sửa textfield, label, button... Mỗi component biết về N-1 component còn lại.

Hệ quả:
- **Combinatorial coupling**: 5 component → 10 cặp; 10 component → 45 cặp. Không scale.
- **Tái sử dụng = 0**: muốn dùng `Button` ở context khác phải gỡ tất cả tham chiếu.
- **Test = ác mộng**: mock toàn bộ N-1 component để test 1 component.
- **Logic tương tác phân tán**: muốn hiểu "khi user submit, chuyện gì xảy ra?" phải đọc 5 file.

**Mediator**: thêm 1 object `FormDialog` (mediator). Mỗi component chỉ giữ reference tới mediator. Khi component có sự kiện, nó báo mediator: `mediator.notify(self, event)`. Mediator quyết định ai cần làm gì.

Hệ quả:
- N component → N edge tới mediator. Linear, không combinatorial.
- Mỗi component **độc lập, tái sử dụng được** (chỉ phụ thuộc interface mediator).
- Logic tương tác **tập trung 1 file** — đọc mediator là hiểu toàn flow.
- **Test**: mock mediator, test component riêng lẻ.

### 1.2. Neuroscience analogy — Thalamus

**Thalamus** ngồi giữa não, là trạm relay gần như tất cả tín hiệu đi vào và đi ra cortex. Có ~50 nuclei chuyên biệt:

| Nucleus | Vai trò |
|---------|---------|
| **LGN** (Lateral Geniculate Nucleus) | Relay thị giác từ võng mạc → V1 |
| **MGN** (Medial Geniculate Nucleus) | Relay thính giác từ inferior colliculus → A1 |
| **VPL / VPM** | Relay somatosensory (cơ thể, mặt) → S1 |
| **VL / VA** | Relay motor từ cerebellum + basal ganglia → motor cortex |
| **MD** (Mediodorsal) | Relay limbic → prefrontal cortex (executive, working memory) |
| **Pulvinar** | Higher-order relay, attention modulation cortex ↔ cortex |

Đặc điểm thalamus mà architect phải để ý:
1. **Cortex không nói thẳng với cortex khác** ở khoảng cách xa — thường qua _higher-order thalamic relay_ (pulvinar, MD). Đây là _cortico-thalamo-cortical loop_.
2. Thalamus không chỉ là dây dẫn — nó **gate** (TRN, thalamic reticular nucleus quyết định signal nào được pass), **gain modulation** (state-dependent: ngủ vs thức), **rhythm coordination** (alpha/gamma).
3. Thalamus chuyên biệt theo modality (LGN cho thị, MGN cho thính). _Không có một thalamus tổng cho tất cả_ — chia theo domain.
4. Thalamus damage → coma, akinetic mutism, severe attention deficit. _Mediator hỏng thì cả hệ thống dừng._ Đó vừa là điểm mạnh (centralized) vừa là điểm yếu (single point of failure).

#### 5 chiều của analogy

| Chiều      | Trong não                                                                              | Trong code                                                                  |
|------------|----------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| Cấu tạo    | Một nhóm nuclei chuyên biệt + TRN gate + cortico-thalamic feedback                    | Mediator interface + ConcreteMediator (có thể là composite of sub-mediators)|
| Vị trí     | Trung tâm não, nằm giữa input/output và cortex                                         | Tách biệt khỏi colleagues, không sub-class colleague                        |
| Chức năng  | Relay + gate + gain modulation + sync rhythm cortex                                    | Route + transform + validate + sequence + suppress message giữa colleagues |
| Kết nối    | Sub-cortical input ↔ thalamus ↔ cortex; cortex ↔ pulvinar ↔ cortex                    | Colleague ↔ Mediator ↔ Colleague (không bao giờ Colleague ↔ Colleague)     |
| Ý nghĩa    | Cho phép cortex tiến hoá thêm vùng mới mà không cần rewire tất cả                      | Cho phép thêm Colleague mới mà không sửa Colleague cũ (Open/Closed)         |

### 1.3. Khi nào DÙNG

- N component có **logic tương tác phức tạp** (UI form, dialog, workflow, state machine).
- Cần thêm/bớt component **mà không sửa các component khác** (Open/Closed).
- Cần **tái sử dụng** component ở nhiều context (component không biết về cụ thể app này).
- Logic tương tác **thay đổi thường xuyên** — tập trung 1 chỗ dễ sửa.
- Cần **audit / log / replay** mọi tương tác (thêm vào mediator, không phải vào từng component).
- Domain cụ thể: GUI form, chat room, air traffic control, command bus (CQRS), workflow engine, microservice orchestrator.

### 1.4. Khi nào KHÔNG DÙNG

- Hệ thống đơn giản, 2–3 component, tương tác stable → trực tiếp đơn giản hơn.
- Component cần **performance cao** (tight loop) → mediator thêm overhead indirection.
- Logic tương tác **đối xứng + đơn giản** (kiểu N publisher cùng broadcast 1 event) → **Observer / Event Bus** phù hợp hơn.
- Khi mediator bắt đầu biết quá nhiều → đó là tín hiệu **God Object anti-pattern**, cần tách thành sub-mediators (giống thalamus có nhiều nuclei).
- Khi cần **scale ngang** (distributed system) → message broker (Kafka, RabbitMQ) thay vì in-process mediator.

### 1.5. Cảnh báo architect

> **Mediator không xoá coupling, nó dồn coupling vào một chỗ**. Nếu mediator có 50 method `if-elif-elif`, bạn không bớt phức tạp — bạn vừa cô đặc nó. Câu hỏi đúng: _"Mediator này có _một mục đích duy nhất_ (form, workflow, transaction) không, hay đang biết tất cả?"_. Nếu là _tất cả_ — tách. Não chia thalamus thành 50 nuclei vì lý do đó.

---

## MỨC 2 — ALGORITHM

### 2.1. Vai diễn

```
                    ┌──────────────────────┐
                    │      Mediator        │
                    │  (interface)         │
                    │ + notify(sender,evt) │
                    └──────────────────────┘
                              △
                              │
                    ┌──────────────────────┐
                    │  ConcreteMediator    │
                    │  - colleagues: list  │
                    │  + notify(...)       │
                    │  + register(c)       │
                    └──────────────────────┘
                              ▲
                              │ knows mediator (1 reference)
              ┌───────────────┼───────────────┐
              │               │               │
        ┌───────────┐  ┌───────────┐  ┌───────────┐
        │ ColleagueA│  │ ColleagueB│  │ ColleagueC│
        │           │  │           │  │           │
        │ - mediator│  │ - mediator│  │ - mediator│
        │ + on_evt()│  │ + on_evt()│  │ + on_evt()│
        └───────────┘  └───────────┘  └───────────┘
```

- **Mediator interface**: thường có method duy nhất `notify(sender, event_type, payload)`.
- **ConcreteMediator**: chứa danh sách colleagues (hoặc tham chiếu cụ thể nếu fixed), implement logic _khi sender gửi event X, ai phản ứng thế nào_.
- **Colleague (BaseColleague)**: mỗi component có 1 reference tới mediator (set qua constructor hoặc setter). Khi có event nội bộ, gọi `self.mediator.notify(self, "evt_name", data)`.
- **Concrete colleagues**: button, dropdown, viewer, panel — cài method handler.

### 2.2. Luồng điều khiển

```
User clicks Button
       │
       ▼
Button.on_click()
       │
       ▼ self.mediator.notify(self, "submit", data)
       │
       ▼
Mediator.notify(sender=Button, event="submit", payload=data)
       │
       ├─ if sender == Button and event == "submit":
       │      Dropdown.reset()
       │      TextField.clear()
       │      Label.set_text("Saved")
       │      Logger.log_audit(...)
       ▼
return
```

### 2.3. Biến trạng thái và bất biến

- Colleague chỉ giữ **reference tới mediator** + state nội bộ. Không giữ ref tới colleague khác.
- Mediator có **registry of colleagues** (dict by name hoặc list).
- Mediator có thể giữ **state phối hợp** (ví dụ: workflow đang ở step nào, transaction state).
- **Invariant**: colleague KHÔNG bao giờ gọi method của colleague khác trực tiếp. Vi phạm = pattern bị phá.
- Mediator nên **không giữ business state của colleague** — đó là việc của colleague.

### 2.4. Biến thể

| Biến thể | Mô tả | Khi nào dùng |
|----------|-------|--------------|
| **Sync mediator** | `notify` chạy đồng bộ, return có thể chứa kết quả | UI form, single-thread, dễ debug |
| **Async mediator** | `await mediator.notify(...)` — không block sender | I/O heavy (DB, network), async UI |
| **Event Bus / Publisher-Subscriber** | Mediator decoupled tuyệt đối: không biết colleague cụ thể, chỉ route theo topic. Colleague subscribe topic. | N-to-N broadcast, loose coupling extreme |
| **Command Bus (CQRS)** | Mediator route _command_ tới _handler_ cụ thể. 1 command = 1 handler. | Backend service (MediatR C#, Brighter, Symfony Messenger) |
| **Mediator + State Machine** | Mediator giữ state, transitions = response logic | Workflow, wizard, multi-step form |
| **Hierarchical mediators** | Mediator gọi sub-mediator (giống thalamus → nuclei) | Hệ phức tạp, chia domain |

### 2.5. Mediator vs Observer vs Event Bus

| Khía cạnh | Observer | Event Bus / Pub-Sub | Mediator |
|-----------|----------|---------------------|----------|
| Sender biết receiver? | Không (chỉ broadcast) | Không | Không |
| Receiver biết sender? | Có (qua Subject reference) | Không | Có (mediator biết colleague) |
| Logic phối hợp ở đâu? | Phân tán (mỗi observer tự quyết) | Phân tán (subscriber tự xử lý) | Tập trung (mediator) |
| Ai quyết định "khi A xảy ra, B làm gì"? | B tự subscribe và quyết | Subscriber tự subscribe | Mediator quyết hết |
| Scale | N-to-many (1 subject, nhiều observer) | Many-to-many | N tới-1-tới-N |
| Đặc trưng | Push notification | Topic-based routing | Centralized coordination |

> **Quy tắc architect**:
> - Khi **A xảy ra → broadcast cho ai quan tâm** (không cần biết là ai) → **Observer** hoặc **Event Bus**.
> - Khi **A xảy ra → cần làm B, C, D theo trình tự, có thể fail rollback** → **Mediator**.
> - Não dùng cả: amygdala broadcast salience (Observer); thalamus relay có routing và gating (Mediator).

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
interface Mediator:
    notify(sender: Colleague, event: string, payload: any)

class ConcreteMediator implements Mediator:
    private colleagues: dict[name → Colleague]
    
    register(name: string, colleague: Colleague):
        colleagues[name] = colleague
        colleague.set_mediator(self)
    
    notify(sender, event, payload):
        match (sender.name, event):
            case ("Button", "submit"):
                colleagues["Dropdown"].reset()
                colleagues["TextField"].clear()
                colleagues["Label"].set_text("Saved")
            case ("Dropdown", "change"):
                colleagues["TextField"].update_options(payload)
            ...

class Colleague:
    private mediator: Mediator
    set_mediator(m): self.mediator = m
    # khi có event nội bộ, gọi: self.mediator.notify(self, "evt", data)
```

### 3.2. Python — 3 ví dụ

Code chạy được ở `17_mediator.py`. Tóm tắt:

#### Ví dụ 1 — Vận hành thường: Ellumm Learning Session Mediator

Một session học có 4 component: `LessonViewer`, `QuizPanel`, `NotesPanel`, `ProgressBar`. Logic phức tạp:
- Khi user **bắt đầu lesson** → ProgressBar reset, NotesPanel clear, QuizPanel khoá.
- Khi user **đọc xong lesson** → ProgressBar tăng, QuizPanel mở khoá.
- Khi user **làm quiz đúng** → ProgressBar +20%, NotesPanel suggest review.
- Khi user **viết note** → autosave qua mediator, không component nào biết storage.

Tất cả logic **tập trung 1 file mediator**. Nếu không có mediator: 4 component × ~3 dependency = 12 cặp tham chiếu, mỗi component biết toàn bộ rest.

#### Ví dụ 2 — Hỏng / thiếu: N×N coupling không có mediator + God Mediator anti-pattern

So sánh trực tiếp:
- **2a** — `BadSession` không có mediator: mỗi component có ref tới 3 component khác. Logic phân tán, thêm component mới = sửa N file.
- **2b** — God Mediator: 1 mediator biết 30 colleague, 200 dòng `if-elif`. Tệ không kém. Cách xử lý: chia thành nhiều mediator chuyên biệt (LessonMediator, QuizMediator, NotesMediator) + 1 SessionMediator điều phối — đúng kiểu thalamus chia nuclei.

#### Ví dụ 3 — Ứng dụng architect: Command Bus (CQRS-style)

Mediator phổ biến nhất ở backend hiện đại không phải UI mà là **Command Bus**. Pattern:

```
class StartLessonCommand: ...
class CompleteQuizCommand: ...

class CommandBus(Mediator):
    handlers: dict[CommandType → Handler]
    register(cmd_type, handler)
    dispatch(cmd) → handler.handle(cmd)
```

- 1 command type = 1 handler (ánh xạ 1-1).
- Caller chỉ biết `bus.dispatch(cmd)`, không biết handler ở đâu.
- Thêm command type mới = thêm handler + register, không sửa caller.
- Đây là pattern của **MediatR (.NET)**, **Brighter**, **Symfony Messenger**, **NestJS CQRS**.
- Architect benefit: middleware (logging, validation, transaction, retry) gắn vào bus — chạy auto cho mọi command.

---

## SO SÁNH VỚI PATTERN KHÁC

| Pattern        | Khác biệt với Mediator                                                                   |
|----------------|------------------------------------------------------------------------------------------|
| **Observer**   | Observer là 1-to-N broadcast không có routing logic. Mediator là N-to-N có routing logic tập trung. |
| **Facade**     | Facade ẩn 1 hệ phức tạp sau interface đơn giản (1 chiều, client → subsystem). Mediator điều phối 2 chiều giữa peer. Facade không có "colleagues" — chỉ subsystem. |
| **Command**    | Command đóng gói _một lệnh_. Mediator có thể _route_ command (Command Bus = Mediator + Command). |
| **Singleton**  | Mediator thường là 1 instance per session/scope, nhưng KHÔNG nên là Singleton global — gây test khó, coupling ngầm. |
| **Chain of Resp.** | Chain truyền request đi cho đến khi 1 handler xử lý. Mediator chủ động chọn handler/recipient. Chain = đẩy đi; Mediator = phân phát. |
| **Proxy**      | Proxy đại diện cho 1 object cụ thể (cùng interface). Mediator điều phối nhiều object khác interface. |

> **Insight architect**: trong production code, ranh giới giữa **Mediator + Command + Observer** rất mờ. Một message broker (Kafka, RabbitMQ) vừa là Mediator (route message), vừa hỗ trợ Observer (subscribe topic), vừa truyền Command (queue). Học pattern không phải để gắn label chính xác, mà để hiểu **ai biết ai, ai quyết định khi nào, ai chịu trách nhiệm gì**.

---

## ANTI-PATTERNS THƯỜNG GẶP

1. **God Mediator** — 1 mediator biết 30 colleague, 50 event types, 500 dòng `if-elif`.
   - Triệu chứng: thêm 1 colleague mới sợ hãi, mất 1 ngày debug.
   - Xử lý: tách theo **bounded context** (UI section, business domain). Mỗi mediator có 1 trách nhiệm.

2. **Mediator giữ business state** — mediator nhớ "user đã làm quiz #3 chưa" thay vì colleague (`QuizPanel`) tự nhớ.
   - Triệu chứng: mediator phình to vô tội vạ.
   - Xử lý: state thuộc về colleague. Mediator chỉ phối hợp, không lưu trữ.

3. **Singleton Mediator global** — `GlobalMediator.instance().notify(...)`.
   - Triệu chứng: test viết khó, mock không được, không thể có 2 session song song.
   - Xử lý: inject mediator qua constructor (DI). Mỗi session/scope một instance.

4. **Colleague vẫn giữ ref tới colleague khác "for performance"** — phá hoàn toàn pattern.
   - Triệu chứng: bypass mediator một số path → couping ngầm.
   - Xử lý: nếu performance đúng là vấn đề (đo được), tối ưu mediator chứ không skip nó.

5. **Notify với string event không type-safe** — `notify(self, "submmit", ...)` (typo).
   - Triệu chứng: silent failure, không lỗi compile.
   - Xử lý: dùng Enum cho event type, hoặc Command class. TypeScript / Python có literal type.

6. **Mediator gọi notify đệ quy không kiểm soát** — A.evt → mediator → B.do → B.evt → mediator → A.do → ...
   - Triệu chứng: stack overflow, race condition.
   - Xử lý: detect cycle (set of in-flight events), hoặc chuyển sang async với queue.

---

## BÀI TẬP

1. **Cơ bản**: Thêm component `BookmarkPanel` vào ví dụ Ellumm session. Khi user bookmark lesson → ProgressBar không tăng, NotesPanel mở section "Saved", LessonViewer highlight. Không sửa 4 component cũ.

2. **Trung bình**: Refactor `BadSession` (ví dụ 2a) thành mediator. Đo số dòng code thay đổi. Đo số tham chiếu giữa colleagues trước/sau (vẽ graph).

3. **Khó (architect)**: Viết một **Command Bus** đầy đủ cho Ellumm:
   - Generic `CommandBus[TCommand, TResult]`.
   - Decorator-based middleware: `@logging_middleware`, `@validation_middleware`, `@retry_middleware`.
   - Auto-register handler bằng decorator: `@bus.handler(StartLessonCommand)`.
   - Test: dispatch 5 command type khác nhau, check middleware chạy đúng thứ tự, retry với exponential backoff khi handler raise.
   - Bonus: thêm async variant với `await bus.dispatch(cmd)`.

4. **Mở rộng neuro**: Mô phỏng "thalamus damage". Trong session đang chạy, "vô hiệu hoá" mediator (set `mediator = None` hoặc raise trên mọi notify). Quan sát hệ thống. So sánh với thalamic stroke (akinetic mutism: không phản ứng, dù cortex còn). Sau đó implement **thalamic redundancy**: mediator backup tự kích hoạt nếu primary fail. Đó là pattern **Failover Mediator**.

---

## PYTHON-NATIVE: signals, blinker, asyncio, dispatch

Python có vài thư viện gần Mediator:
- **`blinker`**: signal/slot kiểu Qt — gần Observer/Event Bus, không phải Mediator thuần.
- **`PyDispatcher`**: tương tự blinker.
- **`asyncio`**: event loop chính nó là một mediator I/O — bạn không gọi callback trực tiếp, bạn `await` event loop.

Pure Python implement Mediator chỉ cần dict + method. Không cần lib. Đó là điểm hay: pattern, không phải framework.

Khi muốn type-safe Mediator (như MediatR C#), dùng `typing.Protocol` + generic + dispatch by class:

```python
from typing import Protocol, TypeVar, Generic
T = TypeVar("T"); R = TypeVar("R")
class Handler(Protocol[T, R]):
    def handle(self, cmd: T) -> R: ...

class CommandBus:
    _handlers: dict[type, Handler] = {}
    def register(self, cmd_type, handler): self._handlers[cmd_type] = handler
    def dispatch(self, cmd):
        return self._handlers[type(cmd)].handle(cmd)
```

---

## CHECKLIST TRƯỚC KHI MERGE PR DÙNG MEDIATOR

- [ ] Mediator có **một trách nhiệm duy nhất** (single bounded context) không?
- [ ] Mediator có dài quá 200 dòng không? (Nếu có, tách.)
- [ ] Colleague có **bị tham chiếu tới colleague khác** ở đâu không? (grep.)
- [ ] Event/command type có **type-safe** (Enum / class) không, hay là string?
- [ ] Có cycle detection nếu mediator có thể trigger chain notify?
- [ ] Mediator có inject qua constructor, không phải Singleton global?
- [ ] Có test **mediator riêng lẻ** với mock colleague được không?
- [ ] Có log/audit trail cho mỗi notify (debug production)?
- [ ] Async vs sync đã quyết rõ chưa? Có timeout cho async notify không?
- [ ] Failure của 1 colleague có làm sập notify không? Có rollback / compensation?

---

## TÓM LẠI BẰNG NEUROSCIENCE

> Bộ não động vật có vú không có 200 cortical area kết nối thẳng trực tiếp với nhau. Đó là vì combinatorial explosion sẽ giết tiến hoá. Thay vào đó, **thalamus** ngồi giữa, chia thành ~50 nuclei chuyên biệt (LGN cho thị, MGN cho thính, MD cho executive...). Mỗi nucleus là một _sub-mediator_ trong domain của nó. Pulvinar còn là _higher-order mediator_ điều phối cortex ↔ cortex.

> Architect khôn ngoan không xây 1 God Mediator giữ 50 trách nhiệm — họ xây 1 mạng các mediator chuyên biệt, mỗi cái lo một bounded context, có thể có meta-mediator điều phối chúng. Đó là cách thalamus đã giải bài toán này 500 triệu năm trước, và là cách CQRS / event-driven architecture / microservice orchestration giải bài toán đó hôm nay.

> Khi thalamus damage → akinetic mutism: cortex còn, body còn, nhưng không có cây cầu. Trong code, khi mediator chết → tất cả colleague đứng im (vì chúng không biết nhau). Đó là **single point of failure** — phải tính đến: failover, redundancy, hoặc graceful degradation.

Lesson kế tiếp đề xuất: **18 — Memento (Hippocampal episodic snapshot)** — pattern lưu state để hồi tưởng, undo/redo, time-travel debugging. Hippocampus + Memento = analog đẹp như tranh.
