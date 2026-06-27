# Lesson 18 — Memento Pattern
## Hippocampus — Snapshot episodic để hồi tưởng

---

## TÓM TẮT MỘT DÒNG

**Memento** = đóng gói state nội bộ của một object thành một "snapshot" mà bên ngoài không nhìn thấy được nội dung, để sau này có thể restore object về trạng thái đó — undo/redo, time-travel, transactional rollback.

> Khi bạn nhớ lại bữa cà phê chiều thứ năm tuần trước với một người bạn, **hippocampus** đang làm Memento pattern: nó đã encode một "engram" (snapshot có cả không gian, thời gian, cảm xúc, người) lúc đó, lưu trữ qua quá trình **consolidation**, và lúc bạn gợi nhớ một mảnh nhỏ (mùi cà phê) thì **pattern completion** ở CA3 restore lại toàn bộ episode. Bệnh nhân H.M. (mất hippocampus) vẫn nhớ trí nhớ cũ, nhưng **không tạo được memento mới** — đó chính xác là analog của một caretaker đầy stack memento cũ nhưng không thể `save()` thêm.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Bạn cần lưu **state nội bộ** của một object để sau này restore — undo, redo, rollback, save game, time-travel debugging.

**Cách ngây thơ**: expose tất cả field qua getter/setter, caretaker đọc hết, nhớ, rồi set lại. **Vấn đề**:
- Phá encapsulation: caretaker biết cấu trúc bên trong → object không thể refactor.
- Caretaker dễ làm hỏng state: set field cá biệt mà bỏ qua invariant.
- Với object có 50 field, code save/restore ở caretaker là 100 dòng boilerplate.

**Memento**: object tự đóng gói state thành một "memento" opaque. Caretaker chỉ giữ memento, không inspect được. Khi restore, đưa memento lại cho object → object tự khôi phục.

Ba role rõ ràng:
- **Originator** (object cần save): có method `save() → Memento` và `restore(Memento)`.
- **Memento** (snapshot): trong sạch — không method ngoài việc giữ state.
- **Caretaker** (history holder): xếp memento vào stack/list, không bao giờ peek vào nội dung.

### 1.2. Neuroscience analogy — Hippocampus

**Hippocampus** (vùng dưới medial temporal lobe) là cấu trúc não đặc biệt cho memory **episodic** — trí nhớ "đã xảy ra ở đâu, khi nào, với ai".

