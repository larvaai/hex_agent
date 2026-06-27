# Lesson 26 — LSP (Liskov Substitution Principle)
## Pyramidal neuron uniformity + Hodgkin-Huxley invariants — mọi neuron pyramidal đều "fire" theo CÙNG MỘT contract

---

## TÓM TẮT MỘT DÒNG

**LSP** = bất kỳ subclass `S` nào cũng phải thay thế được cho superclass `T` mà **caller không cần biết** mình đang nói chuyện với `T` hay `S`. Nói cách khác: subclass tuân thủ **contract** (precondition, postcondition, invariant, exception, side-effect) của superclass.

> Mọi pyramidal neuron trong não — từ CA1 hippocampus đến L5 cortex đến amygdala BLA — đều tuân thủ một **contract universal** do Hodgkin & Huxley (1952) mô tả: action potential dạng all-or-none, kích hoạt bởi Na⁺ influx, repolarize bởi K⁺ efflux, propagate dọc axon. Bạn có thể *swap* một CA1 pyramidal cell bằng một cortical L5 pyramidal cell trong một mạch giả thuyết — mạch vẫn chạy (timing/threshold khác chút, nhưng *contract* AP giữ nguyên). Nhưng nếu bạn swap pyramidal bằng **một loại tế bào khác hợp đồng** — interneuron (chỉ inhibitory, không project xa), glia (không có AP), motor neuron (output ra muscle, không cortex) — mạch *vỡ*. Đó là LSP sinh học: substitutable theo contract, không substitutable theo "trông giống" hay "cùng cha mẹ phân loại".

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Lesson 25 (OCP) khuyên bạn dùng polymorphism: caller phụ thuộc abstraction, mỗi variant impl interface đó. Nhưng nếu một subclass `S` *vi phạm contract* của base `T`:

- `S.score()` đôi khi raise `RuntimeError` ngoài tài liệu → caller phải `try/except` đặc biệt.
- `S.score()` return `ScoreResult` với `points < 0` → invariant bị phá → leaderboard tính sai.
- `S.score()` mutate input `answers` → caller phải copy trước → trap.
- `S.__init__` đòi hỏi param `S` mới — nhưng caller chỉ biết về `T` → wiring vỡ.

Khi đó caller buộc phải `if isinstance(s, S): special_handling()` → if/elif quay lại → **OCP collapse**. LSP là điều kiện *behavioral* để OCP không bị phá ngược.

### 1.2. Định nghĩa

**Barbara Liskov & Jeannette Wing 1994** (*A Behavioral Notion of Subtyping*, ACM TOPLAS) — định nghĩa formal:

> *"Let φ(x) be a property provable about objects x of type T. Then φ(y) should be true for objects y of type S where S is a subtype of T."*

Nói cách khác: bất kỳ tính chất nào caller dựa vào với `T`, vẫn đúng với `S`. Subclass *không được làm yếu đi* contract.

**Robert Martin 1996 reformulation** (cho dễ áp dụng):
> *"Functions that use pointers/references to base classes must be able to use objects of derived classes without knowing it."*

### 1.3. 4 quy tắc cụ thể (Liskov-Wing 1994 + Meyer's contract programming)

LSP-compliance đo bằng 4 trục:

| # | Quy tắc | Phép vi phạm |
|---|---------|---------------|
| 1 | **Preconditions không được mạnh hơn** trong subclass | Base chấp nhận `int >= 0`; sub chỉ chấp nhận `int > 0` → caller hợp lệ với base, fail với sub |
| 2 | **Postconditions không được yếu hơn** trong subclass | Base hứa return `>= 0`; sub return `< 0` → caller dựa vào hứa hẹn này, fail |
| 3 | **Invariants không được phá** | Base bất biến "list không rỗng sau init"; sub init xong list rỗng → corrupt state |
| 4 | **History constraint** (chỉ trạng thái nội bộ thay đổi theo cách base cho phép) | Base immutable; sub mutate → caller cache reference, sau đó nhìn thấy giá trị thay đổi → bug |

