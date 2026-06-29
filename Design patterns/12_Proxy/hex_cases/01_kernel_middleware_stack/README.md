# Case 01 — Middleware Chain as Proxy Stack (Stacked Proxy)

> **Một câu chốt:** Mỗi middleware trong hex_agent là một **Proxy** đứng cùng interface với tool handler thật (`ToolHandler`), chèn một cross-cutting concern (auth, rate-limit, retry, timing), rồi delegate cho tầng kế tiếp (`nxt`). Kernel **xếp chồng** chúng quanh một chokepoint duy nhất — client (vòng lặp agent) KHÔNG biết có bao nhiêu proxy ở giữa.

---

## 1. Bối cảnh trong hex_agent

hex_agent có **một** điểm nghẽn duy nhất để chạy mọi tool: `AgentKernel.execute_tool` (`core/kernel.py:106-225`). Mọi cross-cutting concern (chính sách an toàn, ngân sách lặp, retry, đo thời gian, condense kết quả) KHÔNG được nhét vào client (vòng lặp agent) cũng KHÔNG nhét vào tool thật — mà đặt thành **middleware** bọc quanh chokepoint này.

Vấn đề thật: nếu vòng lặp agent tự kiểm tra policy, tự đếm budget, tự retry trước mỗi lời gọi tool, thì logic đó sẽ lặp lại ở mọi call-site, vi phạm SRP và Open-Closed — thêm một concern mới phải sửa khắp nơi.

Giải pháp: định nghĩa interface Proxy `ToolMiddleware` (`core/middleware.py:11-22`) với chữ ký `__call__(request, nxt)`, rồi lắp chuỗi proxy quanh `core` (RealSubject) theo thứ tự ngược (`core/kernel.py:192-194`):

- `core/kernel.py:152-177` — `core(req)`: **RealSubject**, resolve + execute tool, đóng gói envelope.
- `core/kernel.py:49-73` — `_wrap`: bind một middleware quanh `nxt`, phân biệt **fail-closed** (raise lan ra) và **fail-open** (advisory, raise -> bỏ qua).
- `core/kernel.py:24-46` — `_LatchedNext`: one-shot proxy quanh inner handler, đảm bảo middleware fail-open raise sau khi đã gọi `nxt` không double-run tool.
- `core/kernel.py:192-194` — vòng lắp chuỗi: `for mw in reversed(self._middlewares): handler = _wrap(mw, handler)`.
- `core/bootstrap.py:28-53` — thứ tự cài đặt outer -> inner: timing, policy, retry, condense.

Các proxy cụ thể: `middleware/policy.py:9-21` (PolicyGate), `middleware/budget.py:10-23` (BudgetGuard), `middleware/retry.py:23-33` (Retry), `middleware/timing.py:10-26` (TimingLog), `middleware/condense.py:11-30` (CondenseResult).

---

## 2. Trích đoạn code thật

Interface Proxy (`core/middleware.py:11-22`):

```python
class ToolMiddleware(Protocol):
    """Receives the request and `nxt` (the inner handler). May act before/after,
    short-circuit (return without calling nxt), or modify the result envelope."""
    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]: ...
```

Lắp chuỗi proxy (`core/kernel.py:192-194`):

```python
handler = core
for mw in reversed(self._middlewares):
    handler = _wrap(mw, handler, on_skip=on_skip)
```

Một Proxy cụ thể — PolicyGate, Protection Proxy (`middleware/policy.py:15-21`):

```python
def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
    if request.name in self.deny:
        if self.on_block:
            self.on_block(request)
        return {"ok": False, "capability": request.name, "feature": None, "data": {},
                "error": f"Blocked by policy: {request.name}", "metadata": {"policy_block": True}}
    return nxt(request)
```

Smart-reference Proxy — Retry gọi `nxt` lại (`middleware/retry.py:27-33`):

