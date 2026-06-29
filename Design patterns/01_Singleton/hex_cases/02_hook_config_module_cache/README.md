# Case 02 — Hook Runtime Config: Singleton cache mức module (lazy + memoize)

> **Một lần đọc cấu hình, dùng lại cho mọi hook — None nghĩa là "chưa nạp".**

Đây là dạng Singleton "Pythonic nhất": cache cấu hình trong một biến mức module
(`_config_cache`), nạp lười ở lần đầu, và dùng chung cho mọi lần hook được gọi
trong cả process — không cần override `__new__`, không cần class.

---

## 1. Bối cảnh trong hex_agent

Hệ thống hook (`telemetry`, `nudge`, `compliance`) được gọi **rất nhiều lần**
trong vòng đời một process. Mỗi hook cần đọc cấu hình từ file YAML. Nếu **mỗi lần**
gọi hook đều mở file + parse YAML lại thì vừa chậm (I/O đĩa) vừa lãng phí.

Giải pháp trong `hex_agent` (`harness/hooks/hook_runtime.py`):
- `_config_cache` là biến **mức module**, khởi tạo `None`, kèm comment rõ ý đồ
  `# module-level; None = not yet loaded` (file:line **162**).
- `_load_config()` kiểm tra `if _config_cache is not None: return _config_cache`
  -> trả cache ngay; nếu chưa có thì đọc YAML **đúng một lần** rồi cache lại
  (file:line **172-191**).
- Cấu hình **hỏng/thiếu** (YAML lỗi, thiếu PyYAML) -> trả `{}` + ghi crash-log,
  **không ném exception** (file:line **187-189**). Ranh giới Singleton phải vững:
  config xấu không được làm sập một hook.
- `_reset_config_cache()` là **test seam** để đọc lại file mới (file:line **194-197**).

---

## 2. Trích đoạn code thật

`harness/hooks/hook_runtime.py:162` — biến giữ cache, mức module:

```python
_config_cache = None  # module-level; None = not yet loaded
```

`harness/hooks/hook_runtime.py:172-197` — loader idempotent + xử lý lỗi + test seam:

```python
def _load_config() -> dict:
    """Parse the config once per process. Malformed/unreadable/missing-PyYAML
    ⇒ {} (every hook then falls to its per-class default) + a crash-log line.
    The lazy yaml import keeps telemetry/nudge importable without PyYAML."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    cfg = {}
    try:
        p = _config_path()
        if p.is_file():
            import yaml  # lazy: missing dep degrades to class defaults here
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("hooks"), dict):
                cfg = raw["hooks"]
    except Exception as e:  # noqa: BLE001 — malformed config must never crash a hook
        log_hook_error("hook_runtime", e)
        cfg = {}
    _config_cache = cfg
    return cfg


def _reset_config_cache() -> None:
    """Test seam: drop the per-process config cache so a fresh file is re-read."""
    global _config_cache
    _config_cache = None
```

---

## 3. Ánh xạ vai trò Singleton <-> code thật

| Vai trò trong Singleton | Thành phần trong hex_agent | File:line |
|---|---|---|
| Biến giữ instance duy nhất (instance holder) | `_config_cache` (mức module, `None` = chưa nạp) | `hook_runtime.py:162` |
| Điểm truy cập + loader idempotent | `_load_config()` | `hook_runtime.py:172-191` |
| Kiểm tra "đã có instance?" | `if _config_cache is not None: return _config_cache` | `hook_runtime.py:177` |
| Lazy load (nạp lúc cần) | đọc YAML chỉ khi cache rỗng | `hook_runtime.py:182-186` |
| Ranh giới lỗi vững chắc | `except -> {} + log`, không ném | `hook_runtime.py:187-189` |
| Lưu cache (memoize) | `_config_cache = cfg` | `hook_runtime.py:190` |
| Test seam (xóa state global) | `_reset_config_cache()` | `hook_runtime.py:194-197` |

---

## 4. Bản rút gọn chạy được

File: [`hook_config_module_cache.py`](./hook_config_module_cache.py)

Chạy: `python3 hook_config_module_cache.py`

**Nó mô phỏng gì:**
- Giữ nguyên vai trò: `_config_cache` (holder), `_load_config()` (loader lazy +
  memoize), `_reset_config_cache()` (test seam), và nhánh `except -> {}` (robust).
- Bước 1: ba hook cùng gọi `_load_config()` -> `assert read_count == 1`
  (chỉ parse YAML **một** lần) dù gọi ba lần.
- Bước 2: `_reset_config_cache()` -> lần gọi sau đọc lại file (`read_count == 2`).
- Bước 3: nguồn config **hỏng** -> `_load_config()` trả `{}` + ghi 1 dòng log,
  **không ném exception** (chứng minh ranh giới Singleton vững).
- Đối chứng: không cache -> 100 hook = 100 lần parse YAML (lãng phí I/O).

**Nó lược bỏ gì (so với code thật):**
- File YAML thật + `yaml.safe_load` thay bằng `FakeConfigSource` (chỉ đếm
  `read_count`, và có thể đặt `corrupt=True` để mô phỏng YAML hỏng).
- Bỏ `_config_path()` / `HARNESS_HOOK_CONFIG` / resolve off `__file__`
  (`hook_runtime.py:165-169`) — không liên quan đến vai trò Singleton.
- Bỏ cấu trúc `raw["hooks"]` và `_CLASS_DEFAULTS` (`hook_runtime.py:156-160,185-186`).
- Không import `yaml`, không import `hex_agent`; chỉ dùng thư viện chuẩn.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **State global = khó test.** Cache sống suốt vòng đời process; phải có
  `_reset_config_cache()` thì test mới có thể nạp config khác nhau cho từng case.
- **Hot-reload khó.** Đã cache 1 lần/process thì nếu file YAML đổi lúc runtime,
  process không tự thấy — phù hợp với hook (process ngắn), nhưng **không** phù
  hợp nếu bạn cần config thay đổi nóng (lúc đó dùng file-watcher / TTL cache).
- **Nuốt lỗi có thể giấu bug.** `except -> {} + log` rất robust nhưng cũng làm
  config sai "im lặng" trở về default. `hex_agent` chấp nhận vì triết lý "hook
  không được làm sập host"; nhưng trong hệ khác, fail-fast có thể đúng hơn.
- **Khi nào KHÔNG dùng:** nếu config cần khác nhau theo từng request/tenant trong
  cùng process, module-level Singleton là sai — hãy truyền config qua tham số (DI).

---

## 6. Câu hỏi tự kiểm tra

1. Tại sao gọi `_load_config()` ba lần mà file YAML chỉ bị đọc **một** lần? Dòng
   code nào (line bao nhiêu) chịu trách nhiệm cho hành vi đó?
2. Khi YAML hỏng, vì sao `_load_config()` trả `{}` thay vì ném lỗi? Triết lý
   thiết kế đằng sau lựa chọn này là gì?
3. Nếu bạn cần config tự động cập nhật khi file YAML thay đổi lúc runtime, mô hình
   "cache 1 lần/process" này hỏng ở đâu, và bạn sẽ thay bằng cơ chế gì?
