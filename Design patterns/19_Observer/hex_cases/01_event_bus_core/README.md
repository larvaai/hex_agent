# Case 01 — EventBus: Lõi Pub/Sub thread-safe (Observer thuần khiết)

> Đây là hiện thân **trực tiếp và sạch nhất** của Observer trong hex_agent. Một Subject giữ list observer, `publish` lặp qua từng cái và gọi — đúng định nghĩa pattern, cộng thêm hai bảo vệ thực chiến: tách rời payload và cô lập lỗi.

---

## 1. Bối cảnh trong hex_agent

hex_agent có một *event system* kiểu publish/subscribe để tách rời **nguồn phát event** (kernel, orchestrator) khỏi **bên tiêu thụ** (logging, UI adapter, analytics). Trái tim của nó là `EventBus` ở `core/events.py:11-31`.

Vấn đề thật mà nó giải:
- Kernel chạy tool, phát event `tool.completed` / `tool.failed`. Có **nhiều** bên muốn biết: bộ ghi log JSONL, cầu nối UI, bộ đếm metric. Kernel **không nên** biết tên từng bên.
- Observer là code của người khác viết — **một observer hỏng không được phép kéo sập runtime của agent**. File ghi rõ ở `core/events.py:30`: *"An observer must never break the runtime."*
- Nhiều thread cùng `publish` (xem case 02) — registry phải an toàn đa luồng.

## 2. Trích đoạn code thật

`core/events.py:11-31`:

```python
class EventBus:
    """Minimal pub/sub. Observability subscribes here (E04)."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = threading.RLock()

    def subscribe(self, fn: Subscriber) -> None:
        with self._lock:
            self._subscribers.append(fn)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        data = copy.deepcopy(payload or {})
        for fn in subscribers:
            try:
                fn(topic, copy.deepcopy(data))
            except Exception:
                # An observer must never break the runtime.
                pass
```

Và bằng chứng bất biến "payload tách rời" ở `tests/test_event_concurrency.py:9-21`:

```python
def test_subscribers_receive_detached_payloads():
    bus = EventBus()
    observed = []
    def mutate(topic, payload):
        payload["nested"]["value"] = "changed"
    bus.subscribe(mutate)
    bus.subscribe(lambda topic, payload: observed.append(payload))
    original = {"nested": {"value": "original"}}
    bus.publish("x", original)
    assert original["nested"]["value"] == "original"
    assert observed[0]["nested"]["value"] == "original"
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Observer | Thành phần trong hex_agent | Vị trí |
|------------------|----------------------------|--------|
| **Subject / Publisher** | `EventBus` | `core/events.py:11` |
| **Danh sách observers** | `self._subscribers: list[Subscriber]` | `core/events.py:15` |
| **attach()** | `subscribe(fn)` | `core/events.py:18-20` |
| **notify()** | `publish(topic, payload)` | `core/events.py:22-31` |
| **Observer interface** | `Subscriber = Callable[[str, dict], None]` (duck typing) | `core/events.py:8` |
| **Event** | cặp `(topic: str, payload: dict)` | tham số của `publish` |
| **Cô lập lỗi** | `try/except Exception: pass` | `core/events.py:29-31` |
| **Tách rời state** | `copy.deepcopy(...)` cho từng observer | `core/events.py:25, 28` |
| **An toàn đa luồng** | `threading.RLock` + snapshot `tuple(...)` | `core/events.py:16, 24` |

## 4. Bản rút gọn chạy được

File: [`event_bus_core.py`](./event_bus_core.py) — chạy `python3 event_bus_core.py`.

Nó mô phỏng:
- `EventBus` **giữ nguyên** logic thật: list + lock + snapshot + deepcopy + try/except.
- Một `FileWatcher` đóng vai nguồn phát event (thay cho kernel/orchestrator nặng).
- Hai observer demo: `logger` (in ra) và `count` (đếm). Bước [3] thêm observer thứ ba **mà không sửa Subject** — minh hoạ Open/Closed.
- Bước [4] tái hiện chính xác `test_subscribers_receive_detached_payloads`.
- Bước [5] chứng minh observer raise không chặn observer kế tiếp.
- Bước [6] **đối chứng**: viết một `naive_publish` không có try/except để thấy exception thoát ra ngoài làm "survivor" không bao giờ chạy.

Đã lược bỏ: hằng số epic (E04), type alias đầy đủ, và mọi tích hợp với kernel thật. Vai trò pattern giữ nguyên 100%.

## 5. Cái giá / Khi nào KHÔNG nên dùng

- **Nuốt exception** (`except: pass`) rất tiện cho "observer không kéo sập runtime", nhưng cũng **giấu lỗi**. Bản thật chấp nhận đánh đổi này vì ưu tiên sống sót; trong hệ cần debug, nên log lỗi thay vì nuốt im.
- **`deepcopy` mỗi observer** tốn CPU/bộ nhớ khi payload lớn hoặc số observer nhiều. Với event MB-size nên cân nhắc *pull style* (gửi con trỏ, observer tự lấy phần cần).
- **Memory leak**: Subject giữ strong reference tới observer; quên gỡ subscriber khi component chết = leak. `EventBus` này không có `unsubscribe` — phù hợp khi vòng đời observer trùng vòng đời bus.
- Không hợp khi cần **thứ tự nghiêm ngặt**, **all-or-nothing transactional**, hoặc **routing có điều kiện** (lúc đó dùng Mediator).

## 6. Câu hỏi tự kiểm tra

1. Vì sao `publish` chụp `tuple(self._subscribers)` **trong** lock rồi mới nhả lock để gọi observer, thay vì gọi observer ngay trong lock? (Gợi ý: deadlock + observer subscribe khi đang notify.)
2. Nếu bỏ `copy.deepcopy` ở dòng 28, test nào trong `test_event_concurrency.py:9-21` sẽ fail và vì sao?
3. `except Exception: pass` giúp gì và đánh đổi gì? Bạn sẽ sửa thế nào để vừa sống sót vừa không mất dấu vết lỗi?
