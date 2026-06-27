"""
CASE 01 — OCP qua CapabilityRegistry + ToolPort (plugin pattern)
================================================================

Bản DISTILL TRUNG THỰC (chỉ stdlib) của cơ chế đăng ký + gọi tool trong hex_agent.

NGUỒN THẬT (đã mở file kiểm chứng):
  - core/ports.py:19-27       ToolPort Protocol (seam: name + execute(request) -> dict)
  - core/registry.py:43-122   CapabilityRegistry (register_tool/register_tools/resolve_tool)
  - core/registry.py:29-40    NullToolPort (fallback giữ kernel sống khi thiếu tool)
  - core/kernel.py:106-177    AgentKernel.execute_tool() -> core(req): resolve rồi gọi executor
  - features/example_echo.py:1-26   EchoTool + install(kernel) — feature/plugin đơn giản nhất
  - features/llm_chat.py:17-37       LLMChatTool + install(kernel)
  - rag/feature.py:53-121            _RagTool base + RagHealthTool/RagIngestTool/RagSearchTool + install()

Ý TƯỞNG OCP (Robert C. Martin reformulation, lesson 25 mục 1.2):
  "The behaviors of the system can be altered by adding new code, rather than
   changing existing code that already works."

  - ToolPort = abstraction (interface/seam).
  - EchoTool / LlmChatTool / NewVideoTool = concrete impls (mỗi cái 1 'namespace' riêng,
    giống pattern separation ở dentate gyrus — thêm impl mới KHÔNG đè impl cũ).
  - CapabilityRegistry = registry dispatcher: lookup BẰNG name string, KHÔNG if/elif trên type.
  - kernel.execute_tool() = caller phụ thuộc abstraction, không biết concrete tool nào tồn tại.
  - install(kernel) = extension point: thêm tool mới = thêm class + gọi install, 0 sửa registry/kernel.

LƯỢC BỎ so với bản thật:
  - Bỏ ToolRequest/CapabilityResult envelope phức tạp, lineage events, deep-freeze, scope check,
    middleware chain (xem CASE 02). Ở đây chỉ giữ trục OCP: register -> resolve -> dispatch.
  - Thay LLM/RAG hạ tầng nặng bằng fake stdlib tối thiểu.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, NamedTuple, Protocol, runtime_checkable


# ── 1. ABSTRACTION: ToolPort (distill core/ports.py:19-27) ──────────────────────
@runtime_checkable
class ToolPort(Protocol):
    """Seam mọi tool concrete phải tuân thủ. Structural typing (Protocol):
    không cần kế thừa, chỉ cần CÓ `name` + `execute(request) -> dict` (duck typing)."""

    name: str

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        ...


# ── 2. FALLBACK: NullToolPort (distill core/registry.py:29-40) ──────────────────
class NullToolPort:
    """Giữ 'kernel' sống khi tool không tồn tại — trả lỗi có cấu trúc, không raise."""

    name = "null_tool"

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "tool": request.get("name"),
            "missing_capability": True,
            "error": f"No tool capability is registered for {request.get('name')!r}.",
        }


class ToolResolution(NamedTuple):
    """Distill core/registry.py:23-26 — kết quả lookup: executor + tên feature."""

    executor: Any
    feature: str | None


# ── 3. REGISTRY DISPATCHER: CapabilityRegistry (distill core/registry.py:43-122) ─
class CapabilityRegistry:
    """Đăng ký tool theo NAME, resolve theo NAME. Tuyệt đối KHÔNG có if/switch trên
    'loại tool'. Thêm tool = thêm 1 entry vào dict. Đây là pattern Plugin/Registry
    (lesson 25, bảng 2.1 cơ chế #6)."""

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._tool_features: dict[str, str] = {}
        self._null = NullToolPort()

    def register_tool(self, name: str, executor: Any, *, feature_name: str | None = None) -> None:
        self._tools[name] = executor
        if feature_name:
            self._tool_features[name] = feature_name

    def register_tools(self, names, executor: Any, *, feature_name: str | None = None) -> None:
        for name in names:
            self.register_tool(name, executor, feature_name=feature_name)

    def resolve_tool(self, name: str) -> ToolResolution:
        # Lookup bằng name string. Không biết, không quan tâm tool đó là loại gì.
        if name in self._tools:
            return ToolResolution(self._tools[name], self._tool_features.get(name))
        return ToolResolution(self._null, None)  # fallback: NullToolPort

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[str]:
        return sorted(self._tools)


# ── 4. FEATURE DESCRIPTOR + KERNEL (caller phụ thuộc abstraction) ───────────────
@dataclass
class FeatureDescriptor:
    name: str
    capabilities: tuple[str, ...]
    description: str = ""


@dataclass
class AgentKernel:
    """Distill core/kernel.py:106-177 (rút gọn): execute_tool resolve rồi gọi executor.
    Kernel KHÔNG bao giờ biết EchoTool/LlmChatTool/NewVideoTool tồn tại."""

    registry: CapabilityRegistry = field(default_factory=CapabilityRegistry)
    log: list[str] = field(default_factory=list)

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        request = {"name": tool_name, "args": dict(args or {})}
        resolution = self.registry.resolve_tool(tool_name)
        try:
            result = resolution.executor.execute(request)
        except Exception as exc:  # một tool không bao giờ được làm sập kernel
            result = {"ok": False, "tool": tool_name, "error": str(exc), "kernel_error": True}
        self.log.append(
            f"execute_tool({tool_name!r}) -> executor={resolution.executor.name!r} "
            f"feature={resolution.feature!r} ok={result.get('ok')}"
        )
        return result


# ── 5. CONCRETE IMPLS — mỗi tool 1 class (distill features/*.py + rag/feature.py) ─
class EchoTool:
    """Distill features/example_echo.py:16-21 — tool đơn giản nhất."""

    name = "echo_tool"

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "echo": dict(request["args"])}


