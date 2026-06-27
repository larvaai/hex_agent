# Case 01 — Hệ middleware quanh `execute_tool` (Chain of Responsibility cốt lõi)

> Ví dụ "kinh điển" của CoR trong hex_agent: một request đi qua một chuỗi middleware; mỗi middleware có quyền **handle** (return sớm), **forward** (gọi `nxt`), hoặc **modulate + forward** (sửa result rồi trả ra). Sender (`execute_tool`) không biết handler nào sẽ xử lý.

---

## 1. Bối cảnh trong hex_agent

hex_agent có **một chokepoint duy nhất** cho mọi lần gọi tool: `AgentKernel.execute_tool`. Mọi mối quan tâm cắt ngang (logging/timing, policy, retry, condense...) KHÔNG được nhét vào từng tool, mà được gắn thành **middleware** bao quanh chokepoint đó. Đây chính là một Chain of Responsibility.

- Interface Handler là một `Protocol` cấu trúc — `core/middleware.py:11-22`:
  > "Receives the request and `nxt` (the inner handler). May act before/after, **short-circuit** (return without calling nxt), or **modify the result envelope**." (`core/middleware.py:12-14`)
- Chuỗi được **dựng động lúc chạy**, từ trong ra ngoài — `core/kernel.py:192-194`.
- Thứ tự đăng ký = outer → inner — `core/kernel.py:100-104` (`use()`), và `core/bootstrap.py:28-53` wire sẵn `timing → policy → retry → condense`.
- Handler cuối chuỗi / fallback là `core(req)` — executor thật của tool — `core/kernel.py:152-177`.

Vấn đề thật được giải: tránh "mega switch-case" trong client, cho phép cấu hình chuỗi lúc chạy, mỗi middleware giữ single-responsibility, và hỗ trợ early-exit (chặn sớm).

## 2. Trích đoạn code thật

Interface Handler (`core/middleware.py:11-22`):

```python
class ToolMiddleware(Protocol):
    """Receives the request and `nxt` (the inner handler). May act before/after,
    short-circuit (return without calling nxt), or modify the result envelope.
    ...
    """
    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]: ...
```

Dựng chuỗi từ trong ra ngoài (`core/kernel.py:192-194`):

```python
handler = core
for mw in reversed(self._middlewares):
    handler = _wrap(mw, handler, on_skip=on_skip)
```

Bind một middleware quanh handler kế tiếp — bước "set_next" (`core/kernel.py:49-62`):

```python
def _wrap(middleware, nxt, on_skip=None):
    ...
    if getattr(middleware, "fail_open", False) is not True:
        def handler(request: ToolRequest) -> dict[str, Any]:
            return middleware(request, nxt)
        return handler
```

Đăng ký middleware, thứ tự outer → inner (`core/kernel.py:100-104`):

```python
def use(self, middleware) -> None:
    """Register a ToolMiddleware. Registration order = outer -> inner."""
    if self._frozen:
        raise RuntimeError("Middleware pipeline is frozen for active sessions.")
    self._middlewares.append(middleware)
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong CoR | Thành phần trong hex_agent |
|---|---|
| `Handler` (interface) | `ToolMiddleware` Protocol — `core/middleware.py:11-22` |
| `ConcreteHandler` | từng middleware: `PolicyGate`, `Retry`, `CondenseResult`, `TimingLog`... |
| tham chiếu "handler kế tiếp" (`next`) | tham số `nxt: ToolHandler` truyền vào `__call__` |
| `set_next` (gắn next vào handler) | `_wrap(middleware, nxt)` — `core/kernel.py:49-62` |
| dựng chuỗi | vòng `for mw in reversed(self._middlewares)` — `core/kernel.py:193-194` |
| `Client` (thả request vào chuỗi) | `AgentKernel.execute_tool` — `core/kernel.py:106-225` |
| handler cuối / fallback | `core(req)` gọi executor thật — `core/kernel.py:152-177` |
| đăng ký handler lúc chạy | `AgentKernel.use` — `core/kernel.py:100-104` |

## 4. Bản rút gọn chạy được

File: [`middleware_system.py`](./middleware_system.py) — chạy `python3 middleware_system.py`.

Nó mô phỏng:
- `MiniKernel.execute_tool` = Client + chain builder; `_wrap` + vòng `reversed` = đúng cơ chế dựng chuỗi của `core/kernel.py:192-194`.
- Ba ConcreteHandler tự viết minh hoạ ba kiểu hành vi của CoR:
  - `Logger` = act-before/after, luôn forward (giống `TimingLog`).
  - `Guard` = gate, short-circuit khi tool trong deny-set (giống `PolicyGate`).
  - `Amplifier` = modulate-and-forward, sửa result sau khi gọi `nxt` (giống `CondenseResult`; xem [case 03](../03_condense_fail_open/) cho bản distill đầy đủ của `CondenseResult` + fail-open).
- Có 4 màn: (1) thứ tự outer→inner, (2) short-circuit khiến core không chạy, (3) cấu hình chuỗi khác lúc chạy, (4) đối chứng `monolith_execute` (if/elif nhồi mọi concern).

Đã **lược bỏ** so với bản thật: `CapabilityRegistry`/executor thật, `EventBus`, `ToolRequest`/`CapabilityResult` schema, nhánh **fail-open** + `_LatchedNext` (`core/kernel.py:24-46, 64-73`), deep-freeze config. Phần fail-open + `_LatchedNext` được distill riêng ở [case 03 — `03_condense_fail_open`](../03_condense_fail_open/) để case này giữ trọng tâm là xương sống CoR.

Đối chứng "không dùng pattern": `monolith_execute` cho thấy nếu trộn policy + logging + amplify vào một hàm thì muốn đổi thứ tự hay thêm `retry` phải sửa thẳng client → vi phạm SRP và Open-Closed.

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chuỗi dài = chi phí dispatch + khó debug.** Mỗi request đi qua N lớp closure; lỗi nằm sâu trong chuỗi khó truy. hex_agent giữ chuỗi ngắn (~4 middleware).
- **Thứ tự là ngầm định và dễ sai.** Đăng ký nhầm thứ tự (ví dụ đặt `condense` trước `retry`) cho hành vi khác hẳn. Bản thật có test riêng cố định thứ tự outer→inner.
- **Khi dispatch chỉ là tra cứu theo loại** (`{type: handler}`, không phụ thuộc thứ tự, không cần forward) thì một dict lookup nhanh và rõ hơn CoR.
- **Handler stateful nguy hiểm.** Vì lý do này, bản thật cố tình KHÔNG wire `BudgetGuard` ở kernel-level (counter per-run sẽ rò qua các run) — xem `core/bootstrap.py:31-32`.

## 6. Câu hỏi tự kiểm tra

1. Vì sao kernel duyệt `reversed(self._middlewares)` khi dựng chuỗi? Nếu KHÔNG đảo, middleware đăng ký trước sẽ nằm trong hay ngoài?
2. `_wrap` (`core/kernel.py:49`) ghi chú "avoids late-binding closure bug". Nếu thay `_wrap` bằng một closure viết thẳng trong vòng `for` mà tham chiếu biến `mw`, bug gì sẽ xảy ra?
3. Một middleware muốn **chặn** một tool nguy hiểm thì phải làm gì khác với một middleware chỉ **đo thời gian**? (Gợi ý: gọi hay không gọi `nxt`.)
