# E21 — Stories

> Format giống các epic khác: "As X, I … so that …". ID map 1–1 sang [`acceptance.md`](acceptance.md) (Given/When/Then → test E19). Cột slice cho biết thuộc S-CONTRACT/BACKEND/TRANSPORT/UI/CONTROL/RELIABILITY và epic gốc (E16/E17/E18) nếu có.

## S-CONTRACT — hợp đồng đặt sau Port, không I/O

- **S21.1 RuntimeEvent envelope** — As the runtime, mọi event đi qua **một** envelope (`event_id, event_type, schema_version, session_id, seq, round_no, actor, trace, payload, ui_payload, redaction, created_at`) so that UI/audit/replay đọc đúng một shape.
- **S21.2 Event-type registry** — As the runtime, mỗi `event_type` phải khai trong registry YAML (`visibility, durable, redact_for_ui, checkpoint_candidate`) so that event lạ bị từ chối và visibility là khai báo, không tuỳ tiện.
- **S21.3 RuntimeCommand contract** — As the UI, tôi gửi mọi can thiệp qua một `RuntimeCommand` (`command_id, command_type, schema_version, session_id, issued_by, payload, idempotency_key, created_at`) so that runtime xử lý đồng nhất và từ chối lệnh sai shape trước khi vào hàng đợi.
- **S21.4 Command-type registry** — As the runtime, mỗi `command_type` khai `apply_at` (`next_checkpoint|immediate_if_waiting`) + `requires_permission` so that biết khi nào áp dụng và cần quyền gì; type lạ bị reject.
- **S21.5 RuntimeCheckpoint contract** — As the runtime, một checkpoint nguy hiểm là `RuntimeCheckpoint{checkpoint_id, session_id, type, status∈waiting|approved|rejected|expired|auto_approved, risk_level, payload, resolved_at}` so that approval-flow có đối tượng rõ ràng, tách khỏi *state*-checkpoint của resume.
- **S21.6 Permission contract** — As the runtime, quyền của agent là `Permission{allowed_tools, can_write_artifacts, can_call_other_agents, can_execute_shell, can_modify_workflow, can_modify_permissions, effective_from}` so that quyền có cấu trúc và có thời điểm hiệu lực.
- **S21.7 Redaction engine** — As the runtime, mỗi event tách `payload` (nội bộ) khỏi `ui_payload` (đã redact theo key bí mật + visibility) so that secret không bao giờ rời ra UI/SSE.

## S-BACKEND — điều kiện-trước-UI (chuẩn hoá runtime/store)

- **S21.8 Control store (SQLite)** — As the runtime, control-store mở rộng `SqliteTaskLoopStore` thêm bảng `commands/checkpoints/permissions/audit` so that command/checkpoint/permission/audit query được, không cần Postgres.
- **S21.9 TaskLoopSnapshot projection** — As the UI, tôi đọc một `TaskLoopSnapshot` suy ra từ Blackboard+event (`orchestrator{last_decision,reason}`, `agents[]{status∈pending|waiting|running|done|failed}`, `pending_agent_calls[]`, `tool_calls[]`, `checkpoints[]`, `acceptance_status[]`) so that vẽ được graph/queue mà không tự giữ state thứ hai.
- **S21.10 Command queue + idempotency** — As the runtime, command vào hàng đợi với `idempotency_key` UNIQUE và vòng đời `received→accepted|rejected→applied` so that gửi trùng không áp dụng hai lần và mỗi bước phát event.
- **S21.11 Intervention points + pause/resume + approval-checkpoint** — As the runtime, `_drive` có các safe-point đặt tên (`before_round_start, after_agent_result, before_tool_call, before_acceptance_review, when_blocked`), cờ `pause_requested`, và `apply_pending_commands_at_checkpoint()` so that thay đổi chỉ áp tại điểm an toàn và hành động nguy hiểm dừng chờ duyệt — không kill agent giữa chừng.
- **S21.12 Human-editable permission (effective_from)** — As a human operator, tôi đổi quyền agent qua command; quyền ghi *append-only* và có hiệu lực **từ checkpoint kế**, không giữa turn so that "sửa quyền realtime" vẫn an toàn và truy vết được.
- **S21.13 pending_human_commands vào O** *(⊇ E17)* — As Agent O, `state_view` của tôi có `pending_human_commands[]` đã validate (không phải text thô); tôi ưu tiên xem xét, không áp nếu vi phạm policy, nếu áp thì tạo `AgentInvocation`, nếu không thì giải thích, và xuất `applied_human_commands[]` so that kéo-thả agent/chỉ thị người biến thành hành động có kiểm soát.
- **S21.14 Audit log có actor** — As an auditor, mọi command/permission-change/approval/tool-call ghi audit (actor, diff, thời điểm, link checkpoint, args đã redact) so that trả lời được "ai làm gì, khi nào, vì sao".

