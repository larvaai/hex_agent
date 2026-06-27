# Lesson 16 — Iterator Pattern
## Saccade — Quét Tuần Tự Visual Scene

---

## TÓM TẮT MỘT DÒNG

**Iterator** = đóng gói _cách duyệt_ một collection sao cho client chỉ cần gọi `next()` mà không cần biết bên trong là list, tree, graph hay stream.

> Não bạn không "xem cả visual scene cùng lúc". Mắt nhảy 3–4 lần mỗi giây (saccade). Saccade controller (superior colliculus + FEF + LIP) chính là **Iterator** — nó quyết định "fixation tiếp theo ở đâu", visual cortex chỉ cần xử lý cái đang fixate, không cần biết cách nào đến đó.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Một collection (list, tree, graph, file, stream) có thể được duyệt theo nhiều cách (xuôi, ngược, depth-first, breadth-first, theo độ ưu tiên...). Nếu **client tự duyệt**, hai vấn đề xuất hiện:

1. **Client phải biết cấu trúc bên trong** của collection — làm rò rỉ encapsulation, vi phạm SOLID (Single Responsibility, Open/Closed).
2. **Mỗi cách duyệt phải nhân bản code** ở mọi chỗ dùng — vi phạm DRY, tăng coupling.

Iterator tách _cách duyệt_ thành một object riêng. Collection chỉ cần "đẻ ra Iterator". Client chỉ gọi `has_next() / next()`. Muốn đổi cách duyệt? Đẻ Iterator khác. Muốn duyệt song song nhiều lần? Mỗi cursor là một Iterator độc lập.

### 1.2. Neuroscience analogy — Saccade

Mắt người không quét visual scene như scanner. Trong 200ms một fixation, võng mạc chỉ thấy rõ ~2° quanh fovea — phần còn lại mờ. Mỗi giây có 3–4 saccade, mỗi cái 20–80ms. Trong 30 phút đọc, mắt nhảy ~5400 lần mà bạn không hề nhận ra.

Ai quyết định fixation tiếp theo? **Không phải võng mạc**. Đó là một mạch:

- **Superior Colliculus (SC)**: motor map — sinh saccade vector (đi đâu, bao xa).
- **Frontal Eye Field (FEF)**: goal-driven — "tôi đang tìm chữ X, nhảy về phía đó".
- **Lateral Intraparietal area (LIP)**: salience map — "vùng kia có gì nổi bật".
- **Pulvinar**: gate attention — quyết định info nào được xử lý sau saccade.

→ Visual cortex (V1→V2→V4→IT) chỉ làm việc của nó: **xử lý cái đang fixate**. Nó không cần biết "đến đây bằng cách nào", "tiếp theo đi đâu". Đó chính là Iterator: client (V1) gọi `next()` (saccade), nhận được item (fixation), xử lý.

#### 5 chiều của analogy

| Chiều      | Trong não                                                                | Trong code                                                              |
|------------|--------------------------------------------------------------------------|--------------------------------------------------------------------------|
| Cấu tạo    | SC + FEF + LIP + pulvinar                                                | `Iterator` interface + `ConcreteIterator` (state cursor)                |
| Vị trí     | Tách biệt khỏi võng mạc và visual cortex                                 | Tách biệt khỏi `Aggregate` và client                                    |
| Chức năng  | Sinh sequence fixation, không phụ thuộc nội dung scene                  | Sinh sequence item, không phụ thuộc cấu trúc collection                |
| Kết nối    | SC nhận lệnh từ FEF (goal) + LIP (salience), gửi motor command tới mắt   | Iterator nhận từ Aggregate, gửi item tới client                         |
| Ý nghĩa    | Cho phép cùng một scene được "đọc" theo goal khác nhau                  | Cho phép cùng một collection được duyệt theo strategy khác nhau         |

### 1.3. Khi nào DÙNG

- Cấu trúc collection phức tạp (tree/graph/composite) nhưng client chỉ cần tuần tự.
- Cần **nhiều cách duyệt** trên cùng collection (in-order, pre-order, level-order).
- Cần duyệt **song song** nhiều cursor độc lập (collection bất biến tại thời điểm duyệt).
- Dữ liệu **lazy / infinite** (stream, paginated API, sensor feed) — không thể load hết.
- Muốn **ẩn cấu trúc** (encapsulation): file format, DB cursor, Kafka consumer.

### 1.4. Khi nào KHÔNG DÙNG

