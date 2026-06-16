# Giải thích `discipline/__init__.py`

File `discipline/__init__.py` định nghĩa public API cấp package cho lớp output discipline.

Nó gom các function/class quan trọng từ các module con để caller có thể import ngắn:

```python
from discipline import Budget, parse_action, check_finish, condense
```

thay vì import từ từng file riêng.

## Vai trò trong package

Package `discipline` gồm:

- `budget.py`: giới hạn vòng lặp.
- `condense.py`: rút gọn tool result.
- `finish_gate.py`: chặn final khi chưa validate.
- `json_gate.py`: parse output LLM thành JSON action.

`__init__.py` đóng vai trò facade cho các API chính.

## Các import

```python
from discipline.budget import Budget
from discipline.condense import condense
from discipline.finish_gate import check_finish, has_passing_validation, requires_validation
from discipline.json_gate import JsonGateError, build_retry_message, parse_action
```

Các symbol được export:

- `Budget`: budget control cho loop.
- `condense`: rút gọn dữ liệu.
- `check_finish`: kiểm tra final có được phép không.
- `has_passing_validation`: helper kiểm tra validation pass.
- `requires_validation`: helper kiểm tra có cần validate không.
- `JsonGateError`: exception cho JSON gate.
- `build_retry_message`: tạo message retry cho model.
- `parse_action`: parse output LLM thành action dict.

## Biến `__all__`

```python
__all__ = [
    "Budget",
    "condense",
    "check_finish",
    "has_passing_validation",
    "requires_validation",
    "JsonGateError",
    "build_retry_message",
    "parse_action",
]
```

`__all__` khai báo public API khi dùng:

```python
from discipline import *
```

Nó cũng giúp người đọc biết package này muốn expose chính thức những gì.

## Vì sao cần facade?

### 1. Import ngắn hơn

Test có thể viết:

```python
from discipline import Budget, JsonGateError, check_finish, condense, parse_action
```

### 2. Tách module nội bộ khỏi API dùng ngoài

Caller không cần biết `parse_action` nằm ở `json_gate.py` hay `check_finish` nằm ở `finish_gate.py`.

### 3. Dễ kiểm soát public surface

Nếu thêm helper nội bộ trong module con nhưng không muốn public, chỉ cần không đưa vào `__all__`.

## Quan hệ với file khác

- `tests/test_discipline.py`: import API từ package `discipline`.
- `tests/test_llm_adapter.py`: import `parse_action` từ package.
- Agent loop tương lai nên ưu tiên import từ `discipline` thay vì từng module con nếu dùng API public.

## Tóm tắt một câu

`discipline/__init__.py` là facade public API cho lớp output discipline, gom budget, condense, finish gate và JSON gate vào một import surface gọn.
