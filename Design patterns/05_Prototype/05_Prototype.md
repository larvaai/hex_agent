# Lesson 05 — Prototype

> **Tạo object mới bằng cách clone một instance mẫu, không phải instantiate từ class.**

---

## Mức 1 — CONCEPT (Ý tưởng)

### Vấn đề pattern giải quyết

Đôi khi việc "tạo object mới từ đầu" là **đắt** hoặc **khó tả**:

- Object cần load từ database/network/file (đắt thời gian).
- Object cần qua chuỗi setup phức tạp (đã build qua Builder, không muốn build lại).
- Object có cấu hình runtime mà bạn không muốn hardcode vào class definition.
- Bạn cần nhiều object **gần giống nhau**, chỉ khác vài tham số nhỏ.

Ba pattern Creational đã học (Factory Method, Abstract Factory, Builder) đều **bắt đầu từ class definition**: bạn phải biết chính xác class nào, gọi constructor nào, truyền tham số nào. Prototype lật ngược câu hỏi: **đã có 1 instance đúng — sao không clone nó?**

```python
# Cách Factory Method:
neuron = factory.create_neuron()        # construct từ đầu, mất 5 bước

# Cách Prototype:
neuron = neuron_template.clone()        # copy 1 cú, sửa vài attribute
neuron.position = new_position
```

### Neuroscience analogy — Mirror Neuron + Motor Templates

Khi bạn với tay lấy cốc cà phê, não **không** "lập trình từ đầu" chuỗi co cơ. Nó **clone một motor template đã có sẵn** — chương trình "reach-and-grasp" đã được học từ thuở bé, lưu phân tán trong premotor cortex (PMC), supplementary motor area (SMA), cerebellum, và basal ganglia.

Mirror neurons (vùng F5 ở khỉ; ở người là inferior frontal gyrus + inferior parietal lobule) là chứng cứ trực tiếp của cơ chế này. Mirror neuron cháy trong **hai trường hợp**:
1. Bạn tự thực hiện hành động (cầm cốc).
2. Bạn quan sát người khác làm cùng hành động.

Tại sao? Vì khi quan sát người khác cầm cốc, hệ vận động của bạn **clone template "reach-and-grasp"** vào một sandbox nội bộ — "preview" hành động mà không thực sự co cơ. Đó cũng là cơ chế nền của imitation learning ("nhìn rồi bắt chước").

Khi bạn thực sự muốn cầm cốc, template được clone lần nữa và **tùy biến tham số**:
- target_position = (x, y, z) của cốc
- grip_type = power grip (cốc lớn) hoặc precision grip (bút)
- approach_speed, hand_orientation, ...

Lợi ích của clone-by-template trong não:
- **Học một lần, dùng nhiều lần**: không phải re-learn coordination cho mỗi cốc khác nhau.
- **Tốc độ**: clone + tweak nhanh hơn nhiều so với rebuild từ raw motor primitives.
- **Tính nhất quán**: cùng template → motion smoothness và muscle coordination tương tự nhau giữa các lần thực hiện.
- **Imitation**: có thể "nhập" template hành động từ người khác (xem rồi tập theo).

→ Mirror neuron + motor template = **Prototype pattern ở mức hệ thần kinh**.

### Phân biệt với 4 pattern Creational đã học

| | Bắt đầu từ | Khi dùng |
|---|-----------|----------|
| Singleton | Class | Cần đúng 1 instance toàn cục |
| Factory Method | Class hierarchy | Chọn 1 product type, subclass quyết định |
| Abstract Factory | Class hierarchy | Chọn 1 family product khớp nhau |
| Builder | Field-by-field assembly | Object phức tạp, nhiều invariant cross-field |
| **Prototype** | **Existing instance** | **Clone + tweak, tránh re-construct đắt** |

Điểm khác biệt sâu nhất: 4 pattern đầu giữ logic tạo object trong **class**. Prototype chuyển logic này sang **instance** — bạn có thể có 100 prototype khác nhau cùng class, mỗi cái config khác, tất cả đều clone được. Đây là một dạng **runtime extensibility** mà inheritance không có.

---

## Mức 2 — ALGORITHM (Thuật toán)

