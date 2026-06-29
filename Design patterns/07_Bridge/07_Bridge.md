# Lesson 07 — Bridge

> **Tách abstraction khỏi implementation để hai dimension biến đổi độc lập, tránh bùng nổ class do tổ hợp.**

---

## Mức 1 — CONCEPT (Ý tưởng)

### Vấn đề pattern giải quyết — Cartesian explosion

Bạn có domain với 2 dimension thay đổi độc lập:
- **Dimension A** (loại signal): Form, Color, Motion (3 biến thể)
- **Dimension B** (pathway dẫn truyền): Parvocellular, Magnocellular, Koniocellular (3 biến thể)

Nếu dùng inheritance để biểu diễn:
```python
# ❌ 3 × 3 = 9 class. Thêm 1 dimension biến thể = nhân bội
class FormViaParvocellular: ...
class FormViaMagnocellular: ...
class FormViaKoniocellular: ...
class ColorViaParvocellular: ...
class ColorViaMagnocellular: ...   # bất hợp lý sinh học, nhưng inheritance ép phải có
class ColorViaKoniocellular: ...
class MotionViaParvocellular: ...
class MotionViaMagnocellular: ...
class MotionViaKoniocellular: ...
```

Thêm 1 loại signal (Depth) hoặc 1 pathway (Superior Colliculus) → **nhân thêm hàng loạt class**. Đây là **Cartesian explosion** — anti-pattern kinh điển.

Bridge giải quyết bằng cách: **không lồng inheritance, dùng composition để bắc cầu giữa 2 hierarchy độc lập**.

```python
# ✓ 3 + 3 = 6 class. Thêm 1 biến thể = thêm 1 class.
class VisualInformation:                       # Abstraction
    def __init__(self, pathway: Pathway):      # composition
        self._pathway = pathway

class FormInformation(VisualInformation): ...
class ColorInformation(VisualInformation): ...
class MotionInformation(VisualInformation): ...

class Pathway:                                 # Implementor
    def process(self, signal): ...

class ParvocellularPathway(Pathway): ...
class MagnocellularPathway(Pathway): ...
class KoniocellularPathway(Pathway): ...

# Runtime:
form_p = FormInformation(ParvocellularPathway())
motion_m = MotionInformation(MagnocellularPathway())
```

### Neuroscience analogy — Parvocellular vs Magnocellular

Hệ visual của linh trưởng (bao gồm con người) thực sự được thiết kế theo Bridge ở mức sinh học. Có 2 dimension độc lập:

**Dimension 1 — Loại visual information** (cái não cần biết):

| Loại | Dùng cho |
|------|----------|
| Form (hình dạng) | Nhận diện vật thể, đọc chữ |
| Color (màu sắc) | Phân biệt thực phẩm chín/xanh, signal xã hội |
| Motion (chuyển động) | Phát hiện animate object, navigation |
| Depth (độ sâu) | Reach-and-grasp, navigation 3D |
| Texture (bề mặt) | Phân loại vật liệu, surface property |

**Dimension 2 — Pathway** (cách signal được dẫn truyền):

| Pathway | Đặc tính | Tốc độ |
|---------|----------|--------|
| **Parvocellular (P)** | High spatial resolution, color-sensitive (red-green opponent), small receptive field | Slow (~30 ms) |
| **Magnocellular (M)** | Low spatial resolution, color-blind, large receptive field, motion-sensitive | Fast (~15 ms) |
| **Koniocellular (K)** | Blue-yellow color, less understood, smaller cells | Trung bình |

**Cross-routing thực tế trong não:**

| Loại signal | Pathway chủ yếu |
|-------------|-----------------|
| Form-fine detail | P (LGN layer 3-6 → V1 layer 4Cβ → V2 thin stripes → V4) |
| Color-redgreen | P (cùng route) |
| Color-blueyellow | K (LGN K-layers → V1 blob) |
| Motion | M (LGN layer 1-2 → V1 layer 4Cα → V2 thick stripes → V5/MT) |
| Depth-coarse | M (gắn với motion processing) |
| Depth-fine | P (gắn với detail) |

Lưu ý: **cùng một loại signal (Depth) có thể đi qua nhiều pathway** — não routing dựa vào nhiệm vụ. Đây chính xác là Bridge: abstraction (signal type) decouple khỏi implementation (pathway), runtime composition.

**Chứng cứ thuyết phục cho thiết kế Bridge ở não:**

