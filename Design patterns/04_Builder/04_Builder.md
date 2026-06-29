# Lesson 04 — Builder

> **Tách quá trình lắp ráp object phức tạp khỏi biểu diễn của nó, để cùng một quy trình có thể tạo nhiều biến thể.**

---

## Mức 1 — CONCEPT (Ý tưởng)

### Vấn đề pattern giải quyết

Bạn cần tạo một object có **nhiều thành phần**, mỗi thành phần **có thể có/không** hoặc **có nhiều biến thể**. Ba cách "ngây thơ" đều thất bại:

**Cách 1 — Constructor monster:**
```python
# ❌ 15 tham số, không nhớ thứ tự, dễ truyền nhầm
synapse = Synapse(
    presynaptic_neuron, postsynaptic_neuron,
    "excitatory", 0.8, 12, 4, True, False, "neuroligin-1",
    True, 0.3, "perisynaptic", 5, "Bassoon-Piccolo", True
)
```

**Cách 2 — Telescoping constructor (nhiều overload):**
```python
# ❌ Bùng nổ tổ hợp: 2^N constructor cho N tham số optional
class Synapse:
    def __init__(self, pre, post): ...
    def __init__(self, pre, post, receptor): ...
    def __init__(self, pre, post, receptor, density): ...
    def __init__(self, pre, post, receptor, density, astrocyte): ...
    # ... 32 overload nữa
```

**Cách 3 — Setters sau new:**
```python
# ❌ Object rơi vào trạng thái không hợp lệ giữa chừng
syn = Synapse(pre, post)            # chưa có receptor → chưa hoạt động
syn.set_receptor("AMPA")            # chưa có PSD → AMPA không neo được
syn.set_psd("PSD-95")               # giờ mới hợp lệ — nhưng nếu ai dùng giữa chừng?
```

Builder giải quyết bằng cách: **build từng bước qua một object trung gian, validate khi gọi `build()`, chỉ khi đó mới có Synapse thật**. Trong khi đang build, không ai có thể dùng object dở dang vì nó chưa tồn tại.

### Neuroscience analogy — Synaptogenesis

Một synapse trưởng thành không "sinh ra" nguyên khối. Nó được lắp ráp qua một **chuỗi bước có thứ tự**, mỗi bước có thể được tùy biến hoặc bỏ qua:

| # | Bước | Thành phần | Có thể tùy biến |
|---|------|-----------|-----------------|
| 1 | Axon contact | Adhesion molecules (neurexin–neuroligin) | Loại neurexin (1α/1β/2/3), loại neuroligin (1/2/3/4) → quyết định excitatory hay inhibitory |
| 2 | Active zone | Bassoon, Piccolo, RIM, Munc13 | Mật độ vesicle docking site |
| 3 | Vesicle pool | Synaptic vesicles | Loại neurotransmitter (Glu/GABA/ACh/...) + số lượng pool |
| 4 | PSD assembly | PSD-95 (excitatory) hoặc Gephyrin (inhibitory) | Kích thước PSD |
| 5 | Receptor cluster | AMPA, NMDA, GABA-A, ... | Tỷ lệ AMPA/NMDA, có hay không kainate |
| 6 | Glia ensheath | Astrocyte process bao quanh | Có (tripartite synapse) hay không (binary synapse) |
| 7 | Maturation/Pruning | Hoàn thiện hoặc loại bỏ | Synapse "silent" giữ chỉ NMDA, "unsilenced" sau khi LTP |

Cùng quy trình synaptogenesis, **kết quả khác nhau** tùy bước nào được chọn:
- Excitatory glutamatergic synapse: neurexin-1β + neuroligin-1 + PSD-95 + AMPA + NMDA
- Inhibitory GABAergic synapse: neurexin + neuroligin-2 + Gephyrin + GABA-A
- Electrical gap junction synapse: connexin-36 hemichannel, không vesicle/receptor
- Silent synapse: như excitatory nhưng không có AMPA → không phát signal đến khi unsilenced

