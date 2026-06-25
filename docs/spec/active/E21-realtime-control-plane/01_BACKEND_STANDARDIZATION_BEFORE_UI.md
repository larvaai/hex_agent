# E21 — Những thứ phải chuẩn hoá ở BACKEND trước khi làm UI

> Đây là phần bạn dặn riêng. UI chỉ "vẽ" được khi backend đã có **9 thứ chuẩn hoá** dưới đây. Nếu làm UI trước, mỗi panel sẽ phải tự đoán shape dữ liệu, tự mutate state ⇒ vỡ đúng cái luật bất biến "UI không sửa state trực tiếp".
>
> Mỗi mục: **Hiện trạng → Cần thành → Vì sao phải trước UI → Chạm vào đâu → Done when**. Thứ tự cũng là thứ tự build (B1 trước, B9 sau). Xem bối cảnh ở [`00_UNDERSTANDING_AND_RECONCILIATION.md`](00_UNDERSTANDING_AND_RECONCILIATION.md).

---

## B1. Chuẩn hoá envelope sự kiện (RuntimeEvent) + registry

- **Hiện trạng:** `EventBus.publish(topic, payload)` nhận dict tự do, fire-and-forget, nuốt lỗi ([core/events.py:22](../../../../core/events.py)). `EventLogger` mới đóng dấu `sequence/timestamp/run_id/kind` lúc ghi JSONL ([observability/event_log.py:60](../../../../observability/event_log.py)). Mỗi nơi emit một shape khác nhau.
- **Cần thành:** một **envelope duy nhất** cho mọi event: `event_id`, `event_type`, `schema_version`, `session_id`, `seq` (đơn điệu/session), `round_no`, `actor{type,id}`, `trace{trace_id,span_id,parent}`, `payload`, `ui_payload`, `redaction{level,has_secret,redacted_fields}`, `created_at`. Kèm **event-type registry** (YAML): mỗi type khai `visibility` (`public/ui_safe/internal/secret`), `durable`, `redact_for_ui`, `checkpoint_candidate`. Event lạ bị từ chối.
- **Vì sao trước UI:** Timeline/Graph/Inspector đọc đúng **một** shape; nếu không, UI parse N format và sẽ vỡ mỗi lần thêm event mới.
- **Chạm vào đâu:** bọc `EventBus.publish` qua một `emit_event(RuntimeEvent)`; cập nhật mọi `ctx.emit(...)` trong [supervisor/graph.py:52](../../../../supervisor/graph.py) và `loop.py`; `attach_to_bus` ([observability/event_log.py:102](../../../../observability/event_log.py)) ghi envelope thay vì dict thô.
- **Done when:** emit event thiếu field bắt buộc → reject; event không có trong registry → reject; round-trip encode/decode có test (giống `tests_audit/test_contract_roundtrips.py`).

## B2. Phóng chiếu **live status** vào snapshot (cái UI thật sự vẽ)

- **Hiện trạng:** `TaskLoopState` có `selected_agents` + `turns` + `acceptance_checks` ([supervisor/state.py:80](../../../../supervisor/state.py)) nhưng **không** có trạng thái sống mỗi agent, không `orchestrator.last_decision`, không `pending_agent_calls`, không danh sách checkpoint đang chờ.
- **Cần thành:** một `TaskLoopSnapshot` (read-model) chứa: `status`, `round_no`, `orchestrator{last_decision,reason}`, `agents[]{agent_id,role,status∈pending|waiting|running|done|failed,round_no}`, `pending_agent_calls[]`, `tool_calls[]`, `checkpoints[]`, `acceptance_status[]`, `last_updated_at`. Suy ra **từ event/Blackboard**, không phải state thứ hai để UI ghi vào.
- **Vì sao trước UI:** Graph-view + Queue-panel chỉ là hàm thuần của snapshot này; chưa có nó thì không vẽ được "ai running / ai pending".
- **Chạm vào đâu:** mở rộng `_state_view`/thêm `build_snapshot(state, events)`; tận dụng status enum sẵn có ([supervisor/state.py:14](../../../../supervisor/state.py)).
- **Done when:** từ một chuỗi event của 1 run, `build_snapshot` cho ra graph đúng (test: O→A done, B running, C pending).

## B3. **RuntimeCommand** + queue + idempotency (chưa có gì cả)

