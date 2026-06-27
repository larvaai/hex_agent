"""
Case 01 — Middleware Pipeline: Pluggable Tool Execution Guards (Strategy)
========================================================================

Bản DISTILL TRUNG THỰC từ hex_agent. Nguồn thật:
  - core/middleware.py:11-22   -> ToolMiddleware Protocol (interface của Strategy)
  - core/kernel.py:49-73       -> _wrap(): bind 1 middleware quanh nxt, xử lý fail-open vs fail-closed
  - core/kernel.py:192-194     -> chain: for mw in reversed(self._middlewares): handler = _wrap(mw, handler)
  - core/kernel.py:100-104     -> AgentKernel.use(): inject 1 strategy vào pipeline
  - core/bootstrap.py:28-53    -> _install_middleware(): lắp strategy theo config, thứ tự outer->inner
  - middleware/retry.py:23-33  -> Retry strategy (gọi lại nxt khi non-ok, bỏ qua effect non-idempotent)
  - middleware/policy.py:9-21  -> PolicyGate strategy (chặn theo deny-set TRƯỚC khi chạy)
  - middleware/budget.py:10-23 -> BudgetGuard strategy (đếm cùng-tool, chặn khi vượt ngân sách)
  - middleware/timing.py:10-26 -> TimingLog strategy (fail_open=True, advisory telemetry)

Strategy ở đây xuất hiện ở DẠNG ĐẶC BIỆT: mỗi middleware là một strategy "interceptor"
cùng chữ ký __call__(request, nxt) -> dict. Context (kernel) KHÔNG dùng if/elif để chọn
1 strategy — nó COMPOSE nhiều strategy thành một chain. Đây là Strategy + Decorator/Pipeline
(xem bảng so sánh trong 21_Strategy.md).

Distill này thay LLM/registry/event-bus thật bằng:
  - một "tool core" giả lập gọi callable đăng ký theo tên (thay registry.resolve_tool)
  - dùng dict envelope {"ok": bool, ...} y như code thật trả về

CHẠY: python3 middleware_chain.py   (exit 0, không traceback)
"""
from __future__ import annotations

import time
from typing import Any, Callable, Protocol

# Envelope là dict thuần, giống core/schemas.CapabilityResult.as_dict() rút gọn.
Envelope = dict[str, Any]
ToolHandler = Callable[["ToolRequest"], Envelope]


class ToolRequest:
    """Rút gọn của core/schemas.ToolRequest: chỉ giữ name + args."""

    def __init__(self, name: str, args: dict[str, Any] | None = None) -> None:
        self.name = name
        self.args = args or {}


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY INTERFACE — ToolMiddleware Protocol (core/middleware.py:11-22)
# ─────────────────────────────────────────────────────────────────────────────
class ToolMiddleware(Protocol):
    """Nhận request và nxt (handler bên trong). Có thể: hành động trước/sau,
    short-circuit (return mà không gọi nxt), hoặc sửa envelope.

    Tùy chọn (đọc bằng getattr, KHÔNG ép buộc — Protocol là cấu trúc):
    middleware CÓ THỂ khai báo ``fail_open = True`` để tự đánh dấu là *advisory*
    (telemetry/condense). Nếu một fail-open middleware raise, kernel BỎ QUA nó và
    tiếp tục với kết quả bên trong, thay vì làm hỏng cả call. Mặc định = blocking:
    raise sẽ lan tới biên kernel thành ok=False.
    """

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> Envelope: ...


