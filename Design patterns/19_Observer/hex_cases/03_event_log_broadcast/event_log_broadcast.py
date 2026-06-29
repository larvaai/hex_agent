"""
event_log_broadcast.py — DISTILL biến thể Observer + Event-Sourcing (frozen event, ledger, replay).

NGUỒN THẬT (đã mở đọc và đối chiếu từng dòng):
  - hex_agent/drag_from_zero/dragzero/events.py:37-43
        @dataclass(frozen=True)
        class Event:                              # Event BẤT BIẾN (frozen) — observer không sửa được
            type: EventType
            seq: int = -1                         # -1 = sentinel chưa đóng dấu
            ...
  - hex_agent/drag_from_zero/dragzero/events.py:46-91
        class EventLog:                           # SUBJECT (append-only log)
            _subs: list[Callable[[Event], None]]  # danh sách Observer (events.py:55)
            append(event):                        # = notify (events.py:58-65)
                stamped = replace(event, seq=len(self._events))   # đóng dấu seq (line 59)
                if ledger: ledger.append(stamped)  # DURABLE TRƯỚC khi observer thấy (line 60-61)
                self._events.append(stamped)                      # line 62 (sau ledger)
                for sub in self._subs: sub(stamped)               # broadcast (line 63-64)
            subscribe(fn):                         # = attach (events.py:75-76)
                self._subs.append(fn)
            replay(ledger):                        # rebuild từ đĩa (events.py:67-73)
  - hex_agent/drag_from_zero/tests/unit/test_events.py:29-36
        test_subscribe_fires_on_every_append_with_stamped_event:
            log.subscribe(seen.append); observer nhận event ĐÃ đóng dấu seq [0,1].
  - hex_agent/drag_from_zero/tests/unit/test_events.py:39-45
        test_subscribe_after_appends_only_sees_future_events:
            subscribe SAU khi đã append -> observer CHỈ thấy event tương lai (seq [1], không có [0]).
            (biến thể "cold/warm observable": late subscriber bỏ lỡ quá khứ — trừ khi replay từ ledger.)
  - hex_agent/drag_from_zero/tests/unit/test_events.py:90-93
        test_event_is_frozen_dataclass: gán event.seq=99 -> FrozenInstanceError.

Bản distill CHỈ dùng stdlib (Python 3.14). Không import hex_agent / bên thứ ba.
Thay hạ tầng nặng:
  - JSONL ledger trên đĩa -> InMemoryLedger (list trong RAM) để chạy sạch.
  - Domain agent thật -> máy trạng thái Order: Created -> Preparing -> Shipped -> Delivered.
Giữ NGUYÊN vai trò: Subject=EventLog (_subs + append=notify), Observer=Callable[[Event],None],
Event=frozen dataclass; durable-trước-khi-broadcast; late subscription; replay từ ledger.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable


class EventType(str, Enum):
    ORDER_CREATED = "order_created"
    ORDER_PREPARING = "order_preparing"
    ORDER_SHIPPED = "order_shipped"
    ORDER_DELIVERED = "order_delivered"


@dataclass(frozen=True)
class Event:
    """Event BẤT BIẾN — distill dragzero/events.py:37-43.

    frozen=True là CỐ Ý: observer A không thể mutate event để phá view của observer B.
    """

    type: EventType
    seq: int = -1                       # sentinel, đóng dấu khi append
    order_id: str | None = None
    payload: dict = field(default_factory=dict)


class InMemoryLedger:
    """FAKE ledger (thay JSONL trên đĩa). Lưu durable TRƯỚC khi observer thấy event."""

    def __init__(self) -> None:
        self._rows: list[Event] = []

    def append(self, event: Event) -> None:
        self._rows.append(event)        # ở bản thật: ghi 1 dòng JSON xuống đĩa, flush durable

    def read(self) -> list[Event]:
        return list(self._rows)


class EventLog:
    """SUBJECT append-only — distill dragzero/events.py:46-91."""

    def __init__(self, ledger: InMemoryLedger | None = None) -> None:
        self._events: list[Event] = []
        self._subs: list[Callable[[Event], None]] = []   # danh sách Observer (events.py:55)
        self._ledger = ledger

    def append(self, event: Event) -> Event:
        """= notify. Đóng dấu seq -> lưu durable -> broadcast cho từng observer."""
        stamped = replace(event, seq=len(self._events))  # events.py:59 (frozen -> tạo bản mới)
        if self._ledger is not None:
            self._ledger.append(stamped)                 # events.py:60-61 — DURABLE trước (disk không tụt sau RAM)
        self._events.append(stamped)                     # events.py:62 (sau khi đã durable)
        for sub in self._subs:                           # events.py:63-64
            sub(stamped)
        return stamped                                   # events.py:65 — trả về bản ĐÃ đóng dấu

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        self._subs.append(fn)                            # events.py:75-76 (attach)

    @classmethod
    def replay(cls, ledger: InMemoryLedger) -> "EventLog":
        """Rebuild log từ ledger (events.py:67-73). Dùng cho late subscriber bắt kịp quá khứ."""
        log = cls(ledger=ledger)
        log._events = ledger.read()                      # seq lấy từ đĩa, không đóng dấu lại
        return log

    def events(self) -> list[Event]:
        return list(self._events)                        # bản sao GIL-atomic (events.py:78-79)


# ──────────────────────────────────────────────────────────────────────────────
# Domain fake: máy trạng thái Order. Mỗi chuyển trạng thái -> append 1 Event.
# ──────────────────────────────────────────────────────────────────────────────
_FLOW = [
    EventType.ORDER_CREATED,
    EventType.ORDER_PREPARING,
    EventType.ORDER_SHIPPED,
    EventType.ORDER_DELIVERED,
]


def advance_order(log: EventLog, order_id: str) -> None:
    for t in _FLOW:
        log.append(Event(type=t, order_id=order_id, payload={"state": t.value}))


def demo() -> None:
    print("=" * 70)
    print("CASE 03 — EventLog: Observer + frozen Event + replay (distill dragzero/events.py)")
    print("=" * 70)

    ledger = InMemoryLedger()
    log = EventLog(ledger=ledger)

    # Observer 1: thanh tiến trình UI.
    progress: list[str] = []

    def ui_progress(e: Event) -> None:
        progress.append(e.type.value)
        bar = "#" * (e.seq + 1) + "." * (len(_FLOW) - e.seq - 1)
        print(f"   [UI ] seq={e.seq} {bar} {e.type.value}")

    # Observer 2: nhật ký vận hành.
    journal: list[tuple[int, str]] = []

    def ops_journal(e: Event) -> None:
        journal.append((e.seq, e.type.value))

    print("\n[1] subscribe 2 observer (UI progress + ops journal) trước khi có event.")
    log.subscribe(ui_progress)
    log.subscribe(ops_journal)

    print("[2] Đẩy đơn hàng qua 4 trạng thái: mỗi append = notify cả 2 observer.")
    advance_order(log, "order-1")

    # ── Bất biến: observer nhận event ĐÃ đóng dấu seq đơn điệu từ 0 ─────────────
    assert progress == [t.value for t in _FLOW]
    assert [s for s, _ in journal] == [0, 1, 2, 3], "seq đóng dấu đơn điệu 0..3 (events.py:59)"
    print("   UI thấy:", progress)
    print("   journal:", journal)

    # ── Bất biến durable-trước-broadcast: ledger có đủ trước khi ta đọc ─────────
    assert len(ledger.read()) == 4, "ledger lưu durable mọi event trước khi observer thấy"
    assert [e.seq for e in ledger.read()] == [0, 1, 2, 3]
    print("\n[3] Ledger (durable) đã có đủ 4 event TRƯỚC khi subscribers chạy:",
          [e.type.value for e in ledger.read()])

    # ── Bất biến: Event là frozen — observer KHÔNG thể mutate (chống corrupt view) ──
    print("\n[4] Event frozen: thử mutate event -> FrozenInstanceError (distill test_events.py:90-93).")
    snapshot = log.events()[0]
    frozen_blocked = False
    try:
        snapshot.seq = 999  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        frozen_blocked = True
    assert frozen_blocked, "frozen dataclass chặn observer sửa event chung"
    print("   -> không observer nào sửa được event; observer khác luôn thấy bản đúng.")

    # ── Biến thể: LATE SUBSCRIPTION — observer vào muộn chỉ thấy tương lai ──────
    # Distill test_events.py:39-45.
    print("\n[5] Late subscription (distill test_events.py:39-45): observer vào sau BỎ LỠ quá khứ.")
    log2 = EventLog()
    log2.append(Event(type=EventType.ORDER_CREATED, order_id="o2"))  # seq 0 — TRƯỚC khi subscribe
    late_seen: list[int] = []
    log2.subscribe(lambda e: late_seen.append(e.seq))               # vào muộn
    log2.append(Event(type=EventType.ORDER_PREPARING, order_id="o2"))  # seq 1
    assert late_seen == [1], "late subscriber chỉ thấy [1], không thấy [0]"
    print("   late observer chỉ thấy seq:", late_seen, "(bỏ lỡ seq 0 đã xảy ra trước khi nó subscribe)")

    # ── Cách chữa late subscription: REPLAY từ ledger để bắt kịp quá khứ ────────
    print("\n[6] Chữa bằng replay: dựng lại log từ ledger -> observer mới đọc được TOÀN BỘ lịch sử.")
    rebuilt = EventLog.replay(ledger)
    caught_up = [e.type.value for e in rebuilt.events()]
    assert caught_up == [t.value for t in _FLOW], "replay phục hồi đủ 4 event từ ledger"
    print("   sau replay, observer mới catch-up được:", caught_up)

    # ── ĐỐI CHỨNG: nếu Event KHÔNG frozen, observer xấu phá view observer khác ──
    print("\n[7] ĐỐI CHỨNG — Event KHÔNG frozen (dataclass thường): 1 observer mutate -> kẻ khác lãnh đủ.")

    @dataclass
    class MutableEvent:
        type: str
        payload: dict

    shared = MutableEvent(type="order_created", payload={"state": "created"})
    views: list[str] = []

    def greedy(e: MutableEvent) -> None:
        e.payload["state"] = "BI_GHI_DE"   # phá payload dùng chung

    def innocent(e: MutableEvent) -> None:
        views.append(e.payload["state"])    # đọc SAU greedy -> thấy giá trị đã bị hỏng

    for ob in (greedy, innocent):
        ob(shared)                          # cùng 1 instance, không frozen, không deepcopy
    assert views == ["BI_GHI_DE"], "không frozen: observer 'innocent' thấy state đã bị 'greedy' phá"
    print("   innocent thấy:", views[0], "-> đúng ra phải là 'created'. Frozen Event ngăn được lỗi này.")

    print("\nTẤT CẢ ASSERT PASS. EventLog = Observer + event-sourcing: frozen event, durable, replay, late-sub.")


if __name__ == "__main__":
    demo()
