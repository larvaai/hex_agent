# Đề xuất triển khai: 3 seam mở rộng cho `core_agent`

Mở rộng kernel bằng **seam (điểm cắm)** thay vì thêm method, theo đúng kiến trúc microkernel/hexagonal hiện tại.

1. **Mọi thứ là capability** — đưa lệnh gọi LLM thành một tool (`execute_tool("llm.chat", ...)`).
2. **Middleware/hook quanh `execute_tool`** — chuỗi pre/post (policy → budget → condense → retry → log).
3. **`complete_task()` / `fail_task()`** — đóng vòng đời task cho cân xứng với `accept_task()`.

---

## 0. Nguyên tắc giữ nguyên (nhắc lại từ các đề xuất trước)

Mọi thiết kế dưới đây bám sát những gì đã thống nhất:

- **Kernel mỏng.** Không nhồi vòng lặp agent vào kernel; kernel chỉ là *substrate* (state + events + chokepoint).
- **`execute_tool` là cửa duy nhất.** Mọi tool — kể cả LLM — đi qua đây, nên đây là chỗ đặt safety/observability/budget.
- **Vòng lặp nằm NGOÀI kernel.** Một tầng `orchestrator/` gọi `accept_task` 1 lần → `execute_tool` N lần → `complete_task` 1 lần (tương ứng E05 "single-agent graph").
- **Tái dùng `discipline/`** (`Budget`, `condense`, `check_finish`, `parse_action`) — không nhân bản logic.
- **`finish_gate` do orchestrator áp**, không nhúng vào kernel (giữ kernel không dính policy).
- **Mặc định tương thích ngược.** Không bật gì thì hành vi y hệt hiện tại → 24/24 test vẫn xanh.

---

## Seam 1 — Mọi thứ là capability (LLM là một tool)

### Mục tiêu
Lệnh gọi LLM được bọc **y hệt** tool thường: cùng envelope `CapabilityResult`, cùng event `tool.requested/completed/failed`, cùng middleware (safety/budget/condense/log) — mà bề mặt kernel **không lớn thêm một method nào**.

### Code — `features/llm_chat.py` (feature mới, theo đúng plugin pattern của `example_echo`)

```python
"""LLM call exposed as a capability so it flows through the same chokepoint/middleware. Epic E03/E05."""
from __future__ import annotations
from typing import Any

from core.kernel import AgentKernel
from core.schemas import FeatureDescriptor, ToolRequest
from llm.adapter import call_llm

FEATURE = FeatureDescriptor(
    name="llm",
    capabilities=("llm.chat",),
    description="LLM chat exposed as a tool capability.",
)

class LLMChatTool:
    name = "llm_chat_tool"

    def __init__(self, client: Any = None) -> None:
        self._client = client          # injectable cho test, giống llm/adapter.py

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        args = request.args
        content = call_llm(
            args.get("messages", []),
            model=args.get("model"),
            temperature=args.get("temperature", 0.2),
            json_mode=args.get("json_mode", True),
            client=self._client,
        )
        return {"ok": True, "content": content}   # kernel sẽ bọc thành CapabilityResult

def install(kernel: AgentKernel, *, client: Any = None) -> None:
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tools(FEATURE.capabilities, LLMChatTool(client=client), feature_name=FEATURE.name)
```

### `config/features.yaml`

```yaml
features:
  example_echo:
    enabled: true
    module: features.example_echo
  llm_chat:
    enabled: true
    module: features.llm_chat
```

> Đăng ký tool là **offline và rẻ** — chỉ thực sự gọi mạng khi ai đó `execute_tool("llm.chat", ...)` mà không inject client. Smoke/test offline vẫn an toàn vì chúng không gọi `llm.chat`.

### Đếm metric `llm_calls` (đã có sẵn chỗ trong `_METRICS`)
Sửa nhẹ `observability/event_log.py` → `attach_to_bus`:

```python
def sink(topic: str, payload: dict[str, Any]) -> None:
    logger.emit("KernelEvent", topic=topic, **payload)
    tool = payload.get("tool", "")
    if topic in ("tool.completed", "tool.failed"):
        logger.count("tool_calls")
        if tool.startswith("llm."):
            logger.count("llm_calls")     # <-- mới
    if topic == "tool.failed":
        logger.count("tool_failures")
```

### Lợi ích & đánh đổi
- **Lợi ích:** safety/policy soi được cả LLM call; budget đếm được; observability log đồng nhất; condense áp được cho output tool — tất cả không thêm method kernel.
- **Lưu ý:** LLM trả về *text*, việc `parse_action` vẫn nằm ở orchestrator (đúng chỗ, không lọt vào kernel). `Budget.tool_key` băm cả `args` (gồm `messages`) nên mỗi turn khác nhau → không bị "same-tool" chặn nhầm.

