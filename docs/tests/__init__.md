# Giải thích `tests/__init__.py`

File `tests/__init__.py` hiện tại đang rỗng.

Nó đánh dấu thư mục `tests/` là một Python package truyền thống. Với pytest hiện tại, file này không bắt buộc trong mọi trường hợp, nhưng nó vẫn giúp import/package behavior rõ ràng hơn.

## Vai trò trong package test

Cấu trúc:

```text
tests/
  __init__.py
  test_discipline.py
  test_kernel.py
  test_llm_adapter.py
  test_observability.py
```

`pyproject.toml` cấu hình:

```toml
[tool.pytest.ini_options]
addopts = "-q -p no:cacheprovider"
testpaths = ["tests"]
```

Pytest sẽ tìm test trong thư mục `tests`.

## Vì sao file rỗng vẫn hợp lý?

Một `__init__.py` rỗng:

- không tạo side effect khi pytest import package,
- không expose helper test chung chưa cần,
- giữ package marker đơn giản.

Nếu sau này có fixture dùng chung, thường nên đặt trong `tests/conftest.py` thay vì `tests/__init__.py`.

## Tóm tắt một câu

`tests/__init__.py` là package marker rỗng cho thư mục test, hiện không chứa logic nhưng giữ cấu trúc package rõ ràng.
