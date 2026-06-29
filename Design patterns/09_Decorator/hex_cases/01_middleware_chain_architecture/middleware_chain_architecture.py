"""
Case 01 — Chuỗi Middleware Decorator trong AgentKernel (Decorator, GoF Structural).

Bản DISTILL TRUNG THỰC từ code thật của hex_agent:
  - core/kernel.py:49-73     -> _wrap(): hàm "lắp" một middleware quanh handler kế tiếp (nxt).
  - core/kernel.py:152-194   -> execute_tool(): client dựng chuỗi decorator bằng cách
                                lặp reversed(self._middlewares) và bọc dần quanh `core`.
  - core/kernel.py:24-46     -> _LatchedNext: proxy caching một-lần quanh inner handler
                                (chống chạy lại tool khi advisory middleware raise sau nxt).
  - core/middleware.py:11-22 -> ToolMiddleware Protocol: interface decorator
                                __call__(request, nxt) -> dict.
  - core/bootstrap.py:28-53  -> _install_middleware(): thứ tự lắp ráp outer->inner
                                (timing -> policy -> retry -> condense).
  - middleware/timing.py:10-26   -> TimingLog (ConcreteDecorator, fail_open=True).
  - middleware/policy.py:9-21    -> PolicyGate (ConcreteDecorator, guard/short-circuit).
  - middleware/retry.py:23-33    -> Retry (ConcreteDecorator, gọi nxt nhiều lần).
  - middleware/condense.py:11-30 -> CondenseResult (ConcreteDecorator, post-process, fail_open).

Ánh xạ vai trò Decorator:
  - Component interface     = handler ký hiệu `(request) -> dict`  (ToolHandler trong code thật).
  - ConcreteComponent       = `core` (executor lõi gọi tool thật).
  - ConcreteDecorator       = TimingLog / PolicyGate / Retry / CondenseResult.
  - has-a (inner)           = tham số `nxt` mà mỗi middleware giữ và delegate vào.
  - Decorator assembly      = _wrap() + vòng lặp reversed() trong execute_tool().
  - Client                  = execute_tool() (dựng & gọi chuỗi).

Lược bỏ so với bản thật (thay hạ tầng nặng bằng fake stdlib tối thiểu):
  - Không có EventBus/registry/CapabilityResult thật; "tool" chỉ là 1 dict callable.
  - condense thật dùng discipline.condense; ở đây cắt chuỗi đơn giản bằng slicing.
  - Bỏ deep-freeze, lineage, request_id ngẫu nhiên — không ảnh hưởng cấu trúc Decorator.

Chỉ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent, KHÔNG thư viện bên thứ ba.
Chạy: python3 middleware_chain_architecture.py  (thoát code 0, không traceback).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


# ──────────────────────────────────────────────────────────────────────────
# Component interface (ngầm định bằng type alias — giống ToolHandler trong code thật)
#   Một "handler" nhận request và trả về envelope dict. Mọi decorator giữ NGUYÊN
#   chữ ký này → client không phân biệt được lõi trần với lõi đã bọc.
# ──────────────────────────────────────────────────────────────────────────
Handler = Callable[["ToolRequest"], dict[str, Any]]


@dataclass(frozen=True)
class ToolRequest:
    """Bản rút gọn của core/schemas.py:28-33 — chỉ giữ name + args."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────
# _LatchedNext — distill của core/kernel.py:24-46.
#   Proxy "chạy nhiều nhất MỘT lần" quanh inner handler. Lần đầu chạy thật,
#   các lần sau replay kết quả/exception cũ → KHÔNG chạy lại tool.
#   Mục đích: advisory (fail_open) middleware lỡ raise SAU khi đã gọi nxt thì
#   nhánh skip-fallback không được phép chạy lại tool (non-idempotent).
# ──────────────────────────────────────────────────────────────────────────
class _LatchedNext:
    __slots__ = ("_nxt", "_ran", "_result", "_exc")

    def __init__(self, nxt: Handler) -> None:
        self._nxt = nxt
        self._ran = False
        self._result: Any = None
        self._exc: Exception | None = None

    def __call__(self, request: ToolRequest) -> dict[str, Any]:
        if not self._ran:
            self._ran = True
            try:
                self._result = self._nxt(request)
            except Exception as exc:  # lưu lại để replay, không chạy lại
                self._exc = exc
        if self._exc is not None:
            raise self._exc
        return self._result


