# Lesson 20 — State Pattern
## Sleep Stages (NREM1 → NREM2 → NREM3 → REM) — cùng não, 4 hành vi neural khác nhau

---

## TÓM TẮT MỘT DÒNG

**State** = đóng gói _hành vi tuỳ trạng thái_ thành các class State riêng biệt; Context delegate cho State hiện tại — đổi state = đổi behavior, không cần `if/elif`.

> Cùng một bộ não, lúc bạn thức (Wake) phản ứng tức thì với tiếng còi xe; lúc bạn ngủ NREM1 dễ dàng tỉnh; NREM3 (deep sleep) khó tỉnh nhưng có glymphatic clearance + growth hormone; REM thì cơ thể bị paralysis (atonia) nhưng cortex hoạt động mạnh và bạn mơ. **Não không thay**, chỉ state thay. Mỗi stage có _cùng API_ (xử lý input, motor control, memory) nhưng _logic hoàn toàn khác_. Đó là State pattern thuần khiết.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Một object cần **hành xử khác nhau tuỳ vào state nội bộ**. Ví dụ:
- `Document`: Draft / Review / Published / Archived — mỗi state cho phép thao tác khác.
- `Order`: Cart / Paid / Shipped / Delivered / Cancelled — logic khác.
- `Connection`: Disconnected / Connecting / Connected / Closing.
- `Sleep`: Wake / NREM1 / NREM2 / NREM3 / REM — phản ứng input khác.

**Cách ngây thơ**: dùng `if/elif` trong từng method:
```python
def process_input(self, x):
    if self.state == "wake":
        # 30 dòng logic wake
    elif self.state == "nrem1":
        # 30 dòng logic nrem1
    elif self.state == "nrem3":
        # 30 dòng logic nrem3
    ...
```
Vấn đề:
- Mỗi method 100+ dòng, mỗi state phân tán khắp class.
- Thêm state mới = sửa **tất cả** method (vi phạm Open/Closed nghiêm trọng).
- Dễ quên xử lý state X trong method Y → bug runtime.
- Không reuse được state logic.

**State pattern**: tách mỗi state thành 1 class implement cùng interface. Context giữ ref tới state hiện tại, mọi method delegate cho state. Đổi state = thay object, không sửa Context.

### 1.2. Neuroscience analogy — Sleep stages

Một đêm điển hình ~7-8h, não đi qua **4-6 chu kỳ** ~90 phút, mỗi chu kỳ qua các stage:

| Stage | EEG | Phản ứng kích thích | Vận động | Đặc trưng |
|-------|-----|---------------------|----------|-----------|
| **Wake (W)** | Alpha + beta, mixed | Mạnh, có ý thức | Đầy đủ | Thinking, planning, executive |
| **NREM1** | Theta low-amp | Dễ tỉnh, vẫn nhận biết | Giảm | Hypnagogic transitions, hypnic jerks |
| **NREM2** | Sleep spindles + K-complex | Khó tỉnh hơn | Thư giãn | Memory consolidation declarative |
| **NREM3** | Delta (slow waves) | Rất khó tỉnh | Nhỏ | Glymphatic clearance, GH, memory procedural |
| **REM** | Mixed, gần wake | Khó tỉnh, nhưng cortex active | **Atonia** (paralysis) | Vivid dreaming, emotional processing |

Quy luật transition (đơn giản hoá):
```
W → NREM1 → NREM2 → NREM3 → NREM2 → REM → NREM2 → ... (90 min cycle)
```

Đặc điểm State pattern thuần khiết:
1. **Cùng não** (cùng object) — không thay neuron, không clone.
2. **Cùng input API** (kích thích âm thanh, ánh sáng) → **phản ứng khác nhau**.
3. **State quyết định transition tiếp theo** — REM không gọi từ NREM1 trực tiếp, phải qua NREM2/3.
4. **Mỗi stage có chức năng độc lập**: NREM3 lo glymphatic, REM lo emotional integration. Không phải "1 não đa năng cùng lúc".
5. **Context (não) lưu state hiện tại + lịch sử**; transition có **guard** (đã ngủ đủ NREM chưa? đủ thời gian không?).
6. **Bệnh lý = transition lỗi**: narcolepsy = REM xâm nhập từ Wake (không qua NREM); insomnia = stuck Wake; sleep paralysis = atonia của REM kéo sang Wake. Đây đúng là _state pattern bug_ trong y học.

