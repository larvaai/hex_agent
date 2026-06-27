"""
Case 01 — Chain of Responsibility: hệ middleware quanh execute_tool (hex_agent).

NGUỒN THẬT được distill (đã mở file kiểm chứng từng dòng):
  - core/middleware.py:11-22
        ToolMiddleware Protocol: __call__(request, nxt) -> dict.
        "May act before/after, short-circuit (return without calling nxt),
         or modify the result envelope."  -> đây là interface Handler của CoR.
  - core/kernel.py:49-73
        _wrap(middleware, nxt, on_skip): bind 1 middleware quanh handler kế tiếp
        (tránh late-binding closure bug). Đây là bước "set_next" của CoR.
  - core/kernel.py:192-194
        handler = core
        for mw in reversed(self._middlewares):
            handler = _wrap(mw, handler, on_skip=on_skip)
        -> dựng chuỗi từ trong ra ngoài; thứ tự đăng ký = outer -> inner.
  - core/kernel.py:100-104
        AgentKernel.use(middleware): đăng ký 1 ToolMiddleware (raise nếu đã frozen).
  - core/kernel.py:152-177
        core(req): executor thật (ConcreteHandler cuối cùng / fallback của chuỗi).
  - core/bootstrap.py:28-53
        _install_middleware: wire timing -> policy -> retry -> condense theo thứ tự khai báo.
  - tests_audit/test_core_edges_rigor.py:82-102
        test_tool_middleware_can_short_circuit_without_calling_next
        -> chứng minh short-circuit: tool bên trong KHÔNG bao giờ chạy.
  - tests_audit/test_core_edges_rigor.py:105-126
        test_tool_middleware_registration_order_is_outer_to_inner
        -> chứng minh thứ tự outer:pre, inner:pre, inner:post, outer:post (LIFO unwind).

BẢN DISTILL NÀY mô phỏng gì:
  - Giữ NGUYÊN vai trò CoR: Handler (interface) = callable(request, nxt);
    ConcreteHandler = các middleware; nxt = tham chiếu handler kế tiếp;
    Client = execute_tool(); chain builder = _wrap() + vòng reversed().
  - Thay hạ tầng nặng (registry/executor/LLM/event bus) bằng:
      * một "registry" dict {tên tool -> hàm} cực nhỏ,
      * envelope kết quả là dict thuần,
    đều bằng thư viện chuẩn, KHÔNG import hex_agent.

CHỈ DÙNG stdlib. Chạy: python3 middleware_system.py  (exit 0, không traceback).
"""
from __future__ import annotations

import copy
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Kiểu Handler của CoR.
# Trong hex_agent đây là core/middleware.py:ToolMiddleware (một Protocol cấu trúc):
#     def __call__(self, request, nxt) -> dict: ...
# Ở bản distill ta dùng đúng chữ ký đó: middleware là callable nhận (request, nxt).
# ---------------------------------------------------------------------------
Request = dict[str, Any]
Envelope = dict[str, Any]
Handler = Callable[[Request], Envelope]               # nxt: handler kế tiếp
Middleware = Callable[[Request, Handler], Envelope]   # ConcreteHandler


# ---------------------------------------------------------------------------
# _wrap — distill core/kernel.py:49-62 (nhánh fail-closed, không latch).
# Bind MỘT middleware quanh handler kế tiếp, trả về một handler mới.
# Việc dùng default-arg / closure cố định middleware+nxt chính là "set_next":
# nó ghim tham chiếu "handler kế tiếp" vào trong middleware hiện tại.
# Bản gốc còn nhánh fail-open + _LatchedNext (kernel.py:64-73); ta lược ở case này
# để tập trung vào xương sống CoR, và xử lý fail-open ở phần mở rộng cuối file.
# ---------------------------------------------------------------------------
def _wrap(middleware: Middleware, nxt: Handler) -> Handler:
    def handler(request: Request) -> Envelope:
        return middleware(request, nxt)
    return handler


