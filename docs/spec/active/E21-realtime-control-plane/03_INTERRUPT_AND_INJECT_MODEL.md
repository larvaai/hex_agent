# E21 — Mô hình Ngắt & Chen ngang (Interrupt & Inject)

> Tinh chỉnh hành vi cho [`01_...md` B4](01_BACKEND_STANDARDIZATION_BEFORE_UI.md) và story S21.11. Điểm cốt lõi: **vì đã có checkpoint/resume, "Stop now" giữa lúc sinh token là an toàn** — ta chỉ vứt phần *chưa commit*, checkpoint vẫn nguyên, rồi resume **từ checkpoint đó kèm thay đổi chen ngang**.

## 1. Tôi hiểu đúng chưa (phát biểu lại)

Khi user chen một thay đổi vào giữa run (hook mới · agent mới · system prompt mới · skill mới · instruction mới):

- **Checkpoint = điểm commit an toàn cuối cùng** (`ctx.save` sau mỗi turn [supervisor/graph.py:189](../../../../supervisor/graph.py) và mỗi round [supervisor/loop.py:183](../../../../supervisor/loop.py)).
- Một worker turn **hoặc commit trọn vẹn, hoặc bị bỏ trọn** — không có commit dở. Token đang sinh là **chưa commit**.
- Vì vậy có thể **dừng ngay**, vứt token dở, **reload state từ checkpoint cuối**, **áp thay đổi**, rồi **re-run từ đó** với cấu hình mới.

Ba chế độ khi user submit một injection lúc agent đang chạy:

| Chế độ | Hành vi | Khi nào |
|---|---|---|
| **Wait** *(mặc định)* | Command vào hàng đợi (`apply_at=next_checkpoint`). Turn hiện tại **chạy xong & commit**. Tại safe-point kế, `apply_pending_commands_at_checkpoint()` áp thay đổi rồi loop tiếp. | Mặc định, không phá token đang sinh. |
| **Stop now** | User bấm **Stop** trên node agent → gửi cancel tới generation đang chạy → agent **dừng sinh token**. Token dở **mặc định bị vứt khỏi workflow** (không commit, không feed-forward), nhưng **được giữ lại để xem** (gắn `aborted`, hiển thị trong cửa sổ stream). Runtime **reload từ checkpoint cuối** (turn dở **không** persist), áp command đang chờ, **re-run từ checkpoint** với cấu hình mới. | User cần chen gấp, chấp nhận bỏ output dở. |
| **Ask** | Khi submit injection lúc agent đang chạy, popup hỏi: *"Dừng ngay để chen, hay đợi turn hiện tại xong?"*. **Timeout 5s** → không trả lời thì **mặc định Wait**. | Khi muốn hỏi rõ ý người. |

**Phạm vi Stop = từng agent, KHÔNG phải cả session.** `StopAgentTurn(session_id, agent_id)` chỉ hủy generation của **một** agent; các agent khác trong cùng round/session **vẫn chạy bình thường**. Muốn dừng toàn bộ thì dùng `PauseWorkflow` (cấp session).

## 2. State machine bổ sung

Mở rộng tập trạng thái (S21.38) với nhánh ngắt:

```
running ──(Pause)──────────▶ pause_requested ──(tới safe-point)──▶ paused
running ──(Stop now)───────▶ stop_requested ──(cancel nhận)──▶ aborting ──(reload checkpoint)──▶ paused
paused  ──(Resume, có injection đã áp)──▶ resuming ──▶ running
```

- `pause_requested` / `stop_requested` là *ý định*; chỉ thành `paused` khi runtime tới điểm an toàn (Pause) hoặc khi generation đã thật sự hủy (Stop).
- `aborting` là cửa sổ giữa "nhận lệnh cancel" và "đã reload sạch về checkpoint".

## 3. Bất biến (luật đúng-đắn — phần dễ sai nhất)

1. **Chỉ vứt phần chưa commit.** Checkpoint cuối (state đã `ctx.save`) bất biến qua Stop. Turn bị ngắt **không bao giờ** để lại artifact/turn nửa vời trong store.
2. **Resume = reload, không tái dùng in-memory.** Sau Stop, runtime **đọc lại** `SqliteTaskLoopStore.load()` ([supervisor/checkpoint.py:45](../../../../supervisor/checkpoint.py)) — **không** dùng tiếp `TaskLoopState` đã bị mutate dở trong RAM (vd `context_packet` artifact đã add trước khi `delegate()` xong tại [supervisor/graph.py:142](../../../../supervisor/graph.py)). Đây đúng đường `resume_task_loop` đang làm ([supervisor/loop.py:103](../../../../supervisor/loop.py)).
3. **Không double-execute hiệu ứng.** Nếu turn dở **đã** chạy một tool `kind=effect, idempotent=False` (S10.13) **trước** khi bị Stop, re-run **không** được chạy lại mù: dedup theo `idempotency_key`, hoặc reconcile (S21.24). Tool đã commit + idempotent thì bỏ qua khi gặp lại.
4. **Injection hiệu lực từ checkpoint được áp.** `effective_from=next_checkpoint` (S21.12) — turn re-run dùng **cấu hình mới** (system prompt/skill/hook mới) hoặc có thêm agent mới tham gia.
5. **UI không hiểu nhầm output dở là kết quả.** Token của turn bị ngắt gắn cờ `aborted` (event `agent.aborted`); UI không hiển thị nó như `agent.output.validated`. Output dở **được giữ lại để xem** trong cửa sổ stream (mục §7), nhưng **mặc định bị loại khỏi workflow** — không commit, không làm input cho turn re-run. (User có thể chủ động copy/giữ, nhưng nó không bao giờ tự động feed-forward.)

