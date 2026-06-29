# Case 01 — AgentKernel.execute_tool: Chokepoint Mediator + middleware pipeline

> Mediator dạng **Command-Bus + middleware**: mọi request gọi tool đều bị ép qua
> đúng **một** điểm `kernel.execute_tool`. Kernel là ConcreteMediator giữ danh
> sách middleware (colleague cắt ngang) và bọc chúng quanh một resolver chọn
> executor cuối qua registry. Caller không biết executor, middleware không biết
> nhau, executor không biết ai gọi.

---

## 1. Bối cảnh trong hex_agent

`hex_agent` là một runtime agent: agent/task cần gọi đủ thứ "capability" — `llm.chat`,
đọc/ghi state, tool ngoài... Nếu mỗi caller tự tìm executor rồi tự nhồi các mối quan
tâm cắt ngang (logging, đo thời gian, retry, kiểm tra capability scope, billing),
ta rơi vào đúng cảnh **N×N coupling** mà bài học gốc cảnh báo: thêm một mối quan
tâm = sửa mọi caller; thêm một caller = copy-paste lại toàn bộ.

Lời giải của hex_agent: **một chokepoint duy nhất**. Toàn bộ behavior cắt ngang sống
trong middleware bọc quanh `execute_tool`; còn behavior cụ thể của từng tool sống
sau ports/adapters trong registry. Docstring của `AgentKernel` nói thẳng điều này:

- `core/kernel.py:76-83` — "cross-cutting behavior lives in middleware around the
  single execute_tool chokepoint."
- `core/kernel.py:106-225` — thân `execute_tool`: publish `tool.requested`, kiểm tra
  scope, định nghĩa `core` resolver, **bọc middleware** rồi gọi, cuối cùng publish
  `tool.completed`/`tool.failed`.
- `core/kernel.py:100-104` — `use()` đăng ký một middleware; thứ tự đăng ký =
  outer → inner.
- `core/registry.py:103-112` — `resolve_tool()` map `tool_name` → executor (exact
  thắng; thiếu thì rơi về `NullToolPort`).

Đã mở và kiểm chứng các dòng trên trong file thật.

---

## 2. Trích đoạn code thật

Resolver `core` (người nhận cuối) + vòng bọc middleware, từ `core/kernel.py:152-194`:

```python
def core(req: ToolRequest) -> dict[str, Any]:
    resolution = self.registry.resolve_tool(req.name)        # registry chọn executor
    try:
        result = resolution.executor.execute(req)            # gọi executor cuối
    except Exception as exc:  # a tool must never crash the kernel
        result = {"ok": False, "tool": req.name, "error": str(exc), "kernel_error": True}
    ...
    return CapabilityResult.from_raw(...).as_dict()

# ...
handler = core
for mw in reversed(self._middlewares):                       # bọc outer -> inner
    handler = _wrap(mw, handler, on_skip=on_skip)
try:
    envelope = handler(request)
except Exception as exc:  # a middleware must never crash the kernel boundary
    envelope = CapabilityResult(ok=False, capability=request.name, error=str(exc), ...).as_dict()
```

Cơ chế "fail-open vs fail-closed" của một colleague, từ `core/kernel.py:49-73`:

```python
def _wrap(middleware, nxt, on_skip=None):
    if getattr(middleware, "fail_open", False) is not True:
        def handler(request: ToolRequest) -> dict[str, Any]:
            return middleware(request, nxt)          # fail-closed: raise -> propagate
        return handler

    def handler(request: ToolRequest) -> dict[str, Any]:
        latched = _LatchedNext(nxt)
        try:
            return middleware(request, latched)
        except Exception as exc:                     # advisory hỏng -> skip, giữ inner
            if on_skip is not None:
                on_skip(middleware, exc)
            return latched(request)
    return handler
```

Đăng ký một middleware, từ `core/kernel.py:100-104`:

```python
def use(self, middleware) -> None:
    """Register a ToolMiddleware. Registration order = outer -> inner."""
    if self._frozen:
        raise RuntimeError("Middleware pipeline is frozen for active sessions.")
    self._middlewares.append(middleware)
```

Một colleague cụ thể — `Retry` — gọi `nxt` lặp lại, từ `middleware/retry.py:27-33`:

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

| Vai trò Mediator | Thành phần trong hex_agent | File:line |
|---|---|---|
| **ConcreteMediator** | `AgentKernel` (sở hữu `_middlewares` + `registry`, điều phối chuỗi) | `core/kernel.py:76-225` |
| **Điểm `notify` / chokepoint** | `AgentKernel.execute_tool()` | `core/kernel.py:106-225` |
| **Đăng ký colleague** | `AgentKernel.use()` (outer → inner) | `core/kernel.py:100-104` |
| **Colleague (cắt ngang)** | Middleware: `Retry`, `TimingLog`, condense, policy, billing | `middleware/retry.py`, `middleware/timing.py`, ... |
| **Message tham số hoá** | `ToolRequest` (name, args, context) | `core/schemas.py` (qua `core/kernel.py:114`) |
| **Routing/dispatch cuối** | `core(req)` resolver gọi `registry.resolve_tool` rồi `executor.execute` | `core/kernel.py:152-177` |
| **Bảng map name → executor** | `CapabilityRegistry.resolve_tool()` | `core/registry.py:103-112` |
| **Người nhận cuối (colleague thực thi)** | executor sau port (vd `llm.chat` adapter), hoặc `NullToolPort` | `core/registry.py:29-40` |
| **Bọc 1 colleague quanh handler kế** | `_wrap()` (+ `_LatchedNext` one-shot) | `core/kernel.py:24-73` |

