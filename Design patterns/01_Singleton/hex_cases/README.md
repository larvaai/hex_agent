# Singleton trong hex_agent — Tổng quan các case thực tế

> **Một instance, một điểm truy cập toàn cục** — nhưng trong `hex_agent`, Singleton
> không mang hình class với `__new__`, mà mang hình **Pythonic nhất**: biến mức
> module khởi tạo lười (lazy), dùng chung suốt vòng đời process.

Tài liệu này tách từ bài học gốc [`../01_Singleton.md`](../01_Singleton.md) và soi
chiếu xuống **code thật** trong codebase `hex_agent`. Mọi `path:line` ở đây đều đã
được mở lại và xác nhận khớp với file gốc.

---

## Singleton xuất hiện ở đâu trong hex_agent?

Singleton trong `hex_agent` xuất hiện dưới dạng **cache khởi tạo lười mức module**
và **tài nguyên toàn cục**. Hai biểu hiện chính:

1. **Client LLM** (`llm/adapter.py`): biến mức module `_client` khởi tạo `None`,
   tạo thật sự ở lần gọi đầu tiên qua `_get_client()`. Có `reset_client()` làm
   test seam.
2. **Cache cấu hình hook** (`harness/hooks/hook_runtime.py`): biến `_config_cache`
   nạp YAML đúng một lần, dùng chung cho mọi lời gọi hook. Có `_reset_config_cache()`
   làm test seam.

Đây là dạng Singleton **Pythonic nhất**: tận dụng cơ chế import của Python (module
chỉ import 1 lần mỗi process) để đảm bảo "một instance" mà **không** cần override
`__new__` hay dùng metaclass. Phù hợp với ràng buộc "một instance, truy cập toàn
cục" cho các tài nguyên phải nhất quán trong hệ thống: kết nối LLM, trạng thái
cấu hình.

> **Lưu ý về cách diễn giải:** "cache khởi tạo lười mức module" là một cách hiện
> thực Singleton hợp lệ và rất Pythonic, nhưng hơi rộng so với GoF Singleton cổ
> điển (một class tự kiểm soát instance duy nhất qua `__new__`/metaclass). Tài
> liệu này chủ động nói rõ codebase **không** dùng `__new__`/metaclass, và phân
> biệt rạch ròi với `EventLogger` (xem dưới) để tránh "gượng ép" pattern.

Một điểm đáng chú ý: `observability/event_log.py` có `threading.RLock()` cho an
toàn đa luồng — nhưng `EventLogger` được tạo **mới mỗi run** nên **KHÔNG** phải
Singleton. Nó được liệt kê trong [CATALOG](./CATALOG.md) để phân biệt rõ: "tài
nguyên chia sẻ an toàn đa luồng" là mối quan tâm mà Singleton **cũng** phải xử lý,
nhưng bản thân `EventLogger` không phải Singleton.

---

## Các case con

| # | Case | Biểu hiện | Nguồn thật |
|---|---|---|---|
| 01 | [**Module-Level LLM Client — Lazy Init**](./01_llm_client_lazy_singleton/) | `_client` mức module, lazy + memoize, có `reset_client()` test seam và lối thoát DI. | `llm/adapter.py:9,25-32,35-37,72-90` |
| 02 | [**Hook Runtime Config — Module Cache**](./02_hook_config_module_cache/) | `_config_cache` nạp YAML 1 lần/process, robust `{}`-on-error, có `_reset_config_cache()`. | `harness/hooks/hook_runtime.py:162,172-197` |

Mỗi case có:
- `README.md` — bài học đầy đủ 6 mục (bối cảnh thật, trích code thật, bảng ánh xạ
  vai trò, bản rút gọn, cái giá, câu hỏi tự kiểm tra).
- `<name>.py` — bản distill **chạy được**, chỉ dùng thư viện chuẩn, có `demo()`,
  narration tiếng Việt, đối chứng "không dùng pattern", và `assert` chứng minh
  bất biến.

Xem **[CATALOG.md](./CATALOG.md)** để có bảng vết cản mọi occurrence của Singleton
(và các điểm "không phải Singleton") trong codebase.

---

## Bài học cốt lõi (rút từ code thật)

1. **Module Python đã là Singleton.** Không cần `_instance` class hay `__new__` —
   biến mức module bền vững qua mọi lời gọi vì module chỉ import 1 lần/process.
2. **Lazy init là bạn của hiệu năng.** Cả `_client` và `_config_cache` đều khởi
   tạo `None` và chỉ tạo thật sự ở lần đầu dùng -> không tốn tài nguyên lúc import.
3. **Singleton là kẻ thù của unit test — phải có test seam.** Cả hai nơi đều kèm
   hàm reset (`reset_client`, `_reset_config_cache`) và có fixture/test sử dụng nó
   (`tests_audit/test_llm_features_rigor.py:62-70,78`). Đây là cái giá bắt buộc.
4. **Ranh giới Singleton phải vững khi có lỗi.** `_load_config()` trả `{}` + log
   thay vì ném exception khi YAML hỏng (`hook_runtime.py:187-189`).
5. **Luôn để sẵn lối thoát DI.** `call_llm(client=...)` cho phép bỏ qua Singleton —
   chính là gợi ý "dùng Dependency Injection thay vì Singleton" trong bài gốc.

---

## Cách chạy

```bash
python3 01_llm_client_lazy_singleton/llm_client_lazy_singleton.py
python3 02_hook_config_module_cache/hook_config_module_cache.py
```

Cả hai thoát code 0, in narration từng bước và các dòng `assert PASS`.
