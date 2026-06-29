"""
Case 03 — IDE UI Event Bridge: dịch event của kernel sang event UI qua subscriber (EDA đa tầng).

Bản DISTILL trung thực của luồng EDA nhiều tầng trong hex_agent:
  TẦNG KERNEL phát event thô tool.* lên bus -> TẦNG BRIDGE là 1 subscriber thuần,
  nghe và DỊCH thành từ vựng UI loop.* -> session.emit đẩy vào buffer cho SSE drain.
Bridge KHÔNG gọi kernel; nó CHỈ lắng nghe. Runner ráp dây giữa các tầng.

NGUỒN THẬT (đã mở kiểm chứng):
  - ui/ide/bridge.py:32-96
        KernelEventBridge.subscriber(topic, payload) (dòng 38-44) gắn vào
        kernel.events. _handle (dòng 46-86): tool.requested -> lưu meta {tool, path}
        vào _pending theo request_id; tool.completed/failed -> pop meta, correlate,
        gọi session.emit("loop.tool", ...); graph.parse_error -> "loop.parse_error".
        Bridge không bao giờ raise (try/except ở subscriber).
  - ui/ide/runner.py:123-158, 147-148
        AgentRunner._run: tạo kernel, kernel.events.subscribe(bridge.subscriber)
        (dòng 147) + attach_to_bus(EventLogger, kernel.events) (dòng 148) — NHIỀU
        subscriber độc lập trên 1 bus. Runner tự phát các event boundary của run
        (loop.team_composed/loop.decision/loop.turn/loop.finished) vì chỉ nó biết
        run bắt đầu & kết thúc khi nào.
  - ui/ide/session.py:64-90
        IdeSession.emit: dưới Condition, cấp seq, redact, append vào EventReplayBuffer,
        notify reader SSE đang chờ. Là CHỖ DUY NHẤT event vào buffer.
  - core/events.py:11-31  -> EventBus pub/sub mà bridge subscribe vào.

Ý TƯỞNG MÔ PHỎNG:
  1. Dựng MiniBus (kernel bus) + Bridge + Session (buffer).
  2. "Kernel" phát tool.requested (mang path trong args) rồi tool.completed
     (KHÔNG mang args, chỉ mang request_id).
  3. Bridge correlate 2 event qua request_id để nhấc 'path' lên event UI loop.tool.
  4. Runner phát các event lifecycle (loop.team_composed/loop.turn/loop.finished).
  5. Chứng minh buffer cuối cùng chứa cả event của runner LẪN event do bridge dịch,
     đúng thứ tự seq; và bridge chạy thuần như 1 observer (không gọi ngược kernel).

LƯỢC BỎ: không thread/SSE thật, không Redactor đầy đủ, không HTTP. Giữ đúng VAI:
Producer(kernel) -> Bus -> Consumer(bridge dịch) -> session.emit -> buffer.

Chỉ dùng thư viện chuẩn Python 3.14.
"""
from __future__ import annotations

import copy
import threading
from typing import Any, Callable

Subscriber = Callable[[str, dict[str, Any]], None]


# ──────────────────────────────────────────────────────────────────────────
# BUS — distill core/events.py:11-31 (kernel.events)
# ──────────────────────────────────────────────────────────────────────────
class MiniBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = threading.RLock()

    def subscribe(self, fn: Subscriber) -> None:
        with self._lock:
            self._subscribers.append(fn)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        with self._lock:
            subs = tuple(self._subscribers)
        data = copy.deepcopy(payload or {})
        for fn in subs:
            try:
                fn(topic, copy.deepcopy(data))
            except Exception:
                pass  # 1 observer hỏng không sập bus


