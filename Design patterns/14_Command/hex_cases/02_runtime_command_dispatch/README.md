# Case 02 — RuntimeCommand: Command pattern ở tầng control-plane

> *UI/người dùng KHÔNG sửa state trực tiếp — họ **submit một object `RuntimeCommand`** (bất biến). Gateway validate → chống trùng (idempotency) → lên lịch theo `apply_at` → dispatch tới Receiver.*

---

## 1. Bối cảnh trong hex_agent

Control-plane (E21) cho phép người dùng can thiệp vào một agent đang chạy từ UI: gửi prompt, dừng lượt, duyệt/từ chối checkpoint, sửa quyền... Nếu UI gọi thẳng vào runtime thì không có cách nào để **validate, chống double-click, ghi nhận ai-đã-bấm, lên lịch áp dụng đúng thời điểm, và log/replay để audit**.

Lời giải: mọi can thiệp được đóng gói thành **một object lệnh duy nhất** `RuntimeCommand`. Docstring của file nói thẳng: *"UI never mutates state directly; it submits a `RuntimeCommand`. The gateway validates it (`parse_command`) before it enters the queue."*

File và dòng thật (đã mở kiểm chứng):

- `control/commands.py:61-106` — `RuntimeCommand` (frozen dataclass): `command_type`, `session_id`, `issued_by`, `idempotency_key`, `payload`, `command_id`, `created_at`, `schema_version` (dòng 70, validate `>= 1` ở 80-81). `__post_init__` validate ngay = **ConcreteCommand**.
- `control/commands.py:33-58` — `IssuedBy` (attribution, validate `human` phải có `user_id` (dòng 45-46), `agent` phải có `agent_id` (dòng 47)).
- `control/commands.py:156-166` — `parse_command(data)` = **factory/validator**: thiếu `idempotency_key`/`issued_by` → `ControlContractError`.
- `control/command_registry.py:22-89` — `CommandTypeSpec` + `CommandTypeRegistry`: ánh xạ `command_type → apply_at` = **chiến lược lên lịch**.
- `config/runtime_command_types.yaml:9-37` — bảng khai báo: `SubmitPrompt=next_checkpoint`, `StopAgentTurn=immediate`, `ApproveCheckpoint=immediate_if_waiting`...
- `ui/ide/server.py:127-175` — `IdeControlServer.submit_command()` = **Invoker**: validate (131-135) → dedup map idempotency (143-156) → `_dispatch()` (160-175) route `SubmitPrompt` → `runner.start()` (171).
- `ui/ide/runner.py:90` — `AgentRunner.start(prompt)` = **Receiver** của `SubmitPrompt` (trả `None` nếu đã có run).

---

## 2. Trích đoạn code thật

`RuntimeCommand` — command bất biến, validate ngay (`control/commands.py:61-81`):

```python
@dataclass(frozen=True)
class RuntimeCommand:
    command_type: str
    session_id: str
    issued_by: IssuedBy
    idempotency_key: str
    payload: dict[str, Any] = field(default_factory=dict)
    command_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_utc_now)
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in ("command_id", "command_type", "session_id", "idempotency_key", "created_at"):
            if not getattr(self, name):
                raise ControlContractError(f"RuntimeCommand.{name} is required and must be non-empty.")
        ...
        if self.schema_version < 1:
            raise ControlContractError("RuntimeCommand.schema_version must be >= 1.")
```

Invoker: validate → dedup (idempotency) → dispatch (`ui/ide/server.py:131-158`):

```python
cmd = parse_command(body)
self.command_registry.assert_known(cmd.command_type)
...
key = (cmd.session_id, cmd.idempotency_key)
with self._dedup_lock:
    if key in self._dedup:
        return 200, self._dedup[key]  # idempotent replay → same ack, run dispatched once
    seq = session.emit("command.received", {...})
    ack = CommandAck(command_id=cmd.command_id, status="received", seq=seq)
    self._dedup[key] = ack.as_dict()
self._dispatch(cmd.session_id, cmd.command_type, cmd.payload)
```

Dispatch route `SubmitPrompt` tới Receiver (`ui/ide/server.py:160-172`):

```python
def _dispatch(self, session_id, command_type, payload) -> None:
    ...
    if command_type == "SubmitPrompt":
        prompt = str(payload.get("prompt") or "").strip()[:MAX_PROMPT_CHARS]
        if not prompt:
            return
        if runner.start(prompt, ...) is None:
            session.emit("command.rejected", {"reason": "a run is already active"})
```

Chiến lược lên lịch khai báo bằng dữ liệu (`config/runtime_command_types.yaml:13-16, 30`):

```yaml
StopAgentTurn:     { apply_at: immediate,            requires_permission: null }
SubmitPrompt:      { apply_at: next_checkpoint,      requires_permission: null }
ApproveCheckpoint: { apply_at: immediate_if_waiting, requires_permission: checkpoint.approve }
```

---

## 3. Ánh xạ vai trò pattern ↔ code thật

