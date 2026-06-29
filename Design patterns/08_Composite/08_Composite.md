# Lesson 08 — Composite

> **Tổ chức object thành cấu trúc cây part-whole, để client xử lý đồng nhất single object và composite of objects.**

---

## Mức 1 — CONCEPT (Ý tưởng)

### Vấn đề pattern giải quyết

Bạn có cấu trúc phân cấp với phần tử đơn lẻ và nhóm phần tử. Client cần tính toán đệ quy lên cả cây:

```python
# ❌ Không có Composite — if-else lan toàn codebase
def total_activity(node):
    if isinstance(node, SingleNeuron):
        return node.firing_rate
    elif isinstance(node, Minicolumn):
        return sum(total_activity(n) for n in node.neurons)
    elif isinstance(node, CorticalColumn):
        return sum(total_activity(mc) for mc in node.minicolumns)
    elif isinstance(node, CorticalArea):
        return sum(total_activity(c) for c in node.columns)
    # ... mỗi cấp mới = thêm elif
    # Mỗi operation (fire, plasticity, count) = duplicate cấu trúc if-else này
```

Vấn đề:
1. **Mọi operation lặp lại cấu trúc if-else** — DRY bị phá.
2. **Thêm cấp mới** = sửa mọi function có if-else.
3. **Client phải biết** mọi loại node — coupling chặt.
4. **Đệ quy thủ công** dễ sai (forget recursion case).

Composite giải quyết bằng cách: **mọi cấp đều implement cùng interface**, đệ quy nằm bên trong Composite. Client chỉ gọi `node.total_activity()` — đúng với Leaf, đúng với Composite, đúng với Composite-of-Composite.

### Neuroscience analogy — Cortical Column Hierarchy

Mountcastle (1957) phát hiện cortex được tổ chức theo nguyên tắc cột — đơn vị xử lý cơ bản tổ chức theo phân cấp lồng nhau:

| Cấp | Quy mô | Chức năng |
|-----|--------|-----------|
| **Single neuron** | 1 cell | Đơn vị tính toán nhỏ nhất |
| **Minicolumn** | ~80-100 neurons, đường kính ~50μm | Tất cả neuron cùng response selectivity (vd: cùng orientation preference ở V1) |
| **Cortical column** (macrocolumn) | ~10.000 neurons, đường kính ~500μm | Tổ hợp minicolumn cùng nhóm chức năng (vd: ocular dominance column) |
| **Functional area** | V1, V2, A1, S1, M1, ... | Triệu neuron, khu vực chuyên môn hóa |
| **Cortical region** | Visual region, motor region, ... | Tổ hợp area liên quan |
| **Hemisphere** | Bán cầu trái/phải | Toàn bộ cortex 1 bên |

**Tính chất quan trọng**: ở mọi cấp đều có cùng "interface chức năng":
- `fire()` — phát signal (tổng hợp từ con).
- `receive_input(signal)` — nhận tín hiệu (phân phối xuống con).
- `apply_plasticity(rule)` — học (áp đệ quy).
- `total_activity()` — đo activity (tổng hợp đệ quy).

Khi neurologist nói "vùng V1 fire response cho stimulus", thực ra hàng triệu neuron, hàng nghìn minicolumn, hàng trăm column cùng fire — nhưng *concept* "V1 fire" đúng ở scale region. Đó là Composite ở mức tự nhiên: cùng động từ "fire" áp dụng được cho neuron đơn, column, hay region.

Điều này không phải tình cờ. Cấu trúc lồng cho phép:
- **Modular damage tolerance**: stroke phá 1 column, area vẫn chạy (resilience).
- **Local computation, global emergence**: mỗi minicolumn xử lý cục bộ, hành vi global emerge từ tổng hợp.
- **Scale-invariant interface**: nhà thần kinh học có thể nói "X fire" ở mọi scale.

### Cùng nguyên tắc ở các cấu trúc não khác

| Cấu trúc | Hierarchy | Interface chung |
|----------|-----------|-----------------|
| Cerebellum | Purkinje cell → microzone → zone → lobule | fire / receive climbing fiber / LTD |
| Hippocampus | Pyramidal cell → cluster → CA1/CA3 → entire hippocampus | encode / retrieve / replay |
| Basal ganglia | MSN → matrix/striosome → striatum → BG circuit | gating / dopamine modulation |
| Brainstem | Neuron → subnucleus → nucleus → reticular formation | autonomic output / arousal |

Mọi hệ này đều là Composite tự nhiên — giải thích tại sao não chịu được tổn thương cục bộ và tại sao chúng ta có thể nói chung chung "vùng X làm việc Y".

---

## Mức 2 — ALGORITHM (Thuật toán)

### Cấu tạo (5 chiều theo framework Ellumm)