→ Đây là **Builder pattern ở mức phân tử**: một quy trình lắp ráp chung (`SynaptogenesisBuilder`) tạo nhiều "biểu diễn" synapse khác nhau, mỗi cái pass validation chỉ khi tổ hợp thành phần hợp lệ (ví dụ: PSD-95 chỉ đi với AMPA/NMDA, không đi với GABA-A — Gephyrin mới đúng).

### Phân biệt với 3 pattern Creational đã học

| | Singleton | Factory Method | Abstract Factory | Builder |
|---|-----------|----------------|------------------|---------|
| Quan tâm | Số lượng instance | Loại 1 product | Họ N product khớp | Cách lắp ráp 1 product phức tạp |
| Sản phẩm | 1 instance global | 1 object đơn giản | N object cùng họ | 1 object có cấu trúc bên trong |
| Mở rộng | (không liên quan) | Thêm product type | Thêm family | Thêm bước build / biến thể bước |
| Khi dùng | Toàn cục, single source | If-else dài chọn class | Nhiều family song song | Constructor có > 4 param, hoặc nhiều optional |

---

## Mức 2 — ALGORITHM (Thuật toán)

### Cấu tạo (5 chiều theo framework Ellumm)

| Chiều | Nội dung |
|-------|----------|
| **Cấu tạo** | (a) `Product` (immutable, đầy đủ thành phần), (b) `Builder` (giữ state đang build, có method cho mỗi bước, `build()` trả về Product), (c) optional `Director` (đóng gói trình tự build phổ biến) |
| **Vị trí** | Tầng domain hoặc factory layer. Builder thường là internal — client không nhớ cú pháp constructor, gọi builder. |
| **Chức năng** | Đảm bảo Product luôn được tạo ở trạng thái hợp lệ + cho phép tùy biến trình tự/thành phần. |
| **Kết nối** | Client → Builder (hoặc Director → Builder) → Product. Builder thường stateful, Product thường immutable. |
| **Ý nghĩa** | Đóng gói **logic ràng buộc giữa các thành phần** vào một nơi (validation tại `build()`). |

### Hai biến thể cài đặt

**Biến thể A — Fluent Builder (method chaining):**
```python
synapse = (SynapseBuilder()
    .with_axon_contact(neurexin="1β", neuroligin="1")
    .with_active_zone(vesicle_count=12)
    .with_psd(scaffold="PSD-95")
    .with_receptors(ampa=8, nmda=4)
    .with_astrocyte_ensheath()
    .build())
```
Đẹp, đọc như văn xuôi. Phổ biến trong Java/JavaScript. Trong Python ít dùng hơn vì có keyword arguments.

**Biến thể B — Director + step methods:**
```python
director = SynapseDirector(builder=SynapseBuilder())
excitatory_glu_synapse = director.build_excitatory_glutamatergic()
inhibitory_gaba_synapse = director.build_inhibitory_gabaergic()
silent_synapse = director.build_silent()
```
Khi có vài "preset" phổ biến, Director đóng gói recipe.

### Logic vận hành

```
1. Builder() khởi tạo state rỗng (hoặc default)
2. Mỗi method with_X():
   - Cập nhật state nội bộ
   - return self  (cho phép chaining)
3. build():
   - Validate cross-component (vd: PSD-95 yêu cầu glutamate, không GABA)
   - Tạo Product immutable
   - Reset/discard builder state
   - return Product
```

Validation tại `build()` là **giá trị architect cốt lõi** của Builder. Tất cả invariant cross-field nằm ở 1 chỗ.

### Nguyên lý liên quan

- **Single Responsibility**: Builder chịu trách nhiệm "lắp ráp", Product chịu trách nhiệm "hành vi".
- **Immutability after construction**: Product nên immutable — đảm bảo invariant không bị phá sau khi pass validation.
- **Fail-fast**: validate khi build, không để invariant rò rỉ ra runtime.

---

## Mức 3 — PSEUDOCODE + PYTHON

### Pseudocode