**Bonus quy tắc** (thực tế hay sai):

5. **Exception types không được mở rộng** — sub không được raise exception type mà base không khai báo.
6. **Side-effects không được thêm** — base pure function; sub viết DB → caller không biết, transaction lỗi.
7. **Return type covariance OK; param contravariance OK** (Java rule). Trong Python signature flexibility cho phép, nhưng *spirit* phải giữ.

### 1.4. Ví dụ cổ điển — Square IS-NOT-A Rectangle

```python
class Rectangle:
    def set_width(self, w): self._w = w
    def set_height(self, h): self._h = h
    def area(self): return self._w * self._h

class Square(Rectangle):  # ← IS-A theo phân loại
    def set_width(self, w):
        self._w = w
        self._h = w  # giữ là Square
    def set_height(self, h):
        self._w = h
        self._h = h
```

Caller có hợp đồng với Rectangle:
```python
def grow(rect: Rectangle):
    rect.set_width(10)
    rect.set_height(5)
    assert rect.area() == 50  # invariant cua Rectangle
```

Pass `Square()` vào → `set_height(5)` cũng đặt `_w = 5` → area = 25 ≠ 50 → **assertion fail**. Square không substitutable cho Rectangle ở mức *behavior* dù substitutable ở mức *taxonomy*. Đây là cảnh báo: **IS-A của ngôn ngữ không phải IS-A của LSP**. LSP đo bằng *contract behavior*, không phải hệ phân loại.

### 1.5. Neuroscience analogy — Pyramidal neuron uniformity + Hodgkin-Huxley invariants

#### Cơ chế 1 — Universal AP contract (Hodgkin-Huxley 1952)

Hodgkin & Huxley năm 1952 (giải Nobel 1963) mô tả phương trình 4 biến (V, m, h, n) ghi lại sự bùng nổ điện thế trong axon mực ống. Phương trình này áp dụng *gần như giống nhau* cho mọi neuron có khả năng fire AP:

- **Trigger**: depolarization vượt threshold (~-55 mV).
- **Rising phase**: Na⁺ influx qua voltage-gated Na channel.
- **Peak**: ~+40 mV.
- **Falling phase**: Na channel inactivate + K⁺ efflux qua voltage-gated K channel.
- **Refractory period**: hyperpolarization, không thể fire ngay sau.
- **Propagation**: dọc axon, biên độ giữ nguyên (all-or-none).

Đây là **interface universal** — *tất cả* neuron có axon spike đều tuân thủ contract này. Chi tiết khác:
- Threshold: CA1 ~-50 mV; nociceptor ~-40 mV; Purkinje cell ~-55 mV.
- AP duration: pyramidal 1-2 ms; cardiac myocyte 200 ms.
- Subtype Na/K channel: NaV1.1 vs NaV1.7 vs NaV1.8.

Nhưng *shape của AP* và *protocol fire* là chung. Đây là LSP-compliant subtyping: mỗi loại neuron là một *concrete impl*, contract giữ nguyên.

#### Cơ chế 2 — Pyramidal neuron uniformity

Pyramidal neuron là loại neuron chính ở cortex và hippocampus (~80% neurons cortex). Chúng có *cấu trúc chung*:

- Soma hình pyramid.
- Apical dendrite vươn lên L1.
- Basal dendrite tỏa ngang.
- Axon đi xuống white matter → projection xa (corticothalamic, corticospinal, callosal).
- Glutamatergic (excitatory).
- Spike pattern: regular spiking (RS) hoặc intrinsically bursting (IB).

Vì vậy, một pyramidal cell ở CA1 hippocampus và một pyramidal ở L5 motor cortex *substitutable theo contract*: cả hai đều "nhận glutamate input, integrate, fire AP, project xa, exitatory tại target". Trong các mô hình mạch giả thuyết, swap được mà không phá topology.

Đây là **bằng chứng tự nhiên rằng LSP-correct subtyping work**.