# ──────────────────────────────────────────────────────────────────────────
# _wrap — distill của core/kernel.py:49-73.
#   Đây là LÕI của Decorator: lắp một middleware quanh `nxt` (inner), trả về
#   handler MỚI cùng chữ ký Component. Tách thành hàm riêng để tránh bug
#   late-binding closure khi lặp.
#
#   Posture (tư thế thất bại):
#     - fail-closed (mặc định): middleware raise -> propagate lên biên kernel.
#     - fail-open  (fail_open=True, advisory như timing/condense): raise -> BỎ QUA
#       middleware đó, chuỗi tiếp tục với kết quả inner (đã latch).
# ──────────────────────────────────────────────────────────────────────────
def _wrap(middleware, nxt: Handler, on_skip=None) -> Handler:
    if getattr(middleware, "fail_open", False) is not True:
        def handler(request: ToolRequest) -> dict[str, Any]:
            return middleware(request, nxt)
        return handler

    def handler(request: ToolRequest) -> dict[str, Any]:
        latched = _LatchedNext(nxt)
        try:
            return middleware(request, latched)
        except Exception as exc:  # advisory hỏng -> skip, giữ kết quả inner đã latch
            if on_skip is not None:
                on_skip(middleware, exc)
            return latched(request)
    return handler


# ──────────────────────────────────────────────────────────────────────────
# ConcreteComponent — lõi "execute_tool" (distill core/kernel.py:152-177).
#   Không biết gì về timing/policy/retry. Chỉ tra cứu tool và gọi nó.
# ──────────────────────────────────────────────────────────────────────────
class CoreExecutor:
    def __init__(self, tools: dict[str, Callable[[ToolRequest], dict[str, Any]]]) -> None:
        self._tools = tools

    def __call__(self, req: ToolRequest) -> dict[str, Any]:
        tool = self._tools.get(req.name)
        if tool is None:
            return {"ok": False, "capability": req.name, "data": {},
                    "error": f"No such tool: {req.name}", "metadata": {}}
        try:
            result = tool(req)
        except Exception as exc:  # tool không bao giờ được làm sập kernel
            return {"ok": False, "capability": req.name, "data": {},
                    "error": str(exc), "metadata": {"kernel_error": True}}
        # chuẩn hoá thành envelope thống nhất
        return {"ok": bool(result.get("ok", True)), "capability": req.name,
                "data": result.get("data", {}), "error": result.get("error"),
                "metadata": dict(result.get("metadata", {}))}


