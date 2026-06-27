# Case 01 — Event Storming ở quy mô control-plane: Event + Command + Registry

> Flagship: `control_plane_event_storming`
> Distill từ: `control/events.py`, `control/commands.py`, `control/event_registry.py`, `control/command_registry.py`, `config/runtime_event_types.yaml`, `config/runtime_command_types.yaml`, `control/emitter.py`, `control/redaction.py`

---

## 1. Bối cảnh trong hex_agent

Bài học gốc dạy: kết quả của một workshop Event Storming là *glossary* — danh sách event past-tense (sticky orange) và command imperative (sticky blue) mà cả team đã thống nhất, dán lên một "bức tường". Câu hỏi thực tế: làm sao ép cái glossary đó *tồn tại trong code* để không ai lén dùng term tự phát?

hex_agent (Epic E21 — Realtime Control Plane) trả lời bằng **registry tập trung**. Mọi `event_type` mà emitter định publish PHẢI được khai báo trong `config/runtime_event_types.yaml` (57 event, đã đếm), nếu không sẽ bị từ chối ngay tại lúc emit. Tương tự, mọi `command_type` mà gateway nhận PHẢI có trong `config/runtime_command_types.yaml` (16 command).

Vấn đề thật nó giải:
- Một module gõ nhầm `sessionn.startd` thay vì `session.started` sẽ làm UI/audit/replay rạn nứt âm thầm. Registry chặn ngay (`control/event_registry.py:47-51`).
- UI không được phép sửa state trực tiếp — nó submit một `RuntimeCommand` có `idempotency_key` + `issued_by`; gateway validate trước khi vào queue (`control/commands.py:156-166`).
- Secret trong payload không bao giờ được rò ra UI — `EventEmitter` chạy `Redactor` trước khi fan-out (`control/emitter.py:58`, `control/redaction.py:65-73`).

Đây chính là 3 invariant đầu của Event Storming output (bài gốc mục 2.4): event past-tense, command imperative, và mỗi term phải nằm trong vocabulary đã thống nhất.

---

## 2. Trích đoạn code thật

Registry là "bức tường" — nó từ chối event chưa khai báo (`control/event_registry.py:47-55`):

```python
def assert_known(self, event_type: str) -> None:
    if event_type not in self._specs:
        raise ControlContractError(
            f"Unknown event_type: {event_type!r}. Declare it in runtime_event_types.yaml."
        )

def get(self, event_type: str) -> EventTypeSpec:
    self.assert_known(event_type)
    return self._specs[event_type]
```

EventEmitter là "facilitator": validate → stamp seq → redact → fan-out (`control/emitter.py:53-61`):

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

Command có `idempotency_key` + `issued_by` bắt buộc, validate ngay từ parse (`control/commands.py:156-166`):

```python
def parse_command(data: dict[str, Any]) -> RuntimeCommand:
    if not isinstance(data, dict):
        raise ControlContractError("Command must be a mapping.")
    if not data.get("idempotency_key"):
        raise ControlContractError("Command requires a non-empty 'idempotency_key'.")
    if not isinstance(data.get("issued_by"), dict):
        raise ControlContractError("Command requires an 'issued_by' object.")
    return RuntimeCommand.from_dict(data)
```

Catalog "bức tường sticky orange" (`config/runtime_event_types.yaml:13-17`, `:44`):

```yaml
session.started:        { visibility: ui_safe, durable: true }
session.paused:         { visibility: ui_safe, durable: true }
...
tool.call_requested:    { visibility: ui_safe, durable: true, checkpoint_candidate: true }
```

---

## 3. Bảng ánh xạ vai trò pattern ↔ code thật