- **Hiện trạng:** không tồn tại. UI hiện chỉ `POST /api/runs` để *bắt đầu* run ([ui/server.py:482](../../../../ui/server.py)) — không có lệnh điều khiển.
- **Cần thành:** schema `RuntimeCommand{command_id, command_type, schema_version, session_id, issued_by{type,user_id|agent_id}, payload, idempotency_key, created_at}`; **command-type registry** (YAML) khai `apply_at` (`next_checkpoint|immediate_if_waiting`) và `requires_permission`; bảng SQLite `commands(command_id PK, idempotency_key UNIQUE, status, rejection_reason, applied_at, …)`; vòng đời `received→accepted|rejected→applied`, mỗi bước phát event.
- **Vì sao trước UI:** UI "kéo-thả agent / sửa quyền / approve" **chỉ là** phát command. Không có contract+queue+idempotency thì nút bấm không có chỗ đi, và double-click sẽ áp dụng hai lần.
- **Chạm vào đâu:** mở rộng `SqliteTaskLoopStore` ([supervisor/checkpoint.py:22](../../../../supervisor/checkpoint.py)) thành control-store (thêm bảng); thêm `submit_command()` / `accept_at_checkpoint()`.
- **Done when:** cùng `idempotency_key` gửi 2 lần ⇒ áp dụng 1 lần (test); command thiếu field/`command_type` lạ ⇒ reject + event `command.rejected`.

## B4. **Checkpoint / intervention points** trong vòng lặp (tách state-checkpoint khỏi approval-gate)

- **Hiện trạng:** đã có **điểm dừng state** (`ctx.save` mỗi round [supervisor/loop.py:183](../../../../supervisor/loop.py), sau mỗi turn [supervisor/graph.py:189](../../../../supervisor/graph.py)) — nhưng đây là *lưu để resume*, **không** phải *dừng chờ người duyệt*.
- **Cần thành:** (a) đặt tên các safe-point: `before_round_start`, `after_agent_result`, `before_tool_call`, `before_acceptance_review`, `when_blocked`; (b) cờ `pause_requested`; (c) `apply_pending_commands_at_checkpoint()` chạy đúng các điểm này; (d) `RuntimeCheckpoint{checkpoint_id,type,status∈waiting|approved|rejected|expired|auto_approved,risk_level,payload,resolved_at}` cho hành động nguy hiểm (tool high-risk, ghi file, shell, đổi quyền, overwrite artifact).
- **Vì sao trước UI:** đây là chỗ "thay đổi realtime chỉ áp dụng tại checkpoint an toàn" của bạn. Approval-modal của UI **trỏ vào** checkpoint `waiting`; chưa có nó thì modal không có dữ liệu.
- **Chạm vào đâu:** chèn hook vào `_drive()` ([supervisor/loop.py:141](../../../../supervisor/loop.py)) ngay trước `o_decide`/`run_tool`; tận dụng `run_tool` đã đi qua `execute_tool` ([supervisor/graph.py:194](../../../../supervisor/graph.py)).
- **Done when:** **Wait** (mặc định) — `Pause`/injection không kill agent đang chạy mà áp ở checkpoint kế; **Stop now** — `StopAgentTurn` hủy generation, reload checkpoint cuối, áp injection, re-run (xem B10 + [`03_INTERRUPT_AND_INJECT_MODEL.md`](03_INTERRUPT_AND_INJECT_MODEL.md)); tool high-risk **không chạy** khi checkpoint chưa `approved`; kill giữa chừng rồi resume thì checkpoint vẫn `waiting` (không chạy lại turn đã xong).

## B5. **Permission record** do người chỉnh (session+agent, effective_from=next_checkpoint)

- **Hiện trạng:** scope do O đặt **per-turn** qua `DelegationPolicy.allowed_capabilities` ([supervisor/graph.py:155](../../../../supervisor/graph.py)); người **không** sửa được qua bản ghi bền; không có `effective_from`.
- **Cần thành:** bảng `permissions(session_id, agent_id, permissions_json, effective_from, created_at)` *append-only* (giữ lịch sử). Runtime đọc bản mới nhất **tại biên checkpoint/turn**, không giữa lúc agent đang chạy. Đổi quyền high-risk phải qua approval-checkpoint (B4).
- **Vì sao trước UI:** Permission Editor sửa quyền = phát `UpdateAgentPermission` command (B3) → áp ở checkpoint (B4). Chưa có store + effective_from thì "sửa quyền realtime" không an toàn.
- **Chạm vào đâu:** đan vào `PolicyGate` ([middleware/policy.py:9](../../../../middleware/policy.py)) + `DelegationPolicy` để gate đọc quyền mới nhất.
- **Done when:** đổi quyền không có hiệu lực giữa turn; có hiệu lực từ checkpoint kế; lịch sử quyền không bị ghi đè (audit được).

## B6. **Redaction boundary** trước khi payload rời ra UI/SSE

