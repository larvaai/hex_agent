# Lesson 06 — Adapter

> **Chuyển interface của một class sang interface mà client kỳ vọng, để hai bên không tương thích vẫn hợp tác được.**

---

## Mức 1 — CONCEPT (Ý tưởng)

### Vấn đề pattern giải quyết

Bạn có hai phía:
- **Client** (Cortex) chỉ biết một loại signal: spike train chuẩn 6-layer thalamocortical, có timestamp, modality, confidence.
- **Adaptee** (Retina, Cochlea, Skin) phát signal thô khác hẳn nhau: retinal ganglion cell phát theo grid không gian + on/off center; cochlear nerve phát theo tonotopic frequency; skin afferent phát theo touch/pressure/temperature riêng.

Bạn không thể bắt cortex hiểu mọi format thô — quá nhiều biến thể, mỗi cái cần logic riêng. Bạn cũng không thể sửa retina/cochlea cho "giống" cortex — chúng đã được tối ưu cho công việc của mình.

Adapter là **lớp thứ ba ở giữa**: bao bọc Adaptee, expose ra interface mà Client mong đợi. Client không biết Adapter có gì bên trong — chỉ thấy interface chuẩn.

```python
# ❌ Không có Adapter: cortex phải biết mọi format
if signal_source == "retina":
    spikes = retina.get_ganglion_burst()
    spikes = convert_to_thalamocortical(spikes, ...)
elif signal_source == "cochlea":
    waveform = cochlea.get_basilar_response()
    spikes = convert_audio_to_spikes(waveform, ...)
# ... if-else dài + cortex coupling trực tiếp với mọi adaptee

# ✓ Có Adapter: cortex chỉ thấy interface chuẩn
for adapter in [lgn_adapter, mgn_adapter, vpl_adapter]:
    cortex.process(adapter.get_thalamocortical_spikes())
```

### Neuroscience analogy — Thalamus là "great relay station"

Thalamus là một cấu trúc nhỏ ở giữa não bộ, gồm khoảng 50-60 nucleus, được mệnh danh là **"the great relay station"**. Mọi modality giác quan (trừ olfaction là exception) phải đi qua thalamus trước khi đến cortex. Mỗi nucleus thalamic là một Concrete Adapter cho một loại input:

| Nucleus thalamic | Adaptee (input thô) | Format đầu vào | Output (chuẩn cortex) | Đích cortex |
|------------------|---------------------|----------------|----------------------|-------------|
| **LGN** (lateral geniculate) | Retinal ganglion cell | Grid spatial + on/off center, magnocellular vs parvocellular | Layer-specific spike train | V1 (primary visual cortex) |
| **MGN** (medial geniculate) | Cochlear nerve | Tonotopic frequency, temporal pattern | Layer-specific spike train | A1 (primary auditory cortex) |
| **VPL** (ventral posterior lateral) | Spinothalamic + DCML | Touch/pressure/proprioception body-side | Layer-specific spike train | S1 (primary somatosensory) |
| **VPM** (ventral posterior medial) | Trigeminal | Touch/pressure mặt | Layer-specific spike train | S1 face area |
| **Pulvinar** | Multiple cortical areas | Cross-modal already-cortical signals | Cortical-to-cortical relay | Higher-order cortex |
| **MD** (mediodorsal) | Limbic + olfactory | Emotion-tagged signals | Modulated cortical input | Prefrontal cortex |

Quan sát quan trọng: dù **input thô khác nhau hoàn toàn** (electromagnetic ánh sáng vs mechanical vibration không khí vs deformation skin), **output thalamic đều theo cùng một "protocol"**: thalamocortical projection 6-layer format, mà cortex của vùng đích đã tiến hóa để đọc.

→ Thalamus = Adapter pattern ở quy mô hệ thống. Cortex không cần biết retina hay cochlea hoạt động thế nào — nó chỉ thấy "thalamic input chuẩn" và xử lý.

### Object Adapter vs Class Adapter

GoF mô tả 2 biến thể:

