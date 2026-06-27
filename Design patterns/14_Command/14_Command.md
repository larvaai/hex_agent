# Lesson 14 — Command (Lệnh đóng gói thành object)

> **Một câu chốt:** *Đóng gói một **lời gọi method** thành một **object** — để có thể queue, log, undo, replay, macro, schedule, hoặc gửi qua mạng — mà invoker KHÔNG biết về receiver.*

---

## I. Bản đồ nhanh

| Khía cạnh | Command |
|---|---|
| **Loại** | Behavioral |
| **Vấn đề giải quyết** | Cần parameterize, queue, undo, log, hoặc replay các action |
| **Nguyên lý cốt lõi** | Action = object có `execute()` + (tùy chọn) `undo()` |
| **Anti-pattern thay thế** | Client gọi trực tiếp receiver.method() → không undo được, không queue được |
| **Ví dụ neuroscience** | Motor planning: SMA → PMC → M1 → spinal cord. Mỗi action là 1 motor program |
| **Họ hàng dễ nhầm** | Strategy (chọn 1 algorithm), Observer (notify), Memento (snapshot) |

---

## II. Three-Level Presentation

### Level 1 — Concept (Vì sao cần Command?)

**Tình huống đời thật trong não — đường vận động:**

Khi bạn với tay lấy ly nước, não KHÔNG kích hoạt từng cơ một cách trực tiếp. Một chuỗi cấu trúc đóng gói "ý định → lệnh → thực thi → kiểm tra":

```
[Pre-SMA / SMA]            ← lập kế hoạch hành động phức tạp ("vươn tay phải, mở ngón")
       |                      sinh ra một MOTOR PROGRAM (object trừu tượng)
       v
[Basal Ganglia]            ← INVOKER: gate, chọn motor program nào được phép thực thi
       |                      ức chế các program khác (winner-take-all)
       v
[Premotor Cortex (PMC)]    ← dịch program → muscle synergy
       |
       v
[Primary Motor Cortex (M1)] ← gửi spike train xuống tủy sống
       |
       v
[Spinal Motor Neurons]     ← RECEIVER: kích hoạt cơ thực sự
       |
       v
[Muscle contraction]
       |
       v (afferent feedback)
[Cerebellum]               ← COMPARATOR: so sánh expected vs actual,
                              sinh "correction command" ngược lại để chỉnh
```

**Quan sát quan trọng:**

1. **SMA không trực tiếp gọi cơ.** Nó tạo ra "object" mô tả hành động. Hệ thống phía sau diễn dịch và thực thi.

2. **Có thể QUEUE:** Khi bạn đánh máy 10 ký tự liên tiếp, SMA encode thành sequence command, đẩy vào queue, M1 lần lượt thực thi.

3. **Có thể UNDO:** Cerebellum so sánh kết quả với target. Nếu lệch (overshoot) → tạo lệnh ngược chiều để correct.

4. **Có thể MACRO:** "Buộc dây giày" = chuỗi 30+ subcommand được encode thành 1 macro program (procedural memory ở basal ganglia + cerebellum).

5. **Có thể LOG/REPLAY:** Procedural learning — lặp lại motor command nhiều lần để consolidate (như tập piano).

6. **Decoupling:** SMA không cần biết ngón nào, cơ nào — chỉ encode "with reach right hand to (x,y,z)". M1 + spinal cord lo phần dịch.

> **Insight architect:** Command pattern xuất hiện **bất cứ khi nào bạn cần đưa "hành động" thành **first-class citizen** — passable, queueable, reversible, composable**. Trong não, đây là nền tảng của **motor learning, sequence behavior, và imagination** (mental simulation = chạy command mà không thực thi).

---

### Level 2 — Algorithm (5 Chiều)

```
[Client]
   |
   | 1. tạo command với receiver + params
   v
[Command (interface)]              ← execute(), undo()
   ^
   |
[ConcreteCommand]                  ← lưu receiver, params, prev_state
   |
   | 2. invoker.submit(command)
   v
[Invoker]                          ← queue, history (undo stack)
   |
   | 3. command.execute() → receiver.action(params)
   v
[Receiver]                         ← muscle, file, db, ...
```