#### Cơ chế 3 — Vi phạm LSP trong não (substitution sai = mạch vỡ)

| Vi phạm | Hậu quả sinh học | Tương đương code |
|---------|-------------------|--------------------|
| Substitute pyramidal bằng **interneuron** (PV+, SST+) | Interneuron chỉ inhibitory, axon ngắn không project xa → mất projection signal đến target | Subclass đổi semantics: scorer "trừ" thành scorer "không tính" |
| Substitute neuron bằng **glia** (astrocyte, oligodendrocyte) | Glia không có voltage-gated Na/K channel → không fire AP → mạch im lặng | Subclass missing method: kế thừa interface nhưng không impl contract |
| Substitute pyramidal bằng **motor neuron** (alpha motor) | Motor neuron output ra muscle, không cortex; axon đi qua spinal cord, không callosum → kết nối sai target | Subclass đổi side effect: thay vì write DB, gọi external API |
| Pyramidal **bị block Na channel** (TTX poisoning) | Soma còn, nhưng không fire được → caller (downstream) chờ tín hiệu vô vọng | Subclass đôi khi raise exception lạ → caller không biết handle |
| Glutamate receptor type sai (NMDA thay AMPA) | Gating khác (NMDA cần Mg²⁺ block release + co-agonist glycine) → không fire ngay với input thường → mạch lỗi tiếng-vang ngầm | Subclass strengthen precondition: "tôi chỉ nhận input nếu có flag X" |

Bệnh lý điển hình:
- **Multiple sclerosis**: oligodendrocyte (glia) chết → axon mất myelin → AP không propagate đúng → "subclass" oligodendrocyte mới không giữ contract của oligo cũ.
- **ALS**: motor neuron chết → mất output substitution → cortex còn nguyên nhưng ra ngoại vi mất.
- **Channelopathies** (NaV1.1 mutation gây Dravet syndrome): Na channel impl mới phá invariant Hodgkin-Huxley → AP không đúng → seizure.

#### Cơ chế 4 — Receptor swap = LSP test

Tại synapse, postsynaptic membrane có receptor "expect" một loại neurotransmitter. AMPA receptor expect glutamate, opens Na/K channel — fast excitation. Nếu bạn swap AMPA bằng GABA-A receptor (expect GABA, opens Cl⁻ channel — fast inhibition), receptor *vẫn ghép vào synapse* (taxonomy: cùng họ ionotropic) nhưng *ngược dấu signal* → excitatory synapse trở thành inhibitory → mạch logic ngược.

Đây là LSP violation kinh điển: "trông giống" (cùng họ ligand-gated ion channel), "khác hành vi" (depolarize vs hyperpolarize). Trong code: hai class cùng impl `IScorer` interface, một trả lời "điểm dương", một trả lời "điểm âm" — caller dựa hợp đồng "điểm dương" sẽ vỡ.

#### 5 chiều của analogy

| Chiều | Trong não (Hodgkin-Huxley + pyramidal uniformity) | Trong code (LSP) |
|-------|----------------------------------------------------|-------------------|
| **Cấu tạo** | AP contract: depolarize → Na⁺ in → K⁺ out → repolarize, all-or-none | Interface contract: precondition, postcondition, invariant, exception, side-effect spec |
| **Vị trí** | Áp dụng cho mọi neuron có axon spike, không phải mọi tế bào | Áp dụng tại boundary subclass-superclass, không cần cho mọi cặp class |
| **Chức năng** | Đảm bảo signal propagation đúng dạng giữa các vùng đa dạng | Đảm bảo caller substitute subclass mà không cần if/elif |
| **Kết nối** | Pyramidal swap pyramidal: project pattern giữ; swap glia: project mất | Subclass giữ contract: caller giữ hợp đồng; subclass phá contract: caller buộc kiểm tra type |
| **Ý nghĩa** | Cho phép tiến hóa nhiều loại neuron trên 1 protocol; mạch tổng quát | Cho phép OCP thực sự work; thêm subclass không bắt caller sửa |