# ─────────────────────────────────────────────────────────────────────────────
# CONCRETE STRATEGIES — mỗi middleware là 1 thuật toán "guard" độc lập
# ─────────────────────────────────────────────────────────────────────────────
class TimingLog:
    """Advisory telemetry. Đo wall-time quanh call. fail_open=True (timing.py:10-26).
    Lỗi của nó KHÔNG được biến một call thành công thành thất bại."""

    fail_open = True  # advisory: failure phải không bao giờ block tool call

    def __init__(self, sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.sink = sink

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> Envelope:
        t0 = time.perf_counter()
        env = nxt(request)
        if self.sink:
            try:
                self.sink({"tool": request.name, "ok": (env or {}).get("ok"),
                           "ms": round((time.perf_counter() - t0) * 1000, 3)})
            except Exception:
                pass  # metrics sink hỏng không được làm hỏng tool call
        return env


class PolicyGate:
    """Fail-closed guard. Chặn tool theo deny-set TRƯỚC khi nó chạy (policy.py:9-21).
    Short-circuit: return ngay, KHÔNG gọi nxt."""

    def __init__(self, deny: set[str] | None = None) -> None:
        self.deny = set(deny or ())

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> Envelope:
        if request.name in self.deny:
            return {"ok": False, "capability": request.name, "data": {},
                    "error": f"Blocked by policy: {request.name}",
                    "metadata": {"policy_block": True}}
        return nxt(request)


class Retry:
    """Fail-closed guard. Gọi LẠI nxt khi kết quả non-ok, có giới hạn attempts
    (retry.py:23-33). KHÔNG retry policy_block, KHÔNG retry effect non-idempotent
    (chạy lại side-effect có thể double-apply)."""

    def __init__(self, attempts: int = 2) -> None:
        self.attempts = max(1, attempts)

    @staticmethod
    def _retryable(env: Envelope) -> bool:
        meta = env.get("metadata") or {}
        if meta.get("policy_block"):
            return False
        if meta.get("kind") == "effect" and meta.get("idempotent") is False:
            return False
        return True

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> Envelope:
        env = nxt(request)
        tries = 1
        while isinstance(env, dict) and not env.get("ok") and tries < self.attempts and self._retryable(env):
            env = nxt(request)
            tries += 1
        return env


class BudgetGuard:
    """Fail-closed guard. Đếm số lần gọi CÙNG một tool; chặn khi vượt ngân sách
    (budget.py:10-23). State (counter) là per-instance/per-run — KHÔNG share toàn
    cục để tránh leak giữa các run (xem cảnh báo bootstrap.py:31-32)."""

    def __init__(self, max_calls: int = 1) -> None:
        self.max_calls = max(1, max_calls)
        self._counts: dict[str, int] = {}

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> Envelope:
        key = request.name  # code thật key theo (name, args) qua Budget.tool_key
        self._counts[key] = self._counts.get(key, 0) + 1
        if self._counts[key] > self.max_calls:
            return {"ok": False, "capability": request.name, "data": {},
                    "error": "Same-tool budget exceeded.",
                    "metadata": {"budget_block": True}}
        return nxt(request)


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITION — _wrap() (core/kernel.py:49-73)
# ─────────────────────────────────────────────────────────────────────────────
class _LatchedNext:
    """One-shot proxy quanh nxt (kernel.py:24-46). Chạy nxt tối đa 1 lần; lần gọi
    sau replay kết quả/exception đầu tiên mà KHÔNG chạy lại tool. Bảo vệ fail-open
    middleware (raise SAU khi đã gọi nxt) khỏi chạy đúp tool non-idempotent."""

    def __init__(self, nxt: ToolHandler) -> None:
        self._nxt = nxt
        self._ran = False
        self._result: Any = None
        self._exc: Exception | None = None

    def __call__(self, request: ToolRequest) -> Envelope:
        if not self._ran:
            self._ran = True
            try:
                self._result = self._nxt(request)
            except Exception as exc:
                self._exc = exc
        if self._exc is not None:
            raise self._exc
        return self._result


def _wrap(middleware: ToolMiddleware, nxt: ToolHandler,
          on_skip: Callable[[Any, Exception], None] | None = None) -> ToolHandler:
    """Bind 1 middleware quanh handler kế tiếp.

    Mặc định fail-closed: middleware raise sẽ lan ra biên. Middleware opt-in
    ``fail_open = True`` (advisory) sẽ bị BỎ QUA khi raise: chain tiếp tục với
    kết quả bên trong; nxt của nó được latch (one-shot) để raise-sau-nxt không
    chạy lại tool. Chỉ nhánh fail-open mới latch."""
    if getattr(middleware, "fail_open", False) is not True:
        def handler(request: ToolRequest) -> Envelope:
            return middleware(request, nxt)
        return handler

    def handler(request: ToolRequest) -> Envelope:
        latched = _LatchedNext(nxt)
        try:
            return middleware(request, latched)
        except Exception as exc:
            if on_skip is not None:
                on_skip(middleware, exc)
            return latched(request)
    return handler


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT — AgentKernel (core/kernel.py:76-225, rút gọn)
# ─────────────────────────────────────────────────────────────────────────────
class AgentKernel:
    """Context giữ danh sách middleware (strategy) và compose chúng quanh 1 chokepoint
    execute_tool. Đăng ký tool = callable theo tên (thay registry.resolve_tool)."""

    def __init__(self) -> None:
        self._middlewares: list[ToolMiddleware] = []
        self._tools: dict[str, Callable[[ToolRequest], Envelope]] = {}
        self._descriptors: dict[str, dict[str, Any]] = {}
        self.skipped: list[tuple[str, str]] = []  # (middleware, error) đã skip

    def use(self, middleware: ToolMiddleware) -> None:
        """Inject 1 strategy. Thứ tự đăng ký = outer -> inner (kernel.py:100-104)."""
        self._middlewares.append(middleware)

    def register_tool(self, name: str, fn: Callable[[ToolRequest], Envelope],
                      *, kind: str = "tool", idempotent: bool = True) -> None:
        self._tools[name] = fn
        self._descriptors[name] = {"kind": kind, "idempotent": idempotent}

    def execute_tool(self, name: str, args: dict[str, Any] | None = None) -> Envelope:
        request = ToolRequest(name, args)

        def core(req: ToolRequest) -> Envelope:
            desc = self._descriptors.get(req.name, {"kind": "tool", "idempotent": True})
            fn = self._tools.get(req.name)
            if fn is None:
                return {"ok": False, "capability": req.name, "data": {},
                        "error": f"no such tool: {req.name}", "metadata": {}}
            try:
                result = fn(req)
            except Exception as exc:  # tool không bao giờ làm sập kernel
                result = {"ok": False, "capability": req.name, "data": {},
                          "error": str(exc), "metadata": {}}
            meta = result.setdefault("metadata", {})
            meta.setdefault("kind", desc["kind"])
            meta.setdefault("idempotent", desc["idempotent"])
            return result

        def on_skip(mw: Any, exc: Exception) -> None:
            self.skipped.append((type(mw).__name__, str(exc)))

        handler = core
        for mw in reversed(self._middlewares):  # kernel.py:192-194
            handler = _wrap(mw, handler, on_skip=on_skip)
        try:
            envelope = handler(request)
        except Exception as exc:  # middleware không bao giờ làm sập biên kernel
            envelope = {"ok": False, "capability": request.name, "data": {},
                        "error": str(exc), "metadata": {"kernel_error": True}}
        return envelope


# ─────────────────────────────────────────────────────────────────────────────
# BUILDER — _install_middleware() theo config (bootstrap.py:28-53)
# ─────────────────────────────────────────────────────────────────────────────
def build_kernel(config: dict[str, Any]) -> AgentKernel:
    """Lắp strategy từ config theo thứ tự outer->inner: timing, policy, retry.
    Inert nếu section vắng mặt — đúng tinh thần config-driven của Strategy."""
    kernel = AgentKernel()
    mw = config.get("middleware") or {}
    if (mw.get("timing") or {}).get("enabled"):
        kernel.use(TimingLog(sink=mw["timing"].get("sink")))
    policy = mw.get("policy") or {}
    if policy.get("enabled"):
        kernel.use(PolicyGate(deny=set(policy.get("deny") or ())))
    retry = mw.get("retry") or {}
    if retry.get("enabled"):
        kernel.use(Retry(attempts=int(retry.get("attempts", 2))))
    budget = mw.get("budget") or {}
    if budget.get("enabled"):
        kernel.use(BudgetGuard(max_calls=int(budget.get("max_calls", 1))))
    return kernel


# ─────────────────────────────────────────────────────────────────────────────
# Tool giả lập: một tool "flaky" hỏng N lần đầu rồi mới ok (để Retry tỏa sáng).
# ─────────────────────────────────────────────────────────────────────────────
def make_flaky_tool(fail_first: int):
    state = {"calls": 0}

    def tool(req: ToolRequest) -> Envelope:
        state["calls"] += 1
        if state["calls"] <= fail_first:
            return {"ok": False, "capability": req.name, "data": {},
                    "error": "transient timeout", "metadata": {}}
        return {"ok": True, "capability": req.name,
                "data": {"value": req.args.get("x", 0) * 2, "calls": state["calls"]},
                "metadata": {}}
    return tool


def make_ok_tool():
    def tool(req: ToolRequest) -> Envelope:
        return {"ok": True, "capability": req.name, "data": {"echo": req.args}, "metadata": {}}
    return tool


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — khi KHÔNG dùng Strategy: nhồi if/elif vào Context
# ─────────────────────────────────────────────────────────────────────────────
class HardcodedKernel:
    """Anti-pattern: Context tự if/elif mọi guard. Thêm 1 guard mới = sửa Context.
    Không reorder được, không test riêng từng guard, không tắt/bật theo config."""

    def __init__(self, *, do_retry: bool, deny: set[str]) -> None:
        self.do_retry = do_retry
        self.deny = deny

    def execute_tool(self, name: str, tool: Callable[[ToolRequest], Envelope],
                     args: dict[str, Any] | None = None) -> Envelope:
        req = ToolRequest(name, args)
        if name in self.deny:                       # policy hardcoded
            return {"ok": False, "error": f"Blocked by policy: {name}", "metadata": {}}
        env = tool(req)
        if self.do_retry:                           # retry hardcoded
            tries = 1
            while not env.get("ok") and tries < 2:
                env = tool(req)
                tries += 1
        # muốn thêm budget/timing? -> phải mở lại class này mà sửa. Đó là cái giá.
        return env


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 72)
    print("CASE 01 — Middleware Pipeline (Strategy + Pipeline)")
    print("=" * 72)

    timings: list[dict[str, Any]] = []

    print("\n[1] Cùng MỘT tool 'mul', chạy qua 3 cấu hình pipeline khác nhau (config-driven)\n")

    # --- Cấu hình A: không guard nào -> fail-fast ---
    kA = build_kernel({"middleware": {}})
    kA.register_tool("mul", make_flaky_tool(fail_first=1))
    rA = kA.execute_tool("mul", {"x": 5})
    print(f"  A) pipeline rỗng        -> ok={rA['ok']!s:5} error={rA.get('error')!r}")
    assert rA["ok"] is False, "không có Retry: hỏng lần đầu là thua luôn"

    # --- Cấu hình B: bật Retry -> vượt qua transient ---
    kB = build_kernel({"middleware": {
        "timing": {"enabled": True, "sink": timings.append},
        "retry": {"enabled": True, "attempts": 3},
    }})
    kB.register_tool("mul", make_flaky_tool(fail_first=1))
    rB = kB.execute_tool("mul", {"x": 5})
    print(f"  B) timing+retry         -> ok={rB['ok']!s:5} data={rB['data']}")
    assert rB["ok"] is True, "Retry phải vượt được 1 lần fail transient"
    assert rB["data"]["value"] == 10
    assert rB["data"]["calls"] == 2, "tool được gọi 2 lần: fail rồi ok"

    # --- Cấu hình C: bật PolicyGate chặn 'mul' -> short-circuit, tool KHÔNG chạy ---
    counter = {"n": 0}

    def counting_tool(req: ToolRequest) -> Envelope:
        counter["n"] += 1
        return {"ok": True, "capability": req.name, "data": {}, "metadata": {}}

    kC = build_kernel({"middleware": {
        "policy": {"enabled": True, "deny": ["mul"]},
        "retry": {"enabled": True, "attempts": 3},
    }})
    kC.register_tool("mul", counting_tool)
    rC = kC.execute_tool("mul", {"x": 5})
    print(f"  C) policy(deny=mul)     -> ok={rC['ok']!s:5} error={rC.get('error')!r}")
    assert rC["ok"] is False and rC["metadata"]["policy_block"] is True
    assert counter["n"] == 0, "PolicyGate short-circuit: tool không bao giờ chạy"
    print(f"     (tool thật được gọi {counter['n']} lần — bị chặn trước khi chạy)")

    print("\n[2] Bất biến quan trọng: Retry KHÔNG được chạy lại effect non-idempotent\n")
    applied = {"n": 0}

    def charge_card(req: ToolRequest) -> Envelope:
        applied["n"] += 1  # side-effect: trừ tiền!
        return {"ok": False, "capability": req.name, "data": {},
                "error": "gateway 500", "metadata": {}}

    kD = build_kernel({"middleware": {"retry": {"enabled": True, "attempts": 3}}})
    kD.register_tool("charge", charge_card, kind="effect", idempotent=False)
    rD = kD.execute_tool("charge", {"amount": 100})
    print(f"  charge (effect, non-idempotent) -> ok={rD['ok']!s:5} lần-trừ-tiền={applied['n']}")
    assert applied["n"] == 1, "Retry phải DỪNG: effect non-idempotent không được double-apply"
    print("     Retry tôn trọng metadata kind=effect/idempotent=False -> chỉ chạy 1 lần.")

    print("\n[3] fail-open advisory: TimingLog raise -> bị SKIP, kết quả tool vẫn về\n")

    class BoomTiming:
        fail_open = True

        def __call__(self, request: ToolRequest, nxt: ToolHandler) -> Envelope:
            env = nxt(request)            # đã chạy tool xong
            raise RuntimeError("telemetry backend down")  # rồi mới nổ

        # noqa

    kE = AgentKernel()
    kE.use(BoomTiming())
    kE.register_tool("ping", make_ok_tool())
    rE = kE.execute_tool("ping", {"a": 1})
    print(f"  ping qua BoomTiming     -> ok={rE['ok']!s:5} skipped={kE.skipped}")
    assert rE["ok"] is True, "advisory raise phải bị skip, KHÔNG làm hỏng call"
    assert kE.skipped and kE.skipped[0][0] == "BoomTiming"
    print("     Advisory middleware nổ -> kernel bỏ qua, trả kết quả tool bên trong (fail-open).")

    print("\n[4] ĐỐI CHỨNG — HardcodedKernel (không Strategy): mọi guard nhồi vào Context\n")
    hk = HardcodedKernel(do_retry=True, deny={"danger"})
    out = hk.execute_tool("mul", make_flaky_tool(fail_first=1), {"x": 3})
    print(f"  hardcoded mul (retry inline) -> ok={out['ok']}")
    print("     Muốn thêm BudgetGuard/TimingLog hay đổi thứ tự guard?")
    print("     -> phải MỞ LẠI class HardcodedKernel và sửa (vi phạm Open/Closed).")
    print("     Với pipeline Strategy: chỉ cần kernel.use(...) thêm — Context bất biến.")

    print("\n[5] Strategy có thể TÁI THỨ TỰ chỉ bằng thứ tự use() — Context không đổi\n")
    print(f"  timings thu được từ cấu hình B: {timings}")
    assert any(t["tool"] == "mul" for t in timings), "TimingLog (outermost) đã đo được call"

    print("\n" + "=" * 72)
    print("KẾT LUẬN: middleware = ConcreteStrategy cùng __call__(request, nxt).")
    print("kernel.use() = inject strategy. _wrap()+reversed() = compose thành 1 handler.")
    print("Đổi/bật/tắt/reorder guard = đổi config, KHÔNG sửa Context. Mọi assert PASS.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