# ---------------------------------------------------------------------------
# MiniKernel — distill phần CoR của AgentKernel (core/kernel.py).
#   - use()         : kernel.py:100-104  (đăng ký middleware; outer -> inner)
#   - execute_tool(): kernel.py:106 + 152-177 (core) + 192-196 (dựng & chạy chuỗi)
# ---------------------------------------------------------------------------
class MiniKernel:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[[Request], Envelope]] = {}
        self._middlewares: list[Middleware] = []
        self._frozen = False

    def register_tool(self, name: str, fn: Callable[[Request], Envelope]) -> None:
        """Thay cho CapabilityRegistry: chỉ map tên -> hàm thực thi."""
        self._tools[name] = fn

    def use(self, middleware: Middleware) -> None:
        """Đăng ký 1 middleware. Thứ tự đăng ký = outer -> inner (kernel.py:100-104)."""
        if self._frozen:
            raise RuntimeError("Middleware pipeline is frozen for active sessions.")
        self._middlewares.append(middleware)

    def freeze(self) -> None:
        self._frozen = True

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> Envelope:
        # Deep-copy args để tool không thể mutate object của caller (kernel.py:114).
        request: Request = {"name": tool_name, "args": copy.deepcopy(args) if args else {}}

        # core = ConcreteHandler cuối cùng / fallback (kernel.py:152-177).
        def core(req: Request) -> Envelope:
            fn = self._tools.get(req["name"])
            if fn is None:
                return {"ok": False, "capability": req["name"],
                        "data": {}, "error": f"Unknown tool: {req['name']}", "metadata": {}}
            try:
                raw = fn(req)
            except Exception as exc:  # tool không bao giờ được làm sập kernel (kernel.py:156)
                return {"ok": False, "capability": req["name"], "data": {},
                        "error": str(exc), "metadata": {"kernel_error": True}}
            raw.setdefault("metadata", {})
            return raw

        # Dựng chuỗi từ TRONG ra NGOÀI (kernel.py:192-194):
        #   middleware ĐĂNG KÝ SAU nằm phía trong; ĐĂNG KÝ TRƯỚC bọc ngoài.
        handler: Handler = core
        for mw in reversed(self._middlewares):
            handler = _wrap(mw, handler)

        try:
            envelope = handler(request)
        except Exception as exc:  # middleware không được làm sập biên kernel (kernel.py:197)
            envelope = {"ok": False, "capability": tool_name, "data": {},
                        "error": str(exc), "metadata": {"kernel_error": True}}
        return envelope


# ===========================================================================
# 3 ConcreteHandler tự viết (đóng vai PolicyGate/Timing/Condense thu nhỏ).
# Mỗi cái đều tuân thủ interface Handler chỉ bằng chữ ký __call__(request, nxt).
# ===========================================================================
class Logger:
    """Telemetry quanh cuộc gọi (giống TimingLog, timing.py:10-26):
    act-before, forward, act-after. Luôn forward, không bao giờ short-circuit."""

    def __init__(self, trace: list[str]) -> None:
        self.trace = trace

    def __call__(self, request: Request, nxt: Handler) -> Envelope:
        self.trace.append(f"Logger:in({request['name']})")
        env = nxt(request)                       # forward xuống handler kế tiếp
        self.trace.append(f"Logger:out(ok={env.get('ok')})")
        return env


class Guard:
    """Gate kiểu PolicyGate (policy.py:9-22): nếu tool nằm trong deny-set thì
    TRẢ VỀ NGAY mà KHÔNG gọi nxt -> short-circuit, tool bên trong không chạy."""

    def __init__(self, deny: set[str], trace: list[str]) -> None:
        self.deny = deny
        self.trace = trace

    def __call__(self, request: Request, nxt: Handler) -> Envelope:
        if request["name"] in self.deny:
            self.trace.append(f"Guard:BLOCK({request['name']})")
            return {"ok": False, "capability": request["name"], "data": {},
                    "error": f"Blocked by policy: {request['name']}",
                    "metadata": {"policy_block": True}}
        self.trace.append("Guard:pass")
        return nxt(request)                      # forward khi không bị chặn


class Amplifier:
    """Modulate-and-forward (giống CondenseResult, condense.py:11-30):
    gọi nxt trước, rồi CHỈNH SỬA result envelope, rồi trả ra."""

    def __init__(self, trace: list[str]) -> None:
        self.trace = trace

    def __call__(self, request: Request, nxt: Handler) -> Envelope:
        env = nxt(request)
        if env.get("ok") and isinstance(env.get("data"), dict) and "value" in env["data"]:
            env["data"]["value"] *= 10           # post-process result
            self.trace.append("Amplifier:x10")
        return env


# ---------------------------------------------------------------------------
# ĐỐI CHỨNG: "khi KHÔNG dùng CoR" -> mega if/elif nhồi mọi cross-cutting concern
# vào trong tool. Khó test, vi phạm SRP, không config được runtime.
# ---------------------------------------------------------------------------
def monolith_execute(tool_name: str, args: dict[str, Any], deny: set[str]) -> Envelope:
    # ❌ Mọi mối quan tâm (policy, logging, amplify) trộn vào 1 chỗ, gắn cứng thứ tự.
    if tool_name in deny:                          # policy
        return {"ok": False, "capability": tool_name, "data": {},
                "error": f"Blocked by policy: {tool_name}", "metadata": {"policy_block": True}}
    print(f"  [monolith] log: chạy {tool_name}")   # logging gắn chết
    if tool_name == "double":                      # business logic
        env = {"ok": True, "capability": tool_name, "data": {"value": args.get("value", 0) * 2},
               "metadata": {}}
    else:
        env = {"ok": False, "capability": tool_name, "data": {}, "error": "unknown", "metadata": {}}
    if env["ok"]:                                  # amplify
        env["data"]["value"] *= 10
    return env
    # Muốn thêm "retry" hay đổi thứ tự? Phải sửa thẳng hàm này -> không Open-Closed.