#### 5 chiều của analogy

| Chiều      | Trong não                                                                              | Trong code                                                                |
|------------|----------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| Cấu tạo    | Brainstem (RAS) + thalamus (spindles) + cortex (slow waves) + hypothalamus (circadian)| Context + State interface + N ConcreteStates                              |
| Vị trí     | Hệ phối hợp khắp não, không trú một vùng                                              | State object là field nội bộ của Context (`_state`)                        |
| Chức năng  | Mỗi stage có job riêng (consolidation, clearance, dream, executive)                    | Mỗi State implement cùng API, behavior khác cho cùng phương thức           |
| Kết nối    | Transitions theo cycle có quy luật; có guard (đủ NREM trước khi REM)                   | State có thể tự transition (`ctx.set_state(new)`); có guard predicate     |
| Ý nghĩa    | Cho phép cùng não làm 5 job tách biệt theo thời gian thay vì gắng làm tất cả cùng lúc | Cho phép cùng object có N behavior mà không if/elif; thêm state = thêm class|

### 1.3. Khi nào DÙNG

- Object có **nhiều state** với behavior khác biệt rõ ràng.
- Có **logic transition** giữa các state (state machine — finite, có quy luật).
- Tránh `if/elif`/switch trên state field xuất hiện ở >2 method.
- Cần **thêm state mới** mà không sửa các state cũ (Open/Closed).
- Cần **entry/exit action** khi vào/ra state (init resource, cleanup).
- Domain: workflow, document lifecycle, network protocol, game character (idle/walk/run/jump), parser state, UI screen flow.

### 1.4. Khi nào KHÔNG DÙNG

- Chỉ 2-3 state, mỗi state hành xử gần giống → flag boolean / enum đơn giản đủ.
- Behavior thay đổi không phải theo state nội bộ mà theo **input** → đó là **Strategy** chứ không State.
- Số state không xác định, sinh động → **state machine library** (`transitions`, `XState`) phù hợp hơn.
- State có **N×M chiều orthogonal** (ví dụ: WiFi state × Battery state × Auth state) → state explosion. Dùng **HSM (Hierarchical State Machine, Harel statecharts)** với regions.
- Khi state = data thuần (không có behavior khác nhau) → chỉ cần struct/dataclass.

### 1.5. Cảnh báo architect

> **State explosion**: nếu thêm 1 chiều orthogonal mới = nhân số state lên. 5 state × 4 chiều = 625 (gần đó). Đây là lý do Harel phát minh **statecharts** với composite states + parallel regions. Khi state nhiều hơn 7-8, cân nhắc HSM hoặc state machine declarative (XState).

> **State pattern không miễn phí transition logic**. Bạn vẫn phải quyết: state nào tự transition, state nào để Context quyết. Mỗi cách có trade-off: state-driven transitions linh hoạt nhưng coupling state ↔ state; context-driven tập trung nhưng Context phình to. Có **table-driven** (dict transitions) là middle ground.

---

## MỨC 2 — ALGORITHM

### 2.1. Vai diễn

```
┌─────────────────────────┐         ┌──────────────────────┐
│       Context           │ delegate│      State           │
│ (e.g. SleepingBrain)    │────────▶│   (interface)        │
│                         │         │ + on_enter(ctx)      │
│ - _state: State         │         │ + on_exit(ctx)       │
│ + set_state(s)          │         │ + process_input(ctx, x)
│ + handle_input(x)       │         │ + tick(ctx, dt)      │
│ + tick(dt)              │         └──────────────────────┘
└─────────────────────────┘                  △
                                              │
        ┌────────────┬─────────────┬──────────┴─────┬──────────────┐
   ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
   │  Wake   │ │ NREM1    │ │ NREM2    │ │ NREM3    │ │   REM    │
   └─────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

- **Context**: object chính. Giữ field `_state`. Mọi public method delegate cho state.
- **State interface**: methods chung cho tất cả state. Có thể có `on_enter` / `on_exit` (entry/exit actions).
- **ConcreteState**: implement logic riêng. Có thể gọi `ctx.set_state(NewState())` để self-transition.
- **Transitions**: 2 lựa chọn — state tự transition, hoặc Context quyết dựa trên kết quả từ state.

### 2.2. Luồng điều khiển

```
brain.handle_input("loud_sound")
       │
       ▼  delegate
