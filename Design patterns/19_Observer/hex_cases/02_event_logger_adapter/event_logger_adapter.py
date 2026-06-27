"""
event_logger_adapter.py — DISTILL Observer áp dụng cho observability (logging/metrics).

NGUỒN THẬT (đã mở đọc và đối chiếu từng dòng):
  - hex_agent/observability/event_log.py:102-134
        def attach_to_bus(logger, bus):
            def sink(topic, payload):            # <- ĐÂY là ConcreteObserver (closure)
                logger.emit(...)                 # ghi JSONL (line 110)
                if topic == "tool.completed": logger.count("tool_calls")   # line 111-112
                elif topic == "tool.failed":  logger.count("tool_failures")# line 115-119
                ... (gom metric theo topic)
            bus.subscribe(sink)                  # line 134 — attach
    -> Observer ở đây là CLOSURE 'sink', không phải class. Đây là cách idiomatic Python:
       Subject (EventBus) chỉ cần Callable[[str, dict], None], duck typing.
  - hex_agent/observability/event_log.py:60-73
        EventLogger.emit(): seq tăng đơn điệu dưới lock (line 61-62), ghi 1 dòng JSON (line 71-72).
  - hex_agent/ui/ide/runner.py:147-148
        kernel.events.subscribe(bridge.subscriber)            # observer #1
        attach_to_bus(EventLogger(run_id=run_id), kernel.events)  # observer #2
    -> Hai observer ĐỘC LẬP cùng nghe MỘT EventBus. Đây là 1-tới-N điển hình.
  - hex_agent/tests/test_event_concurrency.py:24-41
        logger là observer; 10 thread x 25 event = 250 event đồng thời;
        sequence vẫn đơn điệu [1..251], không mất, không trùng (lock bảo vệ seq).

Bản distill CHỈ dùng stdlib (Python 3.14). Không import hex_agent / bên thứ ba.
Thay hạ tầng nặng:
  - JSONL trên đĩa  -> ghi CSV vào io.StringIO (in-memory, để chạy sạch, không đụng filesystem).
  - kernel/agent thật -> hàm fake phát các topic 'tool.completed' / 'tool.failed'.
Giữ NGUYÊN vai trò: Subject=EventBus, Observer=closure 'sink', logger gom metric + ghi durable,
lock cho seq đơn điệu, nhiều observer cùng 1 bus, đính kèm/gỡ động.
"""
from __future__ import annotations

import copy
import csv
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

Subscriber = Callable[[str, dict[str, Any]], None]


