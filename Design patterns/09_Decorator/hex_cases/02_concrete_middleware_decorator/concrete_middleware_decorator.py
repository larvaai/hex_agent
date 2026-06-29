"""
Case 02 — Retry: một ConcreteDecorator thêm "thử lại" mà KHÔNG sửa executor.

Bản DISTILL TRUNG THỰC từ code thật của hex_agent:
  - middleware/retry.py:14-20  -> _retryable(): cổng logic quyết định có được retry.
                                  KHÔNG retry policy_block; KHÔNG retry effect non-idempotent.
  - middleware/retry.py:23-33  -> class Retry: ConcreteDecorator. __call__(request, nxt)
                                  gọi nxt(request), kiểm tra env['ok'], gọi lại nxt tối đa
                                  `attempts` lần. Delegate qua nxt — KHÔNG gọi tool trực tiếp.
  - tests/test_middleware.py:83-99  -> test_retry_recovers_flaky_tool: tool fail lần 1, ok lần 2;
                                  Retry phục hồi trong suốt; tool.execute chạy đúng 2 lần.
  - tests_audit/test_middleware_exact_semantics.py:102-123 -> ma trận đếm số lần gọi nxt
                                  (1 lần khi ok ngay; 2 lần khi fail rồi ok; dừng đúng `attempts`;
                                  1 lần khi policy_block / effect non-idempotent).

Ánh xạ vai trò Decorator:
  - Component interface = handler `(request) -> dict`.
  - ConcreteComponent  = executor lõi (ở đây là tool callable) — KHÔNG biết gì về retry.
  - ConcreteDecorator  = Retry (giữ chữ ký __call__(request, nxt), thêm hành vi retry).
  - has-a (inner)      = `nxt` — handler được bọc (có thể là middleware khác hoặc lõi).
  - _retryable()       = cổng kiểm tra điều kiện retry.
  - attempts           = cấu hình của decorator.

Lược bỏ so với bản thật:
  - Không có kernel/registry/EventBus; `nxt` chỉ là một closure quanh tool callable.
  - Envelope rút gọn còn {ok, data, metadata}; bỏ request_id/lineage.
  - _retryable giữ đúng 2 luật quan trọng (policy_block, effect+non-idempotent).

Chỉ dùng thư viện chuẩn Python 3.14. KHÔNG import hex_agent, KHÔNG thư viện bên thứ ba.
Chạy: python3 concrete_middleware_decorator.py  (thoát code 0, không traceback).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


Handler = Callable[["ToolRequest"], dict[str, Any]]


@dataclass(frozen=True)
class ToolRequest:
    """Bản rút gọn của core/schemas.py:28-33."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────
# _retryable — distill middleware/retry.py:14-20.
#   Cổng logic: KHÔNG retry policy block; KHÔNG retry side-effect không idempotent
#   (chạy lại effect có thể double-apply). Read/idempotent thì được retry.
# ──────────────────────────────────────────────────────────────────────────
def _retryable(env: dict[str, Any]) -> bool:
    meta = env.get("metadata") or {}
    if meta.get("policy_block"):
        return False
    if meta.get("kind") == "effect" and meta.get("idempotent") is False:
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────
# Retry — ConcreteDecorator. distill middleware/retry.py:23-33.
#   __call__ nhận request + nxt (inner handler đã bị bọc). Gọi nxt, nếu !ok thì
#   gọi LẠI nxt (không gọi tool trực tiếp) tới khi ok hoặc hết attempts.
# ──────────────────────────────────────────────────────────────────────────
class Retry:
    def __init__(self, *, attempts: int = 2) -> None:
        self.attempts = max(1, attempts)

    def __call__(self, request: ToolRequest, nxt: Handler) -> dict[str, Any]:
        env = nxt(request)                       # lần thử đầu — delegate vào inner
        tries = 1
        while (isinstance(env, dict) and not env.get("ok")
               and tries < self.attempts and _retryable(env)):
            env = nxt(request)                   # delegate LẠI vào inner handler
            tries += 1
        return env


# ──────────────────────────────────────────────────────────────────────────
# Tiện ích: bọc một tool callable thành handler, đếm số lần tool THẬT chạy.
#   Tương tự `core` trong kernel: handler vô lõi gọi tool và chuẩn hoá envelope.
# ──────────────────────────────────────────────────────────────────────────
def make_handler(tool: Callable[[ToolRequest], dict[str, Any]]) -> Handler:
    def handler(req: ToolRequest) -> dict[str, Any]:
        raw = tool(req)
        return {"ok": bool(raw.get("ok", True)),
                "data": raw.get("data", {}),
                "metadata": dict(raw.get("metadata", {}))}
    return handler


