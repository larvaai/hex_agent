# Giải thích `tests/test_safety.py`

File `tests/test_safety.py` kiểm tra safety layer: workspace sandbox và policy chokepoint cho terminal/git.

Nói ngắn gọn: test này đảm bảo tool nguy hiểm bị chặn trước khi chạy.

## Import

```python
import pytest

from safety.policy import ToolPolicy, classify_terminal
from safety.sandbox import SandboxError, resolve_in_workspace
```

Test trực tiếp hai module:

- `safety.sandbox`
- `safety.policy`

## `test_sandbox_resolves_inside`

```python
monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
p = resolve_in_workspace("a/b.txt")
assert str(p).startswith(str(tmp_path.resolve()))
```

Kiểm tra relative path được resolve vào workspace.

Hợp đồng: path hợp lệ phải nằm dưới `AGENT_WORKSPACE_DIR`.

## `test_sandbox_escape_blocked`

```python
with pytest.raises(SandboxError):
    resolve_in_workspace("../../etc/passwd")
```

Kiểm tra path traversal bị chặn.

Hợp đồng: `../..` không được escape khỏi workspace.

## `test_policy_blocks_shell_exe`

```python
d = classify_terminal(["bash", "-c", "echo hi"])
assert d.allowed is False and d.code == "shell_exe"
```

Kiểm tra shell executable bị block.

Hợp đồng: terminal tool không cho chạy shell wrapper như `bash -c`.

## `test_policy_blocks_redirect_token`

```python
assert classify_terminal(["python3", "-c", "x", ">", "f"]).allowed is False
```

Kiểm tra shell redirection token bị block dù executable không phải shell.

Hợp đồng: token như `>`, `<`, `|`, `;` không được xuất hiện trong argv.

## `test_policy_allows_python_argv`

```python
assert classify_terminal(["python3", "-c", "print(1)"]).allowed is True
```

Kiểm tra argv trực tiếp, không shell token, được phép.

Hợp đồng: policy không chặn mọi terminal command, chỉ chặn pattern nguy hiểm.

## `test_policy_blocks_git_mutation`

```python
monkeypatch.delenv("AGENT_ALLOW_GIT_MUTATIONS", raising=False)
d = ToolPolicy().check("git_commit", {})
assert d.allowed is False and d.code == "git_mutation"
```

Kiểm tra git mutation tool bị block khi env allow chưa bật.

Hợp đồng: thao tác git thay đổi repo phải bị chặn mặc định.

## Nếu test này đỏ nghĩa là gì?

- Path jail có thể cho phép đọc/ghi ngoài workspace.
- Terminal policy có thể cho shell hoặc redirection chạy.
- Git mutation có thể không bị chặn mặc định.
- Safety chokepoint có thể quá lỏng hoặc quá chặt.

## Tóm tắt

`tests/test_safety.py` bảo vệ safety layer: workspace path không được escape, shell/control token bị block, command argv an toàn được phép, và git mutation bị chặn mặc định.