def install_echo(kernel: AgentKernel) -> None:
    """Distill features/example_echo.py:23-25 — extension point pattern."""
    feature = FeatureDescriptor(name="example_echo", capabilities=("echo",))
    kernel.registry.register_tools(feature.capabilities, EchoTool(), feature_name=feature.name)


def _fake_call_llm(messages: list[dict[str, str]], *, model: str | None) -> str:
    """Fake stdlib thay cho llm.adapter.call_llm — KHÔNG mạng, KHÔNG SDK bên thứ ba."""
    last = messages[-1]["content"] if messages else ""
    return f"[{model or 'fake-model'}] reply to: {last}"


class LlmChatTool:
    """Distill features/llm_chat.py:17-32 — LLM phơi bày như 1 tool, client injectable."""

    name = "llm_chat_tool"

    def __init__(self, client: Callable[..., str] | None = None) -> None:
        self._client = client or _fake_call_llm

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        a = request["args"]
        content = self._client(a.get("messages", []), model=a.get("model"))
        return {"ok": True, "content": content, "model": a.get("model")}


def install_llm(kernel: AgentKernel, *, client=None) -> None:
    """Distill features/llm_chat.py:35-37."""
    feature = FeatureDescriptor(name="llm", capabilities=("llm.chat",))
    kernel.registry.register_tools(feature.capabilities, LlmChatTool(client), feature_name=feature.name)