self._state.process_input(self, "loud_sound")
       │
       ├─ if isinstance(self._state, NREM1State):
       │      ctx.set_state(WakeState())
       │      # on_exit cũ + on_enter mới
       │
       ├─ if isinstance(self._state, NREM3State):
       │      pass  # tiếng nhỏ → không tỉnh
       │
       └─ if isinstance(self._state, REMState):
              # incorporate vào dream
```

### 2.3. Biến trạng thái và bất biến

- **Context giữ** state hiện tại + có thể giữ history (state stack — pushdown automaton).
- **State có thể stateless** (singleton, không lưu data) — tiết kiệm memory; hoặc stateful (mỗi instance lưu data riêng).
- **Invariant**: chỉ Context **chính chủ** mới gọi `set_state` (qua state hoặc trực tiếp). Đừng để observer ngoài đổi state.
- **on_enter / on_exit phải idempotent + không raise** — nếu raise giữa transition, Context có thể kẹt nửa state.
- **Transition phải atomic**: hoặc xong, hoặc rollback. Quan trọng nếu có DB/network side effect.

### 2.4. Biến thể

| Biến thể | Mô tả | Khi nào dùng |
|----------|-------|--------------|
| **Stateless states (singleton)** | Mỗi state là 1 instance dùng chung | State không lưu data riêng; tiết kiệm memory |
| **Stateful states** | Mỗi lần vào state = new instance | Cần lưu data trong state (timer, counter) |
| **Context-driven transitions** | Context quyết từ kết quả state | Logic transition tập trung, dễ debug |
| **State-driven transitions** | State tự gọi `ctx.set_state` | Linh hoạt, state self-contained |
| **Table-driven (transition table)** | Dict `{(state, event): next_state}` | Khi transition đơn giản, declarative |
| **HSM / Statecharts (Harel)** | State có sub-states, parallel regions | State explosion, UI flow phức tạp |
| **Immutable state objects** | `set_state` tạo Context mới | Functional style, time-travel |
| **State machine library** | `transitions`, `python-statemachine` | Có DSL, visualize, persistence |

### 2.5. State vs Strategy — phân biệt rõ

Cả hai cùng "delegate cho object khác", nhưng intent khác:

| Khía cạnh | Strategy | State |
|-----------|----------|-------|
| Ai chọn? | Client (từ ngoài) | Object tự (theo lifecycle) |
| Khi nào đổi? | Hiếm — set một lần, dùng lâu | Thường xuyên — phản ứng event |
| Object có "biết" mình đang ở state? | Không — dùng strategy như thuộc tính | Có — state là một phần identity |
| Có transitions giữa? | Không — strategy độc lập | Có — state machine |
| Ví dụ | Sort: bubble vs quick (do dev chọn) | Order: cart → paid → shipped (do flow chọn) |

Não dùng cả hai:
- **Strategy**: dual-route fear — low road (thalamo-amygdala) vs high road (cortex-amygdala). Cùng input → 2 strategy chọn theo nhu cầu speed/accuracy.
- **State**: sleep stages — không "chọn" stage; nó tự cycle theo homeostatic + circadian.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
abstract class SleepState:
    on_enter(ctx)
    on_exit(ctx)
    process_input(ctx, stimulus): handler riêng
    tick(ctx, dt): có thể tự transition

class WakeState extends SleepState:
    process_input(ctx, stim):
        # phản ứng tức thì
        ...
    tick(ctx, dt):
        ctx.awake_time += dt
        if ctx.awake_time > sleep_pressure_threshold:
            ctx.set_state(NREM1State())

class NREM1State extends SleepState:
    process_input(ctx, stim):
        if stim.loudness > 0.3:
            ctx.set_state(WakeState())
    tick(ctx, dt):
        ctx.in_state_time += dt
        if ctx.in_state_time > 5:
            ctx.set_state(NREM2State())

class Brain (Context):
    private _state: SleepState
    set_state(s):
        self._state.on_exit(self)
        self._state = s
        self._state.on_enter(self)
    handle_input(stim):
        self._state.process_input(self, stim)
    tick(dt):
        self._state.tick(self, dt)
```

