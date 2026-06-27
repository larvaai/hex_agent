# Lesson 03 — Abstract Factory

> **Cung cấp interface để tạo HỌ object liên quan và khớp nhau, không cần chỉ ra class cụ thể.**

---

## Mức 1 — CONCEPT (Ý tưởng)

### Vấn đề pattern giải quyết

Factory Method (lesson 02) tạo **một** loại object — neuron. Nhưng não thật không chỉ có neuron. Một vùng não vận hành được cần **cả một họ tế bào và mô khớp nhau**:

- Neuron chính (principal neuron)
- Glia hỗ trợ đặc thù vùng đó
- Extracellular matrix (ECM) đúng thành phần
- Vasculature với đặc tính BBB phù hợp

Bạn KHÔNG thể đặt một Purkinje cell (cerebellum) giữa môi trường có protoplasmic astrocyte (cortex) và mong nó hoạt động — Purkinje cell *cần* Bergmann glia bao quanh, *cần* climbing fiber từ inferior olive, *cần* ECM cerebellar đặc thù. Cả họ phải khớp nhau hoặc không vùng nào hoạt động.

Nếu code tạo từng object riêng lẻ:

```python
# ❌ Dễ trộn nhầm — không có gì ngăn bạn ghép sai họ
neuron = PyramidalNeuron()         # cortical
glia = BergmannGlia()              # cerebellar! sai
ecm = HippocampalECM()             # hippocampal! sai
# Hệ thống compile được, runtime mới hỏng — bug ngầm khó truy
```

Abstract Factory giải quyết bằng cách: **một factory chịu trách nhiệm tạo nguyên một họ object khớp nhau**. Client không thể trộn lẫn vì không có cách nào ghép `CorticalFactory` với `BergmannGlia` — `CorticalFactory.create_glia()` trả về `ProtoplasmicAstrocyte`, không có route nào trả về Bergmann.

### Neuroscience analogy — Brain Region Ecosystems

Mỗi vùng não là một **ecosystem** mà các thành phần đã đồng tiến hóa để khớp:

| Vùng não | Neuron chính | Glia đặc thù | ECM | BBB |
|----------|--------------|--------------|-----|-----|
| Cortex | Pyramidal neuron (layer-specific) | Protoplasmic astrocyte | Hyaluronan + tenascin | Tight (blood-brain barrier chặt) |
| Cerebellum | Purkinje cell + granule cell | Bergmann glia (radial!) | Cerebellar-specific proteoglycans | Tight |
| Hippocampus | DG granule + CA1/CA3 pyramidal | Radial glia (vẫn là stem cell ở người trưởng thành) | Perineuronal nets quanh PV interneurons | Hơi leaky hơn cortex |
| Circumventricular organs | Neuroendocrine neurons | Tanycyte | ECM cho phép thẩm thấu | Không có BBB (intentionally!) |

Bergmann glia *chỉ có* ở cerebellum. Tanycyte *chỉ có* ở circumventricular organs. Không thể "import" component từ vùng khác — chúng đã được tinh chỉnh cho neuron chủ và signaling pathway của vùng đó.

→ Mỗi "vùng não" là một **Concrete Factory**. Cùng implement interface `BrainRegionEcosystem`, nhưng mỗi factory tạo họ tế bào khác nhau và khớp nhau nội tại.

### Phân biệt: Factory Method vs Abstract Factory

| | Factory Method | Abstract Factory |
|---|----------------|-------------------|
| Tạo gì | 1 product | Họ N products khớp nhau |
| Cấu trúc | Inheritance: subclass override 1 method | Composition: 1 object có N method, mỗi method tạo 1 product |
| Câu hỏi nó trả lời | "Loại neuron nào ở vùng này?" | "Cả ecosystem nào ở vùng này?" |
| Mở rộng dễ | Thêm loại neuron mới | Thêm cả vùng não mới (kèm họ products) |
| Mở rộng khó | Thêm chiều product mới (vd: glia) | Thêm 1 product type mới vào họ — tất cả factory phải sửa |

