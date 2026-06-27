# Case 01 — Chuỗi Middleware Decorator trong `AgentKernel`

> Flagship: **Complete Middleware Decorator Chain in AgentKernel**
> Đây là bản hiện thực Decorator (GoF, Structural) "thuần" nhất trong hex_agent: nhiều middleware cùng một interface bọc quanh executor lõi, thêm các cross-cutting concern (timing, policy, retry, condense) mà KHÔNG sửa logic thực thi tool.

---

## 1. Bối cảnh trong hex_agent

`AgentKernel.execute_tool()` là **chokepoint duy nhất** để chạy mọi tool. Mọi mối quan tâm "cắt ngang" (cross-cutting) — đo thời gian, chặn theo policy, thử lại khi lỗi, nén kết quả lớn — đều cần áp lên mọi tool mà **không được** trộn vào logic của từng tool. Nếu trộn, mỗi tool phải lặp lại boilerplate, và thêm một concern mới = sửa mọi tool (và nếu dùng inheritance thì bùng nổ `2^N` lớp tổ hợp như `BudgetRetryTimingPolicyCondenseExecutor`).

Giải pháp: mỗi middleware là một **ConcreteDecorator** cùng interface `__call__(request, nxt) -> dict`, bọc quanh handler kế tiếp. Kernel dựng chuỗi bằng cách lặp `reversed(self._middlewares)` và bọc dần.

Đã mở và kiểm chứng các file:

- `core/kernel.py:49-73` — hàm `_wrap()` lắp một middleware quanh `nxt`.
- `core/kernel.py:192-194` — vòng lặp dựng chuỗi trong `execute_tool()`.
- `core/kernel.py:24-46` — `_LatchedNext`, proxy caching một-lần chống chạy lại tool.
- `core/middleware.py:11-22` — `ToolMiddleware` Protocol (interface decorator).
- `core/bootstrap.py:28-53` — `_install_middleware()` quyết định thứ tự outer→inner.

---

## 2. Trích đoạn code thật

Hàm lắp ráp decorator — `core/kernel.py:49-62`:

```python
def _wrap(middleware, nxt, on_skip=None):
    """Bind one middleware around the next handler (avoids late-binding closure bug)."""
    if getattr(middleware, "fail_open", False) is not True:
        def handler(request: ToolRequest) -> dict[str, Any]:
            return middleware(request, nxt)

        return handler
    ...
```

Client dựng & gọi chuỗi — `core/kernel.py:192-196`:

```python
        handler = core
        for mw in reversed(self._middlewares):
            handler = _wrap(mw, handler, on_skip=on_skip)
        try:
            envelope = handler(request)
```

Interface decorator — `core/middleware.py:22`:

```python
    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]: ...
```

Thứ tự lắp ráp outer→inner — `core/bootstrap.py:34-53` (rút gọn): `TimingLog` → `PolicyGate` → `Retry` → `CondenseResult`.

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Decorator (GoF) | Thành phần trong hex_agent |
|---|---|
| `Component` (interface) | Handler `Callable[[ToolRequest], dict]` = `ToolHandler` (`core/middleware.py:8`) |
| `ConcreteComponent` (lõi) | `core` — closure lõi gọi `executor.execute(req)` (`core/kernel.py:152-177`) |
| `Decorator`/`ConcreteDecorator` | `TimingLog`, `PolicyGate`, `Retry`, `CondenseResult` (`middleware/*.py`) |
| Tham chiếu `inner` (has-a) | tham số `nxt` mà mỗi middleware delegate vào |
| Logic lắp ráp decorator | `_wrap()` + vòng `for mw in reversed(...)` (`core/kernel.py:49-73, 193-194`) |
| Client dựng & gọi chuỗi | `execute_tool()` (`core/kernel.py:106-225`) |
| Caching/one-shot proxy | `_LatchedNext` (`core/kernel.py:24-46`) |

---

## 4. Bản rút gọn chạy được

File: [`middleware_chain_architecture.py`](./middleware_chain_architecture.py) — `python3 middleware_chain_architecture.py`.

Nó mô phỏng:
- `Kernel.use()` + dựng chuỗi `reversed()` + `_wrap()` (đúng cơ chế lắp ráp).
- 4 ConcreteDecorator distill từ `middleware/`: `TimingLog` (post, fail_open), `PolicyGate` (guard, short-circuit), `Retry` (gọi nxt nhiều lần), `CondenseResult` (post, fail_open, đệ quy cắt chuỗi).
- `_LatchedNext` + posture fail-open/fail-closed.
- Demo: lõi trần ↔ lõi bọc cùng interface; chuỗi đầy đủ; PolicyGate short-circuit (lõi chạy 0 lần); **đổi thứ tự đổi semantic** (`A:in,B:in,B:out,A:out` vs đảo lại); Retry phục hồi tool chập chờn.

Lược bỏ: `EventBus`, `CapabilityRegistry`, `CapabilityResult`, deep-freeze, lineage/request_id ngẫu nhiên, `discipline.condense` thật (thay bằng slicing đệ quy). Cấu trúc Decorator được giữ nguyên 100%.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Thứ tự là semantic**: lắp sai thứ tự = sai hành vi (vd cache-trước-log thì log không thấy cache hit). Phải khai báo thứ tự tường minh.
- **Khó debug stack trace**: lỗi đi qua N lớp wrapper khó lần dấu vết hơn một hàm phẳng.
- **Chi phí indirection**: mỗi call đi qua nhiều lớp gọi hàm; với hot-path cực nóng có thể không đáng.
- **Đừng dùng khi chỉ có 1 concern cố định cho 1 tool** — lúc đó bọc decorator là over-engineering; viết thẳng đơn giản hơn.
- **Stateful middleware** (như `BudgetGuard` đếm theo run) phải cẩn thận vòng đời: `core/bootstrap.py:31-32` cố tình KHÔNG wire `BudgetGuard` ở tầm kernel vì counter là per-run.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `execute_tool()` lặp `reversed(self._middlewares)` khi dựng chuỗi? Nếu lặp xuôi thì middleware đăng ký đầu tiên sẽ nằm ở vị trí nào trong chuỗi?
2. `PolicyGate` short-circuit bằng cách nào, và làm sao chứng minh lõi (`core`) không hề chạy khi tool bị deny? (Xem section [3] của demo.)
3. `_LatchedNext` chỉ được dùng ở nhánh fail-open. Tại sao nhánh fail-closed (gồm `Retry` — vốn cố ý gọi `nxt` nhiều lần) lại nhận `nxt` thô chứ không latch? (Gợi ý: `core/kernel.py:55-56`.)
