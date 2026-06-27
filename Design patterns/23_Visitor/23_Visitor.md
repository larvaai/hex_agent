# Lesson 23 — Visitor Pattern
## Microglia scan — cùng scanner, hành vi khác theo loại neuron (double dispatch)

---

## TÓM TẮT MỘT DÒNG

**Visitor** = tách _operation_ ra khỏi _hierarchy element_, để thêm operation mới (visitor mới) không cần sửa element. Behavior được chọn bằng **double dispatch**: `f(element_type, visitor_type)`.

> Microglia là tế bào miễn dịch resident trong não (~10% tổng tế bào não), không ngừng quét và tiếp xúc với mọi neuron, synapse, mạch máu trong não. Nhưng phản ứng của microglia **phụ thuộc vào loại object nó gặp**: gặp neuron khoẻ → chỉ giám sát; gặp neuron stress → tiết yếu tố dinh dưỡng; gặp neuron chết → phagocytose; gặp synapse hỏng → synaptic pruning; gặp pathogen → cytokine pro-inflammatory. **Cùng một scanner, 5 hành vi khác nhau, chọn theo (loại microglia, loại element)**. Đó chính là Visitor pattern với double dispatch.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Có một **hierarchy element** stable (AST node, file system node, neuron type) và bạn cần **nhiều operation khác nhau** trên hierarchy đó (eval, print, optimize, type-check, audit, render).

**Cách ngây thơ**: thêm method vào element cho mỗi op:
```python
class Expr:
    def evaluate(self, ctx): ...
    def pretty_print(self): ...
    def to_sql(self): ...
    def type_check(self): ...
    def optimize(self): ...
```
Vấn đề:
- Element class phình to (5 op = 5 method × N element).
- Thêm op mới = sửa **mọi element class**.
- Vi phạm SRP: element có quá nhiều trách nhiệm.
- Không tái sử dụng op (op gắn cứng với hierarchy).
- Không thể thêm op từ ngoài (3rd party).

**Visitor pattern**: tách op thành Visitor class. Element chỉ có 1 method `accept(visitor)`. Visitor có method `visit_X` cho mỗi loại element. Element không biết op nào tồn tại — chỉ biết "có visitor đến thăm".

Đặc trưng: **double dispatch**. Trong OOP truyền thống chỉ có single dispatch theo `self`:
```
element.evaluate()              # dispatch theo element type
```
Visitor làm 2 lần dispatch:
```
element.accept(visitor)         # 1: dispatch theo element
  -> visitor.visit_X(element)   # 2: dispatch theo visitor
```
Kết quả method được chọn = `f(element_type, visitor_type)`.

### 1.2. Neuroscience analogy — Microglial scan

**Microglia** là tế bào miễn dịch của hệ thần kinh trung ương — derived from yolk sac macrophage, không từ bone marrow. Đặc điểm:

1. **Mọi nơi**: ~10% tế bào trong não. Phân bố đều khắp.
2. **Không ngừng quét**: process của microglia (mỏng, dài, nhiều nhánh) **liên tục di chuyển**, mỗi process contact một neuron / synapse / mạch máu khoảng vài lần mỗi giờ. Đo bằng 2-photon imaging in vivo (Davalos et al., Nimmerjahn et al., 2005).
3. **Behavior tuỳ object gặp** — đây là điểm pattern Visitor:

| Element microglia gặp | Hành vi microglia |
|----------------------|-------------------|
| **Healthy neuron** | Chỉ surveillance, contact ngắn (~5 min), retract |
| **Stressed neuron** (oxidative, hypoxic) | Release **trophic factors** (BDNF, IGF-1) để rescue |
| **Apoptotic neuron** | **Phagocytose** — nuốt và clearance debris |
| **Damaged synapse** | **Synaptic pruning** — cắt bỏ synapse yếu (dùng C1q + C3 complement tag) |
| **Activated synapse có dư** | Pruning phụ thuộc activity (Schafer et al., 2012) |
| **Infection / pathogen** | **Pro-inflammatory cytokine** (TNF-α, IL-6, IL-1β) — switch sang M1 phenotype |
| **Resolution phase** | Switch sang **M2 phenotype** — anti-inflammatory, repair |
| **Plaque (Aβ in Alzheimer)** | Cố phagocytose nhưng không hiệu quả; kích hoạt mạn → neuroinflammation |