Đây là **trade-off cốt lõi**: Abstract Factory dễ thêm *family* mới nhưng khó thêm *product type* mới. Factory Method ngược lại. Architect phải dự đoán hướng mở rộng nào sẽ xảy ra trong tương lai.

---

## Mức 2 — ALGORITHM (Thuật toán)

### Cấu tạo (5 chiều theo framework Ellumm)

| Chiều | Nội dung |
|-------|----------|
| **Cấu tạo** | (a) Abstract Factory với N abstract create methods, (b) Concrete Factory mỗi cái cài đặt N method để tạo 1 family, (c) N abstract Product interfaces, (d) N×M Concrete Products (M = số family) |
| **Vị trí** | Tầng domain. Là composition root nội bộ — client nhận factory đã cấu hình, không gọi `new` trực tiếp. |
| **Chức năng** | Đảm bảo **family integrity** (mọi product cùng họ khớp nhau) + đóng gói quyết định "dùng họ nào". |
| **Kết nối** | Client → AbstractFactory → tạo các Product interface. Không có path từ client đến Concrete Product. |
| **Ý nghĩa** | Khi domain có **nhiều biến thể song song** mà mỗi biến thể là một bộ object phải đi cùng nhau. |

### Sơ đồ class

```
                        ┌─────────────────────────────────┐
                        │   BrainRegionEcosystem (abs.)   │
                        │ + create_principal_neuron()     │
                        │ + create_supporting_glia()      │
                        │ + create_ecm()                  │
                        │ + create_vasculature()          │
                        └────────┬────────────────────────┘
                                 △
              ┌──────────────────┼──────────────────┐
        ┌─────┴────────┐  ┌──────┴──────┐  ┌────────┴────────┐
        │CorticalEcosys│  │CerebellarEco│  │HippocampalEco   │
        └──────────────┘  └─────────────┘  └─────────────────┘
              │                  │                  │
              ▼ tạo               ▼ tạo               ▼ tạo
        ┌──────────────────────────────────────────────────────┐
        │      4 product interfaces × 3 family = 12 classes    │
        │ ┌──────────┐  ┌──────┐  ┌─────┐  ┌──────────────┐   │
        │ │P.Neuron  │  │ Glia │  │ ECM │  │ Vasculature  │   │
        │ └──────────┘  └──────┘  └─────┘  └──────────────┘   │
        └──────────────────────────────────────────────────────┘
```

### Logic vận hành

```
client cần build cortex:
    factory = CorticalEcosystem()       ← chọn họ 1 lần
    neuron  = factory.create_principal_neuron()    → PyramidalNeuron
    glia    = factory.create_supporting_glia()     → ProtoplasmicAstrocyte
    ecm     = factory.create_ecm()                 → CorticalECM
    vessel  = factory.create_vasculature()         → CorticalBBB

    region = BrainRegion(neuron, glia, ecm, vessel)
    # Không có cách nào client lấy được Bergmann glia từ CorticalEcosystem.
```

Quan sát quan trọng: client thấy biến `factory: BrainRegionEcosystem` (interface), không biết đang là `Cortical` hay `Cerebellar`. Ai cấu hình `factory =` ở composition root quyết định toàn bộ família — phần code còn lại "platform-agnostic".

### Nguyên lý liên quan

- **Open-Closed**: thêm `BasalGangliaEcosystem` không sửa code cũ.
- **Dependency Inversion**: client phụ thuộc abstraction (`BrainRegionEcosystem` + 4 product interfaces).
- **Single Responsibility**: factory chỉ chịu trách nhiệm "chọn họ"; product chỉ chịu trách nhiệm hành vi của mình.

---

## Mức 3 — PSEUDOCODE + PYTHON

### Pseudocode

