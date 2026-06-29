# Decorator Pattern trong hex_agent — Hex Cases

> Tài liệu dạy học: pattern **Decorator (GoF, Structural)** xuất hiện THẬT trong codebase `hex_agent`, distill thành các case chạy được bằng thư viện chuẩn Python 3.14.

---

## Tổng quan

Decorator được hiện thực nổi bật xuyên suốt **tầng middleware** của hex_agent. Nhiều lớp middleware (`BudgetGuard`, `Retry`, `TimingLog`, `CondenseResult`, `PolicyGate`) cùng bọc executor tool lõi qua **một interface chung** `ToolMiddleware` — `__call__(request, nxt) -> dict` — để thêm các mối quan tâm cắt ngang (budgeting, retry, timing, nén kết quả, policy gate) mà KHÔNG sửa logic thực thi lõi.

`AgentKernel.execute_tool()` dựng một **chuỗi middleware** bằng cách bọc liên tiếp các handler: nó lặp `reversed(self._middlewares)` và bọc dần quanh closure `core`, tạo ra chuỗi composition delegate từ decorator ngoài cùng vào executor trong cùng.

Đây là Decorator GoF "kinh điển" áp cho HTTP-style middleware. Nó tránh bùng nổ `2^N` lớp con (vd `BudgetRetryTimingPolicyCondenseExecutor`) bằng cách **xếp chồng** các concern độc lập. Thêm một middleware mới = thêm 1 lớp, không phải tổ hợp bùng nổ.

### Ánh xạ vai trò (tóm tắt)

| Vai trò Decorator | Thành phần hex_agent |
|---|---|
| `Component` interface | Handler `(ToolRequest) -> dict` = `ToolHandler` (`core/middleware.py:8`) |
| `ConcreteComponent` | closure `core` gọi executor lõi (`core/kernel.py:152-177`) |
| `ConcreteDecorator` | `PolicyGate` / `BudgetGuard` / `Retry` / `TimingLog` / `CondenseResult` (`middleware/*.py`) |
| `inner` (has-a) | tham số `nxt` |
| Logic lắp ráp | `_wrap()` (`core/kernel.py:49-73`) |
| Client dựng & gọi chuỗi | `execute_tool()` (`core/kernel.py:106-225`) |

---

## Các case con

| # | Thư mục | Flagship | Trọng tâm |
|---|---------|----------|-----------|
| 01 | [`01_middleware_chain_architecture/`](./01_middleware_chain_architecture/) | Complete Middleware Decorator Chain in AgentKernel | Cơ chế dựng & gọi chuỗi: `_wrap()`, `reversed()`, thứ tự outer→inner, short-circuit, fail-open/fail-closed, `_LatchedNext`. |
| 02 | [`02_concrete_middleware_decorator/`](./02_concrete_middleware_decorator/) | Retry Middleware: Retrying Failed Calls Without Modifying Executor | Một ConcreteDecorator cụ thể: `Retry` thêm "thử lại" mà không sửa executor; delegate qua `nxt`; cổng `_retryable()`. |

Mỗi case gồm:
- `README.md` — 6 mục: bối cảnh thật, trích code thật, bảng ánh xạ vai trò, bản rút gọn, cái giá, câu hỏi tự kiểm tra.
- `<name>.py` — bản distill self-contained, chỉ stdlib, có `demo()`, narration tiếng Việt, assert chứng minh bất biến, và đối chứng "khi không dùng pattern".

Danh sách **đầy đủ** mọi occurrence của Decorator trong codebase: xem [`CATALOG.md`](./CATALOG.md).

---

## Chạy nhanh

```bash
python3 "01_middleware_chain_architecture/middleware_chain_architecture.py"
python3 "02_concrete_middleware_decorator/concrete_middleware_decorator.py"
```

Cả hai thoát code 0, không traceback.

---

## Vì sao đây là Decorator (chứ không phải pattern khác)

- **Giữ nguyên interface**: mọi middleware và lõi đều là handler `(request) -> dict`; client (`execute_tool`) không phân biệt được lõi trần với lõi đã bọc → khác Adapter (đổi interface).
- **Thêm hành vi, stack được**: nhiều decorator chồng lên nhau theo thứ tự khai báo → khác Proxy (thường 1 lớp kiểm soát truy cập).
- **Composition over inheritance**: tránh `2^N` lớp tổ hợp — đúng động cơ cốt lõi của Decorator.
- Bộ test (`tests/test_middleware.py`, `tests_audit/test_middleware_exact_semantics.py`) chứng thực semantic Decorator: thứ tự, short-circuit, delegation, posture fail-open vs fail-closed.
