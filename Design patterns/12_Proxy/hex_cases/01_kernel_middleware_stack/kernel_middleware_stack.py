# -*- coding: utf-8 -*-
"""
Case 01 — Middleware Chain as Proxy Stack (Proxy pattern, biến thể stacked)

Bản DISTILL TRUNG THỰC của cơ chế xếp chồng middleware quanh execute_tool
trong hex_agent. Mỗi middleware là một Proxy đứng cùng interface với tool
handler thật (RealSubject), chèn cross-cutting logic (auth/policy, rate-limit,
retry, timing), rồi delegate cho tầng kế tiếp (`nxt`). Client (vòng lặp agent)
chỉ gọi execute_tool, KHÔNG biết có bao nhiêu proxy ở giữa.

NGUỒN THẬT (đã mở file kiểm chứng):
  - core/middleware.py:8           ToolHandler = Callable[[ToolRequest], dict]
  - core/middleware.py:11-22       ToolMiddleware protocol — interface Proxy: __call__(request, nxt)
  - core/kernel.py:24-46           _LatchedNext — one-shot proxy quanh inner handler (fail-open guard)
  - core/kernel.py:49-73           _wrap — bind 1 middleware quanh nxt (fail-closed vs fail-open)
  - core/kernel.py:152-177         core(req) — RealSubject: resolve + execute tool, đóng gói envelope
  - core/kernel.py:192-194         lắp chuỗi: for mw in reversed(self._middlewares): handler = _wrap(mw, handler)
  - middleware/policy.py:9-21      PolicyGate — Protection Proxy (deny-list, short-circuit)
  - middleware/budget.py:10-23     BudgetGuard — Rate-limit Proxy (chặn lặp cùng tool)
  - middleware/retry.py:23-33      Retry — Smart Reference Proxy (gọi nxt lại khi non-ok)
  - middleware/timing.py:10-26     TimingLog — Smart Reference Proxy (đo thời gian, fail_open)

LƯỢC BỎ so với bản thật:
  - Không có EventBus / publish telemetry, không có CapabilityRegistry / ports.
  - Không có deep-copy args, không có lineage/context, không có CapabilityResult.
  - LLM/DB/network/file -> thay bằng một dict tool đơn giản đếm số lần gọi.
  - Giữ NGUYÊN cấu trúc Proxy: cùng interface, pre-check, delegate, post-process,
    chuỗi xếp chồng theo reversed order, và phân biệt fail-closed / fail-open.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


# ============================================================
# SUBJECT — interface chung cho RealSubject lẫn mọi Proxy
# (distill core/middleware.py:8 + core/schemas.py:28-33)
# ============================================================
@dataclass(frozen=True)
class ToolRequest:
    """Yêu cầu tool. Bản thật có thêm context/request_id (schemas.py:28-33)."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)


# ToolHandler là "Subject interface": một callable nhận ToolRequest -> envelope dict.
# RealSubject và mọi Proxy đều phơi ra ĐÚNG interface này.
ToolHandler = Callable[[ToolRequest], dict[str, Any]]


# ToolMiddleware (Proxy) interface — distill core/middleware.py:11-22.
# Mỗi middleware là callable __call__(request, nxt): có thể act trước/sau,
# short-circuit (không gọi nxt), hoặc sửa envelope rồi trả về.
#   - fail_open = True  -> advisory: nếu raise thì kernel BỎ QUA, dùng kết quả inner.
#   - vắng / False      -> blocking: raise lan ra biên kernel (ok=False).


# ============================================================
# REAL SUBJECT — tool executor thật (distill core/kernel.py:152-177)
# ============================================================
class ToolCore:
    """RealSubject "naive": chỉ biết chạy tool, KHÔNG biết về proxy nào.

    Thay cho registry.resolve_tool(...).executor.execute(req) ở bản thật,
    ta dùng một bảng tool đơn giản và đếm số lần thực thi để chứng minh
    proxy chặn/đi-qua đúng chỗ."""

    def __init__(self) -> None:
        self.executions: list[str] = []  # log mọi lần tool THẬT chạy

    def __call__(self, request: ToolRequest) -> dict[str, Any]:
        self.executions.append(request.name)
        # Tool "search" được dàn xếp để fail 1 lần đầu rồi ok — minh hoạ Retry.
        if request.name == "flaky_search" and self.executions.count("flaky_search") == 1:
            return {"ok": False, "capability": request.name, "data": {}, "error": "transient",
                    "metadata": {"kind": "read"}}
        return {"ok": True, "capability": request.name,
                "data": {"echo": request.args}, "error": None, "metadata": {"kind": "read"}}