### 3.2. Python — 3 ví dụ

Code ở `20_state.py`. Tóm tắt:

#### Ví dụ 1 — Vận hành thường: SleepCycleBrain (W → NREM1→2→3→2 → REM → ...)

5 state: `WakeState`, `NREM1State`, `NREM2State`, `NREM3State`, `REMState`. Mỗi state implement:
- `process_stimulus(ctx, stimulus)`: phản ứng input (loud sound, light, alarm).
- `tick(ctx, dt)`: tiến thời gian. Tự transition khi đủ điều kiện.
- `on_enter` / `on_exit`: log, set physiological flags (atonia khi vào REM, glymphatic khi vào NREM3).

Demo:
- 1 đêm 8h được simulate trong vài giây (time scaling).
- In ra cycle: W → NREM1 → NREM2 → NREM3 → NREM2 → REM → ... lặp 4-5 chu kỳ.
- Inject sự kiện ngoài (alarm clock, loud noise) ở các stage khác nhau, quan sát phản ứng khác nhau.

Đặc điểm code:
- `SleepState` là abstract base class.
- States là **stateless singletons** — `WAKE = WakeState()`. Tiết kiệm memory.
- Context (`SleepCycleBrain`) giữ thời gian trong stage, awake debt.
- Transitions có **guard**: không cho REM trực tiếp từ Wake (must go through NREM2 first).

#### Ví dụ 2 — Hỏng / thiếu: 3 failure modes

- **2a — `if/elif` anti-pattern**: cùng logic viết bằng if/elif. Đếm số dòng, đếm số chỗ phải sửa khi thêm state mới.
- **2b — Forgotten transition (state lock-in)**: 1 state quên `set_state` → kẹt vĩnh viễn. Detect bằng test "không state nào là sink".
- **2c — Invalid transition (REM từ Wake)**: mô phỏng narcolepsy — REM xâm nhập trực tiếp từ Wake, không qua NREM. Demo guard chống được.

#### Ví dụ 3 — Ứng dụng Ellumm: LessonViewState với guards

Pipeline học một lesson: `Idle → Reading → Quiz → Reviewing → Completed` + có thể quay lại `Reading` từ `Reviewing`. Có guard:
- Không cho vào `Quiz` nếu chưa scroll hết lesson (guard `is_lesson_read >= 0.9`).
- Không cho `Completed` nếu quiz score < 0.7.
- `Reviewing` chỉ available sau khi đã làm Quiz.

Cùng code chạy production-grade với:
- Entry/exit actions: vào `Quiz` → log analytics, exit → save score.
- State persistence: serialize state name + Context data → có thể resume sau N ngày.
- Transition log: full audit trail.

---

## SO SÁNH VỚI PATTERN KHÁC

| Pattern        | Khác biệt với State                                                                       |
|----------------|--------------------------------------------------------------------------------------------|
| **Strategy**   | Strategy: client chọn behavior từ ngoài. State: object tự chọn theo lifecycle. Cấu trúc gần giống, intent khác. |
| **Memento**    | Memento lưu snapshot state. State pattern thay đổi behavior theo state hiện tại. Có thể combine: Memento snapshot Context + State. |
| **Command**    | Command đóng gói operation. State đóng gói behavior cluster. Một command có thể trigger transition. |
| **Observer**   | Observer broadcast event. State có thể trigger Observer khi vào state mới (`on_enter` notify). Bổ sung. |
| **Visitor**    | Visitor: 1 op qua N node. State: 1 object thay behavior theo state. Khác hoàn toàn. |
| **Interpreter (AST)** | AST node có behavior khác per type. State có behavior khác per state. AST = static tree of types; State = dynamic stage of one object. |

> **Insight architect**: nhìn yêu cầu "object có thể ở các state khác nhau" — đầu tiên hỏi: _state có behavior khác không, hay chỉ data khác?_. Nếu chỉ data khác → enum + dataclass. Nếu behavior khác → State. Nếu state có sub-state hoặc parallel regions → HSM. Nếu state machine cần visualize/persist/audit → state machine library.

---

## ANTI-PATTERNS THƯỜNG GẶP