### 1.6. Khi nào LSP áp dụng nghiêm

- Bất kỳ khi nào bạn tạo abstraction (interface, abstract base class) có ≥ 2 impl.
- Bất kỳ khi nào caller dựa vào *contract* của abstraction (không chỉ signature).
- Khi tạo plugin / 3rd-party extension — họ sẽ impl interface, bạn cần đảm bảo họ giữ contract.

### 1.7. Khi nào LSP "lỏng" được (hiếm)

- Class internal, không expose qua interface, 1 impl duy nhất (LSP không kích hoạt).
- "Refused bequest" có thể chấp nhận khi documented (subclass intentionally không impl 1 method, raise `NotImplementedError`) — nhưng đây là smell.
- Thực sự có 2 hành vi khác xa nhau: tách 2 interface riêng (ISP — lesson 27).

---

## MỨC 2 — ALGORITHM / CẤU TRÚC

### 2.1. Vai diễn

```
   Caller code
       ↓ (depend on)
   Abstract T  ← Interface contract: pre/post/invariant/exception/side-effect spec
   ↑       ↑
   S₁     S₂   ← Concrete impls. MỖI impl phải GIỮ contract của T.
                 Nếu Sᵢ làm yếu hợp đồng → caller buộc isinstance(Sᵢ) check
                 → OCP collapse.
```

### 2.2. 4 loại vi phạm và cách phát hiện

#### Loại 1 — Strengthen precondition

```python
class Scorer(ABC):
    @abstractmethod
    def score(self, answers: Dict[str, str]) -> ScoreResult: ...
    # Contract: answers can be empty dict, str:str

class StrictScorer(Scorer):
    def score(self, answers):
        if not answers:
            raise ValueError("answers must be non-empty")  # ← strengthen!
        ...
```

Caller hợp đồng với `Scorer`:
```python
def submit(scorer: Scorer, answers: dict):
    return scorer.score(answers)  # passes empty dict → fail with StrictScorer
```

**Phát hiện**: review precondition của subclass — nếu nó *raise sớm hơn* base, đó là strengthen.

#### Loại 2 — Weaken postcondition

```python
class WeirdScorer(Scorer):
    def score(self, answers):
        return ScoreResult(points=-5.0, total=4.0)  # ← negative violates "points >= 0"
```

Caller dựa vào `result.points >= 0`:
```python
leaderboard.update(user, scorer.score(answers).points)  # negative → bug
```

**Phát hiện**: documented contract của return value (range, type, invariant) — subclass nào trả lời ngoài đó là vi phạm.

#### Loại 3 — Side effect surprise

```python
class MutatingScorer(Scorer):
    def score(self, answers):
        answers["q_secret"] = "hacked"  # ← mutate input
        return ...
```

Caller giữ `answers` để re-use, hoặc cache:
```python
result_a = scorer.score(answers)
result_b = scorer.score(answers)  # khác result_a vì answers bị mutate
```

**Phát hiện**: contract phải tuyên bố input immutable; subclass nào mutate là vi phạm.

#### Loại 4 — Exception type change

```python
class FailingScorer(Scorer):
    def score(self, answers):
        if not self._network_ok():
            raise ConnectionError("offline")  # ← base không khai báo exception này
```

Caller hợp đồng "Scorer.score chỉ raise ValueError với input invalid":
```python
try:
    return scorer.score(answers)
except ValueError:
    return None
# ConnectionError thoát ra → uncaught crash
```

**Phát hiện**: list exception types khai báo trong base; subclass thêm exception là vi phạm — thoát qua wrap, không qua throw.

### 2.3. Recipe LSP-correct subtyping