# ============================================================
# PROXY 1 — PolicyGate (Protection Proxy) distill middleware/policy.py:9-21
# ============================================================
class PolicyGate:
    """Chặn tool nằm trong deny-list TRƯỚC khi nó chạy; nếu không thì delegate."""

    def __init__(self, *, deny: set[str] | None = None,
                 on_block: Callable[[ToolRequest], None] | None = None) -> None:
        self.deny = set(deny or ())
        self.on_block = on_block

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]:
        if request.name in self.deny:                       # pre-check
            if self.on_block:
                self.on_block(request)
            return {"ok": False, "capability": request.name, "data": {},
                    "error": f"Blocked by policy: {request.name}",
                    "metadata": {"policy_block": True}}      # short-circuit, KHÔNG gọi nxt
        return nxt(request)                                 # delegate -> tầng trong


# ============================================================
# PROXY 2 — BudgetGuard (Rate-limit Proxy) distill middleware/budget.py:10-23
# ============================================================
class BudgetGuard:
    """Chặn khi cùng (name,args) bị gọi lặp quá ngưỡng — chống flood/loop."""

    def __init__(self, *, max_same: int = 2,
                 on_block: Callable[[ToolRequest], None] | None = None) -> None:
        self.max_same = max_same
        self.on_block = on_block
        self._counts: dict[str, int] = {}

    @staticmethod
    def _key(request: ToolRequest) -> str:
        import json
        # distill discipline/budget.py:63-67 — Budget.tool_key
        return request.name + ":" + json.dumps(request.args, sort_keys=True)

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]:
        key = self._key(request)
        self._counts[key] = self._counts.get(key, 0) + 1      # record_tool_call
        if self._counts[key] > self.max_same:                 # same_tool_exceeded
            if self.on_block:
                self.on_block(request)
            return {"ok": False, "capability": request.name, "data": {},
                    "error": "Same-tool budget exceeded.",
                    "metadata": {"budget_block": True}}        # short-circuit
        return nxt(request)                                    # delegate


# ============================================================
# PROXY 3 — Retry (Smart Reference Proxy) distill middleware/retry.py:23-33
# ============================================================
def _retryable(env: dict[str, Any]) -> bool:
    """distill middleware/retry.py:14-20 — không retry policy block, không retry
    effect không idempotent (re-run có thể double-apply)."""
    meta = env.get("metadata") or {}
    if meta.get("policy_block"):
        return False
    if meta.get("kind") == "effect" and meta.get("idempotent") is False:
        return False
    return True


class Retry:
    """Gọi nxt; nếu kết quả non-ok và còn lượt và retryable -> gọi nxt LẠI."""

    def __init__(self, *, attempts: int = 2) -> None:
        self.attempts = max(1, attempts)

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]:
        env = nxt(request)                                   # delegate lần 1
        tries = 1
        while isinstance(env, dict) and not env.get("ok") and tries < self.attempts and _retryable(env):
            env = nxt(request)                               # delegate lại — smart reference
            tries += 1
        return env


# ============================================================
# PROXY 4 — TimingLog (Smart Reference Proxy, ADVISORY) distill middleware/timing.py:10-26
# ============================================================
class TimingLog:
    fail_open = True  # advisory telemetry — lỗi của nó KHÔNG được làm hỏng tool call

    def __init__(self, sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.sink = sink

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]:
        t0 = time.perf_counter()
        env = nxt(request)                                   # delegate
        if self.sink:
            try:
                self.sink({"tool": request.name, "ok": (env or {}).get("ok"),
                           "ms": round((time.perf_counter() - t0) * 1000, 3)})
            except Exception:
                pass  # sink hỏng KHÔNG được biến 1 call thành công thành thất bại
        return env