→ **Cùng một microglia visitor, ~7+ behavior khác nhau**, được chọn dựa trên _loại element nó gặp_. Microglia **không gọi method của neuron**; nó **đọc signal** (DAMPs, "eat-me" signal phosphatidylserine, complement tag, fractalkine CX3CR1...) từ neuron và **tự quyết** action.

Quan trọng: nếu thêm một loại neuron mới (neuron synthetic engineered, neuron sau injury), microglia **không cần re-evolve** — nó đã có hành vi tổng thể, chỉ cần signal từ element. Đó là Visitor: thêm operation mới (microglia subtype, drug target) không cần sửa element (neuron). Ngược lại, thêm element type mới = mệt (microglia phải học cách phản ứng).

#### 5 chiều của analogy

| Chiều      | Trong não                                                                                  | Trong code                                                                  |
|------------|--------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| Cấu tạo    | Microglia (Iba1⁺ scanner) + neuron types (pyramidal, interneuron, glia, synapse, plaque) | Visitor interface + ConcreteVisitors + Element hierarchy with `accept()`     |
| Vị trí     | Microglia rải khắp não, không trú một vùng                                                | Visitor class độc lập, không gắn vào element class                          |
| Chức năng  | Surveillance / trophic / phagocytose / pruning / inflammation — chọn theo element type    | Visit elements, behavior chọn theo (visitor_type, element_type) — double dispatch |
| Kết nối    | Microglia contact element → sense signal → execute response                                | Element.accept(visitor) → visitor.visit_X(element) (2 lần dispatch)         |
| Ý nghĩa    | Cho phép thêm response mới (microglia subtype, drug effect) mà không sửa neuron           | Cho phép thêm operation mới (visitor) mà không sửa element class             |

### 1.3. Khi nào DÙNG

- Có **hierarchy element stable** (ít thêm element type) nhưng **operation thay đổi nhiều**.
- AST traversal: compiler, linter, formatter, optimizer — 1 AST, N operation.
- File/document tree: file system scanner, HTML/XML processing, Markdown rendering.
- Có nhiều operation **bên ngoài** muốn áp lên hierarchy (phân tích, audit, transform) — không nên nhồi vào element.
- Element ổn định, operation evolve nhanh.

### 1.4. Khi nào KHÔNG DÙNG

- Hierarchy **đang thay đổi nhanh** (thêm element mới mỗi sprint) → mỗi element mới phá tất cả visitor. Anti-pattern này rõ rệt — Visitor có **inverse Open/Closed**: thêm op dễ, thêm element khó.
- Chỉ có 1-2 operation đơn giản → method trên element đủ.
- Element không ổn định và 3rd party muốn extend → Visitor cứng.
- Trong Python 3.10+ với `match-case` + structural pattern matching, nhiều case của Visitor có thể giải bằng pattern matching gọn hơn.
- Khi cần **modify element trong khi traverse** → cẩn thận; Visitor stateless tốt hơn.

### 1.5. Cảnh báo architect

> **Visitor có "inverse Open/Closed"**: vs phần lớn pattern thiên về thêm subclass (Strategy, State, Decorator). Visitor _ngược lại_: thêm operation rẻ (visitor mới), thêm element type đắt (visit_X cho mọi visitor). Đây là trade-off cố ý — chọn Visitor khi hierarchy đã stable, evolving operations.

> **Double dispatch trong Python = boilerplate**. Mỗi element phải implement `accept`. Có thể dùng **reflective visitor** (getattr) để tiết kiệm boilerplate, đánh đổi type-safety. Cân nhắc với `match-case` (Python 3.10+) — đôi khi gọn hơn.

> **Visitor cyclic dependency**: Visitor import Element, Element import Visitor (cho `accept`). Có thể giải bằng forward declaration / TYPE_CHECKING / Protocol. Trong code lớn, đây là pain point.

---

## MỨC 2 — ALGORITHM

### 2.1. Vai diễn