- Collection nhỏ, đơn giản, dùng 1 lần → `for x in list` của Python là đủ. Iterator pattern dư thừa.
- Cần **random access** theo index (`a[42]`) → Iterator không phù hợp; dùng list/array trực tiếp.
- Logic duyệt cần **biết tổng số phần tử trước** để planning → Iterator chỉ tốt khi có thể incremental.
- Khi traversal có **side effect lan ra collection** (ví dụ vừa duyệt vừa xóa/sửa) → dễ invalidate cursor; cân nhắc **Visitor** hoặc snapshot.

### 1.5. Cảnh báo architect

> **Iterator không phải "for-loop với extra steps"**. Nếu code chỉ làm `next() / has_next()` trên một list, bạn đang viết overhead. Iterator có giá trị **khi cách duyệt có logic riêng** (lazy, ordered, filtered, traversal tree, paginated remote).

---

## MỨC 2 — ALGORITHM

### 2.1. Vai diễn

```
┌─────────────────┐         ┌──────────────────┐
│   Aggregate     │ create  │     Iterator     │
│   (Iterable)    │────────▶│   (interface)    │
│                 │         │                  │
│ + iterator()    │         │ + has_next()     │
│ + iterator(...) │         │ + next() -> Item │
└─────────────────┘         └──────────────────┘
        △                            △
        │                            │
┌─────────────────┐         ┌──────────────────┐
│ ConcreteAggreg. │         │ ConcreteIterator │
│ (VisualScene)   │         │ (TopDownSaccade, │
│                 │         │  BottomUpSaccade)│
└─────────────────┘         └──────────────────┘
```

- **Aggregate**: collection (visual scene). Có method `iterator()` (hoặc nhiều, ví dụ `iterator_top_down()`, `iterator_salience()`).
- **Iterator**: interface với `has_next()` + `next()`. Có thể có thêm `reset()`, `current()`, `remove()` (cẩn thận).
- **ConcreteIterator**: chứa **state cursor** (vị trí, visited set, queue/stack nếu DFS/BFS).
- **Client**: V1 visual cortex — chỉ gọi `while it.has_next(): process(it.next())`.

### 2.2. Luồng điều khiển

```
Client          Aggregate           ConcreteIterator
  │                 │                       │
  ├─iterator()─────▶│                       │
  │                 ├─new(self)────────────▶│  (cursor=0, visited={})
  │◀────────────────┤                       │
  │                                         │
  ├─has_next()─────────────────────────────▶│  (cursor < N ?)
  │◀────────────────────────────────────────┤  True
  │                                         │
  ├─next()─────────────────────────────────▶│  (item=fixate(cursor); cursor++)
  │◀────────────────────────────────────────┤  Item
  │                                         │
  ├─process(item)                           │
  │  ...                                    │
  │  (lặp lại has_next/next)                │
```

### 2.3. Biến trạng thái

- `cursor`: vị trí hiện tại (int, node ref, pagination token).
- `visited`: set các phần tử đã duyệt — quan trọng cho graph/cycle.
- `queue` hoặc `stack`: chỉ DFS/BFS hoặc traversal có backtracking.
- `snapshot`: bản sao collection tại thời điểm tạo iterator — chống "concurrent modification".
- `predicate`: nếu là **filtering iterator** (chỉ trả phần thỏa điều kiện).

### 2.4. Bất biến (invariants)

1. Sau mỗi `next()`, `cursor` **chỉ tiến**, không lùi (trừ khi có `reset()`).
2. Hai iterator độc lập trên cùng collection **không ảnh hưởng nhau**.
3. Nếu collection bị sửa khi đang duyệt: hoặc raise `ConcurrentModificationException`, hoặc đảm bảo snapshot. **Không bao giờ trả kết quả không xác định.**
4. `has_next()` phải **idempotent** — gọi nhiều lần liên tiếp cùng kết quả.

### 2.5. Biến thể (architect cần biết)

- **External iterator** (client cầm cursor): `it.next()` — kiểu Java/Python truyền thống. Linh hoạt, client kiểm soát timing.
- **Internal iterator** (collection tự duyệt): `collection.for_each(callback)` — kiểu Ruby `each`, JS `forEach`. An toàn hơn, nhưng client mất quyền dừng/skip (trừ khi có break protocol).
- **Lazy iterator / generator**: `yield` — chỉ tính khi cần, hỗ trợ infinite stream.
- **Bidirectional iterator**: `next() + previous()`. Đắt hơn (state phức tạp).
- **Random-access iterator**: `at(i)`. Khi đó pattern thoái hóa thành array.
- **Filtering / mapping iterator**: bọc một iterator khác (Decorator on Iterator). Cực mạnh khi compose.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
interface Iterator<T>:
    has_next() -> bool
    next() -> T