```
Khi viet subclass S cua T:

step 1: doc contract cua T (precond, postcond, invariant, exception, side-effect)
        - Neu T khong document, day la red flag - viet contract truoc

step 2: precondition: S.precondition <= T.precondition
        (S accept it nhat moi input ma T accept; co the accept HON, khong duoc IT HON)

step 3: postcondition: S.postcondition >= T.postcondition  
        (S guarantee nhat moi thing T guarantee; co the guarantee HON)

step 4: invariant: S preserve all invariant cua T
        (Khong duoc weaken any data invariant)

step 5: exception: S.exceptions <= T.exceptions
        (S chi raise types ma T da khai bao - hoac wrap)

step 6: side-effect: S.side_effects <= T.side_effects
        (Khong duoc them write/network/log ngam)

step 7: viet test: lay test suite cua T va chay tren S
        - Tat ca pass = LSP compliant
        - Bat ky 1 fail = vi pham
```

### 2.4. "Behavioral subtyping" vs "Inheritance"

Inheritance là *cú pháp* (subclass have access to parent methods). Behavioral subtyping là *ngữ nghĩa* (subclass tuân hợp đồng). Hai khái niệm khác nhau:

| Tình huống | Inheritance? | Behavioral subtyping? |
|------------|--------------|------------------------|
| `Square(Rectangle)` Python | Có | Không (set_height phá invariant) |
| `WeightedScorer(QuizScorer)` của lesson 25 | Có | Có (giữ contract score) |
| `MockEmailNotifier(Notifier)` viết trong test | Có | Có (chỉ no-op send) |
| `class Penguin(Bird): def fly(self): raise` | Có | Không (refused bequest) |
| Composition, không inherit — duck typing | Không | Có nếu giữ contract |

→ **LSP nói về behavioral subtyping, không về inheritance**. Bạn có thể có inheritance mà vi phạm LSP, hoặc duck-typed substitution mà tuân LSP.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode — viết và test một subclass LSP-compliant

```
1. Doc contract cua QuizScorer (lesson 25):
   - score(answers: Dict[str, str]) -> ScoreResult
   - Precondition: answers la dict, co the rong; key/value la str
   - Postcondition: ScoreResult voi points >= 0, total > 0, points <= total + epsilon
   - Invariant: scorer instance immutable sau __init__; score() pure
   - Exception: chi raise ValueError voi input sai schema
   - Side-effect: KHONG (pure function)

2. Cho moi subclass S (Standard, Negative, Weighted, Partial):
   - Precondition: <= base (cung accept dict)
   - Postcondition: >= base (cung tra ScoreResult, points >= 0, etc.)
   - Invariant: <= base (cung pure)
   - Exception: <= base (chi ValueError)
   - Side-effect: <= base (none)

3. Viet test suite ABSTRACT cho QuizScorer (Liskov contract test):
   - test_returns_score_result
   - test_points_non_negative
   - test_pure_no_mutation
   - test_only_raises_value_error
   Chay test nay tren MOI subclass. Subclass nao fail = vi pham.

4. Refactor cac vi pham:
   - Strengthen precondition -> bo
   - Weaken postcondition -> fix logic
   - Side effect surprise -> tach ra hook
   - Exception type -> wrap
```

### 3.2. Python — file `26_lsp.py`

Cấu trúc trong `26_lsp.py`:

1. **Reuse** `QuizScorer`, `ScoreResult` từ lesson 25 (re-define gọn cho self-contained).
2. **4 violation impls** — minh họa từng loại vi phạm:
   - `StrictScorer` — strengthen precondition (raise nếu answers rỗng).
   - `BuggyScorer` — weaken postcondition (return points âm).
   - `MutatingScorer` — side effect (mutate input).
   - `NetworkScorer` — exception type change (raise `ConnectionError`).
3. **LSP-compliant refactor** cho 4 violation:
   - Bỏ check rỗng (chấp nhận empty answers, return points=0).
   - Clamp points >= 0.
   - Copy input thay vì mutate.
   - Wrap network error → trả `ScoreResult(0, total)` hoặc raise `ValueError`.
