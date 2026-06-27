"""
State Pattern — Case 03: IDE Session run lifecycle (idle -> running -> finished/failed/cancelled).

Bản DISTILL TRUNG THỰC từ hex_agent. Nguồn thật:
  - ui/ide/session.py:48        — self._cond = threading.Condition() (serialize mọi truy cập).
  - ui/ide/session.py:50        — run_status = "idle"  # idle | running | finished | failed.
  - ui/ide/session.py:109-112   — set_status(): mutate run_status + notify dưới lock.
  - ui/ide/session.py:118-129   — try_begin_run(): guard nguyên tử idle->running; nếu đang
                                  running thì TỪ CHỐI (return False).
  - ui/ide/session.py:131-133   — snapshot_status(): đọc run_status dưới lock (cho HTTP handler).
  - ui/ide/runner.py:80-88      — cancel(): chỉ hoạt động khi status == "running".
  - ui/ide/runner.py:90-121     — start(): claim run_status nguyên tử (l.101), spawn _run thread.
  - ui/ide/runner.py:123-183    — _run thread: chạy agent -> finished (l.183).
  - ui/ide/runner.py:185-194    — _finish_failed(): status -> "failed".
  - ui/ide/runner.py:196-206    — _finish_cancelled(): status -> "cancelled".

Pattern: State (Behavioral) — biến thể thread-safe.
  - Context: IdeSession (giữ run_status + buffer; delegate run cho runner thread).
  - State: run_status {idle, running, finished, failed, cancelled}.
  - Transition: state-driven (runner thread set status) + context-driven (HTTP stop:
    cancel() đọc status). Guard: try_begin_run() từ chối running->running;
    cancel() từ chối nếu status != "running". Tất cả dưới threading.Condition (nguyên tử).

CHỈ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent / bên thứ ba.
Hạ tầng nặng bị thay:
  - Kernel/LLM agent run -> fake_agent_work(): vài bước ngủ ngắn, kiểm tra cờ cancel.
  - SSE buffer/Redactor/RuntimeEvent -> list event đơn giản.
"""
from __future__ import annotations

import threading
import time