## S-TRANSPORT — kênh local (sau Port)

- **S21.15 Command endpoint + authz** — As the UI, tôi `POST /api/commands` kèm token hợp lệ; server validate schema → ghi `received` → publish → trả ACK kèm `command_id` so that kênh **mutate** không vô danh và lệnh sai bị từ chối ngay.
- **S21.16 SSE redacted + Last-Event-ID** — As the UI, SSE chỉ phát `ui_payload`/event `visibility∈{public,ui_safe}`; reconnect gửi `Last-Event-ID` để catch-up từ ring-buffer, hết thì fallback snapshot+JSONL so that không lộ secret và không mất/nhân đôi event khi rớt mạng.
- **S21.17 Snapshot API** — As the UI, `GET /api/snapshot` trả `TaskLoopSnapshot` (không chứa raw secret), 404 rõ ràng nếu session không tồn tại so that load nhanh không cần replay toàn bộ event.

## S-UI — Control Tower *(⊇ E18, E16)*

- **S21.18 Agent Graph** — As a human operator, tôi thấy O + các agent với status realtime; click agent mở inspector so that nắm được "ai đang chạy/chờ".
- **S21.19 Event Timeline** — As a developer, tôi xem event theo thời gian, lọc theo type/agent/tool/checkpoint, render virtualized so that debug được dòng sự kiện mà không lag.
- **S21.20 Agent Inspector** — As a human operator, tôi xem role, context_packet (đã redact), allowed tools, last output, permission snapshot so that hiểu một agent đang làm gì với quyền gì.
- **S21.21 Checkpoint/Approval modal** *(⊇ E16)* — As a human operator, khi có checkpoint `waiting` tôi thấy risk_level + tóm tắt + diff (nếu có) và Approve/Reject (kèm lý do) so that hành động nguy hiểm chỉ chạy khi tôi duyệt.
- **S21.22 Permission Editor** — As a human operator, tôi sửa quyền agent, thấy diff + đánh dấu escalation, submit `UpdateAgentPermission`; high-risk mở approval so that chỉnh quyền qua command (không mutate state trực tiếp).
- **S21.23 Replay view** — As an auditor, tôi replay session từ JSONL/SQLite (không gọi tool, không mutate, không gửi command mới) so that dựng lại lịch sử để điều tra.

## S-RELIABILITY — right-size

- **S21.24 Resume tại approval-checkpoint** — As the runtime, crash khi checkpoint `waiting` thì checkpoint vẫn `waiting` sau khi load lại; turn đã xong không chạy lại so that recovery an toàn.
- **S21.25 Reconnect** — As the UI, SSE reconnect có backoff, hiển thị `disconnected/reconnecting/connected`, sau reconnect load snapshot + catch-up so that không tạo reconnect storm và không mất event.
- **S21.26 Degrade khi sink lỗi** — As the runtime, nếu event-sink (JSONL) lỗi thì run không mất state (vẫn checkpoint SQLite) và báo degraded so that lỗi observability không làm sập workflow — đúng tinh thần `EventBus` nuốt lỗi observer hiện tại.

## S-EXPANDED — bổ sung từ PRD "Production Control Tower" (giữ Tier per [`02_FULL_FEATURE_MAP.md`](02_FULL_FEATURE_MAP.md))