# ============================================================
# CHAIN ASSEMBLY — distill core/kernel.py:24-73, 192-194
# ============================================================
class _LatchedNext:
    """One-shot proxy quanh inner handler — distill core/kernel.py:24-46.
    Chạy inner TỐI ĐA 1 lần; lần gọi sau replay kết quả/exception đã lưu mà
    KHÔNG chạy lại tool. Bảo vệ middleware fail-open raise SAU khi đã gọi nxt
    khỏi việc double-run tool không idempotent."""

    __slots__ = ("_nxt", "_ran", "_result", "_exc")

    def __init__(self, nxt: ToolHandler) -> None:
        self._nxt = nxt
        self._ran = False
        self._result: Any = None
        self._exc: Exception | None = None

    def __call__(self, request: ToolRequest) -> dict[str, Any]:
        if not self._ran:
            self._ran = True
            try:
                self._result = self._nxt(request)
            except Exception as exc:
                self._exc = exc
        if self._exc is not None:
            raise self._exc
        return self._result


def _wrap(middleware, nxt: ToolHandler,
          on_skip: Callable[[Any, Exception], None] | None = None) -> ToolHandler:
    """Bind 1 middleware quanh nxt — distill core/kernel.py:49-73.

    Mặc định fail-closed: middleware raise -> lan ra ngoài.
    Nếu middleware.fail_open is True (advisory): raise -> BỎ QUA nó, tiếp tục với
    kết quả inner (đã latch one-shot để raise-sau-nxt không double-run tool)."""
    if getattr(middleware, "fail_open", False) is not True:
        def handler(request: ToolRequest) -> dict[str, Any]:
            return middleware(request, nxt)          # tránh late-binding closure bug
        return handler

    def handler(request: ToolRequest) -> dict[str, Any]:
        latched = _LatchedNext(nxt)
        try:
            return middleware(request, latched)
        except Exception as exc:                     # advisory hỏng -> skip, giữ inner result
            if on_skip is not None:
                on_skip(middleware, exc)
            return latched(request)
    return handler


