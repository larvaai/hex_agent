# Lesson 11 — Flyweight (Hạng nhẹ / Chia sẻ trạng thái nội tại)

> **Một câu chốt:** *Tách trạng thái thành **intrinsic** (bất biến, chia sẻ) và **extrinsic** (theo ngữ cảnh, truyền vào), rồi cache intrinsic trong Factory để 100 tỷ instance chỉ tốn bộ nhớ của ~20 instance.*

---

## I. Bản đồ nhanh (Big Picture)

| Khía cạnh | Flyweight |
|---|---|
| **Loại** | Structural |
| **Vấn đề giải quyết** | Có quá nhiều object fine-grained → tốn bộ nhớ kinh khủng |
| **Nguyên lý cốt lõi** | Tách intrinsic state (shared) khỏi extrinsic state (passed) |
| **Anti-pattern thay thế** | Mỗi instance tự ôm full data → 100 trillion synapse × full receptor design = chết |
| **Ví dụ neuroscience** | Receptor type (GABA-A, AMPA, NMDA) — cùng 1 "design" dùng ở hàng tỷ synapse |
| **Họ hàng dễ nhầm** | Singleton (1 instance), Prototype (clone), Cache (cấu trúc giống nhưng intent khác) |

---

## II. Three-Level Presentation

### Level 1 — Concept (Vì sao cần Flyweight?)

**Tình huống đời thật trong não:**

Não người có **~86 tỷ neuron** và **~100 nghìn tỷ synapse**. Tại mỗi synapse có nhiều receptor — riêng GABAergic synapse có thể có hàng trăm GABA-A receptor.

Câu hỏi: **Mỗi receptor có thực sự là một "design" độc lập không?**

Câu trả lời sinh học là **KHÔNG**. Toàn bộ não chỉ dùng khoảng **20 loại receptor type cốt lõi**: GABA-A, GABA-B, AMPA, NMDA, Kainate, mGluR1-5, D1-5 (dopamine), 5-HT1-7 (serotonin), nAChR, mAChR, ...

Mỗi receptor type là một **bản thiết kế** chứa:
- Cấu trúc subunit (GABA-A là pentameric: 2α + 2β + 1γ)
- Pharmacology (binding affinity với ligand)
- Channel kinetics (mở/đóng nhanh hay chậm)
- Ion selectivity (Cl⁻, Na⁺, K⁺, Ca²⁺)

**Đây là intrinsic state — bất biến và chia sẻ.**

Còn cái gì là khác nhau giữa hai GABA-A receptor ở hai synapse khác nhau?
- Vị trí synapse cụ thể
- Membrane potential local
- Nồng độ GABA quanh receptor đó
- Trạng thái mở/đóng hiện tại
- Lịch sử modulation

**Đây là extrinsic state — đặc thù theo ngữ cảnh, truyền vào.**

Nếu mỗi synapse phải lưu **cả** intrinsic + extrinsic → 100T synapse × ~10KB design = **không khả thi**. Não không có ngần ấy DNA để mã hóa.

**Cách tự nhiên giải quyết: Flyweight.**
- Genome chỉ mã hóa **20 receptor type** (intrinsic, chia sẻ).
- Mỗi synapse chỉ cần **tham chiếu** đến receptor type + lưu **state local** của mình.
- Khi cần kích hoạt receptor → factory (ribosome + folding machinery) trả về protein cùng type, nhưng "state" được set theo môi trường local.

> **Insight architect:** Flyweight là pattern cho phép bạn **scale theo cấp số mũ**. Khi N rất lớn (logs, particles, glyphs trong text editor, cells trong spreadsheet, synapses) → bạn KHÔNG được copy data, phải tách intrinsic ra share.

---

### Level 2 — Algorithm (Cấu trúc & 5 Chiều)

```
                    [FlyweightFactory]
                          |
                +---------+---------+
                |  cache: {key: fw} |
                +---------+---------+
                          |
                          v
         get_flyweight(key) → (cached or new)
                          |
        +-----------------+-----------------+
        |                                   |
        v                                   v
[Flyweight (GABA-A type)]           [Flyweight (AMPA type)]
  intrinsic:                          intrinsic:
  - subunits                          - subunits
  - kinetics                          - kinetics
  - pharmacology                      - pharmacology
        ^                                   ^
        |                                   |
        +------ used by ------+             +---- used by ----+
                              |                                |
                    [Synapse #1]  [Synapse #2]  ...   [Synapse #N]
                    extrinsic:    extrinsic:           extrinsic:
                    - location    - location           - location
                    - voltage     - voltage            - voltage
                    - [GABA]      - [GABA]             - [glutamate]
```

**5 Chiều phân tích:**