# ──────────────────────────────────────────────────────────────────────────
# ConcreteDecorator #1 — TimingLog (distill middleware/timing.py:10-26).
#   POST-decoration: đo wall-time SAU khi nxt trả về. fail_open=True (advisory).
# ──────────────────────────────────────────────────────────────────────────
class TimingLog:
    fail_open = True  # telemetry advisory — lỗi đo đạc KHÔNG được làm hỏng tool

    def __init__(self, sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.sink = sink

    def __call__(self, request: ToolRequest, nxt: Handler) -> dict[str, Any]:
        t0 = time.perf_counter()
        env = nxt(request)                      # delegate vào inner
        if self.sink:
            try:
                self.sink({"tool": request.name, "ok": (env or {}).get("ok"),
                           "ms": round((time.perf_counter() - t0) * 1000, 3)})
            except Exception:
                pass  # sink hỏng cũng không biến tool thành fail
        return env                              # trả envelope NGUYÊN, không sửa


# ──────────────────────────────────────────────────────────────────────────
# ConcreteDecorator #2 — PolicyGate (distill middleware/policy.py:9-21).
#   GUARD/PRE-condition: chặn TRƯỚC khi gọi nxt. Nếu deny -> short-circuit,
#   không bao giờ chạm inner handler.
# ──────────────────────────────────────────────────────────────────────────
class PolicyGate:
    def __init__(self, *, deny: set[str] | None = None,
                 on_block: Callable[[ToolRequest], None] | None = None) -> None:
        self.deny = set(deny or ())
        self.on_block = on_block

    def __call__(self, request: ToolRequest, nxt: Handler) -> dict[str, Any]:
        if request.name in self.deny:
            if self.on_block:
                self.on_block(request)
            return {"ok": False, "capability": request.name, "data": {},
                    "error": f"Blocked by policy: {request.name}",
                    "metadata": {"policy_block": True}}
        return nxt(request)                     # cho qua -> delegate


# ──────────────────────────────────────────────────────────────────────────
# ConcreteDecorator #3 — Retry (distill middleware/retry.py:23-33).
#   Gọi nxt NHIỀU LẦN khi kết quả !ok. Không bao giờ retry policy_block.
# ──────────────────────────────────────────────────────────────────────────
class Retry:
    def __init__(self, *, attempts: int = 2) -> None:
        self.attempts = max(1, attempts)

    @staticmethod
    def _retryable(env: dict[str, Any]) -> bool:
        # ĐƠN GIẢN HOÁ có chủ đích cho case "dựng chuỗi": chỉ giữ luật policy_block.
        # Bản THẬT (middleware/retry.py:14-20) còn 1 luật nữa: KHÔNG retry effect
        # non-idempotent (kind=="effect" và idempotent is False). Xem case 02
        # (concrete_middleware_decorator.py:53-59) để có _retryable ĐẦY ĐỦ 2 luật.
        meta = env.get("metadata") or {}
        return not meta.get("policy_block")

    def __call__(self, request: ToolRequest, nxt: Handler) -> dict[str, Any]:
        env = nxt(request)
        tries = 1
        while (isinstance(env, dict) and not env.get("ok")
               and tries < self.attempts and self._retryable(env)):
            env = nxt(request)                  # delegate lại vào inner, KHÔNG gọi tool trực tiếp
            tries += 1
        return env


# ──────────────────────────────────────────────────────────────────────────
# ConcreteDecorator #4 — CondenseResult (distill middleware/condense.py:11-30).
#   POST-process: cắt nhỏ data lớn. Bỏ qua llm.* . fail_open=True (advisory).
# ──────────────────────────────────────────────────────────────────────────
class CondenseResult:
    fail_open = True

    def __init__(self, *, max_chars: int = 2000) -> None:
        self.max_chars = max_chars

    def _shrink(self, value: Any) -> Any:
        # đệ quy như discipline.condense thật: cắt MỌI chuỗi dài ở mọi tầng.
        if isinstance(value, str):
            return value[: self.max_chars] + "…[condensed]" if len(value) > self.max_chars else value
        if isinstance(value, dict):
            return {k: self._shrink(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._shrink(v) for v in value]
        return value

    def __call__(self, request: ToolRequest, nxt: Handler) -> dict[str, Any]:
        env = nxt(request)
        if request.name.startswith("llm."):     # llm.* không bị cắt
            return env
        data = env.get("data")
        if isinstance(data, (dict, list, str)):
            env["data"] = self._shrink(data)
        return env


# ──────────────────────────────────────────────────────────────────────────
# Client — Kernel rút gọn: giữ danh sách middleware (use), dựng & gọi chuỗi.
#   distill core/kernel.py: use():100-104, execute_tool() build chain:192-196.
# ──────────────────────────────────────────────────────────────────────────
class Kernel:
    def __init__(self, tools: dict[str, Callable[[ToolRequest], dict[str, Any]]]) -> None:
        self._core = CoreExecutor(tools)
        self._middlewares: list = []
        self.skipped: list[str] = []  # ghi lại advisory bị skip (giống event middleware.skipped)

    def use(self, middleware) -> None:
        """Thứ tự đăng ký = outer -> inner (giống core/kernel.py:101)."""
        self._middlewares.append(middleware)

    def execute_tool(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        request = ToolRequest(name=name, args=dict(args or {}))

        def on_skip(mw: Any, exc: Exception) -> None:
            self.skipped.append(type(mw).__name__)

        # DỰNG CHUỖI DECORATOR: bắt đầu từ lõi, bọc dần từ inner ra outer.
        # reversed() để middleware đăng ký SỚM nhất nằm NGOÀI cùng.
        handler: Handler = self._core
        for mw in reversed(self._middlewares):
            handler = _wrap(mw, handler, on_skip=on_skip)

        try:
            return handler(request)
        except Exception as exc:  # middleware fail-closed không được làm sập biên kernel
            return {"ok": False, "capability": name, "data": {},
                    "error": str(exc), "metadata": {"kernel_error": True}}


# ──────────────────────────────────────────────────────────────────────────
# DEMO
# ──────────────────────────────────────────────────────────────────────────
def _echo_tool(req: ToolRequest) -> dict[str, Any]:
    return {"ok": True, "data": {"echo": dict(req.args)}}


def demo() -> None:
    print("=" * 70)
    print("CASE 01 — Chuỗi Middleware Decorator trong AgentKernel")
    print("=" * 70)

    # 1) Lõi trần, không decorator: client gọi y hệt như khi có decorator.
    print("\n[1] Lõi TRẦN (chưa decorator) — interface không đổi:")
    k0 = Kernel({"echo": _echo_tool})
    r0 = k0.execute_tool("echo", {"a": 1})
    print(f"    echo({{'a':1}}) -> ok={r0['ok']}, data={r0['data']}")
    assert r0["ok"] and r0["data"]["echo"] == {"a": 1}

    # 2) Dựng chuỗi: TimingLog (outer) -> PolicyGate -> Retry -> CondenseResult (inner).
    #    Đúng thứ tự lắp ráp trong core/bootstrap.py:34-53.
    print("\n[2] Dựng chuỗi outer->inner: Timing -> Policy -> Retry -> Condense")
    timings: list[dict] = []
    k = Kernel({"echo": _echo_tool})
    k.use(TimingLog(sink=timings.append))      # outer cùng
    k.use(PolicyGate(deny={"dangerous"}))
    k.use(Retry(attempts=3))
    k.use(CondenseResult(max_chars=20))        # inner cùng (sát lõi nhất)

    blob = "x" * 200
    r = k.execute_tool("echo", {"blob": blob})
    print(f"    đo được {len(timings)} mẫu timing: {timings}")
    print(f"    blob gốc dài {len(blob)} -> sau condense dài {len(r['data']['echo']['blob'])}")
    assert r["ok"] is True
    assert len(timings) == 1                            # TimingLog chạy đúng 1 lần
    assert len(r["data"]["echo"]["blob"]) < len(blob)   # CondenseResult đã cắt

    # 3) PolicyGate short-circuit: lõi KHÔNG bao giờ chạy với tool bị cấm.
    print("\n[3] PolicyGate chặn TRƯỚC lõi (short-circuit, không chạm inner):")
    core_calls = {"n": 0}

    def spy_tool(req: ToolRequest) -> dict[str, Any]:
        core_calls["n"] += 1
        return {"ok": True, "data": {}}

    kp = Kernel({"dangerous": spy_tool})
    kp.use(PolicyGate(deny={"dangerous"}))
    rp = kp.execute_tool("dangerous", {})
    print(f"    ok={rp['ok']}, policy_block={rp['metadata'].get('policy_block')}, "
          f"số lần lõi chạy={core_calls['n']}")
    assert rp["ok"] is False and rp["metadata"]["policy_block"] is True
    assert core_calls["n"] == 0  # lõi không hề chạy

    # 4) THỨ TỰ outer->inner QUAN TRỌNG: decorator nằm NGOÀI "thấy" call trước,
    #    "thấy" kết quả sau (in trước / out sau). Minh hoạ bằng 2 logger A/B rồi
    #    đảo thứ tự đăng ký -> dãy in/out đảo theo. Đây là cùng bất biến mà
    #    test_ordering_outer_to_inner kiểm tra; KHÔNG đảo Timing/Policy/Retry thật.
    print("\n[4] Thứ tự đăng ký đổi -> trình tự outer->inner đổi (in trước, out sau):")
    trace_outer: list[str] = []
    trace_inner: list[str] = []

    def make_logger(label: str, sink: list[str]):
        def mw(req: ToolRequest, nxt: Handler) -> dict[str, Any]:
            sink.append(f"{label}:in")
            res = nxt(req)
            sink.append(f"{label}:out")
            return res
        return mw

    ka = Kernel({"echo": _echo_tool})
    ka.use(make_logger("A", trace_outer))   # outer
    ka.use(make_logger("B", trace_outer))   # inner
    ka.execute_tool("echo", {})
    print(f"    chuỗi [A(outer), B(inner)] -> {trace_outer}")
    assert trace_outer == ["A:in", "B:in", "B:out", "A:out"]  # giống test_ordering_outer_to_inner

    kb = Kernel({"echo": _echo_tool})
    kb.use(make_logger("B", trace_inner))   # đảo lại
    kb.use(make_logger("A", trace_inner))
    kb.execute_tool("echo", {})
    print(f"    đảo [B(outer), A(inner)] -> {trace_inner}")
    assert trace_inner == ["B:in", "A:in", "A:out", "B:out"]
    assert trace_outer != trace_inner   # đổi thứ tự = đổi semantic

    # 5) Retry recover tool chập chờn (delegate qua nxt, không gọi tool trực tiếp).
    print("\n[5] Retry phục hồi tool chập chờn (fail lần 1, ok lần 2):")
    state = {"n": 0}

    def flaky(req: ToolRequest) -> dict[str, Any]:
        state["n"] += 1
        return {"ok": state["n"] >= 2, "data": {"n": state["n"]}}

    kr = Kernel({"flaky": flaky})
    kr.use(Retry(attempts=3))
    rr = kr.execute_tool("flaky", {})
    print(f"    kết quả ok={rr['ok']}, tool chạy {state['n']} lần (đúng = 2)")
    assert rr["ok"] is True and state["n"] == 2

    # 6) ĐỐI CHỨNG — KHÔNG dùng Decorator: nhồi mọi concern vào tool.
    print("\n[6] ĐỐI CHỨNG: nhồi timing+policy+condense vào THẲNG tool (không Decorator):")
    print("    -> mỗi tool phải tự lặp lại boilerplate; thêm concern = sửa MỌI tool.")
    monolith_timings: list[dict] = []

    def echo_with_everything(req: ToolRequest) -> dict[str, Any]:
        # logic cross-cutting bị TRỘN vào business logic của tool:
        if req.name in {"dangerous"}:                       # policy
            return {"ok": False, "error": "blocked"}
        t0 = time.perf_counter()                            # timing
        data = {"echo": dict(req.args)}                     # business thật (1 dòng)
        for k_, v in list(data["echo"].items()):           # condense
            if isinstance(v, str) and len(v) > 20:
                data["echo"][k_] = v[:20] + "…[condensed]"
        monolith_timings.append({"ms": (time.perf_counter() - t0) * 1000})
        return {"ok": True, "data": data}

    out = echo_with_everything(ToolRequest("echo", {"blob": "y" * 200}))
    print(f"    business thật chỉ 1 dòng, nhưng tool phình ra vì 3 concern trộn lẫn.")
    print(f"    Muốn thêm 'auth' -> phải sửa hàm này VÀ mọi tool khác giống vậy.")
    assert out["ok"] and len(out["data"]["echo"]["blob"]) < 200

    print("\n" + "=" * 70)
    print("TẤT CẢ ASSERT PASS — Decorator: thêm hành vi runtime, lõi KHÔNG đổi,")
    print("stack tự do, thứ tự kiểm soát được, tránh bùng nổ 2^N tổ hợp class.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
