# Giải thích `tests/test_kernel.py`

File `tests/test_kernel.py` kiểm tra các hợp đồng chính của kernel và registry: nạp feature, gọi tool, fallback khi thiếu tool, event emission, introspection capability và config mặc định.

Nói ngắn gọn: test này đảm bảo lõi agent chạy được mà không cần LLM/network.

## Import và config test

```python
from core.bootstrap import build_kernel, create_kernel
```

Test dùng:

- `build_kernel(config)`: build kernel từ dict config trực tiếp.
- `create_kernel()`: build kernel từ config mặc định `config/features.yaml`.

```python
ECHO = {"features": {"example_echo": {"enabled": True, "module": "features.example_echo"}}}
DISABLED = {"features": {"example_echo": {"enabled": False, "module": "features.example_echo"}}}
```

Hai config này đại diện cho:

- feature echo bật,
- feature echo tắt.

## `test_execute_registered_tool`

```python
def test_execute_registered_tool():
    k = build_kernel(ECHO)
    r = k.execute_tool("echo", {"msg": "hi"})
    assert r["ok"] is True
    assert r["capability"] == "echo"
    assert r["feature"] == "example_echo"
    assert r["data"]["echo"] == {"msg": "hi"}
```

Kiểm tra happy path:

1. build kernel với feature `example_echo`,
2. gọi tool `echo`,
3. kết quả thành công,
4. result được wrap thành `CapabilityResult` đúng.

Hợp đồng: feature enabled phải đăng ký tool, kernel phải execute được và envelope phải có capability/feature/data đúng.

## `test_unknown_tool_null_fallback`

```python
def test_unknown_tool_null_fallback():
    k = build_kernel(ECHO)
    r = k.execute_tool("nope")
    assert r["ok"] is False
    assert r["data"].get("missing_capability") is True
```

Gọi tool không tồn tại.

Hợp đồng:

- kernel không crash,
- registry dùng `NullToolPort`,
- result là failure có cấu trúc,
- `missing_capability=True` nằm trong `data`.

## `test_disabled_feature_not_registered`

```python
def test_disabled_feature_not_registered():
    k = build_kernel(DISABLED)
    assert k.registry.has_tool("echo") is False
    r = k.execute_tool("echo")
    assert r["ok"] is False
    assert r["data"].get("missing_capability") is True
```

Feature có trong config nhưng `enabled=False`.

Hợp đồng:

- feature disabled không được install,
- tool `echo` không được đăng ký,
- gọi `echo` khi disabled phải đi qua missing capability fallback.

## `test_events_emitted`

```python
def test_events_emitted():
    k = build_kernel(ECHO)
    seen: list[str] = []
    k.events.subscribe(lambda topic, payload: seen.append(topic))
    k.execute_tool("echo", {"a": 1})
    assert "tool.requested" in seen
    assert "tool.completed" in seen
```

Kiểm tra kernel publish event khi gọi tool.

Hợp đồng:

- trước khi chạy tool phải có `tool.requested`,
- sau khi thành công phải có `tool.completed`,
- EventBus subscribe hoạt động.

## `test_describe_capabilities`

```python
def test_describe_capabilities():
    k = build_kernel(ECHO)
    desc = k.describe_capabilities()
    assert "echo" in [t["name"] for t in desc["tools"]]
    assert any(f["name"] == "example_echo" for f in desc["features"])
```

Kiểm tra introspection API.

Hợp đồng:

- `describe_capabilities()` trả danh sách tool,
- trả danh sách feature,
- `echo` và `example_echo` xuất hiện khi feature enabled.

## `test_default_config_loads`

```python
def test_default_config_loads():
    k = create_kernel()
    assert k.registry.has_tool("echo")
```

Kiểm tra config mặc định trong `config/features.yaml`.

Hợp đồng: gọi `create_kernel()` không truyền config phải nạp feature `example_echo`, nên registry có tool `echo`.

## Nếu file test này đỏ nghĩa là gì?

- Bootstrap không nạp config/feature đúng.
- Registry không resolve tool đúng.
- Kernel không normalize result đúng.
- Missing tool có thể làm crash hoặc trả sai shape.
- EventBus không phát event tool lifecycle.
- Config mặc định không còn bật echo như kỳ vọng.

## Tóm tắt một câu

`tests/test_kernel.py` bảo vệ hợp đồng nền tảng của core agent: kernel build được, feature nạp được, tool chạy được, missing tool an toàn, event phát ra và capability introspection chính xác.
