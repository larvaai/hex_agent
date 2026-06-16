# Giải thích `tests/test_llm_adapter.py`

File `tests/test_llm_adapter.py` kiểm tra `llm/adapter.py`: lazy client, injected client, JSON mode, tắt JSON mode, và error fallback dạng structured final JSON.

Nói ngắn gọn: test này đảm bảo LLM adapter test được offline và không phá agent loop khi request lỗi.

## Import

```python
import llm.adapter as adapter
from discipline import parse_action
```

Test import trực tiếp `llm.adapter` thay vì `from llm import ...` vì cần kiểm tra biến nội bộ `adapter._client`.

`parse_action` dùng để xác nhận error fallback từ adapter vẫn là JSON action parse được.

## Class `_FakeChoiceMsg`

```python
class _FakeChoiceMsg:
    def __init__(self, content: str) -> None:
        self.message = type("M", (), {"content": content})()
```

Fake object mô phỏng một choice trong response của OpenAI chat completions.

Nó tạo object có shape:

```python
choice.message.content
```

đúng với code trong adapter:

```python
response.choices[0].message.content
```

## Class `_FakeClient`

```python
class _FakeClient:
```

Fake client mô phỏng API:

```python
client.chat.completions.create(**kwargs)
```

Mục tiêu:

- không gọi network,
- kiểm tra kwargs adapter gửi,
- mô phỏng lỗi khi cần.

### Constructor

```python
def __init__(self, content: str = '{"action":"final","message":"ok"}', boom: bool = False) -> None:
    self.content = content
    self.boom = boom
    self.kwargs: dict | None = None
```

- `content`: nội dung fake response.
- `boom`: nếu True thì fake client raise lỗi.
- `kwargs`: lưu lại kwargs adapter gửi vào `create()`.

### Nested class `_Completions`

```python
class _Completions:
    def create(self, **kwargs):
        outer.kwargs = kwargs
        if outer.boom:
            raise RuntimeError("boom")
        return type("R", (), {"choices": [_FakeChoiceMsg(outer.content)]})()
```

Mô phỏng method `create`.

Nếu `boom=True`, raise `RuntimeError`.

Nếu không, trả object có:

```python
response.choices[0].message.content
```

### Shape client

```python
self.chat = type("C", (), {"completions": _Completions()})()
```

Tạo object có `chat.completions`.

## `test_module_import_is_lazy`

```python
def test_module_import_is_lazy():
    adapter.reset_client()
    assert adapter._client is None
```

Kiểm tra reset client đưa cache về `None`.

Hợp đồng rộng hơn: chỉ import module và dùng helper không được tự tạo OpenAI client.

Nếu test này đỏ, adapter có thể đang init client quá sớm.

## `test_injected_client_json_mode`

```python
def test_injected_client_json_mode():
    fake = _FakeClient()
    out = adapter.call_llm([{"role": "user", "content": "hi"}], model="m1", client=fake)
    assert out == '{"action":"final","message":"ok"}'
    assert fake.kwargs["response_format"] == {"type": "json_object"}
    assert fake.kwargs["model"] == "m1"
    assert adapter._client is None
```

Kiểm tra nhiều hợp đồng cùng lúc:

- injected client được dùng,
- output trả đúng content fake,
- JSON mode bật mặc định,
- model override `"m1"` được dùng,
- dùng injected client không populate module cache `_client`.

Điểm cuối rất quan trọng cho test offline: fake client không được làm adapter tạo OpenAI client thật.

## `test_json_mode_off`

```python
def test_json_mode_off():
    fake = _FakeClient()
    adapter.call_llm([{"role": "user", "content": "hi"}], json_mode=False, client=fake)
    assert "response_format" not in fake.kwargs
```

Kiểm tra khi `json_mode=False`, adapter không gửi `response_format`.

Hợp đồng: caller có thể tắt JSON mode nếu cần.

## `test_error_returns_structured_final`

```python
def test_error_returns_structured_final():
    fake = _FakeClient(boom=True)
    action = parse_action(adapter.call_llm([{"role": "user", "content": "hi"}], client=fake))
    assert action["action"] == "final"
    assert action["finish_reason"] == "error"
```

Fake client raise lỗi. Adapter không được raise lỗi ra ngoài. Nó phải trả JSON string có:

```json
{"action": "final", "finish_reason": "error", ...}
```

Test dùng `parse_action()` để xác nhận string đó parse được như action object.

Hợp đồng: lỗi LLM request được biến thành structured final, giúp agent loop xử lý an toàn.

## Nếu file test này đỏ nghĩa là gì?

- Adapter có thể import/init OpenAI client quá sớm.
- Injected client có thể không hoạt động.
- JSON mode có thể không được bật mặc định.
- Tắt JSON mode có thể vẫn gửi `response_format`.
- Lỗi LLM có thể làm crash loop thay vì trả action final/error.

## Tóm tắt một câu

`tests/test_llm_adapter.py` bảo vệ thiết kế LLM adapter: lazy, offline-testable, JSON-mode mặc định và fail-safe bằng structured final JSON khi request lỗi.