4. **Liskov contract test suite** — abstract test chạy trên mọi `QuizScorer`. Chạy qua mọi impl → 4 violator fail, 4 sau-refactor pass.
5. **Demo "OCP collapse"**: caller bị buộc `isinstance` check khi 1 subclass vi phạm.
6. **Demo "OCP restored"**: sau refactor LSP, caller không cần check.
7. **Square ≠ Rectangle**: ví dụ kinh điển implement đầy đủ + assertion fail.

Chạy:
```bash
python 26_lsp.py
```

---

## 5 CHIỀU — BẢNG SO SÁNH IN NÃO VS IN CODE

| Chiều | Não (Hodgkin-Huxley contract + pyramidal uniformity) | Code (LSP) |
|-------|------------------------------------------------------|------------|
| **Cấu tạo** | AP contract: trigger threshold, Na⁺/K⁺ kinetics, all-or-none, refractory | Interface contract: precondition, postcondition, invariant, exception, side-effect |
| **Vị trí** | Áp dụng cho mọi neuron có axon fire — không cho glia, sensory transducer | Áp dụng tại biên subclass ↔ superclass khi caller dựa vào abstraction |
| **Chức năng** | Đảm bảo neuron khác loại vẫn truyền signal đúng dạng → mạch tổng quát work | Đảm bảo caller swap subclass mà không if/elif → OCP work |
| **Kết nối** | Pyramidal-pyramidal swap: project topology giữ. Pyramidal-glia swap: signal mất | Substitution giữ contract: hợp đồng caller-subclass giữ. Vi phạm: caller phải isinstance |
| **Ý nghĩa** | Tiến hóa cho phép nhiều loại neuron trên 1 protocol — mạch không phải biết loại nào | Cho phép thêm subclass mới thực sự "drop-in" — caller không phải sửa |

---

## 3 LOẠI VÍ DỤ TRONG CODE

### Ví dụ 1 — Vận hành thường (LSP-compliant)

```python
class QuizScorer(ABC):
    """Contract:
    - score(answers) -> ScoreResult với points >= 0, total > 0
    - pure (không mutate input, không side-effect)
    - chỉ raise ValueError với schema sai
    """
    @abstractmethod
    def score(self, answers: Dict[str, str]) -> ScoreResult: ...

class StandardScorer(QuizScorer):  # ✓ tuân thủ
class WeightedScorer(QuizScorer):  # ✓ tuân thủ
class PartialCreditScorer(QuizScorer):  # ✓ tuân thủ
```

Caller:
```python
def submit(scorer: QuizScorer, answers):
    result = scorer.score(answers)
    assert result.points >= 0           # giữ với mọi impl
    assert isinstance(result, ScoreResult)
    return result
```
→ Mọi subclass swap được, không cần `isinstance`.

### Ví dụ 2 — Hỏng/thiếu (vi phạm LSP)

```python
class StrictScorer(QuizScorer):
    def score(self, answers):
        if not answers:
            raise ValueError("non-empty required")  # strengthen precondition

class BuggyScorer(QuizScorer):
    def score(self, answers):
        return ScoreResult(points=-1.0, total=4.0)  # weaken postcondition

class MutatingScorer(QuizScorer):
    def score(self, answers):
        answers["leaked"] = "true"  # side-effect bonus
        return ...

class NetworkScorer(QuizScorer):
    def score(self, answers):
        raise ConnectionError("offline")  # exception type change
```

Hậu quả:
- Caller `submit(StrictScorer(), {})` raise → ngoài contract.
- Caller `leaderboard.update(BuggyScorer().score(...).points)` lưu điểm âm → leaderboard sai.
- Caller cache `answers` → MutatingScorer làm cache thay đổi → re-run khác kết quả.
- Caller `try/except ValueError` → NetworkScorer thoát → crash.

→ Caller buộc `isinstance(scorer, ...)` check → OCP collapse.

### Ví dụ 3 — Ứng dụng Ellumm (refactor 4 violator)