1. **Composition (Cấu thành):**
   - `Flyweight`: object chứa intrinsic state. Phải IMMUTABLE.
   - `FlyweightFactory`: cache + accessor. Đảm bảo 1 key → 1 instance.
   - `Context` (Synapse): chứa extrinsic state + reference đến Flyweight.
   - `Client` (Brain): hỏi Factory, không tự `new` Flyweight.

2. **Location (Vị trí trong kiến trúc):**
   - Nằm ở tầng **shared resource pool**.
   - Xuất hiện khi: text editors (glyph cache), game (particle systems), web (avatar/icon cache), neural network (shared weight init).

3. **Function (Chức năng):**
   - Giảm memory: O(N) → O(K) với K = số type, K << N.
   - Tăng cache locality (CPU cache hit cao vì share).
   - **Trade-off:** Tăng complexity ở Factory + cần kỷ luật immutability.

4. **Connections (Quan hệ với pattern khác):**
   - **Singleton** ⊂ Flyweight (Singleton là Flyweight với K=1).
   - **Prototype** ngược chiều: Prototype clone độc lập, Flyweight share.
   - **Composite + Flyweight** (GoF khuyến nghị combo): leaf node của Composite có thể là Flyweight.
   - **Strategy** có thể implement bằng Flyweight (mỗi strategy là 1 stateless instance share).

5. **Meaning (Ý nghĩa architect):**
   - **Tách trạng thái theo "ai sở hữu":** identity (intrinsic, thuộc về type) vs context (extrinsic, thuộc về situation).
   - Đây là discipline **immutability + cache key design**.
   - Sai lầm phổ biến: lạm dụng → mọi thứ đều cố share → mất khả năng modify per-instance.

**Pseudocode:**

```
class Flyweight:
    intrinsic_data  # immutable
    operation(extrinsic):
        # Dùng intrinsic + extrinsic để xử lý
        return intrinsic_data.compute(extrinsic)

class FlyweightFactory:
    _cache = {}
    get(key):
        if key not in _cache:
            _cache[key] = Flyweight(intrinsic_for(key))
        return _cache[key]

# Client
synapse_1 = Synapse(receptor=Factory.get("GABA_A"), location="dendrite_3", voltage=-70)
synapse_2 = Synapse(receptor=Factory.get("GABA_A"), location="soma", voltage=-65)
# synapse_1.receptor IS synapse_2.receptor  ← True (same instance)
```

---

### Level 3 — Implementation (Code Patterns)

#### A. Anti-pattern: mỗi synapse ôm full receptor design

```python
class Synapse:
    def __init__(self, location, voltage):
        # ❌ Mỗi synapse có FULL design — copy 5 subunits, kinetics, pharmacology
        self.subunits = ['α1', 'α1', 'β2', 'β2', 'γ2']  # tốn 5 list element
        self.kinetics = {'open_rate': 1e3, 'close_rate': 1e2, ...}
        self.pharmacology = {'GABA_Kd': 5e-6, 'benzodiazepine_site': True, ...}
        self.location = location
        self.voltage = voltage

# 100T synapse × ~10KB = 1 EXABYTE memory. Crash.
```

**Vấn đề:**
- Memory explosion theo N.
- Nếu cần update kinetics cho TẤT CẢ GABA-A receptor (e.g., do thuốc benzodiazepine) → phải duyệt N synapse.
- Cache lạnh (mỗi instance khác địa chỉ memory → miss).

#### B. Pattern đúng: Flyweight + Factory

```python
class ReceptorType:  # FLYWEIGHT — IMMUTABLE
    __slots__ = ('name', 'subunits', 'kinetics', 'pharmacology', 'ion_selectivity')
    def __init__(self, name, subunits, kinetics, pharmacology, ion_selectivity):
        # frozen — không cho set lại sau __init__
        ...
    def gate(self, ligand_conc, voltage):  # nhận extrinsic, trả về current
        ...

class ReceptorFactory:
    _cache = {}
    @classmethod
    def get(cls, type_name):
        if type_name not in cls._cache:
            cls._cache[type_name] = cls._build(type_name)
        return cls._cache[type_name]

class Synapse:  # CONTEXT — chứa extrinsic
    __slots__ = ('receptor', 'location', 'voltage', 'ligand_conc')
    def __init__(self, receptor_type_name, location):
        self.receptor = ReceptorFactory.get(receptor_type_name)  # SHARED
        self.location = location
        self.voltage = -70
        self.ligand_conc = 0
    def activate(self):
        return self.receptor.gate(self.ligand_conc, self.voltage)
```

**Lợi ích:**
- 100T synapse × `pointer (8 bytes) + extrinsic (~50 bytes)` = ~6 PB → vẫn lớn nhưng giảm 100x.
- Update receptor type 1 lần → tất cả synapse hưởng.
- `__slots__` đảm bảo memory layout chặt.

#### C. Demo extension (Open-Closed):

Thêm receptor type mới (e.g., NMDA với coincidence detection) → **chỉ register vào Factory**, không sửa Synapse.