### Cấu tạo (5 chiều theo framework Ellumm)

| Chiều | Nội dung |
|-------|----------|
| **Cấu tạo** | (a) `Prototype` interface với method `clone()`, (b) Concrete prototypes lưu sẵn cấu hình, (c) optional `PrototypeRegistry` ánh xạ tên → prototype |
| **Vị trí** | Tầng domain hoặc cache layer. Thường có 1 registry global hoặc per-context. |
| **Chức năng** | Tạo object mới qua copy thay vì construct, hỗ trợ tùy biến nhỏ sau clone. |
| **Kết nối** | Client → Registry → Prototype.clone() → object mới (độc lập với prototype) |
| **Ý nghĩa** | Object configuration trở thành **first-class citizen runtime** — có thể thêm/sửa prototype không cần đụng class definition. |

### Vấn đề CỐT LÕI: Deep copy vs Shallow copy

Đây là cái bẫy lớn nhất của Prototype. Nếu prototype có nested mutable object:

```python
template = MotorTemplate(
    name="reach_and_grasp",
    muscle_groups=["biceps", "deltoid", "wrist_flexors"],   # list
    coordination_matrix={...},                                # dict
)
clone1 = template.shallow_copy()
clone1.muscle_groups.append("triceps")     # ⚠️ SHALLOW: cũng append vào template!
```

**Shallow copy** chỉ copy reference của nested object — clone và prototype **share** nested state. Modify clone = modify prototype = lan ra mọi clone khác. Bug ngầm cực kỳ khó truy.

**Deep copy** đệ quy copy mọi nested → clone hoàn toàn độc lập, nhưng tốn hơn (đặc biệt với object lớn).

Quyết định architect: nested nào cần deep, nested nào share được.
- **Cần deep**: state mutable mà clone sẽ tweak (muscle parameters, position, target).
- **Có thể share**: immutable data hoặc reference toàn cục (config, constants, lookup table).

Trong Python: `copy.copy()` = shallow, `copy.deepcopy()` = deep. Override `__copy__()` và `__deepcopy__()` để kiểm soát chi tiết.

### Logic vận hành

```
Setup:
    registry = PrototypeRegistry()
    registry.register("reach_and_grasp", MotorTemplate(...))
    registry.register("avoid_threat", MotorTemplate(...))
    registry.register("precision_grip", MotorTemplate(...))

Runtime:
    template = registry.get("reach_and_grasp")    # lấy prototype
    plan = template.clone()                        # ← clone (deep)
    plan.target_position = (0.4, 0.2, 0.1)         # tùy biến tham số
    plan.execute()
```

Prototype (`registry["reach_and_grasp"]`) **không** bị modify. Mỗi lần cần thực hiện hành động cụ thể, ta có 1 instance mới riêng để tweak.

### Nguyên lý liên quan

- **Avoid premature class hierarchy**: nếu sự khác biệt giữa các "loại" chỉ là config, không cần subclass — dùng prototype với config khác nhau.
- **Runtime composition over compile-time inheritance**: prototype cho phép thêm "loại mới" mà không sửa code (chỉ cần register prototype mới).
- **Encapsulate object identity**: prototype có thể chứa state phức tạp đã build — clone bảo toàn state đó.

---

## Mức 3 — PSEUDOCODE + PYTHON

### Pseudocode

```
abstract class Prototype:
    abstract function clone(): Prototype

class MotorTemplate extends Prototype:
    field name, muscle_groups, coordination_matrix, target_position

    function clone() -> MotorTemplate:
        return MotorTemplate(
            name = self.name,
            muscle_groups = deep_copy(self.muscle_groups),
            coordination_matrix = deep_copy(self.coordination_matrix),
            target_position = self.target_position,
        )

class PrototypeRegistry:
    field _registry: dict[str, Prototype]

    function register(name, prototype): _registry[name] = prototype
    function get(name) -> Prototype: return _registry[name].clone()
```

### Python (xem file `05_prototype.py`)