**Object Adapter (composition)** — phổ biến hơn:
```python
class LGNAdapter(ThalamocorticalSignal):
    def __init__(self, retina: Retina):
        self._retina = retina         # has-a
    def get_spikes(self):
        raw = self._retina.fire_ganglion_cells()
        return self._convert_format(raw)
```
Linh hoạt: adapter chỉ tham chiếu adaptee qua interface, có thể đổi adaptee runtime, có thể adapt nhiều adaptee.

**Class Adapter (multiple inheritance)** — ít dùng:
```python
class LGNAdapter(ThalamocorticalSignal, Retina):  # is-a + is-a
    def get_spikes(self):
        raw = self.fire_ganglion_cells()  # gọi thẳng method kế thừa
        return self._convert_format(raw)
```
Có thể override hành vi adaptee, nhưng cứng nhắc (compile-time binding) và Python multiple inheritance dễ gây MRO complexity.

Trong Python hiện đại, **Object Adapter là default**. Class Adapter chỉ dùng khi cần override một số method của Adaptee.

---

## Mức 2 — ALGORITHM (Thuật toán)

### Cấu tạo (5 chiều theo framework Ellumm)

| Chiều | Nội dung |
|-------|----------|
| **Cấu tạo** | (a) `Target` interface (cái client kỳ vọng), (b) `Adaptee` (cái có sẵn, interface khác), (c) `Adapter` cài đặt Target + tham chiếu Adaptee |
| **Vị trí** | Tầng integration / boundary layer. Adapter sống ở "biên" giữa hai hệ thống. |
| **Chức năng** | Translation interface, không thay đổi logic của Adaptee. |
| **Kết nối** | Client ↔ Target ← Adapter → Adaptee. Client không biết Adaptee tồn tại. |
| **Ý nghĩa** | Cô lập legacy/third-party API khỏi domain code, biên rõ ràng giữa hai thế giới. |

### Logic vận hành

```
Setup:
    retina = Retina()                                  ← Adaptee
    lgn = LGNAdapter(retina)                           ← Adapter (Object adapter)
    cochlea = Cochlea()
    mgn = MGNAdapter(cochlea)
    cortex.subscribe([lgn, mgn])                       ← Client thấy Target interface

Runtime:
    lgn.get_thalamocortical_spikes():
        raw = self._retina.fire_ganglion_cells()       ← gọi Adaptee
        return self._translate(raw)                    ← format conversion

    cortex.process(spikes)                             ← Client xử lý theo interface chuẩn
```

Key insight: **Adapter không thêm logic nghiệp vụ**, chỉ làm translation. Nếu Adapter đang làm tính toán phức tạp, có thể đó là Facade (lesson 10) hoặc Decorator (lesson 09), không phải Adapter.

### Nguyên lý liên quan

- **Single Responsibility**: Adapter chỉ chịu trách nhiệm "translate", không xử lý logic.
- **Open-Closed**: thêm modality mới (taste, vestibular) = thêm Adapter mới, không sửa cortex.
- **Interface Segregation**: Target interface nên đủ nhỏ để mọi Adapter implement được.
- **Anti-Corruption Layer** (DDD): Adapter là pattern điển hình bảo vệ domain core khỏi external API.

### Phân biệt với pattern khác

| | Adapter | Decorator | Facade | Bridge |
|---|---------|-----------|--------|--------|
| Mục đích | Đổi interface | Thêm hành vi | Đơn giản hóa interface phức tạp | Tách abstraction khỏi implementation |
| Số interface | 2 khác (Adaptee → Target) | 1 (giữ nguyên) | 1 mới đơn giản hơn | 2 song song |
| Khi dùng | Tích hợp bên ngoài | Mở rộng tính năng | Che hệ con phức tạp | Cho phép biến thể độc lập |

Lesson 07 (Bridge) sẽ làm rõ thêm — Bridge tách "loại signal" khỏi "kênh dẫn", giải quyết vấn đề khác Adapter.

---

## Mức 3 — PSEUDOCODE + PYTHON

### Pseudocode

