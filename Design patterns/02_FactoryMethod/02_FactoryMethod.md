# Lesson 02 — Factory Method

> **Định nghĩa interface để tạo object, nhưng để subclass quyết định loại object cụ thể nào được tạo.**

---

## Mức 1 — CONCEPT (Ý tưởng)

### Vấn đề pattern giải quyết

Bạn đang viết một module xử lý "tế bào thần kinh sinh ra trong vùng não X". Trong code main:

```python
# ❌ Cứng nhắc: mỗi vùng phải sửa code chung
def develop_brain_region(region_name):
    if region_name == "visual_cortex":
        neuron = ExcitatoryNeuron()
    elif region_name == "hippocampus":
        neuron = PyramidalNeuron()
    elif region_name == "cerebellum":
        neuron = GranuleCell()
    elif region_name == "striatum":
        neuron = MediumSpinyNeuron()
    else:
        raise ValueError(...)
    neuron.migrate()
    neuron.connect()
```

Đây là **anti-pattern**: thêm 1 vùng não mới = sửa file chung = vi phạm Open-Closed Principle (mở để mở rộng, đóng để sửa đổi). Mỗi if-else dài là một lời nhắc tự nhiên: "Có một class chưa được sinh ra ở đây."

Factory Method lật ngược câu hỏi: thay vì code main chọn loại neuron, để **subclass của factory** tự khai báo loại neuron của mình. Code main chỉ gọi `factory.create_neuron()` — không quan tâm subclass nào, không có if-else.

### Neuroscience analogy — Neural Stem Cell + Morphogen Gradient

Trong phát triển não, **neural stem cell (NSC)** ở vùng ventricular zone không "biết trước" sẽ sinh ra loại neuron nào. Output phụ thuộc vào **vị trí + thời điểm**:

| Vùng phát triển | Morphogen / Transcription factor | Sản phẩm |
|-----------------|----------------------------------|----------|
| Dorsal forebrain | Pax6⁺, BMP cao | Glutamatergic excitatory neuron (cortex layer 2-6) |
| Ventral forebrain | Nkx2.1⁺, Shh cao | GABAergic interneuron (di chuyển vào cortex) |
| Cerebellum (rhombic lip) | Atoh1⁺ | Granule cell |
| Spinal cord ventral | Olig2⁺ + Shh | Motor neuron (sớm) hoặc oligodendrocyte (muộn) |

Mọi NSC có **cùng "interface"**: phân chia, di trú, biệt hóa. Nhưng sản phẩm cuối cùng (loại neuron) được quyết định bởi **subclass-specific signaling context**.

Nói cách khác: bộ gene cốt lõi của NSC là *creator interface*; cấu hình morphogen ở vị trí đó là *concrete creator*; loại neuron là *concrete product*. Một NSC ở vùng dorsal forebrain *là một subclass* của NSC chung, override quyết định "tôi sẽ tạo glutamatergic neuron".

### Phân biệt nhanh: Simple Factory ≠ Factory Method

- **Simple Factory** (chưa phải GoF pattern, chỉ là idiom): 1 hàm/class với if-else trả về subclass. Đỡ duplicate code nhưng vẫn vi phạm Open-Closed.
- **Factory Method** (GoF): superclass khai báo abstract method `create_product()`, mỗi subclass override. Thêm loại product mới = thêm subclass, không sửa code cũ.

Bài học: nếu bạn vừa viết Simple Factory rồi thấy if-else lại dài thêm, đó là tín hiệu "đáng ra phải dùng Factory Method ngay từ đầu".

---

## Mức 2 — ALGORITHM (Thuật toán)

### Cấu tạo (5 chiều theo framework Ellumm)

| Chiều | Nội dung |
|-------|----------|
| **Cấu tạo** | (a) `Product` interface, (b) `ConcreteProduct` các loại, (c) `Creator` abstract class với `factory_method()` abstract + `template_operation()` concrete, (d) `ConcreteCreator` override `factory_method()` |
| **Vị trí** | Tầng domain hoặc service. Khác với Singleton ở infrastructure, Factory Method nằm trong nghiệp vụ. |
| **Chức năng** | Đóng gói **quyết định kiểu cụ thể** vào subclass, tách khỏi code dùng object. |
| **Kết nối** | Client chỉ biết `Creator` + `Product` interface, không biết concrete types. |
| **Ý nghĩa** | Áp dụng nguyên lý **Open-Closed** + **Dependency Inversion** cho việc tạo object. |

