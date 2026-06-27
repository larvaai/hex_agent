"""
Ca 03 — ToolMiddleware: Protocol callable HẸP (1 chữ ký __call__), compose thành chain.

Bản DISTILL TRUNG THỰC, chỉ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent
hay thư viện bên thứ ba.

NGUỒN THẬT được chưng cất từ (path:line tương đối với /Users/uspro/Desktop/namnson/hex_agent/):
  - core/middleware.py:11-22  ToolMiddleware(Protocol): __call__(request, nxt) -> dict.
                              fail_open là optional attribute (đọc qua getattr, KHÔNG bắt buộc).
  - middleware/retry.py:23-33 Retry implement __call__ — re-invoke khi result non-ok.
  - middleware/timing.py:10-26 TimingLog implement __call__, declare fail_open=True (advisory).

Ý CHÍNH (ISP trên interface dạng CALLABLE):
  Mỗi middleware là MỘT policy độc lập (retry / timing / caching / logging) nhưng chỉ
  phụ thuộc DUY NHẤT một chữ ký hẹp: __call__(request, nxt) -> dict. Structural typing
  (Protocol) cho phép duck typing an toàn — không cần kế thừa. Kernel xếp các middleware
  thành chain; mỗi cái KHÔNG biết cái khác tồn tại. fail_open là attribute TÙY CHỌN: chỉ
  TimingLog khai báo, kernel đọc bằng getattr — Protocol không ép boilerplate này lên ai.

LƯỢC BỎ so với bản thật: ToolRequest/CapabilityResult đầy đủ, kernel chokepoint thật,
metadata policy_block/kind/idempotent đầy đủ. Giữ trung thực: Protocol __call__(request, nxt),
Retry (skip retry khi policy_block / effect non-idempotent), TimingLog (fail_open=True),
cách compose chain qua closure, và posture fail_open vs blocking khi middleware raise.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


# ──────────────────────────────────────────────────────────────────────────────
# Value type — distill core/schemas.ToolRequest (rút gọn)
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ToolRequest:
    name: str
    args: dict = field(default_factory=dict)


# Inner handler: nhận request, trả envelope dict {"ok": bool, ...}
ToolHandler = Callable[[ToolRequest], dict[str, Any]]


# ──────────────────────────────────────────────────────────────────────────────
# PORT HẸP DẠNG CALLABLE — distill core/middleware.py:11-22
# Chỉ 1 chữ ký __call__. Không inheritance. fail_open là OPTIONAL (đọc qua getattr).
# ──────────────────────────────────────────────────────────────────────────────
class ToolMiddleware(Protocol):
    """Nhận request + nxt (inner handler). Có thể act trước/sau, short-circuit
    (return mà không gọi nxt), hoặc sửa envelope.

    Posture (kernel đọc bằng getattr, KHÔNG ép bởi Protocol vì Protocol là structural):
    một middleware CÓ THỂ declare fail_open=True để tự đánh dấu 'advisory'. Nếu một
    fail-open middleware raise, kernel SKIP nó và đi tiếp với inner result. Vắng/False
    (mặc định) = 'blocking': raise lan tới biên kernel thành ok=False."""

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]: ...


# ──────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE #1 — distill middleware/retry.py:23-33
# Implement đúng __call__. KHÔNG biết timing/caching tồn tại.
# ──────────────────────────────────────────────────────────────────────────────
def _retryable(env: dict[str, Any]) -> bool:
    meta = env.get("metadata") or {}
    if meta.get("policy_block"):
        return False
    if meta.get("kind") == "effect" and meta.get("idempotent") is False:
        return False
    return True


class Retry:
    def __init__(self, *, attempts: int = 2) -> None:
        self.attempts = max(1, attempts)

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]:
        env = nxt(request)
        tries = 1
        while isinstance(env, dict) and not env.get("ok") and tries < self.attempts and _retryable(env):
            env = nxt(request)
            tries += 1
        return env


# ──────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE #2 — distill middleware/timing.py:10-26
# Declare fail_open=True (advisory). Cũng chỉ implement __call__.
# ──────────────────────────────────────────────────────────────────────────────
class TimingLog:
    fail_open = True  # advisory telemetry — lỗi của nó KHÔNG được chặn tool call

    def __init__(self, sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.sink = sink

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]:
        t0 = time.perf_counter()
        env = nxt(request)
        if self.sink:
            try:
                self.sink({"tool": request.name, "ok": (env or {}).get("ok"),
                           "ms": round((time.perf_counter() - t0) * 1000, 2)})
            except Exception:
                pass  # metrics sink không bao giờ biến 1 call thành công thành lỗi
        return env


# ──────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE #3 + #4 — middleware MỚI, conform CÙNG port mà không sửa gì khác.
# ──────────────────────────────────────────────────────────────────────────────
class CachingMiddleware:
    """Cache result ok theo (name, args). Minh hoạ: thêm policy mới = thêm 1 class
    conform __call__, không đụng Retry/TimingLog/kernel."""

    def __init__(self) -> None:
        self._cache: dict[tuple, dict[str, Any]] = {}
        self.hits = 0

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]:
        key = (request.name, tuple(sorted(request.args.items())))
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        env = nxt(request)
        if env.get("ok"):
            self._cache[key] = env
        return env


class LoggingMiddleware:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]:
        self._log.append(f"-> {request.name}")
        env = nxt(request)
        self._log.append(f"<- {request.name} ok={env.get('ok')}")
        return env


# ──────────────────────────────────────────────────────────────────────────────
# KERNEL (rút gọn) — xếp middleware thành chain qua closure.
# Distill tinh thần core/kernel chokepoint: mỗi middleware bọc handler kế tiếp.
# fail_open đọc bằng getattr — đúng "optional by convention" của bản thật.
# ──────────────────────────────────────────────────────────────────────────────
class MiniKernel:
    def __init__(self, base: ToolHandler) -> None:
        self._base = base
        self._middlewares: list[ToolMiddleware] = []

    def add_middleware(self, *mws: ToolMiddleware) -> None:
        # Đăng ký theo thứ tự: cái đầu là OUTERMOST (chạy trước, bọc ngoài cùng).
        self._middlewares.extend(mws)

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        handler: ToolHandler = self._base
        # Gói từ INNER ra OUTER: duyệt ngược danh sách.
        for mw in reversed(self._middlewares):
            handler = self._wrap(mw, handler)
        return handler(request)

    @staticmethod
    def _wrap(mw: ToolMiddleware, nxt: ToolHandler) -> ToolHandler:
        def call(request: ToolRequest) -> dict[str, Any]:
            try:
                return mw(request, nxt)
            except Exception as exc:
                # Posture đọc qua getattr — Protocol KHÔNG ép attribute này.
                if getattr(mw, "fail_open", False):
                    # advisory: skip middleware, đi tiếp với inner result
                    return nxt(request)
                # blocking: biến raise thành envelope ok=False ở biên
                return {"ok": False, "error": f"middleware raised: {exc}"}
        return call


# ──────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG — "god middleware": một class ôm mọi quan tâm trong 1 __call__ to.
# ──────────────────────────────────────────────────────────────────────────────
class GodMiddleware:
    """Vi phạm tinh thần ISP/SRP: nhét retry + timing + cache + log vào MỘT __call__.
    Vẫn 'conform' port (vì port chỉ là __call__), nhưng không thể bật/tắt từng policy,
    không test riêng từng cái, không reorder. Đó là lý do hex_agent tách N middleware nhỏ."""

    def __init__(self) -> None:
        self._cache: dict[tuple, dict] = {}

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]:
        key = (request.name, tuple(sorted(request.args.items())))
        if key in self._cache:
            return self._cache[key]
        env = nxt(request)
        tries = 1
        while not env.get("ok") and tries < 2:   # retry trộn lẫn
            env = nxt(request)
            tries += 1
        if env.get("ok"):
            self._cache[key] = env               # cache trộn lẫn
        return env


# ──────────────────────────────────────────────────────────────────────────────
# DEMO
# ──────────────────────────────────────────────────────────────────────────────
def _hr(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def demo() -> None:
    _hr("BƯỚC 1 — Port HẸP dạng callable: ToolMiddleware = __call__(request, nxt)")
    print("Một chữ ký duy nhất. Structural (Protocol), không cần kế thừa.")
    print("fail_open là attribute TÙY CHỌN — chỉ ai cần mới khai báo.")

    _hr("BƯỚC 2 — Nhiều middleware độc lập conform CÙNG port")
    for cls in (Retry, TimingLog, CachingMiddleware, LoggingMiddleware):
        print(f"   {cls.__name__:18s} -> có __call__(request, nxt) ✓")
    # Kiểm tra structural ở runtime bằng callable + chữ ký (Protocol callable):
    assert callable(Retry()) and callable(TimingLog())
    print("Mỗi cái là 1 policy riêng, không cái nào biết cái kia tồn tại.")

    _hr("BƯỚC 3 — Compose chain: Retry trên một handler chập chờn")
    calls = {"n": 0}

    def flaky(request: ToolRequest) -> dict[str, Any]:
        calls["n"] += 1
        # fail lần đầu, ok lần hai
        return {"ok": calls["n"] >= 2, "tool": request.name, "attempt": calls["n"]}

    k = MiniKernel(flaky)
    k.add_middleware(Retry(attempts=3))
    res = k.execute(ToolRequest("fs_read"))
    print(f"flaky gọi {calls['n']} lần, kết quả: ok={res['ok']} (attempt={res['attempt']})")
    assert res["ok"] is True and calls["n"] == 2, "Retry phải re-invoke đến khi ok"

    _hr("BƯỚC 4 — Retry KHÔNG retry effect non-idempotent (an toàn side-effect)")
    eff_calls = {"n": 0}

    def effect(request: ToolRequest) -> dict[str, Any]:
        eff_calls["n"] += 1
        return {"ok": False, "tool": request.name,
                "metadata": {"kind": "effect", "idempotent": False}}

    k2 = MiniKernel(effect)
    k2.add_middleware(Retry(attempts=5))
    k2.execute(ToolRequest("fs_write"))
    print(f"effect non-idempotent gọi {eff_calls['n']} lần (KHÔNG retry dù attempts=5)")
    assert eff_calls["n"] == 1, "không được re-run effect non-idempotent"

    _hr("BƯỚC 5 — Chain nhiều tầng: Logging + Caching + Timing + base")
    log: list[str] = []
    seen: list[dict] = []
    cache = CachingMiddleware()
    base_calls = {"n": 0}

    def base(request: ToolRequest) -> dict[str, Any]:
        base_calls["n"] += 1
        return {"ok": True, "tool": request.name, "value": 42}

    k3 = MiniKernel(base)
    k3.add_middleware(LoggingMiddleware(log), cache, TimingLog(sink=seen.append))
    r1 = k3.execute(ToolRequest("calc", {"x": 1}))
    r2 = k3.execute(ToolRequest("calc", {"x": 1}))  # lần 2 hit cache
    print(f"base gọi {base_calls['n']} lần cho 2 request giống nhau (cache hit={cache.hits})")
    print(f"timing sink ghi {len(seen)} mẫu; log = {log}")
    assert r1 == r2 and base_calls["n"] == 1 and cache.hits == 1
    print("4 thành phần ghép lại, không cái nào biết cái khác — đúng composition của ISP. ✓")

    _hr("BƯỚC 6 — Posture: fail_open (advisory) vs blocking khi middleware RAISE")
    def ok_base(request: ToolRequest) -> dict[str, Any]:
        return {"ok": True, "tool": request.name}

    class BoomTiming:
        fail_open = True
        def __call__(self, request, nxt):
            raise RuntimeError("metrics sink chết")

    class BoomGuard:
        # không khai báo fail_open -> blocking
        def __call__(self, request, nxt):
            raise RuntimeError("guard chết")

    k_adv = MiniKernel(ok_base); k_adv.add_middleware(BoomTiming())
    r_adv = k_adv.execute(ToolRequest("x"))
    print(f"fail_open=True raise -> kernel SKIP, đi tiếp: {r_adv}")
    assert r_adv["ok"] is True, "advisory middleware raise không được chặn call"

    k_blk = MiniKernel(ok_base); k_blk.add_middleware(BoomGuard())
    r_blk = k_blk.execute(ToolRequest("x"))
    print(f"blocking (no fail_open) raise -> ok=False: {r_blk}")
    assert r_blk["ok"] is False, "blocking middleware raise phải thành ok=False"
    print("Posture đọc bằng getattr(mw,'fail_open',False) — Protocol KHÔNG ép attribute. ✓")

    _hr("ĐỐI CHỨNG — 'god middleware' nhồi mọi policy vào 1 __call__")
    god = GodMiddleware()
    kg = MiniKernel(lambda r: {"ok": True, "tool": r.name})
    kg.add_middleware(god)
    kg.execute(ToolRequest("y"))
    print("GodMiddleware 'conform' port (chỉ là __call__), nhưng:")
    print("  - không bật/tắt được retry riêng hay cache riêng;")
    print("  - không reorder (vd Timing ngoài cùng) được;")
    print("  - test 1 policy phải kéo cả 3 logic.")
    print("ISP/SRP: tách thành Retry + Caching + TimingLog nhỏ, ghép tự do qua chain.")

    _hr("KẾT LUẬN")
    print("ToolMiddleware là port hẹp dạng callable (1 chữ ký __call__). Structural typing")
    print("cho phép N middleware độc lập compose thành chain, không cái nào biết cái khác.")


if __name__ == "__main__":
    demo()