interface Aggregate<T>:
    iterator() -> Iterator<T>

class VisualScene implements Aggregate<Fixation>:
    fixations: List<Fixation>
    
    iterator_top_down() -> Iterator<Fixation>:
        return TopDownSaccadeIterator(self.fixations, goal=current_goal)
    
    iterator_salience() -> Iterator<Fixation>:
        return SalienceSaccadeIterator(self.fixations)

class TopDownSaccadeIterator implements Iterator<Fixation>:
    fixations
    goal
    cursor = 0
    
    has_next() -> bool:
        return cursor < len(fixations)
    
    next() -> Fixation:
        item = fixations[cursor]
        cursor += 1
        return item
```

### 3.2. Python — 3 ví dụ

Toàn bộ code chạy được nằm ở `16_iterator.py`. Bên dưới là tóm tắt cấu trúc.

#### Ví dụ 1 — Vận hành thường: Saccade scan theo salience

Visual scene có nhiều fixation point, mỗi point có salience score. Iterator trả ra fixation theo thứ tự salience giảm dần — đây là **bottom-up attention**.

Điểm cần chú ý của architect:
- Iterator **dùng heap** internally → `next()` O(log N), không phải O(N).
- Mỗi gọi `iterator_salience()` đẻ một iterator độc lập → có thể chạy song song.
- Nếu thêm fixation sau khi iterator đã sinh, iterator dùng **snapshot** → không "concurrent modification".

#### Ví dụ 2 — Hỏng / thiếu: Iterator bị invalidate

Mô phỏng case _eye fatigue_: collection bị thay đổi giữa chừng (saccade adaptation, dropped fixation). Có 2 cách xử lý:

- **Fail-fast**: raise `ConcurrentModificationError` ngay khi phát hiện. Code rõ, debug dễ.
- **Snapshot**: iterator clone collection lúc tạo, sửa sau đó không ảnh hưởng. Tốn memory, nhưng predictable.

Bài học architect: **chọn strategy ngay khi thiết kế API**, đừng để runtime quyết định.

#### Ví dụ 3 — Ứng dụng Ellumm: lazy iterator cho paginated content

Ellumm có thư viện bài học khổng lồ. Không thể load 100k bài. Dùng `LazyLessonIterator` — gọi API trang n+1 chỉ khi user cuộn đến cuối trang n. Đây là **iterator như abstraction trên I/O latency**.

Đặc điểm:
- `has_next()` có thể block (network call) → cần async variant.
- Cursor là **opaque token** từ server, không phải int.
- Iterator hold reference tới HTTP client → cần `close()` để release. (Iterator cũng có lifecycle như resource.)

---

## SO SÁNH VỚI PATTERN KHÁC

| Pattern        | Khác biệt với Iterator                                                                     |
|----------------|---------------------------------------------------------------------------------------------|
| **Composite**  | Composite định nghĩa _cấu trúc_ tree; Iterator định nghĩa _cách duyệt_ tree. Bổ sung nhau. |
| **Visitor**    | Visitor đem _operation_ đến từng phần tử (double dispatch). Iterator chỉ đem _phần tử_ ra. Visitor mạnh khi op đa dạng theo type; Iterator mạnh khi op cố định, traversal đa dạng. |
| **Strategy**   | Strategy đổi _logic_, Iterator đổi _thứ tự duyệt_. Iterator thực ra là Strategy của traversal. |
| **Observer**   | Observer là **push** (subject đẩy event); Iterator là **pull** (client kéo item). Bộ não dùng cả hai: amygdala = push (Observer), saccade = pull (Iterator). |
| **Generator (Python)** | Generator là Iterator viết bằng cú pháp `yield`. Cùng pattern, syntactic sugar. |

> **Insight architect**: Khi bạn cần kết hợp _traversal + operation đa dạng_, đừng nhồi vào Iterator. Iterator giữ traversal, Visitor giữ operation. Composing patterns > monolithic patterns.

---

## ANTI-PATTERNS THƯỜNG GẶP

1. **God Iterator** — 1 iterator class biết quá nhiều: vừa duyệt, vừa filter, vừa transform, vừa cache.
   - Triệu chứng: 500+ dòng, 10 method, hàng đống flag.
   - Xử lý: tách thành chuỗi iterator nhỏ (FilterIterator, MapIterator, BatchIterator) — compose lại.

2. **Leaking internal state** — Iterator trả ra reference vào internal buffer; client sửa → collection hỏng.
   - Xử lý: trả copy hoặc immutable view.

3. **Stateful collection inside Iterator** — Iterator giữ state mà collection cũng giữ state, dễ desync.
   - Xử lý: cursor sống trong **Iterator**, dữ liệu sống trong **Aggregate**. Không trùng.

4. **Iterator như cursor DB không close** — leak connection.
   - Xử lý: implement `__enter__`/`__exit__` (context manager) để auto-close.

5. **`for_each` callback vs external iterator nhầm chỗ** — dùng `for_each` khi cần break sớm; phải hack bằng exception.
   - Xử lý: external iterator nếu cần kiểm soát luồng, internal nếu chỉ cần apply.

---

## BÀI TẬP

1. **Cơ bản**: Cài `BinaryTreeIterator` với 3 mode: pre-order, in-order, post-order. Dùng generator (`yield`).
2. **Trung bình**: Viết `FilterIterator` bọc bất kỳ iterator nào, nhận `predicate`. Sau đó viết `MapIterator`. Compose: `MapIterator(FilterIterator(scene.iterator(), predicate=is_high_salience), fn=fixate)`.
3. **Khó (architect)**: Thiết kế `PaginatedAPIIterator` cho API Ellumm với:
   - cursor là opaque token,
   - retry với exponential backoff khi network fail,
   - context manager để release connection,
   - test với mock server giả lập 3 trang, 1 lỗi 503 ở giữa.
   
   Sau đó refactor: tách thành `PageFetcher` (Strategy) + `RetryPolicy` (Strategy) + `Iterator` chỉ orchestrate. Đó là cách architect thật phân chia trách nhiệm.

4. **Mở rộng neuro**: Mô phỏng `ScanpathIterator` mô phỏng eye-tracking thật: kết hợp goal-driven (FEF) + salience (LIP) bằng cách _weighted sum_. Đổi weight để có 2 strategy "reading mode" vs "scanning mode".

---

## PYTHON-NATIVE: `__iter__`, `__next__`, generators

Python đã built-in Iterator pattern qua **iterator protocol**. Bạn không cần class riêng nếu dùng `yield`.

```python
def saccade_top_down(scene):
    for fixation in sorted(scene, key=lambda f: f.priority):
        yield fixation