| Vai trò Event Storming | Khái niệm | Thành phần code thật |
|------------------------|-----------|----------------------|
| Sticky ORANGE | Domain event (past-tense fact) | `RuntimeEvent` — `control/events.py:113-152` |
| Sticky BLUE | Command (imperative) | `RuntimeCommand` — `control/commands.py:62-106` |
| Sticky YELLOW | Actor / người phát | `Actor` (`control/events.py:32-51`), `IssuedBy` (`control/commands.py:34-58`) |
| Bức tường sticky note | Catalog vocabulary | `config/runtime_event_types.yaml:11-83`, `config/runtime_command_types.yaml:9-36` |
| Facilitator gò vào vocabulary | Gate reject term lạ | `EventTypeRegistry.assert_known` (`control/event_registry.py:47-51`), `CommandTypeRegistry.assert_known` (`control/command_registry.py:43-47`) |
| Facilitator điều phối + ghi nhận | Validate + seq + redact + fan-out | `EventEmitter.emit_event` — `control/emitter.py:53-61` |
| Phân loại độ nhạy cảm (hot spot đỏ) | Visibility + che secret | `RedactionInfo` (`control/events.py:85-110`), `Redactor.apply` (`control/redaction.py:65-73`) |
| Bounded context (nhóm sticky) | Tiền tố dotted trong event_type | `session.*` / `agent.*` / `tool.*` / `permission.*` / `command.*` / `artifact.*` / `loop.*` trong YAML |

---

## 4. Bản rút gọn chạy được

File: `control_plane_event_storming.py` (chỉ stdlib).

Nó mô phỏng:
- Hai registry (`EVENT_TYPES`, `COMMAND_TYPES` — dict Python thay cho YAML thật) đóng vai "bức tường".
- `EventEmitter` validate event_type với registry, stamp `seq` tăng đơn điệu per-session, redact secret, fan-out tới sink (list log).
- `CommandGateway` parse + check registry + chặn duplicate idempotency_key.
- 4 nhánh đối chứng: emit event gõ nhầm (bị chặn), submit command lạ (`DeleteEverything` → reject + để lại fact `command.rejected`), submit command thiếu `idempotency_key` (bị chặn từ parse).
- 4 assert bất biến: seq liên tục 1..n; mọi event trong log thuộc registry; không secret nào rò vào `ui_payload`; command bị reject vẫn để lại đúng 1 audit fact.

Nó **lược bỏ** so với bản thật: YAML → dict nhúng; bỏ `trace_id`/`span_id`/`schema_version`/datetime ISO (dùng counter); bỏ permission resolver thật + queue gateway thật (chỉ minh hoạ reject ở mức registry).

Chạy:

```bash
python3 control_plane_event_storming.py
```

Đối chứng "khi KHÔNG dùng pattern": bước [4] cho thấy nếu không có registry làm "bức tường", một event gõ nhầm hoặc một command độc hại sẽ lọt thẳng vào hệ thống, làm ô nhiễm vocabulary domain và phá vỡ khả năng replay/audit.

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Chi phí khai báo trước**: thêm 1 event/command mới = phải sửa file registry. Với domain CRUD trivial hoặc prototype < 1 tuần (đúng mục "khi nào KHÔNG" của bài gốc), bộ máy này là thừa — cứ gọi hàm trực tiếp.
- **Cứng nhắc trong giai đoạn khám phá**: khi domain còn chảy nhanh, ép mọi term qua registry làm chậm việc thử nghiệm. Registry hợp lý khi vocabulary đã ổn định (sau vài vòng workshop), không phải ngày đầu.
- **Ảo giác an toàn**: registry chỉ chặn *tên* lạ, không chặn *payload* sai ngữ nghĩa. Một event đúng tên nhưng payload vô nghĩa vẫn lọt. Validate payload là việc khác.
- **Một điểm nghẽn**: mọi event qua một `EventEmitter`. Nếu nó là synchronous và một sink chậm, nó kéo lùi cả luồng (bản thật fan-out tuần tự).

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `EventEmitter.emit_event` phải gọi `registry.get(event.event_type)` *trước* khi stamp seq và fan-out, chứ không phải sau? (Gợi ý: nếu reject sau khi đã đẩy ra vài sink thì sao?)
2. `idempotency_key` (trên command) và `seq` (trên event) đều liên quan tới "không xử lý trùng", nhưng giải quyết hai vấn đề khác nhau. Khác nhau ở đâu? Cái nào do *client* cấp, cái nào do *server* cấp?
3. Trong bản distill, `command.rejected` vẫn được emit khi một command lạ bị từ chối. Tại sao "việc từ chối" lại cũng là một domain event đáng ghi, thay vì chỉ raise lỗi rồi quên?