1. **State explosion** — mỗi chiều orthogonal nhân số state lên (5 × 4 × 3 = 60).
   - Triệu chứng: thêm 1 dimension = code 100+ class state mới.
   - Xử lý: HSM với composite states + parallel regions (Harel statecharts). Hoặc tách thành nhiều state machine song song, mỗi cái 1 chiều.

2. **State biết quá nhiều về Context** — state truy cập field private cụ thể của Context.
   - Triệu chứng: refactor Context phá tất cả state.
   - Xử lý: Context expose API trung lập (`ctx.set_arousal_level(0.3)`), state dùng API đó, không truy cập field trực tiếp.

3. **Transition không có guard** — nhảy state vô tội vạ.
   - Triệu chứng: invalid state combo, business invariant bị phá.
   - Xử lý: predicate guard trước khi `set_state`. Hoặc transition table `{(from, event): (guard_fn, to_state)}`.

4. **on_enter / on_exit raise** — transition bị kẹt nửa chừng.
   - Triệu chứng: state field đã đổi nhưng resource cũ chưa cleanup.
   - Xử lý: `on_exit` không bao giờ raise (catch + log). Dùng try/finally trong `set_state`.

5. **Forgotten state** — thêm state mới nhưng quên handle ở 1 method.
   - Triệu chứng: NotImplementedError runtime, hoặc behavior fall-through sai.
   - Xử lý: abstract method ép implement. Hoặc `match-case` exhaustive check (Python 3.10+).

6. **Singleton state với mutable field** — 2 Context cùng dùng singleton WakeState với data mâu thuẫn.
   - Triệu chứng: race condition, data leak giữa Context.
   - Xử lý: state stateless (hoàn toàn), hoặc per-Context instance.

7. **Context-driven + state-driven trộn lẫn** — không quy ước rõ ai đổi state.
   - Triệu chứng: bug "state sai" khó debug vì nhiều chỗ set.
   - Xử lý: chọn 1 cách duy nhất + audit log mọi `set_state` với stack trace.

---

## BÀI TẬP

1. **Cơ bản**: Thêm state `Hypnagogic` vào sleep cycle (giữa Wake và NREM1) — vừa tỉnh vừa mơ. Đảm bảo không sửa state cũ. Test: từ Wake → Hypnagogic → NREM1 đúng thứ tự.

2. **Trung bình**: Refactor một function 100 dòng có if/elif trên `order_status` ("cart"/"paid"/"shipped"/"delivered"/"cancelled") thành State pattern. Đo: số dòng giảm, số class tăng. Bonus: tách entry/exit action (gửi email khi paid → shipped).

3. **Khó (architect)**: Cài **Hierarchical State Machine** cho nhân vật game:
   - Top-level: `Alive`, `Dead`.
   - Trong `Alive`: `Idle`, `Walking`, `Running`, `Attacking`.
   - Trong `Walking`: `WalkingNorth`, `WalkingSouth`, ... (4 hướng).
   - Parallel region: `WeaponState` (Sheathed / Drawn) song song với movement state.
   - Test: nhân vật chết khi đang `Running` → exit Running → exit Alive (cleanup ammo) → enter Dead (drop loot).

4. **Mở rộng neuro**: Mô phỏng narcolepsy — REM xâm nhập từ Wake không qua NREM. Implement guard chống. Mô phỏng "REM rebound" — nếu thiếu REM nhiều ngày thì cycle ưu tiên REM. Đây là cơ chế homeostatic — code: thêm `rem_debt` counter, transition logic dùng nó.

   Bonus: simulate **alpha intrusion** — alpha wave Wake xâm nhập NREM3, gây sleep "không sâu" (fibromyalgia). Code: thêm `intrusion_level` parameter, behavior `process_stimulus` thay đổi theo.

---

## PYTHON-NATIVE: Enum + dispatch table, `match-case`, transitions library

### Enum + dispatch table (đơn giản nhất)
Khi state ít, behavior đơn giản:
```python
from enum import Enum, auto

class Stage(Enum):
    WAKE = auto()
    NREM1 = auto()
    NREM2 = auto()
    NREM3 = auto()
    REM = auto()

DISPATCH = {
    Stage.WAKE:  lambda ctx, x: ctx.handle_wake(x),
    Stage.NREM1: lambda ctx, x: ctx.handle_nrem1(x),
    ...
}
```
Vẫn có if/elif ngầm trong dict — chỉ gọn về cú pháp. Khi behavior phức tạp → quay lại class State.

