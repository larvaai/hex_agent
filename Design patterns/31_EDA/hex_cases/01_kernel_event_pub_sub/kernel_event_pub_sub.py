"""
Case 01 — Core Kernel Event Publishing & Multi-Subscriber Dispatch (EDA).

Bản DISTILL trung thực của cơ chế pub-sub trong hex_agent.

NGUỒN THẬT (đã mở kiểm chứng):
  - core/events.py:11-31
        class EventBus: subscribe(fn) + publish(topic, payload). Snapshot list
        subscriber dưới lock (dòng 24), deepcopy payload cho từng subscriber
        (dòng 25-28), nuốt exception của mỗi subscriber (dòng 29-31) để 1
        observer hỏng không làm sập runtime hay các observer khác.
  - core/kernel.py:123-126   -> publish "tool.requested" TRƯỚC khi chạy tool.
  - core/kernel.py:140-150   -> publish "tool.failed" khi tool ngoài scope.
  - core/kernel.py:179-190   -> publish "middleware.skipped" khi advisory mw raise.
  - core/kernel.py:215-224   -> publish "tool.completed"/"tool.failed" SAU khi chạy.
  - observability/event_log.py:102-134 -> attach_to_bus: 1 subscriber ghi JSONL + đếm metric.
  - tests_audit/test_core_edges_rigor.py:523-578 -> test deepcopy/snapshot/concurrency của bus.

Ý TƯỞNG MÔ PHỎNG:
  1. Tạo 1 EventBus tối giản (giống core/events.py).
  2. Subscribe 3 handler ĐỘC LẬP: logging, metrics, audit.
  3. Producer (giống AgentKernel.execute_tool) phát "tool.requested" rồi
     "tool.completed" — KHÔNG biết ai nghe, không biết có bao nhiêu subscriber.
  4. Chứng minh: cả 3 handler đều fire; mỗi handler nhận payload deepcopy riêng;
     1 handler ném exception KHÔNG làm chết bus hay handler khác.

LƯỢC BỎ so với bản thật: không có middleware chain, registry, CapabilityResult,
lineage đầy đủ, ghi file JSONL. Chỉ giữ đúng VAI: Producer -> Bus -> nhiều Consumer,
fire-and-forget, cô lập lỗi, payload tách rời.

Chỉ dùng thư viện chuẩn Python 3.14.
"""
from __future__ import annotations

import copy
import threading
from typing import Any, Callable

# Chữ ký handler thuần hàm — y hệt core/events.py:8 (Subscriber alias).
Subscriber = Callable[[str, dict[str, Any]], None]


# ──────────────────────────────────────────────────────────────────────────
# BUS — distill của core/events.py:11-31
# ──────────────────────────────────────────────────────────────────────────
class EventBus:
    """Pub/sub tối giản, thread-safe. Producer publish(topic, payload); mọi
    subscriber đã đăng ký đều nhận. Fire-and-forget: không await, không thu kết quả."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = threading.RLock()

    def subscribe(self, fn: Subscriber) -> None:
        with self._lock:
            self._subscribers.append(fn)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        # Snapshot danh sách subscriber DƯỚI lock trước khi giao (tránh race
        # iterate-trong-khi-register) — đúng core/events.py:23-24.
        with self._lock:
            subscribers = tuple(self._subscribers)
        data = copy.deepcopy(payload or {})
        for fn in subscribers:
            try:
                # Mỗi subscriber nhận MỘT deepcopy riêng — mutate của người này
                # không ảnh hưởng người kia (core/events.py:28).
                fn(topic, copy.deepcopy(data))
            except Exception:
                # "An observer must never break the runtime." (core/events.py:30)
                pass


# ──────────────────────────────────────────────────────────────────────────
# CONSUMERS — 3 handler độc lập, mỗi handler 1 trách nhiệm
# ──────────────────────────────────────────────────────────────────────────
class LoggingHandler:
    """Consumer 1: ghi lại dòng log con người đọc được."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, topic: str, payload: dict[str, Any]) -> None:
        tool = payload.get("tool", "?")
        self.lines.append(f"[log] {topic} tool={tool}")