| Lesion | Hậu quả | Bằng chứng decoupling |
|--------|---------|------------------------|
| **V4 lesion** (P-pathway destination) | Cerebral achromatopsia — mất hoàn toàn color perception, form/motion còn nguyên | Color tách rời được khỏi form/motion |
| **V5/MT lesion** (M-pathway destination) | Akinetopsia — mất motion perception (thấy "chuỗi ảnh tĩnh"), color/form còn nguyên | Motion tách rời được khỏi color/form |
| **LGN P-layer lesion** | Mất color + form-detail, motion intact | Pathway lựa chọn lọc, không phá toàn diện |

Nếu não dùng inheritance ("FormColorViaParvo" như một module monolithic), 1 lesion sẽ phá tất cả. Vì các dimension thực sự decoupled qua Bridge sinh học, lesion 1 dimension không phá dimension kia. Đây là hiệu quả thiết kế tiến hóa đã chọn.

### Bridge vs Adapter — phân biệt rõ

| | Adapter (lesson 06) | Bridge |
|---|---------------------|--------|
| Mục đích | Fix mismatch giữa 2 interface đã tồn tại | Prevent Cartesian explosion từ đầu |
| Khi quyết định dùng | Sau khi đã có code, cần tích hợp | Khi thiết kế, dự đoán 2+ dimension biến đổi độc lập |
| Vị trí | Biên hệ thống (boundary) | Trong domain core |
| Số dimension | 1 (translate A→B) | 2 (cả Abstraction và Implementor đều có hierarchy) |
| Cấu trúc | Adaptee hiện hữu, không sửa | Abstraction được thiết kế bridge từ đầu |

Quy tắc nhanh: nếu bạn đang **fix problem** với code đã có, đó là Adapter. Nếu bạn đang **thiết kế** code mới với 2 trục mở rộng độc lập, đó là Bridge.

---

## Mức 2 — ALGORITHM (Thuật toán)

### Cấu tạo (5 chiều theo framework Ellumm)

| Chiều | Nội dung |
|-------|----------|
| **Cấu tạo** | (a) `Abstraction` (interface phía client thấy), (b) `RefinedAbstraction` (subclass chuyên biệt hóa), (c) `Implementor` (interface implementation), (d) `ConcreteImplementor`. Abstraction giữ ref tới Implementor qua composition. |
| **Vị trí** | Domain core. Không phải biên hệ thống như Adapter. |
| **Chức năng** | Cho phép cả 2 dimension mở rộng độc lập, runtime composition. |
| **Kết nối** | Client → Abstraction → (composition) → Implementor → ConcreteImplementor. |
| **Ý nghĩa** | Tránh inheritance explosion + cho phép switch implementor runtime. |

### Sơ đồ class

```
   ┌─────────────────────┐                     ┌─────────────────────┐
   │ VisualInformation   │ ────uses────────►   │   Pathway (impl)    │
   │  (Abstraction)      │   composition       │   abstract          │
   │ - pathway: Pathway  │                     │ + process(signal)   │
   │ + extract()         │                     └──────────┬──────────┘
   └──────────┬──────────┘                                △
              △                                           │
   ┌──────────┼──────────┐                ┌───────────────┼──────────────┐
   │          │          │                │               │              │
 Form      Color      Motion         Parvo            Magno            Konio
Information Info     Information   Pathway          Pathway          Pathway
   │          │          │                │               │              │
   └──────────┴──────────┘                └───────────────┴──────────────┘
        (3 lớp)                                       (3 lớp)
        Total = 6, không phải 9
```

### Logic vận hành

```
1. Setup runtime composition:
    form_signal = FormInformation(pathway=ParvocellularPathway())
    color_signal = ColorInformation(pathway=KoniocellularPathway())
    motion_signal = MotionInformation(pathway=MagnocellularPathway())

2. Client gọi method trên Abstraction:
    form_signal.extract(scene)
        └→ delegate đến self._pathway.process(scene)
            └→ ParvocellularPathway.process(scene) → spike train slow + high-resolution

3. Có thể swap pathway runtime (mô phỏng attentional re-routing):
    motion_signal._pathway = ParvocellularPathway()
    # Bây giờ motion đi qua P pathway — slow + high detail
    # (sinh học: ít gặp, nhưng có trong attentional control)

4. Thêm pathway mới (vd: Superior Colliculus subcortical):
    class SuperiorColliculusPathway(Pathway): ...
    # KHÔNG sửa class nào trong Abstraction hierarchy
    # Tất cả VisualInformation subclass tự dùng được pathway mới
```

### Nguyên lý liên quan

- **Composition over inheritance**: nguyên lý cốt lõi của Bridge.
- **Open-Closed**: thêm 1 dimension biến thể không sửa dimension kia.
- **Single Responsibility**: Abstraction tập trung vào "what to extract", Implementor tập trung vào "how to dispatch".

### Khi nào KHÔNG dùng Bridge