# ── Context: IdeSession (distill ui/ide/session.py) ──────────────────────────
class IdeSession:
    """Giữ run_status + sự kiện; mọi truy cập serialize qua MỘT Condition."""

    VALID = frozenset({"idle", "running", "finished", "failed", "cancelled"})
    TERMINAL = frozenset({"finished", "failed", "cancelled"})

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._cond = threading.Condition()          # session.py:48
        self.run_status = "idle"                     # session.py:50
        self.events: list[str] = []
        self.last_prompt = ""

    def emit(self, line: str) -> None:
        with self._cond:
            self.events.append(line)
            self._cond.notify_all()

    def set_status(self, status: str) -> None:
        """Transition có notify, dưới lock (session.py:109-112)."""
        assert status in self.VALID, f"status lạ: {status}"
        with self._cond:
            self.run_status = status
            self._cond.notify_all()

    def try_begin_run(self, prompt: str) -> bool:
        """GUARD nguyên tử idle->running. Nếu đang running -> TỪ CHỐI (session.py:118-129).

        Đây là điểm cốt lõi: hai SubmitPrompt đồng thời KHÔNG thể cùng thắng claim,
        nên không có chuyện hai run xen kẽ sự kiện / ghi đè baseline.
        """
        with self._cond:
            if self.run_status == "running":
                return False
            self.last_prompt = prompt
            self.run_status = "running"
            self._cond.notify_all()
            return True

    def snapshot_status(self) -> str:
        """Đọc status dưới lock — HTTP handler dùng để không race runner (session.py:131-133)."""
        with self._cond:
            return self.run_status

    def wait_until_terminal(self, timeout: float = 5.0) -> str:
        """Chặn tới khi status vào tập terminal (cho demo determinism)."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while self.run_status not in self.TERMINAL:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            return self.run_status


# ── Runner thread (distill ui/ide/runner.py) ─────────────────────────────────
class AgentRunner:
    def __init__(self, session: IdeSession, *, work_steps: int = 4, step_delay: float = 0.02) -> None:
        self.session = session
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._work_steps = work_steps
        self._step_delay = step_delay

    def cancel(self) -> bool:
        """Chỉ hủy được khi đang running (runner.py:80-88).

        Đọc status qua snapshot_status() (lock của session) -> không race runner thread.
        """
        if self.session.snapshot_status() != "running":
            return False
        self._cancel.set()
        return True

    def start(self, prompt: str) -> str | None:
        """Claim status nguyên tử rồi spawn thread (runner.py:90-121).

        Trả None nếu đã có run đang chạy — start thứ hai sẽ làm hỏng state.
        """
        with self._lock:
            if not self.session.try_begin_run(prompt):     # runner.py:101
                return None
            self._cancel.clear()
        self.session.emit(f"loop.team_composed prompt={prompt!r}")
        run_id = f"run-{int(time.monotonic() * 1000)}"
        thread = threading.Thread(target=self._run, args=(run_id,), name=run_id, daemon=True)
        thread.start()
        return run_id

    def _run(self, run_id: str) -> None:
        """Thread công nhân: idle->running (đã set ở start) -> finished/failed/cancelled."""
        try:
            for i in range(self._work_steps):
                if self._cancel.is_set():                   # cooperative cancel (runner.py:139)
                    self._finish_cancelled()
                    return
                self.session.emit(f"loop.tool step={i}")
                time.sleep(self._step_delay)
        except Exception as exc:                            # run stack lỗi (runner.py:162-164)
            self._finish_failed(f"{type(exc).__name__}: {exc}")
            return
        if self._cancel.is_set():                           # cancel rơi vào lúc kết thúc (runner.py:166)
            self._finish_cancelled()
            return
        self.session.emit("loop.turn outcome=ok")
        self.session.emit("loop.finished")
        self.session.set_status("finished")                 # runner.py:183

    def _finish_failed(self, message: str) -> None:
        self.session.emit(f"loop.failed error={message}")
        self.session.set_status("failed")                   # runner.py:194

    def _finish_cancelled(self) -> None:
        self.session.emit("loop.failed cancelled=True")
        self.session.set_status("cancelled")                # runner.py:206


# ── Demo ──────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 70)
    print("CASE 03 — IDE Session run lifecycle (thread-safe State)")
    print("idle -> running -> {finished | failed | cancelled}")
    print("=" * 70)

    # ── Kịch bản 1: chạy bình thường -> finished ──
    print("\n--- Kịch bản 1: submit -> run chạy hết -> finished ---")
    s1 = IdeSession("s1")
    r1 = AgentRunner(s1, work_steps=3, step_delay=0.01)
    print(f"  trước submit: status={s1.snapshot_status()}")
    rid = r1.start("viết hello.py")
    print(f"  start() trả run_id={rid}, status ngay sau claim={s1.snapshot_status()}")
    final = s1.wait_until_terminal()
    print(f"  status cuối: {final}")
    print(f"  events: {s1.events}")
    assert s1.snapshot_status() == "finished"
    print("  [assert] OK: idle -> running -> finished.")

    # ── Kịch bản 2: GUARD — start thứ hai bị từ chối khi đang running ──
    print("\n--- Kịch bản 2: hai start đồng thời -> cái thứ hai bị từ chối ---")
    s2 = IdeSession("s2")
    r2 = AgentRunner(s2, work_steps=6, step_delay=0.02)
    rid_a = r2.start("run A")
    rid_b = r2.start("run B")            # status đang running -> try_begin_run trả False
    print(f"  start A -> {rid_a!r}; start B (khi A đang chạy) -> {rid_b!r}")
    assert rid_a is not None and rid_b is None, "start thứ hai phải bị từ chối (guard nguyên tử)"
    print("  [assert] OK: try_begin_run() chặn running->running (không xen kẽ hai run).")
    s2.wait_until_terminal()

    # ── Kịch bản 3: cancel khi đang running -> cancelled ──
    print("\n--- Kịch bản 3: cancel giữa chừng -> cancelled ---")
    s3 = IdeSession("s3")
    r3 = AgentRunner(s3, work_steps=50, step_delay=0.02)   # run dài để kịp cancel
    r3.start("tác vụ dài")
    # đợi tới khi chắc chắn đang running rồi mới cancel
    while s3.snapshot_status() != "running":
        time.sleep(0.005)
    ok = r3.cancel()
    print(f"  cancel() khi đang running -> {ok}")
    final3 = s3.wait_until_terminal()
    print(f"  status cuối: {final3}")
    assert ok is True
    assert s3.snapshot_status() == "cancelled"
    print("  [assert] OK: cancel hợp lệ khi running -> cancelled.")

    # ── Kịch bản 4: GUARD — cancel khi KHÔNG running thì vô hiệu ──
    print("\n--- Kịch bản 4: cancel khi status != running -> no-op ---")
    s4 = IdeSession("s4")
    r4 = AgentRunner(s4, work_steps=2, step_delay=0.01)
    no_run_cancel = r4.cancel()             # đang idle
    print(f"  cancel() khi idle -> {no_run_cancel}")
    assert no_run_cancel is False, "cancel phải vô hiệu khi không có run đang chạy"
    r4.start("xong nhanh")
    s4.wait_until_terminal()
    after_cancel = r4.cancel()              # đã finished (terminal)
    print(f"  cancel() khi đã finished -> {after_cancel}")
    assert after_cancel is False, "cancel phải vô hiệu khi đã terminal"
    print("  [assert] OK: cancel chỉ có tác dụng khi state == running (behavior theo state).")

    # ── Bất biến tập state ──
    for sess in (s1, s2, s3, s4):
        assert sess.snapshot_status() in IdeSession.VALID
        assert sess.snapshot_status() in IdeSession.TERMINAL
    print("\n[assert] OK: mọi session kết thúc ở một state terminal hợp lệ.")

    print("\n--- Đối chứng: KHÔNG guard nguyên tử ---")
    print("  Nếu start chỉ làm 'if status==idle: status=running' KHÔNG dưới lock,")
    print("  hai thread cùng đọc 'idle' -> cùng claim -> hai run ghi đè baseline + xen sự kiện.")
    print("  try_begin_run() gộp kiểm-tra-và-gán vào MỘT vùng tới hạn (Condition) -> an toàn.")

    print("\nKẾT LUẬN: run_status + try_begin_run/cancel guard theo state + Condition =")
    print("State pattern thread-safe. Hành vi (cancel được/không) phụ thuộc state hiện tại.")


if __name__ == "__main__":
    demo()