### `match-case` (Python 3.10+)
```python
match self.stage:
    case Stage.WAKE:    return process_wake(x)
    case Stage.NREM1:   return process_nrem1(x)
    case Stage.NREM2:   return process_nrem2(x)
```
Vẫn là if/elif đẹp hơn; không scale tốt khi thêm state.

### Library `transitions`
```python
from transitions import Machine

states = ['wake', 'nrem1', 'nrem2', 'nrem3', 'rem']
transitions = [
    {'trigger': 'fall_asleep', 'source': 'wake',  'dest': 'nrem1'},
    {'trigger': 'deepen',      'source': 'nrem1', 'dest': 'nrem2'},
    ...
]
machine = Machine(model=brain, states=states, transitions=transitions, initial='wake')
brain.fall_asleep()  # auto-method
```
Pros: declarative, có visualize (graphviz), có persistence, hỗ trợ HSM. Cons: thêm dependency, "magic" hơn.

> Quy tắc architect: <5 state, behavior đơn giản → enum/match. 5-15 state có behavior phức tạp → State pattern bằng class. >15 state hoặc cần HSM/visualize/persistence → library hoặc custom DSL.

---

## CHECKLIST TRƯỚC KHI MERGE PR DÙNG STATE PATTERN

- [ ] Có thực sự nhiều state với **behavior** khác (không chỉ data) không?
- [ ] State interface có **đầy đủ** các method cần (process_input, tick, on_enter, on_exit)?
- [ ] State có **stateless / singleton** được không (tiết kiệm memory)?
- [ ] Có **guard** trước transition cho các state có business invariant?
- [ ] Có **on_exit không bao giờ raise** (try/finally trong `set_state`)?
- [ ] Có **audit log** mỗi transition (state_from → state_to + lý do)?
- [ ] Có test cho **mỗi transition path** (kể cả invalid)?
- [ ] Có **cycle detection** nếu transition có thể loop (A → B → A → ...)?
- [ ] Khi state nhiều hơn 7-8 — đã cân nhắc HSM hoặc state machine library?
- [ ] Có cần **persist state qua restart** (DB/disk)? Cần serialize state name + context data.

---

## TÓM LẠI BẰNG NEUROSCIENCE

> Não đã giải bài toán "cùng một hệ làm nhiều job tách biệt" bằng cách **tách theo thời gian, không tách theo thực thể**: cùng não, các stage khác nhau cho memory consolidation (NREM2/3), glymphatic clearance (NREM3), emotional integration (REM), executive (Wake). Mỗi stage có cùng cấu trúc neuron, cùng "API input/output", nhưng **logic neural hoàn toàn khác**.

> Quan trọng nhất: **transitions có quy luật**. Não không nhảy thẳng từ Wake sang REM (trừ khi narcolepsy = bug). NREM3 phải xảy ra trước REM. Đó là **state machine với guards** thuần khiết. Khi designer code phớt lờ guard, hậu quả tương đương narcolepsy: state chuyển bậy, business invariant phá vỡ.

> Bệnh lý của sleep dạy chúng ta về anti-pattern code: narcolepsy = invalid transition. Insomnia = stuck Wake (state lock-in). Sleep paralysis = REM atonia leak sang Wake (state đã đổi nhưng cleanup chưa xong = forgotten on_exit). Mỗi case tương ứng một bug pattern khi triển khai State.

> Architect khôn ngoan biết: State pattern là chìa khoá khi có _nhiều state với behavior khác nhau_, nhưng phải đề phòng **state explosion** (HSM giúp), **forgotten transitions** (abstract method ép), **on_exit raise** (try/finally), và **invalid transitions** (guards). Khi state >7-8 → cân nhắc state machine library hoặc declarative DSL — đừng tự dựng nếu hệ thống thật sự lớn.

Lesson kế tiếp đề xuất: **21 — Strategy (Dual-route fear: low road vs high road)** — pattern đối xứng với State nhưng chọn từ ngoài. LeDoux's dual-route fear là analog không thể đẹp hơn.
