"""
event_bus_core.py — DISTILL của Observer pattern "thuần khiết" nhất trong hex_agent.

NGUỒN THẬT (đã mở đọc và đối chiếu từng dòng):
  - hex_agent/core/events.py:11-31
        class EventBus:                          # Subject (Publisher)
            _subscribers: list[Subscriber]       # danh sách Observer
            subscribe(fn)                        # attach
            publish(topic, payload)              # notify
        Điểm tinh tế:
          * line 24-25 + 28: deepcopy payload -> mỗi observer nhận BẢN TÁCH RỜI,
            observer này mutate không ảnh hưởng observer kia.
          * line 29-31: try/except nuốt exception -> 1 observer hỏng KHÔNG kéo
            sập cả runtime ("An observer must never break the runtime").
          * line 16 + 19 + 23: threading.RLock -> subscribe/publish an toàn đa luồng.
  - hex_agent/tests/test_event_concurrency.py:9-21
        test_subscribers_receive_detached_payloads:
            2 observer (mutate + append), chứng minh deepcopy chặn lan truyền mutation.

Bản distill này CHỈ dùng stdlib (Python 3.14). Không import hex_agent, không bên thứ ba.
Hạ tầng nặng đã được thay bằng fake tối thiểu:
  - "kernel/agent phát event" -> một hàm giả lập phát hiện thay đổi file (FileWatcher).
  - Observer thật (EventLogger, KernelEventBridge) -> 2 observer demo: log + đếm.
Giữ NGUYÊN vai trò pattern: Subject giữ list, notify = lặp + gọi, deepcopy, exception isolation, RLock.
"""
from __future__ import annotations

import copy
import threading
from typing import Any, Callable

# Observer interface bằng duck typing: bất kỳ Callable[[str, dict], None] nào cũng là Observer.
# (Đúng như Subscriber = Callable[[str, dict[str, Any]], None] trong core/events.py:8)
Subscriber = Callable[[str, dict[str, Any]], None]


class EventBus:
    """SUBJECT: pub/sub tối thiểu, thread-safe, tách rời payload, cô lập lỗi observer.

    Distill trung thực core/events.py:11-31.
    """

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []          # danh sách Observer
        self._lock = threading.RLock()                    # core/events.py:16

    def subscribe(self, fn: Subscriber) -> None:
        """attach() — thêm Observer. Subject KHÔNG biết fn là ai cụ thể."""
        with self._lock:                                  # core/events.py:19
            self._subscribers.append(fn)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        """notify() — broadcast (topic, payload) tới mọi Observer."""
        with self._lock:
            # Chụp ảnh snapshot dưới lock rồi NHẢ lock trước khi gọi observer:
            # observer có thể subscribe() ngay trong update() mà không kẹt lock.
            subscribers = tuple(self._subscribers)        # core/events.py:24
        data = copy.deepcopy(payload or {})               # core/events.py:25
        for fn in subscribers:
            try:
                fn(topic, copy.deepcopy(data))            # core/events.py:28 — bản tách rời cho từng observer
            except Exception:
                # core/events.py:29-31 — "An observer must never break the runtime."
                pass