# Client:
for f in saccade_top_down(scene):
    visual_cortex.process(f)
```

→ Generator là Iterator. `yield` lưu state implicitly. **Khi nào vẫn cần class Iterator** (không dùng generator)?
- Cần `reset()` / random access / `current()`.
- Cần Iterator có **lifecycle** (resource, close, retry).
- Cần serialize Iterator state qua process boundary (microservice).
- Cần multiple methods ngoài `next()` (peek, skip, batch).

> Quy tắc architect: **dùng generator cho 90% case, class Iterator cho 10% case có yêu cầu lifecycle/state nâng cao.**

---

## CHECKLIST TRƯỚC KHI MERGE PR DÙNG ITERATOR

- [ ] Iterator có document rõ: thứ tự duyệt là gì? Có ổn định không?
- [ ] Có handle "concurrent modification" (fail-fast / snapshot / locked)?
- [ ] Có resource cần release? Có context manager chưa?
- [ ] Iterator có thể dùng song song nhiều cursor không?
- [ ] Có overhead nào không cần thiết khi dùng generator được?
- [ ] Test có cover: empty collection, 1 element, traverse 2 lần, modify giữa chừng?

---

## TÓM LẠI BẰNG NEUROSCIENCE

> Mắt + SC + FEF + LIP đã giải quyết bài toán "duyệt cảnh quan vô cùng phức tạp với năng lượng hữu hạn" qua hàng triệu năm tiến hóa: **tách logic chọn fixation tiếp theo ra khỏi xử lý nội dung fixation**. Đó chính là Iterator. Khi bạn nhìn một trang code 500 dòng, mắt bạn vừa đang demo Iterator pattern — và nó hoạt động vì SC không cần biết cấu trúc não, chỉ cần biết "fixation tiếp theo ở đâu".

Đến lesson 17 (Mediator — Thalamus), bạn sẽ thấy não tiếp tục dùng pattern để **chống N-to-N coupling** giữa các vùng cortex. Architect thật sự là người nhận ra: pattern đã có ở đó từ 500 triệu năm trước, code chỉ là phiên bản digital.