**5 Chiều:**

1. **Composition:**
   - `Command`: interface với `execute()`, optional `undo()`.
   - `ConcreteCommand`: bind tới receiver + params; lưu state trước thực thi cho undo.
   - `Receiver`: object thực sự làm việc.
   - `Invoker`: nhận command, có thể queue/log/replay.
   - `Client`: assemble Command + Receiver + đẩy Invoker.

2. **Location:**
   - Undo/redo trong editor.
   - Job queue (Celery, RabbitMQ tasks).
   - Macro recording.
   - Transaction (db rollback).
   - Remote procedure call (RPC).
   - GUI button → command (different button trigger same command).

3. **Function:**
   - Decouple invoker ↔ receiver.
   - Cho phép queueing, scheduling, logging, undo, replay, macro.
   - Hỗ trợ **command pattern as message** trong distributed systems.

4. **Connections:**
   - **Composite + Command** = MacroCommand (sequence).
   - **Memento** lưu snapshot để command undo được.
   - **Strategy** khác: Strategy chọn 1 algorithm tại 1 điểm; Command đóng gói 1 action.
   - **Observer** khác: Observer là notify; Command là execute.

5. **Meaning:**
   - Hành động trở thành **dữ liệu** — có thể store, transmit, manipulate.
   - Mở ra: **temporal decoupling** (đặt command bây giờ, thực thi sau), **spatial decoupling** (gửi command qua mạng).

**Pseudocode:**

```
interface Command:
    execute()
    undo()

class MoveCommand implements Command:
    def __init__(self, receiver, dx, dy):
        self.receiver = receiver
        self.dx, self.dy = dx, dy
        self.prev = None
    def execute(self):
        self.prev = (receiver.x, receiver.y)
        receiver.move(self.dx, self.dy)
    def undo(self):
        receiver.set(*self.prev)

class Invoker:
    def __init__(self):
        self.history = []
    def submit(self, cmd):
        cmd.execute()
        self.history.append(cmd)
    def undo_last(self):
        cmd = self.history.pop()
        cmd.undo()
```

---

### Level 3 — Implementation

#### A. Anti-pattern: Client gọi trực tiếp receiver

```python
class Editor:
    def __init__(self):
        self.text = ""
    def insert(self, s): self.text += s
    def delete(self, n): self.text = self.text[:-n]

# Client
editor = Editor()
editor.insert("hello")
editor.delete(2)
# ❌ Không undo được. Không queue. Không log.
```

#### B. Pattern đúng

```python
class Command(ABC):
    @abstractmethod
    def execute(self): ...
    @abstractmethod
    def undo(self): ...

class InsertCommand(Command):
    def __init__(self, editor, s):
        self.editor, self.s = editor, s
    def execute(self): self.editor.text += self.s
    def undo(self): self.editor.text = self.editor.text[:-len(self.s)]

class Invoker:
    def __init__(self): self.history = []
    def submit(self, cmd):
        cmd.execute()
        self.history.append(cmd)
    def undo(self):
        if self.history: self.history.pop().undo()
```

#### C. Macro (Composite + Command)

```python
class MacroCommand(Command):
    def __init__(self, cmds): self.cmds = cmds
    def execute(self):
        for c in self.cmds: c.execute()
    def undo(self):
        for c in reversed(self.cmds): c.undo()  # ← reverse order!
```

#### D. Cerebellar comparator

```python
class CerebellarComparator:
    def __init__(self, target_predictor):
        self.target_predictor = target_predictor
    def correct(self, command, actual):
        expected = self.target_predictor(command)
        error = actual - expected
        if abs(error) > tolerance:
            return CorrectionCommand(receiver, -error * gain)
        return None
```

#### E. Ellumm Application

`ActionCommand` cho mọi thao tác mà Ellumm agent thực hiện: `RecallEpisodeCommand`, `EncodeMemoryCommand`, `GenerateResponseCommand`, `ScheduleTaskCommand`. Lợi ích:
- **Undo:** rollback memory write nếu downstream fail.
- **Log:** mọi action được persist → audit trail.
- **Replay:** replay log để debug agent behavior.
- **Macro:** complex behavior = sequence of atomic commands.

