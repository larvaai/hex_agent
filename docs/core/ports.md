# Giải thích `core/ports.py`

File `core/ports.py` định nghĩa protocol cho tool executor. Đây là phần "port" trong kiến trúc ports and adapters: kernel có thể nói chuyện với tool thông qua một interface chung, còn implementation cụ thể nằm ở adapter/feature bên ngoài.

Nói ngắn gọn: `ports.py` định nghĩa hình dạng tối thiểu của một tool.

## Vai trò trong architecture

Trong project này, tool cụ thể như `EchoTool` không cần kế thừa class base. Nó chỉ cần có:

- attribute `name`,
- method `execute(request: ToolRequest) -> dict[str, Any]`.

`ToolPort` mô tả hợp đồng đó bằng `Protocol`.

Điều này giúp kiến trúc linh hoạt:

- tool có thể là class bất kỳ,
- không cần inheritance cứng,
- type checker vẫn hiểu object nào có thể dùng như tool,
- kernel/registry chỉ dựa vào behavior, không dựa vào class cụ thể.

## Các import

```python
from __future__ import annotations
```

Bật postponed evaluation cho annotation.

```python
from typing import Any, Protocol, runtime_checkable
```

- `Any`: dùng cho dict result linh hoạt.
- `Protocol`: tạo structural interface.
- `runtime_checkable`: cho phép kiểm tra protocol bằng `isinstance()` ở runtime nếu cần.

```python
from core.schemas import ToolRequest
```

`ToolRequest` là object được truyền vào method `execute()`.

## Decorator `@runtime_checkable`

```python
@runtime_checkable
class ToolPort(Protocol):
```

`Protocol` mặc định chủ yếu phục vụ static type checking. Khi thêm `@runtime_checkable`, có thể kiểm tra:

```python
isinstance(obj, ToolPort)
```

Lưu ý: runtime check với protocol chỉ kiểm tra sự tồn tại của attribute/method ở mức cơ bản, không kiểm tra sâu signature hoặc type runtime.

Trong code hiện tại, project chưa dùng `isinstance(..., ToolPort)`, nhưng decorator này chuẩn bị sẵn cho validation sau này.

## Class `ToolPort`

```python
class ToolPort(Protocol):
    """A tool executor. Concrete behavior lives behind this port."""
```

`ToolPort` không phải implementation thật. Nó là interface dạng structural typing.

Docstring nói rõ: behavior cụ thể nằm sau port này.

## Attribute `name`

```python
name: str
```

Mỗi tool executor nên có `name`.

Ví dụ:

```python
class EchoTool:
    name = "echo_tool"
```

Kernel dùng tên executor để ghi metadata:

```python
getattr(resolution.executor, "name", resolution.executor.__class__.__name__)
```

Nếu executor không có `name`, kernel fallback về tên class. Nhưng theo protocol, executor nên có `name`.

## Method `execute`

```python
def execute(self, request: ToolRequest) -> dict[str, Any]:
    ...
```

Đây là method bắt buộc của một tool executor.

Input:

- `request`: `ToolRequest` gồm `name`, `args`, `request_id`.

Output:

- dict kết quả.

Tool có thể trả raw dict như:

```python
{"ok": True, "echo": {"msg": "hi"}}
```

hoặc trả envelope chuẩn như:

```python
{
    "ok": True,
    "capability": "echo",
    "feature": "example_echo",
    "data": {"echo": {"msg": "hi"}},
    "error": None,
    "metadata": {}
}
```

Kernel sẽ normalize bằng `CapabilityResult.from_raw()`.

Dấu `...` nghĩa là protocol chỉ khai báo signature, không implement logic.

## Ví dụ implementation hợp lệ

```python
from typing import Any

from core.schemas import ToolRequest


class EchoTool:
    name = "echo_tool"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {"ok": True, "echo": dict(request.args)}
```

Class này hợp lệ với `ToolPort` vì có `name` và `execute()`.

## Vì sao dùng Protocol thay vì abstract base class?

### 1. Structural typing

Object được xem là hợp lệ nếu có đúng hình dạng, không cần kế thừa.

### 2. Feature/plugin linh hoạt hơn

Plugin bên ngoài không cần import base class chỉ để subclass. Chỉ cần implement đúng method.

### 3. Giảm coupling

Kernel không phụ thuộc vào class hierarchy của tool.

### 4. Vẫn có lợi cho type checker

Type checker có thể hiểu contract của executor mà không ép inheritance.

## Quan hệ với file khác

- `core/kernel.py`: gọi `resolution.executor.execute(request)`.
- `core/registry.py`: lưu executor trong registry.
- `core/schemas.py`: cung cấp `ToolRequest`.
- `features/example_echo.py`: `EchoTool` là một implementation thực tế của port này.

## Giới hạn hiện tại

`ToolPort` hiện chỉ định nghĩa sync execute.

Chưa có:

- async tool execution,
- streaming result,
- schema cho args,
- schema cho output cụ thể,
- cancellation,
- timeout,
- permission boundary.

Các phần đó có thể được thêm sau nếu runtime cần.

## Tóm tắt một câu

`core/ports.py` định nghĩa contract tối thiểu cho tool executor: có `name` và method `execute(ToolRequest) -> dict`, giúp kernel gọi tool qua interface chung mà không phụ thuộc implementation cụ thể.