Điểm khớp đắt giá: đây là biến thể **Command Bus** trong mục 2.4 của bài học gốc —
"middleware (logging, validation, transaction, retry) gắn vào bus, chạy auto cho
mọi command". Caller chỉ biết `execute_tool(name, args)`, y như `bus.dispatch(cmd)`.

---

## 4. Bản rút gọn chạy được

File: [`kernel_middleware_mediator.py`](./kernel_middleware_mediator.py) — chỉ dùng
thư viện chuẩn, chạy `python3 kernel_middleware_mediator.py` (exit 0).

Nó **mô phỏng**:
- `AgentKernel` + `execute_tool` chokepoint, `use()` đăng ký outer → inner.
- `_wrap()` bọc middleware theo `reversed(_middlewares)` y như bản thật.
- `CapabilityRegistry.resolve_tool` + `NullToolPort` fallback.
- 4 colleague: `ScopeGate` (capability gate), `LoggingMw`, `TimingLog`
  (`fail_open=True`), `Retry` (gọi `nxt` lặp khi `!ok`).
- Đối chứng `TanglingCaller`: caller tự ráp scope + log + retry và giữ ref executor
  trực tiếp — minh hoạ N×N coupling khi vứt mediator.

Nó **lược bỏ** (so với bản thật): LLM/DB/network thật; lineage + event-envelope đầy
đủ; `CapabilityResult` chuẩn hoá; `_deep_freeze`/`freeze` config; `_LatchedNext`
one-shot (bản rút gọn vẫn chứng minh fail-open bằng một middleware raise sau khi đã
có kết quả inner); descriptor `kind/idempotent/risk` của registry.

> ⚠️ **Đánh đổi của việc bỏ `_LatchedNext` (rủi ro double-run).** Nhánh fail-open ở
> bản rút gọn gọi lại `nxt(request)` trong `except`. Nếu một middleware `fail_open=True`
> raise **sau** khi đã gọi `nxt` (đã chạm executor), executor sẽ chạy **2 lần** — đã
> kiểm chứng: 2 calls ở bản rút gọn vs 1 ở kernel thật. Đây đúng là lỗi double-run mà
> `_LatchedNext` one-shot ở bản thật (`core/kernel.py:24-46`, docstring _"FM-HIGH,
> non-idempotent"_) sinh ra để **chặn**: nó latch `nxt` để post-nxt raise replay kết
> quả cũ thay vì re-execute. Với tool **non-idempotent** (charge, write, send) đây là
> lỗi thật, không chỉ là chi tiết bị giản lược. Demo [6] dùng middleware raise *sau*
> `nxt` nên về mặt số lần executor cũng đang bị gọi đôi — chấp nhận được cho mục đích
> minh hoạ fail-open, nhưng phải hiểu rõ rủi ro khi bê pattern này vào production.

Các bước demo in ra: gọi `echo` (đi hết chuỗi), `flaky` (Retry gọi executor đúng 3
lần), tool ngoài scope (bị `ScopeGate` chặn trước executor), tool chưa đăng ký
(`NullToolPort` giữ kernel sống), fail-open (TimingLog hỏng → skip, tool vẫn ok), và
đối chứng `TanglingCaller`.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Single point of failure**: chokepoint chết thì mọi tool đứng. Bản thật phòng bị
  bằng nhiều lớp "không bao giờ làm sập kernel" (`core/kernel.py:156-157, 197-209`).
- **Overhead indirection**: mỗi call đi qua N lớp middleware. Trong tight loop hiệu
  năng cao, indirection này là chi phí thật — bài học gốc 1.4 cảnh báo điều này.
- **Nguy cơ God Object**: nếu nhồi quá nhiều logic vào kernel/middleware thay vì tách
  theo trách nhiệm, ta cô đặc phức tạp chứ không giảm (cảnh báo 1.5 của bài gốc). Ở
  hex_agent điều này được giữ bằng cách mỗi middleware có đúng một trách nhiệm.
- **Thứ tự middleware là ngữ nghĩa**: đăng ký sai thứ tự (vd Retry ngoài Scope) đổi
  hành vi một cách tinh vi. Phải coi thứ tự `use()` như một phần API.
- Nếu chỉ có 1-2 tool, tương tác ổn định, gọi thẳng đơn giản hơn nhiều.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `execute_tool` bọc middleware bằng `for mw in reversed(self._middlewares)`?
   Nếu bỏ `reversed`, thứ tự "outer → inner" mà `use()` hứa hẹn có còn đúng không?
2. `TimingLog` đặt `fail_open = True` còn `Retry` thì không. Khi mỗi cái raise giữa
   chừng, biên kernel xử lý khác nhau ra sao, và vì sao Retry **không** được latch
   `nxt` như nhánh fail-open?
3. Đây là Mediator hay chỉ là Chain of Responsibility? Dựa vào việc *ai chọn người
   nhận cuối* (registry-resolve trong `core`) và *ai quyết định chuỗi*, hãy lập luận.
