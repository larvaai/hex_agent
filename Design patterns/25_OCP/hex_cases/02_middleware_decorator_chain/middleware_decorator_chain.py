"""
CASE 02 — OCP qua ToolMiddleware chain (Decorator pattern)
==========================================================

Bản DISTILL TRUNG THỰC (chỉ stdlib) của middleware chokepoint trong hex_agent.

NGUỒN THẬT (đã mở file kiểm chứng):
  - core/middleware.py:11-22   ToolMiddleware Protocol: __call__(request, nxt) -> dict
                               (+ thuộc tính tùy chọn fail_open cho middleware advisory)
  - core/kernel.py:24-46       _LatchedNext — proxy one-shot bảo vệ fail-open middleware
                               khỏi chạy lại tool (non-idempotent) khi raise SAU khi đã gọi nxt
  - core/kernel.py:49-73       _wrap(middleware, nxt, on_skip) — bind 1 middleware quanh handler
  - core/kernel.py:100-104     AgentKernel.use(middleware) — chỉ append vào list
  - core/kernel.py:192-194     handler=core; for mw in reversed(_middlewares): handler=_wrap(mw, handler)
  - middleware/timing.py:1-26  TimingLog (fail_open=True, advisory telemetry)
  - middleware/policy.py:1-21  PolicyGate (deny-list, short-circuit không gọi nxt)
  - middleware/retry.py:1-33   Retry (gọi nxt lặp lại khi !ok)
  - core/bootstrap.py:28-53    _install_middleware — kernel.use(...) theo config, order outer->inner

Ý TƯỞNG OCP (lesson 25, bảng 2.1 cơ chế #3 — Decorator):
  Cross-cutting concern (logging, retry, policy, budget) KHÔNG được nhồi vào execute_tool().
  Mỗi concern là 1 middleware độc lập, cắm vào bằng kernel.use(). Thêm concern mới =
  thêm class middleware + 1 dòng kernel.use(), 0 sửa logic execute_tool.

  - ToolMiddleware = abstraction.
  - LoggingMiddleware / RetryMiddleware / PolicyGate / BudgetGate = concrete decorators.
  - _wrap() = decorator factory (đóng closure quanh handler kế tiếp).
  - execute_tool() = orchestrator dựng chain bằng reversed(middlewares) -> outer..inner.
  - kernel.use() = extension point.

LƯỢC BỎ so với bản thật:
  - Bỏ envelope CapabilityResult, lineage/events, scope check.
  - Giữ NGUYÊN cơ chế cốt lõi: chain dựng từ reversed(list), fail_open + _LatchedNext
    (để chứng minh tool không bị chạy 2 lần), short-circuit của policy gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


# ── 1. ABSTRACTION: ToolMiddleware (distill core/middleware.py:11-22) ────────────
class ToolMiddleware(Protocol):
    """Nhận request + nxt (handler bên trong). Có thể act before/after, short-circuit
    (return mà không gọi nxt), hoặc sửa result. Thuộc tính tùy chọn `fail_open=True`
    đánh dấu middleware advisory (telemetry): nếu nó raise, kernel BỎ QUA nó."""

    def __call__(self, request: dict[str, Any], nxt: ToolHandler) -> dict[str, Any]: ...


# ── 2. _LatchedNext: proxy one-shot (distill core/kernel.py:24-46) ──────────────
class _LatchedNext:
    """Chạy inner handler TỐI ĐA 1 lần; lần gọi sau replay kết quả/exception ĐÃ lưu
    mà KHÔNG chạy lại. Bảo vệ fail-open middleware (nếu raise SAU khi đã gọi nxt) khỏi
    làm tool non-idempotent chạy đôi."""

    __slots__ = ("_nxt", "_ran", "_result", "_exc")

    def __init__(self, nxt: ToolHandler) -> None:
        self._nxt = nxt
        self._ran = False
        self._result: Any = None
        self._exc: Exception | None = None

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self._ran:
            self._ran = True
            try:
                self._result = self._nxt(request)
            except Exception as exc:  # lưu lại để fallback replay, không bao giờ chạy lại
                self._exc = exc
        if self._exc is not None:
            raise self._exc
        return self._result


# ── 3. _wrap: decorator factory (distill core/kernel.py:49-73) ──────────────────
def _wrap(middleware: Any, nxt: ToolHandler, on_skip=None) -> ToolHandler:
    """Bind 1 middleware quanh handler kế tiếp.
    - Mặc định fail-closed: middleware raise -> propagate (ok=False ở biên).
    - fail_open=True (advisory): nếu raise -> BỎ QUA, chain tiếp tục với inner result;
      nxt được 'latched' (one-shot) nên post-nxt raise không làm tool chạy lại."""
    if getattr(middleware, "fail_open", False) is not True:
        def handler(request: dict[str, Any]) -> dict[str, Any]:
            return middleware(request, nxt)
        return handler

    def handler(request: dict[str, Any]) -> dict[str, Any]:
        latched = _LatchedNext(nxt)
        try:
            return middleware(request, latched)
        except Exception as exc:  # advisory failed -> skip, giữ inner result (latched)
            if on_skip is not None:
                on_skip(middleware, exc)
            return latched(request)
    return handler


# ── 4. ORCHESTRATOR: AgentKernel (distill core/kernel.py:76-194, rút gọn) ────────
@dataclass
class AgentKernel:
    """Chokepoint duy nhất. Logic execute_tool BẤT BIẾN; mọi cross-cutting concern
    đến qua middleware list."""

    tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = field(default_factory=dict)
    _middlewares: list = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # ghi lại middleware advisory bị skip

    def register_tool(self, name: str, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.tools[name] = fn

    def use(self, middleware: Any) -> None:
        """Distill core/kernel.py:100-104. Order đăng ký = outer -> inner."""
        self._middlewares.append(middleware)

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        request = {"name": tool_name, "args": dict(args or {})}

        def core(req: dict[str, Any]) -> dict[str, Any]:
            fn = self.tools.get(req["name"])
            if fn is None:
                return {"ok": False, "tool": req["name"], "error": "no such tool"}
            try:
                return fn(req)
            except Exception as exc:  # tool không bao giờ làm sập kernel
                return {"ok": False, "tool": req["name"], "error": str(exc), "kernel_error": True}

        def on_skip(mw: Any, exc: Exception) -> None:
            self.skipped.append(getattr(mw, "name", type(mw).__name__))

        # Dựng chain: bắt đầu từ core, wrap reversed(middlewares) -> outer chạy trước.
        handler = core
        for mw in reversed(self._middlewares):
            handler = _wrap(mw, handler, on_skip=on_skip)
        try:
            return handler(request)
        except Exception as exc:  # middleware không bao giờ làm sập biên kernel
            return {"ok": False, "tool": tool_name, "error": str(exc), "kernel_error": True}


# ── 5. CONCRETE MIDDLEWARES (decorators độc lập) ────────────────────────────────
class LoggingMiddleware:
    """Distill ý của middleware/timing.py — advisory (fail_open). In before/after."""

    name = "logging"
    fail_open = True  # telemetry: nếu nó hỏng, KHÔNG được làm hỏng tool call

    def __init__(self, sink: list[str]) -> None:
        self.sink = sink

    def __call__(self, request: dict[str, Any], nxt: ToolHandler) -> dict[str, Any]:
        self.sink.append(f"-> {request['name']}")
        env = nxt(request)
        self.sink.append(f"<- {request['name']} ok={env.get('ok')}")
        return env


class PolicyGate:
    """Distill middleware/policy.py:9-21 — deny-list, SHORT-CIRCUIT (không gọi nxt)."""

    name = "policy"

    def __init__(self, deny: set[str] | None = None) -> None:
        self.deny = set(deny or ())

    def __call__(self, request: dict[str, Any], nxt: ToolHandler) -> dict[str, Any]:
        if request["name"] in self.deny:
            return {"ok": False, "tool": request["name"],
                    "error": f"Blocked by policy: {request['name']}", "policy_block": True}
        return nxt(request)


class RetryMiddleware:
    """Distill middleware/retry.py:23-33 — gọi nxt lặp lại khi !ok (không retry policy block)."""

    name = "retry"

    def __init__(self, attempts: int = 3) -> None:
        self.attempts = max(1, attempts)

    def __call__(self, request: dict[str, Any], nxt: ToolHandler) -> dict[str, Any]:
        env = nxt(request)
        tries = 1
        while isinstance(env, dict) and not env.get("ok") and tries < self.attempts \
                and not env.get("policy_block"):
            env = nxt(request)
            tries += 1
        env["tries"] = tries
        return env


class BudgetGate:
    """MIDDLEWARE MỚI ('open for extension'): chặn sau N lần gọi cùng tool.
    Cắm vào CHỈ bằng kernel.use(BudgetGate(...)). execute_tool() KHÔNG đổi 1 dòng.
    (hex_agent có middleware/budget.py thật — đây là distill của ý tưởng đó.)"""

    name = "budget"

    def __init__(self, max_calls: int = 2) -> None:
        self.max_calls = max_calls
        self._counts: dict[str, int] = {}

    def __call__(self, request: dict[str, Any], nxt: ToolHandler) -> dict[str, Any]:
        n = self._counts.get(request["name"], 0)
        if n >= self.max_calls:
            return {"ok": False, "tool": request["name"], "error": "budget exceeded"}
        self._counts[request["name"]] = n + 1
        return nxt(request)


# ── 6. Middleware advisory cố tình HỎNG để chứng minh fail-open + latch ──────────
class BrokenTelemetry:
    """fail_open=True nhưng raise SAU khi đã gọi nxt. Phải bị skip; tool chỉ chạy 1 lần."""

    name = "broken_telemetry"
    fail_open = True

    def __call__(self, request: dict[str, Any], nxt: ToolHandler) -> dict[str, Any]:
        env = nxt(request)            # gọi tool (1 lần)
        raise RuntimeError("telemetry blew up after running tool")  # advisory raise -> skip


def demo() -> None:
    print("=" * 72)
    print("CASE 02 — OCP qua ToolMiddleware chain (Decorator pattern)")
    print("=" * 72)

    log: list[str] = []
    kernel = AgentKernel()

    # tool counter để chứng minh số lần chạy thật
    runs = {"flaky": 0, "side_effect": 0}

    def echo_tool(req: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "echo": dict(req["args"])}

    def flaky_tool(req: dict[str, Any]) -> dict[str, Any]:
        runs["flaky"] += 1
        return {"ok": runs["flaky"] >= 2, "n": runs["flaky"]}  # fail lần 1, ok lần 2

    def side_effect_tool(req: dict[str, Any]) -> dict[str, Any]:
        runs["side_effect"] += 1  # đếm side-effect: KHÔNG được chạy 2 lần
        return {"ok": True, "applied": runs["side_effect"]}

    kernel.register_tool("echo", echo_tool)
    kernel.register_tool("flaky", flaky_tool)
    kernel.register_tool("danger", side_effect_tool)

    # --- Bước 1: 1 middleware ---
    print("\n[1] Cắm LoggingMiddleware bằng kernel.use() — 0 sửa execute_tool:")
    kernel.use(LoggingMiddleware(log))
    r = kernel.execute_tool("echo", {"x": 1})
    print("    result:", r)
    print("    log:   ", log)
    assert r["ok"] and log == ["-> echo", "<- echo ok=True"]

    # --- Bước 2: chồng thêm middleware — composition, không conflict ---
    print("\n[2] Chồng thêm PolicyGate + RetryMiddleware (composition, không inheritance):")
    kernel.use(PolicyGate(deny={"forbidden"}))
    kernel.use(RetryMiddleware(attempts=3))
    log.clear()
    r2 = kernel.execute_tool("flaky", {})
    print("    flaky (fail lần 1, ok lần 2) ->", r2)
    print("    log:", log)
    assert r2["ok"] and r2["tries"] == 2, "Retry phải chạy lại tới khi ok"

    # --- Bước 3: short-circuit của policy gate ---
    print("\n[3] PolicyGate short-circuit: tool bị deny KHÔNG bao giờ chạy:")
    r3 = kernel.execute_tool("forbidden", {})
    print("    ->", r3)
    assert r3["ok"] is False and r3["policy_block"] is True

    # --- Bước 4: THÊM middleware mới (BudgetGate) — invariant OCP ---
    import inspect
    et_src_before = inspect.getsource(AgentKernel.execute_tool)
    print("\n[4] THÊM BudgetGate (middleware MỚI) bằng 1 dòng kernel.use():")
    kernel.use(BudgetGate(max_calls=2))
    r_a = kernel.execute_tool("echo", {"i": 1})
    r_b = kernel.execute_tool("echo", {"i": 2})
    r_c = kernel.execute_tool("echo", {"i": 3})  # vượt budget
    print("    call#1:", r_a.get("ok"), "| call#2:", r_b.get("ok"), "| call#3:", r_c)
    assert r_a["ok"] and r_b["ok"] and r_c["ok"] is False and r_c["error"] == "budget exceeded"
    et_src_after = inspect.getsource(AgentKernel.execute_tool)
    assert et_src_before == et_src_after, "execute_tool KHÔNG được sửa khi thêm middleware!"
    print("    OK: execute_tool() KHÔNG đổi 1 dòng (closed for modification).")

    # --- Bước 5: fail-open + latch — advisory raise không làm tool chạy đôi ---
    print("\n[5] fail-open + _LatchedNext: middleware advisory HỎNG bị skip,")
    print("    và tool side-effect chỉ chạy ĐÚNG 1 lần (không double-apply):")
    k2 = AgentKernel()
    k2.register_tool("danger", side_effect_tool)
    k2.use(BrokenTelemetry())           # advisory, sẽ raise sau khi gọi nxt
    runs["side_effect"] = 0
    r5 = k2.execute_tool("danger", {})
    print("    result:", r5, "| side-effect chạy", runs["side_effect"], "lần | skipped:", k2.skipped)
    assert r5["ok"] is True, "fail-open middleware raise -> phải skip, giữ inner result"
    assert runs["side_effect"] == 1, "tool non-idempotent KHÔNG được chạy 2 lần (latch)"
    assert k2.skipped == ["broken_telemetry"]

    print("\n[KẾT] Mọi concern là 1 decorator độc lập, cắm bằng use(); chokepoint bất biến. OCP đạt.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