---

## Seam 2 — Middleware/hook quanh `execute_tool`

### Mục tiêu
Thêm **một** seam mở rộng (đăng ký middleware) thay vì mười method. Cross-cutting concern (policy, budget, condense, retry, log) thành các lớp **tháo lắp được**, bọc quanh chokepoint duy nhất.

> Cơ chế chuỗi (onion) bên dưới đã được prototype và verify: đúng thứ tự ngoài→trong, short-circuit hoạt động, và helper `_wrap` tránh bug late-binding closure trong vòng lặp.

### Protocol — `core/middleware.py` (kernel chỉ biết *seam*, không biết *policy*)

```python
"""ToolMiddleware protocol — pre/post hook quanh execute_tool. Epic E01/E06."""
from __future__ import annotations
from typing import Any, Callable, Protocol
from core.schemas import ToolRequest

ToolHandler = Callable[[ToolRequest], dict[str, Any]]

class ToolMiddleware(Protocol):
    def __call__(self, request: ToolRequest, nxt: ToolHandler) -> dict[str, Any]: ...
```

### Sửa `core/kernel.py` — thêm 1 field + 1 method, và bọc chuỗi quanh "core"

```python
def _wrap(mw, nxt):
    """Bind tránh late-binding closure bug."""
    def handler(req: ToolRequest) -> dict[str, Any]:
        return mw(req, nxt)
    return handler

@dataclass
class AgentKernel:
    registry: CapabilityRegistry
    events: EventBus
    state: StateStore
    config: dict[str, Any] = field(default_factory=dict)
    _middlewares: list = field(default_factory=list)        # MỚI — mặc định rỗng

    def use(self, middleware) -> None:                       # MỚI — 1 seam, không phải 10 method
        """Đăng ký middleware. Thứ tự đăng ký = NGOÀI -> TRONG."""
        self._middlewares.append(middleware)

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        request = ToolRequest(name=tool_name, args=args or {})
        self.events.publish(
            "tool.requested",
            {"tool": request.name, "request_id": request.request_id, "args": request.args},
        )

        def core(req: ToolRequest) -> dict[str, Any]:        # phần lõi hiện tại, giữ nguyên
            resolution = self.registry.resolve_tool(req.name)
            try:
                result = resolution.executor.execute(req)
            except Exception as exc:
                result = {"ok": False, "tool": req.name, "error": str(exc), "kernel_error": True}
            if not isinstance(result, dict):
                result = {"ok": False, "tool": req.name,
                          "error": f"Tool returned {type(result).__name__}, expected dict.",
                          "kernel_error": True}
            return CapabilityResult.from_raw(
                capability=req.name, feature=resolution.feature, result=result,
                metadata={"request_id": req.request_id,
                          "executor": getattr(resolution.executor, "name", resolution.executor.__class__.__name__)},
            ).as_dict()

        handler = core
        for mw in reversed(self._middlewares):               # bọc chuỗi
            handler = _wrap(mw, handler)
        envelope = handler(request)

        self.events.publish(
            "tool.completed" if envelope.get("ok") else "tool.failed",
            {"tool": request.name, "request_id": request.request_id,
             "ok": bool(envelope.get("ok")), "error": envelope.get("error")},
        )
        return envelope
```

**Tương thích ngược:** `_middlewares` mặc định rỗng → `handler = core` → `execute_tool` chạy *y hệt* hiện tại. Không bật gì thì không đổi gì.

### Middleware mẫu — `middleware/` (NGOÀI kernel, tái dùng `discipline/`)

```python
# middleware/policy.py — "safety = one chokepoint"
from core.schemas import ToolRequest

class PolicyGate:
    def __init__(self, *, deny: set[str] | None = None, on_block=None) -> None:
        self.deny = deny or set()
        self.on_block = on_block            # ví dụ: lambda r: logger.count("policy_blocks")
    def __call__(self, request: ToolRequest, nxt):
        if request.name in self.deny:
            if self.on_block: self.on_block(request)
            return {"ok": False, "capability": request.name, "feature": None,
                    "data": {}, "error": f"Blocked by policy: {request.name}",
                    "metadata": {"policy_block": True}}
        return nxt(request)                  # cho qua
```

