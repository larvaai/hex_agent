# Case 01 — CapabilityRegistry + ToolPort: đăng ký tool kiểu plugin (OCP)

> "The behaviors of the system can be altered by **adding new code**, rather than
> changing existing code that already works." — Robert C. Martin (lesson 25, mục 1.2)

---

## 1. Bối cảnh trong hex_agent

hex_agent là 1 agent kernel: mọi năng lực (LLM chat, RAG, echo, …) đều phơi bày dưới dạng
**tool**. Bài toán thật: làm sao thêm tool mới (video, search, …) mà **không** đụng vào
kernel hay registry đã chạy production?

Lời giải gồm 3 mảnh, đều đã mở file kiểm chứng:

- **Abstraction (seam):** `ToolPort` Protocol — `core/ports.py:19-27`. Mọi tool chỉ cần có
  `name` + `execute(request) -> dict`. Vì là `Protocol` (structural typing), tool **không
  cần kế thừa** gì cả — duck typing.
- **Registry dispatcher:** `CapabilityRegistry` — `core/registry.py:43-122`. `resolve_tool(name)`
  tra cứu **bằng name string**, không hề có `if/switch` trên "loại tool". Thiếu tool thì rơi
  về `NullToolPort` (`core/registry.py:29-40`) để kernel không sập.
- **Caller phụ thuộc abstraction:** `AgentKernel.execute_tool()` — `core/kernel.py:106-177`.
  Hàm `core(req)` bên trong gọi `resolution.executor.execute(req)` — kernel **không biết**
  concrete tool nào tồn tại.
- **Extension point:** mỗi feature có hàm `install(kernel)` gọi `registry.register_tools(...)`
  — `features/example_echo.py:23-25`, `features/llm_chat.py:35-37`, `rag/feature.py:109-121`.

Thêm tool = thêm 1 class + 1 `install()`. `git diff --stat` trên `registry.py`/`kernel.py` = 0.

---

## 2. Trích đoạn code thật

`core/ports.py:19-27` — abstraction:

```python
@runtime_checkable
class ToolPort(Protocol):
    """A tool executor. Concrete behavior lives behind this port."""
    name: str
    def execute(self, request: ToolRequest) -> dict[str, Any]:
        ...
```

`core/registry.py:103-112` — dispatch bằng name, fallback NullToolPort, **không if/elif trên type**:

```python
def resolve_tool(self, name: str) -> ToolResolution:
    if name in self._tools:
        return ToolResolution(
            self._tools[name],
            self._tool_features.get(name),
            self._descriptors.get(name, DEFAULT_DESCRIPTOR),
        )
    if self._fallback is not None:
        return ToolResolution(self._fallback, self._fallback_feature, DEFAULT_DESCRIPTOR)
    return ToolResolution(self._null, None, DEFAULT_DESCRIPTOR)
```

`features/example_echo.py:16-25` — concrete impl + extension point:

```python
class EchoTool:
    name = "echo_tool"
    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {"ok": True, "echo": dict(request.args)}

def install(kernel: AgentKernel) -> None:
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tools(FEATURE.capabilities, EchoTool(), feature_name=FEATURE.name)
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò OCP | Thành phần trong hex_agent | File:line |
|---|---|---|
| Abstraction / seam | `ToolPort` Protocol | `core/ports.py:19-27` |
| Concrete implementations | `EchoTool`, `LLMChatTool`, `RagHealthTool/RagIngestTool/RagSearchTool` | `features/example_echo.py:16-21`, `features/llm_chat.py:17-32`, `rag/feature.py:71-106` |
| Registry dispatcher | `CapabilityRegistry.resolve_tool()` | `core/registry.py:103-112` |
| Fallback (no-op an toàn) | `NullToolPort` | `core/registry.py:29-40` |
| Caller phụ thuộc abstraction | `AgentKernel.execute_tool()` → `core(req)` | `core/kernel.py:152-177` |
| Extension point | `install(kernel)` của mỗi feature | `features/*.py`, `rag/feature.py:109-121` |

---

## 4. Bản rút gọn chạy được

File: [`capability_registry_and_port_pattern.py`](./capability_registry_and_port_pattern.py)
(`python3 capability_registry_and_port_pattern.py`, exit 0).

**Mô phỏng:** `ToolPort` Protocol, `CapabilityRegistry` (register/resolve), `NullToolPort`
fallback, `AgentKernel.execute_tool`, và 3 concrete tool (`EchoTool`, `LlmChatTool`,
`VideoProcessingTool`) + các hàm `install_*`. Demo chứng minh: thêm `VideoProcessingTool`
qua `install_video()` mà **mã nguồn của `CapabilityRegistry` và `AgentKernel` không đổi
1 ký tự** (kiểm bằng `inspect.getsource` so sánh trước/sau), kernel chạy được tool nó chưa
từng "thấy", và thiếu tool thì rơi về `NullToolPort`.

**Lược bỏ:** envelope `ToolRequest`/`CapabilityResult`, lineage + events, deep-freeze args,
scope check, middleware chain (xem case 02). LLM/RAG hạ tầng nặng thay bằng fake stdlib.
Giữ nguyên trục OCP: register → resolve-by-name → polymorphic dispatch.

**Đối chứng anti-OCP:** hàm `execute_tool_anti_ocp()` dùng `if/elif` trên `tool_name`. Thêm
`video.process` buộc **mở lại** hàm đã test; typo tool name chỉ lộ ở runtime (`else: raise`).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Magic + khó debug:** tool load runtime, stack trace đi qua `resolve_tool` gián tiếp; tên
  tool sai chỉ lộ khi gọi (registry mềm dẻo đánh đổi compile-time check).
- **Speculative generality:** nếu hệ thống mãi chỉ có **1 tool** và không có bên thứ ba, dựng
  registry + Protocol là thừa (lesson 25, mục 1.6 — rule of 3). Gọi hàm thẳng là đủ.
- **Mất tính tường minh:** không nhìn 1 chỗ mà biết hết tool nào tồn tại — phải lần theo các
  `install()` rải rác. Bù lại bằng `list_tools()`/`describe_capabilities()`.
- Khi **chưa có ≥ 2 variant thật**, đừng vội extract Protocol.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `resolve_tool` dùng **lookup theo name string** lại đạt OCP, còn `if tool_name == ...`
   thì không? (Gợi ý: cái nào buộc sửa code cũ khi thêm tool thứ N?)
2. `ToolPort` là `Protocol` (structural) chứ không phải abstract base class (`ABC`). Điều này
   thay đổi gì cho người viết tool mới? Có cần `import ToolPort` rồi kế thừa không?
3. `NullToolPort` đóng vai trò gì với OCP và với **độ bền** của kernel? Nếu bỏ nó đi, lời gọi
   1 tool chưa đăng ký sẽ ra sao?