- **Hiện trạng:** **không** redact event payload. UI chỉ chặn *file* nhạy cảm (`SENSITIVE_NAMES/SUFFIXES`, [ui/server.py:49](../../../../ui/server.py)). Raw prompt/API key/secret hiện sẽ lọt nếu được đẩy ra event.
- **Cần thành:** tách `payload` (nội bộ) khỏi `ui_payload` (đã redact); engine redact theo key bí mật (`api_key/authorization/password/token/access_token/refresh_token`, kể cả lồng nhau) + theo `visibility` của registry (B1). SSE/UI **chỉ** dùng `ui_payload`; thiếu `ui_payload` thì gateway **không** được tự đẩy raw.
- **Vì sao trước UI:** một khi UI có Payload Inspector, mọi event chảy ra trình duyệt — phải redact *trước*, không thể vá sau.
- **Chạm vào đâu:** đặt redactor ngay trong `emit_event` (B1) trước khi vào EventLogger/SSE; SSE `_stream` ([ui/server.py:517](../../../../ui/server.py)) phát `ui_payload`.
- **Done when:** test: event chứa `api_key` ⇒ không xuất hiện trong payload SSE; `redacted_fields` liệt kê đúng. (Phù hợp tinh thần `tests_audit/`.)

## B7. Đưa **pending_human_commands** vào input của Agent O

- **Hiện trạng:** `o_decide` đọc `_state_view(state)` ([supervisor/graph.py:88](../../../../supervisor/graph.py),[:105](../../../../supervisor/graph.py)) — **không** có lệnh người. O chưa "nghe lệnh có cấu trúc".
- **Cần thành:** `_state_view` thêm `pending_human_commands[]` = các command **đã accepted/validated** (không phải text thô từ UI). Prompt O có luật: ưu tiên xem xét, **không** áp nếu vi phạm policy, nếu áp thì tạo `AgentInvocation`, nếu không thì giải thích lý do; O xuất `applied_human_commands[]` + `next_agent_calls[]`.
- **Vì sao trước UI:** đây là chỗ "kéo-thả agent X" biến thành hành động thật — O phải nhận command **đã qua gate**, không đọc WebSocket thô. Đây là backend-contract, không phải việc UI.
- **Chạm vào đâu:** `_state_view` + `LLMOrchestrator` prompt ([supervisor/llm.py](../../../../supervisor/llm.py)); `run_round` đã có authority-check để chặn agent không được chọn ([supervisor/graph.py:122](../../../../supervisor/graph.py)).
- **Done when:** command `AddAgentToLoop` accepted ⇒ O tạo `AgentInvocation` cho agent X với đúng role/scope; command vi phạm policy ⇒ O từ chối kèm lý do (test offline với `ScriptedOrchestrator`).

## B8. **Audit log** có actor (append-only)

- **Hiện trạng:** `events.jsonl` có nhưng chưa cấu trúc thành audit ai-làm-gì cho command/permission/approval.
- **Cần thành:** mọi command (received/accepted/rejected/applied), đổi quyền (old/new diff + người + thời điểm + link checkpoint), approve/reject checkpoint, tool call (args đã redact) → ghi audit query được theo `session/actor/type/time`.
- **Vì sao trước UI:** Replay panel + câu hỏi "vì sao agent X được thêm, ai thêm, round nào" cần audit. Rẻ nếu làm cùng B1/B3; đắt nếu retrofit.
- **Chạm vào đâu:** tái dùng EventLogger/JSONL + bảng SQLite `audit`; actor lấy từ `issued_by` của command (B3).
- **Done when:** từ audit, dựng lại được dòng thời gian can thiệp của 1 session; không có command/permission-change nào thiếu audit.

## B9. **Authz tối thiểu** trên bề mặt điều khiển

- **Hiện trạng:** `ui/server.py` chạy localhost **không xác thực**; có CSP/same-origin headers ([ui/server.py:389](../../../../ui/server.py)) nhưng bất kỳ ai gọi localhost đều chạy được run.
- **Cần thành:** trước khi cho **mutate** (gửi command): token theo session / kiểm same-origin + khái niệm `issued_by` (ai phát lệnh). Đọc (snapshot/SSE) có thể nới hơn ghi.
- **Vì sao trước UI:** ngay khi command có thể đổi quyền/đổi workflow, kênh ghi không thể vô danh; và `issued_by` là field bắt buộc của command (B3) + audit (B8).
- **Chạm vào đâu:** middleware ở `AgentUIHandler` ([ui/server.py:379](../../../../ui/server.py)); endpoint mới `POST /api/commands`.
- **Done when:** command không kèm token hợp lệ ⇒ bị từ chối + audit; mọi command áp dụng đều có `issued_by` không rỗng.

## B10. **Generation hủy được** (cho nút Stop — xem [`03_INTERRUPT_AND_INJECT_MODEL.md`](03_INTERRUPT_AND_INJECT_MODEL.md))

