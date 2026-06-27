# Case 01 — SafeToolPort: lớp chính sách an toàn bọc quanh `ToolPort`

> DIP (Dependency Inversion Principle) — SOLID Pattern 5
> Cấp cao (`core/`) ĐỊNH NGHĨA `ToolPort`; cấp thấp (`toolbox/`) PHẢI ADAPT theo.

---

## 1. Bối cảnh trong hex_agent

Kernel của agent cần "thực thi một tool theo tên" (đọc file, chạy terminal, index code…).
Nếu kernel import thẳng từng lớp tool cụ thể thì: (a) mỗi tool mới phải sửa kernel,
(b) không thể chèn một chốt chặn an toàn chung trước mọi tool, (c) không test được kernel
nếu thiếu hạ tầng filesystem/terminal thật.

hex_agent giải bằng DIP. Cấp cao `core/` tuyên bố hợp đồng `ToolPort` (chỉ cần `name` +
`execute()`). Mọi tool cụ thể chỉ cần tuân hợp đồng đó. Một **adapter** `SafeToolPort` bọc
một tool bất kỳ, chạy policy gate rồi mới delegate — và bản thân `SafeToolPort` cũng là một
`ToolPort` nên trong suốt với kernel. Composition root ở `toolbox/feature.py` mới là nơi
duy nhất biết cả lớp tool cụ thể lẫn policy.

File:line thật đã mở kiểm chứng:
- `core/ports.py:19-26` — định nghĩa `ToolPort` Protocol (abstraction, do cấp cao sở hữu).
- `safety/policy.py:105-124` — `SafeToolPort` (adapter bọc + policy gate).
- `toolbox/feature.py:67-77` — `install()` (composition root: bọc rồi register).
- `core/registry.py:29-40` — `NullToolPort` (fallback khi thiếu tool).

---

## 2. Trích đoạn code thật

`core/ports.py:19-26` — abstraction do cấp cao định nghĩa:

```python
@runtime_checkable
class ToolPort(Protocol):
    """A tool executor. Concrete behavior lives behind this port."""

    name: str

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        ...
```

`safety/policy.py:105-124` — adapter bọc, chèn policy trước khi delegate:

```python
class SafeToolPort:
    """Wrap a tool executor; run the policy chokepoint before delegating. Epic E06."""

    def __init__(self, name: str, inner: Any, policy: ToolPolicy | None = None) -> None:
        self.name = name
        self._inner = inner
        self._policy = policy or ToolPolicy()

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        decision = self._policy.check(request.name, request.args)
        if not decision.allowed:
            return {"ok": False, "tool": request.name, "policy_blocked": True, ...}
        return self._inner.execute(request)
```

`toolbox/feature.py:67-77` — composition root wiring concrete vào abstraction:

```python
def install(kernel: AgentKernel) -> None:
    kernel.registry.register_feature(FEATURE)
    policy = ToolPolicy()
    for tool_cls in _TOOL_CLASSES:
        tool = tool_cls()
        kernel.registry.register_tool(
            tool.name,
            SafeToolPort(tool.name, tool, policy),   # ← bọc trong adapter rồi register
            feature_name=FEATURE.name,
            **_DESCRIPTORS[tool.name],
        )
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò DIP | Thành phần trong hex_agent | Trong bản rút gọn |
|---|---|---|
| Abstraction (do cấp cao sở hữu) | `ToolPort` Protocol — `core/ports.py:19-26` | `ToolPort` |
| Cấp cao tiêu thụ (consumer) | `AgentKernel.execute_tool()` + `CapabilityRegistry` — `core/` | `AgentKernel`, `CapabilityRegistry` |
| Adapter bọc (decorator-port) | `SafeToolPort` — `safety/policy.py:105-124` | `SafeToolPort` |
| Cấp thấp cụ thể (provider) | `FsRead`, `Terminal`, … — `toolbox/` | `FsRead`, `FakeEcho` |
| Fallback (graceful degradation) | `NullToolPort` — `core/registry.py:29-40` | `NullToolPort` |
| Composition root (wiring) | `install()` — `toolbox/feature.py:67-77` | `install()` |

Đảo chiều source code: `core/` **không** import `toolbox/`; `toolbox/` import abstraction từ
`safety/` + `core/`. Chỉ composition root thấy cả hai tầng.

---

## 4. Bản rút gọn chạy được

File: `tool_safety_port_adapter.py` (chỉ thư viện chuẩn).

Mô phỏng đầy đủ: `ToolPort` Protocol, `SafeToolPort` adapter + policy gate, hai tool cụ thể
(`FsRead`, `FakeEcho`), registry với `NullToolPort` fallback, kernel gọi qua abstraction,
và composition root `install()`.

Lược bỏ / thay bằng fake: filesystem sandbox và terminal subprocess thật → `FsRead` đọc
dict trong bộ nhớ, `FakeEcho` vọng lại argv; `ToolPolicy` chỉ chặn vài chuỗi nguy hiểm
thay vì toàn bộ chuỗi quy tắc gốc; registry rút gọn còn `register_tool/resolve`.

Chạy:

```bash
python3 tool_safety_port_adapter.py
```

Bước [6] là đối chứng: nếu kernel dùng `if name == 'fs_read': ...` thì mỗi tool mới phải sửa
kernel, không chèn được policy chung, không fake để test.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- Thêm một lớp gián tiếp (`ToolPort`) + một lớp adapter (`SafeToolPort`) → nhiều file, một
  cú nhảy thêm khi đọc luồng gọi.
- Nếu chỉ có **một** loại tool duy nhất và sẽ không bao giờ thêm, lại không cần policy chung
  hay test cô lập → port là over-engineering; gọi thẳng đủ rồi.
- Adapter "trong suốt" (cùng interface với thứ nó bọc) dễ bị lạm dụng thành nhiều tầng wrap
  khó debug — giữ tối đa 1–2 lớp.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `SafeToolPort` phải tự nó là một `ToolPort` thì kernel mới "không nhận ra" có policy
   gate ở giữa?
2. Nếu muốn thêm tool `git_clone`, bạn phải sửa những file nào? Kernel có nằm trong số đó không?
3. `NullToolPort` minh hoạ tính chất gì của hệ DIP-compliant khi một dependency vắng mặt?