Cấu trúc và pipeline:
- **Entorhinal cortex (EC)**: input/output gateway. Cortex → EC → hippocampus → EC → cortex.
- **Dentate gyrus (DG)**: pattern separation — biến trải nghiệm tương tự thành representation phân biệt (giống hash).
- **CA3**: auto-associative network — nơi engram (memory trace) được lưu, hỗ trợ **pattern completion** (cho cue → retrieve full).
- **CA1**: comparator + output — so sánh prediction (top-down) với reality (bottom-up).
- **Place cells** (O'Keefe, 1971) trong CA1/CA3: encode vị trí không gian.
- **Time cells** (Eichenbaum): encode thứ tự thời gian.
- **Grid cells** (EC): hệ tọa độ.

3 pha của episodic memory chính là 3 method của Memento:
1. **Encoding** = `originator.save()` → tạo engram.
2. **Consolidation** = caretaker giữ memento (chuyển từ hippocampus sang neocortex theo thời gian = serialize sang persistent storage).
3. **Retrieval** = `originator.restore(memento)` → CA3 pattern completion từ cue.

Bệnh nhân **H.M.** (Henry Molaison) — bị cắt 2 hippocampus năm 1953 để chữa epilepsy:
- Trí nhớ cũ vẫn còn (memento đã consolidate sang cortex trước phẫu thuật).
- Không tạo được trí nhớ mới (originator không save() được nữa).
- → Đây là analog hoàn hảo: caretaker còn nguyên với toàn bộ history cũ, nhưng `save()` bị disable.

#### 5 chiều của analogy

| Chiều      | Trong não                                                                                | Trong code                                                              |
|------------|------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| Cấu tạo    | Hippocampus (DG, CA3, CA1) + entorhinal cortex + place/time cells                        | Originator + Memento (snapshot opaque) + Caretaker (history)            |
| Vị trí     | Medial temporal lobe, kết nối cortex qua EC                                              | Tách khỏi business logic; caretaker không trong cùng class với originator|
| Chức năng  | Encode / consolidate / retrieve episodic memory; pattern completion từ partial cue       | save() → Memento; caretaker store; restore(memento) → trạng thái cũ     |
| Kết nối    | Cortex ↔ EC ↔ DG → CA3 → CA1 → EC ↔ Cortex                                             | Originator → Memento (capture); Caretaker → Memento (hold) → Originator (restore)|
| Ý nghĩa    | Cho phép experience-dependent learning, planning theo precedent                          | Cho phép undo, transaction rollback, time-travel, save game             |

### 1.3. Khi nào DÙNG

- Cần **undo / redo** trong editor, IDE, design tool, game.
- Cần **transactional rollback** — nếu thao tác fail giữa chừng, restore về trước.
- Cần **save game / checkpoint** — game state, AI training checkpoint.
- Cần **time-travel debugging** — Redux DevTools, debugger state replay.
- Cần **branching history** — explore "what if" scenario (git stash, AI search tree).
- Cần lưu state mà **không phá encapsulation** của Originator.

### 1.4. Khi nào KHÔNG DÙNG

- State quá lớn (GB scale) → snapshot full quá đắt. Dùng **diff / delta** hoặc **Command** lưu inverse op.
- State thay đổi rất tần số (hàng nghìn lần/giây) → snapshot mỗi lần = OOM. Dùng **persistent data structure** (structural sharing) hoặc **debounce**.
- Object nhỏ + ít state → trực tiếp deep copy đơn giản hơn pattern formal.
- State có **resource ngoài** (file handle, socket, DB connection) → memento không capture được. Cần thiết kế lại.
- Yêu cầu replay deterministic / audit chi tiết → **Event Sourcing** (lưu chuỗi event) tốt hơn Memento.

### 1.5. Cảnh báo architect

> **Memento ngược với Command về trade-off**. Memento: tốn memory (lưu full state), `restore()` rẻ (gán lại). Command: tốn CPU (replay/inverse), lưu rẻ (chỉ op + param). Chọn hướng nào tuỳ "state to op size ratio". Editor text với 1MB document, 1 keystroke change → Command thắng. Game save với cả map + entities → Memento thắng.

---

## MỨC 2 — ALGORITHM

### 2.1. Vai diễn

```
┌──────────────────────────┐         ┌─────────────────────┐
│       Originator         │ creates │      Memento        │
│                          │────────▶│  (opaque snapshot)  │
│ - state: Internal        │         │ - _state (private)  │
│ + save() → Memento       │         │                     │
│ + restore(m: Memento)    │◀────────│ getState() — chỉ    │
│                          │ uses    │   Originator gọi    │
└──────────────────────────┘         └─────────────────────┘
                                              ▲
                                              │ holds (không inspect)
                                     ┌─────────────────────┐
                                     │     Caretaker       │
                                     │ - history: [Memento]│
                                     │ + push / pop / peek │
                                     └─────────────────────┘
```

- **Originator** giữ state. Có `save()` tạo Memento, `restore(m)` set state từ Memento.
- **Memento** opaque — caretaker chỉ giữ tham chiếu, không gọi method nội dung. Trong Python không thật sự "private" được, nhưng convention `_state` hoặc dataclass frozen + dùng "narrow interface" giúp.
- **Caretaker** giữ history. Đẩy memento mới vào, pop khi undo, có thể giới hạn size.

### 2.2. Luồng điều khiển

```
User edits doc:
  doc.do_edit("hello")
    └─ caretaker.push(doc.save())   ← snapshot trước khi edit
    └─ apply edit
  doc.do_edit("world")
    └─ caretaker.push(doc.save())
    └─ apply edit

User undo:
  m = caretaker.pop()
  doc.restore(m)                    ← rollback

User redo:
  caretaker.push_redo(doc.save())
  m = caretaker.pop_redo()
  doc.restore(m)
```

### 2.3. Biến trạng thái và bất biến

- **Memento immutable**: tạo xong không sửa được. Nếu sửa được, ý nghĩa "snapshot" mất. Dùng `@dataclass(frozen=True)` hoặc tuple.
- **Memento phải là deep copy**: nếu chỉ giữ reference vào internal mutable structure của Originator, edit sau đó sẽ làm hỏng "snapshot". Trap rất phổ biến.
- **Caretaker không inspect**: chỉ store/retrieve. Vi phạm = phá encapsulation, biến memento thành DTO.
- **Memento bound với Originator type**: memento của `LessonEditor` không restore vào `QuizEditor`. Type-tagged.

### 2.4. Biến thể

| Biến thể | Mô tả | Khi nào dùng |
|----------|-------|--------------|
| **Full snapshot** | Memento = deep copy toàn state | State nhỏ, save tần số thấp |
| **Delta / incremental** | Memento = diff với snapshot trước (chỉ field changed) | State lớn, save tần số cao |
| **Persistent data structure** | State immutable + structural sharing → mỗi state là Memento miễn phí | Functional programming, Clojure, Immer.js, Redux |
| **Command (alternative)** | Lưu inverse op thay vì state | Op nhỏ, state lớn |
| **Event Sourcing** | Lưu chuỗi event, state = fold(events) | Distributed system, audit, CQRS |
| **Memento + Compression** | Snapshot lớn → gzip/zstd trước khi store | Save game, IDE workspace |
| **External serialization** | Memento serialize sang disk/DB → "consolidation" | Persist undo history qua restart |

### 2.5. Memento vs Command vs Event Sourcing — bảng kép

| Khía cạnh | Memento | Command (undo) | Event Sourcing |
|-----------|---------|----------------|----------------|
| Lưu cái gì | State snapshot | Inverse operation | Forward events |
| Restore = | Gán state lại | Replay inverse | Replay từ đầu hoặc snapshot+events |
| Memory cost | Cao (full state mỗi snapshot) | Thấp (op nhỏ) | Vừa (events) |
| CPU restore | Thấp (set) | Vừa (replay 1 op) | Cao (replay nhiều) |
| Branching | Dễ (giữ nhiều memento riêng) | Vừa (cây command) | Vừa (event branch) |
| Audit / replay | Yếu | Trung bình | Mạnh nhất |
| Use case điển hình | Save game, simple undo | Text editor, image edit | Banking, e-commerce, CQRS backend |

> **Quy tắc architect**: Bắt đầu bằng Memento cho prototype (đơn giản). Khi đo được bottleneck (memory hoặc save tần số) → chuyển sang Command. Khi cần audit / distributed / time-machine UX → Event Sourcing.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
class LessonEditor (Originator):
    private title: str
    private body: str
    private cursor: int
    
    save() -> Memento:
        return Memento(deep_copy({title, body, cursor}))
    
    restore(m: Memento):
        s = m._state    # chỉ Originator gọi (convention)
        self.title = s.title
        self.body = s.body
        self.cursor = s.cursor

class Memento (frozen):
    _state: dict   # chỉ Originator hiểu

class History (Caretaker):
    private undo_stack: List[Memento]
    private redo_stack: List[Memento]
    private max_size: int
    
    push(m: Memento):
        undo_stack.push(m)
        redo_stack.clear()       # mỗi action mới xoá redo
        if len(undo_stack) > max_size:
            undo_stack.pop_oldest()
    
    undo() -> Memento | None
    redo() -> Memento | None
```

### 3.2. Python — 3 ví dụ

Code chạy được ở `18_memento.py`. Tóm tắt:

#### Ví dụ 1 — Vận hành thường: LessonEditor undo/redo

`LessonEditor` có title, body, cursor. Mỗi edit (`type_text`, `set_title`, `move_cursor`) tự `save()` trước khi sửa. `History` giữ undo/redo stack có giới hạn.

Đặc điểm cần để ý:
- Memento là **frozen dataclass** + state cũng frozen (tuple thay vì list cho dễ ví dụ; production thường deep-copy mutable).
- Memento **không expose** field `state` ra ngoài — convention `_state` + `getter chỉ Originator gọi`.
- History có `max_size` để chống OOM.

#### Ví dụ 2 — Hỏng / thiếu: 3 failure mode

- **2a — Tampering**: caretaker peek + sửa memento → restore ra state lai căng. Chống bằng frozen dataclass.
- **2b — Shallow copy**: memento giữ reference vào list internal. Edit sau đó "rò" vào memento → snapshot không còn snapshot. Sửa = `deepcopy`.
- **2c — OOM**: save mỗi keystroke + history vô hạn → memory blow up. Sửa = ring buffer / max_size + structural sharing.

#### Ví dụ 3 — Ứng dụng architect: Memento vs Command vs PersistentState

Cùng 1 use case (text editor undo) cài 3 cách:

- **MementoEditor** (snapshot full): đơn giản, đắt memory.
- **CommandEditor** (lưu inverse op): rẻ memory, đắt CPU khi undo nhiều bước.
- **PersistentEditor** (state immutable + structural sharing): mỗi edit trả Editor mới, "memento" miễn phí — đó là lý do Redux có time-travel rẻ.

So sánh memory + CPU thực tế. Architect chọn cách nào tuỳ workload.

---

## SO SÁNH VỚI PATTERN KHÁC

| Pattern        | Khác biệt với Memento                                                                  |
|----------------|----------------------------------------------------------------------------------------|
| **Command**    | Command lưu _operation_ (cùng inverse). Memento lưu _state_. Trade-off bù trừ — Command tiết kiệm memory, Memento tiết kiệm CPU. Cùng giải bài toán undo theo hai góc. |
| **Prototype**  | Prototype clone object để tạo mới. Memento clone object để rollback. Cùng dùng deep-copy nhưng intent khác. |
| **State**      | State pattern thay đổi behavior theo state. Memento lưu state để restore. Trực giao. |
| **Snapshot Isolation (DB)** | MVCC (Multi-Version Concurrency Control) trong PostgreSQL/Oracle = Memento ở DB level. Mỗi transaction thấy snapshot nhất quán của data. |
| **Iterator**   | Iterator cursor có thể được "save" làm Memento để pause/resume duyệt. Bookmark trong file reader, paginated cursor. |

> **Insight architect**: Khi thấy yêu cầu "undo/redo", "save/load", "rollback", "branch", "what-if scenario" — phản xạ đầu tiên không phải "code Memento". Phản xạ là: _state có lớn không, op có inverse rõ không, có cần audit không?_ Câu trả lời quyết định Memento / Command / Event Sourcing.

---

## ANTI-PATTERNS THƯỜNG GẶP

1. **Shallow snapshot** — memento giữ reference vào mutable internal.
   - Triệu chứng: undo trả về state lai giữa cũ và mới.
   - Xử lý: `copy.deepcopy()` hoặc convert sang immutable structure (tuple, frozenset, frozen dataclass).

2. **Memento expose state** — caretaker đọc `memento.body` để debug.
   - Triệu chứng: refactor field trong Originator phá tất cả caretaker code.
   - Xử lý: convention `_state` + chỉ Originator có method đọc. Trong Java/C#, friend class. Trong Python, code review + lint.

3. **Unbounded history** — undo stack vô hạn → OOM.
   - Triệu chứng: editor edit lâu → app crash.
   - Xử lý: ring buffer, max_size, hoặc persist sang disk khi vượt threshold.

4. **Memento serialize fail vì có resource ngoài** — state có file handle, socket, thread.
   - Triệu chứng: pickle thất bại, hoặc restore xong resource chết.
   - Xử lý: tách "stateful core" khỏi "resource handle". Memento chỉ capture core. Resource re-acquire khi restore.

5. **Memento lệch schema** — code thay đổi, memento cũ load lại lỗi.
   - Triệu chứng: save game cũ không đọc được sau update.
   - Xử lý: version field trong memento + migration function. Đó là lý do mọi save game serious đều có `version: 1`, `version: 2`.

6. **Lưu memento cho mỗi keystroke** — debounce không có.
   - Triệu chứng: edit nhanh = 100 memento/giây.
   - Xử lý: gom theo word boundary / time window (vd: save mỗi 500ms idle hoặc khi gặp space).

---

## BÀI TẬP

1. **Cơ bản**: Mở rộng `LessonEditor` (ví dụ 1) thêm `delete_text(start, end)`. Đảm bảo undo hoạt động không sửa logic Memento. Test 5 thao tác liên tiếp + 3 undo + 2 redo.

2. **Trung bình**: Thêm **branching history** vào `History`. Khi undo rồi edit mới — thay vì xoá redo stack, tạo branch mới (cây). Cài `tree.list_branches()`, `tree.switch(branch_id)`. Đây là git internals đơn giản hoá.

3. **Khó (architect)**: Cài 3 phiên bản (Memento / Command / Persistent) trong ví dụ 3 với cùng API public. Benchmark:
   - Memory: 1000 edit, đo sizeof history.
   - CPU: undo 500 lần liên tiếp.
   - Branching: tạo 10 nhánh.
   - Vẽ bảng kết quả, thảo luận trade-off.

4. **Mở rộng neuro**: Mô phỏng "consolidation" — sau N giây, memento được "consolidate" từ hippocampus (in-memory) sang neocortex (disk/db). Memento cũ bị evict khỏi RAM. Khi restore, nếu cần memento cũ → load lại từ disk (lazy load + cache). Đây là pattern thực tế của save game / IDE workspace, và là analog chính xác của hippocampal-cortical consolidation thật.

   Bonus: mô phỏng **H.M. lesion** — disable `save()` (raise) nhưng giữ history cũ vẫn restore được. Quan sát hành vi hệ thống. So sánh với mô tả lâm sàng anterograde amnesia.

---

## PYTHON-NATIVE: copy.deepcopy, pickle, dataclasses, immutables

Python toolset cho Memento:
- **`copy.deepcopy(obj)`**: clone toàn bộ. Đơn giản, đúng, có thể chậm với object lớn.
- **`pickle.dumps(obj)`**: serialize sang bytes — Memento persistent. Cẩn thận: pickle không cross-version.
- **`dataclasses.replace(obj, field=new)`**: với frozen dataclass, "update" = tạo mới (immutable).
- **`copy.copy(obj)`**: shallow — KHÔNG dùng cho Memento (anti-pattern 1).
- **Library `immutables`** / **`pyrsistent`**: persistent data structures với structural sharing. Gần giống Clojure/Immer.

Pattern minimal Pythonic:
```python
from dataclasses import dataclass, replace
from copy import deepcopy

@dataclass(frozen=True)
class EditorState:
    title: str
    body: str
    cursor: int

class LessonEditor:
    def __init__(self):
        self._state = EditorState("", "", 0)
    def save(self): return deepcopy(self._state)        # dataclass frozen + immutable fields → có thể chỉ return self._state
    def restore(self, snap): self._state = snap
```

Vì `EditorState` immutable (frozen + str/int là immutable), `deepcopy` có thể bỏ. Đó chính là điểm hay của persistent state: memento miễn phí.

---

## CHECKLIST TRƯỚC KHI MERGE PR DÙNG MEMENTO

- [ ] Memento là **immutable** (frozen dataclass / tuple / namedtuple)?
- [ ] Memento **deep-copy** mọi mutable internal, hay state đã immutable?
- [ ] Caretaker có **không inspect** memento internal (grep field access)?
- [ ] History có **bounded size** chống OOM?
- [ ] Có **debounce** save khi user thao tác nhanh?
- [ ] Có **version field** trong memento để migration?
- [ ] Memento có capture **resource ngoài** (file, socket) không, nếu có thì có re-acquire khi restore?
- [ ] Có tính chuyện **Command** thay Memento để tiết kiệm memory?
- [ ] Có tính chuyện **persistent data structure** để memento miễn phí?
- [ ] Test có cover: undo qua 0, undo full stack, undo rồi edit (xoá redo), serialize/deserialize?

---

## TÓM LẠI BẰNG NEUROSCIENCE

> Hippocampus đã giải bài toán "lưu trải nghiệm để hồi tưởng" qua hàng triệu năm tiến hoá: tách **encoding** (originator save), **consolidation** (caretaker store, dần chuyển sang cortex/disk), và **retrieval** (restore từ partial cue qua pattern completion). Place cells và time cells encode "where" và "when" — chính là metadata của một episodic memento.

> Bệnh nhân H.M. dạy chúng ta điều quan trọng: **mất khả năng tạo memento mới ≠ mất memento cũ**. Trong code, đó là sự độc lập giữa Originator (có thể hỏng) và Caretaker (history vẫn restore được). Đây là lý do bạn nên thiết kế Memento để **không phụ thuộc vào Originator còn sống** — pickle được, version có thể migrate.

> Persistent data structure (Clojure, Immer, Redux state) là **giấc mơ của hippocampus**: mọi state cũ đều immutable + share structure → không tốn nhiều memory, retrieve = O(1). Đó là vì sao Redux DevTools time-travel không lag — state không bao giờ bị mutate, mỗi action tạo state mới, history chỉ là một mảng các pointer. Đó cũng là cơ sở của **MVCC** trong PostgreSQL: mỗi transaction thấy snapshot nhất quán mà không lock.

> Architect học Memento là để biết: khi nào dùng full snapshot (đơn giản, prototype), khi nào dùng inverse Command (state lớn op nhỏ), khi nào dùng Event Sourcing (audit + distributed), và khi nào — sang nhất — chuyển toàn bộ state sang persistent data structure để "memento miễn phí".

Lesson kế tiếp: **19 — Observer (Amygdala salience broadcast)** — pattern đối xứng với Mediator. Amygdala phát tín hiệu salience cao → insula, HPA axis, motor cortex cùng react độc lập, không có routing logic tập trung.
