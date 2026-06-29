"""
Case 02 — Chain of Responsibility: PolicyGate, một handler "early-exit" (hex_agent).

NGUỒN THẬT được distill (đã mở file kiểm chứng từng dòng):
  - middleware/policy.py:9-22
        class PolicyGate:
            def __call__(self, request, nxt):
                if request.name in self.deny:
                    if self.on_block: self.on_block(request)
                    return {"ok": False, ..., "metadata": {"policy_block": True}}
                return nxt(request)
        -> ConcreteHandler thuần "gate": chỉ chọn handle (return) HOẶC forward (nxt).
           Không modulate, không hậu xử lý. Đây là dạng early-termination kinh điển.
  - tests/test_middleware.py:15-23
        test_policy_blocks_before_core
        -> chứng minh: tool KHÔNG chạy khi bị chặn; metadata mang policy_block=True;
           callback on_block ghi nhận tool bị chặn (blocked == ["echo"]).
  - core/bootstrap.py:38-42
        _install_middleware wire PolicyGate(deny=...) khi config bật.
  - core/kernel.py:152-177
        core(req): executor thật phía sau gate — chính là cái mà gate ngăn không cho chạm.

BẢN DISTILL NÀY mô phỏng gì:
  - Giữ NGUYÊN vai trò CoR của PolicyGate: nó là một ConcreteHandler trong chuỗi,
    quyết định handle-here (return envelope chặn) hay forward (nxt).
  - Thay registry/executor/event bus của hex_agent bằng:
      * một dict {tên tool -> hàm} cực nhỏ làm "core",
      * một hàm wrap chuỗi tối giản (giống core/kernel.py:_wrap + reversed loop).
    Tất cả bằng stdlib, KHÔNG import hex_agent.

CHỈ DÙNG stdlib. Chạy: python3 policy_gate_handler.py  (exit 0, không traceback).
"""
from __future__ import annotations

import copy
from typing import Any, Callable

Request = dict[str, Any]
Envelope = dict[str, Any]
Handler = Callable[[Request], Envelope]
Middleware = Callable[[Request, Handler], Envelope]


# ---------------------------------------------------------------------------
# PolicyGate — distill TRUNG THỰC middleware/policy.py:9-22.
# Vai trò CoR: ConcreteHandler dạng "gate".
#   - Điểm quyết định: request["name"] in self.deny.
#   - Nếu chặn  -> return envelope NGAY (short-circuit, không gọi nxt).
#   - Nếu không -> nxt(request) (forward sang handler kế tiếp).
# Có on_block callback giống bản gốc (để observable, test ...:18 dùng nó).
# ---------------------------------------------------------------------------
class PolicyGate:
    def __init__(self, *, deny: set[str] | None = None,
                 on_block: Callable[[Request], None] | None = None) -> None:
        self.deny = set(deny or ())
        self.on_block = on_block

    def __call__(self, request: Request, nxt: Handler) -> Envelope:
        if request["name"] in self.deny:
            if self.on_block:
                self.on_block(request)          # quan sát được việc chặn, không im lặng
            return {"ok": False, "capability": request["name"], "feature": None,
                    "data": {}, "error": f"Blocked by policy: {request['name']}",
                    "metadata": {"policy_block": True}}     # <- handle-here, KHÔNG forward
        return nxt(request)                                  # <- forward


# ---------------------------------------------------------------------------
# Hạ tầng chuỗi tối giản — distill core/kernel.py:_wrap (49-62) + 192-194.
# ---------------------------------------------------------------------------
def _wrap(middleware: Middleware, nxt: Handler) -> Handler:
    def handler(request: Request) -> Envelope:
        return middleware(request, nxt)
    return handler


class MiniKernel:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[[Request], Envelope]] = {}
        self._middlewares: list[Middleware] = []

    def register_tool(self, name: str, fn: Callable[[Request], Envelope]) -> None:
        self._tools[name] = fn

    def use(self, middleware: Middleware) -> None:
        self._middlewares.append(middleware)

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> Envelope:
        request: Request = {"name": tool_name, "args": copy.deepcopy(args) if args else {}}

        def core(req: Request) -> Envelope:
            fn = self._tools.get(req["name"])
            if fn is None:
                return {"ok": False, "capability": req["name"], "data": {},
                        "error": f"Unknown tool: {req['name']}", "metadata": {}}
            return fn(req)

        handler: Handler = core
        for mw in reversed(self._middlewares):     # dựng chuỗi từ trong ra ngoài
            handler = _wrap(mw, handler)
        return handler(request)