# ──────────────────────────────────────────────────────────────────────────
# DEMO
# ──────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 70)
    print("CASE 02 — Retry: ConcreteDecorator thêm 'thử lại' không sửa executor")
    print("=" * 70)

    # 1) Tool chập chờn: fail 1 lần đầu, ok từ lần 2. Bọc Retry(attempts=3).
    print("\n[1] Tool chập chờn (fail lần 1, ok lần 2) + Retry(attempts=3):")
    calls = {"n": 0}

    def flaky(req: ToolRequest) -> dict[str, Any]:
        calls["n"] += 1
        ok = calls["n"] >= 2
        print(f"    - flaky.execute() lần {calls['n']} -> ok={ok}")
        return {"ok": ok, "data": {"n": calls["n"]}}

    inner = make_handler(flaky)
    r = Retry(attempts=3)(ToolRequest("flaky"), inner)
    print(f"    kết quả cuối: ok={r['ok']}, data={r['data']}; tool chạy {calls['n']} lần")
    assert r["ok"] is True and r["data"]["n"] == 2
    assert calls["n"] == 2  # delegate qua nxt; tool thật chỉ chạy đúng 2 lần

    # 2) Ma trận đếm số lần gọi nxt (giống tests_audit ...:102-123).
    print("\n[2] Ma trận số lần gọi inner (nxt):")
    cases = [
        # (responses, attempts, expected_calls, expected_ok, mô tả)
        ([{"ok": True}], 5, 1, True, "ok ngay -> 1 lần"),
        ([{"ok": False}, {"ok": True}], 5, 2, True, "fail rồi ok -> 2 lần"),
        ([{"ok": False}] * 5, 3, 3, False, "luôn fail -> dừng đúng attempts=3"),
        ([{"ok": False, "metadata": {"policy_block": True}}], 5, 1, False,
         "policy_block -> KHÔNG retry, 1 lần"),
        ([{"ok": False, "metadata": {"kind": "effect", "idempotent": False}}], 5, 1, False,
         "effect non-idempotent -> KHÔNG retry, 1 lần"),
    ]
    for responses, attempts, exp_calls, exp_ok, desc in cases:
        queue = list(responses)
        seen = []

        def inner_q(req: ToolRequest, _q=queue, _resp=responses, _seen=seen):
            _seen.append(req)
            return _q.pop(0) if _q else _resp[-1]

        res = Retry(attempts=attempts)(ToolRequest("tool"), inner_q)
        print(f"    - {desc:45s} | gọi={len(seen)} ok={res['ok']}")
        assert len(seen) == exp_calls, (desc, len(seen), exp_calls)
        assert res["ok"] is exp_ok, (desc, res["ok"], exp_ok)

    # 3) Bằng chứng "delegate qua nxt": Retry không hề biết tới tool, chỉ biết nxt.
    print("\n[3] Retry stack được — bọc Retry quanh một logging-middleware:")
    log: list[str] = []

    def logging_mw(req: ToolRequest, nxt: Handler) -> dict[str, Any]:
        log.append("log:in")
        res = nxt(req)
        log.append(f"log:out(ok={res['ok']})")
        return res

    attempt = {"n": 0}

    def again(req: ToolRequest) -> dict[str, Any]:
        attempt["n"] += 1
        return {"ok": attempt["n"] >= 2, "data": {}}

    core_handler = make_handler(again)
    # chuỗi: Retry( logging_mw( core ) ) -> Retry gọi lại TOÀN BỘ inner (gồm cả log)
    inner_chain: Handler = lambda req: logging_mw(req, core_handler)
    r3 = Retry(attempts=3)(ToolRequest("again"), inner_chain)
    print(f"    log = {log}")
    print(f"    -> logging_mw chạy lại MỖI lần Retry gọi nxt (2 lần), chứng tỏ retry delegate qua nxt")
    assert r3["ok"] is True
    assert log == ["log:in", "log:out(ok=False)", "log:in", "log:out(ok=True)"]

    # 4) ĐỐI CHỨNG — KHÔNG Retry: tool chập chờn fail luôn.
    print("\n[4] ĐỐI CHỨNG: KHÔNG bọc Retry -> tool chập chờn fail ngay lần đầu:")
    s = {"n": 0}

    def flaky2(req: ToolRequest) -> dict[str, Any]:
        s["n"] += 1
        return {"ok": s["n"] >= 2, "data": {"n": s["n"]}}

    raw = make_handler(flaky2)(ToolRequest("flaky2"))
    print(f"    không Retry -> ok={raw['ok']} (mất kết quả tốt ở lần thử thứ 2)")
    assert raw["ok"] is False

    # 4b) Retry với attempts KHÔNG đủ: tool cần 3 lần mới ok, chỉ cho attempts=2.
    print("\n[4b] ĐỐI CHỨNG: attempts không đủ (cần 3, cho 2) -> vẫn fail:")
    t = {"n": 0}

    def needs_three(req: ToolRequest) -> dict[str, Any]:
        t["n"] += 1
        return {"ok": t["n"] >= 3, "data": {"n": t["n"]}}

    r4 = Retry(attempts=2)(ToolRequest("needs_three"), make_handler(needs_three))
    print(f"    attempts=2 -> ok={r4['ok']}, tool chạy {t['n']} lần (chưa đủ 3)")
    assert r4["ok"] is False and t["n"] == 2

    # 5) Bất biến: executor lõi (tool) KHÔNG có một dòng nào nói về retry.
    print("\n[5] Bất biến: executor KHÔNG biết gì về retry — concern nằm ở decorator.")
    import inspect
    src_flaky = inspect.getsource(flaky)
    src_retry = inspect.getsource(Retry)
    assert "attempts" not in src_flaky and "retry" not in src_flaky.lower()
    assert "attempts" in src_retry
    print("    OK: 'attempts'/'retry' chỉ xuất hiện trong Retry, không có trong tool.")

    print("\n" + "=" * 70)
    print("TẤT CẢ ASSERT PASS — Retry minh hoạ 'thêm hành vi mà không sửa lõi':")
    print("executor không biết retry; Retry stack được; chỉ retry khi an toàn.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