class Kernel:
    """Client-facing chokepoint — distill core/kernel.py AgentKernel.

    Đăng ký middleware theo thứ tự outer -> inner (use()). Khi execute_tool,
    lắp chuỗi proxy quanh `core` (RealSubject) theo reversed order, rồi gọi.
    Client KHÔNG biết có proxy nào ở giữa."""

    def __init__(self, core: ToolHandler) -> None:
        self._core = core
        self._middlewares: list = []
        self.skipped: list[str] = []  # log middleware advisory bị skip

    def use(self, middleware) -> None:                # distill kernel.py:100-104
        self._middlewares.append(middleware)

    def execute_tool(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        request = ToolRequest(name=name, args=args or {})

        def on_skip(mw: Any, exc: Exception) -> None:
            self.skipped.append(type(mw).__name__)

        handler: ToolHandler = self._core
        for mw in reversed(self._middlewares):        # distill kernel.py:192-194
            handler = _wrap(mw, handler, on_skip=on_skip)
        try:
            envelope = handler(request)
        except Exception as exc:                       # middleware fail-closed raise -> biên kernel
            envelope = {"ok": False, "capability": request.name,
                        "error": str(exc), "metadata": {"kernel_error": True}}
        return envelope


# ============================================================
# DEMO
# ============================================================
def demo() -> None:
    print("=" * 64)
    print("CASE 01 — Middleware Chain as Proxy Stack (hex_agent)")
    print("=" * 64)

    core = ToolCore()
    timings: list[dict[str, Any]] = []
    kernel = Kernel(core)
    # Thứ tự đăng ký = outer -> inner (giống bootstrap.py:34-53):
    #   TimingLog (ngoài cùng) -> PolicyGate -> BudgetGuard -> Retry -> core
    kernel.use(TimingLog(sink=timings.append))
    kernel.use(PolicyGate(deny={"terminal_run"}))
    kernel.use(BudgetGuard(max_same=2))
    kernel.use(Retry(attempts=3))

    print("\n[1] Gọi tool hợp lệ 'read_file' — đi xuyên qua TẤT CẢ proxy tới core.")
    r1 = kernel.execute_tool("read_file", {"path": "a.txt"})
    print("    envelope.ok =", r1["ok"], "| data =", r1["data"])
    assert r1["ok"] is True
    assert core.executions == ["read_file"], "core phải chạy đúng 1 lần"
    print("    -> Client chỉ gọi execute_tool, KHÔNG biết 4 proxy ở giữa (transparent).")

    print("\n[2] PolicyGate (Protection Proxy) chặn 'terminal_run' TRƯỚC khi tới core.")
    before = len(core.executions)
    r2 = kernel.execute_tool("terminal_run", {"argv": ["rm", "-rf", "/"]})
    print("    envelope.ok =", r2["ok"], "| error =", r2["error"])
    assert r2["ok"] is False and r2["metadata"]["policy_block"] is True
    assert len(core.executions) == before, "tool bị chặn KHÔNG được chạm tới core"
    print("    -> RealSubject KHÔNG bao giờ thấy request bị deny (short-circuit).")

    print("\n[3] Retry (Smart Reference Proxy) gọi lại core khi gặp lỗi transient.")
    r3 = kernel.execute_tool("flaky_search", {"q": "bbb"})
    n_flaky = core.executions.count("flaky_search")
    print("    envelope.ok =", r3["ok"], "| số lần core chạy 'flaky_search' =", n_flaky)
    assert r3["ok"] is True and n_flaky == 2, "Retry phải gọi nxt 2 lần (fail->ok)"
    print("    -> Client thấy 1 lời gọi; proxy âm thầm thử lại lần 2.")

    print("\n[4] BudgetGuard (Rate-limit Proxy) chặn khi lặp cùng (name,args) > max_same=2.")
    kernel.execute_tool("scan", {"x": 1})  # lần 1
    kernel.execute_tool("scan", {"x": 1})  # lần 2
    r4 = kernel.execute_tool("scan", {"x": 1})  # lần 3 -> vượt ngưỡng
    print("    lần 3: envelope.ok =", r4["ok"], "| error =", r4["error"])
    assert r4["ok"] is False and r4["metadata"]["budget_block"] is True
    print("    -> Cùng args lặp lần 3 bị chặn; nhưng đổi args thì lại đi qua:")
    r4b = kernel.execute_tool("scan", {"x": 2})
    assert r4b["ok"] is True
    print("       scan{x:2}.ok =", r4b["ok"], "(key khác -> không tính chung)")

    print("\n[5] TimingLog (advisory, fail_open) — đo thời gian MỌI call ở vòng ngoài cùng.")
    print("    số bản ghi timing =", len(timings), "| ví dụ:", timings[0])
    assert len(timings) >= 5, "TimingLog phải bọc ngoài cùng và ghi mọi call"

    # ----- Đối chứng: KHÔNG dùng Proxy -> client phải tự lo mọi concern -----
    print("\n[6] ĐỐI CHỨNG — nếu KHÔNG có proxy, client phải tự nhúng auth/limit/retry:")
    naive_core = ToolCore()

    def naive_client_call(name: str, args: dict[str, Any], deny: set[str], counts: dict[str, int]) -> dict:
        # client tự kiểm tra policy
        if name in deny:
            return {"ok": False, "error": "blocked"}
        # client tự đếm budget
        key = name + str(sorted(args.items()))
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > 2:
            return {"ok": False, "error": "budget"}
        # client tự retry
        env = naive_core(ToolRequest(name, args))
        if not env.get("ok"):
            env = naive_core(ToolRequest(name, args))
        return env

    counts: dict[str, int] = {}
    naive_client_call("read_file", {"p": 1}, {"terminal_run"}, counts)
    print("    -> Logic auth+budget+retry rò rỉ vào client; lặp lại ở MỌI nơi gọi tool.")
    print("       Thêm 1 concern mới (vd: condense) = sửa MỌI call site -> vi phạm SRP/OCP.")
    print("    Với Proxy: chỉ cần kernel.use(NewProxy()) một lần, client không đổi.")

    print("\nTẤT CẢ assert PASS. Proxy stack hoạt động đúng & trong suốt với client.")


if __name__ == "__main__":
    demo()