```python
# middleware/budget.py — tái dùng discipline.Budget
from core.schemas import ToolRequest
from discipline import Budget

class BudgetGuard:
    def __init__(self, budget: Budget, *, on_block=None) -> None:
        self.budget = budget; self.on_block = on_block
    def __call__(self, request: ToolRequest, nxt):
        key = Budget.tool_key(request.name, request.args)
        self.budget.record_tool_call(key)
        if self.budget.same_tool_exceeded(key):
            if self.on_block: self.on_block(request)
            return {"ok": False, "capability": request.name, "feature": None,
                    "data": {}, "error": "Same-tool budget exceeded.",
                    "metadata": {"budget_block": True}}
        return nxt(request)
```

```python
# middleware/condense.py — tái dùng discipline.condense
from core.schemas import ToolRequest
from discipline import condense

class CondenseResult:
    def __init__(self, *, max_chars=2000, max_list=10, on_condense=None) -> None:
        self.max_chars = max_chars; self.max_list = max_list; self.on_condense = on_condense
    def __call__(self, request: ToolRequest, nxt):
        env = nxt(request)
        # QUAN TRỌNG: bỏ qua llm.* — output của model phải tới parser nguyên vẹn,
        # nếu condense cắt chuỗi JSON action sẽ làm parse_action gãy.
        if request.name.startswith("llm."):
            return env
        env["data"] = condense(env.get("data", {}), max_chars=self.max_chars, max_list=self.max_list)
        if self.on_condense: self.on_condense(request)   # logger.count("condensed")
        return env
```

```python
# middleware/retry.py — retry lỗi tool tạm thời (không retry khi bị policy chặn)
from core.schemas import ToolRequest

class Retry:
    def __init__(self, *, attempts: int = 2) -> None:
        self.attempts = attempts
    def __call__(self, request: ToolRequest, nxt):
        env = nxt(request); tries = 1
        while (not env.get("ok") and tries < self.attempts
               and not env.get("metadata", {}).get("policy_block")):
            env = nxt(request); tries += 1
        return env
```

```python
# middleware/logging.py — đo thời gian, ngoài cùng
import time
from core.schemas import ToolRequest

class TimingLog:
    def __init__(self, sink=None) -> None:
        self.sink = sink                    # ví dụ: lambda info: logger.emit("ToolTiming", **info)
    def __call__(self, request: ToolRequest, nxt):
        t0 = time.perf_counter()
        env = nxt(request)
        if self.sink:
            self.sink({"tool": request.name, "ok": env.get("ok"),
                       "ms": round((time.perf_counter() - t0) * 1000, 2)})
        return env
```

### Đăng ký (thứ tự = ngoài → trong)

```python
kernel.use(TimingLog(sink=...))                                              # ngoài cùng: đo cả retry
kernel.use(PolicyGate(deny={"shell.rm"}, on_block=lambda r: logger.count("policy_blocks")))
kernel.use(BudgetGuard(budget))                                              # dùng chung Budget với orchestrator
kernel.use(Retry(attempts=2))                                                # bao quanh core
kernel.use(CondenseResult(on_condense=lambda r: logger.count("condensed"))) # trong cùng: gọn data
```

> Thứ tự đề xuất: **log → policy → budget → retry → condense**. Log ngoài cùng để đo tổng (gồm retry); policy/budget chặn sớm trước khi tốn công; retry bao quanh lõi; condense gần lõi để gọn từng kết quả. Thứ tự là **cấu hình được** — đó chính là lợi ích của seam.

---

## Seam 3 — `complete_task()` / `fail_task()`

### Mục tiêu
Đối xứng với `accept_task()`: đóng task, lưu kết quả, bắn event. Thuộc về kernel vì đây là **state + lifecycle** mà kernel sở hữu.

### Code — thêm vào `core/kernel.py`

```python
def complete_task(self, result: Any = None, *, status: str = "completed") -> dict[str, Any]:
    task = self.state.get("current_task")
    task_id = getattr(task, "task_id", None)
    outcome = {"task_id": task_id, "status": status, "result": result}
    self.state.set("last_result", outcome)
    self.state.set("current_task", None)
    self.events.publish(
        "task.completed" if status == "completed" else "task.failed",
        {"task_id": task_id, "status": status},
    )
    return outcome

def fail_task(self, reason: str, **extra: Any) -> dict[str, Any]:
    return self.complete_task({"reason": reason, **extra}, status="failed")
```

> **Không** gọi `check_finish` trong đây. Orchestrator chạy `check_finish` *trước*, rồi mới quyết định gọi `complete_task`. Kernel vẫn không dính policy (nhất quán với đề xuất trước).

---

