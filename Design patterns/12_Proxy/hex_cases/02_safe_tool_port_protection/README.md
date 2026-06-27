# Case 02 — SafeToolPort: Protection Proxy

> **Một câu chốt:** `SafeToolPort` là Proxy "một class" sách-giáo-khoa: cùng interface với executor thật (`.execute(request) -> dict`), giữ reference real subject trong `self._inner`, chạy **policy check trước**, rồi hoặc trả "blocked" hoặc **delegate** nguyên vẹn cho `self._inner.execute()`. Client không phân biệt được nó với executor thật.

---

## 1. Bối cảnh trong hex_agent

Mọi tool trong toolbox đều có khả năng chạm tới hệ thống thật (terminal, file, git). hex_agent KHÔNG để mỗi server tự lo an toàn — thay vào đó dồn về **một cổng an toàn cross-cutting duy nhất**, rồi bọc mỗi executor bằng một Protection Proxy.

Đã mở file kiểm chứng — `safety/policy.py`:

- `safety/policy.py:105-124` — `SafeToolPort`: `__init__` lưu `self._inner` (executor thật) và `self._policy`; `execute()` (dòng 113-124) check policy rồi block hoặc delegate. Đây là toàn bộ thân Proxy.
- `safety/policy.py:77-102` — `ToolPolicy.check`: cổng an toàn duy nhất; nhánh `terminal_run` gọi `classify_terminal`, nhánh git mutation, nhánh repair-mode whole-file write.
- `safety/policy.py:53-71` — `classify_terminal`: phân loại argv (shell exe, shell token, destructive, git mutation, path escape).
- `safety/policy.py:41-46` — `PolicyDecision`: dataclass frozen `(allowed, reason, code, risk)`.
- `safety/policy.py:13-18` — các tập hằng: `SHELL_EXES`, `SHELL_TOKENS`, `DESTRUCTIVE_EXES`, `_ABS_PATH_RE`.

Vấn đề thật được giải quyết: nếu để LLM gọi `terminal_run(["bash","-c","rm -rf /"])` chạm thẳng executor thật, hệ thống bị huỷ. SafeToolPort chặn ngay tại biên — executor thật KHÔNG bao giờ thấy request bị deny.

---

## 2. Trích đoạn code thật

`SafeToolPort` (`safety/policy.py:105-124`):

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
            return {
                "ok": False,
                "tool": request.name,
                "policy_blocked": True,
                "policy_code": decision.code,
                "error": decision.reason,
                "metadata": {"risk": decision.risk},
            }
        return self._inner.execute(request)
```

Pre-check logic — `ToolPolicy.check` (`safety/policy.py:88-102`, rút gọn):

```python
def check(self, tool_name: str, args: dict[str, Any]) -> PolicyDecision:
    if tool_name in {"terminal_run", "terminal.run", "terminal"}:
        return classify_terminal(args.get("argv"))
    ...
    return PolicyDecision(True)
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Proxy (GoF) | Thành phần trong hex_agent | File:line |
|---|---|---|
| **Subject interface** | quy ước `ToolPort.execute(request) -> dict` | `safety/policy.py:113` |
| **RealSubject** | executor thật bên trong (`self._inner`) | `safety/policy.py:124` (`self._inner.execute`) |
| **Proxy** | `SafeToolPort` | `safety/policy.py:105-124` |
| **Pre-check (gate logic)** | `ToolPolicy.check` + `classify_terminal` | `safety/policy.py:88-102, 53-71` |
| **Quyết định block/allow** | `PolicyDecision(allowed, reason, code, risk)` | `safety/policy.py:41-46` |
| **Client** | hàm dựng executor (kernel core) gọi `.execute` | `core/kernel.py:155` |

---

## 4. Bản rút gọn chạy được

File: [`safe_tool_port_protection.py`](./safe_tool_port_protection.py)

Nó mô phỏng:
- `EchoExecutor` = RealSubject "naive" (cứ nhận request là "chạy", đếm số lần execute).
- `ToolPolicy` + `classify_terminal` distill 1-1 các nhánh shell-exe / shell-token / destructive.
- `SafeToolPort` giữ nguyên cấu trúc: `_inner`, `_policy`, `execute()` = check rồi block-or-delegate.

Nó lược bỏ: kiểm tra path-escape ngoài workspace (`_argv_escapes_workspace`), nhánh git mutation, `repair_mode` whole-file write; và thay executor chạy lệnh thật bằng echo stdlib không chạm hệ thống. Mục [6] của demo là **đối chứng** "bypass the proxy" (đúng tinh thần `12_Proxy.md` mục III): gọi thẳng `real.execute("rm -rf /")` cho thấy nếu còn một đường truy cập thẳng RealSubject thì Proxy bị vô hiệu hoá.

Chạy:

```bash
python3 safe_tool_port_protection.py
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Phải đóng kín mọi access.** Proxy chỉ bảo vệ nếu MỌI lời gọi đi qua nó. Để một call-site gọi thẳng `_inner` = bypass toàn bộ chính sách (lỗ hổng nghiêm trọng).
- **Policy tập trung là con dao hai lưỡi.** Gom về một `ToolPolicy` giúp dễ audit, nhưng cũng là điểm-hỏng-đơn-lẻ: sai một dòng `check` là cả hệ thống mất hàng rào.
- **Không phải nơi cho business logic.** Proxy chỉ nên kiểm soát truy cập (intent của Proxy), không nên biến đổi nghiệp vụ — nếu cần thêm tính năng, đó là Decorator chứ không phải Proxy.
- **Chi phí false-positive.** Policy quá chặt (vd chặn mọi argv tuyệt đối) có thể chặn nhầm lệnh hợp lệ; cần `risk`/`code` rõ để người dùng hiểu vì sao bị chặn.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `SafeToolPort` là **Proxy** chứ không phải **Adapter**? (Gợi ý: interface vào/ra có đổi không?)
2. Trong demo, sau khi gọi 4 lệnh bị chặn, vì sao `real.executions` vẫn chỉ có đúng 1 phần tử? Điều đó chứng minh tính chất nào của Protection Proxy?
3. "Bypass the proxy" nguy hiểm thế nào trong một API gateway thật? Cho một ví dụ đường truy cập nội bộ vô tình bỏ qua lớp auth.
