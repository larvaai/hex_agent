# Case 02 — EventLogger: Closure-as-Observer cho Observability

> Observer áp dụng vào một bài toán thật: **một nguồn event (kernel/agent) → nhiều bên tiêu thụ (log, UI, analytics)**. Điểm hay là Observer ở đây là một **closure** (`sink`), không phải class — cách idiomatic của Python: Subject chỉ cần một `Callable`, không cần interface tường minh.

---

## 1. Bối cảnh trong hex_agent

Khi agent chạy, kernel phát các topic như `tool.completed`, `tool.failed`, `graph.step`... lên `EventBus`. Hệ observability cần:
- **Ghi durable** mọi event xuống `events.jsonl` để có thể truy vết một lượt chạy.
- **Gom metric** (`tool_calls`, `tool_failures`, `steps`...) theo topic.
- Làm việc đó **an toàn đa luồng** vì nhiều thread cùng publish.

`attach_to_bus` ở `observability/event_log.py:102-134` chính là nơi một Observer được tạo ra (closure `sink`) và gắn vào bus. Và `EventLogger.emit` ở `observability/event_log.py:60-73` tăng `seq` đơn điệu **dưới lock** rồi ghi một dòng JSON.

Trong sản phẩm thật, đây là 1-tới-N rõ ràng — `ui/ide/runner.py:147-148`:

```python
kernel.events.subscribe(bridge.subscriber)               # observer #1: cầu nối UI
attach_to_bus(EventLogger(run_id=run_id), kernel.events)  # observer #2: ghi log durable
```

## 2. Trích đoạn code thật

`observability/event_log.py:102-134` (lược phần giữa):

```python
def attach_to_bus(logger: EventLogger, bus: EventBus) -> None:
    """Mirror kernel events into the event log and update metrics."""

    def sink(topic: str, payload: dict[str, Any]) -> None:
        tool = payload.get("tool", "")
        is_llm = isinstance(tool, str) and tool.startswith("llm.")
        logger.emit("LLMCallEvent" if is_llm else "KernelEvent", topic=topic, **payload)
        if topic == "tool.completed":
            logger.count("tool_calls")
            if is_llm:
                logger.count("llm_calls")
        elif topic == "tool.failed":
            logger.count("tool_calls")
            logger.count("tool_failures")
            ...
    bus.subscribe(sink)
```

`EventLogger.emit` giữ seq đơn điệu dưới lock — `observability/event_log.py:60-73`:

```python
def emit(self, kind: str, **fields: Any) -> dict[str, Any]:
    with self._lock:
        self.seq += 1
        event = {"sequence": self.seq, "timestamp": _now(), "run_id": self.run_id, "kind": kind, **fields}
        if self.enabled:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event
```

Bằng chứng concurrency — `tests/test_event_concurrency.py:24-41`: 10 thread × 25 event = 250, `sequence` vẫn là `[1..251]` (1 `run_started` + 250).

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Observer | Thành phần trong hex_agent | Vị trí |
|------------------|----------------------------|--------|
| **Subject** | `EventBus` | `core/events.py:11` |
| **ConcreteObserver** | closure `sink` | `observability/event_log.py:105-132` |
| **attach()** | `bus.subscribe(sink)` | `observability/event_log.py:134` |
| **State của observer** | `EventLogger` (seq, metrics, file) | `observability/event_log.py:41-99` |
| **Phản ứng riêng theo event** | `if topic == "tool.completed": logger.count(...)` | `observability/event_log.py:111-132` |
| **Durable side-effect** | `emit()` ghi JSONL | `observability/event_log.py:60-73` |
| **1-tới-N (2 observer cùng bus)** | `subscribe(bridge.subscriber)` + `attach_to_bus(...)` | `ui/ide/runner.py:147-148` |
| **seq đơn điệu dưới đua thread** | `with self._lock: self.seq += 1` | `observability/event_log.py:61-62` |

## 4. Bản rút gọn chạy được

File: [`event_logger_adapter.py`](./event_logger_adapter.py) — chạy `python3 event_logger_adapter.py`.

Nó mô phỏng:
- `attach_to_bus(logger, bus)` tạo **closure `sink`** rồi `subscribe` — đúng vai trò ConcreteObserver.
- `EventLogger` gom metric `tool_calls` / `tool_failures` và ghi durable. **Thay JSONL trên đĩa bằng CSV in-memory (`io.StringIO`)** để chạy sạch, không đụng filesystem — nhưng vẫn giữ nguyên tinh thần "mỗi event = một dòng ghi durable, seq đơn điệu dưới lock".
- Bước [2] thêm observer thứ hai (UI counter) trên cùng bus → tái hiện 1-tới-N của `runner.py:147-148`.
- Bước [5] **gỡ động** (`unsubscribe`) → observer ngừng nhận event.
- Bước [6] tái hiện chính xác `test_event_concurrency.py:24-41`: 10 thread × 25 = 250, assert `seq == range(1, 252)`.
- Bước [7] **đối chứng**: một bộ đếm không khoá lock dưới 8 thread để minh hoạ race condition — chính lý do `EventLogger` phải dùng `RLock`.

Đã lược bỏ: nhánh `llm.*`, hơn chục metric khác, `summary.json` / `index.jsonl`, và ghi đĩa thật. Vai trò pattern + bất biến seq giữ nguyên.

## 5. Cái giá / Khi nào KHÔNG nên dùng

- **Closure-as-observer** rất gọn nhưng **khó gỡ** nếu không giữ tham chiếu tới chính closure đó (như bước [5] phải `return sink` rồi mới `unsubscribe(sink)` được). Class observer có handle ổn định hơn.
- **Observer ghi đĩa đồng bộ** (`emit` mở file mỗi lần) khiến `publish` chậm nếu I/O nghẽn — observer chậm sẽ block subject. Khi cần thông lượng cao: đẩy event vào queue, ghi ở worker riêng.
- Gom metric trong observer làm observer **giữ state** — phải khoá lock cẩn thận; quên lock = race (bước [7]).
- Không hợp khi cần **đảm bảo không mất event lúc chưa ai subscribe**: late subscriber sẽ bỏ lỡ (xem case 03 về replay).

## 6. Câu hỏi tự kiểm tra

1. Vì sao `sink` được viết là closure thay vì một class có method `update`? Lợi và hại của lựa chọn này so với interface tường minh?
2. Trong bước [6], điều gì đảm bảo 250 event từ 10 thread cho ra `seq` đúng `[1..251]` không trùng/không sót? Bỏ lock ở đâu thì hỏng?
3. Nếu muốn thêm metric mới `parse_errors`, bạn sửa ở đâu — trong `EventBus`, hay chỉ trong closure `sink`? Điều đó nói gì về nguyên lý Open/Closed của Observer?
