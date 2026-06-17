# Giải thích `toolbox/terminal.py`

File `toolbox/terminal.py` định nghĩa tool `terminal_run`, chạy command dạng argv trực tiếp trong workspace với timeout.

Nói ngắn gọn: module này cho agent chạy process không qua shell.

## Class `Terminal`

```python
class Terminal:
    name = "terminal_run"
```

Capability name là `terminal_run`.

Tool này được đăng ký qua `SafeToolPort` trong `toolbox/feature.py`, nên policy check chạy trước khi `Terminal.execute()` được gọi.

## Method `execute`

```python
def execute(self, request: ToolRequest) -> dict[str, Any]:
```

Input là `ToolRequest`, args kỳ vọng có:

- `argv`: list command arguments,
- `timeout`: optional seconds.

## Validate argv

```python
argv = request.args.get("argv")
if not isinstance(argv, list) or not argv:
    return {"ok": False, "error": "argv must be a non-empty list"}
```

Tool yêu cầu argv là list không rỗng.

Không nhận string command kiểu:

```text
"echo hi"
```

vì string command thường kéo theo shell parsing rủi ro.

## Clamp timeout

```python
timeout = min(max(int(request.args.get("timeout", 10)), 1), 30)
```

Timeout mặc định là 10 giây.

Giá trị được clamp trong khoảng 1 đến 30 giây.

## Workspace cwd

```python
cwd = workspace_dir()
cwd.mkdir(parents=True, exist_ok=True)
```

Command chạy với current working directory là workspace.

Nếu workspace chưa tồn tại, tạo nó.

## Chạy process

```python
proc = subprocess.run(
    [str(a) for a in argv],
    cwd=str(cwd),
    capture_output=True,
    text=True,
    timeout=timeout,
)
```

Điểm quan trọng:

- truyền argv list trực tiếp,
- không dùng `shell=True`,
- capture stdout/stderr,
- text mode,
- timeout rõ ràng.

## Error handling

Nếu executable không tồn tại:

```python
except FileNotFoundError as exc:
    return {"ok": False, "error": f"command not found: {exc}"}
```

Nếu timeout:

```python
except subprocess.TimeoutExpired:
    return {"ok": False, "error": f"timeout after {timeout}s"}
```

## Result

```python
return {
    "ok": proc.returncode == 0,
    "returncode": proc.returncode,
    "stdout": proc.stdout,
    "stderr": proc.stderr,
}
```

Nếu process exit code 0 thì `ok=True`, ngược lại `ok=False`.

Result vẫn chứa `returncode`, `stdout`, `stderr` để agent/debugger đọc.

## Safety nằm ở đâu?

`Terminal` tự validate argv shape và timeout, nhưng rule nguy hiểm nằm ở `safety.policy`.

Trong `toolbox/feature.py`, terminal được đăng ký như:

```python
SafeToolPort(tool.name, tool, policy)
```

Do đó các command như:

```python
["bash", "-c", "echo hi"]
```

bị block trước khi vào `Terminal.execute()`.

## Quan hệ với file khác

- `safety/policy.py`: chặn shell, token, destructive command, git mutation.
- `safety/sandbox.py`: cung cấp workspace cwd.
- `toolbox/feature.py`: đăng ký terminal qua `SafeToolPort`.
- `tests/test_toolbox.py`: kiểm tra argv Python chạy được và shell bị policy block.

## Tóm tắt

`toolbox/terminal.py` cung cấp `terminal_run`, chạy argv trực tiếp trong workspace với timeout, còn policy layer bên ngoài chịu trách nhiệm chặn command nguy hiểm.