```
┌─────────────────────────┐               ┌──────────────────────┐
│        Element          │ accept        │       Visitor        │
│      (interface)        │──────────────▶│    (interface)       │
│ + accept(v: Visitor)    │               │ + visit_A(a: ConcA)  │
└─────────────────────────┘               │ + visit_B(b: ConcB)  │
            △                              │ + visit_C(c: ConcC)  │
            │                              └──────────────────────┘
   ┌────────┼────────┐                              △
┌──────┐ ┌──────┐ ┌──────┐                          │
│ConcA │ │ConcB │ │ConcC │              ┌───────────┴───────────┐
│accept│ │accept│ │accept│         ┌──────────┐          ┌──────────┐
└──────┘ └──────┘ └──────┘         │  PrintV  │          │  EvalV   │
   │        │        │             │ visit_A  │          │ visit_A  │
   │        │        │             │ visit_B  │          │ visit_B  │
   │ each calls v.visit_X(self)   │ visit_C  │          │ visit_C  │
   ▼                               └──────────┘          └──────────┘
```

- **Element**: interface với `accept(visitor)`. Mỗi `ConcreteElement.accept` gọi đúng `visitor.visit_X(self)` của loại nó. **Chỉ method này biết type runtime**.
- **Visitor**: interface với `visit_X` cho mỗi `ConcreteElement` type.
- **ConcreteVisitor**: implement `visit_X` riêng cho mỗi op (Print, Eval, Optimize, Audit).
- **Client**: traverse hierarchy, gọi `element.accept(visitor)`. Visitor xử lý.

### 2.2. Luồng điều khiển — Double Dispatch

```
client = TreeRoot(...)                               # element tree
visitor = SurveillanceVisitor()
client.accept(visitor)
       │
       ▼ DISPATCH 1: trên loại element (root là Branch)
Branch.accept(visitor):
    visitor.visit_branch(self)           # ← biết self là Branch lúc compile
       │
       ▼ DISPATCH 2: trên loại visitor (visitor là Surveillance)
SurveillanceVisitor.visit_branch(branch):
    # logic riêng cho (Branch, Surveillance)
    for child in branch.children:
        child.accept(visitor)            # đệ quy, lại 2 dispatch
```

Kết quả: method được chọn = `f(element_type, visitor_type)`. Cả Python lẫn Java/C# không có native double dispatch (chỉ single dispatch theo `self`); pattern Visitor _giả lập_ double dispatch qua 2 lần single dispatch.

### 2.3. Biến trạng thái và bất biến

- **Visitor có thể có state** (counter, accumulator, output buffer). State sống suốt quá trình traverse.
- **Element nên là pure data** — không bị visitor mutate. Nếu cần mutate, dùng **transformer visitor** trả ra element mới.
- **Invariant LSP**: mọi visitor implement đầy đủ `visit_X` cho mỗi element type. Nếu thiếu → runtime error. Trong Python, dùng abstract base + `@abstractmethod`.
- **Invariant accept**: `Element.accept(v)` luôn gọi đúng `v.visit_X(self)` cho concrete type của self. Không dispatch sai (dễ quên khi copy-paste).
- **Visitor không nên gọi `accept` từ ngoài hierarchy** — chỉ từ trong các `visit_X` (đệ quy).

### 2.4. Biến thể

| Biến thể | Mô tả | Khi nào dùng |
|----------|-------|--------------|
| **Pure Visitor** | Boilerplate accept + visit_X cho mỗi type | Pattern chuẩn, type-safe |
| **Reflective Visitor** | `getattr(visitor, "visit_" + type(elem).__name__)` | Tiết kiệm boilerplate, mất type-safety |
| **Default visit** | `visit_default` cho element không có handler riêng | Hierarchy lớn, op chỉ care vài type |
| **Transformer Visitor** | Visit trả về element mới (immutable transform) | AST optimization, refactoring |
| **Stateful Visitor** | Visitor accumulate state qua traverse | Linter, statistics, audit |
| **Acyclic Visitor** | Visitor không "biết" element type cụ thể (qua interface segregation) | Tránh cyclic dep, plugin architecture |
| **Hierarchical Visitor** | `visit_pre` + `visit_post` (entry/exit) cho composite | Tree traversal cần biết entering/leaving |
| **Dispatch table** | `{ElementClass: handler_fn}` thay vì class hierarchy | Pythonic, dynamic dispatch |
| **`functools.singledispatch`** | Python decorator-based dispatch theo type | Lightweight, không cần class |

