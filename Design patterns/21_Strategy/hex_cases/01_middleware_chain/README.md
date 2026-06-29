# Case 01 — Middleware Pipeline: Pluggable Tool Execution Guards

> Strategy (Behavioral) ở dạng **Strategy + Pipeline/Decorator**: nhiều middleware
> cùng một interface được *compose* (không phải *chọn 1*) thành một chuỗi quanh đúng
> một chokepoint `execute_tool`.

---

## 1. Bối cảnh trong hex_agent

`AgentKernel` có **một chokepoint duy nhất** để chạy tool: `execute_tool()`. Mọi hành vi
cross-cutting (đo thời gian, chặn theo policy, retry khi lỗi tạm thời, giới hạn ngân sách,
condense kết quả) KHÔNG được nhồi vào kernel — nếu nhồi thì kernel phình to, mỗi lần thêm
một guard là sửa lõi, không tắt/bật theo cấu hình được, không test riêng từng guard được.

Giải pháp: mỗi guard là một **middleware** thoả Protocol `ToolMiddleware`
(`core/middleware.py:11-22`), được *inject* vào kernel qua `kernel.use()`
(`core/kernel.py:100-104`) và *compose* thành một handler duy nhất tại
`core/kernel.py:192-194`:

```python
handler = core
for mw in reversed(self._middlewares):
    handler = _wrap(mw, handler, on_skip=on_skip)
```

Builder `_install_middleware()` (`core/bootstrap.py:28-53`) đọc `config['middleware']` và
lắp các strategy theo thứ tự outer→inner: timing → policy → retry → condense. Section vắng
mặt thì middleware đó im lặng không hoạt động — đúng tinh thần config-driven của Strategy.

Tinh tế quan trọng: kernel phân biệt hai **tư thế thất bại** (declarative):
- **fail-closed** (mặc định, mọi gate/guard): middleware raise → lan ra biên thành `ok=False`.
- **fail-open** (`fail_open = True`, advisory như `TimingLog`/`CondenseResult`): middleware
  raise → kernel **skip** nó và tiếp tục với kết quả bên trong (`_wrap`, `core/kernel.py:49-73`),
  có `_LatchedNext` (`core/kernel.py:24-46`) bảo đảm tool không bị chạy đúp.

Và bất biến nghiệp vụ: `Retry` **không** chạy lại một effect non-idempotent
(`middleware/retry.py:14-20`) — chạy lại "trừ tiền" hai lần là tai hoạ.

---

## 2. Trích đoạn code thật

`core/middleware.py:11-22` — Strategy interface:

```python
class ToolMiddleware(Protocol):
    """Receives the request and `nxt` (the inner handler). May act before/after,
    short-circuit (return without calling nxt), or modify the result envelope.
    ...
    a middleware MAY declare ``fail_open = True`` to mark itself **advisory** ...
    """
    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]: ...
```

`middleware/retry.py:23-33` — một ConcreteStrategy:

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

`core/kernel.py:58-73` — composition function `_wrap()` (fail-open vs fail-closed):