class MetricsHandler:
    """Consumer 2: đếm số tool gọi / số tool fail (giống observability metrics)."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {"tool_calls": 0, "tool_failures": 0}

    def __call__(self, topic: str, payload: dict[str, Any]) -> None:
        if topic == "tool.completed":
            self.counts["tool_calls"] += 1
        elif topic == "tool.failed":
            self.counts["tool_calls"] += 1
            self.counts["tool_failures"] += 1


class AuditHandler:
    """Consumer 3: lưu bản ghi audit BẤT BIẾN. Cố tình mutate payload nhận được
    để chứng minh deepcopy bảo vệ các subscriber khác."""

    def __init__(self) -> None:
        self.trail: list[dict[str, Any]] = []

    def __call__(self, topic: str, payload: dict[str, Any]) -> None:
        payload["seen_by_audit"] = True  # mutate bản copy của riêng audit
        self.trail.append({"topic": topic, "request_id": payload.get("request_id")})


class BrokenHandler:
    """Consumer hỏng: luôn ném exception. Bus phải nuốt nó, các handler khác vẫn chạy."""

    def __init__(self) -> None:
        self.attempts = 0

    def __call__(self, topic: str, payload: dict[str, Any]) -> None:
        self.attempts += 1
        raise RuntimeError("observer này bị bug")


# ──────────────────────────────────────────────────────────────────────────
# PRODUCER — distill của AgentKernel.execute_tool (core/kernel.py:106-225)
# ──────────────────────────────────────────────────────────────────────────
class MiniKernel:
    """Producer. execute_tool() phát fact "tool.requested" rồi "tool.completed"/
    "tool.failed". KHÔNG hề gọi handler trực tiếp, KHÔNG biết có subscriber nào."""

    def __init__(self, bus: EventBus, *, allowed: set[str]) -> None:
        self.events = bus
        self._allowed = allowed
        self._counter = 0

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        self._counter += 1
        request_id = f"req-{self._counter}"
        # (1) Phát fact "đã có yêu cầu gọi tool" — kernel.py:123-126.
        self.events.publish(
            "tool.requested",
            {"tool": tool_name, "request_id": request_id, "args": args or {}},
        )

        # (2) Scope block: tool ngoài quyền -> phát "tool.failed" (KHÔNG raise) — kernel.py:140-150.
        if tool_name not in self._allowed:
            envelope = {"ok": False, "tool": tool_name, "error": f"ngoài scope: {tool_name}"}
            self.events.publish(
                "tool.failed",
                {"tool": tool_name, "request_id": request_id, "ok": False, "error": envelope["error"]},
            )
            return envelope

        # (3) Chạy "tool" (fake) rồi phát kết quả — kernel.py:215-224.
        envelope = {"ok": True, "tool": tool_name, "data": {"echo": args or {}}}
        self.events.publish(
            "tool.completed" if envelope["ok"] else "tool.failed",
            {"tool": tool_name, "request_id": request_id, "ok": True, "error": None},
        )
        return envelope


# ──────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — "khi KHÔNG dùng EDA"
# ──────────────────────────────────────────────────────────────────────────
class TightlyCoupledKernel:
    """Phản ví dụ: producer GỌI TRỰC TIẾP từng consumer. Muốn thêm 1 observer
    mới phải SỬA producer (vi phạm OCP). 1 observer ném lỗi -> sập cả request."""

    def __init__(self, logging_handler, metrics_handler, audit_handler) -> None:
        self._log = logging_handler
        self._metrics = metrics_handler
        self._audit = audit_handler

    def execute_tool(self, tool_name: str) -> dict[str, Any]:
        payload = {"tool": tool_name, "request_id": "x"}
        # Producer phải biết TỪNG consumer và gọi tay từng cái:
        self._log("tool.completed", dict(payload))
        self._metrics("tool.completed", dict(payload))
        self._audit("tool.completed", dict(payload))  # nếu cái này raise -> nổ luôn
        return {"ok": True, "tool": tool_name}


def demo() -> None:
    print("=" * 72)
    print("CASE 01 — Kernel Event Pub/Sub: 1 producer, nhiều consumer độc lập")
    print("=" * 72)

    bus = EventBus()
    logging_h = LoggingHandler()
    metrics_h = MetricsHandler()
    audit_h = AuditHandler()
    broken_h = BrokenHandler()

    print("\n[Bước 1] Subscribe 4 handler ĐỘC LẬP vào cùng 1 bus")
    print("         (logging, metrics, audit, + 1 handler cố tình hỏng)")
    bus.subscribe(logging_h)
    bus.subscribe(metrics_h)
    bus.subscribe(audit_h)
    bus.subscribe(broken_h)

    kernel = MiniKernel(bus, allowed={"fs_read", "fs_write"})
    print("\n[Bước 2] Producer (kernel) KHÔNG biết có bao nhiêu subscriber.")
    print("         Nó chỉ publish fact lên bus.")

    print("\n[Bước 3] execute_tool('fs_read')  -> phát tool.requested + tool.completed")
    kernel.execute_tool("fs_read", {"path": "a.txt"})

    print("[Bước 3] execute_tool('danger')   -> ngoài scope -> phát tool.failed")
    kernel.execute_tool("danger", {"rm": "-rf"})

    print("\n[Bước 4] Kết quả fan-out tới từng consumer:")
    print("  - logging.lines :")
    for line in logging_h.lines:
        print("      " + line)
    print(f"  - metrics.counts: {metrics_h.counts}")
    print(f"  - audit.trail   : {audit_h.trail}")
    print(f"  - broken.attempts (đã bị gọi & nuốt lỗi): {broken_h.attempts}")

    # ── ASSERT: bất biến của EDA ──────────────────────────────────────────
    # (a) Cả 3 handler "lành" đều fire cho mỗi event (4 event: 2 requested + 1 completed + 1 failed).
    assert logging_h.lines == [
        "[log] tool.requested tool=fs_read",
        "[log] tool.completed tool=fs_read",
        "[log] tool.requested tool=danger",
        "[log] tool.failed tool=danger",
    ], logging_h.lines
    # (b) Metrics đếm đúng: 2 tool_calls (1 completed + 1 failed), 1 failure.
    assert metrics_h.counts == {"tool_calls": 2, "tool_failures": 1}, metrics_h.counts
    # (c) Audit thấy đủ 4 event.
    assert len(audit_h.trail) == 4, audit_h.trail
    # (d) Handler hỏng ĐÃ được gọi (4 lần) nhưng KHÔNG làm sập bus.
    assert broken_h.attempts == 4, broken_h.attempts

    print("\n[Bước 5] ĐỐI CHỨNG — khi KHÔNG dùng EDA (gọi trực tiếp consumer):")
    coupled = TightlyCoupledKernel(LoggingHandler(), MetricsHandler(), broken_h)
    try:
        coupled.execute_tool("fs_read")
        raise AssertionError("đáng lẽ phải nổ")
    except RuntimeError as exc:
        print(f"         -> request NỔ vì 1 consumer raise: {exc!r}")
        print("         -> producer phải biết & gọi tay từng consumer (vi phạm OCP),")
        print("            và 1 consumer hỏng kéo sập toàn bộ request.")

    # ── ASSERT: payload mỗi subscriber là deepcopy độc lập ────────────────
    print("\n[Bước 6] Chứng minh mỗi subscriber nhận DEEPCOPY riêng:")
    spy_bus = EventBus()
    received: list[dict[str, Any]] = []
    spy_bus.subscribe(lambda t, p: p["nested"].__setitem__("v", "mutated-by-first"))
    spy_bus.subscribe(lambda t, p: received.append(copy.deepcopy(p)))
    spy_bus.publish("topic", {"nested": {"v": "orig"}})
    # Subscriber thứ 2 vẫn thấy "orig" dù subscriber thứ 1 đã mutate bản của nó.
    assert received == [{"nested": {"v": "orig"}}], received
    print(f"         subscriber 1 mutate -> subscriber 2 vẫn thấy: {received[0]}")

    print("\nTẤT CẢ ASSERT PASS. EDA: producer phát fact, consumer tự xử lý, cô lập lỗi.")


if __name__ == "__main__":
    demo()