### Instrumentation breadth (F2) + span (F1)
- **S21.27 Hook lifecycle events** — As a developer, runtime phát `hook.before_run/after_run/failed` (hook_name, hook_point, input/output summary đã redact, duration, modified?, blocked?) so that thấy hook nào sắp chạy và đã đổi/chặn gì; emit lỗi không làm mất audit.
- **S21.28 Skill resolution event** — As an operator, runtime phát `skill.resolved` (skill_id, version, reason, agent_id, allowed_tools summary) so that Inspector biết agent được nạp skill nào; skill thiếu ⇒ lỗi hiện rõ.
- **S21.29 Rule resolution event** — As an operator, runtime phát `rule.resolved` (rule_id, severity, scope, decision allow/deny/warn, reason) + phát hiện xung đột rule so that thấy ràng buộc trước khi agent chạy; rule deny chặn hành động.
- **S21.30 Raw↔validated output split** — As a developer, runtime phát `agent.output.raw` (lưu an toàn, UI thấy bản redact/summary) và `agent.output.validated` (status + field-path errors) so that phân biệt model nói gì vs đã hợp lệ chưa; output sai schema kích hoạt retry/blocked/human-review (qua json-gate E02 đã có).
- **S21.31 Span hierarchy** — As a developer, mỗi `agent.before_run` mở parent span; skill/rule/hook/tool tạo child span (`parent_span_id`) so that timeline render lồng nhau; thiếu parent span không làm vỡ delivery.

### Orchestration depth (F6) — mở rộng E10
- **S21.32 AgentInvocation + AgentBrief** — As Agent O, mỗi điều phối là `AgentInvocation{agent_id, purpose, context_packet, expected_output_schema, return_to, permissions_snapshot, round_no}` so that worker nhận brief riêng (mở rộng `AgentAssignment`/`ContextPacket` của E10, không thay thế); kernel chỉ chạy khi có invocation hợp lệ.
- **S21.33 AC evidence types + AC report** — As a product owner, mỗi AC `passed` phải có ≥1 evidence thuộc {artifact, tool_result, reviewer_report, diff, test_result} và session `finished` sinh artifact "AC report" so that "Finished" luôn có bằng chứng resolvable (siết thêm `judge_acceptance` S10.6 đã có).

### Artifact control (F12)
- **S21.34 Artifact write events + diff** — As an operator, runtime phát `artifact.before_write` (id/path/type + diff nếu sửa file cũ, đã redact) và `artifact.after_write` (version, checksum, agent/tool chịu trách nhiệm) so that thấy thay đổi file trước/sau; ghi nguy hiểm tạo checkpoint (nối B4).
- **S21.35 Artifact versioning + rollback** — As a developer, mỗi lần ghi tạo version mới, bản cũ vẫn truy cập được, có command `RollbackArtifact` (audited) so that khôi phục và truy vết được.
- **S21.36 Work-tree linkage** *(↗E13/E14)* — As an operator, session mang `task_id/subtask_id`, thay đổi `work_tree.yaml` phát artifact event, task status chỉ cập nhật khi AC passed so that điều hướng từ task-node sang session timeline; logic work-management thuộc E13/E14, E21 chỉ phát event + link.

### Security depth (F13)
- **S21.37 Role-based payload access** — As an admin, default stream là `ui_payload`; xem `payload` raw phải qua endpoint có quyền và bị log so that người thường không thấy raw, mọi truy cập raw đều audit (nối S21.7/S21.14).

### State machine + locking (F14)
- **S21.38 Session state machine tường minh** — As the runtime, tập trạng thái hợp lệ (`created/running/pause_requested/paused/blocked/failed/finished`, mở rộng `TaskLoopStatus`) với bảng transition hợp pháp so that transition phi pháp bị từ chối và mỗi transition phát `state.updated`.
- **S21.39 Session lock đơn-ghi** — As the runtime, một session chỉ có một writer tại một thời điểm (lock có lease + thu hồi stale) so that không có hai worker mutate cùng session; lock event quan sát được (right-size: trong v1 đơn tiến trình là in-process lock, contract sẵn cho phân tán sau).

### Reliability depth (F15)
- **S21.40 Backpressure + large payload** — As the runtime, hàng đợi event nội bộ có trần (critical không bao giờ drop, debug có thể sample), payload lớn lưu by-reference (`payload_ref`) so that tải cao không làm sập tiến trình và UI tải payload theo yêu cầu; số event bị drop được đo.