# ──────────────────────────────────────────────────────────────────────────────
# FAKE hạ tầng: nguồn phát event. Trong hex_agent đây là kernel/orchestrator.
# Ở đây ta giả lập một "FileWatcher" phát hiện file đổi rồi publish.
# ──────────────────────────────────────────────────────────────────────────────
class FileWatcher:
    """ConcreteSubject-ish: state đổi -> publish lên bus. Không biết ai đang nghe."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def file_changed(self, path: str, size: int) -> None:
        self._bus.publish("fs.changed", {"path": path, "size": size, "meta": {"dirty": True}})


def demo() -> None:
    print("=" * 70)
    print("CASE 01 — EventBus: lõi Observer thread-safe (distill core/events.py)")
    print("=" * 70)

    bus = EventBus()
    watcher = FileWatcher(bus)

    # Observer 1: logger — chỉ in ra.
    log_lines: list[str] = []

    def logger(topic: str, payload: dict[str, Any]) -> None:
        line = f"[LOG] {topic}: {payload['path']} ({payload['size']} bytes)"
        log_lines.append(line)
        print("   " + line)

    # Observer 2: counter — đếm số event.
    counter = {"n": 0}

    def count(topic: str, payload: dict[str, Any]) -> None:
        counter["n"] += 1

    print("\n[1] Đăng ký 2 observer (logger + counter) bằng bus.subscribe(...).")
    bus.subscribe(logger)
    bus.subscribe(count)

    print("[2] Watcher phát hiện 2 file đổi -> publish. Subject KHÔNG gọi tên observer.")
    watcher.file_changed("src/app.py", 120)
    watcher.file_changed("README.md", 42)
    assert counter["n"] == 2, "counter phải nhận đủ 2 event"
    assert len(log_lines) == 2

    # ── Open/Closed: THÊM observer mới mà KHÔNG sửa Subject ─────────────────────
    print("\n[3] Open/Closed: thêm observer thứ 3 (cảnh báo file lớn) — KHÔNG sửa EventBus.")
    big_files: list[str] = []

    def big_file_alarm(topic: str, payload: dict[str, Any]) -> None:
        if payload["size"] > 100:
            big_files.append(payload["path"])
            print(f"   [ALARM] file lớn: {payload['path']}")

    bus.subscribe(big_file_alarm)
    watcher.file_changed("data/model.bin", 999)
    assert big_files == ["data/model.bin"], "observer mới phải hoạt động ngay"
    assert counter["n"] == 3

    # ── Bất biến 1: payload tách rời (deepcopy) — distill test_event_concurrency.py:9-21 ──
    print("\n[4] Bất biến deepcopy: 1 observer mutate payload KHÔNG ảnh hưởng observer khác.")
    observed: list[dict] = []

    def mutator(topic: str, payload: dict[str, Any]) -> None:
        payload["meta"]["dirty"] = "DA_BI_SUA"   # cố tình phá

    def reader(topic: str, payload: dict[str, Any]) -> None:
        observed.append(payload)

    bus2 = EventBus()
    bus2.subscribe(mutator)
    bus2.subscribe(reader)
    original = {"path": "x", "size": 1, "meta": {"dirty": True}}
    bus2.publish("fs.changed", original)
    assert original["meta"]["dirty"] is True, "payload gốc của caller phải nguyên vẹn"
    assert observed[0]["meta"]["dirty"] is True, "observer reader phải thấy bản nguyên vẹn"
    print("   payload gốc:", original["meta"], "| reader thấy:", observed[0]["meta"], "-> KHÔNG bị mutator phá")

    # ── Bất biến 2: exception isolation — 1 observer hỏng không kéo sập cái sau ──
    print("\n[5] Exception isolation: observer hỏng (raise) KHÔNG chặn observer sau nó.")
    order: list[str] = []

    def broken(topic: str, payload: dict[str, Any]) -> None:
        order.append("broken-vào")
        raise RuntimeError("observer này nổ tung")

    def survivor(topic: str, payload: dict[str, Any]) -> None:
        order.append("survivor-chạy")

    bus3 = EventBus()
    bus3.subscribe(broken)
    bus3.subscribe(survivor)
    bus3.publish("anything", {})
    assert order == ["broken-vào", "survivor-chạy"], "survivor vẫn phải chạy dù broken nổ"
    print("   thứ tự thực thi:", order, "-> survivor vẫn chạy")

    # ── ĐỐI CHỨNG: nếu KHÔNG dùng pattern (gọi trực tiếp, không cô lập lỗi) ──────
    print("\n[6] ĐỐI CHỨNG — không có EventBus: Subject gọi thẳng từng observer, không try/except.")

    def naive_publish(observers: list[Subscriber], topic: str, payload: dict) -> list[str]:
        ran = []
        for ob in observers:          # không snapshot, không deepcopy, không try/except
            ob(topic, payload)        # 1 cái nổ -> exception bay ra, các cái sau KHÔNG chạy
            ran.append("ok")
        return ran

    crashed = False
    try:
        naive_publish([broken, survivor], "x", {})
    except RuntimeError:
        crashed = True
    assert crashed, "cách ngây thơ: exception thoát ra ngoài, survivor không bao giờ chạy"
    print("   -> Không pattern: 'broken' nổ làm cả vòng lặp chết, survivor bị bỏ qua. Đó là cái giá.")

    print("\nTẤT CẢ ASSERT PASS. EventBus = Observer thuần: list + notify + deepcopy + cô lập lỗi.")


if __name__ == "__main__":
    demo()