| Chiều | Nội dung |
|-------|----------|
| **Cấu tạo** | (a) `Component` interface chung, (b) `Leaf` không có con, (c) `Composite` chứa nhiều `Component` (có thể là Leaf hoặc Composite khác) |
| **Vị trí** | Domain core nơi có cấu trúc cây/phân cấp tự nhiên (DOM, file system, org chart, scene graph, neural hierarchy) |
| **Chức năng** | Xử lý đồng nhất leaf vs composite, đệ quy đóng gói trong Composite. |
| **Kết nối** | Client → Component → (đệ quy xuống Leaf hoặc Composite con). |
| **Ý nghĩa** | Encapsulate đệ quy, tránh if-else theo type ở mọi operation. |

### Sơ đồ class

```
                  ┌─────────────────────────┐
                  │   NeuralUnit (Component)│
                  │  abstract               │
                  │ + fire(stimulus)        │
                  │ + total_activity()      │
                  │ + apply_plasticity(rule)│
                  │ + add(child)?           │← (transparent vs safe)
                  │ + remove(child)?        │
                  └────────┬────────────────┘
                           △
            ┌──────────────┴──────────────┐
            │                             │
   ┌────────┴────────┐         ┌──────────┴────────────┐
   │ SingleNeuron    │         │ NeuralComposite       │
   │   (Leaf)        │         │  - children: list     │
   │ - firing_rate   │         │ + fire(stim):         │
   │ - threshold     │         │     for c in children:│
   │                 │         │         c.fire(stim)  │
   └─────────────────┘         └───────────┬───────────┘
                                           △
                          ┌────────────────┼────────────────┐
                          │                │                │
                    ┌─────┴──────┐  ┌──────┴──────┐  ┌──────┴───────┐
                    │ Minicolumn │  │CorticalColumn│  │CorticalArea  │
                    └────────────┘  └─────────────┘  └──────────────┘
```

### Logic vận hành — đệ quy bên trong Composite

```
NeuralComposite.fire(stimulus):
    for child in self.children:
        child.fire(stimulus)         # đệ quy: child có thể là Leaf hoặc Composite

NeuralComposite.total_activity():
    return sum(child.total_activity() for child in self.children)

SingleNeuron.fire(stimulus):
    self.last_input = stimulus
    if stimulus * self.weight > self.threshold:
        self.firing_rate = ...

SingleNeuron.total_activity():
    return self.firing_rate
```

Client code:
```
v1_area = CorticalArea("V1", columns=[col1, col2, col3, ...])
v1_area.fire(stimulus_at_visual_field_origin)    # toàn bộ V1 fire
total = v1_area.total_activity()                  # tổng activity của V1
```

Client không cần biết V1 chứa column → minicolumn → neuron. Chỉ gọi method, đệ quy tự chạy.

### Transparency vs Safety — quyết định thiết kế

GoF mô tả 2 biến thể:

**Transparent Composite** (uniform interface):
```python
class NeuralUnit(ABC):
    @abstractmethod
    def fire(self, stim): ...
    @abstractmethod
    def add(self, child): ...        # ← cả Leaf cũng phải có
    @abstractmethod
    def remove(self, child): ...

class SingleNeuron(NeuralUnit):
    def add(self, child):
        raise InvalidOperation("Neuron không có con")  # hoặc no-op
```

Ưu: client treat leaf và composite hoàn toàn giống nhau.
Nhược: Leaf có method "không có ý nghĩa" — phải hoặc raise (kém uniform thật) hoặc no-op (silent bug).

**Safe Composite** (separated interface):
```python
class NeuralUnit(ABC):
    @abstractmethod
    def fire(self, stim): ...
    @abstractmethod
    def total_activity(self): ...

class NeuralComposite(NeuralUnit, ABC):     # subclass riêng cho composite
    @abstractmethod
    def add(self, child): ...
    @abstractmethod
    def remove(self, child): ...
```

Ưu: type-safe, Leaf không có method vô nghĩa.
Nhược: client cần check `isinstance(node, NeuralComposite)` khi muốn add/remove.

Trade-off: **Transparent đơn giản hơn cho client**, **Safe an toàn hơn về kiểu**. Python hiện đại thường dùng Safe + duck typing — chỉ Composite có `add/remove`, client chỉ gọi khi biết chắc đang ở Composite.

### Leaf operations vs Composite operations

Một số operations chỉ có nghĩa ở Leaf, một số chỉ ở Composite:

| Operation | Leaf | Composite |
|-----------|------|-----------|
| `fire(stim)` | Tính firing rate | Forward đến mọi con |
| `total_activity()` | Trả firing_rate | Sum đệ quy |
| `add(child)` | Vô nghĩa (raise hoặc no-op) | Add vào children |
| `find(name)` | Match self.name | Match self hoặc đệ quy children |
| `apply_plasticity(rule)` | Update weight cục bộ | Forward + có thể có rule cấp cao |

