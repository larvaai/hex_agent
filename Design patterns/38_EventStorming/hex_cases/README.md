# Event Storming trong hex_agent — hex_cases

> Tài liệu dạy học: pattern **Event Storming (Domain Event Discovery)** xuất hiện THẬT trong codebase `hex_agent` như thế nào, và cách distill nó thành code stdlib chạy được.

---

## 0. Một dòng nối với bài học gốc

Bài học gốc `38_EventStorming.md` dạy Event Storming như một **kỹ thuật workshop** (sticky note 7 màu trên tường: orange=event, blue=command, green=read model...). hex_agent **không** chạy workshop — nhưng nó *đông cứng kết quả của một workshop* vào code: vocabulary của domain (event past-tense + command imperative) được đăng ký tường minh trong registry, mọi sự kiện đi qua một "facilitator" (EventEmitter) để được validate + đánh số + che secret, và các read model (snapshot) được *fold* ra từ chuỗi event thay vì tự sửa state.

Nói cách khác: **Event Storming là design-time; hex_agent là cái cây mọc ra từ thiết kế đó ở run-time.** Sticky note "session.started", "tool.call_requested", "PauseWorkflow" không nằm trên tường — chúng nằm trong `config/*.yaml` và bị từ chối nếu chưa được khai báo.

---

## 1. Pattern này biểu hiện ra sao trong hex_agent

hex_agent hiện thực Event Storming qua **control plane hướng sự kiện** (Epic E21). 5 mảnh ghép:

1. **Domain event = fact thì quá khứ** (sticky orange):
   `session.started`, `agent.before_run`, `tool.call_requested`, `loop.team_composed`, `task.completed`... Mỗi event là một bản ghi bất biến đã-xảy-ra. Khai báo trong `config/runtime_event_types.yaml` (60+ event).
2. **Command = hành động ra lệnh** (sticky blue):
   `PauseWorkflow`, `ApproveCheckpoint`, `SubmitPrompt`... do người/agent phát ra. Khai báo trong `config/runtime_command_types.yaml` (17 command). UI không bao giờ sửa state trực tiếp — nó gửi command.
3. **Registry = bức tường sticky note**:
   `control/event_registry.py` + `control/command_registry.py`. Một event/command lạ (chưa dán lên tường) bị từ chối ngay. Đây chính là cơ chế "ép vocabulary domain" của Event Storming.
4. **EventEmitter = facilitator của workshop**:
   `control/emitter.py`. Trước khi publish, nó (a) kiểm tra event_type với registry, (b) đóng dấu `seq` tăng đơn điệu, (c) redact `ui_payload`, (d) fan-out tới các sink.
5. **Projection = read model** (sticky green):
   `control/snapshot.py` — `TaskLoopSnapshot` *fold* chuỗi `loop.*` event thành một view cho UI. Event là nguồn sự thật; projection chỉ là hàm thuần của chuỗi event.

So với 5 invariant của Event Storming output trong bài gốc (mục 2.4): event past-tense, command imperative, mỗi event được trigger bởi command/policy, mỗi aggregate gom quanh ≥ vài event, mỗi bounded context có read model — hex_agent thoả gần hết: bounded context ẩn (session lifecycle / agent / tool / permission / command / artifact / loop) lộ ra qua cách event được nhóm theo tiền tố trong YAML.

---

## 2. Các case con

| # | Thư mục | Flagship | Distill từ file thật |
|---|---------|----------|----------------------|
| 01 | `01_control_plane_event_storming/` | Event + Command + Registry ở quy mô control-plane | `control/events.py`, `control/commands.py`, `control/event_registry.py`, `control/command_registry.py`, `config/*.yaml`, `control/emitter.py` |
| 02 | `02_event_projection_snapshot/` | Event Projection: fold `loop.*` event thành `TaskLoopSnapshot` | `control/snapshot.py`, `supervisor/graph.py` |

Mỗi thư mục có `README.md` (bài học 6 mục) và 1 file `.py` self-contained chạy bằng `python3`.

---

## 3. Catalog đầy đủ

Xem `CATALOG.md` — bảng vét cạn MỌI nơi pattern xuất hiện trong codebase (path:line + mô tả + độ rõ).

---

## 4. Cách chạy

```bash
python3 01_control_plane_event_storming/control_plane_event_storming.py
python3 02_event_projection_snapshot/event_projection_snapshot.py
```

Mỗi script chỉ dùng thư viện chuẩn Python 3, in narration tiếng Việt từng bước, có đối chứng "khi KHÔNG dùng pattern thì hỏng thế nào", và có `assert` chứng minh bất biến của pattern.

---

## 5. Lưu ý trung thực

Các file `.py` ở đây là **bản distill** — giữ đúng vai trò/cấu trúc pattern nhưng:
- Đổi tên cho dễ đọc (ví dụ giữ nguyên `RuntimeEvent`/`EventEmitter` vì chúng đã rõ).
- Thay YAML thật bằng dict Python nhúng trong code (vẫn giữ ý "khai báo tập trung").
- Thay LLM/orchestrator/broker/DB thật bằng fake tối thiểu bằng stdlib.

Docstring đầu mỗi file ghi rõ path:line nguồn thật để bạn đối chiếu.
