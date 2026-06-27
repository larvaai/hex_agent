# Case 02 — Event Type Registry với Visibility & Schema Versioning

> EDA cấp production cần **quản trị schema**. Trong hex_agent, mọi `event_type` phải được khai báo trước trong một registry trung tâm; emitter là cổng gác validate trước khi publish; mỗi event được stamp `seq` đơn điệu và **redact** theo mức visibility trước khi tới UI. Producer và consumer chỉ couple qua *event_type + payload đã khai báo* — đúng tinh thần "coupling = event schema only" của bài học.

---

## 1. Bối cảnh trong hex_agent

Nếu cho phép `bus.publish(bất_kỳ_topic, dict)` tự do, thì:

- Một module có thể **bịa** event mới hoặc gõ sai tên (`agnet.beforeRun`) — consumer chờ `agent.before_run` sẽ không bao giờ nhận, bug âm thầm.
- Không ai biết một event có được phép ra UI không, hay chứa secret (token, password) không.
- Không có thứ tự (seq) để UI sắp xếp/dedup khi delivery out-of-order.

hex_agent giải bằng **control plane (Epic E21)**: registry khai báo mọi event_type + visibility; emitter validate → stamp seq → redact → fan-out tới sinks.

Các điểm thật đã mở kiểm chứng:

- `config/runtime_event_types.yaml:11-83` — catalog ~52 event_type (`session.*`, `agent.*`, `tool.*`, `hook.*`, `artifact.*`, `loop.*`...). Mỗi cái khai báo `visibility` (public|ui_safe|internal|secret|restricted), `durable`, `redact_for_ui`, `checkpoint_candidate`.
- `control/event_registry.py:22-37` — `EventTypeSpec` là `@dataclass(frozen=True)` — contract bất biến.
- `control/event_registry.py:47-51` — `assert_known(event_type)` raise `ControlContractError` nếu type chưa khai báo.
- `control/event_registry.py:64-93` — `parse_event_registry` ép tên có dấu chấm + visibility thuộc `VISIBILITY_LEVELS`.
- `control/events.py:113-151` — `RuntimeEvent` là `@dataclass(frozen=True)`; `__post_init__` validate (event_id/event_type/session_id non-empty, `schema_version >= 1`, `seq >= 0`, payload là dict). Có sẵn field `schema_version` để versioning.
- `control/events.py:193-213` — `SessionSeq`: cấp seq đơn điệu per-session, thread-safe (RLock).
- `control/emitter.py:53-61` — `EventEmitter.emit_event`: (1) `registry.get(type)` [gate], (2) stamp seq nếu chưa có, (3) `redactor.apply` theo visibility, (4) fan-out tới sinks.
- `control/emitter.py:28-36` & `control/emitter.py:93-95` — `BusEventSink` adapt `EventBus` thành `EventSinkPort`; `bus_emitter` ráp emitter lên bus. Đổi sang Kafka chỉ là thêm sink mới.
- `control/redaction.py:37-73` — `Redactor` tách `payload` → `ui_payload`, mask các key bí mật, không mutate bản gốc.

---

## 2. Trích đoạn code thật

`control/emitter.py:53-61` — cổng gác duy nhất để publish, đúng 4 bước:

```python
def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
    """Validate, stamp seq, redact, then fan out to sinks. Returns the finalized event.
    An unknown event_type raises before anything is published (registry is the gate)."""
    spec = self._registry.get(event.event_type)  # ControlContractError if unknown
    staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
    final = self._redactor.apply(staged, level=spec.visibility)
    for sink in self._sinks:
        sink.emit(final)
    return final
```

`control/event_registry.py:47-51` — gate chặn type lạ:

