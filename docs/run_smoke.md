# `run_smoke.py` — deterministic offline smoke

Chạy:

```powershell
python run_smoke.py
```

Thành công khi in:

```text
CORE_AGENT_SMOKE_OK run_id=<run_id>
```

Script không gọi LLM/network. Flow hiện tại:

1. `create_kernel()` đọc `config/features.yaml`, tạo shared `AgentKernel`, registry/event bus và
   cài enabled features/middleware.
2. `EventLogger()` tạo run log; `attach_to_bus()` subscribe vào `kernel.events`.
3. `SessionFactory(kernel).create_root(...)` tạo `KernelSession`, `SessionIdentity`, per-session
   `StateStore`, accept `TaskEnvelope` và freeze shared kernel/registry/config.
4. `session.execute_tool("echo", {"msg":"hi"})` kiểm tra session → kernel → registry →
   `EchoTool` → `CapabilityResult` + lineage metadata.
5. `session.execute_tool("does_not_exist")` bị session scope chặn có cấu trúc (`scope_block`);
   default root scope chỉ gồm capability đã đăng ký.
6. `parse_action()` kiểm tra JSON fence/trailing-comma repair.
7. `check_finish()` kiểm tra code-changed-without-validation gate.
8. `session.complete_task()` đóng lifecycle; `logger.finish()` ghi summary và success marker.

Đây là smoke của foundation, không thay thế full suite:

```powershell
python -m pytest
python -m ruff check .
```