### Nguyên lý liên quan

- **Single Responsibility**: mỗi class chỉ chịu trách nhiệm cho cấp của mình.
- **Open-Closed**: thêm cấp mới = thêm Composite subclass, không sửa code đã có.
- **Liskov Substitution**: Leaf và Composite đều substitute cho Component ở client code.
- **Recursive uniformity**: cùng method định nghĩa ở mọi cấp.

---

## Mức 3 — PSEUDOCODE + PYTHON

### Pseudocode

```
abstract class NeuralUnit:
    abstract function fire(stimulus)
    abstract function total_activity() -> float
    abstract function find(name) -> NeuralUnit?

class SingleNeuron extends NeuralUnit:
    field firing_rate, threshold, weight, name

    function fire(stimulus):
        if stimulus * self.weight > self.threshold:
            self.firing_rate = compute(stimulus)
        else:
            self.firing_rate = 0

    function total_activity(): return self.firing_rate
    function find(name): return self if self.name == name else None

class NeuralComposite extends NeuralUnit:
    field children: list[NeuralUnit], name: str

    function fire(stimulus):
        for child in self.children:
            child.fire(stimulus)

    function total_activity():
        return sum(c.total_activity() for c in self.children)

    function find(name):
        if self.name == name: return self
        for child in self.children:
            result = child.find(name)
            if result is not None: return result
        return None

    function add(child): self.children.append(child)
    function remove(child): self.children.remove(child)
```

### Python (xem file `08_composite.py`)

File code triển khai:
1. **Anti-pattern** isinstance-based đệ quy.
2. **Component interface** `NeuralUnit` (Safe variant với separated `NeuralComposite`).
3. **Leaf**: `SingleNeuron` với firing rate, threshold, plasticity (Hebbian).
4. **Composite cấp 1**: `Minicolumn` (chứa SingleNeuron).
5. **Composite cấp 2**: `CorticalColumn` (chứa Minicolumn).
6. **Composite cấp 3**: `CorticalArea` (chứa CorticalColumn).
7. **Operations đệ quy**: `fire`, `total_activity`, `find_by_name`, `apply_hebbian`, `count_units_by_type`.
8. **Demo simulated stroke**: xóa 1 cortical column — area vẫn chạy với reduced output (resilience).
9. **Ellumm version**: `MemoryNode` hierarchy — atomic → cluster → episode → theme.

---

## 3 LOẠI VÍ DỤ

### Ví dụ 1 — Vận hành thường

Ánh sáng cường độ 0.7 ở vị trí (5°, 3°) thị trường tới mắt phải. Quy trình ở V1:
1. `v1_right_hemisphere.fire(stimulus)` được gọi.
2. V1 (Composite cấp 3) iterate qua các CorticalColumn — mỗi column responsible cho một patch thị trường.
3. Column phụ trách (5°, 3°) iterate qua các Minicolumn — mỗi minicolumn phụ trách một orientation preference.
4. Minicolumn phụ trách "horizontal edge" (vì stimulus có edge ngang) iterate qua các SingleNeuron — mỗi neuron có response curve hơi khác.
5. Neuron với weight phù hợp fire mạnh nhất.
6. Activity tổng hợp ngược lên: `total_activity()` ở minicolumn = sum of neurons; ở column = sum of minicolumns; ở V1 = sum of columns.

Một call `v1.fire(stim)`, hàng triệu neuron tham gia, đệ quy đóng gói gọn. Client code (cortical area V2 nhận output từ V1) chỉ gọi `v1.total_activity()` — không cần biết V1 có 36 column × 50 minicolumn × 80 neuron.

### Ví dụ 2 — Hỏng / Thiếu

**Trường hợp sinh học — Cortical column irregularity trong autism**: một số nghiên cứu (Casanova và cộng sự) cho thấy ở phổ tự kỷ, **minicolumn hẹp hơn và dày đặc hơn bình thường**, lateral inhibition giữa các minicolumn yếu. Hậu quả: signal trong 1 column "rò rỉ" sang column lân cận → integration bị nhiễu, sensory hyperresponsivity. Đây là Composite ở mức biểu diễn cấu trúc — khi cấp con (minicolumn) lệch chuẩn, cấp cha (column, area) không thực hiện đúng vai trò aggregation.

**Trường hợp sinh học — Stroke khu trú**: stroke ở một động mạch nhỏ phá ~3-5 column ở V1, nhưng V1 vẫn xử lý visual field bình thường ở các vùng khác. Bệnh nhân có **scotoma** — vùng mù nhỏ ở vị trí tương ứng — nhưng phần còn lại của visual field vẫn nguyên. Đây là **damage tolerance** mà cấu trúc Composite cho phép: phá 1 component không phá toàn cây.

**Trường hợp code — đệ quy thủ công sai**:

