# Ca 03 — `ToolMiddleware`: Protocol callable hẹp, compose thành chain

> ISP áp lên interface dạng *callable*: port chỉ là **một chữ ký** `__call__(request, nxt) -> dict`. Mỗi middleware (retry, timing, caching, logging) là một policy độc lập conform chữ ký đó; kernel xếp chúng thành chain — không cái nào biết cái khác tồn tại.

---

## 1. Bối cảnh trong hex_agent

Kernel (Epic E01/E06) cần bọc mỗi lần `execute_tool` bằng các *pre/post hook*: đo thời gian, retry khi lỗi tạm thời, gate policy, v.v. Câu hỏi thiết kế: làm sao để thêm/bớt/đảo thứ tự các hook mà không sửa kernel hay sửa các hook khác?

Lời giải ISP: định nghĩa `ToolMiddleware` (`core/middleware.py:11-22`) là một `Protocol` **callable** — interface hẹp đúng một method `__call__(request, nxt)`. Không cần kế thừa (structural typing): bất kỳ object nào "tự nhiên" gọi được với chữ ký đó là một middleware hợp lệ. `Retry` (`middleware/retry.py:23-33`) và `TimingLog` (`middleware/timing.py:10-26`) đều chỉ implement `__call__` và **không biết nhau**.

Điểm tinh tế: `fail_open` là **attribute tùy chọn**. Docstring port ghi rõ — kernel đọc nó bằng `getattr`, "optional by convention — read via getattr, never required; Protocol stays structural". Nghĩa là interface không ép boilerplate `fail_open` lên mọi middleware; chỉ `TimingLog` (advisory telemetry) khai báo `fail_open = True`.

Đã mở kiểm chứng:
- `core/middleware.py:11-22` — `ToolMiddleware(Protocol)` + posture doc về `fail_open`
- `middleware/retry.py:23-33` — `Retry.__call__` (+ `_retryable` ở 14-20)
- `middleware/timing.py:10-26` — `TimingLog` với `fail_open = True`

## 2. Trích đoạn code thật

Port callable hẹp — `core/middleware.py:11-22`:

```python
class ToolMiddleware(Protocol):
    """Receives the request and `nxt` (the inner handler). May act before/after,
    short-circuit (return without calling nxt), or modify the result envelope.

    Failure posture (read by the kernel, optional attribute ...): a middleware MAY
    declare ``fail_open = True`` to mark itself **advisory** ...
    (Optional by convention — read via getattr, never required; Protocol stays structural.)"""

    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]: ...
```

Middleware Retry — `middleware/retry.py:23-33`:

```python
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

Middleware TimingLog với `fail_open` — `middleware/timing.py:10-16`:

```python
class TimingLog:
    fail_open = True  # advisory telemetry — its failure must never block a tool call

    def __init__(self, sink=None) -> None:
        self.sink = sink

    def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
        ...
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò ISP | Trong file `.py` của ca này | Trong hex_agent thật |
|-------------|------------------------------|----------------------|
| Port hẹp dạng callable | `ToolMiddleware(Protocol)` | `core/middleware.py:11-22` |
| Middleware: retry policy | `Retry` (+ `_retryable`) | `middleware/retry.py:23-33` |
| Middleware: timing (advisory) | `TimingLog` (`fail_open=True`) | `middleware/timing.py:10-26` |
| Middleware mới (mở rộng) | `CachingMiddleware`, `LoggingMiddleware` | (cùng port, dễ thêm) |
| Kernel xếp chain | `MiniKernel.execute/_wrap` | kernel chokepoint (E01/E06) |
| Posture đọc qua getattr | `getattr(mw, "fail_open", False)` | kernel đọc `fail_open` qua getattr |

## 4. Bản rút gọn chạy được

File: [`tool_middleware_composition.py`](tool_middleware_composition.py) — chạy `python3 tool_middleware_composition.py`.

Nó **mô phỏng**: port `ToolMiddleware` callable; bốn middleware độc lập (`Retry`, `TimingLog`, `CachingMiddleware`, `LoggingMiddleware`); một `MiniKernel` xếp chúng thành chain bằng closure (outermost trước); sáu bước demo gồm retry handler chập chờn, **không** retry effect non-idempotent, compose 4 tầng với cache hit, và posture `fail_open` (advisory skip) vs blocking (raise → `ok=False`).

Nó **lược bỏ**: `ToolRequest`/`CapabilityResult` đầy đủ, kernel chokepoint thật và toàn bộ vòng đời tool, `metadata` đầy đủ (chỉ giữ `policy_block` / `kind` / `idempotent` mà `Retry` cần). Logic `_retryable` và `fail_open` giữ trung thực với bản gốc.

Đối chứng: `GodMiddleware` nhồi retry + cache vào một `__call__` — vẫn "conform" port (vì port chỉ là `__call__`) nhưng không bật/tắt/reorder/test riêng từng policy được; assert chứng minh Retry re-invoke đến khi `ok`, không re-run effect non-idempotent, cache short-circuit base, và posture fail_open vs blocking đúng.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Thứ tự chain là ngữ nghĩa, dễ sai**: `TimingLog` phải đặt ngoài cùng để đo cả retry; `Caching` đặt ngoài `Timing` sẽ khiến cache hit không qua timing (đúng như demo thấy chỉ 1 mẫu timing). Port hẹp cho linh hoạt nhưng đẩy trách nhiệm "xếp đúng thứ tự" cho người lắp.
- **Port callable quá mơ hồ**: vì chỉ là `__call__`, type checker khó bắt lỗi nếu một middleware quên gọi `nxt`. Đó là cái giá của structural typing rất lỏng — bù lại bằng test từng middleware.
- **Optional attribute (`fail_open`) là con dao hai lưỡi**: tiện vì không ép boilerplate, nhưng người đọc phải biết quy ước. Với một guard/gate, *phải* để `fail_open` vắng (blocking) — quên là nuốt lỗi an toàn.
- Nếu chỉ có 1 hook duy nhất, không cần Protocol + chain; gọi thẳng.

## 6. Câu hỏi tự kiểm tra

1. `ToolMiddleware` không có `register()` hay base class. Một object cần gì để "là" một `ToolMiddleware` hợp lệ? Khái niệm này tên là gì (Mục 2.4 bài gốc)?
2. Vì sao `fail_open` được đọc bằng `getattr(mw, "fail_open", False)` thay vì khai báo trong Protocol? Điều gì sẽ hỏng nếu ép mọi middleware phải có `fail_open`?
3. Trong demo, `Retry` không retry một `effect` non-idempotent. Quy tắc này nằm ở đâu, và tại sao retry side-effect lại nguy hiểm?