| Violator | Vi phạm | Refactor |
|----------|---------|----------|
| `StrictScorer` | Strengthen precondition | Bỏ check rỗng. Return `ScoreResult(0, len(key))` cho empty input |
| `BuggyScorer` | Weaken postcondition | `clamp(points, 0, total)` trong return |
| `MutatingScorer` | Side-effect | Copy input: `answers = dict(answers)` đầu method, hoặc dùng frozen mapping |
| `NetworkScorer` | Exception type | Wrap: `try: …; except ConnectionError as e: raise ValueError("offline") from e` — hoặc dùng circuit breaker (Decorator) |

Sau refactor: chạy lại Liskov contract test suite → tất cả pass.

---

## SO SÁNH PATTERN LÂN CẬN

| Pattern / Principle | Đặc điểm | Quan hệ với LSP |
|---------------------|----------|-----------------|
| **OCP** (Lesson 25) | Mở extension, đóng modification | OCP yêu cầu LSP để work. Vi phạm LSP → caller `isinstance` → OCP collapse |
| **ISP** (Lesson 27) | Interface không ép client phụ thuộc method thừa | Có thể tách 1 interface to thành nhiều nhỏ — LSP áp dụng cho từng interface |
| **DIP** (Lesson 28) | Cấp cao phụ thuộc abstraction | Abstraction phải có *contract*, LSP đảm bảo subclass giữ contract đó |
| **Refused Bequest** (anti-pattern) | Subclass override 1 method với `raise NotImplementedError` | Vi phạm LSP — subclass không thực sự là `T` |
| **Tell, Don't Ask** | Đừng hỏi type, hãy gọi method | LSP làm điều này khả thi: gọi method polymorphic, không cần biết type |
| **Design by Contract** (Meyer) | Class có pre/post/invariant rõ ràng | LSP là **đặc trường hợp** của DBC cho subclass |
| **Composition over Inheritance** | Tránh inherit, dùng wrap | Khi LSP khó giữ qua inheritance, composition cứu — wrapper không claim là `T` |

**Vai trò trong SOLID**: LSP đứng giữa OCP và DIP. OCP nói "phụ thuộc abstraction"; DIP nói "abstraction nằm bên trong"; LSP nói "abstraction có *contract* và mọi impl giữ contract đó". Thiếu LSP, OCP và DIP đều suy yếu.

---

## TRADE-OFFS

| Trade-off | Chi phí | Lợi ích |
|-----------|---------|---------|
| Document contract chi tiết | Viết doc + maintain doc | Subclass biết phải giữ gì; reviewer biết check gì |
| Liskov contract test suite | Viết test abstract + chạy cho mọi impl | Phát hiện vi phạm tự động ở CI |
| Tránh inheritance phức tạp | Đôi khi composition rườm rà | LSP dễ giữ hơn — wrapper không claim "is-a" |
| Chấp nhận duplicate thay vì subtype | Code dài hơn | Tránh wrong abstraction (Sandi Metz) |
| Wrap exception thay vì throw mới | Indirection | Exception contract giữ |

**Quy tắc**: chấp nhận chi phí khi abstraction có ≥ 3 impl và caller phụ thuộc abstraction. Với 1 impl duy nhất, LSP không kích hoạt — viết thẳng concrete.

---

## CHECKLIST TRƯỚC KHI MERGE PR

- [ ] **Contract của abstraction được document?** (Pre/post/invariant/exception/side-effect.) Không có doc = không có contract = LSP không đo được.
- [ ] **Subclass có strengthen precondition không?** Nó raise sớm hơn base với input nào?
- [ ] **Subclass có weaken postcondition không?** Nó trả ngoài range / type / invariant base hứa?
- [ ] **Subclass có raise exception type mới không?** Có wrap thành type base đã khai báo chưa?
- [ ] **Subclass có thêm side-effect ngầm?** (DB write, network call, log, mutate input.)
- [ ] **Test abstract** (Liskov contract test) chạy được trên subclass mới mà không cần chỉnh?
- [ ] **Caller có cần `isinstance` check ở đâu trong code base?** Mỗi `isinstance` là dấu LSP có thể đang vi phạm.
- [ ] **Refused bequest**: subclass có method `raise NotImplementedError`? → smell, có thể tách interface (ISP).
- [ ] **`Square IS-NOT Rectangle` test**: nếu subclass override một method *làm đổi semantics* của method khác, đó là LSP violation.
- [ ] **Composition alternative**: nếu LSP khó giữ, có thể dùng wrap thay inherit?