| Vai trò trong Command | Thành phần trong hex_agent | File:line |
|---|---|---|
| **ConcreteCommand** | `RuntimeCommand` (frozen, validate `__post_init__`) | `control/commands.py:61-106` |
| **Factory/Parser** | `parse_command(data)` | `control/commands.py:156-166` |
| **Metadata attribution** | `IssuedBy` | `control/commands.py:33-58` |
| **Chiến lược lên lịch (queue)** | `CommandTypeRegistry.apply_at()` | `control/command_registry.py:53-54` |
| **Khai báo lịch bằng dữ liệu** | bảng `apply_at` trong YAML | `config/runtime_command_types.yaml:9-37` |
| **Invoker** | `IdeControlServer.submit_command()` | `ui/ide/server.py:127-158` |
| **Router** | `_dispatch()` | `ui/ide/server.py:160-175` |
| **Receiver** | `AgentRunner.start()` | `ui/ide/runner.py:90` |
| **Chống replay** | dedup map theo `idempotency_key` | `ui/ide/server.py:143-156` |

---

## 4. Bản rút gọn chạy được

File: [`runtime_command_dispatch.py`](./runtime_command_dispatch.py)

**Mô phỏng đúng**: `RuntimeCommand` + `IssuedBy` (frozen + validate `__post_init__`, gồm `schema_version >= 1` và `agent` phải có `agent_id` — khớp `commands.py:47, 70, 80-81`), `parse_command` (reject thiếu `idempotency_key`/`issued_by`), `CommandTypeRegistry` với bảng `apply_at` **giữ nguyên giá trị** từ `runtime_command_types.yaml`, `IdeControlServer.submit_command` (validate → dedup idempotency → emit seq → `_dispatch`), và `FakeRunner.start` (Receiver, từ chối khi đã active).

Demo chứng minh:
- `apply_at` khác nhau theo loại command: `SubmitPrompt=next_checkpoint`, `StopAgentTurn=immediate`, `ApproveCheckpoint=immediate_if_waiting` — đây là **chiến lược queue/schedule** đính kèm từng command.
- **Idempotency**: submit lại đúng command (cùng `idempotency_key`) → trả ack cũ, Receiver **chỉ chạy một lần** (`server.py:143-156`).
- `StopAgentTurn` (immediate) huỷ run ngay.
- Thiếu `idempotency_key` → HTTP 400 reject; `command_type` lạ → reject.
- `IssuedBy(type="human")` thiếu `user_id` → hỏng ngay khi tạo command; `IssuedBy(type="agent")` thiếu `agent_id` cũng hỏng (đúng "command phải đủ context", `commands.py:45-47`).
- `schema_version < 1` → `RuntimeCommand` reject ngay ở `__post_init__` (`commands.py:80-81`); mặc định `schema_version = 1`.
- Mỗi command để lại event (`command.received`, `run.stopped`) → log/replay/audit được.

**Đã lược bỏ** so với bản thật: HTTP server thật + token auth + CORS (`server.py:103-125, 188-200`), đọc YAML qua thư viện `yaml` (thay bằng dict stdlib giữ nguyên giá trị), `IdeSession`/`EventReplayBuffer` đầy đủ + redaction + SSE (`ui/ide/session.py`, `control/replay.py`), threading/locks, `CommandAck.seq` tương quan vào SSE, và các command type còn lại của YAML. Giữ đúng **xương sống Command** ở control-plane.

Chạy:

```bash
python3 runtime_command_dispatch.py
```

---

## 5. Cái giá / khi nào KHÔNG nên dùng

- **Boilerplate.** Mỗi thao tác UI giờ phải đóng gói thành command + khai báo trong registry. Với một nút bấm cục bộ, không trạng thái, không cần audit, đây là thừa.
- **`apply_at` sai → hành vi nguy hiểm.** `StopAgentTurn` phải là `immediate`; nếu để `next_checkpoint`, lệnh dừng sẽ kẹt trong hàng đợi khi agent đang vòng lặp — đúng tinh thần "Invoker là điểm điều phối, lên lịch sai thì hỏng" (bài học Parkinson trong `14_Command.md`).
- **Idempotency chỉ là một cửa sổ.** Bản thật giới hạn dedup map (`MAX_DEDUP_ENTRIES`, `server.py:46, 153-155`); một replay rất muộn sau khi key bị trục xuất có thể chạy lại. Command + dedup không thay thế được idempotency phía Receiver cho các tác vụ tối quan trọng.
- **Attribution ≠ authz.** `issued_by` chỉ **ghi nhận** ai bấm (tự khai), KHÔNG phải bằng chứng quyền (`control/commands.py:31-32`, `control/authz.py:1-11`). Đừng dùng nó để ra quyết định phân quyền.

---

## 6. Câu hỏi tự kiểm tra

1. Vì sao `idempotency_key` là **bắt buộc** trong `RuntimeCommand`? Điều gì xảy ra khi người dùng bấm nút "Send" hai lần và mạng retry, nếu KHÔNG có nó? (Gợi ý: `server.py:143-156`.)
2. `apply_at` đóng vai trò gì trong Command pattern — nó tương ứng với "queue/schedule" như thế nào? Vì sao `StopAgentTurn` là `immediate` còn `SubmitPrompt` là `next_checkpoint`?
3. Phân biệt `issued_by` (attribution) và `requires_permission` (authz). Vì sao bản thật tách hai khái niệm này (`control/commands.py:31-32`, `control/authz.py`)? Một issuer "tự khai là admin" có được tin không?