## Ráp 3 seam lại — orchestrator `run()` (NGOÀI kernel)

Đây là "bộ não chạy vòng" (E05), nơi caller chỉ cần gọi `run(...)` và **không bao giờ chạm** `accept_task`/`execute_tool` (giải quyết đúng mong muốn "bên ngoài không cần quan tâm `accept_task`").

```python
# orchestrator/loop.py — KHÔNG nằm trong kernel
import json
from core.kernel import AgentKernel
from discipline import Budget, JsonGateError, build_retry_message, check_finish, parse_action

SYSTEM = "You are an agent. Reply with exactly ONE JSON object: {\"action\": ...}."

def run(kernel: AgentKernel, user_request: str, *, budget: Budget | None = None) -> dict:
    kernel.accept_task(user_request)                              # 1 lần
    budget = budget or Budget()
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_request}]
    while True:
        if budget.step_exceeded():
            return kernel.fail_task("step budget exceeded")       # seam 3
        budget.record_step()

        # seam 1: LLM là capability -> seam 2: đi qua chokepoint + middleware
        resp = kernel.execute_tool("llm.chat", {"messages": messages, "json_mode": True})
        raw = resp["data"].get("content", "")

        try:
            action = parse_action(raw)                            # discipline
        except JsonGateError as e:
            budget.record_parse_error()                           # parse-error KHÔNG tốn step
            if budget.parse_exceeded():
                return kernel.fail_task("too many parse errors")
            messages.append({"role": "user", "content": build_retry_message(e)})
            continue

        if action["action"] == "final":
            gate = check_finish(kernel.state.as_dict(), action.get("finish_reason"))
            if not gate["allowed"]:                                # finish_gate áp Ở ĐÂY
                messages.append({"role": "user", "content": gate["reason"]})
                continue
            return kernel.complete_task(action.get("message"))     # seam 3

        # tool action -> cùng một chokepoint (seam 2 bọc nó)
        result = kernel.execute_tool(action["tool"], action.get("args", {}))
        messages.append({"role": "user", "content": json.dumps(result, ensure_ascii=False)})
```

> **Budget dùng chung:** cùng một `Budget` truyền cho `BudgetGuard` (chặn lặp tool ở chokepoint) và dùng trong `run()` (đếm steps/parse). Một nguồn sự thật, không tách đôi.

---

## Test & tương thích ngược

**Mặc định không đổi hành vi** → 24/24 test hiện tại vẫn xanh:
- `_middlewares = []` → `execute_tool` chạy y hệt.
- `complete_task`/`fail_task` là *thêm mới*, không đụng path cũ.
- `llm_chat` chỉ được đăng ký nếu config bật (hoặc test tự đăng ký), và chỉ chạm mạng khi bị gọi.

**Test mới đề xuất:**
- `test_middleware_order_and_short_circuit` — chuỗi gọi đúng thứ tự; policy chặn thì lõi không chạy (đã prototype).
- `test_policy_block_emits_tool_failed` — envelope `ok=False`, có `policy_block`, kernel bắn `tool.failed`.
- `test_condense_middleware_shrinks_data` — data tool lớn bị cắt; `llm.*` được bỏ qua.
- `test_llm_chat_capability` — dùng `_FakeClient` (tái dùng từ `tests/test_llm_adapter.py`), assert envelope `ok=True` + `data.content`.
- `test_complete_task_clears_and_emits` — `current_task` về `None`, `last_result` được set, bắn `task.completed`.

---

## Thứ tự triển khai (checklist)

1. **Seam 3 — `complete_task`/`fail_task`.** Nhỏ nhất, độc lập, không rủi ro. Cập nhật `run_smoke.py` gọi `complete_task` cho `accept_task` cân xứng.
2. **Seam 1 — `features/llm_chat.py` + metric `llm_calls`.** Độc lập, không đụng kernel.
3. **Seam 2 — `core/middleware.py` + sửa `execute_tool` + package `middleware/`.** Đụng chokepoint nên làm sau; mặc định rỗng nên an toàn.
4. **`orchestrator/loop.py` — `run()`.** Ráp cả 3 seam → đây là bước "có agent thật" (E05).

**Tóm tắt:** cả ba đều mở rộng hệ thống mà **không phình bề mặt kernel** — kernel chỉ thêm đúng 1 field + 1 method (`use`) cho seam middleware, và 2 method lifecycle (`complete_task`/`fail_task`). Mọi hành vi (LLM, policy, budget, condense, retry, log, vòng lặp) sống ở adapter/middleware/orchestrator tháo lắp được — đúng tinh thần microkernel.