```
abstract class BrainRegionEcosystem:
    abstract function create_principal_neuron(): Neuron
    abstract function create_supporting_glia(): Glia
    abstract function create_ecm(): ECM
    abstract function create_vasculature(): Vasculature

class CorticalEcosystem extends BrainRegionEcosystem:
    create_principal_neuron() -> PyramidalNeuron
    create_supporting_glia()  -> ProtoplasmicAstrocyte
    create_ecm()              -> CorticalECM
    create_vasculature()      -> CorticalBBB

class CerebellarEcosystem extends BrainRegionEcosystem:
    create_principal_neuron() -> PurkinjeCell
    create_supporting_glia()  -> BergmannGlia
    create_ecm()              -> CerebellarECM
    create_vasculature()      -> CerebellarBBB

# Client KHÔNG gọi new trực tiếp:
function build_brain_region(factory: BrainRegionEcosystem) -> BrainRegion:
    return BrainRegion(
        neuron = factory.create_principal_neuron(),
        glia   = factory.create_supporting_glia(),
        ecm    = factory.create_ecm(),
        vessel = factory.create_vasculature(),
    )
```

### Python (xem file `03_abstract_factory.py`)

File code triển khai:
1. **4 abstract product interfaces** (`PrincipalNeuron`, `SupportingGlia`, `ExtracellularMatrix`, `Vasculature`).
2. **3 concrete factories** (Cortical, Cerebellar, Hippocampal) — mỗi cái sản xuất 1 họ 4 product khớp nhau.
3. **Compatibility check tự động** — neuron có method `compatible_with(glia)` raise error nếu sai họ. Đây là cách mã hóa "family integrity" thành runtime check.
4. **Demo failure** mô phỏng heterotopia: ép trộn họ → vùng não không hoạt động.
5. **Ellumm version**: `ModalityFactory` cho visual / auditory / interoceptive — mỗi cái tạo bộ memory unit + emotion tag + consolidation policy + retrieval index khớp nhau.

---

## 3 LOẠI VÍ DỤ

### Ví dụ 1 — Vận hành thường

Trong tuần 8-20 của thai kỳ, neurogenesis cortex bắt đầu ở dorsal pallium. Hệ thống signaling Wnt/BMP định danh vùng này là cortex → "instantiate" `CorticalEcosystem`. Từ đó:
- Pyramidal neuron sinh ra ở ventricular zone, di trú lên cortical plate.
- Protoplasmic astrocyte sinh ra song song (gliogenesis bắt đầu sau neurogenesis).
- ECM cortical (hyaluronan, tenascin-C) được tổng hợp tại chỗ.
- Vasculature mọc vào cortical plate với BBB tight.

Bốn thành phần này *được tạo trong cùng một context signaling*, vì thế chúng tự nhiên khớp. Pyramidal neuron có receptor đáp ứng đúng tín hiệu glutamate-glutamine cycle mà protoplasmic astrocyte cung cấp. ECM cortical hỗ trợ đúng kiểu dendrite arborization của pyramidal neuron. Đây là Abstract Factory hoạt động ở mức phát triển phôi.

### Ví dụ 2 — Hỏng / Thiếu

**Trường hợp sinh học**: subcortical band heterotopia (SBH, "double cortex syndrome") — đột biến gene LIS1/DCX khiến một phần neuron pyramidal di trú dở dang, dừng lại trong substance trắng. Những neuron lạc chỗ này:
- *Là* PyramidalNeuron (đúng identity).
- Nhưng môi trường quanh chúng là white matter ECM, không phải cortical ECM.
- Không có protoplasmic astrocyte cortical bao quanh.
- Vasculature kiểu khác.

→ Họ tế bào không khớp → mạng lưới rối loạn → bệnh nhân thường có động kinh và thiểu năng trí tuệ. Đây chính xác là kịch bản "trộn product từ các family khác nhau" mà Abstract Factory được thiết kế để chặn.