```python
if getattr(middleware, "fail_open", False) is not True:
    def handler(request: ToolRequest) -> dict[str, Any]:
        return middleware(request, nxt)
    return handler

def handler(request: ToolRequest) -> dict[str, Any]:
    latched = _LatchedNext(nxt)
    try:
        return middleware(request, latched)
    except Exception as exc:          # advisory failed → skip it, keep the inner result
        if on_skip is not None:
            on_skip(middleware, exc)
        return latched(request)
return handler
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Strategy | Thành phần trong hex_agent | File:line |
|---|---|---|
| **Strategy interface** | `ToolMiddleware` Protocol (`__call__(request, nxt) -> dict`) | `core/middleware.py:11-22` |
| **ConcreteStrategy** | `Retry` | `middleware/retry.py:23-33` |
| **ConcreteStrategy** | `PolicyGate` (short-circuit, không gọi `nxt`) | `middleware/policy.py:9-21` |
| **ConcreteStrategy** | `BudgetGuard` (state per-run) | `middleware/budget.py:10-23` |
| **ConcreteStrategy (fail-open)** | `TimingLog` (`fail_open = True`) | `middleware/timing.py:10-26` |
| **Context** | `AgentKernel`, giữ `_middlewares` | `core/kernel.py:76-104` |
| **Strategy injection** | `kernel.use(middleware)` | `core/kernel.py:100-104` |
| **Composition** | `_wrap()` + `for mw in reversed(...)` | `core/kernel.py:49-73`, `192-194` |
| **Selection by config** | `_install_middleware()` | `core/bootstrap.py:28-53` |

---

## 4. Bản rút gọn chạy được

File: [`middleware_chain.py`](./middleware_chain.py) — `python3 middleware_chain.py` (exit 0).

**Mô phỏng trung thực:**
- `ToolMiddleware` Protocol + 4 ConcreteStrategy (`TimingLog`, `PolicyGate`, `Retry`, `BudgetGuard`)
  giữ nguyên chữ ký `__call__(request, nxt)` và ngữ nghĩa của bản thật.
- `_wrap()` + `_LatchedNext` + `for mw in reversed(...)` sao đúng cơ chế fail-open/fail-closed.
- `build_kernel(config)` mô phỏng `_install_middleware()` chọn strategy theo config.
- Demo chạy **cùng một tool** qua 3 cấu hình pipeline khác nhau → 3 kết quả khác (fail-fast,
  retry vượt transient, policy chặn trước khi chạy); chứng minh Retry không double-apply effect;
  chứng minh advisory raise bị skip mà call vẫn `ok=True`.

**Lược bỏ (thay bằng fake stdlib):** registry/`resolve_tool` thật → dict `{tên: callable}`;
`CapabilityResult`/event-bus/lineage → dict envelope `{"ok": ...}` tối thiểu; `CondenseResult`
và `discipline.Budget` thật → bỏ bớt (BudgetGuard tự đếm in-process).

**Đối chứng:** `HardcodedKernel` nhồi if/elif (policy + retry) vào Context — muốn thêm
BudgetGuard/TimingLog hay đổi thứ tự là phải mở lại class mà sửa (vi phạm Open/Closed).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Thứ tự middleware là một hợp đồng ngầm.** outer→inner quyết định ai chạy trước
  (vd. PolicyGate phải nằm ngoài Retry để không retry một call đã bị chặn). Sai thứ tự = bug
  khó thấy. Pipeline mạnh nhưng đòi kỷ luật về ordering.
- **Tư thế fail-open/fail-closed phải đúng.** Đánh dấu nhầm một guard an toàn thành `fail_open`
  = nuốt lỗi nghiêm trọng. Đây là leak abstraction nếu interface không "truth-telling".
- **State trong middleware là nguồn rò rỉ.** `BudgetGuard` cố tình KHÔNG được wire ở
  kernel-lifetime (`core/bootstrap.py:31-32`) vì counter của nó là per-run — instance dùng chung
  sẽ leak giữa các run. Strategy lý tưởng nên stateless/immutable.
- **Khi chỉ có 1 guard và không thấy trước có cái thứ 2** → một `if` trong execute_tool đơn giản
  hơn, đừng dựng pipeline để đầu cơ trừu tượng.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao kernel duyệt `reversed(self._middlewares)` khi compose, và điều đó làm thứ tự
   đăng ký (`use`) tương ứng outer hay inner trong lúc chạy?
2. `_LatchedNext` giải quyết rủi ro cụ thể nào của một middleware fail-open? Nếu bỏ nó đi,
   tool non-idempotent có thể bị chạy mấy lần trong một call?
3. Tại sao `Retry` cần đọc `metadata.kind` và `metadata.idempotent` thay vì cứ thử lại mọi
   kết quả non-ok? Cho một ví dụ tool mà retry sẽ gây hại.