# ---------------------------------------------------------------------------
# Một "tool" nhạy cảm. Nếu PolicyGate hỏng và để nó chạy, side-effect sẽ xảy ra
# (ta dùng list side_effects để bắt quả tang). Đây là cách chứng minh bằng chứng
# "tool bên trong không bao giờ chạy" — giống test ...:82 dùng ExplodingTool.
# ---------------------------------------------------------------------------
def make_admin_tool(side_effects: list[str]) -> Callable[[Request], Envelope]:
    def admin_tool(req: Request) -> Envelope:
        side_effects.append(req["name"])           # tác dụng phụ "nguy hiểm"
        return {"ok": True, "capability": req["name"], "data": {"deleted": True}, "metadata": {}}
    return admin_tool


def safe_tool(req: Request) -> Envelope:
    return {"ok": True, "capability": req["name"], "data": {"echo": req["args"]}, "metadata": {}}


# ---------------------------------------------------------------------------
# ĐỐI CHỨNG: nếu KHÔNG có gate trong chuỗi -> request đi thẳng tới core,
# side-effect xảy ra. Cho thấy chính cái gate (early-exit handler) bảo vệ core.
# ---------------------------------------------------------------------------
def demo() -> None:
    print("=" * 68)
    print("CASE 02 — PolicyGate: handler early-exit (chặn trước khi tới core)")
    print("=" * 68)

    side_effects: list[str] = []
    blocked: list[str] = []

    k = MiniKernel()
    k.register_tool("admin_tool", make_admin_tool(side_effects))
    k.register_tool("read_doc", safe_tool)
    # Gate là handler NGOÀI CÙNG, đứng trước core (giống bootstrap.py wire PolicyGate).
    k.use(PolicyGate(deny={"admin_tool"}, on_block=lambda req: blocked.append(req["name"])))

    # --- 1) Tool bị chặn: short-circuit, core KHÔNG chạy ----------------------
    print("\n[1] execute_tool('admin_tool') — nằm trong deny-set {'admin_tool'}")
    r = k.execute_tool("admin_tool", {"target": "prod-db"})
    print("    ok      =", r["ok"])
    print("    error   =", r["error"])
    print("    metadata=", r["metadata"])
    print("    on_block ghi nhận:", blocked)
    print("    side_effects (tool có chạy không?):", side_effects)
    assert r["ok"] is False
    assert r["metadata"]["policy_block"] is True
    assert blocked == ["admin_tool"], "callback on_block phải ghi nhận tool bị chặn"
    # Bằng chứng then chốt của CoR early-exit: core executor không bao giờ bị chạm.
    assert side_effects == [], "Gate short-circuit -> admin_tool KHÔNG được chạy"
    print("    OK: gate trả về NGAY, không gọi nxt -> tool nguy hiểm không thực thi.")

    # --- 2) Tool không bị chặn: forward bình thường tới core ------------------
    print("\n[2] execute_tool('read_doc') — KHÔNG nằm trong deny-set")
    r2 = k.execute_tool("read_doc", {"id": 42})
    print("    ok   =", r2["ok"], " data =", r2["data"])
    assert r2["ok"] is True
    assert r2["data"]["echo"] == {"id": 42}, "tool an toàn được forward & chạy"
    assert "policy_block" not in r2["metadata"], "không bị gắn cờ chặn"
    print("    OK: gate forward (gọi nxt) -> core chạy như thường.")

    # --- 3) ĐỐI CHỨNG: bỏ gate khỏi chuỗi -> tool nguy hiểm chạy --------------
    print("\n[3] ĐỐI CHỨNG — kernel KHÔNG có PolicyGate trong chuỗi:")
    side2: list[str] = []
    k_nogate = MiniKernel()
    k_nogate.register_tool("admin_tool", make_admin_tool(side2))
    r3 = k_nogate.execute_tool("admin_tool", {"target": "prod-db"})
    print("    ok =", r3["ok"], " side_effects =", side2)
    assert r3["ok"] is True and side2 == ["admin_tool"], "không gate -> tool CHẠY (xóa db!)"
    print("    -> Không có gate, request đi thẳng tới core và side-effect xảy ra.")
    print("       Chính handler early-exit trong chuỗi là thứ bảo vệ core.")

    print("\n[KẾT LUẬN] PolicyGate minh hoạ quyết định cốt lõi của CoR: handle (return)")
    print("           hay forward (nxt). Đây là 'gate' thuần, không modulate, dễ test,")
    print("           và chặn được trước khi core chạy. Tất cả assert PASS.")
    print("=" * 68)


if __name__ == "__main__":
    demo()