File code triển khai:
1. **Anti-pattern**: rebuild motor program from scratch mỗi lần → đắt + dễ sai.
2. **MotorTemplate** với `__deepcopy__()` override để kiểm soát chính xác cái gì deep, cái gì share.
3. **PrototypeRegistry** với 4 motor template đã học sẵn.
4. **Demo shallow vs deep copy bug** — hiển thị tận mắt sự khác biệt.
5. **Demo "apraxia"** — registry mất template, runtime fallback.
6. **Ellumm version**: `BehavioralTemplateLibrary` cho approach/avoid/explore/freeze patterns, mỗi cái clone + tùy biến tham số khi gặp stimulus mới.

---

## 3 LOẠI VÍ DỤ

### Ví dụ 1 — Vận hành thường

Bạn ngồi trước bàn làm việc, thấy cốc cà phê. Quy trình thực tế trong não:
1. Visual cortex nhận diện "cốc" + parietal lobe tính ra (x, y, z) tương đối với tay.
2. Premotor cortex tra "motor template library" → tìm template `reach_and_grasp_power_grip` (vì cốc cỡ vừa).
3. Template được **clone** vào một buffer execution (gọi là "motor plan" tạm thời).
4. Tham số tùy biến được fill: `target_position = (x, y, z)`, `grip_force` ước tính từ trọng lượng dự đoán, `approach_angle` tránh chướng ngại trên bàn.
5. Plan này được gửi xuống M1 (primary motor cortex) → spinal cord → muscles. Cerebellum giám sát smoothness.
6. **Template gốc trong library KHÔNG bị thay đổi** — chỉ plan instance bị thay đổi (rồi vứt sau khi thực hiện xong).

Đây chính là Prototype: prototype (template) bất biến, mỗi instance hành động là một clone tạm + tweak.

### Ví dụ 2 — Hỏng / Thiếu

**Trường hợp sinh học**: **Ideomotor apraxia** — tổn thương vùng inferior parietal lobule (IPL) hoặc supplementary motor area (SMA). Bệnh nhân:
- Hiểu yêu cầu ("hãy chải tóc")
- Có muscle strength bình thường
- Nhưng KHÔNG thể clone template "chải tóc" vào motor plan → động tác sai trình tự, hoặc dùng đối tượng sai (cầm bàn chải như muỗng).

Đây chính xác là "Prototype Registry hỏng" — template vẫn tồn tại đâu đó (vì bệnh nhân có thể nhận biết khi người khác làm), nhưng route từ "intention" đến "clone template vào execution" bị đứt. Ở mức code, tương đương với `registry.get(name)` raise `KeyError` hoặc trả về wrong template.

**Trường hợp code — Shallow copy bug kinh điển**:

```python
template = MotorTemplate(muscle_groups=["biceps", "deltoid"])
plan_A = copy.copy(template)        # shallow!
plan_B = copy.copy(template)
plan_A.muscle_groups.append("triceps")
print(plan_B.muscle_groups)         # ['biceps', 'deltoid', 'triceps']
print(template.muscle_groups)       # ['biceps', 'deltoid', 'triceps'] — cả prototype!
```

Bạn nghĩ mỗi clone là độc lập, nhưng vì `muscle_groups` là list (mutable), mọi clone share cùng 1 list. Modify 1 clone = phá template + mọi clone khác. Loại bug này thường nằm im 6 tháng rồi nổ ở case edge (có concurrent execution).

### Ví dụ 3 — Ứng dụng Ellumm

Ellumm có một thư viện "behavioral templates" đã được học/khởi tạo:

| Template | Mô tả | Trigger điển hình |
|----------|-------|-------------------|
| `approach_food` | Tiếp cận nguồn dinh dưỡng | Visual food + đói |
| `avoid_threat` | Né tránh nguy hiểm | Salience cao + valence âm |
| `explore_novel` | Khám phá môi trường mới | Novelty + arousal trung bình |
| `freeze_predator` | Bất động khi gặp săn mồi | Salience cực cao + escape impossible |
| `social_approach` | Tiếp cận đồng loại | Conspecific cue + valence dương |

Mỗi template là một `BehavioralProgram` đã build sẵn: emotion response curve + motor activation pattern + learning rate adjustment + memory encoding policy. Khi gặp stimulus mới, Ellumm:

```python
template = behavior_library.get("avoid_threat")
plan = template.clone()                              # deep copy
plan.threat_position = stimulus.location             # tùy biến
plan.urgency = amygdala.salience_score
plan.escape_route = spatial_map.compute_escape()
plan.execute()
```

Lợi ích cụ thể:
1. **Speed**: gặp rắn không phải re-derive "rắn = nguy hiểm = né"; clone + tweak < 10ms.
2. **Library extensibility**: thêm template mới (`mating_display`, `play_with_juvenile`) chỉ cần register vào library — không sửa core engine.
3. **Hot-reload**: trong Ellumm dev mode, có thể tweak template tham số runtime mà không restart engine.
4. **Personalization theo agent**: mỗi Ellumm agent có template library riêng được tinh chỉnh theo trải nghiệm — clone từ shared base, tweak per-agent.

---

## TÓM LẠI

Prototype = **clone-instead-of-construct**, dùng instance đã cấu hình làm nguồn cho instance mới. Trong não, mirror neuron + motor template là Prototype tự nhiên — học motor program một lần, clone + tweak nhiều lần. Apraxia là minh chứng sinh học cho việc "Prototype Registry hỏng".

Cái bẫy lớn nhất là **deep vs shallow copy**. Architect phải quyết định cho mỗi nested field: cần deep (mutable per-clone) hay share được (immutable global). Sai trong khoản này → bug ngầm cascade qua mọi clone.

Cặp pattern thường đi cùng:
- **Prototype + Registry**: lookup by name + clone (cực phổ biến).
- **Prototype + Memento** (lesson 18): prototype lưu state dưới dạng snapshot, clone = restore snapshot.
- **Prototype + Composite** (lesson 08): clone cây cấu trúc phân cấp.

### Tổng kết nhóm Creational (Lesson 01-05)

| Pattern | Câu hỏi nó trả lời | Trục mở rộng |
|---------|---------------------|--------------|
| Singleton | Số lượng instance? | Không |
| Factory Method | Class concrete nào? | Thêm product type qua subclass |
| Abstract Factory | Family nào? | Thêm family qua concrete factory |
| Builder | Lắp ráp phức tạp? | Thêm bước hoặc preset |
| Prototype | Clone từ instance có sẵn? | Thêm prototype runtime |

5 pattern Creational là **5 cách trả lời câu hỏi "tạo object thế nào"**. Architect không học để dùng "đúng cái nào" — học để **nhận ra** khi nào câu hỏi bắt đầu phức tạp hơn `new ClassX()`. Khi đó, một trong 5 cái này sẽ phù hợp.

### Câu hỏi tự kiểm tra

1. Tại sao Prototype "phá vỡ" inheritance hierarchy? Trong tình huống nào điều đó tốt, tình huống nào xấu?
2. Trong Ellumm, khi clone một `BehavioralProgram`, `emotion_response_curve` (numpy array đã train) có nên deep copy không? Trade-off là gì? (Gợi ý: read-only vs runtime-tweaked)
3. Cặp Mirror Neuron + Motor Template hỗ trợ imitation learning ở người. Trong code, có equivalent nào? Ví dụ: testing framework có thể clone state setup từ một test pattern khác (Gợi ý: test fixture).

---

## Sắp tới

Hết nhóm **Creational**. Tiếp theo là 7 pattern **Structural** — cách *ghép* các object đã tạo vào kiến trúc lớn hơn:

| # | Pattern | Neuroscience Analogy |
|---|---------|----------------------|
| 06 | Adapter | Thalamus chuyển định dạng signal sensorial → cortex |
| 07 | Bridge | Tách signal type khỏi pathway (parvocellular/magnocellular) |
| 08 | Composite | Cortical column — neuron đơn và cụm cùng giao diện |
| 09 | Decorator | Myelin sheath — bọc thêm chức năng (tăng tốc) |
| 10 | Facade | Brainstem — 1 cổng đơn giản che hệ tự động |
| 11 | Flyweight | Receptor type dùng chung ở hàng tỉ synapse |
| 12 | Proxy | Blood-Brain Barrier — kiểm soát truy cập |