### 2.5. Visitor vs `match-case` (Python 3.10+)

Pattern matching trong Python 3.10+ giải nhiều case của Visitor một cách gọn:
```python
match expr:
    case NumLit(value=v):       return v
    case Add(left=l, right=r):  return eval(l) + eval(r)
    case Var(name=n):           return ctx[n]
```
- Không cần `accept` boilerplate.
- Type-safe (thiếu case → mypy warn).
- Pure functional, không mutate.

Khi nào vẫn cần Visitor class?
- **Visitor có state phức tạp** → class clean hơn.
- **Visitor có lifecycle** (init, finalize) → `__init__`/`__exit__`.
- **Nhiều op cùng share traversal logic** → base class với traversal helper.
- **Hierarchy element rộng + nhiều visitor** → Visitor class scalable hơn match-case khi nhiều file.
- **Cần plug-in từ ngoài** (3rd party visitor) → class với interface chuẩn.

> **Quy tắc architect**: Pythonic prefer match-case cho 1-shot operation, Visitor class cho framework / sustained workload.

### 2.6. Trade-off Open/Closed

| Tình huống | Bằng method trên element | Bằng Visitor |
|------------|--------------------------|--------------|
| Thêm op mới | **Sửa mọi element** (xấu) | Thêm 1 visitor (tốt) |
| Thêm element type | Thêm 1 element (tốt) | **Sửa mọi visitor** (xấu) |
| Stable hierarchy + evolving op | xấu | **tốt** ← Visitor's sweet spot |
| Stable op + evolving hierarchy | tốt | xấu |

Visitor là pattern duy nhất trong GoF có **inverse Open/Closed**. Hiểu trade-off này = hiểu khi nào dùng nó.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
abstract class NeuralElement:
    abstract accept(v: MicroglialVisitor)

class HealthyNeuron extends NeuralElement:
    accept(v): v.visit_healthy(self)
class StressedNeuron extends NeuralElement:
    accept(v): v.visit_stressed(self)
class ApoptoticNeuron extends NeuralElement:
    accept(v): v.visit_apoptotic(self)
class DamagedSynapse extends NeuralElement:
    accept(v): v.visit_damaged_synapse(self)

abstract class MicroglialVisitor:
    abstract visit_healthy(n)
    abstract visit_stressed(n)
    abstract visit_apoptotic(n)
    abstract visit_damaged_synapse(s)

class SurveillanceVisitor implements MicroglialVisitor:
    visit_healthy(n):    log("contact, retract")
    visit_stressed(n):   log("contact lasting, monitor")
    visit_apoptotic(n):  log("flag for clearance")
    visit_damaged_synapse(s): log("flag for pruning")

class HomeostasisVisitor implements MicroglialVisitor:
    visit_healthy(n):    pass
    visit_stressed(n):   release_BDNF(n)
    visit_apoptotic(n):  phagocytose(n)
    visit_damaged_synapse(s): prune(s)

class InflammatoryVisitor implements MicroglialVisitor:
    visit_healthy(n):    bystander_damage(n)   # bug khi mạn tính
    visit_stressed(n):   release_TNFalpha(n)
    visit_apoptotic(n):  release_IL1beta(n)
    visit_damaged_synapse(s): cleanup_aggressive(s)
