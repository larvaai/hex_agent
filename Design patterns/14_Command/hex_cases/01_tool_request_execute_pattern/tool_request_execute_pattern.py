"""
Case 01 — Command pattern: ToolRequest + ToolPort.execute() + AgentKernel (Invoker).

Đây là bản DISTILL TRUNG THỰC, self-contained, CHỈ dùng thư viện chuẩn Python 3.14,
mô phỏng đúng vai trò/cấu trúc của Command pattern trong hex_agent.

Nguồn thật được distill (đã mở file kiểm chứng từng dòng):
  - core/schemas.py:28-34       -> ToolRequest (frozen dataclass) = ConcreteCommand
                                    (name + args + context + request_id)
  - core/ports.py:19-26         -> ToolPort Protocol với execute(request) -> dict
                                    = Command interface
  - core/kernel.py:106-226      -> AgentKernel.execute_tool() = Invoker
  - core/kernel.py:152-177      -> core(req): resolution.executor.execute(req) (dòng 155)
                                    = thực thi Command qua Receiver
  - core/kernel.py:192-194      -> dựng middleware chain: handler = _wrap(mw, handler)
  - core/registry.py:103-112    -> CapabilityRegistry.resolve_tool(name) -> executor
                                    = ánh xạ tên command -> Receiver
  - features/example_echo.py:16-25 -> EchoTool.execute(request) = ConcreteReceiver
  - middleware/retry.py:23-33   -> Retry: gọi nxt(request) lặp lại = lớp xử lý/queue
  - middleware/policy.py:9-22   -> PolicyGate: chặn trước khi execute = gate trong chain

Ý tưởng cốt lõi của Command ở đây:
  * Một "lời gọi tool" được ĐÓNG GÓI thành object ToolRequest (immutable).
  * Invoker (kernel) KHÔNG biết tool cụ thể làm gì — chỉ biết gọi .execute(request).
  * Vì action là object đi qua một chokepoint duy nhất, ta gắn được logging,
    đếm, retry, policy... mà KHÔNG đụng vào code của từng tool.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# 1. ConcreteCommand — distill core/schemas.py:28-34 (ToolRequest)
#    Immutable: đóng gói đủ ngữ cảnh để execute độc lập (đúng bài học Apraxia:
#    command thiếu context sẽ execute sai).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolRequest:
    """ConcreteCommand: một hành động đã được đóng gói thành dữ liệu."""

    name: str
    args: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)


# ---------------------------------------------------------------------------
# 2. Command interface — distill core/ports.py:19-26 (ToolPort Protocol)
#    Mọi Receiver phải có .name và .execute(request) -> dict.
# ---------------------------------------------------------------------------
@runtime_checkable
class ToolPort(Protocol):
    name: str

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        ...


# ---------------------------------------------------------------------------
# 3. Concrete Receivers — distill features/example_echo.py:16-25 + toolbox/*
#    Mỗi tool là một object thực sự "làm việc". Invoker không biết chi tiết này.
# ---------------------------------------------------------------------------
class EchoTool:
    """Receiver: trả lại args (distill EchoTool.execute, features/example_echo.py:19-20)."""

    name = "echo_tool"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {"ok": True, "echo": dict(request.args)}


class AddTool:
    """Receiver: cộng hai số. Minh hoạ decoupling — kernel chỉ gọi execute()."""

    name = "add_tool"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        a = request.args.get("a", 0)
        b = request.args.get("b", 0)
        return {"ok": True, "sum": a + b}


class FlakyTool:
    """Receiver hay hỏng ở những lần đầu — để minh hoạ Retry middleware (idempotent)."""

    name = "flaky_tool"

    def __init__(self, fail_times: int) -> None:
        self._fail_times = fail_times
        self.calls = 0

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        self.calls += 1
        if self.calls <= self._fail_times:
            return {"ok": False, "error": f"transient failure #{self.calls}"}
        return {"ok": True, "value": "finally-ok", "attempts": self.calls}


# ---------------------------------------------------------------------------
# 4. Registry — distill core/registry.py:103-112 (resolve_tool)
#    Ánh xạ tên command -> Receiver. Nếu thiếu thì trả NullTool (fail mềm,
#    distill NullToolPort, registry.py:29-40) để Invoker không sập.
# ---------------------------------------------------------------------------
class NullTool:
    name = "null_tool"

    def __init__(self, requested: str) -> None:
        self._requested = requested

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {
            "ok": False,
            "missing_capability": True,
            "error": f"No tool registered for '{self._requested}'.",
        }


class CapabilityRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolPort] = {}

    def register(self, executor: ToolPort) -> None:
        self._tools[executor.name] = executor

    def resolve_tool(self, name: str) -> ToolPort:
        if name in self._tools:
            return self._tools[name]
        return NullTool(name)


# ---------------------------------------------------------------------------
# 5. Middleware — distill core/kernel.py:49-73, 192-194 + middleware/retry.py +
#    middleware/policy.py. Mỗi middleware nhận (request, nxt) và quyết định có
#    gọi nxt(request) hay không. Vì command là object đi qua một chokepoint,
#    ta cài cross-cutting concern ở đây mà KHÔNG sửa tool.
# ---------------------------------------------------------------------------
Handler = Callable[[ToolRequest], dict[str, Any]]
Middleware = Callable[[ToolRequest, Handler], dict[str, Any]]


class LoggingCounter:
    """Đếm + log mỗi lần một command đi qua. Distill ý 'gắn logging quanh chokepoint'."""

    name = "logging_counter"

    def __init__(self) -> None:
        self.log: list[tuple[str, str]] = []  # (phase, tool_name)
        self.count = 0

    def __call__(self, request: ToolRequest, nxt: Handler) -> dict[str, Any]:
        self.count += 1
        self.log.append(("before", request.name))
        env = nxt(request)
        self.log.append(("after", request.name))
        return env


class PolicyGate:
    """Distill middleware/policy.py:9-22 — chặn tool trong deny-list TRƯỚC khi execute."""

    name = "policy_gate"

    def __init__(self, deny: set[str]) -> None:
        self.deny = set(deny)

    def __call__(self, request: ToolRequest, nxt: Handler) -> dict[str, Any]:
        if request.name in self.deny:
            return {"ok": False, "error": f"Blocked by policy: {request.name}",
                    "metadata": {"policy_block": True}}
        return nxt(request)


class Retry:
    """Distill middleware/retry.py:23-33 — gọi lại nxt(request) khi kết quả không ok.

    request IMMUTABLE nên gọi lại nhiều lần là an toàn (không tích luỹ state bẩn).
    """

    name = "retry"

    def __init__(self, attempts: int = 3) -> None:
        self.attempts = max(1, attempts)

    def __call__(self, request: ToolRequest, nxt: Handler) -> dict[str, Any]:
        env = nxt(request)
        tries = 1
        while isinstance(env, dict) and not env.get("ok") and tries < self.attempts:
            if env.get("metadata", {}).get("policy_block"):
                break  # không retry policy block (đúng _retryable, retry.py:14-20)
            env = nxt(request)
            tries += 1
        return env


# ---------------------------------------------------------------------------
# 6. Invoker — distill core/kernel.py:106-226 (AgentKernel.execute_tool)
#    Tạo ToolRequest (Command), dựng middleware chain quanh lõi 'core' (dòng
#    152-177), trong đó resolution.executor.execute(req) (dòng 155) là điểm
#    thực thi command qua Receiver.
# ---------------------------------------------------------------------------
@dataclass
class AgentKernel:
    registry: CapabilityRegistry
    _middlewares: list[Middleware] = field(default_factory=list)

    def use(self, middleware: Middleware) -> None:
        """Đăng ký middleware. Thứ tự đăng ký = ngoài -> trong (kernel.py:100-104)."""
        self._middlewares.append(middleware)

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        # Deep-copy args: tool KHÔNG được mutate object của caller qua request.args
        # (distill kernel.py:113-114).
        request = ToolRequest(name=tool_name, args=copy.deepcopy(args) if args else {})

        # core = lõi thực thi command (distill kernel.py:152-177).
        def core(req: ToolRequest) -> dict[str, Any]:
            executor = self.registry.resolve_tool(req.name)  # registry.py:103-112
            try:
                result = executor.execute(req)               # kernel.py:155 — Command execute
            except Exception as exc:  # một tool KHÔNG bao giờ được làm sập kernel
                result = {"ok": False, "error": str(exc), "kernel_error": True}
            if not isinstance(result, dict):
                result = {"ok": False, "error": "Tool returned non-dict.", "kernel_error": True}
            # gắn metadata executor (distill kernel.py:165-177)
            meta = dict(result.get("metadata") or {})
            meta.setdefault("executor", getattr(executor, "name", type(executor).__name__))
            meta.setdefault("request_id", req.request_id)
            result["metadata"] = meta
            return result

        # Dựng chain: bọc từ trong ra ngoài (distill kernel.py:192-194).
        handler: Handler = core
        for mw in reversed(self._middlewares):
            handler = _wrap(mw, handler)

        try:
            envelope = handler(request)
        except Exception as exc:  # middleware KHÔNG được làm sập biên kernel
            envelope = {"ok": False, "error": str(exc), "metadata": {"kernel_error": True}}
        return envelope


def _wrap(middleware: Middleware, nxt: Handler) -> Handler:
    """Bind 1 middleware quanh handler kế tiếp (tránh late-binding closure bug,
    distill kernel.py:49-62)."""

    def handler(request: ToolRequest) -> dict[str, Any]:
        return middleware(request, nxt)

    return handler


# ---------------------------------------------------------------------------
# Đối chứng: KHÔNG dùng Command pattern — client gọi thẳng tool.
# ---------------------------------------------------------------------------
class DirectCaller:
    """Anti-pattern (như 14_Command.md mục III.A): client gọi trực tiếp tool.

    Hậu quả: không có chokepoint -> muốn thêm log/retry/policy phải sửa rải rác
    ở MỌI call-site, và mỗi tool tự lo. Không thể log/đếm/replay tập trung.
    """

    def __init__(self) -> None:
        self.echo = EchoTool()
        self.add = AddTool()

    def run_echo(self, **args: Any) -> dict[str, Any]:
        # phải tự tay nhớ gọi đúng object, tự build request, tự lo lỗi...
        return self.echo.execute(ToolRequest(name="echo_tool", args=args))


# ---------------------------------------------------------------------------
# demo()
# ---------------------------------------------------------------------------
def demo() -> None:
    print("=" * 72)
    print("CASE 01 — Command: ToolRequest + execute() + Kernel(Invoker)")
    print("=" * 72)

    # --- Dựng registry + đăng ký các Receiver ---
    registry = CapabilityRegistry()
    registry.register(EchoTool())
    registry.register(AddTool())
    flaky = FlakyTool(fail_times=2)  # hỏng 2 lần đầu, lần 3 ok
    registry.register(flaky)

    kernel = AgentKernel(registry=registry)

    # --- Gắn middleware QUANH chokepoint (không đụng tool nào) ---
    logger = LoggingCounter()
    kernel.use(logger)                 # ngoài cùng
    kernel.use(PolicyGate(deny={"danger_tool"}))
    kernel.use(Retry(attempts=3))      # trong cùng (sát core)

    print("\n[Bước 1] Gửi command 'echo_tool' (args bị deep-copy, immutable).")
    payload = {"x": 1}
    env = kernel.execute_tool("echo_tool", payload)
    print("   kết quả:", env["echo"], "| executor:", env["metadata"]["executor"])
    payload["x"] = 999  # thử mutate object gốc của caller
    assert env["echo"] == {"x": 1}, "deep-copy bảo vệ command khỏi mutate ngoài"
    print("   -> sau khi caller đổi payload['x']=999, command CŨ vẫn giữ {'x': 1}.")

    print("\n[Bước 2] Gửi command 'add_tool' — kernel KHÔNG biết nó cộng số.")
    env = kernel.execute_tool("add_tool", {"a": 2, "b": 40})
    print("   2 + 40 =", env["sum"])
    assert env["sum"] == 42

    print("\n[Bước 3] Command tới tool hỏng tạm thời -> Retry tự gọi lại nxt(request).")
    env = kernel.execute_tool("flaky_tool", {})
    print("   kết quả:", env.get("value"), "| số lần thử:", env.get("attempts"))
    assert env["ok"] is True and env["attempts"] == 3, "Retry phải lặp tới khi ok"
    print("   -> Retry hoạt động mà KHÔNG cần sửa code của FlakyTool.")

    print("\n[Bước 4] Command bị PolicyGate chặn TRƯỚC khi tới Receiver.")
    env = kernel.execute_tool("danger_tool", {"rm": "-rf"})
    print("   ok =", env["ok"], "| error =", env["error"])
    assert env["ok"] is False and env["metadata"]["policy_block"] is True

    print("\n[Bước 5] Command tới tool KHÔNG đăng ký -> NullTool, kernel không sập.")
    env = kernel.execute_tool("khong_ton_tai", {})
    print("   ok =", env["ok"], "| error =", env["error"])
    assert env["ok"] is False and env["metadata"]["executor"] == "null_tool"

    print("\n[Bước 6] Vì mọi action là command qua 1 chokepoint -> log tập trung:")
    for phase, name in logger.log:
        print(f"     {phase:<6} {name}")
    print("   tổng số command đi qua chokepoint:", logger.count)
    assert logger.count == 5, "đúng 5 command đã đi qua Invoker"

    # --- Đối chứng: không dùng pattern ---
    print("\n[Đối chứng] DirectCaller gọi thẳng tool, KHÔNG có chokepoint:")
    direct = DirectCaller()
    direct.run_echo(x=7)
    print("   -> chạy được, nhưng KHÔNG có log/retry/policy tập trung.")
    print("      Muốn thêm những thứ đó phải sửa MỌI nơi gọi tool (rải rác).")
    print("      Đây chính là anti-pattern ở 14_Command.md mục III.A.")

    print("\nTẤT CẢ assert PASS. Command pattern hoạt động đúng.")


if __name__ == "__main__":
    demo()
