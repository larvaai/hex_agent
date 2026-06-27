# Lesson 01 — Singleton

> **Một lớp, một instance, một điểm truy cập toàn cục.**

---

## Mức 1 — CONCEPT (Ý tưởng)

### Vấn đề pattern giải quyết

Có những loại "tài nguyên" trong hệ thống mà nếu tồn tại nhiều bản sao thì sẽ mâu thuẫn:
- 1 file log mà 2 logger ghi cùng lúc → dòng log xen kẽ rối loạn.
- 1 cấu hình hệ thống mà 2 instance khác nhau → module A đọc giá trị cũ, module B đọc giá trị mới.
- 1 connection pool mà tạo 2 cái → tốn gấp đôi tài nguyên, deadlock.

Singleton đảm bảo **chỉ tồn tại đúng 1 instance** của class trong toàn vòng đời chương trình, và mọi nơi truy cập đều thấy cùng 1 đối tượng.

### Neuroscience analogy — Locus Coeruleus (LC)

LC là 1 nhân nhỏ ở thân não (pons), chỉ chứa khoảng 50.000 neuron mỗi bên. Nhưng:
- Đây là **nguồn norepinephrine (NE) chính** cho toàn cortex, hippocampus, amygdala, cerebellum, tủy sống.
- Mọi vùng não cần "tăng arousal / chú ý / cảnh giác" đều **không tự sinh NE riêng** — chúng đọc tín hiệu từ chung 1 LC.
- Nếu có 2 hệ LC độc lập phát NE mâu thuẫn (1 bảo "tăng arousal", 1 bảo "giảm"), toàn não sẽ rơi vào trạng thái không nhất quán → không thể quyết định hành vi.

→ LC là **Singleton sinh học**: một nguồn duy nhất, truy cập toàn cục, đảm bảo arousal-state nhất quán giữa mọi vùng.

### Khi nào KHÔNG dùng Singleton

Singleton bị lạm dụng nhiều nhất trong các pattern. Nó **chống lại unit test**, gây **coupling ngầm**, và là **global state trá hình**. Chỉ dùng khi:
1. Đối tượng thực sự **chỉ tồn tại đúng 1 trong domain** (LC thật chỉ có 1).
2. Mọi nơi cần **đồng bộ state** chia sẻ.
3. Tạo lại sẽ **tốn kém hoặc sai semantic**.

Nếu chỉ vì "tôi muốn dễ truy cập" → dùng Dependency Injection thay vì Singleton.

---

## Mức 2 — ALGORITHM (Thuật toán)

### Cấu tạo (5 chiều theo framework Ellumm)

| Chiều | Nội dung |
|-------|----------|
| **Cấu tạo** | 1 class với: (a) biến class lưu instance duy nhất, (b) constructor private/protected, (c) static method `get_instance()` |
| **Vị trí** | Tầng infrastructure / cross-cutting (logger, config, cache, clock, registry) |
| **Chức năng** | Đảm bảo "chỉ 1 instance" + cung cấp global access point |
| **Kết nối** | Bị **mọi class khác** trong hệ thống tham chiếu — chính vì thế Singleton dễ thành "thượng đế class" |
| **Ý nghĩa** | Single Source of Truth cho 1 loại state cụ thể |

### Logic vận hành

```
KHI client gọi LocusCoeruleus.get_instance():
    NẾU instance chưa tồn tại:
        TẠO instance mới (chạy __init__ đúng 1 lần)
        LƯU vào biến class
    TRẢ VỀ instance
```

Có 3 vấn đề kỹ thuật cần xử lý:

1. **Lazy vs Eager**: tạo lúc khởi động chương trình (eager) hay lúc lần đầu được gọi (lazy)? Lazy tiết kiệm bộ nhớ nhưng cần lock cho thread.
2. **Thread safety**: 2 thread gọi `get_instance()` đồng thời, cả 2 thấy `instance is None` → tạo 2 instance → vi phạm Singleton. Cần `Lock`.
3. **Subclassing**: cho phép kế thừa Singleton không? Thường KHÔNG, để tránh nhiều "loại" instance.

---

## Mức 3 — PSEUDOCODE + PYTHON

### Pseudocode