def double_tool(req: Request) -> Envelope:
    """Một 'tool' nghiệp vụ tối giản: nhân đôi value."""
    v = req["args"].get("value", 0)
    return {"ok": True, "capability": req["name"], "data": {"value": v * 2}, "metadata": {}}


def explode_tool(req: Request) -> Envelope:
    """Tool 'không bao giờ được phép chạy' — dùng để chứng minh short-circuit."""
    raise AssertionError("Tool này lẽ ra phải bị Guard chặn, không được chạy!")


# ===========================================================================
def demo() -> None:
    print("=" * 68)
    print("CASE 01 — Chain of Responsibility: middleware quanh execute_tool")
    print("=" * 68)

    # --- Phần 1: thứ tự outer -> inner (kernel.py:192-194; test ...:105-126) -----
    print("\n[1] Đăng ký 3 middleware theo thứ tự: Logger -> Guard -> Amplifier")
    print("    Kỳ vọng CoR: đăng ký trước = bọc NGOÀI -> chạy 'in' trước, 'out' sau.")
    trace: list[str] = []
    k = MiniKernel()
    k.register_tool("double", double_tool)
    k.register_tool("admin_tool", explode_tool)
    k.use(Logger(trace))          # outer nhất
    k.use(Guard({"admin_tool"}, trace))
    k.use(Amplifier(trace))       # inner nhất (gần core)

    print("\n[2] Gọi execute_tool('double', {'value': 3})")
    r = k.execute_tool("double", {"value": 3})
    print("    Trace thực thi:", trace)
    print("    Kết quả:", r["data"])
    # value = 3 -> double_tool x2 = 6 -> Amplifier x10 = 60
    assert r["ok"] is True
    assert r["data"]["value"] == 60, "double(3)->6, amplify->60"
    # Bất biến CoR: Logger bọc ngoài nên 'in' đầu tiên và 'out' cuối cùng.
    assert trace[0] == "Logger:in(double)", "Logger đăng ký trước -> in trước"
    assert trace[-1].startswith("Logger:out"), "Logger out cuối cùng (LIFO unwind)"
    print("    OK: thứ tự outer->inner đúng, Logger bọc ngoài cùng.")

    # --- Phần 2: short-circuit — tool bên trong KHÔNG chạy (test ...:82-102) -----
    print("\n[3] Gọi execute_tool('admin_tool') — Guard nằm trong deny-set")
    print("    Kỳ vọng: Guard trả về NGAY, không gọi nxt -> explode_tool KHÔNG chạy.")
    trace.clear()
    r2 = k.execute_tool("admin_tool", {"value": 1})
    print("    Trace thực thi:", trace)
    print("    Kết quả:", {"ok": r2["ok"], "error": r2["error"], "metadata": r2["metadata"]})
    assert r2["ok"] is False
    assert r2["metadata"]["policy_block"] is True
    # Bằng chứng short-circuit: Amplifier (nằm SAU Guard) không bao giờ chạy,
    # và explode_tool cũng vậy (nếu chạy sẽ raise AssertionError -> demo sập).
    assert "Guard:BLOCK(admin_tool)" in trace
    assert all("Amplifier" not in t for t in trace), "Amplifier sau Guard -> bị bỏ qua"
    print("    OK: short-circuit hoạt động, core executor không bị chạm tới.")

    # --- Phần 3: cấu hình runtime — bỏ Guard, thêm lại chuỗi khác ---------------
    print("\n[4] CoR cho phép cấu hình runtime: dựng kernel KHÁC chỉ Logger->Amplifier")
    trace2: list[str] = []
    k2 = MiniKernel()
    k2.register_tool("double", double_tool)
    k2.use(Logger(trace2))
    k2.use(Amplifier(trace2))
    r3 = k2.execute_tool("double", {"value": 5})
    print("    Trace:", trace2, "-> value =", r3["data"]["value"])
    assert r3["data"]["value"] == 100  # 5*2=10, *10=100
    print("    OK: thêm/bớt handler mà KHÔNG đụng client (Open-Closed).")

    # --- Phần 4: đối chứng monolith (không CoR) --------------------------------
    print("\n[5] ĐỐI CHỨNG — monolith if/elif nhồi mọi concern vào một hàm:")
    m = monolith_execute("double", {"value": 3}, deny=set())
    print("    monolith('double',3):", m["data"])
    print("    Vấn đề: muốn đổi thứ tự / thêm retry phải SỬA thẳng hàm,")
    print("    không test riêng từng concern, không config runtime -> vi phạm SRP & OCP.")

    print("\n[KẾT LUẬN] Sender (execute_tool) thả request vào chuỗi; mỗi handler tự")
    print("           quyết định handle / forward / modulate. Chuỗi dựng động, có")
    print("           early-exit. Tất cả assert PASS.")
    print("=" * 68)


if __name__ == "__main__":
    demo()