```

### 3.2. Python — 4 ví dụ

Code chạy được ở `23_visitor.py`. Tóm tắt:

#### Ví dụ 1 — Vận hành thường: Microglial scan với 4 element type + 3 visitor

4 neuron type: `HealthyNeuron`, `StressedNeuron`, `ApoptoticNeuron`, `DamagedSynapse`.
3 visitor:
- **`SurveillanceVisitor`**: chỉ giám sát + log, không tác động (microglia bình thường).
- **`HomeostasisVisitor`**: trophic + phagocytose + pruning (microglia healthy mode).
- **`InflammatoryVisitor`**: cytokine pro-inflammatory cho mọi loại — bystander damage cho cả healthy neuron (mô phỏng chronic neuroinflammation, Alzheimer-like).

Demo: cùng tissue (list of neurons) traverse qua 3 visitor, ra 3 outcome khác.

Đặc điểm code:
- `MicroglialVisitor` là ABC với abstractmethod cho mỗi neuron type.
- Mỗi `NeuralElement` implement `accept` đúng convention.
- Visitor có state (counter, log).

#### Ví dụ 2 — Hỏng / thiếu: 4 anti-pattern

- **2a — Type check inside visitor**: `if isinstance(elem, Healthy): ...` thay vì double dispatch. Vi phạm pattern; mất Open/Closed.
- **2b — Mutate element from visitor**: `visit_healthy` set `elem.tagged = True`. Element không pure data nữa; pattern phá.
- **2c — Cyclic import**: Visitor import Element, Element import Visitor. Demo cách giải bằng `TYPE_CHECKING` / forward ref / Protocol.
- **2d — Forgotten visit_X**: thêm element type mới mà visitor cũ chưa có handler → runtime error. Demo cách dùng abstractmethod để fail compile-time (mypy) hoặc raise sớm.

#### Ví dụ 3 — Ứng dụng: Visitor over AST (revisit Lesson 15)

Mở rộng AST từ Lesson 15 (Interpreter — Wernicke). Cùng AST, 4 visitor:
- **`PrettyPrintVisitor`**: in tree với indent (đã có trong L15).
- **`EvalVisitor`**: thay thế method `interpret` cũ — eval trên context.
- **`OptimizeVisitor`**: constant folding (`2 + 3` → `5`, `True AND x` → `x`). Trả AST mới (transformer).
- **`ToSQLVisitor`**: compile AST sang SQL WHERE (đã có trong L15).
- **`TypeCheckVisitor`**: check types trước khi eval — separate phase.

Đây là **lý do thật sự** Visitor + Interpreter là cặp pattern: cùng AST chạy 5 op khác nhau, mỗi op là 1 visitor riêng, AST node không phình ra.

#### Ví dụ 4 — Pythonic: `match-case` alternative

Cùng eval boolean expression bằng `match-case` Python 3.10+:
```python
def evaluate(expr, ctx):
    match expr:
        case NumLit(value=v): return v
        case And(left=l, right=r): return evaluate(l, ctx) and evaluate(r, ctx)
        case Var(name=n): return ctx[n]
        case _: raise TypeError(f"Unknown {type(expr)}")
