# Case 02 — ToolMiddleware chain: cross-cutting concern kiểu Decorator (OCP)

> Decorator (lesson 25, bảng 2.1 cơ chế #3): wrap object hiện có để thêm cross-cutting
> concern (logging, retry, budget) **orthogonal** với core — open for extension theo trục
> "concern", closed for modification ở chokepoint.

---

## 1. Bối cảnh trong hex_agent

Mọi tool call trong hex_agent đi qua **đúng một chokepoint**: `AgentKernel.execute_tool()`.
Bài toán thật: thêm các quan tâm xuyên suốt (đo thời gian, chặn theo policy, retry, giới hạn
ngân sách) mà **không** nhồi tất cả vào `execute_tool` — vì như thế chokepoint sẽ phình to,
mỗi concern mới là 1 lần mổ xẻ code đã test.

Lời giải (đã mở file kiểm chứng):

- **Abstraction:** `ToolMiddleware` Protocol — `core/middleware.py:11-22`:
  `__call__(request, nxt) -> dict`. Mỗi middleware nhận `nxt` (handler bên trong), có thể act
  before/after, **short-circuit** (return không gọi `nxt`), hoặc sửa result. Thuộc tính tùy chọn
  `fail_open=True` đánh dấu middleware **advisory** (telemetry) — nếu raise thì kernel bỏ qua.
- **Decorator factory:** `_wrap(middleware, nxt, on_skip)` — `core/kernel.py:49-73`. Tạo closure
  bind 1 middleware quanh handler kế tiếp (tránh late-binding bug). Nhánh fail-open dùng
  `_LatchedNext` (`core/kernel.py:24-46`) — proxy one-shot, đảm bảo tool **không chạy 2 lần** nếu
  middleware advisory raise sau khi đã gọi `nxt` (an toàn cho tool non-idempotent).
- **Dựng chain:** `core/kernel.py:192-194` — `handler = core; for mw in reversed(_middlewares):
  handler = _wrap(mw, handler)`. Reversed để order đăng ký = outer → inner.
- **Extension point:** `AgentKernel.use(middleware)` — `core/kernel.py:100-104` — chỉ `append`
  vào list. Wiring theo config ở `core/bootstrap.py:28-53` (`_install_middleware`).

Các concrete middleware thật: `middleware/timing.py:1-26` (TimingLog, `fail_open`),
`middleware/policy.py:1-21` (PolicyGate, short-circuit), `middleware/retry.py:1-33` (Retry,
gọi `nxt` lặp lại), `middleware/budget.py`, `middleware/condense.py`.

---

## 2. Trích đoạn code thật

`core/middleware.py:11-22` — abstraction:

```python
class ToolMiddleware(Protocol):
    """Receives the request and `nxt` (the inner handler). May act before/after,
    short-circuit (return without calling nxt), or modify the result envelope."""
    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]: ...
```

`core/kernel.py:192-194` — dựng chain bằng `reversed`, **logic này không đổi khi thêm middleware**:

```python
handler = core
for mw in reversed(self._middlewares):
    handler = _wrap(mw, handler, on_skip=on_skip)
```

`core/kernel.py:100-104` — extension point:

```python
def use(self, middleware) -> None:
    """Register a ToolMiddleware. Registration order = outer -> inner."""
    if self._frozen:
        raise RuntimeError("Middleware pipeline is frozen for active sessions.")
    self._middlewares.append(middleware)
```

`middleware/retry.py:27-33` — một concrete decorator (gọi `nxt` lặp lại):

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

| Vai trò OCP / Decorator | Thành phần trong hex_agent | File:line |
|---|---|---|
| Abstraction | `ToolMiddleware` Protocol | `core/middleware.py:11-22` |
| Concrete decorators | `TimingLog`, `PolicyGate`, `Retry`, `BudgetGuard`, `CondenseResult` | `middleware/timing.py:1-26`, `policy.py:1-21`, `retry.py:1-33`, `budget.py`, `condense.py` |
| Decorator factory | `_wrap()` | `core/kernel.py:49-73` |
| Wrapper an toàn fail-open | `_LatchedNext` | `core/kernel.py:24-46` |
| Orchestrator dựng chain | `execute_tool()` (vòng `reversed`) | `core/kernel.py:192-194` |
| Extension point | `AgentKernel.use()` | `core/kernel.py:100-104` |
| Wiring theo config | `_install_middleware()` | `core/bootstrap.py:28-53` |

---

## 4. Bản rút gọn chạy được

File: [`middleware_decorator_chain.py`](./middleware_decorator_chain.py)
(`python3 middleware_decorator_chain.py`, exit 0).

**Mô phỏng:** `ToolMiddleware` Protocol, `_LatchedNext`, `_wrap`, `AgentKernel.use/execute_tool`
(dựng chain bằng `reversed`), và 4 concrete middleware: `LoggingMiddleware` (advisory, `fail_open`),
`PolicyGate` (short-circuit), `RetryMiddleware`, `BudgetGate`. Demo chứng minh:
- chồng nhiều middleware bằng `use()` (composition, không inheritance) — chúng không xung đột;
- `PolicyGate` short-circuit khiến tool bị deny **không bao giờ chạy**;
- thêm `BudgetGate` mà `execute_tool` **không đổi 1 dòng** (kiểm bằng `inspect.getsource`);
- `BrokenTelemetry` (advisory raise sau khi gọi `nxt`) bị **skip**, và nhờ `_LatchedNext`, tool
  side-effect chỉ chạy **đúng 1 lần** (assert `runs["side_effect"] == 1`).

**Lược bỏ:** envelope `CapabilityResult`, lineage/events, scope check, `_retryable` (kind/idempotent
metadata). Giữ nguyên cơ chế cốt lõi: chain `reversed`, `fail_open` + `_LatchedNext`, short-circuit.

**Đối chứng anti-OCP:** không có hàm anti riêng — đối chứng nằm ngay ở invariant: nếu nhồi
logging/retry/budget **vào trong** `execute_tool` bằng if-flag, mỗi concern mới là 1 lần sửa
chokepoint đã test (regression chéo). Bản này cho thấy concern đến qua `use()`, chokepoint bất biến.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Khó trace:** một call đi qua nhiều wrapper lồng nhau; debug phải lần qua từng lớp (lesson 25,
  bảng Trade-offs). Thứ tự đăng ký (outer→inner) ảnh hưởng hành vi — dễ sai nếu không cẩn thận.
- **Đúng/sai posture rất tinh tế:** fail-open vs fail-closed, latch để tránh double-run tool
  non-idempotent — sai 1 ly là double-apply side-effect. Đây là chi phí "Decorator + retry" thật.
- **Đừng dùng cho logic nghiệp vụ cốt lõi** của 1 tool — middleware chỉ cho concern *xuyên suốt,
  orthogonal*. Nhồi business logic vào middleware là sai trục abstraction.
- Khi chỉ có 1 concern duy nhất và mãi mãi như vậy: viết thẳng còn rõ hơn.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao chain được dựng bằng `for mw in reversed(self._middlewares)`? Nếu bỏ `reversed`, thứ tự
   outer/inner thay đổi thế nào, và `TimingLog` (đo wall-time) có còn bao trọn tool không?
2. `_LatchedNext` giải quyết rủi ro gì? Mô tả kịch bản một middleware `fail_open` gọi `nxt` rồi
   raise — nếu **không** có latch thì tool non-idempotent sẽ bị gì?
3. `PolicyGate` *không* gọi `nxt` khi deny. Tính chất "short-circuit" này của Decorator giúp gì
   cho OCP so với việc nhét một `if request.name in deny:` vào giữa `execute_tool`?
