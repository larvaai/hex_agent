# Case 01 — Module-Level LLM Client: Singleton khởi tạo lười (lazy)

> **Một client, một kết nối, một điểm truy cập toàn cục — tạo lúc cần, tạo một lần.**

Đây là hiện thân rõ nhất của Singleton trong `hex_agent`: client LLM được giữ
trong một biến mức module (`_client`), khởi tạo lười ở lần gọi đầu tiên, và dùng
chung cho mọi lời gọi trong cả process.

---

## 1. Bối cảnh trong hex_agent

Agent gọi LLM rất nhiều lần trong một phiên chạy (mỗi "bước suy nghĩ" là một lời
gọi). Tạo một `OpenAI()` client là việc **tốn kém**: nó mở kết nối mạng, cấu hình
`base_url`/`api_key`/`timeout`. Nếu mỗi lời gọi LLM lại dùng một client mới thì:
- Lãng phí: mở lại kết nối mạng liên tục.
- Không nhất quán: cấu hình/timeout có thể lệch nhau giữa các client.

Giải pháp trong `hex_agent` (`llm/adapter.py`):
- `_client` là biến **mức module**, khởi tạo `None` (file:line **9**).
- `_get_client()` chỉ tạo `OpenAI()` ở **lần đầu** rồi lưu vào `_client`; các lần
  sau trả ngay object đã có (file:line **25-32**).
- `reset_client()` đặt `_client = None` làm **test seam** (file:line **35-37**).
- `call_llm(..., client=None)` cho phép **inject** client để test, không chạm
  Singleton (file:line **72-90**, điểm chọn client ở **77**).

Test xác nhận ý đồ này: `tests_audit/test_llm_features_rigor.py:62-70` có fixture
`autouse` gọi `adapter.reset_client()` trước/sau mỗi test, và `:78` assert
`adapter._client is None` ngay sau khi reset.

---

## 2. Trích đoạn code thật

`llm/adapter.py:9` — biến giữ instance, mức module:

```python
_client: Any = None
```

`llm/adapter.py:25-32` — điểm truy cập (factory idempotent):

```python
def _get_client() -> Any:
    global _client
    if _client is None:
        from openai import OpenAI  # lazy import

        cfg = _defaults()
        _client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"], timeout=cfg["timeout"])
    return _client
```

`llm/adapter.py:35-37` — test seam (đặt lại về `None`):

```python
def reset_client() -> None:
    global _client
    _client = None
```

`llm/adapter.py:77` — cho phép inject client (không dùng Singleton khi test):

```python
active = client if client is not None else _get_client()
```

`tests_audit/test_llm_features_rigor.py:62-70` — fixture reset Singleton quanh mỗi test:

```python
@pytest.fixture(autouse=True)
def _reset_adapter_singleton():
    """The module-level client cache + sleep are process global; reset around each
    test so lazy-construction assertions are never contaminated by a prior test."""
    adapter.reset_client()
    original_sleep = adapter._sleep
    yield
    adapter._sleep = original_sleep
    adapter.reset_client()
```

---

## 3. Ánh xạ vai trò Singleton <-> code thật

| Vai trò trong Singleton | Thành phần trong hex_agent | File:line |
|---|---|---|
| Biến giữ instance duy nhất (instance holder) | `_client` (mức module, `None` = chưa tạo) | `llm/adapter.py:9` |
| Điểm truy cập toàn cục + factory idempotent | `_get_client()` | `llm/adapter.py:25-32` |
| Lazy init (tạo lúc cần) | `if _client is None: ... OpenAI(...)` | `llm/adapter.py:27-31` |
| "Class private" kiểu Python | module chỉ import 1 lần/process | (cơ chế import) |
| Test seam (xóa state global) | `reset_client()` | `llm/adapter.py:35-37` |
| Lối thoát khỏi Singleton (DI) | tham số `client=` của `call_llm` | `llm/adapter.py:72,77` |
| Bằng chứng test isolation | fixture `_reset_adapter_singleton` + assert `_client is None` | `tests_audit/test_llm_features_rigor.py:62-70,78` |

---

## 4. Bản rút gọn chạy được

File: [`llm_client_lazy_singleton.py`](./llm_client_lazy_singleton.py)

Chạy: `python3 llm_client_lazy_singleton.py`

**Nó mô phỏng gì:**
- Giữ nguyên 4 vai trò Singleton: `_client` (holder), `_get_client()` (access
  point lazy), `reset_client()` (test seam), và `call_llm(client=None)` (DI).
- Bước 0: chứng minh **lazy** — sau import, `_client is None`, chưa mở kết nối.
- Bước 1: ba "module" cùng gọi `_get_client()` -> `assert` cả ba là **cùng một**
  object (`is`), chỉ mở **1** kết nối.
- Bước 3: `reset_client()` -> lần gọi sau tạo **object khác** (chứng minh test
  isolation), giống assert `_client is None` trong test thật.
- Bước 4: inject client -> Singleton **không bị đóng vào** (giống test:82).
- Đối chứng: không dùng Singleton -> ba lời gọi mở ba kết nối khác nhau.

**Nó lược bỏ gì (so với code thật):**
- `OpenAI()` thật thay bằng `FakeOpenAIClient` (chỉ đếm số kết nối, không mạng).
- Bỏ retry/backoff, JSON-mode, downgrade `response_format`, phân loại lỗi
  transient/connection (`llm/adapter.py:40-119`) — không liên quan đến Singleton.
- Không import `openai`, không import `hex_agent`; chỉ dùng thư viện chuẩn.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Singleton chống lại unit test.** Vì `_client` là global state, nếu không có
  `reset_client()` thì test trước sẽ "lây nhiễm" test sau. Cái giá phải trả là
  luôn kèm một test seam + fixture reset.
- **Coupling ngầm.** Mọi nơi gọi `_get_client()` đều phụ thuộc ngầm vào state
  module. `hex_agent` giảm đau bằng lối thoát DI (`client=` của `call_llm`).
- **Không thread-safe.** Hai thread cùng thấy `_client is None` có thể tạo hai
  client. `hex_agent` chấp nhận vì model "process-per-session". Nếu bạn cần dùng
  đa luồng thật sự, phải thêm `Lock` (xem `01_Singleton.md`, mục thread safety).
- **Khi nào dùng DI thay vì Singleton:** nếu bạn chỉ muốn "dễ truy cập" chứ đối
  tượng không thực sự duy nhất trong domain -> dùng Dependency Injection.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao gọi `_get_client()` ba lần chỉ mở **một** kết nối, nhưng sau khi gọi
   `reset_client()` thì lần gọi tiếp theo lại mở kết nối **mới**?
2. Khi truyền `client=fake` vào `call_llm`, tại sao `_client` của module vẫn phải
   là `None`? Điều này giúp test ở chỗ nào?
3. Nếu hex_agent chuyển sang model đa luồng (nhiều thread cùng gọi LLM), `_get_client()`
   hiện tại sai ở đâu, và bạn sẽ sửa bằng cơ chế gì?