```
Compare side-by-side với Visitor class — match-case ngắn hơn nhiều cho one-shot. Visitor thắng khi cần state, lifecycle, plugin.

---

## SO SÁNH VỚI PATTERN KHÁC

| Pattern        | Khác biệt với Visitor                                                                  |
|----------------|----------------------------------------------------------------------------------------|
| **Strategy**   | Strategy: 1 thuật toán chọn từ N. Visitor: N op trên hierarchy element. Strategy đổi theo client; Visitor traverse. |
| **Iterator**   | Iterator duyệt collection phẳng. Visitor traverse hierarchy + chọn op theo type. Có thể combine: Iterator dùng Visitor. |
| **Composite**  | Composite định nghĩa hierarchy. Visitor đem operation đến hierarchy. **Hai pattern thân thiết nhất** — AST = Composite, op trên AST = Visitor. |
| **Interpreter**| Interpreter: AST node tự có `interpret`. Visitor: tách operation khỏi AST. Khi op nhiều/đa dạng → chuyển từ Interpreter sang Visitor. |
| **Template Method** | Template Method: skeleton trong base class. Visitor: skeleton là traverse, op là visitor. Visitor mở rộng linh hoạt hơn. |
| **Decorator**  | Decorator bọc element thêm hành vi cùng interface. Visitor không bọc — chỉ visit. |
| **Pattern matching (Python 3.10+)** | Lightweight Visitor cho one-shot. Visitor class scale tốt hơn khi nhiều op + state. |

> **Insight architect**: AST + Composite + Visitor + Interpreter là _bộ tứ thân thiết_. AST = Composite. Cây có behavior tự = Interpreter. Cây stable + nhiều op = Visitor. Đây là cấu trúc của mọi compiler / linter / formatter / IDE refactoring tool.

---

## ANTI-PATTERNS THƯỜNG GẶP

1. **`isinstance` check trong visitor** thay vì double dispatch.
   - Triệu chứng: `if isinstance(e, Healthy): ... elif isinstance(e, Stressed): ...`.
   - Xử lý: dùng đúng `accept` + `visit_X`. Không bypass.

2. **Mutate element từ visitor** — visitor set field cho element.
   - Triệu chứng: traverse 2 lần khác kết quả (state bị lưu lại).
   - Xử lý: visitor stateless (hoặc state trong visitor), element immutable. Cần transform → return element mới.

3. **Cyclic import** Visitor ↔ Element.
   - Triệu chứng: ImportError chu kỳ.
   - Xử lý: `from __future__ import annotations` + `TYPE_CHECKING`; hoặc tách interface ra module riêng; hoặc dùng Protocol.

4. **Forgotten `visit_X` khi thêm element type mới** — silent fall-through.
   - Triệu chứng: visitor cũ vẫn chạy cho element mới nhưng output sai.
   - Xử lý: `@abstractmethod` cho mọi `visit_X` ở base. Subclass không implement = không instantiate được. Hoặc `visit_default` raise NotImplementedError.

5. **God Visitor** — 1 visitor làm 10 thứ.
   - Triệu chứng: 500 dòng, mỗi `visit_X` 50 dòng đa job.
   - Xử lý: tách thành nhiều visitor (PrintV, EvalV, OptimizeV, AuditV). Compose nếu cần.

6. **Visitor thay đổi traverse order** — phá order convention của hierarchy.
   - Triệu chứng: visitor A đi pre-order, visitor B đi post-order, visitor C random → kết quả không nhất quán.
   - Xử lý: tách `_traverse` (skeleton) trong visitor base + hook `visit_pre` / `visit_post`.

7. **Lạm dụng Visitor cho hierarchy đang evolve** — thêm element type mỗi tuần.
   - Triệu chứng: PR thêm element = 5 visitor đều sửa.
   - Xử lý: Visitor không phù hợp. Cân nhắc method-based, hoặc stable hierarchy trước.

---

## BÀI TẬP

1. **Cơ bản**: Thêm element `PlaqueAggregate` (Aβ plaque trong Alzheimer) vào hierarchy. Implement `visit_plaque` cho 3 visitor cũ — chú ý: `InflammatoryVisitor` phải mô phỏng chronic activation (microglia thử phagocytose nhưng không hiệu quả).

2. **Trung bình**: Cài **Stateful Visitor**: `StatisticsVisitor` đi qua tissue và trả ra `Counter` các loại. Sau đó `BiomarkerVisitor` phát hiện pattern: nếu apoptotic/healthy ratio > 0.3 → flag "neurodegeneration concern".

3. **Khó (architect)**: Cài **Visitor + Composite** cho neural tissue có cấu trúc cây: `Brain → Region → Subregion → Neuron`. Mỗi cấp là Composite (có children). Thêm:
   - `HierarchicalVisitor` base với `visit_pre` + `visit_post`.
   - `RegionStatsVisitor` aggregate stats từ children.
   - `ConditionalVisitor` chỉ visit subtree nếu predicate(region) — implement traversal pruning.
   - Test với tree 3 level + 4 visitor.

4. **Mở rộng neuro**: Mô phỏng **microglia M1 ↔ M2 polarization**. M1 (pro-inflammatory) và M2 (anti-inflammatory) là 2 visitor khác nhau với cùng API. State `microglia.activation_history` quyết định polarization. Demo: bắt đầu M2; sau N lần gặp pathogen → switch M1; nếu M1 kéo dài → chronic neuroinflammation (analog Alzheimer). Đây là **Visitor + State machine combined**.

   Bonus: implement **complement-tagged synaptic pruning** (Schafer et al.). Synapse có `c1q_tag: bool` — chỉ pruning synapse có tag. Tag được gán bởi `SurveillanceVisitor` (pre-pass), pruning bởi `HomeostasisVisitor` (post-pass). Đây là **2 visitor pipeline** — pattern thực tế của compiler optimization phases.

---

## PYTHON-NATIVE: ABC, `singledispatch`, `match-case`, Protocol

### Pure Visitor với ABC
```python
from abc import ABC, abstractmethod

