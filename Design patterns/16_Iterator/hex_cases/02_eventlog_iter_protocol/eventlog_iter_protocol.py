#!/usr/bin/env python3
"""
EventLog Iterator Protocol — __iter__ cho journal append-only (distill từ hex_agent).

NGUỒN THẬT distill từ:
  - drag_from_zero/dragzero/events.py:87-88  -> EventLog.__iter__() trả iter(self._events),
                                               biến EventLog thành iterable native ('for e in log').
  - drag_from_zero/dragzero/events.py:78-85  -> events()/of_type()/types(): accessor lọc bằng
                                               cách duyệt self._events.
  - drag_from_zero/dragzero/ledger.py:47-67  -> Ledger.read(): duyệt từng dòng JSONL trên đĩa,
                                               parse mỗi dòng thành Event, BỎ QUA dòng hỏng
                                               (fail-soft) — đĩa là sự thật, log là cache.

Ý TƯỞNG: Python có sẵn iterator protocol. Một collection chỉ cần định nghĩa __iter__
là 'for x in collection' chạy được — KHÔNG cần class Iterator riêng (xem mục
'PYTHON-NATIVE' của bài gốc). Đồng thời dạy fail-soft: khi nguồn là storage ngoài
(JSONL có thể bị crash half-write), reader phải bỏ qua dòng hỏng thay vì sập cả run.

Bản distill này:
  - GIỮ NGUYÊN vai trò: Aggregate (EventLog in-memory + Ledger on-disk) chứa collection;
    Iterator (__iter__ / read()) trả Event từng cái; Client ('for e in log') xử lý mà
    không biết cấu trúc.
  - GIỮ NGUYÊN fail-soft: dòng JSONL hỏng/cụt bị bỏ, không raise.
  - LƯỢC BỎ: fsync durable, subscribe/live-view, seq-stamping phức tạp, EventType enum
    đầy đủ. Dùng file thật trong scratchpad tmp để Ledger.read() có cái để đọc.

Chạy: python3 eventlog_iter_protocol.py   (chỉ dùng stdlib, thoát code 0)
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# ITEM — Event (rút gọn từ events.py:37-43)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Event:
    type: str
    seq: int = -1
    payload: dict = field(default_factory=dict)


def event_to_dict(e: Event) -> dict:
    # ledger.py:19-20
    return {"seq": e.seq, "type": e.type, "payload": e.payload}


def event_from_dict(d: dict) -> Event:
    # ledger.py:23-30 — KeyError/ValueError nếu thiếu/sai field
    return Event(type=d["type"], seq=int(d.get("seq", -1)), payload=d.get("payload") or {})


# ─────────────────────────────────────────────────────────────────────────────
# AGGREGATE in-memory — EventLog với iterator protocol native (events.py:46-92)
# ─────────────────────────────────────────────────────────────────────────────
class EventLog:
    """Log append-only in-memory. Chỉ cần định nghĩa __iter__ + __len__ là trở thành
    iterable native — client viết 'for e in log' như với list."""

    def __init__(self) -> None:
        self._events: list[Event] = []

    def append(self, event: Event) -> Event:
        # events.py:58-65 (rút gọn: seq = số phần tử hiện có)
        stamped = Event(type=event.type, seq=len(self._events), payload=event.payload)
        self._events.append(stamped)
        return stamped

    # ── ITERATOR PROTOCOL — chìa khoá của case (events.py:87-88) ──────────────
    def __iter__(self):
        return iter(self._events)

    def __len__(self) -> int:  # events.py:90-91
        return len(self._events)

    # ── accessor lọc, bọc quanh iterator (events.py:78-85) ───────────────────
    def events(self) -> list[Event]:
        return list(self._events)

    def of_type(self, t: str) -> list[Event]:
        return [e for e in self._events if e.type == t]


# ─────────────────────────────────────────────────────────────────────────────
# AGGREGATE on-disk — Ledger: external iterator fail-soft (ledger.py:33-67)
# ─────────────────────────────────────────────────────────────────────────────
class Ledger:
    """JSONL append-only writer + reader corruption-tolerant. Đĩa là sự thật."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, event: Event) -> None:
        # ledger.py:39-45 (lược fsync — không cần cho demo)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event_to_dict(event), ensure_ascii=False)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read(self) -> list[Event]:
        """Fold ledger về list[Event]. Dòng cụt/non-dict ở đuôi (crash half-write)
        bị BỎ, không raise — mọi dòng prefix sạch đều sống. (ledger.py:47-67)"""
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
                break  # dòng cụt chỉ có thể là đuôi; mọi thứ sau đó cũng nghi ngờ
            if not isinstance(d, dict) or "type" not in d:
                break
            try:
                out.append(event_from_dict(d))
            except (KeyError, ValueError):
                break
        return out


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — reader 'ngây thơ' không fail-soft
# ─────────────────────────────────────────────────────────────────────────────
def read_naive(path: Path) -> list[Event]:
    """Đọc mọi dòng và json.loads thẳng tay. Một dòng hỏng -> nổ JSONDecodeError,
    cả run sập. Đây là điều xảy ra nếu Iterator trên storage KHÔNG fail-soft."""
    out: list[Event] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        d = json.loads(raw)          # <- không try/except: dòng hỏng làm nổ ở đây
        out.append(event_from_dict(d))
    return out


# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 72)
    print("CASE 02 — EventLog Iterator Protocol: __iter__ + Ledger fail-soft")
    print("=" * 72)

    print("\n[1] Iterator protocol native — 'for e in log' nhờ __iter__:")
    log = EventLog()
    for t in ["root_task_created", "task_started", "tool_called", "task_completed"]:
        log.append(Event(type=t))
    # Client KHÔNG biết bên trong là list — chỉ dùng for-loop:
    collected = [e.type for e in log]   # <- __iter__ làm việc này chạy được
    print(f"    Duyệt log bằng for-loop: {collected}")
    assert collected == ["root_task_created", "task_started", "tool_called", "task_completed"]
    print(f"    len(log) = {len(log)} (qua __len__)")

    # accessor lọc bọc quanh iterator
    tool_events = log.of_type("tool_called")
    assert len(tool_events) == 1 and tool_events[0].type == "tool_called"
    print(f"    of_type('tool_called') -> {len(tool_events)} event (filter bọc iterator).")

    # Bất biến: seq tăng đơn điệu theo thứ tự append (cursor chỉ tiến).
    seqs = [e.seq for e in log]
    assert seqs == sorted(seqs) == [0, 1, 2, 3], "seq phải tăng đơn điệu 0,1,2,3"
    print(f"    [ok] seq tăng đơn điệu {seqs} — iterator chỉ tiến, không lùi.")

    print("\n[2] Ledger on-disk — external iterator đọc JSONL từng dòng:")
    tmp = Path(tempfile.mkdtemp(prefix="hexcase02_")) / "events.jsonl"
    led = Ledger(tmp)
    for e in log:                      # ghi mỗi event thành 1 dòng JSONL
        led.append(e)
    print(f"    Đã ghi {len(log)} event ra {tmp}")
    replayed = led.read()              # đọc lại — 'resume = re-read'
    assert [e.type for e in replayed] == collected, "read() phải khớp những gì đã ghi"
    print(f"    read() trả {len(replayed)} event, khớp bản gốc.")

    print("\n[3] FAIL-SOFT — thêm một dòng JSONL HỎNG (crash half-write):")
    with open(tmp, "a", encoding="utf-8") as f:
        f.write('{"type": "task_failed", "seq": 4, "payl')  # dòng bị cụt giữa chừng
    print("    Đã nối thêm 1 dòng cụt (mô phỏng crash giữa lúc ghi).")

    survivors = led.read()             # ledger.py: dòng cụt ở đuôi bị bỏ, KHÔNG raise
    print(f"    Ledger.read() vẫn trả {len(survivors)} event sạch (bỏ dòng cụt).")
    assert len(survivors) == 4, "4 dòng sạch phải sống; dòng cụt bị bỏ"
    assert [e.type for e in survivors] == collected, "prefix sạch nguyên vẹn"
    print("    [ok] Iterator fail-soft: partial evidence không làm sập run đọc nó.")

    print("\n[4] ĐỐI CHỨNG — reader 'ngây thơ' không fail-soft thì sao?")
    try:
        read_naive(tmp)
        raise AssertionError("đáng lẽ phải nổ JSONDecodeError ở dòng cụt")
    except json.JSONDecodeError:
        print("    [đối chứng] read_naive() NỔ JSONDecodeError trên dòng cụt -> cả run sập.")
        print("    => Iterator trên storage ngoài BẮT BUỘC phải fail-soft (bài gốc anti-pattern #2).")

    print("\nKẾT LUẬN: Python cho không iterator protocol — chỉ cần __iter__, 'for' chạy.")
    print("Nhưng khi item đến từ đĩa, 'cách duyệt' phải gánh thêm trách nhiệm chống hỏng.")
    print("EventLog (in-memory cache) + Ledger (đĩa = sự thật) cùng đóng một Iterator hai tầng.")


if __name__ == "__main__":
    demo()
