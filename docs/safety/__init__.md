# Giải thích `safety/__init__.py`

File `safety/__init__.py` là facade public API cho package `safety`.

Nó export:

```python
from safety.policy import PolicyDecision, SafeToolPort, ToolPolicy, classify_terminal
from safety.sandbox import SandboxError, resolve_in_workspace, workspace_dir
```

## Vai trò

Package `safety` có hai nhóm chức năng:

- policy chokepoint: kiểm tra tool/terminal command có được phép chạy không.
- workspace sandbox: giới hạn file path nằm trong workspace.

`__init__.py` gom API chính để caller có thể import:

```python
from safety import SafeToolPort, ToolPolicy, resolve_in_workspace
```

## `__all__`

```python
__all__ = [
    "PolicyDecision",
    "SafeToolPort",
    "ToolPolicy",
    "classify_terminal",
    "SandboxError",
    "resolve_in_workspace",
    "workspace_dir",
]
```

Đây là public surface chính của safety layer.

## Tóm tắt

`safety/__init__.py` export policy và sandbox APIs, giúp toolbox và test dùng safety layer qua một package surface rõ ràng.