class EventBus:
    """Subject — bản rút gọn của core/events.py (đã có case 01)."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = threading.RLock()

    def subscribe(self, fn: Subscriber) -> Subscriber:
        with self._lock:
            self._subscribers.append(fn)
        return fn  # trả về để có thể unsubscribe sau (tiện cho demo gỡ động)

    def unsubscribe(self, fn: Subscriber) -> None:
        with self._lock:
            if fn in self._subscribers:
                self._subscribers.remove(fn)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        with self._lock:
            subs = tuple(self._subscribers)
        data = copy.deepcopy(payload or {})
        for fn in subs:
            try:
                fn(topic, copy.deepcopy(data))
            except Exception:
                pass


class EventLogger:
    """ConcreteObserver-state: ghi durable (CSV in-memory) + gom metric.

    Distill EventLogger ở observability/event_log.py:41-73 (chỉ giữ phần Observer cần):
      - seq đơn điệu dưới lock (event_log.py:61-62)
      - emit() ghi 1 dòng durable (event_log.py:71-72)
      - count() cộng dồn metric dưới lock (event_log.py:75-78)
    """

    METRICS = ("tool_calls", "tool_failures")

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.seq = 0
        self.metrics: dict[str, int] = {k: 0 for k in self.METRICS}
        self._buf = io.StringIO()
        self._writer = csv.writer(self._buf)
        self._writer.writerow(["sequence", "topic", "tool"])  # header
        # "run_started" như event_log.py:58 — chứng minh logger có state ngay khi tạo.
        self._emit_row("run_started", "")

    def _emit_row(self, topic: str, tool: str) -> int:
        with self._lock:
            self.seq += 1
            self._writer.writerow([self.seq, topic, tool])  # ghi durable (đây = JSONL ở bản thật)
            return self.seq

    def emit(self, topic: str, tool: str) -> int:
        return self._emit_row(topic, tool)

    def count(self, metric: str, n: int = 1) -> None:
        with self._lock:
            if metric in self.metrics:
                self.metrics[metric] += n

    def csv_text(self) -> str:
        return self._buf.getvalue()

    def rows(self) -> list[list[str]]:
        return list(csv.reader(io.StringIO(self.csv_text())))


def attach_to_bus(logger: EventLogger, bus: EventBus) -> Subscriber:
    """Tạo Observer (closure 'sink') và attach vào bus.

    Distill observability/event_log.py:102-134 — closure-as-observer:
      sink quan sát (topic, payload), lọc theo loại event, gom metric, ghi durable.
    Subject KHÔNG biết gì về logger; nó chỉ thấy 1 Callable[[str, dict], None].
    """

    def sink(topic: str, payload: dict[str, Any]) -> None:        # event_log.py:105
        tool = str(payload.get("tool", ""))
        logger.emit(topic, tool)                                  # event_log.py:110
        if topic == "tool.completed":                             # event_log.py:111-112
            logger.count("tool_calls")
        elif topic == "tool.failed":                              # event_log.py:115-117
            logger.count("tool_calls")
            logger.count("tool_failures")

    bus.subscribe(sink)                                           # event_log.py:134
    return sink


def fake_agent_run(bus: EventBus) -> None:
    """FAKE kernel: phát chuỗi tool event như một lượt chạy agent thật."""
    bus.publish("tool.completed", {"tool": "fs_read"})
    bus.publish("tool.completed", {"tool": "fs_write"})
    bus.publish("tool.failed", {"tool": "terminal_run", "error": "exit 1"})
    bus.publish("tool.completed", {"tool": "fs_list"})


def demo() -> None:
    print("=" * 70)
    print("CASE 02 — EventLogger: closure-as-observer (distill observability/event_log.py)")
    print("=" * 70)

    bus = EventBus()
    logger = EventLogger()

    print("\n[1] attach_to_bus(logger, bus): tạo closure 'sink' rồi subscribe. Subject mù về logger.")
    sink = attach_to_bus(logger, bus)

    # Observer thứ 2 độc lập trên CÙNG bus — như runner.py:147-148 (bridge + logger).
    print("[2] Thêm observer thứ 2 (UI live counter) trên CÙNG bus — 1-tới-N (như runner.py:147-148).")
    ui_seen: list[str] = []
    bus.subscribe(lambda topic, payload: ui_seen.append(topic))

    print("[3] Chạy 1 lượt agent fake: 3 tool.completed + 1 tool.failed.")
    fake_agent_run(bus)

    assert logger.metrics["tool_calls"] == 4, "4 tool call (3 ok + 1 fail)"
    assert logger.metrics["tool_failures"] == 1, "đúng 1 fail"
    assert len(ui_seen) == 4, "observer UI cũng nhận đủ 4 event độc lập"
    print("   metrics:", logger.metrics, "| UI observer thấy:", ui_seen)

    # ── Durability: dòng đã ghi ra "đĩa" (CSV) — như JSONL ở bản thật ──────────
    rows = logger.rows()
    # rows[0]=header, rows[1]=run_started, rows[2..5]=4 event
    assert rows[0] == ["sequence", "topic", "tool"]
    assert rows[1][1] == "run_started"
    assert [r[1] for r in rows[2:]] == ["tool.completed", "tool.completed", "tool.failed", "tool.completed"]
    seqs = [int(r[0]) for r in rows[1:]]
    assert seqs == list(range(1, 6)), "seq đơn điệu 1..5, không nhảy cóc"
    print("\n[4] Durable CSV (mỗi dòng = 1 event đã ghi):")
    for line in logger.csv_text().strip().splitlines():
        print("   " + line)

    # ── Gỡ động: unsubscribe -> observer ngừng nhận event ──────────────────────
    print("\n[5] Gỡ observer động: unsubscribe(sink) -> logger không nhận event mới nữa.")
    bus.unsubscribe(sink)
    before = logger.metrics["tool_calls"]
    bus.publish("tool.completed", {"tool": "fs_read"})
    assert logger.metrics["tool_calls"] == before, "đã gỡ thì không cộng thêm"
    print("   tool_calls vẫn =", logger.metrics["tool_calls"], "(observer đã rời bus)")

    # ── Concurrency: nhiều thread publish, seq vẫn đơn điệu, không mất event ────
    # Distill test_event_concurrency.py:24-41 (10 thread x 25 event = 250).
    print("\n[6] Concurrency (distill test_event_concurrency.py:24-41): 10 thread x 25 event.")
    bus_c = EventBus()
    logger_c = EventLogger()
    attach_to_bus(logger_c, bus_c)

    def worker(w: int) -> None:
        for i in range(25):
            bus_c.publish("tool.completed", {"tool": f"w{w}-{i}"})

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(worker, range(10)))

    rows_c = logger_c.rows()
    body = rows_c[1:]  # bỏ header
    assert len(body) == 251, f"1 run_started + 250 event = 251, thực tế {len(body)}"
    seqs_c = [int(r[0]) for r in body]
    assert seqs_c == list(range(1, 252)), "seq đơn điệu liên tục, không trùng/không mất dưới đua thread"
    assert logger_c.metrics["tool_calls"] == 250
    print("   tổng dòng durable:", len(body), "| seq cuối:", seqs_c[-1], "| tool_calls:", logger_c.metrics["tool_calls"])

    # ── ĐỐI CHỨNG: nếu seq không khoá lock thì đua thread làm mất/đụng số ───────
    print("\n[7] ĐỐI CHỨNG — bộ đếm KHÔNG khoá lock dưới đa luồng (race condition):")
    racy = {"n": 0}

    def racy_inc() -> None:
        for _ in range(2000):
            cur = racy["n"]      # đọc
            time.sleep(0)        # NHƯỜNG lịch: ép GIL chuyển thread giữa đọc và ghi
            racy["n"] = cur + 1  # ghi — không atomic: thread khác đã ghi đè -> mất cập nhật

    n_threads = 8
    per_thread = 2000
    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        list(pool.map(lambda _: racy_inc(), range(n_threads)))
    expected = n_threads * per_thread
    lost = expected - racy["n"]
    # time.sleep(0) cưỡng bức context switch giữa read-modify-write -> race lộ ra ổn định:
    # gần như luôn LỆCH (mất cập nhật). Vẫn xử lý cả 2 nhánh để không bao giờ crash.
    if racy["n"] == expected:
        verdict = "BẰNG (hiếm: lịch luồng tình cờ không xen kẽ lần này)"
    else:
        verdict = f"LỆCH {lost} đơn vị = mất cập nhật do thiếu lock (read-modify-write bị xen kẽ)"
    print(f"   kỳ vọng {expected}, thực tế {racy['n']} -> {verdict}")
    print("   => EventLogger.count()/emit() khoá RLock chính là để tránh đúng lỗi này.")

    print("\nTẤT CẢ ASSERT PASS. Closure 'sink' là Observer; logger gom metric + ghi durable an toàn đa luồng.")


if __name__ == "__main__":
    demo()
