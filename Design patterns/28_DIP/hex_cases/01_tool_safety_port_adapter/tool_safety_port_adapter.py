"""
Case 01 — DIP: SafeToolPort — lớp chính sách an toàn bọc quanh ToolPort
==========================================================================

Bản DISTILL TRUNG THỰC từ hex_agent:

  - core/ports.py:19-26
        @runtime_checkable
        class ToolPort(Protocol):  # name + execute()  -> ABSTRACTION do cấp cao (core) sở hữu
  - safety/policy.py:105-124
        class SafeToolPort:        # adapter bọc 1 tool, kiểm tra policy rồi mới delegate
  - toolbox/feature.py:67-77
        def install(kernel):       # composition root: bọc mỗi tool trong SafeToolPort
                                   # rồi register vào kernel.registry (cấp cao KHÔNG biết lớp tool cụ thể)
  - core/registry.py:29-40
        class NullToolPort:        # fallback khi không tìm thấy tool (graceful degradation)

Ý tưởng DIP ở đây:
  * core/ (cấp cao) ĐỊNH NGHĨA cái nó cần: "thực thi 1 tool có name + execute()".
  * toolbox/ (cấp thấp) cung cấp các tool cụ thể (FsRead, Terminal, ...).
  * SafeToolPort là adapter: cũng tuân ToolPort, nhưng chèn policy gate trước khi delegate.
  * Kernel chỉ gọi qua ToolPort — KHÔNG import lớp tool cụ thể.
  * Bằng chứng đảo chiều: source code core/ KHÔNG import toolbox/.

Bản rút gọn này thay hạ tầng thật (filesystem sandbox, terminal subprocess, registry
đầy đủ) bằng các fake tối thiểu chỉ dùng thư viện chuẩn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ───────────────────────────────────────────────────────────────────────────
# 1) ABSTRACTION — sống ở "cấp cao" (mô phỏng core/ports.py:19-26)
#    Cấp cao tuyên bố HỢP ĐỒNG: bất kỳ thứ gì có .name + .execute() đều là tool.
# ───────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ToolRequest:
    """Yêu cầu gọi tool (mô phỏng core.schemas.ToolRequest)."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ToolPort(Protocol):
    """A tool executor. Concrete behavior lives behind this port. (core/ports.py:20-26)"""
    name: str

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        ...


# ───────────────────────────────────────────────────────────────────────────
# 2) CÁC TOOL CỤ THỂ — "cấp thấp" (mô phỏng toolbox/filesystem.py, toolbox/terminal.py)
#    Chúng chỉ cần implement ToolPort về mặt CẤU TRÚC (structural typing) — không kế thừa.
# ───────────────────────────────────────────────────────────────────────────
class FsRead:
    """Tool đọc file (fake): trả nội dung từ một filesystem trong bộ nhớ. Idempotent, low risk."""
    name = "fs_read"

    def __init__(self, files: dict[str, str]) -> None:
        self._files = files

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        path = request.args.get("path", "")
        if path not in self._files:
            return {"ok": False, "tool": self.name, "error": f"no such file: {path}"}
        return {"ok": True, "tool": self.name, "content": self._files[path]}


class FakeEcho:
    """Tool 'terminal' giả: vọng lại argv. Đánh dấu high risk để policy chặn được."""
    name = "terminal_run"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        argv = request.args.get("argv", [])
        return {"ok": True, "tool": self.name, "stdout": " ".join(str(a) for a in argv)}


# ───────────────────────────────────────────────────────────────────────────
# 3) POLICY + ADAPTER — SafeToolPort (mô phỏng safety/policy.py:105-124)
#    SafeToolPort CŨNG tuân ToolPort, nên nó "trong suốt" với kernel.
# ───────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""
    code: str = ""
    risk: str = "low"


class ToolPolicy:
    """Chốt chặn an toàn rút gọn: chặn lệnh terminal nguy hiểm (mô phỏng safety/policy.py)."""
    _DANGEROUS = ("rm -rf", "mkfs", ":(){", "shutdown")

    def check(self, tool_name: str, args: dict[str, Any]) -> PolicyDecision:
        if tool_name == "terminal_run":
            cmd = " ".join(str(a) for a in args.get("argv", []))
            for bad in self._DANGEROUS:
                if bad in cmd:
                    return PolicyDecision(False, f"dangerous command blocked: {bad!r}",
                                          "dangerous_terminal", "high")
        return PolicyDecision(True)


class SafeToolPort:
    """Wrap a tool executor; run the policy chokepoint before delegating. (safety/policy.py:105-124)

    Đây là ADAPTER: nó implement ToolPort (name + execute) nhưng KHÔNG tự làm việc — nó
    delegate cho ``inner`` sau khi policy cho phép. Kernel không biết ``inner`` là lớp gì.
    """

    def __init__(self, name: str, inner: ToolPort, policy: ToolPolicy | None = None) -> None:
        self.name = name
        self._inner = inner
        self._policy = policy or ToolPolicy()

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        decision = self._policy.check(request.name, request.args)
        if not decision.allowed:
            return {
                "ok": False,
                "tool": request.name,
                "policy_blocked": True,
                "policy_code": decision.code,
                "error": decision.reason,
                "metadata": {"risk": decision.risk},
            }
        return self._inner.execute(request)


# ───────────────────────────────────────────────────────────────────────────
# 4) REGISTRY + KERNEL — "cấp cao" tiêu thụ (mô phỏng core/registry.py + core/kernel.py)
#    Kernel chỉ biết ToolPort. Khi thiếu tool, rơi về NullToolPort (graceful degradation).
# ───────────────────────────────────────────────────────────────────────────
class NullToolPort:
    """Keeps the kernel alive when a tool is missing. (core/registry.py:29-40)"""
    name = "null_tool"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {
            "ok": False,
            "tool": request.name,
            "missing_capability": True,
            "error": f"No tool capability is registered for '{request.name}'.",
        }


