"""
Case 03 — Chain of Responsibility: CondenseResult (modulate-and-forward) + fail-open/_LatchedNext.

NGUỒN THẬT được distill (đã mở file kiểm chứng từng dòng):
  - middleware/condense.py:11-30
        class CondenseResult:
            fail_open = True
            def __call__(self, request, nxt):
                env = nxt(request)                 # forward TRƯỚC
                if request.name.startswith("llm."): return env
                if isinstance(env, dict) and isinstance(env.get("data"), (dict, list, str)):
                    condensed = condense(env["data"], ...)
                    env["data"] = condensed         # MODULATE result rồi trả ra
                    ...
                return env
        -> ConcreteHandler dạng "modulate-and-forward": gọi nxt, quan sát result
           envelope, rút gọn field data, rồi forward result ra ngoài.
  - discipline/condense.py:13-24
        condense(value, max_chars, max_list): rút gọn str/list/dict đệ quy.
  - core/middleware.py:11-22
        ToolMiddleware Protocol — "may ... modify the result envelope" + ghi chú
        fail_open: middleware advisory (telemetry/condense) đánh dấu fail_open=True;
        nếu raise thì kernel SKIP nó và tiếp tục với inner result (không fail call).
  - core/kernel.py:49-73
        _wrap(middleware, nxt, on_skip): nhánh fail-OPEN (64-73) bọc nxt bằng
        _LatchedNext rồi try/except; nếu middleware advisory raise -> on_skip + trả
        latched(request) (inner result). Nhánh fail-CLOSED (58-62) cho nxt thô.
  - core/kernel.py:24-46
        _LatchedNext: proxy one-shot quanh inner handler. Chạy nxt TỐI ĐA MỘT LẦN;
        lần gọi sau replay outcome cũ (result/exception) KHÔNG chạy lại tool.
        Phòng fail-open middleware raise SAU khi đã gọi nxt -> tool chạy 2 lần (FM-HIGH).
  - tests/test_middleware.py:53-71
        test_condense_shrinks_tool_but_skips_llm
        -> chứng minh: tool result bị rút gọn; tool "llm.*" KHÔNG bị rút gọn.
  - tests/test_middleware.py:111-125
        test_advisory_middleware_failure_is_fail_open
        -> advisory raise -> call vẫn ok=True, inner result sống sót, có event skipped.
  - tests/test_middleware.py:128-137
        test_blocking_middleware_failure_is_fail_closed
        -> middleware KHÔNG đánh dấu fail_open mà raise -> ok=False (fail-closed).
  - tests/test_middleware.py:160-187
        test_advisory_failure_after_nxt_does_not_double_execute
        -> advisory gọi nxt (tool chạy 1 lần) rồi raise; latched nxt KHÔNG chạy lại tool.

BẢN DISTILL NÀY mô phỏng gì:
  - Giữ NGUYÊN vai trò CoR: CondenseShrink = ConcreteHandler "modulate-and-forward";
    nxt = handler kế tiếp; chuỗi dựng bằng _wrap + reversed (giống core/kernel.py).
  - Giữ NGUYÊN hai tư thế lỗi của hex_agent: fail-open (advisory, đánh dấu fail_open=True
    -> bị SKIP khi raise) vs fail-closed (mặc định -> raise nổi ra biên ok=False).
  - Giữ NGUYÊN cơ chế latch one-shot: tool chạy ĐÚNG MỘT LẦN dù advisory raise sau nxt.
  - Thay registry/executor/LLM/event bus bằng dict {tên tool -> hàm} + list ghi sự kiện.
    Tất cả bằng stdlib, KHÔNG import hex_agent.

CHỈ DÙNG stdlib. Chạy: python3 condense_fail_open.py  (exit 0, không traceback).
"""
from __future__ import annotations

import copy
from typing import Any, Callable

Request = dict[str, Any]
Envelope = dict[str, Any]
Handler = Callable[[Request], Envelope]
Middleware = Callable[[Request, Handler], Envelope]


# ---------------------------------------------------------------------------
# condense() — distill discipline/condense.py:13-24.
# Rút gọn đệ quy: str cắt theo max_chars, list cắt theo max_list, dict đi sâu.
# ---------------------------------------------------------------------------
def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"... [+{len(text) - max_chars} chars]"


