# Case 01 — ToolRequest + ToolPort.execute() + AgentKernel (Invoker)

> *Đóng gói một lời gọi tool thành một object `ToolRequest`, đẩy qua một chokepoint duy nhất; invoker (`AgentKernel`) chỉ biết gọi `.execute(request)` mà KHÔNG biết tool cụ thể làm gì.*

---

## 1. Bối cảnh trong hex_agent

`hex_agent` là một agent có nhiều "tool" (đọc/ghi file, chạy terminal, echo, RAG...). Vấn đề kiến trúc: làm sao cài **logging, retry, policy, budget, scope-check** cho MỌI tool mà **không** phải sửa code rải rác trong từng tool và từng nơi gọi tool?

Lời giải là Command pattern. Một lời gọi tool được **đóng gói thành object** `ToolRequest` (immutable) rồi đi qua **một chokepoint duy nhất** là `AgentKernel.execute_tool()`. Vì action giờ là dữ liệu đi qua một điểm, các cross-cutting concern được gắn dưới dạng **middleware** quanh điểm đó.

File và dòng thật (đã mở kiểm chứng):

- `core/schemas.py:28-34` — `ToolRequest` (frozen dataclass): `name`, `args`, `context`, `request_id` = **ConcreteCommand**.
- `core/ports.py:19-26` — `ToolPort` Protocol: `name` + `execute(request: ToolRequest) -> dict` = **Command interface**.
- `core/kernel.py:106-226` — `AgentKernel.execute_tool()` = **Invoker**: tạo `ToolRequest` (dòng 114), dựng middleware chain (dòng 192-194), gọi handler (dòng 196).
- `core/kernel.py:152-177` — hàm `core(req)`: `resolution.executor.execute(req)` (dòng **155**) là điểm thực thi command qua **Receiver**.
- `core/registry.py:103-112` — `CapabilityRegistry.resolve_tool(name)` ánh xạ tên command → executor (Receiver).
- `features/example_echo.py:16-25` — `EchoTool.execute(request)` = một **ConcreteReceiver**.
- `middleware/retry.py:23-33` — `Retry`: gọi `nxt(request)` lặp lại khi chưa `ok`.
- `middleware/policy.py:9-22` — `PolicyGate`: chặn tool trong deny-list **trước** khi execute.

---

## 2. Trích đoạn code thật

`ToolRequest` — command bất biến (`core/schemas.py:28-34`):

```python
@dataclass(frozen=True)
class ToolRequest:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    context: "ToolCallContext | None" = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
```

Command interface (`core/ports.py:19-26`):

```python
@runtime_checkable
class ToolPort(Protocol):
    """A tool executor. Concrete behavior lives behind this port."""
    name: str
    def execute(self, request: ToolRequest) -> dict[str, Any]:
        ...
```

Invoker tạo command, resolve receiver, execute qua middleware chain (`core/kernel.py:114, 152-155, 192-196`):

```python
request = ToolRequest(name=tool_name, args=copy.deepcopy(args) if args else {}, context=context)
...
def core(req: ToolRequest) -> dict[str, Any]:
    resolution = self.registry.resolve_tool(req.name)
    try:
        result = resolution.executor.execute(req)   # <-- Command execute trên Receiver
    except Exception as exc:  # a tool must never crash the kernel
        result = {"ok": False, "tool": req.name, "error": str(exc), "kernel_error": True}
    ...
handler = core
for mw in reversed(self._middlewares):
    handler = _wrap(mw, handler, on_skip=on_skip)
envelope = handler(request)
```

Một Receiver cụ thể (`features/example_echo.py:16-20`):