# ── 6. EXTENSION DEMO: thêm tool MỚI mà KHÔNG sửa registry/kernel ───────────────
class VideoProcessingTool:
    """TOOL MỚI ('open for extension'). Để cắm vào, ta CHỈ viết class này + 1 hàm install.
    0 dòng nào của CapabilityRegistry hay AgentKernel bị sửa ('closed for modification')."""

    name = "video_processing_tool"

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        seconds = float(request["args"].get("seconds", 0))
        return {"ok": True, "thumbnails": int(seconds // 10) + 1}


def install_video(kernel: AgentKernel) -> None:
    feature = FeatureDescriptor(name="video", capabilities=("video.process",))
    kernel.registry.register_tools(feature.capabilities, VideoProcessingTool(), feature_name=feature.name)


# ── 7. ĐỐI CHỨNG: nếu KHÔNG dùng pattern -> if/elif trên tool_name ──────────────
def execute_tool_anti_ocp(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """VI PHẠM OCP (lesson 25, Ví dụ 2): dispatch bằng if/elif trên type tag.
    Mỗi tool mới = SỬA chính hàm này -> merge conflict, regression chéo, không có
    compile-time check cho typo tool name (chỉ phát hiện runtime ở nhánh else)."""
    if tool_name == "echo":
        return {"ok": True, "echo": dict(args)}
    elif tool_name == "llm.chat":
        return {"ok": True, "content": _fake_call_llm(args.get("messages", []), model=args.get("model"))}
    # Muốn thêm 'video.process'? -> phải MỞ hàm này ra, thêm 1 nhánh elif nữa.
    else:
        raise ValueError(f"Unknown tool: {tool_name}")  # lỗi runtime, không phải compile-time


def demo() -> None:
    print("=" * 72)
    print("CASE 01 — OCP qua CapabilityRegistry + ToolPort (plugin pattern)")
    print("=" * 72)

    # --- Bước 1: dựng kernel, cài 2 feature qua extension point install() ---
    kernel = AgentKernel()
    install_echo(kernel)
    install_llm(kernel)
    print("\n[1] Đã cài 2 feature qua install(). Tools registry biết:")
    print("   ", kernel.registry.list_tools())

    r_echo = kernel.execute_tool("echo", {"msg": "xin chào"})
    r_llm = kernel.execute_tool("llm.chat", {"messages": [{"role": "user", "content": "2+2?"}], "model": "m1"})
    print("    echo  ->", r_echo)
    print("    llm   ->", r_llm)
    assert r_echo["ok"] and r_echo["echo"] == {"msg": "xin chào"}
    assert r_llm["ok"] and "2+2?" in r_llm["content"]

    # --- Bước 2: snapshot 'mã cũ' để chứng minh nó KHÔNG bị sửa khi thêm tool ---
    import inspect
    registry_src_before = inspect.getsource(CapabilityRegistry)
    kernel_src_before = inspect.getsource(AgentKernel)

    print("\n[2] THÊM tool mới (VideoProcessingTool) qua install_video() — open for extension:")
    install_video(kernel)
    print("    Tools registry sau khi thêm:", kernel.registry.list_tools())
    r_video = kernel.execute_tool("video.process", {"seconds": 35})
    print("    video ->", r_video)
    assert r_video["ok"] and r_video["thumbnails"] == 4  # 35//10 + 1

    # INVARIANT OCP: thêm variant mới = 0 sửa code cũ (lesson 25, mục 2.3 #2).
    registry_src_after = inspect.getsource(CapabilityRegistry)
    kernel_src_after = inspect.getsource(AgentKernel)
    assert registry_src_before == registry_src_after, "CapabilityRegistry KHÔNG được sửa!"
    assert kernel_src_before == kernel_src_after, "AgentKernel KHÔNG được sửa!"
    print("    OK: CapabilityRegistry + AgentKernel KHÔNG đổi 1 dòng (closed for modification).")

    # --- Bước 3: caller phụ thuộc abstraction — kernel chạy tool nó chưa từng 'thấy' ---
    print("\n[3] Kernel gọi VideoProcessingTool mà bên trong execute_tool KHÔNG có nhánh nào")
    print("    nhắc tới 'video'. Dispatch hoàn toàn bằng registry lookup (polymorphic).")
    assert "video" not in inspect.getsource(AgentKernel.execute_tool)

    # --- Bước 4: fallback NullToolPort cho tool thiếu — không sập ---
    print("\n[4] Gọi tool KHÔNG tồn tại -> NullToolPort fallback (kernel vẫn sống):")
    r_missing = kernel.execute_tool("does.not.exist", {})
    print("    ->", r_missing)
    assert r_missing["ok"] is False and r_missing["missing_capability"] is True

    # --- Bước 5: ĐỐI CHỨNG anti-OCP ---
    print("\n[5] ĐỐI CHỨNG — phiên bản if/elif (anti-OCP):")
    print("    'echo' và 'llm.chat' chạy được:")
    print("    ", execute_tool_anti_ocp("echo", {"x": 1}))
    print("    Nhưng 'video.process' CHƯA có nhánh -> raise ValueError (phải SỬA hàm cũ):")
    try:
        execute_tool_anti_ocp("video.process", {"seconds": 35})
        raise AssertionError("đáng lẽ phải raise")
    except ValueError as exc:
        print("     ->", exc)
    print("    => Mỗi tool mới buộc mở lại 1 hàm đã test. Đó là điều OCP loại bỏ.")

    print("\n[KẾT] Thêm tool = thêm class + install(); registry/kernel bất biến. OCP đạt.")
    print("=" * 72)


if __name__ == "__main__":
    demo()