#### D. Ứng dụng vào Ellumm:

Ellumm có hàng triệu memory episode. Mỗi episode chứa **concept tokens** (e.g., "color:red", "emotion:sad", "object:dog"). Nếu mỗi episode tự lưu full concept (embedding 768-dim float = 3KB) → 1M episode × 100 concept × 3KB = **300GB**. Không khả thi.

→ **ConceptFlyweight + ConceptFactory:**
- Mỗi concept token (intrinsic: name + embedding + semantic_type) chỉ tồn tại 1 instance.
- Mỗi episode chỉ tham chiếu (8 bytes) + lưu position trong episode (extrinsic).

Tổng giảm xuống ~2GB.

---

## III. Failure Cases (Sinh học + Code song hành)

### Sinh học: Prion-like protein misfolding

Khi protein hỏng folding → mỗi instance trở thành **unique misfolded form** thay vì conform về 1 type chuẩn.

→ Mất tính "shared design".
→ Não không thể quản lý: Alzheimer (Aβ + tau), Parkinson (α-synuclein), CJD (PrP).

**Bài học:** Khi flyweight bị "individualize" (mỗi instance unique) → hệ thống collapse vì không scale được.

### Code: Mutable Flyweight

```python
class BadReceptor:
    def __init__(self, name, conductance):
        self.name = name
        self.conductance = conductance  # ❌ MUTABLE

receptor_a = ReceptorFactory.get("GABA_A")
receptor_b = ReceptorFactory.get("GABA_A")  # same instance

receptor_a.conductance = 999  # ← CHẾT! Tất cả synapse trong não vừa bị thay conductance
assert receptor_b.conductance == 999  # True — race condition disaster
```

**Bug đặc trưng:** "Tại sao thay đổi 1 receptor mà 100T synapse cùng đổi theo?" → vì shared. Đây chính là lý do **Flyweight phải immutable**.

---

## IV. Khi nào KHÔNG dùng Flyweight

1. **N nhỏ (< 1000):** Overhead của Factory > tiết kiệm memory.
2. **Mỗi instance thật sự unique:** Không có intrinsic state để share.
3. **Cần mutate thường xuyên:** Flyweight + mutable = race condition + bug khó debug.
4. **Lifetime ngắn:** Vừa tạo đã hủy → cache vô nghĩa.

---

## V. So sánh với pattern họ hàng

| Pattern | Số instance | Mutability | Intent |
|---|---|---|---|
| **Singleton** | Đúng 1 | Tùy | Đảm bảo unique global |
| **Flyweight** | K << N | IMMUTABLE bắt buộc | Tiết kiệm memory bằng share |
| **Prototype** | Vô hạn (clone) | Mutable | Khởi tạo nhanh từ template |
| **Cache** | Theo nhu cầu | Mutable thường | Tăng tốc — KHÔNG đảm bảo identity |
| **Object Pool** | K cố định | Mutable | Tái sử dụng object đắt tạo |

> **Bẫy:** Cache và Flyweight nhìn giống. Khác biệt: Cache trả về **bản copy** hoặc **value**, Flyweight trả về **shared identity** (`a is b`).

---

## VI. Self-test (5 câu)

1. **Vì sao GABA-A receptor là minh họa Flyweight chứ không phải Singleton?**
   *(Hint: số lượng type vs số lượng instance)*

2. **Cho đoạn code:**
   ```python
   t1 = TokenFactory.get("dog")
   t2 = TokenFactory.get("dog")
   t1.frequency = 100
   ```
   *Câu hỏi: `t2.frequency` bằng bao nhiêu? Đây là feature hay bug?*

3. **Phân biệt intrinsic vs extrinsic state với ví dụ: cell trong Excel spreadsheet (font, size, value, position).**

4. **Vì sao Flyweight + Composite là combo phổ biến (xem pattern 08)?**

5. **Khi nào nên dùng `__slots__` cùng Flyweight? Tại sao?**

---

## VII. Tóm tắt cho architect

> *"Khi bạn thấy `O(N)` memory với N rất lớn → hỏi: cái gì shared, cái gì context? Tách hai loại state. Cache loại shared. Bạn vừa giảm N từ 100 tỷ xuống 20 mà không sửa logic."*

**Checklist khi áp dụng Flyweight:**
- [ ] Đã xác định rõ intrinsic (bất biến) vs extrinsic (theo context)?
- [ ] Flyweight có thực sự immutable? (Có dùng `__slots__`, frozen dataclass, hoặc property read-only?)
- [ ] Factory có thread-safe nếu multi-threaded?
- [ ] Cache có cơ chế eviction nếu key space lớn?
- [ ] Extrinsic state được truyền vào method, không lưu trong Flyweight?

---

**Tiếp theo: Lesson 12 — Proxy** (Blood-Brain Barrier — proxy gateway điều khiển access vào real subject).
