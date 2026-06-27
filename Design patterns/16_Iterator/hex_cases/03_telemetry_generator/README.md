# Case 03 — Lazy Generator Iterator: `iter_records_in_window()`

> Iterator pattern ở dạng _generator_ — cú pháp `yield` chính là Iterator (bài gốc, bảng "SO SÁNH": *"Generator là Iterator viết bằng cú pháp `yield`"*). Đây là dạng dùng cho **dữ liệu lazy/infinite/quá-lớn-để-load-hết**, đúng "ví dụ 3 — lazy iterator cho paginated content" của bài gốc.

---

## 1. Bối cảnh trong hex_agent

Harness ghi một **usage telemetry ledger** dạng JSONL — mỗi op của hook là một dòng. File này rotation ở **8MB** trước khi tạo `.bak`. Các "lens" (báo cáo metrics) cần đọc các record trong một time-window (ví dụ `--days 7`), nhưng:

- Không thể nạp cả file 8MB vào RAM mỗi lần một lens chạy.
- Nhiều lens chạy → nếu mỗi lens tự đọc file + tự lọc thì code lọc bị nhân bản, và mỗi lens dễ quên một guard (đúng "bug class the lens review found re-implemented inconsistently" — comment trong code).

Giải pháp: **một** generator chung — `iter_records_in_window()` — `yield` từng record hợp lệ trong window, stream line-by-line với bộ nhớ O(1). Mọi lens dùng chung nó.

File thật:
- `harness/scripts/telemetry_paths.py:54-84` — `iter_records_in_window()`.
- `harness/scripts/telemetry_paths.py:41-51` — `parse_iso_ts()` (trả `None` thay vì raise).

Docstring/comment trong code nói thẳng:
> "Stream line-by-line (O(1) memory regardless of sink size; the 8 MB cap is the current bound)." (`telemetry_paths.py:65-66`)
> "The single read-path every lens shares ... so no lens can forget the non-object guard." (`telemetry_paths.py:57-59`)

---

## 2. Trích đoạn code thật

`harness/scripts/telemetry_paths.py:54-84`:

```python
def iter_records_in_window(sink_name: str, days: int):
    """Yield each dict record from telemetry sink ``sink_name`` whose ts is within
    the last ``days``. ... Fail-soft."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    p = harness_paths.telemetry_dir() / sink_name  # read-side resolver
    if not p.exists():
        return
    try:
        fh = open(p, "r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(rec, dict):
                continue
            ts = parse_iso_ts(rec.get("ts", ""))
            if ts is None or ts < cutoff:
                continue
            yield rec
```

Điểm cốt lõi: `for line in fh` đọc từng dòng (file object là iterator), và `yield` phát record khi cần. Không hề có `read()` toàn-file. `yield` lưu state cursor (file handle, cutoff) một cách _implicit_.

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Iterator | Trong hex_agent | Trong bản distill (`telemetry_generator.py`) |
|------------------|-----------------|----------------------------------------------|
| **Aggregate** | file sink JSONL (logic chứa "tập event"), bản thân nó không phải object Python | file JSONL thật trong tmp |
| **Iterator (lazy)** | `iter_records_in_window()` — generator | `iter_records_in_window(path, days)` |
| **State cursor (implicit)** | file handle `fh` + `cutoff`, do `yield` giữ giùm | giữ nguyên |
| **Item** | `rec: dict` (một record telemetry) | `rec: dict` |
| **Filter / window** | `ts is None or ts < cutoff: continue` | giữ nguyên |
| **Fail-soft skip** | bỏ dòng unparseable / non-dict / ts xấu bằng `continue` | giữ nguyên |
| **Client** | các lens gọi `iter_records_in_window(sink, days=7)` | vòng `for rec in iter_records_in_window(...)` |

Khác case 02 (`Ledger.read()` trả `list`, materialize hết): ở đây **không** có list trung gian. Đây là biến thể "lazy iterator / generator" ở mục 2.5 bài gốc.