```python
def __call__(self, request: ToolRequest, nxt) -> dict[str, Any]:
    env = nxt(request)
    tries = 1
    while isinstance(env, dict) and not env.get("ok") and tries < self.attempts and _retryable(env):
        env = nxt(request)
        tries += 1
    return env
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Proxy (GoF) | Thành phần trong hex_agent | File:line |
|---|---|---|
| **Subject interface** | `ToolHandler = Callable[[ToolRequest], dict]` | `core/middleware.py:8` |
| **Proxy interface** | `ToolMiddleware.__call__(request, nxt)` | `core/middleware.py:11-22` |
| **RealSubject** | `core(req)` — resolve + execute tool thật | `core/kernel.py:152-177` |
| **Proxy: Protection** | `PolicyGate` (deny-list, short-circuit) | `middleware/policy.py:9-21` |
| **Proxy: Rate-limit** | `BudgetGuard` (chặn lặp cùng tool) | `middleware/budget.py:10-23` |
| **Proxy: Smart Reference** | `Retry` (gọi `nxt` lại khi non-ok) | `middleware/retry.py:23-33` |
| **Proxy: Smart Reference (advisory)** | `TimingLog` (`fail_open=True`) | `middleware/timing.py:10-26` |
| **Cơ chế xếp chồng** | `_wrap` + vòng `reversed` | `core/kernel.py:49-73, 192-194` |
| **One-shot guard** | `_LatchedNext` | `core/kernel.py:24-46` |
| **Client** | vòng lặp agent gọi `execute_tool` | `core/kernel.py:106` |

---

## 4. Bản rút gọn chạy được

File: [`kernel_middleware_stack.py`](./kernel_middleware_stack.py)

Nó mô phỏng:
- `ToolCore` = RealSubject "naive" (chỉ chạy tool, đếm số lần thực thi).
- Bốn proxy thật được distill 1-1: `PolicyGate`, `BudgetGuard`, `Retry`, `TimingLog`.
  - *Lưu ý chữ ký:* `BudgetGuard` THẬT (`middleware/budget.py:10-23`) nhận một đối tượng `Budget` (`__init__(self, budget: Budget, ...)`) và uỷ thác đếm cho `Budget.record_tool_call` / `Budget.same_tool_exceeded` (`discipline/budget.py:56-67`). Bản distill ở đây gộp bộ đếm (`_counts`) vào thẳng trong proxy và dùng `__init__(self, *, max_same=2, ...)` cho gọn — cùng hành vi, khác cách bố trí trạng thái.
- `Kernel.use()` + `Kernel.execute_tool()` lắp chuỗi proxy theo `reversed` order, đúng như `kernel.py:192-194`.
- Giữ nguyên `_LatchedNext` và `_wrap` (fail-closed vs fail-open).

Nó lược bỏ: EventBus/telemetry, CapabilityRegistry/ports, deep-copy args, lineage/context, `CapabilityResult`. Hạ tầng LLM/DB/network được thay bằng một dict tool đơn giản. Mục [6] của demo là **đối chứng**: viết tay một client "naive" tự nhúng auth+budget+retry để cho thấy logic rò rỉ và không scale khi không dùng Proxy.

Chạy:

```bash
python3 kernel_middleware_stack.py
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Thứ tự proxy là load-bearing.** Auth phải trước cache; timing nên ngoài cùng. Đặt sai thứ tự = lỗ hổng hoặc đo sai (xem `bootstrap.py:28-53`).
- **Khó debug do nhiều tầng.** Một envelope `ok=False` có thể đến từ bất kỳ tầng nào; cần metadata (`policy_block`, `budget_block`) để truy vết — bản thật publish event `middleware.skipped` cho đúng việc này.
- **Bẫy double-run.** Một fail-open middleware gọi `nxt` rồi raise có thể chạy lại tool không idempotent; phải có `_LatchedNext`. Nếu pattern đơn giản (1 concern, 1 nơi gọi) thì một wrapper thẳng còn rõ hơn cả chuỗi.
- **Retry + side-effect.** Retry chỉ an toàn với tool read/idempotent; `_retryable` (`retry.py:14-20`) chặn re-run effect không idempotent — bỏ guard này là double-apply.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao chuỗi được lắp bằng `reversed(self._middlewares)`? Nếu bỏ `reversed`, thứ tự thực thi của TimingLog và PolicyGate sẽ đổi thế nào?
2. `TimingLog` đặt `fail_open = True` còn `PolicyGate` thì không. Nếu một sink telemetry của TimingLog ném exception, kết quả tool có bị fail không? Còn nếu PolicyGate ném exception?
3. `_LatchedNext` bảo vệ điều gì? Cho một kịch bản tool KHÔNG idempotent bị chạy hai lần nếu thiếu nó.
