# CATALOG — Singleton trong hex_agent (vết cản mọi occurrence)

Bảng này liệt kê **mọi** vị trí liên quan đến Singleton (hoặc cần làm rõ là
**KHÔNG** phải Singleton) trong codebase `hex_agent`, lấy từ bước discover.
Mọi `path:line` đã được mở lại và xác nhận khớp với file thật.

| path:line | Mô tả | Độ rõ |
|---|---|---|
| `llm/adapter.py:9` | `_client: Any = None` — biến mức module giữ instance Singleton (instance holder). | high |
| `llm/adapter.py:25-32` | `_get_client()` — điểm truy cập toàn cục, factory idempotent (lazy init). `if _client is None` (27) rồi `_client = OpenAI(...)` (31). | high |
| `llm/adapter.py:26` | `global _client` bên trong `_get_client()` để kiểm tra/điền Singleton. | high |
| `llm/adapter.py:35-37` | `reset_client()` — đặt `_client = None` cho test/reset scenario (test seam). | high |
| `llm/adapter.py:72,77` | `call_llm(..., client=None)` và `active = client if client is not None else _get_client()` — lối thoát DI, cho phép bỏ qua Singleton khi test. | high |
| `harness/hooks/hook_runtime.py:162` | `_config_cache = None  # module-level; None = not yet loaded` — instance holder của config cache. | high |
| `harness/hooks/hook_runtime.py:172-191` | `_load_config()` — loader idempotent + access point. Lazy-load YAML 1 lần, cache lại. | high |
| `harness/hooks/hook_runtime.py:176` | `global _config_cache` bên trong `_load_config()` để cập nhật cache mức module. | high |
| `harness/hooks/hook_runtime.py:177` | `if _config_cache is not None: return _config_cache` — kiểm tra "đã nạp chưa". | high |
| `harness/hooks/hook_runtime.py:187-190` | `except -> log + cfg = {}` rồi `_config_cache = cfg` — config hỏng trả `{}`, không ném lỗi (robust). | high |
| `harness/hooks/hook_runtime.py:194-197` | `_reset_config_cache()` (với `global _config_cache` ở 196) — test seam reset cache. | high |
| `tests_audit/test_llm_features_rigor.py:62-70` | Fixture `autouse` `_reset_adapter_singleton()` — setup/teardown để cô lập state Singleton quanh mỗi test. | high |
| `tests_audit/test_llm_features_rigor.py:78` | `assert adapter._client is None` — xác nhận test isolation hoạt động sau reset. | high |
| `observability/event_log.py:15` | `_INDEX_LOCK = threading.RLock()` — khóa mức module cho truy cập an toàn đa luồng vào index. **KHÔNG** phải Singleton, nhưng minh họa quan tâm về tài nguyên chia sẻ mà Singleton phải xử lý. | medium |
| `observability/event_log.py:44` | `self._lock = threading.RLock()` — khóa per-instance trong `EventLogger`. `EventLogger` được tạo mới mỗi run -> **KHÔNG** phải Singleton; đưa vào đây để phân biệt rõ. | medium |

## Ghi chú phân loại

- **Là Singleton (module-level, Pythonic):** `llm/adapter.py` (`_client`) và
  `harness/hooks/hook_runtime.py` (`_config_cache`). Cả hai dùng đúng khuôn mẫu
  "biến mức module + lazy init + idempotent access + test seam", không override
  `__new__`, không dùng metaclass — vì module Python vốn đã là Singleton (chỉ
  import 1 lần/process). Lưu ý: đây là cách diễn giải Singleton hơi rộng so với
  GoF cổ điển (class tự kiểm soát instance qua `__new__`/metaclass), nhưng là hiện
  thực hợp lệ và Pythonic — tài liệu trung thực nói rõ codebase không dùng
  `__new__`/metaclass.
- **KHÔNG phải Singleton (đưa vào để tránh nhầm):** `observability/event_log.py`.
  `EventLogger` được khởi tạo **mới mỗi run** (per-instance), `self._lock` là khóa
  riêng của từng instance. Đây là vấn đề "tài nguyên chia sẻ an toàn đa luồng" —
  một mối quan tâm mà Singleton **cũng** phải giải quyết (xem thread-safety trong
  `01_Singleton.md`), nhưng bản thân nó không phải Singleton.

## Các flagship được dùng làm case con

| # | Case | Nguồn chính |
|---|---|---|
| 01 | [`01_llm_client_lazy_singleton`](./01_llm_client_lazy_singleton/) | `llm/adapter.py:9,25-32,35-37,72-90` |
| 02 | [`02_hook_config_module_cache`](./02_hook_config_module_cache/) | `harness/hooks/hook_runtime.py:162,172-197` |
