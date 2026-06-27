# Case 01 — Core Kernel Event Publishing & Multi-Subscriber Dispatch

> Trái tim của EDA trong hex_agent: `AgentKernel.execute_tool()` **phát fact** ("đã có yêu cầu gọi tool", "tool xong/hỏng") lên một `EventBus` in-process. Nhiều subscriber độc lập nghe và xử lý — kernel không biết ai nghe, có bao nhiêu người nghe.

---

## 1. Bối cảnh trong hex_agent

Kernel là chokepoint duy nhất chạy tool. Nếu kernel phải tự gọi từng "khán giả" (observability ghi log, UI bridge cập nhật timeline, metrics counter...), thì:

- Thêm 1 khán giả mới (vd: tracing exporter) phải **sửa kernel** — vi phạm OCP.
- 1 khán giả ném exception sẽ **làm sập** cả `execute_tool` — coupling thất bại.
- Kernel dính chặt vào tầng observability/UI — không test được riêng.

hex_agent giải bằng pub-sub: kernel chỉ `self.events.publish(topic, payload)`. Bus fan-out tới mọi subscriber, **deepcopy** payload cho từng người, và **nuốt exception** của từng người để một observer hỏng không phá runtime.

Các điểm thật đã mở kiểm chứng:

- `core/events.py:11-31` — `EventBus`: `subscribe(fn)` + `publish(topic, payload)`. Snapshot list subscriber dưới lock (dòng 23-24), deepcopy payload mỗi lần giao (dòng 25-28), `except Exception: pass` (dòng 29-31).
- `core/kernel.py:123-126` — publish `tool.requested` TRƯỚC khi chạy tool, mang `tool`, `request_id`, `args`, lineage.
- `core/kernel.py:140-150` — publish `tool.failed` (scope_block) khi tool ngoài `allowed_capabilities`. Là **event**, không phải exception.
- `core/kernel.py:179-190` — publish `middleware.skipped` khi middleware advisory (fail_open) raise.
- `core/kernel.py:215-224` — publish `tool.completed`/`tool.failed` SAU khi chạy. Fire-and-forget: kernel return ngay.
- `observability/event_log.py:102-134` — `attach_to_bus`: một subscriber `sink(topic, payload)` ghi JSONL + đếm metric. Đây là 1 consumer thực tế của bus.
- `tests_audit/test_core_edges_rigor.py:523-578` — test chứng minh: publish không payload giao dict rỗng; mỗi subscriber nhận deepcopy độc lập; subscriber đăng ký giữa chừng không nhận event đang bay; subscribe/publish đồng thời không vỡ registry.

---

## 2. Trích đoạn code thật

`core/events.py:18-31` — bus tối giản, đúng tinh thần "observer must never break the runtime":

```python
def subscribe(self, fn: Subscriber) -> None:
    with self._lock:
        self._subscribers.append(fn)

def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
    with self._lock:
        subscribers = tuple(self._subscribers)          # snapshot dưới lock
    data = copy.deepcopy(payload or {})
    for fn in subscribers:
        try:
            fn(topic, copy.deepcopy(data))              # mỗi subscriber 1 bản copy
        except Exception:
            # An observer must never break the runtime.
            pass
```

`core/kernel.py:215-224` — producer phát fact sau khi chạy tool, KHÔNG biết ai nghe:

```python
self.events.publish(
    "tool.completed" if envelope.get("ok") else "tool.failed",
    {
        **lineage,
        "tool": request.name,
        "request_id": request.request_id,
        "ok": bool(envelope.get("ok")),
        "error": envelope.get("error"),
    },
)
return envelope
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai EDA | Trong hex_agent | Trong bản rút gọn `kernel_event_pub_sub.py` |
|---|---|---|
| **Producer** | `AgentKernel.execute_tool()` (`core/kernel.py:106-225`) | `MiniKernel.execute_tool()` |
| **Event Bus** | `EventBus` (`core/events.py:11-31`) | `EventBus` (distill 1-1) |
| **Event (fact)** | topic `tool.requested` / `tool.completed` / `tool.failed` + payload dict | cùng các topic đó |
| **Consumer A** | `EventLogger.sink` qua `attach_to_bus` (`observability/event_log.py:102-134`) | `LoggingHandler`, `MetricsHandler` |
| **Consumer B** | `KernelEventBridge.subscriber` (`ui/ide/bridge.py:38`) | `AuditHandler` |
| **Cô lập lỗi** | `except Exception: pass` (`core/events.py:29-31`) | `BrokenHandler` bị nuốt lỗi |
| **Tách payload** | `copy.deepcopy` mỗi delivery (`core/events.py:25-28`) | bước 6 trong demo |

---

## 4. Bản rút gọn chạy được

File: [`kernel_event_pub_sub.py`](./kernel_event_pub_sub.py) — chạy `python3 kernel_event_pub_sub.py` (exit 0).

**Mô phỏng gì:**
- `EventBus` distill 1-1 từ `core/events.py` (snapshot dưới lock, deepcopy, nuốt lỗi).
- `MiniKernel` distill `execute_tool`: phát `tool.requested` rồi `tool.completed`/`tool.failed`, kể cả nhánh scope-block.
- 3 consumer độc lập (logging / metrics / audit) + 1 consumer hỏng để chứng minh cô lập lỗi.
- Đối chứng `TightlyCoupledKernel`: gọi trực tiếp từng consumer — thêm khán giả phải sửa producer, và 1 consumer raise kéo sập cả request.

**Lược bỏ:** middleware chain, `CapabilityRegistry`, `CapabilityResult`, lineage đầy đủ (run_id/task_id/...), ghi file JSONL, threading thật. Chỉ giữ đúng vai Producer → Bus → nhiều Consumer.

**Bất biến được assert:**
- Cả 3 consumer lành đều fire cho mỗi event.
- Metrics đếm đúng (2 tool_calls, 1 failure).
- Consumer hỏng đã được gọi nhưng KHÔNG làm sập bus.
- Mỗi subscriber nhận một deepcopy độc lập (mutate của người này không ảnh hưởng người kia).

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Khó debug:** không còn stack trace xuyên suốt producer→consumer. Phải dựa vào log + correlation id (`request_id`).
- **Nuốt lỗi âm thầm:** `except Exception: pass` bảo vệ runtime nhưng có thể giấu bug trong consumer — bắt buộc consumer phải tự log lỗi của mình.
- **Chỉ 1 consumer cho mỗi event:** nếu mãi chỉ có đúng 1 người nghe, gọi method trực tiếp đơn giản hơn, không cần bus.
- **Cần kết quả trả về:** publish là fire-and-forget, không thu kết quả. Cần feedback thì dùng command/call trực tiếp, không phải event.
- **deepcopy không rẻ:** payload lớn × nhiều subscriber × tần suất cao có thể tốn CPU.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `publish` phải **snapshot** danh sách subscriber dưới lock *trước* khi giao, thay vì lặp trực tiếp trên `self._subscribers`? (Gợi ý: test `subscriber_added_during_publish` ở `tests_audit/test_core_edges_rigor.py:543-559`.)
2. Nếu bỏ `copy.deepcopy` ở dòng `core/events.py:28`, kịch bản nào sẽ vỡ khi có 2 subscriber và subscriber đầu mutate payload?
3. `tool.failed` do scope-block (`core/kernel.py:140-150`) được phát như một **event** chứ không **raise** exception. Lợi gì cho consumer observability so với việc ném exception lên caller?