---

## III. Failure Cases

### Sinh học: Apraxia (Ideomotor / Ideational)

Tổn thương SMA / parietal cortex → bệnh nhân **biết mình muốn làm gì**, **biết object** (e.g., bàn chải đánh răng), nhưng **không thể formulate motor command đúng**. Yêu cầu "vẫy tay chào" → tay đập lung tung.

**Bài học code:** Nếu Command class không capture đủ context (params), execute sẽ làm sai. Đảm bảo command IMMUTABLE và có đủ state.

### Sinh học: Parkinson's Disease

Basal ganglia (invoker) thoái hóa → khó **initiate** command. Bệnh nhân muốn đi nhưng "freeze". Khi đã start → vẫn đi được.

**Bài học code:** Invoker là single point of failure. Nếu invoker chết, mọi command nằm trong queue không thực thi được. Cần redundancy.

### Sinh học: Cerebellar Ataxia

Cerebellum hỏng → không có comparator → không có correction → motor commands overshoot/undershoot/dysmetria.

**Bài học code:** Command nên có cơ chế kiểm tra kết quả (post-condition). Nếu kết quả khác expected → trigger undo hoặc compensation.

### Code: Stale state trong undo

```python
class BadDeleteCommand(Command):
    def __init__(self, editor, n): self.editor, self.n = editor, n
    def execute(self): self.editor.text = self.editor.text[:-self.n]
    def undo(self): self.editor.text += "?" * self.n  # ❌ không nhớ ký tự đã xóa
```

**Bài học:** undo phải khôi phục CHÍNH state — phải snapshot trước execute.

### Code: Macro undo sai thứ tự

```python
class BadMacro(Command):
    def undo(self):
        for c in self.cmds:  # ❌ phải reversed!
            c.undo()
```

**Bài học:** Undo macro phải reverse order. Như "rửa tay rồi mở vòi" undo phải "đóng vòi rồi rút tay khỏi nước".

---

## IV. So sánh với pattern họ hàng

| Pattern | Action là object? | Có undo? | Có queue? | Có receiver decouple? |
|---|---|---|---|---|
| **Command** | Có | Có (tùy chọn) | Có | Có |
| **Strategy** | Algorithm là object | Không | Không | Không (caller biết) |
| **Observer** | Event là object | Không | Có (event queue) | Có |
| **Memento** | State là object | Implicit | Không | Không |
| **Iterator** | Traversal | Không | Không | Có (collection) |

> **Bẫy phổ biến:** Nhầm Command với Strategy. Khác biệt: **Strategy** = "làm việc X bằng cách nào?", **Command** = "tôi muốn thực hiện X (đóng gói)".

---

## V. Self-test (5 câu)

1. **Vì sao SMA → M1 minh họa Command tốt hơn Strategy?**

2. **Cho macro `[Insert("hello"), BoldText, ChangeColor]`. Khi undo, thứ tự đúng là gì? Tại sao?**

3. **Tại sao Command nên IMMUTABLE sau khi tạo? Cho ví dụ bug nếu mutable.**

4. **Phân biệt Command queue và Event queue (Observer).**

5. **Làm sao để Command hỗ trợ "redo"? Cần thêm gì vào Invoker?**

---

## VI. Tóm tắt cho architect

> *"Khi action cần là first-class citizen — passable, queueable, reversible, replayable — dùng Command. Khi chỉ cần chọn 1 algorithm — dùng Strategy. Đừng nhét logic undo vào client; đặt vào Command. Đừng quên reverse order trong macro undo. Cerebellum đã làm điều này 500 triệu năm rồi."*

**Checklist:**
- [ ] Command có đầy đủ context để execute độc lập?
- [ ] Command IMMUTABLE sau __init__?
- [ ] Có lưu prev_state trước execute để undo chính xác?
- [ ] MacroCommand undo theo thứ tự ngược?
- [ ] Invoker có history limit để tránh memory leak?
- [ ] Có comparator (verify post-condition) cho command quan trọng?

---

**Tiếp theo: Lesson 15 — Interpreter** (ngữ pháp ngôn ngữ trong não — Broca's area + grammar tree; cách parse và evaluate biểu thức).
