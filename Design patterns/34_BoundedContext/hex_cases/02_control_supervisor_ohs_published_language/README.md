# Case 02 — OHS + Published Language: Control ↔ Supervisor (qua `RuntimeEvent`)

> Flagship của Lesson 34 (Bounded Context) trong codebase thật `hex_agent`.
> Hai context độc lập — Supervisor (điều phối) và Control (phân phối event control-plane) —
> giao tiếp qua **một hợp đồng có version**, không qua chia sẻ cấu trúc dữ liệu nội bộ.

---

## 1. Bối cảnh trong hex_agent — vấn đề thật

Supervisor sinh ra rất nhiều sự kiện: `loop.team_composed`, `loop.decision`, `loop.turn`, `loop.tool`...
Nhiều consumer cần đọc chúng: UI (qua SSE), audit log (JSONL), replay. Nếu mỗi nơi tự định dạng một
dict tuỳ ý, ta rơi vào Big Ball of Mud về mặt event: không version, không thứ tự, và — nguy hiểm nhất —
**secret trong payload có thể rò thẳng ra UI**.

hex_agent giải đúng kiểu Bounded Context: **Control là OHS provider** — nó publish *một* schema chuẩn
(`RuntimeEvent`) cho mọi consumer; **Supervisor là downstream consumer** — nó không tự định dạng envelope,
chỉ gọi `emit(topic, payload)` và để Control chuẩn hoá. **Redactor** là tường ngăn (Anti-Corruption
translation layer): payload thô không bao giờ chạm UI sink; secret bị che *trước khi* rời Control context.

Bằng chứng file:line (đã mở kiểm chứng):

- `control/events.py:113-151` — `RuntimeEvent`: frozen dataclass, `schema_version`, tách `payload` (raw) khỏi `ui_payload` (đã redact) + `redaction`. `__post_init__` validate để event không hợp lệ không thể tồn tại.
- `control/events.py:85-110` — `RedactionInfo(level, has_secret, redacted_fields)`.
- `control/events.py:193-211` — `SessionSeq`: cấp `seq` monotonic theo từng session.
- `control/redaction.py:37-73` — `Redactor`: che field bí mật theo **tên key chính xác**, điền `ui_payload` + `RedactionInfo`, không mutate payload gốc.
- `control/emitter.py:53-61` — `EventEmitter.emit_event`: validate type qua registry → stamp `seq` → redact → fan-out tới sink.
- `supervisor/graph.py:56-76` — `SupervisorContext.emit()`: có emitter → đi qua envelope `RuntimeEvent`; emitter=None → publish raw dict (legacy).
- `supervisor/graph.py:103` — `compose_team` phát topic `loop.team_composed` qua `emit()`.

---

## 2. Trích đoạn code thật

`SupervisorContext.emit()` chọn đường OHS hay legacy (`supervisor/graph.py:56-75`):

```python
def emit(self, topic: str, payload: dict[str, Any]) -> None:
    # E21 B1: when an emitter is wired, every supervisor event flows through the
    # canonical envelope (registry-validated, seq-stamped, redacted). Otherwise keep
    # the legacy raw-dict publish so existing callers/tests are unaffected.
    if self.emitter is not None:
        if self.trace is None:
            self.trace = TraceContext.new_root()
        identity = self.supervisor_session.identity
        self.emitter.emit(
            topic,
            session_id=identity.session_id,
            actor=Actor(type="runtime", id="supervisor"),
            trace=self.trace,
            payload=dict(payload),
            task_id=identity.task_id,
        )
        return
    self.supervisor_session.kernel.events.publish(
        topic, {**self.supervisor_session.call_context().event_fields(), **payload}
    )
```

`EventEmitter.emit_event` — đường publish duy nhất, đã chuẩn hoá (`control/emitter.py:53-61`):

```python
def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
    spec = self._registry.get(event.event_type)  # ControlContractError if unknown
    staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))
    final = self._redactor.apply(staged, level=spec.visibility)
    for sink in self._sinks:
        sink.emit(final)
    return final
```