```
interface ThalamocorticalSignal:
    function get_spikes() -> list[Spike]
    function modality() -> str
    function timestamp_ms() -> int

class Retina:                                          # Adaptee
    function fire_ganglion_cells() -> RetinalBurst   # interface khác

class LGNAdapter implements ThalamocorticalSignal:     # Adapter
    field _retina: Retina

    function get_spikes() -> list[Spike]:
        raw = self._retina.fire_ganglion_cells()
        return convert_retinal_to_thalamocortical(raw)

    function modality() -> str: return "visual"
    function timestamp_ms() -> int: return now_ms()

class Cortex:                                          # Client
    function process(signal: ThalamocorticalSignal):
        # Chỉ thấy Target interface, không biết Adaptee
        for spike in signal.get_spikes(): ...
```

### Python (xem file `06_adapter.py`)

File code triển khai:
1. **3 Adaptee** với interface raw, không tương thích nhau: `Retina`, `Cochlea`, `Skin`.
2. **Target interface** `ThalamocorticalSignal` (Protocol).
3. **3 Concrete Object Adapter**: `LGNAdapter`, `MGNAdapter`, `VPLAdapter`.
4. **Cortex client** chỉ phụ thuộc Target — không biết Adaptee.
5. **Demo failure**: `thalamic_stroke()` xóa adapter → cortex mất modality đó (mô phỏng cortical blindness/deafness do LGN/MGN bị tổn thương).
6. **Two-way Adapter**: cortico-thalamo-cortical loop — tín hiệu phản hồi từ cortex về thalamus.
7. **Ellumm version**: `SensoryInputAdapter` adapt camera/microphone/file/network event sang interface `SensoryInput` chuẩn.

---

## 3 LOẠI VÍ DỤ

### Ví dụ 1 — Vận hành thường

Bạn nhìn một quả táo đỏ. Quy trình:
1. Photoreceptor (rod/cone) trong retina chuyển ánh sáng → tín hiệu hóa học.
2. Bipolar cell và horizontal cell xử lý sơ bộ → contrast, color opponency.
3. Retinal ganglion cell (RGC) phát spike train với on-center/off-center pattern, M-cell (magnocellular, motion) vs P-cell (parvocellular, color) khác nhau hoàn toàn.
4. **LGN (Adapter visual)** nhận RGC spike, sắp xếp thành 6 layer (4 parvo + 2 magno), thêm timestamp tổ chức theo cortex protocol, modulate gain bằng feedback từ cortex.
5. LGN gửi output qua optic radiation đến V1 layer 4.
6. V1 nhận signal **đúng format thalamocortical chuẩn** — V1 không cần biết retina có rod/cone hay RGC có M/P type.

Cùng lúc, MGN làm chính xác việc tương tự cho auditory (cochlear → A1), VPL cho somatosensory. Mọi cortical primary area chỉ nhận "thalamic input chuẩn", logic xử lý cortex không cần phân biệt input gốc thuộc modality nào ở mức format. Cortex tập trung vào "đọc spike train" thay vì "xử lý đa định dạng".

### Ví dụ 2 — Hỏng / Thiếu

**Trường hợp sinh học**: **Thalamic stroke** ở vùng LGN → toàn bộ visual signal từ retina không adapt được sang cortex format → bệnh nhân mù (cortical blindness) dù retina còn nguyên, V1 còn nguyên. Đây chính xác là "Adapter lớp giữa hỏng" — hai đầu hoạt động bình thường nhưng không nói chuyện được vì lớp dịch không còn.

Ngược lại, **Anton-Babinski syndrome** (mù do tổn thương V1 hai bên nhưng bệnh nhân phủ nhận mình mù): adapter LGN vẫn chạy, nhưng client (V1) hỏng — bài học: Adapter không cứu được khi client/adaptee thực sự hỏng, nó chỉ giải quyết vấn đề interface.

**Trường hợp code — Unit conversion bug**:
NASA's Mars Climate Orbiter (1999) bị mất do một module gửi thrust force theo pound-seconds, module nhận xử lý theo newton-seconds — không có Adapter làm conversion. Tàu thám hiểm bốc cháy trong khí quyển sao Hỏa. Đây là một trong những bug Adapter đắt giá nhất lịch sử kỹ thuật.