# ──────────────────────────────────────────────────────────────────────────
# SESSION — distill ui/ide/session.py:31-90 (buffer + emit; chỗ duy nhất vào buffer)
# ──────────────────────────────────────────────────────────────────────────
class IdeSession:
    """Buffer event UI cho 1 session. emit() cấp seq đơn điệu rồi append."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.buffer: list[dict[str, Any]] = []
        self._seq = 0
        self._lock = threading.RLock()

    def emit(self, event_type: str, payload: dict[str, Any], *, actor: str = "system") -> int:
        # Dưới lock: cấp seq, append, (thực tế còn redact + notify SSE reader).
        with self._lock:
            self._seq += 1
            seq = self._seq
            self.buffer.append({
                "seq": seq,
                "event_type": event_type,
                "actor": actor,
                "payload": dict(payload),
            })
        return seq


# ──────────────────────────────────────────────────────────────────────────
# BRIDGE — distill ui/ide/bridge.py:32-96 (CONSUMER thuần, dịch tool.* -> loop.*)
# ──────────────────────────────────────────────────────────────────────────
_PATH_ARG_KEYS = ("path",)
_MAX_PENDING = 1_024


class KernelEventBridge:
    """Subscriber CÓ TRẠNG THÁI: giữ _pending {request_id -> {tool, path}} để
    correlate tool.requested -> tool.completed (vì tool.completed không mang args)."""

    def __init__(self, session: IdeSession) -> None:
        self.session = session
        self._lock = threading.Lock()
        self._pending: dict[str, dict[str, Any]] = {}
        self.called_kernel = False  # cờ chứng minh bridge KHÔNG gọi ngược kernel

    def subscriber(self, topic: str, payload: dict[str, Any]) -> None:
        """Gắn qua kernel.events.subscribe(bridge.subscriber). Không bao giờ raise."""
        try:
            self._handle(topic, payload)
        except Exception:
            pass

    def _handle(self, topic: str, payload: dict[str, Any]) -> None:
        if topic == "tool.requested":
            request_id = str(payload.get("request_id") or "")
            if request_id:
                with self._lock:
                    self._pending[request_id] = {
                        "tool": str(payload.get("tool") or ""),
                        "path": _extract_path(payload.get("args")),
                    }
                    if len(self._pending) > _MAX_PENDING:
                        del self._pending[next(iter(self._pending))]
            return

        if topic in ("tool.completed", "tool.failed"):
            request_id = str(payload.get("request_id") or "")
            with self._lock:
                meta = self._pending.pop(request_id, {})
            tool = str(payload.get("tool") or meta.get("tool") or "")
            ok = bool(payload.get("ok")) if topic == "tool.completed" else False
            ui_payload: dict[str, Any] = {"tool": tool, "ok": ok, "status": "ok" if ok else "failed"}
            path = meta.get("path")
            if path:
                ui_payload["path"] = path  # nhấc path từ event 'requested' lên event UI
            error = payload.get("error")
            if error and not ok:
                ui_payload["error"] = str(error)[:300]
            actor_id = str(payload.get("actor_id") or "agent:root")
            # Dịch sang từ vựng UI 'loop.tool' và đẩy vào buffer.
            self.session.emit("loop.tool", ui_payload, actor=actor_id)
            return

        if topic == "graph.parse_error":
            self.session.emit(
                "loop.parse_error",
                {"detail": str(payload.get("error") or payload.get("detail") or "parse error")[:300]},
            )


def _extract_path(args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    for key in _PATH_ARG_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


# ──────────────────────────────────────────────────────────────────────────
# KERNEL (producer) — distill core/kernel.py:106-225 (phát tool.* lên bus)
# ──────────────────────────────────────────────────────────────────────────
class MiniKernel:
    def __init__(self, bus: MiniBus) -> None:
        self.events = bus
        self._counter = 0

    def execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        self._counter += 1
        request_id = f"req-{self._counter}"
        # tool.requested MANG args (có path) — kernel.py:123-126.
        self.events.publish("tool.requested",
                            {"tool": tool_name, "request_id": request_id, "args": args})
        ok = not tool_name.startswith("bad_")
        envelope = {"ok": ok, "tool": tool_name}
        # tool.completed/failed KHÔNG mang args, chỉ request_id — kernel.py:215-224.
        self.events.publish(
            "tool.completed" if ok else "tool.failed",
            {"tool": tool_name, "request_id": request_id, "ok": ok,
             "error": None if ok else "tool nổ"},
        )
        return envelope


# ──────────────────────────────────────────────────────────────────────────
# RUNNER — distill ui/ide/runner.py:123-181 (ráp dây + phát event boundary)
# ──────────────────────────────────────────────────────────────────────────
class AgentRunner:
    _AGENT_ID = "agent:root"

    def __init__(self, session: IdeSession) -> None:
        self.session = session

    def run(self, kernel: MiniKernel, bridge: KernelEventBridge, work) -> None:
        # Ráp dây: bridge subscribe vào bus kernel (runner.py:147). Có thể thêm
        # subscriber observability khác (attach_to_bus) — NHIỀU consumer, 1 bus.
        kernel.events.subscribe(bridge.subscriber)

        # Runner tự phát event MỞ run (chỉ runner biết run bắt đầu) — runner.py:105-116.
        self.session.emit("loop.team_composed", {"selected": [self._AGENT_ID]})
        self.session.emit("loop.decision", {"decision": "dispatch", "round": 1})

        # Agent làm việc: mỗi execute_tool sẽ khiến bridge phát loop.tool.
        work(kernel)

        # Runner phát event ĐÓNG run — runner.py:175-182.
        self.session.emit("loop.turn", {"agent_id": self._AGENT_ID, "round": 1}, actor=self._AGENT_ID)
        self.session.emit("loop.finished", {"status": "completed"})


def demo() -> None:
    print("=" * 72)
    print("CASE 03 — IDE UI Event Bridge: EDA đa tầng (kernel -> bridge -> UI buffer)")
    print("=" * 72)

    bus = MiniBus()
    session = IdeSession("sess-1")
    bridge = KernelEventBridge(session)
    kernel = MiniKernel(bus)
    runner = AgentRunner(session)

    print("\n[Bước 1] Ráp dây: bridge.subscriber được subscribe vào kernel.events.")
    print("         Bridge CHỈ lắng nghe — không hề gọi kernel.")

    def work(k: MiniKernel) -> None:
        print("[Bước 2] Agent gọi 2 tool; kernel phát tool.requested + tool.completed/failed.")
        k.execute_tool("fs_write", {"path": "src/app.py", "content": "print(1)"})
        k.execute_tool("bad_tool", {"path": "src/broken.py"})

    runner.run(kernel, bridge, work)

    print("\n[Bước 3] Buffer UI cuối cùng (event runner LẪN event bridge dịch, theo seq):")
    for ev in session.buffer:
        print(f"         seq={ev['seq']} {ev['event_type']:18s} payload={ev['payload']}")

    # ── ASSERT: bất biến của EDA đa tầng ──────────────────────────────────
    types = [ev["event_type"] for ev in session.buffer]
    # (a) Thứ tự đúng: runner mở -> 2 loop.tool do bridge dịch -> runner đóng.
    assert types == [
        "loop.team_composed",
        "loop.decision",
        "loop.tool",        # dịch từ tool.completed của fs_write
        "loop.tool",        # dịch từ tool.failed của bad_tool
        "loop.turn",
        "loop.finished",
    ], types

    # (b) seq đơn điệu, liên tục.
    seqs = [ev["seq"] for ev in session.buffer]
    assert seqs == [1, 2, 3, 4, 5, 6], seqs

    # (c) CORRELATION: bridge nhấc được 'path' từ event 'requested' (mang args)
    #     lên event 'completed' (vốn KHÔNG mang args).
    tool_events = [ev for ev in session.buffer if ev["event_type"] == "loop.tool"]
    assert tool_events[0]["payload"]["path"] == "src/app.py", tool_events[0]
    assert tool_events[0]["payload"]["status"] == "ok"
    assert tool_events[1]["payload"]["path"] == "src/broken.py", tool_events[1]
    assert tool_events[1]["payload"]["status"] == "failed"
    assert tool_events[1]["payload"]["error"] == "tool nổ"
    print("\n[Bước 4] Correlation OK: bridge nhấc 'path' từ tool.requested lên loop.tool")
    print(f"         (fs_write -> path={tool_events[0]['payload']['path']}, status=ok)")

    # (d) _pending đã được dọn sạch sau khi correlate (không rò rỉ).
    assert bridge._pending == {}, bridge._pending

    # (e) Bridge KHÔNG gọi ngược kernel — decoupling theo chiều: kernel không biết bridge.
    assert bridge.called_kernel is False

    print("\n[Bước 5] ĐỐI CHỨNG — nếu KHÔNG có bridge (kernel tự đẩy UI):")
    print("         Kernel phải nhúng từ vựng UI 'loop.tool', biết về EventReplayBuffer,")
    print("         biết redaction & SSE. Tầng orchestration dính chặt tầng trình bày;")
    print("         thêm UI thứ 2 (CLI/web) phải sửa kernel. EDA tách 2 tầng qua event.")

    # Đối chứng cụ thể: kernel phát 1 event mà KHÔNG có bridge nào nghe -> buffer
    # không nhận được gì (fire-and-forget, không subscriber = tín hiệu rơi).
    lonely_bus = MiniBus()
    lonely_session = IdeSession("sess-2")
    lonely_kernel = MiniKernel(lonely_bus)
    lonely_kernel.execute_tool("fs_read", {"path": "x.txt"})  # không ai subscribe
    assert lonely_session.buffer == [], lonely_session.buffer
    print("         -> Không subscribe bridge: event kernel rơi, buffer UI rỗng.")

    print("\nTẤT CẢ ASSERT PASS. EDA đa tầng: kernel phát thô, bridge dịch, UI nhận —")
    print("mỗi tầng chỉ couple qua event, thêm/bớt tầng không phá tầng khác.")


if __name__ == "__main__":
    demo()