---

## 4. Bản rút gọn chạy được

File: [`telemetry_generator.py`](telemetry_generator.py)

**Mô phỏng:**
1. Sinh một file JSONL thật: 1000 record "recent" (trong 1 ngày qua), 1000 record "old" (30 ngày trước), và ~30 dòng rác (JSON cụt, JSON non-object, record thiếu `ts`) **rải rác giữa file** (không chỉ ở đuôi).
2. Duyệt bằng `iter_records_in_window(path, days=2)` → đúng 1000 record "recent", bỏ "old" và rác.
3. Chứng minh **lazy**: `next(gen)` kéo 1 item rồi `gen.close()` — không đọc nốt phần còn lại.
4. **So sánh bộ nhớ** bằng `tracemalloc`: đối chứng `read_all_then_filter()` (nạp hết file → O(N)) vs generator (O(1)). `assert peak_lazy < peak_eager`.
5. Fail-soft: file thiếu → generator rỗng, không raise.

**Lược bỏ so với bản thật:** `harness_paths` resolver, env knobs `HARNESS_*`, enrich `actor`/`session`, rotation 8MB + `.bak`, dedup marker, `fsync`. Trọng tâm là **lazy iteration + window filter + fail-soft**; các thứ về write-path bị bỏ. File JSONL được sinh _thật_ để generator có cái để stream.

**Bất biến / đúng đắn được `assert`:**
- Generator và đối chứng eager cho **cùng** số record (`lazy_count == len(eager) == count`).
- Chỉ record trong window lọt ra (`count == 1000`, 3 record đầu đều `"recent"`).
- Lazy dùng **ít** bộ nhớ hơn eager (`peak_lazy < peak_eager`).
- File thiếu → generator rỗng (fail-soft).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Generator chỉ duyệt được một lần.** Nếu lens cần quét file hai lần (ví dụ tính tổng rồi tính tỉ lệ), phải gọi `iter_records_in_window()` lại — đọc đĩa hai lượt. Nếu dữ liệu đủ nhỏ và cần dùng nhiều lần, materialize thành `list` một lần có khi rẻ hơn.
- **`has_next()` ẩn = đọc đĩa.** Mỗi bước generator là một dòng đọc từ file → nếu file ở mạng/đĩa chậm, iteration sẽ block. Bài gốc cảnh báo: với nguồn I/O cần cân nhắc async variant.
- **Fail-soft `continue` (bỏ _từng_ dòng hỏng) khác `break` của `Ledger.read()` (bỏ từ dòng hỏng đầu tiên trở đi).** Telemetry chấp nhận mất dữ liệu cũ (rotation), nên `continue` qua rác giữa file là hợp lý ở đây — nhưng với một audit-trace không được mất gì thì lựa chọn này SAI. Phải khớp chiến lược với giá trị của dữ liệu.
- **Đừng dùng generator nếu cần random access / đếm tổng trước khi duyệt.** Generator không biết `len()` trước — bài gốc mục 1.4: "Logic duyệt cần biết tổng số phần tử trước để planning → Iterator chỉ tốt khi có thể incremental."

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `iter_records_in_window()` dùng bộ nhớ O(1) còn `read_all_then_filter()` là O(N)? Chỗ nào trong code tạo nên khác biệt đó? (Gợi ý: so `for line in fh` với `read_text().splitlines()`.)
2. `parse_iso_ts()` trả `None` thay vì raise khi ts xấu. Nếu nó raise, điều gì xảy ra với lens đang `for rec in iter_records_in_window(...)`? Liên hệ với "contract: a telemetry write must NEVER break the hook/op it observes".
3. Generator này dùng `continue` để bỏ qua _từng_ dòng hỏng, còn `Ledger.read()` (case 02) dùng `break`. Với dữ liệu telemetry (rotation 8MB, mất dữ liệu cũ không sao), vì sao `continue` hợp lý hơn? Còn với một sổ cái tài chính thì sao?