### Các vai trò (theo GoF)

```
            ┌──────────────────────────┐
            │       Creator (abstract) │
            │ + operation()  [template]│
            │ + factory_method() [abs] │ ─────────┐
            └──────────┬───────────────┘          │
                       △                          │ tạo
        ┌──────────────┼──────────────┐           ▼
   ┌────┴─────┐   ┌────┴─────┐    ┌────┴─────┐  ┌──────────────┐
   │DorsalNSC │   │VentralNSC│    │CerebNSC  │  │   Product    │
   │+ factory │   │+ factory │    │+ factory │  │   (interface)│
   │ → Glut.  │   │ → GABA   │    │ → Granule│  └──────┬───────┘
   └──────────┘   └──────────┘    └──────────┘         △
                                                        │
                          ┌─────────────────────────────┼──────────┐
                  ┌───────┴────────┐  ┌─────────────┐  ┌┴──────────┐
                  │GlutamatergicN  │  │GABAergicN   │  │GranuleCell│
                  └────────────────┘  └─────────────┘  └───────────┘
```

### Logic vận hành

```
client KHÔNG gọi:        new GlutamatergicNeuron()
client GỌI:              dorsal_nsc.differentiate()
                              │
                              ▼
                          template method:
                              neuron = self.factory_method()    ← subclass override
                              neuron.migrate()
                              neuron.form_synapses()
                              return neuron
```

`differentiate()` là **template** chung cho mọi NSC: gọi factory method (override theo subclass) để tạo neuron, rồi chạy các bước phổ thông (migrate, form synapses). Code chung này viết **đúng 1 lần**, mở rộng không cần sửa.

### Nguyên lý liên quan

- **Open-Closed Principle**: thêm `StriatalNSC` không cần sửa `Creator` hay client.
- **Dependency Inversion**: client phụ thuộc abstraction (`Neuron`), không phụ thuộc concrete (`GlutamatergicNeuron`).
- **Liskov Substitution**: mọi `Neuron` subclass phải dùng được ở chỗ client kỳ vọng `Neuron`.

---

## Mức 3 — PSEUDOCODE + PYTHON

### Pseudocode

```
abstract class Neuron:
    abstract function fire(): ...
    abstract function neurotransmitter(): str

abstract class NeuralStemCell:
    function differentiate() -> Neuron:        # template method
        neuron = self.create_neuron()          # ← Factory Method (abstract)
        neuron.migrate()
        neuron.form_synapses()
        return neuron

    abstract function create_neuron() -> Neuron

class DorsalForebrainNSC extends NeuralStemCell:
    function create_neuron() -> Neuron:
        return GlutamatergicNeuron()           # quyết định cụ thể ở subclass

class VentralForebrainNSC extends NeuralStemCell:
    function create_neuron() -> Neuron:
        return GABAergicInterneuron()
```

### Python (xem file `02_factory_method.py`)

File code triển khai:
1. **Phiên bản anti-pattern** (if-else trong code chung) để bạn thấy đau khi mở rộng.
2. **Factory Method đầy đủ** với `NeuralStemCell` abstract + 4 subclass NSC vùng não khác nhau.
3. **Phiên bản Pythonic gọn** dùng class attribute thay cho method (khi factory method chỉ là "trả về 1 class") — đây là tối ưu Python phổ biến.
4. **Demo failure**: nếu một subclass quên override `create_neuron`, hệ thống raise `NotImplementedError` ngay khi khởi tạo NSC đó — fail-fast đúng tinh thần TypeError sớm còn hơn bug ngầm.

---

## 3 LOẠI VÍ DỤ

### Ví dụ 1 — Vận hành thường

Trong giai đoạn embryonic week 8-12 ở người, vùng dorsal pallium của telencephalon bắt đầu neurogenesis. Mỗi NSC ở đây *là một instance* của `DorsalForebrainNSC`. Khi gọi `nsc.differentiate()`:
1. Template gọi `create_neuron()` → trả về `GlutamatergicNeuron`.
2. Template gọi `neuron.migrate()` → neuron leo theo radial glia lên cortical plate.
3. Template gọi `neuron.form_synapses()` → mọc dendrite, tạo synapse với neuron lân cận.