class CapabilityRegistry:
    """Đăng ký các ToolPort theo tên; trả NullToolPort khi không có (core/registry.py:43-...)."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolPort] = {}
        self._null = NullToolPort()

    def register_tool(self, name: str, tool: ToolPort) -> None:
        # CHÚ Ý: registry nhận ToolPort, không quan tâm lớp cụ thể.
        self._tools[name] = tool

    def resolve(self, name: str) -> ToolPort:
        return self._tools.get(name, self._null)


class AgentKernel:
    """Cấp cao: chỉ gọi qua ToolPort.execute(), KHÔNG import FsRead/FakeEcho/SafeToolPort."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def execute_tool(self, name: str, **args: Any) -> dict[str, Any]:
        port = self.registry.resolve(name)        # type là ToolPort (abstraction)
        return port.execute(ToolRequest(name, args))


# ───────────────────────────────────────────────────────────────────────────
# 5) COMPOSITION ROOT — điểm DUY NHẤT biết cả 2 tầng (mô phỏng toolbox/feature.py:67-77)
# ───────────────────────────────────────────────────────────────────────────
def install(kernel: AgentKernel, tools: list[ToolPort], policy: ToolPolicy) -> None:
    """Với mỗi tool cụ thể: BỌC trong SafeToolPort rồi register. Giống install() trong feature.py."""
    for tool in tools:
        kernel.registry.register_tool(tool.name, SafeToolPort(tool.name, tool, policy))


# ───────────────────────────────────────────────────────────────────────────
# DEMO
# ───────────────────────────────────────────────────────────────────────────
def demo() -> None:
    print("=" * 72)
    print("CASE 01 — SafeToolPort bọc quanh ToolPort (DIP)")
    print("=" * 72)

    # --- Composition root: wiring concrete -> abstraction ---
    print("\n[1] Composition root: bọc mỗi tool cụ thể trong SafeToolPort rồi register.")
    kernel = AgentKernel(CapabilityRegistry())
    policy = ToolPolicy()
    concrete_tools = [
        FsRead(files={"README.md": "# Hex Agent\nDIP demo."}),
        FakeEcho(),
    ]
    install(kernel, concrete_tools, policy)
    print("    Đã register:", ", ".join(t.name for t in concrete_tools))
    print("    -> Lưu ý: kernel.registry chỉ giữ ToolPort, không biết lớp FsRead/FakeEcho.")

    # --- Cấp cao gọi qua abstraction ---
    print("\n[2] Kernel gọi execute_tool() — chỉ qua ToolPort, không biết kiểu cụ thể.")
    r1 = kernel.execute_tool("fs_read", path="README.md")
    print("    fs_read README.md ->", r1)
    assert r1["ok"] and "DIP demo" in r1["content"]

    r2 = kernel.execute_tool("terminal_run", argv=["echo", "hello"])
    print("    terminal_run echo hello ->", r2)
    assert r2["ok"] and r2["stdout"] == "echo hello"

    # --- Policy gate chặn lệnh nguy hiểm NGAY TRONG adapter ---
    print("\n[3] Adapter chèn policy: lệnh nguy hiểm bị chặn trước khi chạm tool thật.")
    r3 = kernel.execute_tool("terminal_run", argv=["rm", "-rf", "/"])
    print("    terminal_run rm -rf / ->", r3)
    assert r3["ok"] is False and r3["policy_blocked"] is True
    assert r3["policy_code"] == "dangerous_terminal"

    # --- Graceful degradation: tool thiếu -> NullToolPort ---
    print("\n[4] Thiếu tool -> NullToolPort giữ kernel sống (graceful degradation).")
    r4 = kernel.execute_tool("does_not_exist")
    print("    does_not_exist ->", r4)
    assert r4["ok"] is False and r4["missing_capability"] is True

    # --- Bằng chứng DIP: SafeToolPort là ToolPort về mặt cấu trúc ---
    print("\n[5] Bất biến DIP: SafeToolPort và các tool đều thoả ToolPort (structural).")
    wrapped = SafeToolPort("fs_read", FsRead({"a": "x"}), policy)
    assert isinstance(wrapped, ToolPort), "SafeToolPort phải thoả ToolPort"
    assert isinstance(FsRead({}), ToolPort), "FsRead phải thoả ToolPort"
    assert isinstance(NullToolPort(), ToolPort), "NullToolPort phải thoả ToolPort"
    print("    isinstance(SafeToolPort, ToolPort) =", isinstance(wrapped, ToolPort))

    # --- ĐỐI CHỨNG: nếu kernel phụ thuộc lớp cụ thể thì sao? ---
    print("\n[6] ĐỐI CHỨNG — nếu KHÔNG dùng port (kernel cứng nhắc theo lớp cụ thể):")
    print("    Giả sử kernel viết: if name == 'fs_read': FsRead(...).read(...)")
    print("    Hậu quả: mỗi tool mới phải SỬA kernel; không thể chèn policy chung;")
    print("    không thể fake để test; không thể fallback khi thiếu tool.")
    print("    Với DIP: thêm tool = thêm 1 lớp ToolPort + 1 dòng ở composition root. Kernel BẤT BIẾN.")

    print("\nTẤT CẢ ASSERT PASS. DIP giữ kernel độc lập khỏi tool cụ thể + policy.\n")


if __name__ == "__main__":
    demo()