def condense(value: Any, *, max_chars: int = 2000, max_list: int = 10) -> Any:
    if isinstance(value, dict):
        return {k: condense(v, max_chars=max_chars, max_list=max_list) for k, v in value.items()}
    if isinstance(value, list):
        head = [condense(v, max_chars=max_chars, max_list=max_list) for v in value[:max_list]]
        if len(value) > max_list:
            head.append(f"... [+{len(value) - max_list} items]")
        return head
    if isinstance(value, str):
        return _truncate(value, max_chars)
    return value


# ---------------------------------------------------------------------------
# CondenseShrink — distill middleware/condense.py:11-30.
# Vai trò CoR: ConcreteHandler "modulate-and-forward".
#   - forward TRƯỚC (gọi nxt) để lấy result của tool,
#   - quan sát + RÚT GỌN field data của envelope,
#   - rồi trả envelope ra ngoài.
# Đánh dấu fail_open = True: đây là middleware ADVISORY (rút gọn không bao giờ
# được làm hỏng một tool call ok). Nếu raise -> kernel SKIP, giữ inner result.
# Bỏ qua tool "llm.*" để action JSON của model tới parser nguyên vẹn (condense.py:22).
# ---------------------------------------------------------------------------
class CondenseShrink:
    fail_open = True  # advisory — condense failure must not fail an ok tool call

    def __init__(self, *, max_chars: int = 50, max_list: int = 3,
                 on_condense: Callable[[Request], None] | None = None) -> None:
        self.max_chars = max_chars
        self.max_list = max_list
        self.on_condense = on_condense

    def __call__(self, request: Request, nxt: Handler) -> Envelope:
        env = nxt(request)                              # forward trước, lấy result
        if request["name"].startswith("llm."):
            return env                                   # llm.* không bị rút gọn
        if isinstance(env, dict) and isinstance(env.get("data"), (dict, list, str)):
            condensed = condense(env["data"], max_chars=self.max_chars, max_list=self.max_list)
            changed = condensed != env["data"]
            env["data"] = condensed                      # <- MODULATE result
            if changed and self.on_condense:
                self.on_condense(request)
        return env                                       # <- forward result ra ngoài


# ---------------------------------------------------------------------------
# _LatchedNext — distill core/kernel.py:24-46.
# Proxy one-shot quanh inner handler: chạy nxt TỐI ĐA MỘT LẦN; lần sau replay
# outcome đầu tiên (result HOẶC exception) mà KHÔNG chạy lại tool.
# Đây là thứ ngăn một fail-open middleware (gọi nxt rồi raise) làm tool chạy 2 lần.
# ---------------------------------------------------------------------------
class _LatchedNext:
    __slots__ = ("_nxt", "_ran", "_result", "_exc")

    def __init__(self, nxt: Handler) -> None:
        self._nxt = nxt
        self._ran = False
        self._result: Any = None
        self._exc: Exception | None = None

    def __call__(self, request: Request) -> Envelope:
        if not self._ran:
            self._ran = True
            try:
                self._result = self._nxt(request)
            except Exception as exc:  # lưu lại để replay, không bao giờ chạy lại
                self._exc = exc
        if self._exc is not None:
            raise self._exc
        return self._result


# ---------------------------------------------------------------------------
# _wrap — distill core/kernel.py:49-73 (CẢ HAI nhánh, khác case 01 chỉ lấy fail-closed).
#   - fail-closed (mặc định, 58-62): middleware raise -> nổi ra biên kernel (ok=False).
#   - fail-open  (đánh dấu fail_open=True, 64-73): bọc nxt bằng _LatchedNext, try/except;
#       advisory raise -> on_skip(...) + trả latched(request) (inner result, không re-run).
# ---------------------------------------------------------------------------
def _wrap(middleware: Middleware, nxt: Handler,
          on_skip: Callable[[Middleware, Exception], None] | None = None) -> Handler:
    if getattr(middleware, "fail_open", False) is not True:
        def handler(request: Request) -> Envelope:
            return middleware(request, nxt)            # fail-closed: raise nổi ra ngoài
        return handler

    def handler(request: Request) -> Envelope:
        latched = _LatchedNext(nxt)
        try:
            return middleware(request, latched)
        except Exception as exc:  # advisory hỏng -> skip nó, giữ inner (latched) result
            if on_skip is not None:
                on_skip(middleware, exc)
            return latched(request)                    # replay, KHÔNG chạy lại tool
    return handler