Trong code thường ngày: tích hợp Stripe API (cents) với ledger nội bộ (dollars) mà không Adapter → mọi transaction off bằng 100 lần. Hoặc datetime `naive` vs `aware` của Python — không adapter giữa code legacy và code mới → bug timezone lan toàn hệ.

### Ví dụ 3 — Ứng dụng Ellumm

Ellumm core engine xử lý events qua interface chuẩn `SensoryInput`:
```python
@dataclass
class SensoryInput:
    modality: str          # 'visual', 'auditory', 'tactile', 'system_event'
    timestamp_ns: int
    payload: bytes
    metadata: dict
    confidence: float
```

Nhưng input đến từ nhiều nguồn khác nhau, mỗi nguồn có API riêng:

| Source | Adaptee API | Adapter |
|--------|-------------|---------|
| OpenCV camera | `cv2.VideoCapture.read() → (bool, ndarray)` | `CameraAdapter` |
| PortAudio mic | `stream.read(n_frames) → bytes` | `MicAdapter` |
| File system watcher | `inotify event → (path, event_type)` | `FileEventAdapter` |
| HTTP webhook | `flask request → JSON dict` | `WebhookAdapter` |
| Hardware sensor (IoT) | `sensor.read() → struct` | `IoTSensorAdapter` |

Mỗi adapter wrap raw API, normalize timestamp về `time.time_ns()`, encode payload thành bytes với metadata mô tả nội dung, trả về `SensoryInput`. Core engine chỉ thấy interface chuẩn — không bị coupling với OpenCV, PortAudio, Flask, hay vendor IoT cụ thể.

Lợi ích cụ thể:
1. **Replaceability**: đổi từ OpenCV sang FFmpeg cho camera = chỉ thay `CameraAdapter` impl, không sửa core.
2. **Testability**: viết `MockSensoryAdapter` để feed test data, không cần camera/mic thật.
3. **Composability**: có thể chain adapter (`CompressionAdapter(EncryptionAdapter(CameraAdapter(...)))`).
4. **Anti-Corruption**: nếu vendor API thay đổi (Stripe v2 → v3), chỉ adapter sửa, domain logic giữ nguyên.

---

## TÓM LẠI

Adapter = **dịch interface, không đổi logic**. Đặt giữa client và adaptee để cả hai không cần biết về nhau. Trong não, thalamus là adapter ở quy mô hệ thống — mọi modality (trừ olfaction) đi qua một thalamic nucleus phù hợp để format-convert sang chuẩn cortex. Tổn thương thalamic nucleus = cortex mất khả năng nhận modality đó dù periphery và cortex còn nguyên.

Dấu hiệu cần Adapter:
- Tích hợp third-party library hoặc legacy code có API khác.
- Cùng concept trong domain code có nhiều biểu diễn (units, formats, timezones).
- Cần "anti-corruption layer" giữa domain và external bounded context.
- Code đang có if-else dài check format/source và xử lý khác nhau.

Cặp kết hợp phổ biến:
- **Adapter + Strategy** (lesson 21): nhiều adapter cho nhiều backend, runtime chọn cái nào.
- **Adapter + Factory Method** (lesson 02): factory tạo adapter phù hợp dựa vào source type.
- **Adapter + Bridge** (lesson 07): bridge tách dimension, adapter chuẩn hóa từng cái.

### Câu hỏi tự kiểm tra

1. Khi nào nên dùng Adapter vs **viết lại Adaptee với interface mới**? (Gợi ý: cost, ownership, breaking changes)
2. Trong não, một số modality có thể đi qua nhiều thalamic nucleus (vd: visual qua LGN cho V1, qua pulvinar cho cross-modal). Tại sao? Bài học gì cho việc nhiều adapter cho cùng adaptee?
3. Trong Ellumm, nếu một adapter cần xử lý logic phức tạp (vd: `CameraAdapter` thực hiện noise reduction, color balance, frame interpolation), có còn là Adapter không? Hay đã trở thành pattern khác? (Gợi ý: lesson 09, 10)