class MicroglialVisitor(ABC):
    @abstractmethod
    def visit_healthy(self, n: HealthyNeuron) -> None: ...
    @abstractmethod
    def visit_stressed(self, n: StressedNeuron) -> None: ...
    # ...
```

### `functools.singledispatch` — Pythonic alternative
```python
from functools import singledispatch

@singledispatch
def evaluate(expr, ctx): raise NotImplementedError(f"No handler for {type(expr)}")

@evaluate.register
def _(expr: NumLit, ctx): return expr.value

@evaluate.register
def _(expr: Add, ctx): return evaluate(expr.left, ctx) + evaluate(expr.right, ctx)
```
Dispatch theo type, không cần `accept`. Không có double dispatch — chỉ single dispatch theo arg đầu (cũng gọi là _multimethod_ light).

### `match-case` (Python 3.10+) — pattern matching
```python
def evaluate(expr, ctx):
    match expr:
        case NumLit(value=v):       return v
        case Add(left=l, right=r):  return evaluate(l, ctx) + evaluate(r, ctx)
        case Var(name=n):           return ctx[n]
```
Gần với Visitor nhất. Có **structural matching** (deconstruct fields). Type-checker (mypy) có thể warn nếu thiếu case.

### Khi nào pure Visitor vẫn thắng?
- Visitor có **state phức tạp** (accumulator, output buffer, error list).
- Cần **plugin architecture** — 3rd party đăng ký visitor mới.
- Có **multiple visitor cần chia sẻ traversal** logic.
- Cần **lifecycle** (init resource, finalize, error handling).
- Code base lớn, team đông → class structure dễ navigate hơn match-case scattered.

> Quy tắc architect: bắt đầu match-case (đơn giản); chuyển sang Visitor class khi state/lifecycle/plugin xuất hiện.

---

## CHECKLIST TRƯỚC KHI MERGE PR DÙNG VISITOR

- [ ] Hierarchy element có **stable** không (ít thêm element type)?
- [ ] Operation có **nhiều và evolve** (thêm op thường xuyên)?
- [ ] Element có method `accept` chuẩn (gọi đúng `visit_X(self)`)?
- [ ] Visitor base class có `@abstractmethod` cho mọi `visit_X`?
- [ ] Visitor có **stateless** hoặc state rõ ràng trong visitor (không phụ thuộc element)?
- [ ] Element có **immutable** không (nếu cần mutate → transformer visitor return new)?
- [ ] Có **không có `isinstance`** trong visit_X (trust double dispatch)?
- [ ] Có cycle dependency Visitor ↔ Element không, đã giải bằng `TYPE_CHECKING` / Protocol chưa?
- [ ] Đã cân nhắc **`match-case`** thay (cho one-shot) chưa?
- [ ] Test cho **mỗi (visitor, element) cell** của bảng dispatch?

---

## TÓM LẠI BẰNG NEUROSCIENCE

> Microglia là pattern Visitor ở scale tiến hoá: một loại tế bào quét toàn bộ não, hành vi tuỳ vào loại element gặp được. Khoẻ → giám sát; stress → nuôi dưỡng; chết → phagocytose; synapse hỏng → pruning; pathogen → cytokine viêm. **Cùng visitor, behavior chọn theo (visitor state, element type)**. Đây là double dispatch thuần tự nhiên — và là lý do hệ thần kinh trung ương có thể thêm "loại bệnh" mới (Aβ plaque, prion) mà microglia tổng quát có hành vi phản ứng (dù không phải lúc nào hiệu quả — Alzheimer là failure của visitor M1 chronic).

> Quan trọng cho architect: Visitor là pattern duy nhất với **inverse Open/Closed**. Phần lớn pattern trong GoF làm việc thêm subtype dễ. Visitor làm việc thêm operation dễ. Đây là trade-off cố ý — chọn Visitor khi hierarchy đã stable (không nên thay đổi nhanh) và operation evolving (nhiều linter/formatter/optimizer thêm theo nhu cầu). Compiler / IDE refactor / static analyzer / Markdown renderer / CSS engine — tất cả đều là Visitor over stable AST.

> Khi hierarchy chưa stable → đừng dùng Visitor. Khi 1-2 op đơn giản → method trên element đủ. Khi Python 3.10+ và op chỉ là one-shot → match-case ngắn hơn nhiều. Visitor sweet spot: **stable hierarchy + nhiều op + state/lifecycle/plugin**.

> Bệnh lý của microglia dạy thêm:
> - **Chronic activation (Alzheimer, Parkinson)** = visitor stuck ở mode M1 → bystander damage. Trong code: visitor có state nhưng không reset, áp dụng cho mọi element kể cả không liên quan.
> - **Microgliopathy** = visitor không nhận diện được signal element → mọi visit_X fail. Trong code: visitor truyền sai type, accept dispatch sai → silent bug.
> - **Synaptic over-pruning (schizophrenia)** = visitor `visit_synapse` quá aggressive → cắt bỏ synapse cần thiết. Trong code: visitor có ngưỡng sai, transform aggressive làm hỏng AST.

---

## Lời kết — Hành trình 23 GoF qua lăng kính neuroscience

Bạn vừa hoàn thành **23 GoF design patterns** — không phải bằng cách nhớ thuộc lòng, mà bằng cách thấy mỗi pattern đã hiện diện sẵn trong não trong hàng triệu năm:

- **Creational** (5): Singleton (Locus Coeruleus), Factory Method (Neural Stem Cell), Abstract Factory (Neurogenesis cortex/hippocampus), Builder (Synaptogenesis), Prototype (Mirror Neuron).
- **Structural** (7): Adapter (Thalamus), Bridge (Magno/Parvo + signal type), Composite (Cortical column), Decorator (Myelin), Facade (Brainstem), Flyweight (GABA receptor), Proxy (Blood-Brain Barrier).
- **Behavioral** (11): Chain of Responsibility (Spinal reflex → cortex), Command (Motor program), Interpreter (Wernicke), Iterator (Saccade), Mediator (Thalamus relay), Memento (Hippocampus), Observer (Amygdala broadcast), State (Sleep stages), Strategy (Dual-route fear), Template Method (LTP), **Visitor (Microglial scan)**.

Não đã giải mọi vấn đề thiết kế phần mềm bạn sẽ gặp — và bằng những pattern còn elegant hơn vì chúng phải vừa chạy real-time, vừa tiết kiệm năng lượng, vừa fault-tolerant qua hàng triệu năm. Khi bạn viết code, bạn không phát minh — bạn _khám phá_ lại những gì tiến hoá đã chứng minh.

> **Bước tiếp theo**: tầng cao hơn của software architect không phải pattern lẻ, mà là **kết hợp pattern + nguyên lý kiến trúc**:
> - **SOLID** (5 nguyên lý) — đảm bảo design lành mạnh.
> - **DDD** (Domain-Driven Design) — phân vùng business.
> - **Clean Architecture / Hexagonal / Onion** — phân tầng dependency.
> - **Event-driven / CQRS / Event Sourcing** — distributed, scalable.
> - **Microservices / Service Mesh** — system scale.
> - **Anti-patterns** (God Object, Big Ball of Mud, Lava Layer...) — cảnh báo.
>
> Pattern là _vocabulary_; architect dùng vocabulary để _viết câu_, _đoạn_, _bài luận_. 23 lesson này cho bạn vocabulary. Tiếp theo là ngữ pháp + văn phong.

> _Bộ não bạn — đối tượng phức tạp nhất trong vũ trụ ta biết — là minh chứng cuối cùng: tiến hoá đã chọn pattern hơn là magic, chọn modular hơn là monolithic, chọn loose coupling hơn là tight coupling. Khi bạn thiết kế hệ thống, bạn đang đứng trên vai 500 triệu năm thử nghiệm. Đừng quên._