## 4. Cái gì được "chen ngang" (command types)

| Injection | Command | apply_at | Ghi chú |
|---|---|---|---|
| Thêm agent | `AddAgentToLoop` | next_checkpoint | đã có (S21.13) |
| Sửa instruction / **system prompt** | `EditAgentInstruction` / `SetSystemPrompt` | next_checkpoint | system prompt = trường hợp riêng của instruction |
| Thêm **hook** | `InjectHook` | next_checkpoint | hook chạy ở hook_point từ turn kế (S21.27) |
| Thêm **skill** | `AddSkill` | next_checkpoint | resolve skill cho agent từ turn kế (S21.28) |
| Sửa quyền | `UpdateAgentPermission` | next_checkpoint | đã có (S21.12) |
| Dừng phiên | `StopAgentTurn` | immediate (cancel) | kích hoạt nhánh Stop-now |
| Tạm dừng | `PauseWorkflow` | next_checkpoint | nhánh Wait |

`StopAgentTurn` là command **immediate** (không đợi checkpoint) — nó *gây ra* việc về checkpoint, khác mọi command khác (đều `next_checkpoint`).

## 5. Gap backend mới mà mô hình này lộ ra (→ B10)

**Generation hiện KHÔNG hủy được.** `delegation_service.delegate(...)` ([supervisor/graph.py:156](../../../../supervisor/graph.py)) chạy **blocking** tới khi xong; không có cancellation token tới tận lời gọi LLM. Để có nút **Stop**, cần:

- Luồng một **cancellation token** qua `delegate()` → adapter agent → `llm.chat`, kiểm tra hợp tác (cooperative) tại ranh giới step/stream để dừng sớm.
- Worker turn chạy ở luồng/đối tượng **hủy được** (không chặn vòng `_drive` vĩnh viễn); UI gửi `StopAgentTurn` → runtime set cancel → turn thoát với trạng thái `aborted`.
- Đảm bảo **atomicity tại biên turn**: artifact của turn chỉ "thật" sau `ctx.save`; abort trước `ctx.save` ⇒ reload checkpoint là sạch.

Đây là **việc backend, phải có trước khi UI có nút Stop hoạt động** (nút Stop mà không hủy được generation thì chỉ là giả vờ). Xem **B10** trong [`01_BACKEND_STANDARDIZATION_BEFORE_UI.md`](01_BACKEND_STANDARDIZATION_BEFORE_UI.md).

## 6. UI node agent (đặc tả từ mô tả của bạn)

- Mỗi agent = **node tròn** trong Agent Graph (S21.18).
- **Hover** hiện cụm control: **Stream** (xem token) · Stop · Inspect · (Edit permission) · (Edit instruction).
- **Stream**: bấm → mở **cửa sổ/panel riêng** xem token sinh **live** của agent đó (§7). Opt-in (không bật mặc định để tránh ngập timeline).
- **Stop**: bấm → gửi `StopAgentTurn(session_id, agent_id)`; node chuyển `aborting`→`paused`; output dở hiển thị mờ + nhãn *aborted*, vẫn xem được trong cửa sổ stream.
- Khi user submit một injection lúc node đang `running`: theo cấu hình, hoặc **Wait** (mặc định, badge "sẽ áp ở checkpoint kế"), hoặc bật **popup Ask** (timeout 5s → Wait).
- Sau khi áp injection + **Resume**: node re-run, UI thấy turn mới (cấu hình mới) qua event stream — **không** mutate graph trực tiếp.

## 7. Stream token & cửa sổ xem output

- **Hiện trạng:** `call_llm` ([llm/adapter.py:67](../../../../llm/adapter.py)) gọi `chat.completions.create` **blocking, không stream**; chỉ có stream cấp-**bước** qua `delegation.progress`/`progress_sink` ([delegation/manager.py:142](../../../../delegation/manager.py)), **chưa** có stream cấp-**token**.
- **Cần thành (B11):** `call_llm` hỗ trợ `stream=True` + một **token-sink** luồng qua `handler.run → delegate` (song song `progress_sink`); runtime phát `agent.token` (delta) **coalesce theo nhịp** (gộp chunk, lớp event "debug" — bị backpressure điều tiết theo S21.40, **không** drop event critical).
- **Cửa sổ stream:** mỗi agent một sub-stream `agent.token` riêng; UI mở panel theo `agent_id`, hiển thị live; đóng panel ⇒ ngừng nhận delta (server giảm tải). Token vẫn đi qua **redaction** (S21.7) trước khi rời ra UI. **Chỉ live** — `agent.token` **không lưu durable để replay** (chỉ bản ghép cuối `agent.output.raw` được lưu). **Mặc định 1 panel**: mở panel stream mới sẽ đóng panel đang mở (không xem đồng thời nhiều agent).
- **Cùng seam với cancel (B10):** vòng lặp đọc stream chính là chỗ kiểm `cancel` hợp tác giữa các chunk — stream **làm cancel dễ hơn** (dừng giữa hai delta thay vì chờ cả block).
- **Quan hệ với output cuối:** `agent.token` = các delta sống; `agent.output.raw` (S21.30) = bản ghép cuối; `agent.output.validated` = sau json-gate. Turn bị Stop ⇒ stream đóng với cờ `aborted`, **không** sinh `agent.output.validated`.

## 8. Liên hệ story
S21.11 (intervention points) · S21.12 (effective_from) · S21.24 (resume an toàn) · S10.13 (capability kind) · **S21.46–S21.52** (mục *S-INTERRUPT* trong [`stories.md`](stories.md)) · B10/B11 trong [`01_BACKEND_STANDARDIZATION_BEFORE_UI.md`](01_BACKEND_STANDARDIZATION_BEFORE_UI.md).