Cùng lúc, ở vùng medial ganglionic eminence, các NSC *là instance* của `VentralForebrainNSC` — gọi cùng `differentiate()` nhưng `create_neuron()` trả về `GABAergicInterneuron`. Hai dòng phát triển song song, dùng *cùng template logic*, sản phẩm khác nhau. Đó chính là Factory Method ở mức tế bào.

### Ví dụ 2 — Hỏng / Thiếu

**Trường hợp sinh học**: holoprosencephaly là rối loạn phát triển trong đó tín hiệu Shh (morphogen ventral) sai → vùng ventral forebrain không biệt hóa thành interneuron đúng cách. "Factory" sai context tạo product sai → cấu trúc não bị merge giữa hai bán cầu, dẫn đến rối loạn nặng. Bài học: factory phụ thuộc vào **context (signaling)** đúng — sai context, sai product.

**Trường hợp code**: viết Simple Factory với if-else, sau 6 tháng team thêm 12 loại neuron mới. Hàm factory dài 200 dòng if-else, mỗi loại có vài biến thể nhỏ. Tester không thể test tất cả nhánh. Một bug "sai loại neuron khi region_name có khoảng trắng cuối" tồn tại 3 tháng vì test không cover. Đây là chi phí của việc không refactor sang Factory Method khi if-else vượt 3 nhánh.

### Ví dụ 3 — Ứng dụng Ellumm

Ellumm có pixel-tracing phát hiện pattern lặp ổn định. Mỗi pattern cần được encode thành một **MemoryUnit**, nhưng loại MemoryUnit phụ thuộc vào nguồn:
- Visual pattern → `VisualMemoryUnit` (lưu pixel signature, eye-position context)
- Auditory pattern → `AuditoryMemoryUnit` (lưu spectral signature, temporal envelope)
- Internal state pattern → `InteroceptiveMemoryUnit` (lưu emotion vector, hormonal context)
- Cross-modal pattern → `MultimodalMemoryUnit` (gắn các unit con với nhau)

Cấu trúc:

```python
class SensoryRegion(ABC):
    def encode_pattern(self, raw_signal):           # template
        unit = self.create_memory_unit(raw_signal)  # factory method
        unit.tag_with_context(GlobalEmotionState())
        unit.consolidate()
        return unit

    @abstractmethod
    def create_memory_unit(self, raw_signal): ...

class VisualCortex(SensoryRegion):
    def create_memory_unit(self, raw_signal):
        return VisualMemoryUnit(raw_signal)

class AuditoryCortex(SensoryRegion):
    def create_memory_unit(self, raw_signal):
        return AuditoryMemoryUnit(raw_signal)
```

Khi Ellumm sau này thêm `OlfactoryCortex` hoặc `TactileCortex` — chỉ thêm subclass mới, không đụng đến code đã chạy ổn định của VisualCortex và AuditoryCortex. Đây là **giá trị kỹ sư thật** của Factory Method: khả năng mở rộng mà không gây regression.

---

## TÓM LẠI

Factory Method = **tách quyết định "tạo loại nào" ra khỏi code dùng object**, ủy thác cho subclass. Trong não, NSC + morphogen là Factory Method tự nhiên: cùng creator interface, sản phẩm phụ thuộc context. Trong code, dấu hiệu cần Factory Method là **if-else dài chọn class theo tham số**.

Pattern này thường đi cặp với **Template Method** (lesson 22): `differentiate()` là template, `create_neuron()` là factory method bên trong template. Hai pattern này là cặp đôi cổ điển — Template điều phối quy trình, Factory cung cấp object cho quy trình.

### Câu hỏi tự kiểm tra

1. Tại sao Factory Method **không phải** là Singleton, dù đôi khi cài đặt giống nhau (1 instance Creator dùng chung)?
2. Khi nào nên dùng Factory Method vs **Strategy** (lesson 21)? Cả hai đều dùng inheritance để tùy biến hành vi.
3. Trong Ellumm, nếu bạn cần tạo cả `VisualMemoryUnit` + `VisualEmotionTag` + `VisualConsolidationPolicy` cùng một lúc (vì chúng phải khớp nhau), Factory Method có đủ không, hay cần pattern khác? (Gợi ý: lesson 03)