```
class Synapse:                          # immutable Product
    field axon_contact, active_zone, psd, receptors, has_astrocyte

class SynapseBuilder:
    state = {}

    function with_axon_contact(neurexin, neuroligin):
        validate (neurexin, neuroligin) là pair hợp lệ
        state["axon_contact"] = (neurexin, neuroligin)
        return self

    function with_active_zone(vesicle_count): ...
    function with_psd(scaffold): ...
    function with_receptors(ampa, nmda, gaba_a): ...
    function with_astrocyte_ensheath(): ...

    function build() -> Synapse:
        # Cross-component validation:
        if state.psd == "PSD-95" and state.receptors.has("GABA-A"):
            raise ValueError("PSD-95 không neo GABA-A. Dùng Gephyrin.")
        if state.psd == "Gephyrin" and state.receptors.has("AMPA"):
            raise ValueError("Gephyrin neo GABA-A, không neo AMPA.")
        if not state.has("axon_contact"):
            raise ValueError("Synapse cần axon contact.")
        # Pass — tạo Product immutable
        return Synapse(**state)
```

### Python (xem file `04_builder.py`)

File code triển khai:
1. **Anti-pattern constructor monster** — minh họa vì sao 15 tham số là sai.
2. **Fluent SynapseBuilder** với cross-component validation.
3. **SynapseDirector** đóng gói 4 preset: excitatory glutamatergic, inhibitory GABAergic, silent (chỉ NMDA), gap junction.
4. **Demo failure**: cố build synapse với PSD-95 + GABA-A → bị `SynapseInvalid` chặn ngay tại `.build()`.
5. **Ellumm application**: `MemoryEpisodeBuilder` lắp ráp episodic memory với visual + auditory + emotion + spatial-temporal context, mỗi thành phần có thể có/không tùy nguồn dữ liệu.

---

## 3 LOẠI VÍ DỤ

### Ví dụ 1 — Vận hành thường

Trong cortex visual, một pyramidal neuron L2/3 đang form synapse mới với neuron L4 đến. Bước 1: axon L4 contact dendrite L2/3 → neurexin-1β trên axon gặp neuroligin-1 trên dendrite → adhesion thiết lập. Bước 2: trong vài giờ, các vesicle chứa Bassoon/Piccolo được vận chuyển đến điểm contact, lắp active zone với 8-12 docking site. Bước 3: vesicle chứa glutamate dock và prime. Bước 4: bên dendrite, PSD-95 cluster tại đối diện active zone (qua trans-synaptic neurexin-neuroligin signaling). Bước 5: AMPA receptor (4 GluA1+GluA2) và NMDA receptor (2 GluN1+2 GluN2A) được neo vào PSD-95. Bước 6: astrocyte process cortical đến bao quanh — tripartite synapse hoàn chỉnh. Bước 7: trong vài tuần, nếu có hoạt động đồng thời pre-post (Hebbian), synapse được củng cố; nếu không, bị tỉa.

Đây là Builder hoạt động ở mức phân tử — mỗi bước build trên nền bước trước, sản phẩm cuối là synapse glutamatergic hoàn chỉnh có thể truyền tín hiệu.

### Ví dụ 2 — Hỏng / Thiếu

**Trường hợp sinh học**: Hội chứng Phelan-McDermid (đột biến SHANK3) — SHANK3 là scaffold protein ở PSD, kết nối PSD-95 với receptor và actin cytoskeleton. Khi SHANK3 thiếu/hỏng, "bước build PSD" không hoàn thành đúng → AMPA/NMDA không được neo chắc → synapse hình thành nhưng plasticity kém → biểu hiện autism spectrum disorder + intellectual disability. Đây chính là kịch bản "build object thiếu một thành phần thiết yếu mà validation không bắt được" — điểm yếu khi Builder không có cross-component check đầy đủ.

