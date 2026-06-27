# Case 02 — EventLog Iterator Protocol: `__iter__` + Ledger fail-soft

> Iterator pattern ở dạng _ẩn_ — đúng tinh thần "PYTHON-NATIVE" của bài gốc: bạn không cần class Iterator riêng, chỉ cần `__iter__` là `for x in collection` chạy. Case này còn dạy thêm một bài học mà bài gốc nhấn mạnh ở anti-pattern #2: khi item đến từ storage ngoài, "cách duyệt" phải chịu trách nhiệm chống dữ liệu hỏng.

---

## 1. Bối cảnh trong hex_agent

`drag_from_zero` (dragzero) dựng một hệ event-sourcing: **đĩa là sự thật duy nhất**. Cây thực thi không bao giờ được lưu — nó được "fold" lại từ một log event append-only. Có hai tầng:

- `EventLog` (in-memory) — một _cache_ của các `Event`, là iterable native.
- `Ledger` (on-disk) — file JSONL, mỗi event một dòng. Khi crash giữa lúc ghi, dòng cuối có thể bị cụt. Reader phải **bỏ qua** dòng hỏng đó, không được sập — vì "journal là evidence, và partial evidence must not take down the run that reads it".

File thật:
- `drag_from_zero/dragzero/events.py:87-88` — `EventLog.__iter__()`.
- `drag_from_zero/dragzero/events.py:78-85` — `events()` / `of_type()` / `types()`.
- `drag_from_zero/dragzero/ledger.py:47-67` — `Ledger.read()` corruption-tolerant.

Docstring `ledger.py:4-6` nói rõ:
> "The reader is corruption-tolerant: a truncated or non-dict last line (a half-written crash record) is dropped, not fatal — `reduce` over the survivors still yields a coherent tree, and resume = re-read + fold."

---

## 2. Trích đoạn code thật

Iterator protocol native — `events.py:87-88`:

```python
def __iter__(self):
    return iter(self._events)
```

Reader fail-soft — `ledger.py:47-67`:

```python
def read(self) -> list[Event]:
    """Fold the ledger back into Events. A truncated/non-dict tail line is dropped (crash
    half-write), never raised — every clean prefix line survives."""
    if not self.path.exists():
        return []
    out: list[Event] = []
    for raw in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            break  # a torn line can only be the tail; everything after is suspect too
        if not isinstance(d, dict) or "type" not in d:
            break
        try:
            out.append(event_from_dict(d))
        except (KeyError, ValueError):
            break
    return out
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Iterator | Trong hex_agent | Trong bản distill (`eventlog_iter_protocol.py`) |
|------------------|-----------------|-------------------------------------------------|
| **Aggregate (in-memory)** | `EventLog._events: list[Event]` | `EventLog._events` |
| **Iterator (in-memory)** | `EventLog.__iter__()` → `iter(self._events)` | `__iter__` y hệt |
| **Aggregate (on-disk)** | `Ledger` (file JSONL = sự thật) | `Ledger` ghi/đọc file thật trong tmp |
| **Iterator (on-disk)** | `Ledger.read()` duyệt từng dòng, parse, **bỏ dòng hỏng** | `Ledger.read()` giữ nguyên logic fail-soft |
| **Item** | `Event` (frozen dataclass) | `Event` (frozen dataclass) |
| **Filtering iterator** | `of_type(t)` / `types()` bọc quanh `_events` | `of_type(t)` |
| **Client** | mọi chỗ viết `for event in log` | `[e.type for e in log]` trong `demo()` |

Đây là **Iterator hai tầng**: tầng in-memory dùng iterator protocol _ẩn_ của Python; tầng on-disk là external iterator _tường minh_ có thêm trách nhiệm chống hỏng. Cả hai cùng che giấu "cách duyệt" khỏi client.

---

## 4. Bản rút gọn chạy được

File: [`eventlog_iter_protocol.py`](eventlog_iter_protocol.py)

**Mô phỏng:**
1. Tạo `EventLog`, append vài event, rồi duyệt bằng `for e in log` — chứng minh `__iter__` đủ để `for` chạy mà client không biết bên trong là list.
2. Ghi log ra `Ledger` (file JSONL thật trong thư mục tmp), `read()` lại để chứng minh "resume = re-read".
3. **Nối thêm một dòng JSONL bị cụt** (mô phỏng crash half-write). `Ledger.read()` vẫn trả về 4 event sạch, bỏ qua dòng hỏng.
4. **Đối chứng `read_naive()`**: reader không có `try/except` — gặp dòng cụt thì nổ `json.JSONDecodeError`, cả run sập.

**Lược bỏ so với bản thật:** `os.fsync` durable trước khi `append()` trả về, cơ chế `subscribe`/live-view, `EventLog.replay(ledger)`, seq-stamping qua nhiều lớp, và `EventType` enum đầy đủ (thay bằng `str`). Trọng tâm là **duyệt + fail-soft**, nên hạ tầng durability bị bỏ; nhưng file JSONL được ghi/đọc _thật_ để `read()` có cái để duyệt.

**Bất biến được `assert`:**
- Duyệt log bằng `for` cho đúng thứ tự append.
- `seq` tăng đơn điệu `0,1,2,3` (iterator chỉ tiến, không lùi — bất biến 1 mục 2.4 bài gốc).
- `read()` khớp những gì đã ghi.
- Sau khi nối dòng hỏng, `read()` vẫn trả đúng 4 event prefix sạch.
- `read_naive()` nổ `JSONDecodeError` trên cùng file đó.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **`Ledger.read()` đọc cả file vào RAM** (`read_text().splitlines()`). Với journal nhỏ-per-node thì ổn, nhưng với file rất lớn nên dùng generator stream-line-by-line (đó chính là case 03). Đây là ranh giới giữa "list-based iterator" và "lazy iterator".
- **Fail-soft `break`-ở-dòng-đầu-tiên-hỏng** giả định mọi hỏng hóc đều nằm ở **đuôi** (crash half-write). Nếu file bị hỏng ở **giữa** (ví dụ đĩa lỗi block), cách này sẽ âm thầm bỏ mất dữ liệu sạch phía sau. Phải biết rõ mô hình hỏng của storage trước khi chọn chiến lược này (so với case 03 dùng `continue` để bỏ _từng_ dòng hỏng).
- **Đừng dùng iterator protocol cho cái cần random access.** Nếu client thật ra cần `events[42]`, thì `list` trực tiếp tốt hơn — `__iter__` ở đây chỉ có giá vì client luôn duyệt tuần tự.

---

## 6. Câu hỏi tự kiểm tra

1. `EventLog` không định nghĩa `__next__`, vẫn `for e in log` được. Vì sao? (Gợi ý: `__iter__` trả về cái gì, và cái đó có sẵn `__next__` chưa?)
2. `Ledger.read()` dùng `break` khi gặp dòng hỏng, còn `Journal.records()` (`decompose_agent/journal.py:43-44`) dùng `continue`. Khác biệt này phản ánh giả định gì về _vị trí_ của dòng hỏng trong từng file? Khi nào mỗi lựa chọn đúng?
3. Trong đối chứng, `read_naive()` nổ ngay dòng cụt. Nếu dòng cụt nằm ở _giữa_ file (không phải đuôi), `Ledger.read()` sẽ trả về gì, và điều đó có còn là hành vi mong muốn không?
