# Giải thích `toolbox/__init__.py`

File `toolbox/__init__.py` hiện tại đang rỗng.

Nó đánh dấu thư mục `toolbox/` là Python package để các module như `toolbox.feature`, `toolbox.filesystem`, `toolbox.terminal` import được.

## Vai trò

Toolbox được nạp qua config:

```yaml
toolbox:
  enabled: true
  module: toolbox.feature
```

Feature loader sẽ import `toolbox.feature` trực tiếp. Package `toolbox` không cần export API cấp package, nên `__init__.py` để rỗng là hợp lý và tránh side effect.

## Tóm tắt

`toolbox/__init__.py` là package marker rỗng cho toolbox feature, không tự đăng ký tool và không tạo side effect khi import package.