- Chỉ có 1 dimension thay đổi → dùng Strategy hoặc Template Method, đơn giản hơn.
- 2 dimension thực ra không độc lập (1 luôn quyết định cái kia) → dùng Factory Method.
- Domain nhỏ, không có khả năng mở rộng → đừng over-engineer. Inheritance đơn giản đủ dùng.

---

## Mức 3 — PSEUDOCODE + PYTHON

### Pseudocode

```
abstract class Pathway:                              # Implementor
    abstract function process(signal: dict) -> dict

class ParvocellularPathway extends Pathway:
    function process(signal):
        return high_resolution_slow_processing(signal)

class MagnocellularPathway extends Pathway:
    function process(signal):
        return low_resolution_fast_motion_processing(signal)

abstract class VisualInformation:                    # Abstraction
    field pathway: Pathway

    function extract(scene) -> Result:
        # Subclass tùy biến phần "trích xuất gì",
        # phần "đi pathway nào" giao cho pathway
        feature = self._select_feature(scene)
        return self.pathway.process(feature)

class FormInformation extends VisualInformation:
    function _select_feature(scene): return scene.edges_and_contours

class ColorInformation extends VisualInformation:
    function _select_feature(scene): return scene.color_channels

class MotionInformation extends VisualInformation:
    function _select_feature(scene): return scene.frame_diff
```

### Python (xem file `07_bridge.py`)

File code triển khai:
1. **Anti-pattern Cartesian explosion** — 3×3=9 class với inheritance, để cảm nhận nỗi đau.
2. **Bridge đầy đủ**: `Pathway` (Implementor) hierarchy 3 cái + `VisualInformation` (Abstraction) hierarchy 3 cái + composition.
3. **Demo runtime swap**: cùng signal type, đổi pathway → kết quả khác.
4. **Demo achromatopsia**: phá ParvocellularPathway → color/form bị ảnh hưởng nhưng motion (qua M) còn nguyên.
5. **Demo akinetopsia**: phá MagnocellularPathway → motion mất, form/color còn.
6. **Mở rộng không sửa**: thêm `SuperiorColliculusPathway` (subcortical, fast reflex) — abstraction hierarchy không bị đụng.
7. **Ellumm version**: `MemoryOperation × StorageBackend` bridge — encode/retrieve/consolidate × in-memory/sqlite/vector DB.

---

## 3 LOẠI VÍ DỤ

### Ví dụ 1 — Vận hành thường

Bạn đi trong rừng, thấy một vật thể chuyển động ở tầm nhìn ngoại vi. Quy trình thực tế:
1. Retina phát signal đến LGN (peripheral vision có nhiều M-cell hơn).
2. **Motion information** được routing chủ yếu qua **Magnocellular pathway** → V1 layer 4Cα → V2 thick stripes → **V5/MT** (motion area). Tốc độ ~15ms — đủ nhanh cho phản ứng phòng vệ tiềm năng.
3. **Cùng vật thể**, signal cũng được phân nhánh đi **Parvocellular pathway** → V1 layer 4Cβ → V4 (form area) cho **form recognition** chậm hơn (~30ms+).
4. Trong khi M pathway đã đưa amygdala vào trạng thái cảnh giác, P pathway từ từ identify "đó là con sóc, không phải rắn".

Hai pathway xử lý **cùng input** nhưng cho ra **2 loại information khác nhau** ở 2 tốc độ khác nhau. Cả hai song song, không phụ thuộc nhau. Đây là Bridge tự nhiên: dimension "loại info" tách rời khỏi dimension "pathway".

Trong code Bridge tương đương: `MotionInformation(MagnocellularPathway())` chạy fast, `FormInformation(ParvocellularPathway())` chạy slow, cả hai cùng nhận một `scene` và trả 2 result. Có thể chạy đồng thời (asyncio).

### Ví dụ 2 — Hỏng / Thiếu

**Cerebral achromatopsia** (sau stroke V4 hai bên): bệnh nhân mô tả thế giới như "phim đen trắng cũ". Nhưng:
- Vẫn nhận diện được vật thể (form intact).
- Vẫn theo dõi được chuyển động (motion intact).
- Chỉ mất color.

Đây là chứng cứ Bridge ở não: phá P-pathway destination cho color (V4) không phá pathway-routing cho form/motion. Nếu thiết kế monolithic (mọi visual info nén chung), lesion V4 sẽ phá toàn diện.

**Akinetopsia** (sau stroke V5/MT hai bên — bệnh nhân LM năm 1983 là ca nổi tiếng): bệnh nhân thấy thế giới "như một loạt ảnh tĩnh" — không cảm nhận được chuyển động liên tục. Cô không thể rót nước vào cốc vì không thấy mức nước dâng lên. Nhưng:
- Form intact (vẫn nhận diện vật thể).
- Color intact.
- Chỉ mất motion.

