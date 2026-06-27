#!/usr/bin/env python3
"""
Lazy Generator Iterator — iter_records_in_window() cho pagination/streaming
(distill từ hex_agent).

NGUỒN THẬT distill từ:
  - harness/scripts/telemetry_paths.py:54-84 -> iter_records_in_window(sink_name, days):
        generator YIELD từng record dict khớp time-window. Stream line-by-line, O(1)
        bộ nhớ bất kể file lớn cỡ nào (comment dòng 65: "O(1) memory regardless of
        sink size"). Fail-soft: bỏ qua dòng unparseable, dòng non-object, ts thiếu/sai.
  - harness/scripts/telemetry_paths.py:41-51 -> parse_iso_ts(): parse ISO ts, trả None
        nếu không parse được (không crash lens).

Ý TƯỞNG: collection (file telemetry 8MB) quá lớn/đắt để materialize. Generator trả
một item mỗi lần khi cần (lazy) → bộ nhớ O(1). Đây là 'iterator như abstraction trên
I/O' (ví dụ 3 của bài gốc — lazy iterator cho paginated content). 'yield' lưu state
cursor (file handle, cutoff) một cách implicit.

Bản distill này:
  - GIỮ NGUYÊN: generator stream-line-by-line, lọc theo time-window, fail-soft (bỏ
    dòng hỏng / non-dict / ts xấu), bộ nhớ O(1).
  - GIỮ NGUYÊN: parse_iso_ts trả None thay vì raise.
  - LƯỢC BỎ: harness_paths resolver, env knobs HARNESS_*, actor enrichment, rotation,
    dedup, fsync. Dùng file thật trong tmp, sinh sẵn N record với ts trải nhiều ngày.

Chạy: python3 telemetry_generator.py   (chỉ dùng stdlib, thoát code 0)
"""
from __future__ import annotations

import json
import tempfile
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


# ─────────────────────────────────────────────────────────────────────────────
# parse_iso_ts — trả None thay vì raise (telemetry_paths.py:41-51)
# ─────────────────────────────────────────────────────────────────────────────
def parse_iso_ts(raw):
    """Parse ISO-8601 ts thành aware datetime (UTC nếu naive), hoặc None nếu không
    parse được. Một ts xấu không được làm sập lens — chỉ bị loại khỏi window."""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# ITERATOR — generator lazy (telemetry_paths.py:54-84)
# ─────────────────────────────────────────────────────────────────────────────
def iter_records_in_window(path: Path, days: int) -> Iterator[dict]:
    """Yield từng record dict trong file có ts nằm trong 'days' ngày gần nhất.

    State cursor (file handle + cutoff) được 'yield' lưu IMPLICIT — không cần class.
    Đọc line-by-line: O(1) bộ nhớ dù file bao nhiêu MB. Fail-soft: bỏ qua
    file thiếu, dòng unparseable, dòng NON-OBJECT, record có ts thiếu/sai."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if not path.exists():
        return  # file thiếu -> generator rỗng (không raise)
    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh:
        for line in fh:                       # <- stream từng dòng, KHÔNG nạp cả file
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue                       # dòng hỏng -> bỏ qua (không break, không raise)
            if not isinstance(rec, dict):
                continue                       # dòng JSON non-object -> bỏ qua
            ts = parse_iso_ts(rec.get("ts", ""))
            if ts is None or ts < cutoff:
                continue                       # ts xấu hoặc ngoài window -> bỏ qua
            yield rec                          # chỉ phát record hợp lệ + trong window


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — đọc EAGER toàn bộ file rồi mới lọc
# ─────────────────────────────────────────────────────────────────────────────
def read_all_then_filter(path: Path, days: int) -> list[dict]:
    """Cách KHÔNG dùng lazy iterator: nạp HẾT file vào RAM, parse hết, rồi lọc.
    Đúng kết quả, nhưng bộ nhớ O(N) — file 8MB nạp 8MB. Với file lớn -> nổ RAM."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()  # <- nạp HẾT
    recs = []
    for line in lines:
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(rec, dict):
            continue
        ts = parse_iso_ts(rec.get("ts", ""))
        if ts is None or ts < cutoff:
            continue
        recs.append(rec)
    return recs