```python
def find_neuron_by_name_BAD(node, target):
    if isinstance(node, SingleNeuron):
        if node.name == target: return node
        return None
    elif isinstance(node, Minicolumn):
        for n in node.neurons:                  # ← chỉ kiểm tra neurons
            if n.name == target: return n        # ← thiếu đệ quy!
        return None
    # quên xử lý CorticalColumn → bug ngầm khi cấu trúc lồng sâu
```

Với Composite đúng:
```python
class NeuralComposite:
    def find_by_name(self, target):
        if self.name == target: return self
        for child in self.children:
            result = child.find_by_name(target)   # đệ quy đa hình
            if result: return result
        return None
```
Một định nghĩa, đúng cho mọi cấp lồng.

### Ví dụ 3 — Ứng dụng Ellumm

Trong Ellumm, ký ức được tổ chức phân cấp theo thời gian/chủ đề:

| Cấp | Loại | Ví dụ |
|-----|------|-------|
| **Atomic** (Leaf) | 1 trải nghiệm đơn | "Nhìn thấy táo đỏ lúc 14:32" |
| **Cluster** (Composite cấp 1) | Nhóm atomic gần nhau theo thời gian/không gian | "Đoạn ăn sáng" |
| **Episode** (Composite cấp 2) | Nhóm cluster trong một sự kiện | "Buổi sáng thứ Tư" |
| **Theme** (Composite cấp 3) | Nhóm episode chung chủ đề | "Tuần làm việc 1/12" |
| **Era** (Composite cấp 4) | Nhóm theme dài hạn | "Tháng 12 năm 2024" |

Operations cùng interface:
```python
class MemoryNode(ABC):
    @abstractmethod
    def total_emotion_load(self) -> float: ...
    @abstractmethod
    def find_episodes_about(self, query: str) -> list: ...
    @abstractmethod
    def consolidate(self): ...
```

Ứng dụng:
- `era.total_emotion_load()` — đo "trọng lượng cảm xúc" của cả tháng (sum đệ quy).
- `era.find_episodes_about("snake")` — tìm mọi episode có liên quan đến rắn (đệ quy xuyên cây).
- `theme.consolidate()` — chạy consolidation đệ quy: atomic được tag, cluster được summary hóa, episode được index, theme được abstracted.

Mở rộng dễ dàng:
- Thêm cấp mới `MemoryDecade` (Composite cấp 5) — không sửa class nào hiện hữu.
- Thêm operation mới `total_dopamine_signal()` — định nghĩa 1 lần ở Component, override ở Leaf, đệ quy đóng gói ở Composite.

Khi user query "trải nghiệm vui nhất tháng 12":
```python
december = library.get_era("december_2024")
candidates = december.find_episodes_about("happy")     # đệ quy xuyên cây
top = max(candidates, key=lambda ep: ep.total_emotion_load())
```

Một call, đệ quy đầy đủ. Client không cần quan tâm hierarchy.

---

## TÓM LẠI

Composite = **xử lý đồng nhất single và group object qua interface chung, đệ quy đóng gói**. Trong não, cortical column hierarchy là Composite tự nhiên — neuron → minicolumn → column → area → region, mọi cấp cùng interface "fire/integrate/learn". Tính chất resilience (chịu damage cục bộ) và scale-invariant interface là hệ quả thiết kế Composite mà tiến hóa đã chọn.

Dấu hiệu cần Composite:
- Có cấu trúc cây part-whole tự nhiên trong domain.
- Code đang có nhiều `isinstance()` check để xử lý đệ quy.
- Cần áp operation thống nhất ở mọi cấp (sum, count, find, transform).
- Dự đoán sẽ thêm cấp mới hoặc loại Leaf mới.

Cặp pattern thường đi cùng:
- **Composite + Iterator** (lesson 16): traverse cây theo thứ tự (DFS, BFS, in-order).
- **Composite + Visitor** (lesson 23): operation phức tạp tách khỏi cấu trúc.
- **Composite + Decorator** (lesson 09): wrap node với hành vi bổ sung.
- **Composite + Builder** (lesson 04): xây cây phân cấp từng bước.

### Câu hỏi tự kiểm tra

1. Khi nào nên dùng Transparent (Leaf có `add/remove` no-op) vs Safe (chỉ Composite có)? Trade-off thực tế là gì?
2. Trong não, tại sao "scale-invariant interface" (cùng động từ "fire" áp dụng được cho neuron đến region) là hiệu quả tiến hóa? Nếu mỗi cấp có interface riêng, khó khăn gì xảy ra?
3. Trong Ellumm, nếu một số operation chỉ có nghĩa ở cấp Theme/Era (vd: `seasonal_pattern_analysis()`), bạn xử lý sao trong hierarchy Composite? (Gợi ý: lựa chọn giữa default no-op trong Component hoặc Visitor pattern lesson 23)