```python
class EchoTool:
    name = "echo_tool"
    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {"ok": True, "echo": dict(request.args)}
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Command | Thành phần trong hex_agent | File:line |
|---|---|---|
| **Command (interface)** | `ToolPort` Protocol với `execute()` | `core/ports.py:19-26` |
| **ConcreteCommand** | `ToolRequest` (frozen, đủ context) | `core/schemas.py:28-34` |
| **Receiver** | `EchoTool`, `FsRead`, `Terminal`... (object `.execute()`) | `features/example_echo.py:16-25`, `toolbox/filesystem.py:16-60` |
| **Invoker** | `AgentKernel.execute_tool()` | `core/kernel.py:106-226` |
| **Điểm thực thi** | `resolution.executor.execute(req)` | `core/kernel.py:155` |
| **Ánh xạ tên → Receiver** | `CapabilityRegistry.resolve_tool()` | `core/registry.py:103-112` |
| **Lớp xử lý/queue quanh command** | middleware chain (`Retry`, `PolicyGate`) | `core/kernel.py:192-194`, `middleware/retry.py`, `middleware/policy.py` |

> Lưu ý: hex_agent dùng Command để **decouple + queue/log/retry**, KHÔNG cần `undo()` (tool ở đây có cả side-effect không hoàn tác được). Đây là biến thể "Command như message qua chokepoint", đúng như mục II.3 và II.5 của `14_Command.md`.

---

## 4. Bản rút gọn chạy được

File: [`tool_request_execute_pattern.py`](./tool_request_execute_pattern.py)

**Mô phỏng đúng** các vai trò: `ToolRequest` (ConcreteCommand bất biến, deep-copy args), `ToolPort` (interface), `EchoTool/AddTool/FlakyTool` (Receiver), `CapabilityRegistry.resolve_tool` (tên → Receiver, có `NullTool` fail mềm), `AgentKernel.execute_tool` (Invoker dựng chain bằng `_wrap`), và 3 middleware `LoggingCounter / PolicyGate / Retry`.

Demo chứng minh:
- Command **immutable**: caller đổi `payload` sau khi gửi, command cũ không đổi (deep-copy, distill `kernel.py:113-114`).
- **Retry** lặp `nxt(request)` cho `FlakyTool` mà không sửa code tool.
- **PolicyGate** chặn command trước khi tới Receiver.
- Tool lạ → `NullTool`, kernel **không sập** (distill `NullToolPort`, `registry.py:29-40`).
- Vì có một chokepoint → **log tập trung** đếm đúng 5 command.

**Đã lược bỏ** so với bản thật: `ToolCallContext`/lineage và `allowed_capabilities` scope-check (`kernel.py:115-150`), envelope `CapabilityResult` chuẩn hoá (`schemas.py:63-111`), `EventBus.publish` (chỉ thay bằng list log), cơ chế fail-open + `_LatchedNext` (`kernel.py:24-73`), và `freeze()`. Giữ lại đúng **xương sống Command**: action = object → Invoker → execute() qua Receiver, với middleware quanh chokepoint.

Chạy:

```bash
python3 tool_request_execute_pattern.py
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Gián tiếp tốn chi phí nhận thức.** Một lời gọi đơn giản giờ phải qua `ToolRequest` + registry + chain. Nếu hệ thống chỉ có 1–2 hành động cố định, gọi thẳng `obj.method()` rõ hơn (xem `DirectCaller` trong file).
- **Retry chỉ an toàn khi command idempotent.** Bản thật chặn retry với `kind == "effect" and idempotent is False` (`middleware/retry.py:14-20`) đúng vì "re-running an effect could double-apply it". Nếu bỏ guard này, Command + Retry sẽ nhân đôi side-effect.
- **Command phải đủ context.** Đúng bài học **Apraxia** (`14_Command.md` mục III): nếu `ToolRequest` thiếu thông tin, `execute()` làm sai. Vì vậy nó **frozen** và mang đủ `args`/`context`.
- **Invoker là single point of failure** (bài học **Parkinson** trong `14_Command.md`): mọi command đều qua `execute_tool`; nếu chokepoint hỏng thì cả hệ tê liệt — bản thật bao try/except ở mọi biên (`kernel.py:156-157, 197-203`) để tool/middleware không làm sập kernel.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `ToolRequest` là `frozen=True` và vì sao kernel `deepcopy(args)` trước khi tạo command? (Gợi ý: bài học Apraxia + mục "Command nên IMMUTABLE" trong `14_Command.md`.)
2. Nếu bỏ `CapabilityRegistry` và để Invoker tự `if name == "echo": ... elif ...`, ta mất đặc tính nào của Command pattern? Khi thêm tool mới phải sửa ở đâu?
3. `Retry` gọi lại `nxt(request)` nhiều lần. Vì sao điều này an toàn với `add_tool` nhưng nguy hiểm với một tool "gửi email"? Bản thật xử lý ra sao (`middleware/retry.py:14-20`)?
