# Giải thích `safety/sandbox.py`

File `safety/sandbox.py` định nghĩa workspace path jail: mọi path của filesystem tool phải được resolve và kiểm tra nằm trong workspace.

Nói ngắn gọn: `sandbox.py` ngăn tool đọc/ghi file bên ngoài workspace.

## Hằng số `PROJECT_DIR`

```python
PROJECT_DIR = Path(__file__).resolve().parent.parent
```

Xác định project root từ vị trí file.

## Class `SandboxError`

```python
class SandboxError(ValueError):
    pass
```

Exception riêng khi path vi phạm sandbox, ví dụ cố escape ra ngoài workspace.

## Function `workspace_dir`

```python
def workspace_dir() -> Path:
    return Path(os.getenv("AGENT_WORKSPACE_DIR", str(PROJECT_DIR / "var" / "workspace"))).resolve()
```

Trả về workspace directory.

Ưu tiên env var:

```text
AGENT_WORKSPACE_DIR
```

Nếu không có, dùng mặc định:

```text
var/workspace
```

`.resolve()` chuyển về absolute canonical path.

## Function `resolve_in_workspace`

```python
def resolve_in_workspace(raw_path: str) -> Path:
```

Resolve một path và đảm bảo path đó vẫn nằm trong workspace.

### Lấy workspace

```python
workspace = workspace_dir()
```

### Convert raw path

```python
path = Path(raw_path)
if not path.is_absolute():
    path = workspace / path
```

Nếu caller truyền relative path, path được hiểu là nằm dưới workspace.

Ví dụ:

```text
a/b.txt -> <workspace>/a/b.txt
```

Nếu caller truyền absolute path, giữ nguyên rồi kiểm tra sau.

### Resolve path

```python
resolved = path.resolve()
```

Resolve `..`, symlink/canonical path tùy hệ điều hành.

### Chặn escape

```python
if resolved != workspace and not resolved.is_relative_to(workspace):
    raise SandboxError(f"Path is outside workspace: {raw_path}")
```

Path hợp lệ nếu:

- chính là workspace, hoặc
- nằm bên trong workspace.

Nếu không, raise `SandboxError`.

## Ví dụ

Nếu workspace là:

```text
D:/tmp/ws
```

Hợp lệ:

```text
a.txt -> D:/tmp/ws/a.txt
d/a.txt -> D:/tmp/ws/d/a.txt
```

Bị chặn:

```text
../../etc/passwd
D:/outside/file.txt
```

## Quan hệ với file khác

- `toolbox/filesystem.py`: dùng `resolve_in_workspace()` cho `fs_read`, `fs_write`, `fs_list`.
- `toolbox/terminal.py`: dùng `workspace_dir()` làm cwd khi chạy command.
- `tests/test_safety.py`: kiểm tra path trong workspace và escape bị block.

## Tóm tắt

`safety/sandbox.py` là path jail của project, đảm bảo filesystem và terminal tool chỉ thao tác trong workspace được cấu hình.