### Causal debugging (F16)
- **S21.41 Causal trace "vì sao X"** — As a developer, UI dựng được chuỗi nhân quả một hành động (command → quyết định O áp dụng → permission checks → `AgentInvocation` kết quả) so that trả lời "agent X được thêm vì sao, ai, round nào, quyền lúc đó".
- **S21.42 Trace tool bị từ chối** — As a developer, UI nối `tool.call_requested` → `permission.check_result` → permission profile áp dụng → rule từ chối so that debug được vì sao tool bị chặn.

### Production gates (F20) + Ops (F18 min)
- **S21.43 Feature DoD gate** — As a project owner, một feature chỉ merge khi: có event instrumentation, có permission check (nếu liên quan), có test, có metric, có failure-behavior, có UI-visibility (hoặc lý do không cần), có audit (nếu đổi state) so that mọi thứ vào nhánh đều production-grade (kế thừa DoD ở file 00 §6).
- **S21.44 Release checklist gate** — As a release owner, trước phát hành: migration store tested, schema thay đổi backward-compatible, có rollback plan, có dashboard/metrics, smoke offline xanh so that phát hành an toàn.
- **S21.45 Health + metrics tối thiểu** — As an operator, runtime/server có health endpoint + metrics local (event throughput, checkpoint wait time, permission denial rate, tool failure rate, SSE connection count) so that quan sát sức khoẻ; *Kafka/Redis lag, scale ngang, alert* là T2 (sau Port).

## S-INTERRUPT — ngắt & chen ngang (chi tiết [`03_INTERRUPT_AND_INJECT_MODEL.md`](03_INTERRUPT_AND_INJECT_MODEL.md))

- **S21.46 Ba chế độ chen ngang** — As an operator, khi tôi submit một injection lúc agent đang chạy, hệ chọn một trong **Wait** (mặc định: áp ở checkpoint kế), **Stop now** (dừng generation ngay rồi áp), hoặc **Ask** (popup hỏi) so that tôi kiểm soát được việc chen ngang mà không mặc định phá token đang sinh.
- **S21.47 Generation hủy được** *(= B10)* — As the runtime, một worker turn chạy ở đối tượng hủy được; `StopAgentTurn` luồng cancellation token tới tận `llm.chat` để dừng sớm so that nút Stop thật sự dừng sinh token, không phải giả vờ.
- **S21.48 Resume-from-checkpoint-with-injection** — As the runtime, sau Stop tôi **reload** state từ checkpoint cuối (không tái dùng in-memory đã mutate dở), áp command đang chờ, rồi re-run với cấu hình mới so that turn dở không để lại artifact nửa vời và hiệu ứng non-idempotent không bị chạy lại mù.
- **S21.49 Injection command types** — As an operator, tôi chen được hook mới (`InjectHook`), skill mới (`AddSkill`), system prompt mới (`SetSystemPrompt`/`EditAgentInstruction`), agent mới (`AddAgentToLoop`), quyền mới (`UpdateAgentPermission`) so that mọi loại thay đổi đều là command có validate, không phải sửa state trực tiếp; tất cả `apply_at=next_checkpoint` trừ `StopAgentTurn` (immediate).
- **S21.50 Agent node UI (Stop on hover, per-agent)** — As an operator, mỗi agent là node tròn, hover hiện control gồm **Stream** và **Stop**; bấm Stop gửi `StopAgentTurn(session_id, agent_id)` chỉ dừng **agent đó** (agent khác vẫn chạy), node chuyển `aborting→paused`, output dở hiển thị mờ + nhãn *aborted* so that tôi dừng/chen ngang ở mức từng agent; graph chỉ đổi qua event sau khi runtime áp dụng.
- **S21.51 Token streaming + cửa sổ xem** *(= B11)* — As an operator, mỗi agent có nút **Stream** opt-in; bấm mở cửa sổ/panel riêng xem token sinh **live** (delta `agent.token` đã redact, coalesce theo nhịp); đóng panel ⇒ ngừng nhận so that xem được quá trình sinh mà không làm ngập timeline.
- **S21.52 Stop giữ output dở để xem (mặc định vứt)** — As an operator, khi Stop, token dở **mặc định bị loại khỏi workflow** (không commit, không feed-forward) nhưng **được giữ lại để xem** trong cửa sổ stream với cờ `aborted` so that tôi xem lại được phần dở nhưng nó không bao giờ tự ảnh hưởng kết quả.