# ---------------------------------------------------------------------------
# MiniKernel — distill phần CoR của AgentKernel có truyền on_skip (core/kernel.py:179-194).
# ---------------------------------------------------------------------------
class MiniKernel:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[[Request], Envelope]] = {}
        self._middlewares: list[Middleware] = []
        self.skipped: list[str] = []   # thay EventBus: ghi nhận "middleware.skipped"

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

        def on_skip(mw: Middleware, exc: Exception) -> None:
            # advisory bị skip -> quan sát được (giống event "middleware.skipped").
            # Bản thật ghi getattr(mw, "name", type(mw).__name__) (kernel.py:187); ở đây
            # middleware demo là hàm trần nên ưu tiên __name__ để nhãn có ý nghĩa.
            label = getattr(mw, "name", None) or getattr(mw, "__name__", None) or type(mw).__name__
            self.skipped.append(label)

        handler: Handler = core
        for mw in reversed(self._middlewares):         # dựng chuỗi từ trong ra ngoài
            handler = _wrap(mw, handler, on_skip=on_skip)
        try:
            envelope = handler(request)
        except Exception as exc:  # fail-closed: middleware không được làm sập biên kernel
            envelope = {"ok": False, "capability": tool_name, "data": {},
                        "error": str(exc), "metadata": {"kernel_error": True}}
        return envelope


# ---------------------------------------------------------------------------
# Tools nghiệp vụ tối giản.
# ---------------------------------------------------------------------------
def fetch_tool(req: Request) -> Envelope:
    """Trả result 'to': blob dài + list dài -> để CondenseShrink có cái mà rút."""
    return {"ok": True, "capability": req["name"],
            "data": {"blob": "x" * 500, "items": list(range(20))}, "metadata": {}}


def llm_chat_tool(req: Request) -> Envelope:
    """Tool 'llm.*': result KHÔNG được rút gọn (action JSON phải tới parser nguyên vẹn)."""
    return {"ok": True, "capability": req["name"],
            "data": {"content": "y" * 500}, "metadata": {}}


def make_counter_tool(counter: dict[str, int]) -> Callable[[Request], Envelope]:
    """Tool đếm số lần thực thi -> để chứng minh latch (tool chạy đúng MỘT lần)."""
    def counter_tool(req: Request) -> Envelope:
        counter["n"] += 1
        return {"ok": True, "capability": req["name"], "data": {"n": counter["n"]}, "metadata": {}}
    return counter_tool