---

## BÀI TẬP 4 MỨC

### Mức 1 — Cơ bản

Mở `26_lsp.py`. Đọc 4 violator (Strict, Buggy, Mutating, Network). Với mỗi cái:
- Liệt kê quy tắc LSP nó vi phạm (1 trong 4: strengthen pre / weaken post / invariant / exception).
- Viết 1 test case caller fail vì vi phạm đó.
- Chỉ ra dòng cụ thể trong refactor làm cho subclass tuân thủ.

### Mức 2 — Trung bình

Refactor `Square(Rectangle)` để LSP-compliant. Có 2 hướng:
1. Bỏ inheritance: `Square` không kế thừa `Rectangle`. Dùng *composition* hoặc tách 2 interface (`Shape` chung).
2. Đổi semantics của Rectangle: làm Rectangle immutable (no `set_*`), khi đó `Square(Rectangle)` immutable cũng OK vì invariant không bị phá runtime.

Implement cả 2 hướng. So sánh:
- Số dòng code.
- Tính tự nhiên với caller (`grow(rect)` viết được trong cách nào?).
- Test contract pass với cách nào?

### Mức 3 — Khó (architect-level)

Tình huống: `QuizScorer` interface đang nhận `Dict[str, str]`. Yêu cầu mới: hỗ trợ `MultiChoiceAnswers` (list các option đã chọn cho 1 câu) — kiểu dữ liệu hoàn toàn khác.

Hai hướng:
1. **Mở rộng interface**: thêm `score_multi(answers: MultiChoiceAnswers) -> ScoreResult` vào `QuizScorer`. Subclass cũ phải impl method này (refused bequest hay default impl?).
2. **Tách interface**: `MultiChoiceScorer` riêng. Caller cần biết loại nào để gọi.

Phân tích: hướng 1 có vi phạm ISP (lesson 27) không? Hướng 2 làm gì với caller — phải `isinstance` không (vi phạm OCP)?

Đề xuất hướng 3 (giải hợp lý): convert input về một *common type* (ví dụ `AnswerSheet` abstract) trước khi vào scorer. Phân tích trade-off.

### Mức 4 — Mở rộng neuroscience

Câu hỏi mở:
1. Tại sao tiến hóa lại "chọn" giữ Hodgkin-Huxley AP contract universal qua hàng triệu năm? (Hint: alternative là mỗi loại neuron có protocol khác — interface explosion.)
2. **Channelopathies** (Dravet syndrome do NaV1.1 mutation): channel mới impl interface VGSC nhưng kinetics sai → seizure. Đây là *strengthen* hay *weaken* contract? Liên hệ với code.
3. **Plasticity vs LSP tension**: synaptic plasticity (lesson 25) làm receptor "đổi" theo thời gian — strength, location, even type (AMPA → NMDA). Có vi phạm LSP không? Hay đó là *graceful evolution*? Liên hệ với "interface versioning" trong code.

Trả lời 4–6 câu mỗi mục.

---

## SAU LESSON NÀY

LSP đã đảm bảo subclass giữ contract. Nhưng nếu interface *đầu vào* quá to (10 method), subclass nào cũng phải impl cả 10 dù chỉ cần 2 — đó là vấn đề **ISP (Interface Segregation Principle)** — Lesson 27. ISP nói: interface phải hẹp, đặc thù theo client view; không nên ép client phụ thuộc method nó không dùng.

> **Nhớ một câu**: LSP không phải "subclass kế thừa class cha". LSP là "subclass **hành xử** đúng như cha — caller không cần biết".
