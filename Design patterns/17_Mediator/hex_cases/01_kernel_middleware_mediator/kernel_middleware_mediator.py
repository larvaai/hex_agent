"""
Case 01 — AgentKernel.execute_tool: Chokepoint Mediator + middleware pipeline.

Bản DISTILL TRUNG THỰC từ codebase hex_agent. Nguồn thật:
  - core/kernel.py:106-225  (AgentKernel.execute_tool — chokepoint duy nhất)
  - core/kernel.py:49-73    (_wrap — bind 1 middleware quanh handler kế tiếp)
  - core/kernel.py:100-104  (AgentKernel.use — đăng ký middleware, outer->inner)
  - core/kernel.py:152-177  (core(req) — resolver: registry.resolve_tool + executor.execute)
  - core/registry.py:103-112 (CapabilityRegistry.resolve_tool — map tool_name -> executor)
  - core/registry.py:29-40   (NullToolPort — giữ kernel sống khi thiếu tool)
  - middleware/retry.py:23-33 (Retry — gọi nxt lặp lại khi !ok)
  - middleware/timing.py:10-26 (TimingLog — advisory, fail_open=True)

Ý tưởng pattern (Mediator):
  Mọi request gọi tool KHÔNG đi thẳng tới executor. Tất cả phải đi qua MỘT
  chokepoint là `kernel.execute_tool`. Kernel (ConcreteMediator) sở hữu một
  danh sách middleware (các "colleague" cắt ngang) và bọc chúng quanh một
  resolver `core` chọn executor cuối qua registry. Các middleware KHÔNG biết
  về nhau; caller KHÔNG biết executor; thêm/bớt một middleware không đụng tới
  caller hay executor. Đây là Mediator kiểu Command-Bus + middleware pipeline.

Bản rút gọn này bỏ: LLM/DB/network, lineage/event-envelope đầy đủ, deep-freeze
config, _LatchedNext one-shot. Giữ ĐÚNG: chokepoint, registry-resolve, chuỗi
middleware bọc theo thứ tự outer->inner, fail-open (advisory) vs fail-closed,
NullTool fallback, và bất biến "không có đường tắt caller->executor".

LƯU Ý hệ quả của việc bỏ _LatchedNext: vì nhánh fail-open ở đây gọi lại
`nxt(request)` sau khi middleware raise, một middleware fail_open=True raise SAU
khi đã gọi nxt sẽ khiến executor chạy 2 LẦN (double-run). Đây CHÍNH là lỗi mà
_LatchedNext (core/kernel.py:24-46, "FM-HIGH, non-idempotent") sinh ra để chặn —
nguy hiểm với tool non-idempotent. Xem cảnh báo chi tiết trong docstring `_wrap`.

Chạy: python3 kernel_middleware_mediator.py   (exit code 0, không traceback)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


# ── Message tham số hoá request (≈ ToolRequest trong core/schemas) ────────────
@dataclass
class ToolRequest:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


# ── COLLEAGUE phía thực thi: các executor cụ thể (≈ ToolPort/executor) ────────
class EchoExecutor:
    """Một tool 'thật': trả về dữ liệu. Không biết gì về middleware hay caller."""
    name = "echo"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {"ok": True, "tool": request.name, "data": {"echo": request.args.get("text", "")}}


class FlakyExecutor:
    """Tool chập chờn: hỏng vài lần đầu rồi mới ok — để chứng minh Retry middleware."""
    name = "flaky"

    def __init__(self, fail_times: int) -> None:
        self._left = fail_times
        self.calls = 0

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        self.calls += 1
        if self._left > 0:
            self._left -= 1
            return {"ok": False, "tool": request.name, "error": "transient"}
        return {"ok": True, "tool": request.name, "data": {"value": 42}}


# ── REGISTRY: map tool_name -> executor (≈ core/registry.py resolve_tool) ──────
class NullToolPort:
    """Giữ mediator sống khi không có executor đăng ký (≈ registry.py:29-40)."""
    name = "null_tool"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {"ok": False, "tool": request.name, "missing_capability": True,
                "error": f"No tool registered for '{request.name}'."}


class CapabilityRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._null = NullToolPort()

    def register_tool(self, name: str, executor: Any) -> None:
        self._tools[name] = executor

    def resolve_tool(self, name: str) -> Any:
        # Exact wins; nếu thiếu -> NullToolPort (≈ registry.py:103-112).
        return self._tools.get(name, self._null)


# ── MIDDLEWARE = các COLLEAGUE cắt ngang. Mỗi cái nhận (request, nxt). ─────────
# Chúng không gọi nhau; chỉ gọi `nxt` (handler kế trong chuỗi do mediator bọc).
class TimingLog:
    """Advisory telemetry. fail_open=True: nếu nó hỏng, KHÔNG được chặn tool
    (≈ middleware/timing.py:10-26). Mediator sẽ skip nó và dùng kết quả inner."""
    fail_open = True

    def __init__(self, sink: Callable[[dict[str, Any]], None]) -> None:
        self.name = "timing"
        self.sink = sink

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        env = nxt(request)
        self.sink({"event": "timing", "tool": request.name, "ok": env.get("ok")})
        return env


class LoggingMw:
    """Ghi log trước/sau. Không biết Retry hay Scope tồn tại."""
    def __init__(self, sink: Callable[[dict[str, Any]], None]) -> None:
        self.name = "logging"
        self.sink = sink

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        self.sink({"event": "log.before", "tool": request.name})
        env = nxt(request)
        self.sink({"event": "log.after", "tool": request.name, "ok": env.get("ok")})
        return env


class Retry:
    """Gọi nxt lặp lại khi kết quả !ok (≈ middleware/retry.py:23-33).
    fail-closed: KHÔNG opt-in fail_open => raise sẽ propagate (ở bản rút gọn
    không demo raise, nhưng giữ đúng tư thế)."""
    def __init__(self, attempts: int = 3) -> None:
        self.name = "retry"
        self.attempts = max(1, attempts)

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        env = nxt(request)
        tries = 1
        while isinstance(env, dict) and not env.get("ok") and tries < self.attempts:
            env = nxt(request)
            tries += 1
        return env


class ScopeGate:
    """Capability gate: chặn tool ngoài scope TRƯỚC khi chạm executor."""
    def __init__(self, allowed: set[str], sink: Callable[[dict[str, Any]], None]) -> None:
        self.name = "scope"
        self.allowed = allowed
        self.sink = sink

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        if request.name not in self.allowed:
            self.sink({"event": "scope.block", "tool": request.name})
            return {"ok": False, "tool": request.name, "error": "outside scope", "scope_block": True}
        return nxt(request)


# ── CONCRETE MEDIATOR: AgentKernel ────────────────────────────────────────────
def _wrap(middleware, nxt, on_skip):
    """Bind 1 middleware quanh handler kế (≈ core/kernel.py:49-73).
    fail-open (advisory): nếu nó raise -> skip, dùng kết quả inner.
    fail-closed: raise propagate ra ngoài (kernel boundary đổi thành ok=False).

    RỦI RO ĐÃ-BIẾT (do bản rút gọn LƯỢC BỎ _LatchedNext): nhánh fail-open gọi
    `nxt(request)` lại trong `except`. Nếu một middleware fail_open=True raise SAU
    khi ĐÃ gọi `nxt` (đã chạm executor), executor sẽ chạy 2 LẦN — đúng lỗi
    double-run mà `_LatchedNext` one-shot ở bản thật (core/kernel.py:24-46,
    docstring "FM-HIGH, non-idempotent") sinh ra để CHẶN. Với tool non-idempotent
    (charge, write, send) đây là lỗi thật, không chỉ là chi tiết bị giản lược.
    Bản thật latch `nxt` để post-nxt raise replay kết quả cũ, KHÔNG re-execute."""
    if getattr(middleware, "fail_open", False) is not True:
        def handler(request: ToolRequest) -> dict[str, Any]:
            return middleware(request, nxt)
        return handler

    def handler(request: ToolRequest) -> dict[str, Any]:
        try:
            return middleware(request, nxt)
        except Exception as exc:  # advisory hỏng -> skip, vẫn chạy inner
            on_skip(middleware, exc)
            return nxt(request)    # CẢNH BÁO: nếu mw đã gọi nxt trước khi raise -> double-run
    return handler


@dataclass
class AgentKernel:
    """Mediator: sở hữu registry + danh sách middleware; là chokepoint DUY NHẤT.
    (≈ core/kernel.py:76-225)."""
    registry: CapabilityRegistry
    events: list = field(default_factory=list)          # bus tối giản: list event
    _middlewares: list = field(default_factory=list)

    def use(self, middleware) -> None:
        """Đăng ký middleware. Thứ tự đăng ký = outer -> inner (≈ kernel.py:100-104)."""
        self._middlewares.append(middleware)

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        request = ToolRequest(name=tool_name, args=dict(args or {}))
        self.events.append({"event": "tool.requested", "tool": request.name})

        def core(req: ToolRequest) -> dict[str, Any]:
            # Resolver: registry chọn executor cuối, rồi gọi execute (≈ kernel.py:152-177).
            executor = self.registry.resolve_tool(req.name)
            try:
                result = executor.execute(req)
            except Exception as exc:  # tool không bao giờ được làm sập kernel
                result = {"ok": False, "tool": req.name, "error": str(exc), "kernel_error": True}
            return result

        def on_skip(mw: Any, exc: Exception) -> None:
            self.events.append({"event": "middleware.skipped", "middleware": getattr(mw, "name", "?"),
                                "error": str(exc)})

        # Bọc các middleware quanh core theo thứ tự đảo (reversed) => phần tử
        # đăng ký đầu tiên nằm NGOÀI cùng (≈ kernel.py:192-194).
        handler = core
        for mw in reversed(self._middlewares):
            handler = _wrap(mw, handler, on_skip)

        try:
            envelope = handler(request)
        except Exception as exc:  # middleware fail-closed raise -> biên kernel hoá ok=False
            envelope = {"ok": False, "tool": request.name, "error": str(exc), "kernel_error": True}

        self.events.append({"event": "tool.completed" if envelope.get("ok") else "tool.failed",
                            "tool": request.name, "ok": bool(envelope.get("ok"))})
        return envelope


# ── ĐỐI CHỨNG: KHÔNG có mediator -> caller phải tự ráp mọi cross-cutting concern
class TanglingCaller:
    """Anti-pattern: caller giữ reference TRỰC TIẾP tới executor và tự nhồi
    logging/scope/retry vào trong mình. Mỗi caller mới phải copy-paste lại toàn
    bộ; thêm 1 concern (vd timing) = sửa MỌI caller. Đây là N×N coupling."""
    def __init__(self, executor: Any, allowed: set[str]) -> None:
        self.executor = executor              # biết executor cụ thể
        self.allowed = allowed                # tự gánh scope
        self.log: list[str] = []

    def call(self, name: str, **args: Any) -> dict[str, Any]:
        if name not in self.allowed:          # tự gánh scope check
            return {"ok": False, "error": "outside scope"}
        self.log.append(f"before:{name}")     # tự gánh logging
        env = self.executor.execute(ToolRequest(name, dict(args)))
        tries = 1
        while not env.get("ok") and tries < 3:  # tự gánh retry
            env = self.executor.execute(ToolRequest(name, dict(args)))
            tries += 1
        self.log.append(f"after:{name}:{env.get('ok')}")
        return env


def demo() -> None:
    print("=" * 70)
    print("CASE 01 — AgentKernel.execute_tool: Chokepoint Mediator")
    print("=" * 70)

    # 1) Dựng registry + đăng ký executor (colleague phía thực thi).
    registry = CapabilityRegistry()
    echo = EchoExecutor()
    flaky = FlakyExecutor(fail_times=2)
    registry.register_tool("echo", echo)
    registry.register_tool("flaky", flaky)

    # 2) Dựng mediator + cắm middleware (colleague cắt ngang). Thứ tự = outer->inner.
    telemetry: list[dict[str, Any]] = []
    kernel = AgentKernel(registry=registry)
    kernel.use(TimingLog(sink=telemetry.append))                 # ngoài cùng
    kernel.use(LoggingMw(sink=telemetry.append))
    kernel.use(ScopeGate(allowed={"echo", "flaky"}, sink=telemetry.append))
    kernel.use(Retry(attempts=3))                                # trong cùng (sát core)

    print("\n[1] Gọi tool 'echo' qua chokepoint. Request đi qua chuỗi:")
    print("    tool.requested -> timing -> logging -> scope -> retry -> registry -> executor")
    env = kernel.execute_tool("echo", {"text": "xin chao"})
    print(f"    -> kết quả: {env}")
    assert env["ok"] is True
    assert env["data"]["echo"] == "xin chao"

    print("\n[2] Gọi 'flaky' (hỏng 2 lần đầu). Retry middleware tự gọi lại nxt:")
    env = kernel.execute_tool("flaky", {})
    print(f"    -> số lần executor được gọi = {flaky.calls} (1 fail + 1 fail + 1 ok)")
    print(f"    -> kết quả: {env}")
    assert env["ok"] is True
    assert flaky.calls == 3, "Retry phải gọi executor đúng 3 lần"

    print("\n[3] Gọi tool ngoài scope -> ScopeGate chặn TRƯỚC khi chạm executor:")
    env = kernel.execute_tool("danger.rm_rf", {})
    print(f"    -> kết quả: {env}")
    assert env["ok"] is False and env.get("scope_block") is True

    print("\n[4] Gọi tool chưa đăng ký nhưng trong scope -> NullToolPort giữ kernel sống:")
    kernel2 = AgentKernel(registry=CapabilityRegistry())
    kernel2.use(ScopeGate(allowed={"ghost"}, sink=telemetry.append))
    env = kernel2.execute_tool("ghost", {})
    print(f"    -> kết quả: {env}")
    assert env["ok"] is False and env.get("missing_capability") is True

    print("\n[5] OPEN/CLOSED — đổi THỨ TỰ / THÊM middleware mà KHÔNG đụng caller/executor:")
    order_a = [e["event"] for e in telemetry if e["event"] in ("timing", "log.before")]
    # Cùng executor 'echo', chỉ đổi cấu hình mediator: hành vi quan sát đổi theo.
    print(f"    -> telemetry tích luỹ có {len(telemetry)} bản ghi; executor code KHÔNG đổi 1 dòng.")
    assert any(e["event"] == "timing" for e in telemetry)

    print("\n[6] Bằng chứng fail-open: TimingLog hỏng -> bị SKIP, tool vẫn ok:")
    class BoomTiming(TimingLog):
        def __call__(self, request, nxt):
            env = nxt(request)
            raise RuntimeError("telemetry sink down")  # advisory hỏng sau khi đã có inner
    k3 = AgentKernel(registry=registry)
    k3.use(BoomTiming(sink=telemetry.append))
    k3.use(Retry(attempts=2))
    env = kernel_echo = k3.execute_tool("echo", {"text": "still works"})
    print(f"    -> kết quả: {env}")
    skipped = [e for e in k3.events if e["event"] == "middleware.skipped"]
    print(f"    -> middleware.skipped = {skipped}")
    assert env["ok"] is True, "fail-open advisory hỏng KHÔNG được chặn tool"
    assert len(skipped) == 1

    print("\n[7] ĐỐI CHỨNG — KHÔNG dùng mediator (TanglingCaller):")
    f2 = FlakyExecutor(fail_times=1)
    caller = TanglingCaller(executor=f2, allowed={"flaky"})
    env = caller.call("flaky")
    print(f"    -> caller phải TỰ ráp scope+log+retry; biết executor cụ thể: {env}")
    print(f"    -> log nội bộ caller: {caller.log}")
    print("    -> Hệ quả: thêm 1 caller nữa = copy-paste lại toàn bộ; thêm 'timing' = sửa MỌI caller.")
    print("       Đó chính là N×N coupling mà Mediator triệt tiêu (dồn về 1 chokepoint).")
    assert env["ok"] is True

    print("\n[BẤT BIẾN] Caller chỉ biết kernel.execute_tool(name, args); KHÔNG giữ ref executor.")
    print("           Executor chỉ biết execute(request); KHÔNG biết caller/middleware.")
    print("           Mọi đường đi đều qua đúng MỘT chokepoint -> N×1, không N×N.")
    print("\nTẤT CẢ ASSERT PASS. ✔")


if __name__ == "__main__":
    demo()