# ===========================================================================
def demo() -> None:
    print("=" * 70)
    print("CASE 03 — CondenseResult (modulate-and-forward) + fail-open/_LatchedNext")
    print("=" * 70)

    condensed_on: list[str] = []

    # --- 1) modulate-and-forward: rút gọn result của tool thường -----------------
    print("\n[1] execute_tool('fetch') với CondenseShrink(max_chars=50, max_list=3)")
    print("    Kỳ vọng CoR: handler gọi nxt TRƯỚC, rồi SỬA result envelope (rút gọn data).")
    k = MiniKernel()
    k.register_tool("fetch", fetch_tool)
    k.register_tool("llm.chat", llm_chat_tool)
    k.use(CondenseShrink(max_chars=50, max_list=3,
                         on_condense=lambda req: condensed_on.append(req["name"])))
    r = k.execute_tool("fetch")
    print("    data.blob (len):", len(r["data"]["blob"]), "->", repr(r["data"]["blob"][:60]))
    print("    data.items     :", r["data"]["items"])
    print("    on_condense ghi nhận:", condensed_on)
    assert r["ok"] is True
    assert len(r["data"]["blob"]) < 120, "blob 500 ký tự phải bị rút gọn"
    assert r["data"]["blob"].endswith("chars]"), "đuôi truncation marker"
    assert r["data"]["items"][-1].endswith("items]"), "list 20 phần tử bị cắt còn 3 + marker"
    assert condensed_on == ["fetch"], "callback on_condense chỉ bắn khi thật sự rút gọn"
    print("    OK: CondenseShrink forward trước, rồi modulate result (rút gọn) rồi trả ra.")

    # --- 2) bỏ qua llm.*: cùng handler nhưng KHÔNG modulate ----------------------
    print("\n[2] execute_tool('llm.chat') — handler chủ động KHÔNG rút gọn tool llm.*")
    r2 = k.execute_tool("llm.chat")
    print("    data.content (len):", len(r2["data"]["content"]))
    assert len(r2["data"]["content"]) == 500, "llm.* phải tới nguyên vẹn, không rút gọn"
    assert condensed_on == ["fetch"], "không có lần condense thứ hai"
    print("    OK: cùng một handler, nhưng forward-NGUYÊN-VẸN với llm.* (không modulate).")

    # --- 3) fail-OPEN: advisory raise -> call vẫn ok, inner result sống sót ------
    print("\n[3] fail-OPEN: một advisory middleware (fail_open=True) RAISE sau khi gọi nxt")
    print("    Kỳ vọng: kernel SKIP nó, giữ inner result -> call vẫn ok=True.")
    k3 = MiniKernel()
    k3.register_tool("fetch", fetch_tool)

    def boom_advisory(req: Request, nxt: Handler) -> Envelope:
        env = nxt(req)                                  # downstream chạy bình thường
        raise RuntimeError("advisory nổ trong hậu xử lý")
    boom_advisory.fail_open = True                       # đánh dấu advisory

    k3.use(boom_advisory)
    r3 = k3.execute_tool("fetch")
    print("    ok =", r3["ok"], " skipped =", k3.skipped)
    assert r3["ok"] is True, "advisory hỏng KHÔNG được làm fail call"
    assert "blob" in r3["data"], "inner result của tool vẫn sống sót"
    assert k3.skipped == ["boom_advisory"], "việc nuốt lỗi phải quan sát được, không im lặng"
    print("    OK: fail-open -> advisory bị skip, inner result giữ nguyên, có ghi nhận skipped.")

    # --- 4) fail-CLOSED: middleware KHÔNG đánh dấu mà raise -> ok=False ----------
    print("\n[4] fail-CLOSED: middleware KHÔNG có fail_open mà raise -> nổi ra biên (ok=False)")
    k4 = MiniKernel()
    k4.register_tool("fetch", fetch_tool)

    def boom_blocking(req: Request, nxt: Handler) -> Envelope:  # mặc định = blocking
        raise RuntimeError("blocking nổ")

    k4.use(boom_blocking)
    r4 = k4.execute_tool("fetch")
    print("    ok =", r4["ok"], " metadata =", r4["metadata"])
    assert r4["ok"] is False, "blocking raise -> fail-closed"
    assert r4["metadata"]["kernel_error"] is True
    assert k4.skipped == [], "blocking KHÔNG đi qua nhánh skip"
    print("    OK: mặc định fail-closed -> raise nổi ra biên kernel thành ok=False.")

    # --- 5) latch: advisory gọi nxt rồi raise -> tool chạy ĐÚNG MỘT LẦN ----------
    print("\n[5] _LatchedNext: advisory gọi nxt (tool chạy) rồi raise -> tool KHÔNG chạy lại")
    counter = {"n": 0}
    k5 = MiniKernel()
    k5.register_tool("counter", make_counter_tool(counter))

    def post_raise(req: Request, nxt: Handler) -> Envelope:
        nxt(req)                                        # tool chạy ĐÚNG ở đây (n -> 1)
        raise RuntimeError("hậu xử lý nổ sau khi tool đã chạy")
    post_raise.fail_open = True

    k5.use(post_raise)
    r5 = k5.execute_tool("counter")
    print("    counter.n =", counter["n"], " ok =", r5["ok"], " data =", r5["data"])
    assert counter["n"] == 1, "tool phải chạy ĐÚNG MỘT LẦN dù advisory raise sau nxt (FM-HIGH)"
    assert r5["ok"] is True and r5["data"]["n"] == 1, "replay đúng result đầu tiên"
    print("    OK: latched nxt replay outcome đầu tiên -> tool non-idempotent không chạy 2 lần.")

    print("\n[KẾT LUẬN] CondenseResult là biến thể 'modulate-and-forward' của CoR: gọi nxt")
    print("           trước, rồi sửa result rồi trả ra. Vì là advisory nên đánh dấu fail_open")
    print("           -> raise thì bị SKIP (giữ inner result), và _LatchedNext bảo đảm tool")
    print("           chạy đúng một lần. Tất cả assert PASS.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
