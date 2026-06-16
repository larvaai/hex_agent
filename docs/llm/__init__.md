# Giải thích `llm/__init__.py`

File `llm/__init__.py` định nghĩa public API cấp package cho module `llm`.

Nó export hai function từ `llm.adapter`:

```python
from llm.adapter import call_llm, reset_client

__all__ = ["call_llm", "reset_client"]
```

## Vai trò trong package

Nhờ file này, caller có thể import ngắn:

```python
from llm import call_llm, reset_client
```

thay vì:

```python
from llm.adapter import call_llm, reset_client
```

Đây là facade nhỏ cho package `llm`.

## Import `call_llm` và `reset_client`

```python
from llm.adapter import call_llm, reset_client
```

Hai function được đưa lên package-level:

- `call_llm`: gọi OpenAI-compatible chat endpoint.
- `reset_client`: reset lazy client cache.

Vì `llm.adapter` được thiết kế lazy, import package `llm` vẫn không tạo OpenAI client thật. Client chỉ được tạo khi `call_llm()` cần `_get_client()`.

## Biến `__all__`

```python
__all__ = ["call_llm", "reset_client"]
```

`__all__` khai báo public symbols của package khi dùng:

```python
from llm import *
```

Nó cũng là tín hiệu cho người đọc: package `llm` muốn expose chính thức hai API này.

## Ý nghĩa kiến trúc

Khác với `core/__init__.py` và `features/__init__.py`, file này không rỗng. Lý do là package `llm` có một API nhỏ, rõ ràng:

- gọi LLM,
- reset client cho test.

Export ở đây giúp phần còn lại của codebase không cần biết adapter đang nằm ở file nào.

## Quan hệ với file khác

- `llm/adapter.py`: nơi implement thật `call_llm` và `reset_client`.
- `tests/test_llm_adapter.py`: import trực tiếp adapter để kiểm tra `_client`, nhưng app code có thể import từ `llm`.

## Tóm tắt một câu

`llm/__init__.py` là facade package nhỏ, export `call_llm` và `reset_client` như public API chính của lớp LLM adapter.