`Redactor.apply` điền `ui_payload` + `RedactionInfo`, không đụng payload gốc (`control/redaction.py:65-73`):

```python
def apply(self, event: RuntimeEvent, *, level: str | None = None) -> RuntimeEvent:
    ui_payload, fields = self.redact(event.payload)
    info = RedactionInfo(
        level=level or event.redaction.level,
        has_secret=bool(fields),
        redacted_fields=tuple(fields),
    )
    return replace(event, ui_payload=ui_payload, redaction=info)
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Context Map | Thành phần code thật (hex_agent) |
|---|---|
| **OHS provider** (publish 1 contract) | `EventEmitter` — `control/emitter.py:39-90` |
| **Published Language** (versioned, redactable) | `RuntimeEvent` — `control/events.py:113-151` |
| **Downstream consumer** (route qua envelope) | `SupervisorContext.emit` — `supervisor/graph.py:56-76` |
| **Anti-Corruption translation layer** | `Redactor` — `control/redaction.py:37-73` |
| **Bất biến thứ tự / dedup** | `SessionSeq` — `control/events.py:193-211` |
| **Cổng (gate) type hợp lệ** | `EventTypeRegistry.get` — `control/emitter.py:56` |
| **Tách raw vs UI-safe** | `payload` ≠ `ui_payload` + `RedactionInfo` — `control/events.py:85-132` |

---

## 4. Bản rút gọn chạy được

File: [`control_supervisor_ohs_published_language.py`](./control_supervisor_ohs_published_language.py) — chỉ stdlib, chạy:

```bash
python3 control_supervisor_ohs_published_language.py
```

Nó **mô phỏng**:

- `RuntimeEvent` (frozen, `__post_init__` validate, `schema_version`, `payload` vs `ui_payload`), `RedactionInfo`, `SessionSeq`, `Redactor`, `EventTypeRegistry`, `EventEmitter` đúng vai trò thật.
- `SupervisorContext.emit`: có emitter → envelope chuẩn; emitter=None → raw dict (legacy).
- Bốn bất biến: **versioned + seq monotonic**, **secret redact trước khi tới UI sink**, **payload thô không bị mutate** (raw còn nguyên trong audit), và **type lạ bị chặn tại gate** trước khi publish.
- **Đối chứng** `no_ohs_anti_pattern()`: emitter=None → secret đi thẳng ra bus thô, không version/seq/redact.
- Lưu ý: `Redactor` khớp **tên key chính xác** (giống `control/redaction.py`), nên ví dụ dùng key `api_key` (nằm trong `SECRET_KEYS`), không phải tên bịa.

Nó **lược bỏ**: `KernelSession`/`Actor`/`TraceContext` đầy đủ, SSE/Kafka thật, `event_registry` YAML, và `uuid`/`created_at` — chỉ giữ phần load-bearing của Published Language + redaction.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Cái giá**: thêm một lớp envelope + registry + redactor cho *mọi* event; mọi event mới phải đăng ký type và chọn `visibility`. Với một consumer duy nhất và không có secret, đây là chi phí thừa.
- **Khi KHÔNG nên**: tool/script một-tiến-trình không có UI ngoài, không có dữ liệu nhạy cảm. `print()` hay một dict tuỳ ý là đủ.
- **Dấu hiệu lạm dụng**: nếu mỗi consumer lại "đọc lén" `payload` thô thay vì `ui_payload`, thì OHS bị phá — Published Language chỉ có giá trị khi *mọi* sink tôn trọng `ui_payload`.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `RuntimeEvent` tách `payload` (raw) khỏi `ui_payload` (đã redact) thay vì redact tại chỗ trên `payload`? Audit log được lợi gì từ việc giữ raw?
2. Khi `emitter=None`, `SupervisorContext.emit` rơi về raw dict. Ba thứ nào bị mất so với đường OHS, và rủi ro bảo mật cụ thể là gì?
3. `EventEmitter` chặn `event_type` lạ *trước* khi publish. Vì sao đặt cổng kiểm tra ở provider (Control) lại đúng tinh thần OHS hơn là để mỗi consumer tự lọc?
