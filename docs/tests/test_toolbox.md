# Giải thích `tests/test_toolbox.py`

File `tests/test_toolbox.py` kiểm tra toolbox feature khi được đăng ký vào kernel: filesystem tools và terminal tool chạy qua safety wrapper.

Nói ngắn gọn: test này đảm bảo toolbox dùng được qua `kernel.execute_tool()`.

## Config test

```python
TOOLBOX = {"features": {"toolbox": {"enabled": True, "module": "toolbox.feature"}}}
```

Kernel chỉ bật feature `toolbox`.

## Helper `_kernel`

```python
def _kernel(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    return build_kernel(TOOLBOX)
```

Helper set workspace vào temp dir rồi build kernel.

Điều này đảm bảo filesystem/terminal tool không đụng vào project thật.

## `test_fs_write_then_read`

```python
w = k.execute_tool("fs_write", {"path": "d/a.txt", "content": "hi"})
assert w["ok"] is True
r = k.execute_tool("fs_read", {"path": "d/a.txt"})
assert r["ok"] is True and r["data"]["content"] == "hi"
```

Kiểm tra:

1. `fs_write` ghi file trong workspace.
2. `fs_read` đọc lại đúng content.
3. Kernel envelope chứa content trong `data`.

Hợp đồng: filesystem tools hoạt động qua registry/kernel.

## `test_fs_read_escape_blocked`

```python
r = k.execute_tool("fs_read", {"path": "../../etc/passwd"})
assert r["ok"] is False
assert "outside workspace" in (r["error"] or "")
```

Kiểm tra path traversal bị chặn khi gọi qua kernel.

Hợp đồng: sandbox error phải đi qua tool result và kernel envelope.

## `test_terminal_argv_runs`

```python
r = k.execute_tool("terminal_run", {"argv": ["python3", "-c", "print('hi')"]})
assert r["ok"] is True
assert "hi" in r["data"]["stdout"]
```

Kiểm tra terminal tool chạy argv trực tiếp.

Hợp đồng: policy cho phép command argv an toàn, terminal capture stdout, kernel wrap đúng.

## `test_terminal_shell_blocked_by_policy`

```python
r = k.execute_tool("terminal_run", {"argv": ["bash", "-c", "echo hi"]})
assert r["ok"] is False
assert r["data"].get("policy_blocked") is True
```

Kiểm tra shell executable bị `SafeToolPort` block trước khi terminal chạy.

Hợp đồng: toolbox tool phải được đăng ký qua safety wrapper, không đăng ký raw executor.

## Nếu test này đỏ nghĩa là gì?

- Toolbox feature có thể không đăng ký tool.
- Filesystem sandbox có thể hỏng.
- Kernel envelope có thể không chứa data/error đúng.
- Terminal tool có thể không chạy argv đúng.
- Safety wrapper có thể không được áp dụng.

## Tóm tắt

`tests/test_toolbox.py` bảo vệ integration của toolbox với kernel: fs write/read, sandbox escape block, terminal argv chạy được và shell bị policy chặn.