- **Hiện trạng:** `delegation_service.delegate(...)` ([supervisor/graph.py:156](../../../../supervisor/graph.py)) chạy **blocking** tới khi xong; không có cancellation token tới tận `llm.chat`. Không thể dừng một turn giữa lúc sinh token.
- **Cần thành:** luồng **cancellation token** qua `delegate()` → adapter agent → LLM, kiểm tra hợp tác tại biên step/stream; worker turn chạy ở đối tượng **hủy được** (không chặn `_drive` vĩnh viễn); `StopAgentTurn` → set cancel → turn thoát `aborted`, phát `agent.aborted`; **atomicity tại biên turn** (artifact chỉ "thật" sau `ctx.save`, abort trước đó ⇒ reload checkpoint là sạch).
- **Vì sao trước UI:** nút **Stop** mà không hủy được generation chỉ là giả vờ. Đây là điều kiện-cần để chế độ **Stop now** hoạt động.
- **Chạm vào đâu:** `DelegationServicePort.delegate` ([core/ports.py:65](../../../../core/ports.py)) + adapter; `_drive` ([supervisor/loop.py:141](../../../../supervisor/loop.py)); reload qua `resume_task_loop` ([supervisor/loop.py:103](../../../../supervisor/loop.py)).
- **Done when:** `StopAgentTurn` dừng sinh token < ~1s, turn dở **không** persist artifact; resume reload checkpoint cuối + áp injection + re-run với cấu hình mới; tool `kind=effect,idempotent=False` đã chạy trước Stop **không** bị chạy lại mù (S10.13/S21.24).

## B11. **Token streaming** (cho cửa sổ xem stream — xem [`03_INTERRUPT_AND_INJECT_MODEL.md`](03_INTERRUPT_AND_INJECT_MODEL.md) §7)

- **Hiện trạng:** `call_llm` ([llm/adapter.py:67](../../../../llm/adapter.py)) gọi `chat.completions.create` **blocking, không stream** (`choices[0].message.content`). Đã có stream cấp-**bước** (`delegation.progress`/`progress_sink` [delegation/manager.py:142](../../../../delegation/manager.py)) nhưng **chưa** cấp-**token**.
- **Cần thành:** `call_llm(stream=True)` + **token-sink** luồng qua `handler.run → delegate` (song song `progress_sink`); phát `agent.token` (delta) **coalesce theo nhịp**, lớp "debug" chịu backpressure (S21.40), redact trước khi ra UI (S21.7); mở/đóng panel theo `agent_id` để bật/tắt nhận delta.
- **Vì sao trước UI:** cửa sổ "xem token live" không có dữ liệu nếu adapter không stream. Đây cũng là seam dùng chung với B10 (cancel kiểm giữa hai chunk).
- **Chạm vào đâu:** `call_llm` ([llm/adapter.py:53](../../../../llm/adapter.py)); adapter agent `handler.run`; `progress_sink` pattern ([delegation/manager.py:142](../../../../delegation/manager.py)).
- **Done when:** mở panel ⇒ nhận `agent.token` live (đã redact, coalesced); đóng panel ⇒ ngừng đẩy delta; tải token cao **không** drop event critical; turn Stop ⇒ stream đóng cờ `aborted`, không sinh `agent.output.validated`.

---

## Bảng tổng hợp (checklist gọn)

| # | Hạng mục | Loại | Chặn UI? |
|---|---|---|---|
| B1 | RuntimeEvent envelope + event-type registry | Contract | ✅ bắt buộc |
| B2 | TaskLoopSnapshot read-model (live status) | Projection | ✅ bắt buộc |
| B3 | RuntimeCommand + queue + idempotency | Contract+Store | ✅ bắt buộc |
| B4 | Checkpoint/intervention points + approval-gate | Runtime | ✅ bắt buộc |
| B5 | Permission record do người chỉnh (effective_from) | Store+Gate | ⚠️ cần cho Permission Editor |
| B6 | Redaction boundary (ui_payload) | Security | ✅ bắt buộc |
| B7 | pending_human_commands vào O | Contract+Prompt | ⚠️ cần cho kéo-thả agent |
| B8 | Audit log có actor | Observability | ⚠️ cần cho Replay/audit |
| B9 | Authz tối thiểu cho command channel | Security | ✅ bắt buộc cho mọi mutate |
| B10 | Generation hủy được (cancellation) | Runtime | ⚠️ cần cho nút Stop / "Stop now" |
| B11 | Token streaming (delta + token-sink) | Runtime | ⚠️ cần cho cửa sổ xem stream |

**Tối thiểu để bật UI v1 (chỉ quan sát + approve):** B1, B2, B6, B9 (+ B4 nếu muốn approval-modal).
**Để UI điều khiển đầy đủ (kéo-thả agent, sửa quyền):** thêm B3, B4, B5, B7, B8.