```
class LocusCoeruleus:
    _instance = None              # biến class, không phải instance
    _lock = Lock()                # bảo vệ tạo instance đa luồng

    function get_instance():
        with _lock:
            if _instance is None:
                _instance = new LocusCoeruleus()
        return _instance

    function release_norepinephrine(level):
        self.ne_level = clamp(level, 0, 100)

    function read_arousal():
        return self.ne_level
```

### Python (xem file `01_singleton.py`)

3 cách cài đặt phổ biến (file code minh họa cả 3):
- **`__new__` override**: Pythonic nhất, ngắn gọn.
- **Metaclass**: dùng khi muốn "Singleton-hóa" nhiều class một cách đồng nhất.
- **Module-level singleton**: thực ra Python module *đã là* Singleton (chỉ import 1 lần) — đây là cách Pythonic nhất nếu không cần lazy init phức tạp.

---

## 3 LOẠI VÍ DỤ

### Ví dụ 1 — Vận hành thường

Cortex prefrontal cần đánh giá xem stimulus hiện tại có đáng chú ý không, gọi `LocusCoeruleus.get_instance().read_arousal()` → nhận giá trị NE = 65. Cùng lúc, hippocampus đang quyết định có encode trải nghiệm này thành memory không, cũng gọi đúng method đó → nhận **chính giá trị 65**. Cả 2 vùng đồng bộ về một mức arousal duy nhất.

### Ví dụ 2 — Hỏng / Thiếu

Giả sử Singleton bị phá: mỗi vùng não tự khởi tạo `LocusCoeruleus()` riêng. Một sự kiện stress đến → amygdala tự tạo LC riêng và set NE=90; hippocampus tự tạo LC riêng và vẫn ở NE=20. Kết quả: amygdala hành xử như đang nguy hiểm, hippocampus hành xử như đang an toàn → memory được encode với cảm xúc tag sai (encode "an toàn" cho 1 sự kiện thực ra rất đáng sợ). Đây chính là cơ chế gốc của một số rối loạn lo âu trong đó hệ noradrenergic mất đồng bộ.

Trong code: 2 module ghi log vào 2 instance Logger khác nhau → file log thiếu một nửa thông tin, debug không thể truy được nguyên nhân.

### Ví dụ 3 — Ứng dụng Ellumm

Trong Ellumm, `GlobalArousalState` là Singleton chứa các biến cảm xúc tức thời:
```python
class GlobalArousalState:
    arousal: float       # 0-100
    valence: float       # -50 đến +50
    cortisol: float
    dopamine: float
```

Mọi module — vision (đang trace pixel), memory_dict (đang quyết định encode), instinct (đang quyết định reflex) — đọc cùng 1 instance. Khi pixel-tracing phát hiện mẫu lặp ổn định → memory_dict gọi `arousal.read()` để gating learning rate (nguyên tắc Yerkes-Dodson: chỉ học khi arousal trong khoảng tối ưu). Nếu mỗi module có instance riêng, biến arousal sẽ phân mảnh → vi phạm nguyên tắc "Single Source of Truth" và làm Ellumm mất tính nhất quán cảm xúc.

---

## TÓM LẠI

Singleton = **1 instance + global access**. Đơn giản về kỹ thuật, **khó về kỷ luật** — bạn phải chứng minh được "thật sự chỉ có 1" trong domain trước khi dùng. Trong neuroscience, các hệ neuromodulator nhân nhỏ (LC cho NE, raphe cho serotonin, VTA cho dopamine, tuberomammillary cho histamine) đều là Singleton tự nhiên — chúng nhỏ về số neuron nhưng phủ sóng toàn não, và đó là bài học kiến trúc: **Singleton chỉ chính đáng khi nó là kênh phát toàn cục, không phải khi nó là kho dữ liệu lười dùng global**.

### Câu hỏi tự kiểm tra

1. Tại sao module-level singleton trong Python an toàn hơn class Singleton có `_instance`?
2. Nếu Ellumm cần test riêng module memory mà không khởi động cả `GlobalArousalState`, làm thế nào? (Gợi ý: Dependency Injection + interface)
3. Trường hợp nào LC sinh học không hành xử như Singleton tuyệt đối? (Gợi ý: lateralization — bán cầu trái/phải có thể có mức NE khác nhau)
