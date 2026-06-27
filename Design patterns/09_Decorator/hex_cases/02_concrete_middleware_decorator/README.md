# Case 02 — `Retry`: ConcreteDecorator thử lại lời gọi lỗi mà không sửa executor

> Flagship: **Retry Middleware: Retrying Failed Calls Without Modifying Executor**
> `Retry` là ví dụ điển hình cho nguyên lý "thêm hành vi mà KHÔNG sửa lõi": executor không biết gì về retry; `Retry` bọc handler, giữ nguyên interface, thêm logic thử lại, và delegate qua `nxt` — KHÔNG gọi tool trực tiếp.

---

## 1. Bối cảnh trong hex_agent

Một số tool chập chờn (network blip, tài nguyên tạm bận). Ta muốn thử lại lời gọi lỗi một cách **trong suốt**, nhưng executor lõi tuyệt đối không nên chứa logic retry — nó chỉ chạy tool. Đồng thời, **không phải lỗi nào cũng được thử lại**: một policy block hay một side-effect không idempotent mà retry thì có thể double-apply (vd gửi tiền hai lần).

`Retry` giải quyết bằng một ConcreteDecorator: nhận `(request, nxt)`, gọi `nxt(request)`, nếu `!ok` và còn lượt và `_retryable()` thì gọi LẠI `nxt` (chứ không gọi tool trực tiếp).

Đã mở và kiểm chứng các file:

- `middleware/retry.py:14-20` — `_retryable()`: cổng logic (chặn retry với `policy_block` và `effect` + `idempotent is False`).
- `middleware/retry.py:23-33` — `class Retry`, `__call__(request, nxt)`.
- `tests/test_middleware.py:83-99` — `test_retry_recovers_flaky_tool`.
- `tests_audit/test_middleware_exact_semantics.py:102-123` — ma trận đếm số lần gọi `nxt`.

---

## 2. Trích đoạn code thật

`middleware/retry.py:14-33`:

```python
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

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        env = nxt(request)
        tries = 1
        while isinstance(env, dict) and not env.get("ok") and tries < self.attempts and _retryable(env):
            env = nxt(request)
            tries += 1
        return env
```

Bằng chứng "tool chỉ chạy đúng 2 lần" — `tests/test_middleware.py:92-99`:

```python
        def execute(self, req):
            self.n += 1
            return {"ok": self.n >= 2, "n": self.n}

    k.registry.register_tool("flaky", Flaky(), feature_name="t")
    k.use(Retry(attempts=3))
    r = k.execute_tool("flaky", {})
    assert r["ok"] is True and r["data"]["n"] == 2
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Decorator (GoF) | Thành phần trong hex_agent |
|---|---|
| `Component` (interface) | Handler `(request) -> dict` (`ToolHandler`, `core/middleware.py:8`) |
| `ConcreteComponent` (lõi) | executor được bọc — KHÔNG biết retry (`core/kernel.py:152-177`) |
| `ConcreteDecorator` | `Retry` (`middleware/retry.py:23-33`) |
| Tham chiếu `inner` (has-a) | `nxt` (có thể là middleware khác hoặc lõi) |
| Điểm chèn hành vi (intercept) | `Retry.__call__` (`middleware/retry.py:27-33`) |
| Cổng điều kiện | `_retryable()` (`middleware/retry.py:14-20`) |
| Cấu hình decorator | `attempts` (`middleware/retry.py:24-25`) |

---

## 4. Bản rút gọn chạy được

File: [`concrete_middleware_decorator.py`](./concrete_middleware_decorator.py) — `python3 concrete_middleware_decorator.py`.

Nó mô phỏng:
- `_retryable()` và `Retry` distill nguyên văn cấu trúc từ `middleware/retry.py`.
- Tool chập chờn (fail lần 1, ok lần 2) được `Retry(attempts=3)` phục hồi; chứng minh tool thật chạy **đúng 2 lần**.
- **Ma trận đếm số lần gọi `nxt`** đúng theo `tests_audit/...:102-123` (ok ngay→1; fail rồi ok→2; luôn fail→dừng đúng `attempts`; `policy_block`→1; effect non-idempotent→1).
- Bằng chứng "delegate qua nxt": bọc `Retry` quanh một logging-middleware → logging chạy lại mỗi lần Retry gọi `nxt`.
- Bất biến qua `inspect.getsource`: chữ "retry"/"attempts" KHÔNG xuất hiện trong tool.

Lược bỏ: kernel/registry/EventBus; `nxt` chỉ là closure quanh tool callable; envelope rút gọn còn `{ok, data, metadata}`.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Không retry side-effect không idempotent**: retry mù có thể double-apply (gửi tiền, gửi email hai lần). `_retryable()` chính là rào an toàn — bỏ nó đi là nguy hiểm.
- **Retry che giấu lỗi thật**: nếu tool fail có hệ thống, retry chỉ làm chậm và che dấu hiệu hỏng.
- **Không backoff**: bản này (và bản thật) retry ngay, không delay — với lỗi do quá tải, retry liên tục có thể làm tệ hơn (cần thêm Strategy backoff nếu cần).
- **Đừng dùng khi tool đã được đảm bảo deterministic/không bao giờ lỗi tạm thời** — retry chỉ thêm độ trễ.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `Retry.__call__` gọi lại `nxt(request)` mà KHÔNG gọi thẳng tool? Điều này cho phép `Retry` stack với middleware khác như thế nào? (Xem section [3] của demo.)
2. Nếu bỏ `_retryable()` đi, kịch bản nào sẽ trở nên nguy hiểm? (Gợi ý: `kind == "effect"` và `idempotent is False`.)
3. Tool cần 3 lần mới ok nhưng `Retry(attempts=2)` — kết quả là gì và vì sao? (Xem section [4b].)
