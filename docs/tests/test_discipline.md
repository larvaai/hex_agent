# Giải thích `tests/test_discipline.py`

File `tests/test_discipline.py` kiểm tra các hợp đồng của package `discipline`: JSON gate, condense, finish gate và budget.

Nói ngắn gọn: test này đảm bảo lớp output discipline đủ chắc để dùng trong agent loop.

## Import

```python
import pytest

from discipline import Budget, JsonGateError, check_finish, condense, parse_action
```

Test import từ facade `discipline/__init__.py`, không import từng module con. Điều này cũng kiểm tra public API của package đang export đúng các symbol cần dùng.

`pytest` dùng cho `pytest.raises`.

## Nhóm test `parse_action`

### `test_parse_clean`

```python
def test_parse_clean():
    assert parse_action('{"action": "tool", "tool": "echo", "args": {}}')["action"] == "tool"
```

Kiểm tra JSON action sạch được parse đúng.

Hợp đồng: output LLM dạng JSON object chuẩn phải parse được và giữ field `action`.

### `test_parse_repairs_fences_and_trailing_comma`

```python
def test_parse_repairs_fences_and_trailing_comma():
    assert parse_action('```json\n{"action": "final", "message": "ok",}\n```')["action"] == "final"
```

Kiểm tra hai cơ chế repair:

- bỏ markdown fence ` ```json `,
- xóa trailing comma trước `}`.

Hợp đồng: model lỡ bọc JSON trong markdown hoặc thêm comma cuối vẫn được chấp nhận.

### `test_parse_extracts_embedded_object`

```python
def test_parse_extracts_embedded_object():
    assert parse_action('action: {"action":"final","message":"x"} thanks')["action"] == "final"
```

Kiểm tra JSON object nằm lẫn trong prose vẫn được trích ra.

Hợp đồng: parser có thể cứu output không hoàn toàn thuần JSON nếu trong đó có một object hợp lệ.

### `test_missing_action_raises`

```python
def test_missing_action_raises():
    with pytest.raises(JsonGateError) as ei:
        parse_action('{"tool": "echo"}')
    assert ei.value.stage == "schema"
```

JSON parse được nhưng thiếu field `action`.

Hợp đồng:

- thiếu `action` phải raise `JsonGateError`,
- lỗi phải ở stage `"schema"`, không phải `"parse"`.

Điều này giúp agent loop biết lỗi do object sai schema.

### `test_garbage_raises`

```python
def test_garbage_raises():
    with pytest.raises(JsonGateError):
        parse_action("not json at all")
```

Text không có JSON object phải fail.

Hợp đồng: JSON gate không được nhận bừa mọi output.

## Nhóm test `condense`

### `test_condense_truncates`

```python
def test_condense_truncates():
    out = condense({"text": "x" * 5000}, max_chars=100)
    assert len(out["text"]) < 200
    assert "+4900" in out["text"]
```

Kiểm tra string dài bị cắt và marker cho biết số ký tự bị lược bỏ.

Hợp đồng:

- string dài không được giữ nguyên,
- output phải nói rõ phần bị cắt.

### `test_condense_lists`

```python
def test_condense_lists():
    out = condense({"items": list(range(50))}, max_list=5)
    assert len(out["items"]) == 6
```

List 50 item với `max_list=5` sẽ còn:

- 5 item đầu,
- 1 marker `"... [+45 items]"`.

Hợp đồng: list dài bị giới hạn nhưng vẫn có marker phần bị lược bỏ.

## Nhóm test `finish_gate`

### `test_finish_gate_blocks_unvalidated_code`

```python
def test_finish_gate_blocks_unvalidated_code():
    res = check_finish({"code_changed": True, "validation_passed": False}, finish_reason="validated")
    assert res["allowed"] is False
```

Nếu code đã thay đổi nhưng validation chưa pass, final bị chặn.

Hợp đồng: agent không được kết thúc như đã validated khi chưa có validation pass.

### `test_finish_gate_allows_blocker`

```python
def test_finish_gate_allows_blocker():
    assert check_finish({"code_changed": True, "validation_passed": False}, finish_reason="blocker")["allowed"]
```

Nếu agent khai báo blocker, finish được phép dù chưa validation pass.

Hợp đồng: có đường thoát hợp lệ khi agent thật sự bị chặn.

### `test_finish_gate_allows_validated`

```python
def test_finish_gate_allows_validated():
    assert check_finish({"code_changed": True, "validation_passed": True})["allowed"]
```

Nếu code thay đổi và validation đã pass, final được phép.

## Nhóm test `Budget`

### `test_budget_parse_does_not_consume_steps`

```python
def test_budget_parse_does_not_consume_steps():
    b = Budget(max_steps=3, max_parse_errors=2)
    b.record_parse_error()
    b.record_parse_error()
    assert b.parse_exceeded() is True
    assert b.steps == 0
```

Kiểm tra parse error budget riêng với step budget.

Hợp đồng:

- parse error tăng `parse_errors`,
- không tăng `steps`,
- đến `max_parse_errors` thì exceeded.

### `test_budget_same_tool`

```python
def test_budget_same_tool():
    b = Budget(max_same_tool_calls=2)
    key = Budget.tool_key("echo", {"a": 1})
    for _ in range(3):
        b.record_tool_call(key)
    assert b.same_tool_exceeded(key) is True
```

Kiểm tra giới hạn lặp cùng tool call.

Với max là 2, gọi lần thứ 3 thì exceeded.

## Nếu file test này đỏ nghĩa là gì?

- JSON gate có thể nhận output sai hoặc không repair được output phổ biến.
- Condense có thể feed dữ liệu quá lớn vào LLM.
- Finish gate có thể cho agent kết thúc khi chưa validate.
- Budget có thể để loop chạy quá lâu hoặc đếm sai loại lỗi.

## Tóm tắt một câu

`tests/test_discipline.py` là hợp đồng sống cho lớp output discipline, đảm bảo parse JSON, rút gọn context, chặn final thiếu validation và kiểm soát loop budget hoạt động đúng.