# ─────────────────────────────────────────────────────────────────────────────
def make_sink(path: Path, n_recent: int, n_old: int, n_corrupt: int) -> None:
    """Sinh một file telemetry JSONL: n_recent record trong 1 ngày qua, n_old record
    từ 30 ngày trước, n_corrupt dòng rác. Trộn lẫn để generator phải lọc."""
    now = datetime.now(timezone.utc)
    lines: list[str] = []
    for i in range(n_recent):
        ts = (now - timedelta(hours=i % 20)).isoformat(timespec="seconds")
        lines.append(json.dumps({"event": "recent", "i": i, "ts": ts}))
    for i in range(n_old):
        ts = (now - timedelta(days=30, hours=i % 20)).isoformat(timespec="seconds")
        lines.append(json.dumps({"event": "old", "i": i, "ts": ts}))
    for i in range(n_corrupt):
        if i % 3 == 0:
            lines.append('{"event": "torn", "ts": "2026-')   # JSON cụt
        elif i % 3 == 1:
            lines.append('["not", "an", "object"]')          # JSON hợp lệ nhưng non-object
        else:
            lines.append(json.dumps({"event": "no_ts"}))     # thiếu ts
    # trộn cho thực tế: rác nằm rải rác giữa file, không chỉ ở đuôi
    interleaved: list[str] = []
    for idx, ln in enumerate(lines):
        interleaved.append(ln)
        if idx % 50 == 49 and n_corrupt:
            interleaved.append('{"event": "torn-mid", "ts": "2026-')  # rác giữa file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(interleaved) + "\n", encoding="utf-8")


def demo() -> None:
    print("=" * 72)
    print("CASE 03 — Lazy Generator Iterator: iter_records_in_window()")
    print("=" * 72)

    tmp = Path(tempfile.mkdtemp(prefix="hexcase03_")) / "usage.jsonl"

    print("\n[1] Sinh file telemetry: 1000 recent + 1000 old + dòng rác:")
    make_sink(tmp, n_recent=1000, n_old=1000, n_corrupt=30)
    size = tmp.stat().st_size
    print(f"    File: {tmp}")
    print(f"    Kích thước: {size:,} bytes ({size/1024:.1f} KB)")

    print("\n[2] DÙNG lazy generator — yield từng record trong window 2 ngày:")
    count = 0
    first_three = []
    for rec in iter_records_in_window(tmp, days=2):   # <- không nạp cả file
        count += 1
        if len(first_three) < 3:
            first_three.append(rec["event"])
    print(f"    Số record trong window: {count}")
    print(f"    3 record đầu (chỉ 'recent', không 'old'): {first_three}")
    assert count == 1000, "Chỉ 1000 record recent lọt window; old + rác bị loại"
    assert all(e == "recent" for e in first_three), "Window 2 ngày chỉ chứa 'recent'"
    print("    [ok] Generator lọc đúng: chỉ record trong window, rác/old bị bỏ.")

    print("\n[3] Bất biến lazy — chỉ tính khi cần (consume 1 phần tử rồi dừng):")
    gen = iter_records_in_window(tmp, days=2)
    one = next(gen)                 # chỉ kéo 1 item; generator chưa hề đọc hết file
    assert one["event"] == "recent"
    gen.close()                     # dừng giữa chừng — không lãng phí đọc phần còn lại
    print(f"    Kéo 1 record rồi close() — đọc 1, KHÔNG đọc nốt {count - 1} record còn lại.")
    print("    [ok] Lazy: client kiểm soát timing, dừng sớm tuỳ ý (mục 2.5 bài gốc).")

    print("\n[4] So sánh bộ nhớ: lazy generator vs đọc-hết-rồi-lọc (đối chứng):")
    # Đo peak khi đọc HẾT file vào list (O(N)).
    tracemalloc.start()
    eager = read_all_then_filter(tmp, days=2)
    _, peak_eager = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Đo peak khi chỉ duyệt qua generator, không giữ record nào (O(1)).
    tracemalloc.start()
    lazy_count = sum(1 for _ in iter_records_in_window(tmp, days=2))
    _, peak_lazy = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"    Đọc-hết-rồi-lọc : peak ~{peak_eager:,} bytes (giữ {len(eager)} record trong RAM)")
    print(f"    Lazy generator  : peak ~{peak_lazy:,} bytes (không giữ record nào)")
    assert lazy_count == len(eager) == count, "Hai cách cho CÙNG kết quả"
    assert peak_lazy < peak_eager, "Lazy phải dùng ÍT bộ nhớ hơn đọc-hết"
    print(f"    [ok] Cùng kết quả ({count} record) nhưng lazy nhẹ hơn ~{peak_eager/max(peak_lazy,1):.0f}x.")

    print("\n[5] Fail-soft — file rỗng/thiếu cho generator rỗng, không raise:")
    missing = tmp.parent / "khong_ton_tai.jsonl"
    assert list(iter_records_in_window(missing, days=2)) == [], "File thiếu -> generator rỗng"
    print("    [ok] File thiếu -> generator rỗng, không nổ. (telemetry phải fail-soft).")

    print("\nKẾT LUẬN: 'yield' biến hàm thành Iterator, lưu state cursor implicit.")
    print("Collection 8MB không bao giờ nạp hết — mỗi record được phát khi cần, O(1) RAM.")
    print("Đây là iterator như abstraction trên I/O latency (ví dụ 3, bài gốc).")


if __name__ == "__main__":
    demo()