**Trường hợp code**: app dùng GUI framework Qt. Lập trình viên import nhầm `from PySide6 import QPushButton` và `from PyQt5 import QMainWindow` cùng lúc. Compile/runtime không lỗi rõ — nhưng button render sai theme, signal-slot connection sometime mất. Bug *ngẫu hứng*, debug kinh hoàng. Abstract Factory (ở đây là cấu hình "1 binding duy nhất per app") chặn ngay từ kiến trúc.

### Ví dụ 3 — Ứng dụng Ellumm

Ellumm có nhiều **modality** — visual, auditory, interoceptive, motor. Mỗi modality cần một họ object khớp nhau để encode ký ức:

| Modality | MemoryUnit | EmotionTag | ConsolidationPolicy | RetrievalIndex |
|----------|-----------|------------|---------------------|----------------|
| Visual | pixel signature + saccade trace | visual valence (đẹp/xấu) | replay khi REM, sleep-dependent | spatial-grid |
| Auditory | spectral envelope + temporal contour | tonal valence (vui/buồn) | replay rapid, NREM-2 | pitch-time grid |
| Interoceptive | hormone vector + body-map | bodily affect (dễ chịu/khó chịu) | continuous reinforcement | somatic-cluster |

`VisualEmotionTag` không hiểu spectral data. `AuditoryRetrievalIndex` không có spatial-grid. **Bắt buộc** phải đi cùng họ.

```python
class ModalityEcosystem(ABC):
    def encode(self, raw_signal):
        unit = self.create_memory_unit(raw_signal)
        tag  = self.create_emotion_tag()
        unit.attach(tag)
        policy = self.create_consolidation_policy()
        index  = self.create_retrieval_index()
        return EncodedMemory(unit, policy, index)
    
    @abstractmethod
    def create_memory_unit(self, raw_signal): ...
    @abstractmethod
    def create_emotion_tag(self): ...
    @abstractmethod
    def create_consolidation_policy(self): ...
    @abstractmethod
    def create_retrieval_index(self): ...
```

Sau này khi Ellumm thêm modality `Olfactory`, chỉ cần thêm `OlfactoryEcosystem` với 4 concrete classes — không sửa Visual/Auditory/Interoceptive đã ổn định.

Nếu bạn dự đoán Ellumm sẽ cần thêm "chiều product" mới (vd: thêm `AttentionFilter` cho mỗi modality), cân nhắc Builder (lesson 04) hoặc combine với Composite (lesson 08) thay vì đổ thêm vào Abstract Factory.

---

## TÓM LẠI

Abstract Factory = **tạo nguyên họ object khớp nhau, qua một interface duy nhất**. Trong não, mỗi vùng phát triển là một ecosystem có sản phẩm đã đồng tiến hóa — neuron + glia + ECM + vasculature đặc thù vùng đó. Heterotopia/SBH là minh chứng sinh học rằng "trộn họ" gây lỗi nghiêm trọng.

Trade-off architect cần ý thức:
- Abstract Factory dễ **thêm họ mới** (vùng não mới, theme UI mới, database driver mới).
- Abstract Factory khó **thêm chiều product mới** (phải sửa toàn bộ concrete factory).
- Khi có ≥ 3 product types đi cùng nhau và ≥ 2 family song song, đây là pattern đúng. Dưới ngưỡng đó, Factory Method đã đủ.

### Câu hỏi tự kiểm tra

1. Tại sao Abstract Factory thường được dùng cùng với Singleton (lesson 01) trong các framework lớn? (Gợi ý: composition root)
2. Nếu Ellumm thêm `AttentionFilter` cho mọi modality (chiều product mới), bạn refactor thế nào để giảm đau? (Gợi ý: registry-based factory hoặc Builder)
3. Trong não, glia (đặc biệt astrocyte) có thể được "tái sử dụng" giữa các vùng ở mức nào? Phần nào "không tái sử dụng được"? Bài học gì cho việc thiết kế Concrete Product trong Abstract Factory? (Gợi ý: Flyweight + region-specific phenotype)
