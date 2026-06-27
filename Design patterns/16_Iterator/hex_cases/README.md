# Iterator Pattern trong hex_agent — Bộ case thực chiến

> Phụ lục thực hành cho [16_Iterator.md](../16_Iterator.md). Ở bài học gốc ta dùng analogy **saccade** (mắt nhảy fixation, SC/FEF/LIP quyết định "fixation tiếp theo ở đâu" thay cho võng mạc). Ở đây ta đi tìm **chính cái cơ chế đó trong code thật của hex_agent**: chỗ nào client chỉ gọi `next()` mà không cần biết bên trong là tree, JSONL journal, hay file 8MB.

---

## TÓM TẮT MỘT DÒNG (nhắc lại)

**Iterator** = đóng gói _cách duyệt_ một collection sao cho client chỉ cần gọi `next()` / `for x in ...` mà không cần biết bên trong là list, tree, graph hay stream.

---

## Iterator xuất hiện ở đâu trong hex_agent?

Pattern này có mặt **xuyên suốt** codebase, ở cả hai dạng: **tường minh** (một class/hàm cố tình che giấu logic duyệt) và **ẩn** (tận dụng iterator protocol native của Python qua `__iter__` và generator). Ba dạng nổi bật nhất:

1. **Tree cursor** — `Tree.next_node()` trong decompose agent: trả node "kế tiếp" theo topo-order `(depth, order)` mà không lộ cấu trúc DAG. `solve()` chỉ làm `while (node := tree.next_node()) is not None`. Đây là ví dụ Iterator _đóng gói_ rõ nhất, vì logic duyệt (topo-sort + status tracking) hoàn toàn nằm trong `next_node()`.
2. **Iterator protocol native** — `EventLog.__iter__()` và `Ledger.read()` trong drag_from_zero: log append-only đọc từng dòng JSONL, biến `for event in log` thành chuyện đương nhiên. Dạy luôn về **fail-soft**: reader bỏ qua dòng hỏng thay vì sập cả run.
3. **Lazy generator** — `iter_records_in_window()` trong harness telemetry: `yield` từng record khớp time-window, đọc file 8MB với bộ nhớ O(1) thay vì nạp hết.

Ba dạng này phủ đúng phổ mà bài gốc nói tới: **external iterator có logic riêng** (case 01), **iterator protocol / internal iterator** (case 02), và **lazy iterator / generator cho dữ liệu không thể load hết** (case 03).

---

## Các case con

| # | Thư mục | Distill từ (file thật) | Trọng tâm |
|---|---------|------------------------|-----------|
| 01 | [`01_tree_next_node_cursor/`](01_tree_next_node_cursor/) | `decompose_agent/tree.py:43-51`, `decompose_agent/solve.py:262-293` | External iterator có logic riêng: cursor topo-order ẩn trong `next_node()`; client chỉ gọi đến khi `None`. |
| 02 | [`02_eventlog_iter_protocol/`](02_eventlog_iter_protocol/) | `drag_from_zero/dragzero/events.py:87-88`, `drag_from_zero/dragzero/ledger.py:47-67` | Iterator protocol native (`__iter__`) + reader fail-soft bỏ qua dòng JSONL hỏng. |
| 03 | [`03_telemetry_generator/`](03_telemetry_generator/) | `harness/scripts/telemetry_paths.py:54-84` | Lazy generator: `yield` record theo time-window, bộ nhớ O(1) bất kể file lớn cỡ nào. |

Mỗi case có `README.md` (6 mục: bối cảnh → trích code thật → bảng ánh xạ vai trò → bản rút gọn chạy được → cái giá → câu hỏi tự kiểm tra) và một file `.py` self-contained chạy được bằng `python3` (chỉ stdlib).

---

## Liệt kê đầy đủ mọi nơi Iterator xuất hiện

Xem [CATALOG.md](CATALOG.md) — bảng vét cạn mọi occurrence (từ rõ nét đến mờ) với `path:line`, mô tả và độ rõ.

---

## Cách chạy

```bash
cd "Design patterns/16_Iterator/hex_cases"
python3 01_tree_next_node_cursor/tree_next_node_cursor.py
python3 02_eventlog_iter_protocol/eventlog_iter_protocol.py
python3 03_telemetry_generator/telemetry_generator.py
```

Mỗi script in narration tiếng Việt từng bước, có đối chứng "khi KHÔNG dùng pattern thì hỏng/khó thế nào", và `assert` chứng minh bất biến của pattern. Tất cả thoát code 0, không traceback.
