# Giải thích `features/__init__.py`

File `features/__init__.py` hiện tại đang rỗng.

Dù không có code, file này đánh dấu thư mục `features/` là một Python package, giúp các module feature import được bằng đường dẫn như `features.example_echo`.

## Vai trò trong package

Cấu trúc hiện tại:

```text
features/
  __init__.py
  loader.py
  example_echo.py
```

Nhờ có package `features`, config có thể khai báo:

```yaml
features:
  example_echo:
    enabled: true
    module: features.example_echo
```

Sau đó `features.loader` có thể chạy:

```python
importlib.import_module("features.example_echo")
```

## Vì sao file rỗng vẫn hợp lý?

Package `features` hiện chưa cần public API cấp package.

Caller không cần:

```python
from features import example_echo
```

Thay vào đó, feature được nạp động bằng module path trong config.

Để `__init__.py` rỗng giúp tránh side effect khi import package `features`.

## Có nên export gì ở đây không?

Hiện tại chưa cần.

Nếu sau này muốn expose helper cấp package, có thể thêm:

```python
from features.loader import install_configured_features

__all__ = ["install_configured_features"]
```

Nhưng điều đó làm `features` import `loader` ngay khi package được import. Với plugin system, tránh import sớm thường là lựa chọn sạch hơn.

## Ý nghĩa kiến trúc

`features/__init__.py` rỗng giữ package nhẹ và không tự kích hoạt feature nào.

Feature chỉ được nạp khi:

1. config bật feature,
2. loader import module cụ thể,
3. module có `install(kernel)`.

Điều này giúp runtime kiểm soát rõ feature nào được cài.

## Tóm tắt một câu

`features/__init__.py` là package marker rỗng, cho phép dynamic import các feature module mà không tạo side effect ở cấp package.
