# Giải thích `core/__init__.py`

File `core/__init__.py` hiện tại đang rỗng.

Dù không có code, file này vẫn có ý nghĩa trong cấu trúc Python package: nó đánh dấu thư mục `core/` là một package Python truyền thống, để các module như `core.kernel`, `core.bootstrap`, `core.registry` có thể được import ổn định.

## Vai trò trong package

Với cấu trúc:

```text
core/
  __init__.py
  bootstrap.py
  events.py
  kernel.py
  ports.py
  registry.py
  schemas.py
  state.py
```

các file khác có thể import:

```python
from core.kernel import AgentKernel
from core.bootstrap import create_kernel
from core.registry import CapabilityRegistry
```

`__init__.py` làm cho `core` trở thành package namespace rõ ràng.

## Vì sao file rỗng vẫn hợp lý?

Một `__init__.py` rỗng là lựa chọn tốt khi package không muốn expose API cấp package.

Ví dụ project hiện không định nghĩa:

```python
from core import AgentKernel
```

Thay vào đó, caller import trực tiếp từ module cụ thể:

```python
from core.kernel import AgentKernel
```

Cách này giúp dependency rõ hơn:

- cần kernel thì import `core.kernel`,
- cần bootstrap thì import `core.bootstrap`,
- cần schema thì import `core.schemas`.

## Có nên export gì trong `__init__.py` không?

Hiện tại chưa cần.

Nếu sau này muốn public API gọn hơn, có thể thêm:

```python
from core.bootstrap import create_kernel
from core.kernel import AgentKernel

__all__ = ["AgentKernel", "create_kernel"]
```

Khi đó caller có thể dùng:

```python
from core import AgentKernel, create_kernel
```

Nhưng việc này cũng làm `core.__init__` import thêm module khi package được import. Với lõi đang muốn nhẹ và tránh coupling sớm, để rỗng là hợp lý.

## Ý nghĩa kiến trúc

`core/__init__.py` rỗng thể hiện project chưa gom toàn bộ core thành một API facade. Mỗi module vẫn có trách nhiệm riêng và được import trực tiếp.

Điều này phù hợp với Sprint 0:

- module nhỏ,
- dependency rõ,
- tránh import side effect,
- tránh tạo API công khai quá sớm.

## Tóm tắt một câu

`core/__init__.py` hiện là marker package rỗng, giúp `core/` import được như Python package mà không tạo thêm side effect hay API facade chưa cần thiết.