Bridge một lần nữa: phá M-pathway destination không phá P và K pathway destination.

**Trường hợp code — Cartesian explosion thực tế**:
Một codebase logging có 4 log level × 3 sink (file, console, network) × 2 format (JSON, plaintext) = 24 class nếu inheritance. Mỗi lần thêm sink hoặc format → thêm 8-12 class. 6 tháng sau, codebase có 200+ class log, không ai hiểu hierarchy. Đây là Cartesian explosion thực — Bridge ngay từ đầu sẽ giữ ở 4+3+2 = 9 class.

### Ví dụ 3 — Ứng dụng Ellumm

Trong Ellumm có 2 dimension cần độc lập:

**Dimension A — Memory Operation**: Encode, Retrieve, Consolidate, Forget
**Dimension B — Storage Backend**: InMemoryDict, SQLite, VectorDB, CloudSync

Inheritance: 4 × 4 = 16 class. Thêm 1 backend (Postgres) → +4 class.

Bridge:

```python
class MemoryOperation(ABC):
    def __init__(self, storage: StorageBackend):
        self._storage = storage
    @abstractmethod
    def execute(self, episode): ...

class EncodeOperation(MemoryOperation):
    def execute(self, episode):
        validated = self._validate(episode)           # logic riêng của Encode
        return self._storage.put(episode.id, validated)

class RetrieveOperation(MemoryOperation):
    def execute(self, query):
        results = self._storage.query(query)          # logic riêng của Retrieve
        return self._rank(results)

class StorageBackend(ABC):
    @abstractmethod
    def put(self, key, value): ...
    @abstractmethod
    def query(self, q): ...

class InMemoryDictStorage(StorageBackend): ...
class SQLiteStorage(StorageBackend): ...
class VectorDBStorage(StorageBackend): ...
```

Runtime composition:
```python
fast_encode = EncodeOperation(InMemoryDictStorage())     # cho hot loop
durable_encode = EncodeOperation(SQLiteStorage())         # cho persistence
semantic_retrieve = RetrieveOperation(VectorDBStorage())  # cho similarity search
```

Lợi ích cụ thể:
1. **Test isolation**: test EncodeOperation với MockStorage, test SQLiteStorage với MockOperation.
2. **Hot-swap backend**: develop với InMemory, prod với SQLite, không sửa MemoryOperation logic.
3. **Migration path**: dual-write tạm thời (Encode chạy cả InMemory và Cloud) bằng `CompositeStorage` wrap 2 backend.
4. **Open-Closed**: thêm `PostgresStorage` không sửa MemoryOperation. Thêm `BatchEncodeOperation` không sửa Storage.

---

## TÓM LẠI

Bridge = **tách 2 dimension biến đổi độc lập, kết nối qua composition thay vì inheritance lồng**. Trong não, parvo/magno/konio pathway là Bridge ở mức sinh học — visual information type tách rời khỏi pathway type. Lesion 1 dimension không phá dimension kia (achromatopsia, akinetopsia là minh chứng). Đây là hiệu quả thiết kế tiến hóa đã chọn vì cho phép phá hủy cục bộ + nâng cấp từng phần.

Dấu hiệu cần Bridge:
- Có 2+ dimension thay đổi độc lập, cả hai có khả năng mở rộng.
- Đang dùng inheritance và class count tăng theo tích số (Cartesian).
- Cần switch implementation runtime, không chỉ compile-time.
- Cần test 1 dimension độc lập với dimension kia.

Cặp pattern thường đi cùng:
- **Bridge + Strategy** (lesson 21): Implementor có thể là Strategy (algorithm hoán đổi runtime).
- **Bridge + Abstract Factory** (lesson 03): Factory tạo Implementor phù hợp với Abstraction.
- **Bridge + Adapter** (lesson 06): Implementor có thể là Adapter wrap external API.
- **Bridge + Observer** (lesson 19): Abstraction publish events, Implementor là transport.

### Câu hỏi tự kiểm tra

1. Phân biệt Bridge vs Strategy — khi nào nên chọn cái nào?
2. Trong não, một số neuron ở V1 nhận input từ cả P và M pathway (gọi là "blob" cells). Điều này có vi phạm Bridge không? Bài học gì cho việc một abstraction có thể tham chiếu nhiều implementor?
3. Trong Ellumm, nếu một số `MemoryOperation` (vd: `Consolidate`) cần truy cập **nhiều storage backend cùng lúc** (đọc từ in-memory + ghi vào SQLite + index vào VectorDB), Bridge thuần có đủ không? Nếu không, pattern nào hỗ trợ? (Gợi ý: Composite lesson 08, Coordinator)