```python
def assert_known(self, event_type: str) -> None:
    if event_type not in self._specs:
        raise ControlContractError(
            f"Unknown event_type: {event_type!r}. Declare it in runtime_event_types.yaml."
        )
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai EDA | Trong hex_agent | Trong bản rút gọn `event_registry_versioning.py` |
|---|---|---|
| **Event type registry (contract)** | `EventTypeRegistry` + `runtime_event_types.yaml` (`control/event_registry.py:40-99`) | `EventTypeRegistry` + `SAMPLE_REGISTRY_ROWS` |
| **Spec bất biến** | `EventTypeSpec` frozen (`control/event_registry.py:22-37`) | `EventTypeSpec` frozen |
| **Producer + gate** | `EventEmitter.emit_event` (`control/emitter.py:53-61`) | `EventEmitter.emit_event` |
| **Envelope bất biến + validate** | `RuntimeEvent` (`control/events.py:113-151`) | `RuntimeEvent` (rút gọn) |
| **Seq đơn điệu/session** | `SessionSeq` (`control/events.py:193-213`) | `SessionSeq` (distill 1-1) |
| **Redaction theo visibility** | `Redactor.apply` (`control/redaction.py:65-73`) | `Redactor.apply` |
| **Sink port (swap được)** | `EventSinkPort` (`control/ports.py:14-22`), `BusEventSink` | `EventSinkPort`, `CollectingSink` |

---

## 4. Bản rút gọn chạy được

File: [`event_registry_versioning.py`](./event_registry_versioning.py) — chạy `python3 event_registry_versioning.py` (exit 0).

**Mô phỏng gì:**
- Nạp registry từ một dict (đóng vai `runtime_event_types.yaml`), ép tên có dấu chấm + visibility hợp lệ.
- Emitter **chặn** `event_type` lạ (`ControlContractError`) — chứng minh "không tự bịa event"; event lạ không lọt vào sink.
- Emit event đã khai báo → qua gate, stamp seq, redact, fan-out.
- `SessionSeq` cấp seq đơn điệu, mỗi session một bộ đếm riêng.
- Redaction: event `internal` mang `token`/`api_key` → `ui_payload` bị mask, `payload` thật giữ nguyên.
- `EventTypeSpec` frozen — chứng minh contract bất biến runtime.

**Lược bỏ:** không parse YAML thật (dùng dict thuần để khỏi cần `pyyaml`), không `Actor`/`TraceContext`/`RedactionInfo` đầy đủ, không JSONL/Kafka sink, redactor chỉ mask theo key bí mật (không lồng sâu mọi nhánh như bản thật). Giữ đúng vai Registry → Emitter (gate) → Redactor → Sink.

**Bất biến được assert:**
- Event lạ bị raise và KHÔNG vào sink.
- seq đơn điệu `1,2,3` trong cùng session; session khác bắt đầu lại từ `1`.
- `payload` thật giữ secret; `ui_payload` đã mask `token` + `api_key`, field thường giữ nguyên.
- `EventTypeSpec` frozen không gán lại được.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí khai báo:** mọi event mới phải thêm vào registry trước — chậm hơn `publish` tự do một chút, đổi lấy an toàn.
- **Schema thành public contract:** đổi/xóa field là breaking change cho mọi consumer; chỉ nên *thêm field optional* (versioning lùi tương thích).
- **Overkill cho hệ nhỏ:** monolith nhỏ, 1-2 event type, không cần registry + redactor + seq — gắn vào sớm là gánh nặng.
- **Redaction sai sót nguy hiểm:** nếu quên khai `redact_for_ui` / để sai visibility, secret có thể lọt UI — registry chỉ an toàn khi được duy trì kỷ luật.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `emit_event` gọi `registry.get(type)` **trước** khi stamp seq và redact, thay vì sau? (Gợi ý: "registry is the gate" — đừng tiêu seq cho event sẽ bị từ chối.)
2. `payload` và `ui_payload` được tách làm hai. Tầng SSE/gateway nên stream cái nào, và điều gì xảy ra nếu fallback về `payload` thô khi `ui_payload` vắng?
3. Field `schema_version` trên `RuntimeEvent` để làm gì khi một consumer cũ (chưa nâng cấp) gặp event do producer mới phát? Nêu một quy tắc tiến hóa schema an toàn.
