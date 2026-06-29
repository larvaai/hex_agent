# Case 03 — EventLog: Observer + Event Sourcing (frozen event, durable, replay, late-sub)

> Một "hương vị" khác của Observer: event là **frozen dataclass** (bất biến), được **lưu durable vào ledger TRƯỚC khi** subscribers nhìn thấy, và có ngữ nghĩa **late subscription** (đăng ký muộn chỉ thấy event tương lai) — chữa được bằng **replay** từ ledger.

---

## 1. Bối cảnh trong hex_agent

`drag_from_zero` là một biến thể agent dùng kiến trúc **event-sourcing**: cây thực thi (Đồ thị 2) không bao giờ được lưu trực tiếp — nó được *fold* lại từ một append-only event log. `EventLog` ở `drag_from_zero/dragzero/events.py:46-91` vừa là **kho sự thật**, vừa là **Subject**: ai muốn theo dõi diễn biến thì `subscribe`.

Khác biệt then chốt so với case 01/02:
- **Event là `@dataclass(frozen=True)`** (`events.py:37-43`) — observer không thể mutate, nên không thể làm hỏng view của observer khác.
- **Durable trước broadcast** (`events.py:61-62`): event được flush xuống ledger *trước khi* subscribers chạy → resume = đọc lại ledger.
- **Late subscription**: đăng ký sau khi đã có event thì chỉ thấy event tương lai (`tests/test_events.py:39-45`).

## 2. Trích đoạn code thật

`drag_from_zero/dragzero/events.py:58-76`:

```python
def append(self, event: Event) -> Event:
    stamped = replace(event, seq=len(self._events))
    if self._ledger is not None:
        self._ledger.append(stamped)  # durable FIRST — before memory is mutated,
    self._events.append(stamped)      # so disk never falls behind RAM
    for sub in self._subs:
        sub(stamped)
    return stamped

@classmethod
def replay(cls, ledger) -> "EventLog":
    log = cls(ledger=ledger)
    log._events = ledger.read()  # seqs come from disk, not re-stamped
    return log

def subscribe(self, fn: Callable[[Event], None]) -> None:
    self._subs.append(fn)
```

Event bất biến — `events.py:37-43`:

```python
@dataclass(frozen=True)
class Event:
    type: EventType
    seq: int = -1
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    payload: dict = field(default_factory=dict)
```

Biến thể late subscription — `drag_from_zero/tests/unit/test_events.py:39-45`:

```python
def test_subscribe_after_appends_only_sees_future_events():
    log = EventLog()
    log.append(Event(EventType.TASK_STARTED, task_id="t1"))
    seen: list[Event] = []
    log.subscribe(seen.append)
    log.append(Event(EventType.TASK_COMPLETED, task_id="t1"))
    assert [e.seq for e in seen] == [1]
```

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò Observer | Thành phần trong hex_agent | Vị trí |
|------------------|----------------------------|--------|
| **Subject** | `EventLog` | `drag_from_zero/dragzero/events.py:46` |
| **Danh sách observers** | `self._subs: list[Callable[[Event], None]]` | `events.py:55` |
| **notify()** | `append(event)` (đóng dấu → durable → broadcast) | `events.py:58-65` |
| **attach()** | `subscribe(fn)` | `events.py:75-76` |
| **Observer interface** | `Callable[[Event], None]` | `events.py:55` |
| **Event** | `@dataclass(frozen=True) Event` | `events.py:37-43` |
| **Durable trước broadcast** | `ledger.append(stamped)` trước vòng `for sub` | `events.py:61-64` |
| **Replay (catch-up)** | `EventLog.replay(ledger)` | `events.py:67-73` |
| **Biến thể late-sub** | test minh hoạ seq `[1]` | `tests/unit/test_events.py:39-45` |

## 4. Bản rút gọn chạy được

File: [`event_log_broadcast.py`](./event_log_broadcast.py) — chạy `python3 event_log_broadcast.py`.

Nó mô phỏng:
- `EventLog` giữ nguyên logic thật: `append` = đóng dấu `seq` qua `replace(...)` → lưu ledger → broadcast cho từng `sub`.
- `Event` là `@dataclass(frozen=True)` giống hệt bản thật (đổi `EventType` sang vòng đời Order cho dễ hình dung).
- **Ledger trên đĩa (JSONL) được thay bằng `InMemoryLedger`** (list trong RAM) để chạy sạch — nhưng giữ đúng tính chất "durable trước khi observer thấy".
- Hai observer độc lập: `ui_progress` (thanh tiến trình) và `ops_journal` (nhật ký).
- Bước [4] chứng minh **frozen**: gán `event.seq = 999` ném `FrozenInstanceError` (tái hiện `test_events.py:90-93`).
- Bước [5] tái hiện **late subscription** (`test_events.py:39-45`): observer vào muộn chỉ thấy `seq [1]`.
- Bước [6] dùng `EventLog.replay(ledger)` để observer mới **catch-up toàn bộ lịch sử** — cách chữa late-sub.
- Bước [7] **đối chứng**: nếu Event **không** frozen, một observer "greedy" mutate payload chung → observer "innocent" nhận giá trị đã hỏng.

Đã lược bỏ: ~20 `EventType` thật, ledger ghi đĩa/flush thật, `of_type`/`types`/`__iter__`. Vai trò pattern + 4 bất biến (đóng dấu seq, durable-trước-broadcast, frozen, late-sub/replay) giữ nguyên.

## 5. Cái giá / Khi nào KHÔNG nên dùng

- **Frozen event** an toàn nhưng mỗi lần "sửa" phải `replace(...)` tạo object mới — tốn allocation; với event rất lớn hoặc rất nhiều, cân nhắc.
- **Durable trước broadcast** làm `append` chậm bằng tốc độ ghi đĩa của ledger; nếu observer cần phản ứng tức thời mà ledger nghẽn, độ trễ tăng.
- **Late subscription** là con dao hai lưỡi: tiện (không phát lại quá khứ ồ ạt) nhưng dễ gây "lost event" cho subscriber vào muộn. Nếu mọi subscriber đều cần lịch sử → luôn phải `replay`, tốn chi phí.
- Không hợp khi không cần kho sự thật append-only; lúc đó `EventBus` đơn giản (case 01) đủ dùng.

## 6. Câu hỏi tự kiểm tra

1. Vì sao `append` ghi ledger **trước** vòng `for sub in self._subs`? Điều gì hỏng nếu broadcast trước rồi mới ghi ledger và tiến trình chết giữa chừng?
2. `frozen=True` chống được lớp bug nào mà case 01 phải dùng `deepcopy` mới chống được? Hai cách tiếp cận này đánh đổi gì khác nhau?
3. Một observer đăng ký muộn muốn biết toàn bộ lịch sử order. Bạn dùng cơ chế nào trong file này, và nó tương ứng với khái niệm "warm/replay observable" thế nào?