**Trường hợp code**: API REST có hàm `create_user(name, email, age, address, phone, role, perms, ...)` 12 tham số. Caller hay quên truyền `role` → user mặc định role=None → một module khác sau đó crash khi check permission. Lỗi xuất hiện sâu trong runtime, log không nói nguyên nhân là `create_user` thiếu role. Nếu dùng Builder + validation, lỗi xuất hiện ngay tại `.build()` với message "User cần role". Đây là **fail-fast giá trị thực** của Builder.

### Ví dụ 3 — Ứng dụng Ellumm

Trong Ellumm, một `MemoryEpisode` (ký ức hồi tưởng) có thể có nhiều thành phần, không phải lúc nào cũng đầy đủ:

| Thành phần | Khi nào có | Khi nào không |
|-----------|-----------|---------------|
| Visual snapshot | Đang mở mắt, có pixel-tracing input | Ngủ, mơ trừu tượng, suy nghĩ thuần lý |
| Auditory snippet | Có âm thanh đáng chú ý | Môi trường yên |
| Emotion vector | LUÔN CÓ (interoception luôn chạy) | (không có exception) |
| Spatial-temporal context | Có grid cell + place cell signal | Decoupled từ không gian (vd: dreaming) |
| Salience score | LUÔN CÓ (amygdala salience map) | (không có exception) |
| Consolidation flags | Set sau khi sleep replay | Trước replay là None |

Builder lắp ráp linh hoạt:

```python
episode = (MemoryEpisodeBuilder()
    .with_emotion(GlobalEmotionState().snapshot())   # bắt buộc
    .with_salience(amygdala.current_salience())       # bắt buộc
    .with_visual(visual_cortex.last_snapshot())       # optional
    .with_spatial_temporal(hippocampus.place_cells()) # optional
    .build())
```

`build()` validate: nếu thiếu emotion hoặc salience → raise `EpisodeInvalid`; nếu có spatial nhưng không có place cell signature đúng → reject. Đảm bảo không có episode "rác" lọt vào memory store.

Khi sau này Ellumm thêm modality `olfactory_trace` hoặc `body_state_diff`, thêm `with_X()` method vào Builder — không sửa Episode đã chạy ổn định.

---

## TÓM LẠI

Builder = **lắp ráp object phức tạp qua nhiều bước, validate cross-component khi `.build()`, sản phẩm immutable**. Trong não, synaptogenesis là Builder phân tử — cùng quy trình tạo nhiều loại synapse tùy bước nào được chọn. Bệnh thần kinh phát triển (autism, intellectual disability) thường là Builder hỏng — bước thiếu hoặc tổ hợp không hợp lệ.

Dấu hiệu cần Builder trong code:
- Constructor có > 4 tham số, đặc biệt khi nhiều cái optional
- Phải dùng setters sau new để hoàn thiện object
- Có nhiều invariant cross-field cần validate
- Cùng quy trình build cần tạo nhiều biến thể (tham số khác nhau, cấu trúc tương tự)

Cặp pattern thường đi cùng:
- **Builder + Director**: khi có vài preset phổ biến cần đóng gói.
- **Abstract Factory + Builder**: factory chọn family, builder lắp ráp object trong family đó.
- **Builder + Composite** (lesson 08): build cây cấu trúc phân cấp.
- **Fluent Builder + DSL**: cú pháp đẹp như văn xuôi (vd: SQL query builder, GraphQL schema builder).

### Câu hỏi tự kiểm tra

1. Khi nào nên dùng Builder thay vì **kwargs + dataclass + `__post_init__` validation**? (Gợi ý: Python có cách Pythonic, không phải lúc nào cũng cần Builder).
2. Trong Ellumm, nếu bạn cần tạo `MemoryEpisode` thường xuyên với cùng preset (vd: "default visual episode"), bạn refactor thế nào? (Gợi ý: Director hoặc Prototype lesson 05).
3. Synapse có thể "matur hóa" sau khi đã build (vd: silent synapse được unsilenced). Điều này có vi phạm immutability của Product không? Bạn xử lý sao trong code? (Gợi ý: Memento lesson 18 hoặc functional update).
