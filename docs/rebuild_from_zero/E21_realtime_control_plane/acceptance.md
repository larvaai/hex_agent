# E21 — Acceptance Criteria

> Given/When/Then, map 1–1 với [`stories.md`](stories.md). Mỗi AC → ≥1 test trong harness E19 (`tests/` + `tests_audit/`).

## S-CONTRACT

### S21.1 RuntimeEvent envelope
- Given một event hợp lệ, When encode→decode round-trip, Then mọi field giữ nguyên; And event thiếu field bắt buộc (`event_id/event_type/session_id/actor/redaction/created_at`) ⇒ raise (không publish).
- Given hai event cùng `session_id`, When phát lần lượt, Then `seq` tăng đơn điệu trong phạm vi session.

### S21.2 Event-type registry
- Given registry YAML đã load, When emit một `event_type` **không** có trong registry, Then bị từ chối; And mỗi type trả về `visibility/durable/redact_for_ui/checkpoint_candidate`.

### S21.3 RuntimeCommand contract
- Given một command thiếu `idempotency_key` hoặc `issued_by`, When validate, Then reject + phát `command.rejected` kèm lý do.
- Given command đúng shape, When parse, Then ra đối tượng `RuntimeCommand` đầy đủ.

### S21.4 Command-type registry
- Given `command_type` lạ, When submit, Then reject; And mỗi type hợp lệ trả `apply_at` + `requires_permission`.

### S21.5 RuntimeCheckpoint contract
- Given một checkpoint nguy hiểm tạo ra, When khởi tạo, Then `status="waiting"` và mang `risk_level` + `payload` đã redact; And `status` chỉ chuyển sang `approved/rejected/expired/auto_approved`.

### S21.6 Permission contract
- Given một `Permission` với `effective_from="next_checkpoint"`, When serialize, Then đủ field boolean (`can_write_artifacts/can_execute_shell/can_modify_workflow/can_modify_permissions`) + `allowed_tools` + `effective_from`.

### S21.7 Redaction engine
- Given payload chứa `api_key` (kể cả lồng trong dict con), When redact, Then `ui_payload[...]="[REDACTED]"`, `redaction.has_secret=true`, `redacted_fields` liệt kê đúng key; And `payload` gốc không đổi.

## S-BACKEND

### S21.8 Control store (SQLite)
- Given control-store khởi tạo, When mở, Then tồn tại bảng `commands/checkpoints/permissions/audit`; And `commands.idempotency_key` có ràng buộc UNIQUE; And `run_id` path-like bị từ chối (giống guard hiện có ở `SqliteTaskLoopStore`).

### S21.9 TaskLoopSnapshot projection
- Given một chuỗi event của 1 run (O chọn A,B; A done; B running; C pending), When `build_snapshot`, Then snapshot cho `agents` đúng status từng agent + `orchestrator.last_decision` + `pending_agent_calls`; And snapshot **không** chứa raw secret.

### S21.10 Command queue + idempotency
- Given cùng một `idempotency_key` gửi 2 lần, When xử lý, Then chỉ áp dụng 1 lần và lần 2 trả kết quả deterministic của lần đầu.
- Given một command, When đi qua vòng đời, Then phát `command.received/accepted|rejected/applied` đúng thứ tự.

### S21.11 Intervention points + pause/resume + approval-checkpoint
- Given `PauseWorkflow` gửi khi một agent đang chạy, When tới safe-point kế, Then run chuyển `paused` **sau khi** turn hiện tại xong (không kill giữa chừng).
- Given một tool `risk_level=high`, When `_drive` tới `before_tool_call`, Then tạo checkpoint `waiting` và tool **không** chạy cho tới khi `approved`; And `RejectCheckpoint` ⇒ tool không chạy, run về `blocked/paused` theo policy.
- Given `pending_human_commands` đang chờ, When tới `apply_pending_commands_at_checkpoint()`, Then chỉ command `apply_at=next_checkpoint` mới được áp tại đây.

### S21.12 Human-editable permission (effective_from)
- Given `UpdateAgentPermission` accepted khi agent đang chạy turn, When turn đó tiếp tục, Then **vẫn** dùng quyền cũ; And từ checkpoint kế, `PolicyGate`/`DelegationPolicy` dùng quyền mới.
- Given nhiều lần đổi quyền, When đọc lịch sử, Then các bản ghi cũ không bị ghi đè (append-only).

### S21.13 pending_human_commands vào O
- Given `AddAgentToLoop` accepted (agent_x, role security_reviewer, scope chỉ `read_file/search_code`), When O quyết định ở round kế, Then O tạo `AgentInvocation` cho agent_x đúng scope đó và liệt kê trong `applied_human_commands`; And `run_round` chặn nếu assignment trỏ agent không được composition chọn (authority check sẵn có).
- Given một command vi phạm policy, When O xử lý, Then O **không** áp và nêu lý do (test offline với `ScriptedOrchestrator`).

### S21.14 Audit log có actor
- Given một command đổi quyền được áp, When đọc audit, Then có bản ghi `{actor, old, new, ts, checkpoint_id}`; And mọi command/approval/tool-call (args redacted) đều có audit — không cái nào thiếu actor.

## S-TRANSPORT

### S21.15 Command endpoint + authz
- Given `POST /api/commands` **không** token hợp lệ, When nhận, Then 401/403 + audit; And body sai schema ⇒ 400 + `command.rejected`.
- Given command hợp lệ, When nhận, Then ghi `received`, trả ACK kèm `command_id` (< ~300ms local).

### S21.16 SSE redacted + Last-Event-ID
- Given một event `visibility=secret`, When stream qua SSE, Then **không** gửi; And event `ui_safe` chỉ gửi `ui_payload`.
- Given client reconnect với `Last-Event-ID`, When còn trong ring-buffer, Then catch-up từ đó; And nếu đã rớt khỏi buffer, fallback snapshot + JSONL; And client không nhận trùng event đã có.

### S21.17 Snapshot API
- Given session tồn tại, When `GET /api/snapshot`, Then trả `TaskLoopSnapshot` không chứa raw secret; And session không tồn tại ⇒ 404 rõ ràng.

## S-UI

### S21.18 Agent Graph
- Given snapshot có A done/B running/C pending, When render, Then graph hiển thị đúng status mỗi node; And event duplicate đến không làm graph vỡ (idempotent theo `event_id`).

### S21.19 Event Timeline
- Given hàng nghìn event, When render timeline, Then dùng virtualized rendering (không dựng toàn bộ DOM); And lọc theo type/agent/tool/checkpoint hoạt động; And payload bí mật hiển thị `[REDACTED]`.

### S21.20 Agent Inspector
- Given click một agent, When mở inspector, Then thấy role/context_packet (redacted)/allowed_tools/last_output/permission_snapshot; And không hiển thị secret.

### S21.21 Checkpoint/Approval modal
- Given checkpoint `waiting`, When UI nhận qua SSE, Then hiện modal với `risk_level` + tóm tắt (+ diff nếu có); And Approve ⇒ gửi `ApproveCheckpoint`, runtime resume; And Reject ⇒ gửi `RejectCheckpoint`, hành động không chạy; And modal cập nhật trạng thái sau quyết định.

### S21.22 Permission Editor
- Given mở editor cho 1 agent, When sửa quyền, Then hiện diff + đánh dấu escalation; And submit ⇒ phát `UpdateAgentPermission` (UI **không** sửa state trực tiếp); And command hiển thị `received/accepted/rejected/applied`; And thay đổi high-risk mở approval-flow.

### S21.23 Replay view
- Given một session đã chạy, When replay, Then hiển thị lại timeline từ JSONL/SQLite; And replay **không** gọi tool, **không** mutate state, **không** gửi command mới; And đánh dấu rõ chế độ replay.

## S-RELIABILITY

### S21.24 Resume tại approval-checkpoint
- Given runtime bị kill khi một checkpoint `waiting`, When load lại từ control-store, Then checkpoint vẫn `waiting`; And turn đã hoàn tất không bị chạy lại; And resume tiếp tục đúng từ điểm chờ.

### S21.25 Reconnect
- Given SSE rớt, When client reconnect, Then có backoff (không reconnect storm), hiển thị trạng thái kết nối, và sau reconnect load snapshot + catch-up không trùng event.

### S21.26 Degrade khi sink lỗi
- Given event-sink (JSONL) ném lỗi khi ghi, When runtime emit event, Then workflow không sập (state vẫn checkpoint SQLite) và báo trạng thái degraded; And không mất event "durable" sau khi sink phục hồi (replay từ checkpoint/Blackboard).

## S-EXPANDED

### S21.27 Hook lifecycle events
- Given một hook chạy ở một hook_point, When runtime chạy hook, Then phát `hook.before_run` (trước) và `hook.after_run` (sau, có `duration`, `modified?`, `blocked?`); And hook ném lỗi ⇒ `hook.failed` (error_type/message) và **không** bị bỏ qua audit; And input nhạy cảm đã redact.

### S21.28 Skill resolution event
- Given runtime resolve skill cho một agent, When resolve xong, Then phát `skill.resolved` (skill_id, version, reason, agent_id); And skill thiếu ⇒ event lỗi hiện rõ; And Inspector hiển thị skill đã nạp.

### S21.29 Rule resolution event
- Given một rule được áp, When resolve, Then phát `rule.resolved` (rule_id, severity, scope, decision∈allow/deny/warn, reason); And `deny` chặn hành động; And hai rule xung đột ⇒ phát hiện và báo.

### S21.30 Raw↔validated output split
- Given agent sinh output, When runtime xử lý, Then phát `agent.output.raw` (lưu an toàn, UI nhận bản redact/summary) **và** `agent.output.validated` (status + field-path lỗi nếu sai schema); And output sai schema ⇒ retry/blocked/human-review (json-gate E02); And UI phân biệt rõ raw vs validated.

### S21.31 Span hierarchy
- Given một `agent.before_run`, When các thao tác con (skill/rule/hook/tool) phát event, Then chúng mang `parent_span_id` trỏ về span của agent-run; And `span_id` là duy nhất; And thiếu parent span không làm vỡ delivery; And UI render được timeline lồng.

### S21.32 AgentInvocation + AgentBrief
- Given Agent O điều phối agent X, When tạo invocation, Then có đủ `agent_id/purpose/context_packet/expected_output_schema/return_to/permissions_snapshot/round_no`; And kernel **không** chạy agent nếu invocation thiếu field; And context_packet là riêng cho X (không chứa transcript toàn cục) — nhất quán với S10.3.

### S21.33 AC evidence types + AC report
- Given một AC `passed`, When validate, Then phải có ≥1 evidence thuộc {artifact, tool_result, reviewer_report, diff, test_result} **và** evidence resolve được trên Blackboard; And session `finished` ⇒ sinh artifact "AC report" (AC status + evidence + session_id); And thiếu evidence ⇒ không `finished` (siết S10.6).

### S21.34 Artifact write events + diff
- Given agent/tool sắp ghi artifact, When trước khi ghi, Then phát `artifact.before_write` (id/path/type + diff nếu sửa bản cũ, đã redact); And sau khi ghi phát `artifact.after_write` (version + checksum + agent/tool); And ghi nguy hiểm (overwrite/protected) ⇒ tạo checkpoint `waiting` trước (B4).

### S21.35 Artifact versioning + rollback
- Given một artifact bị ghi nhiều lần, When đọc lịch sử, Then mỗi lần ghi là một version mới, bản cũ vẫn truy cập được, mỗi version link `event_id`; And `RollbackArtifact` khôi phục bản trước và được audit.

### S21.36 Work-tree linkage
- Given một session gắn `task_id/subtask_id`, When thay đổi `work_tree.yaml`, Then phát artifact event + diff trước khi ghi; And task status chỉ chuyển `done` khi AC passed; And UI điều hướng được từ task-node sang session timeline. (Logic work-management thuộc E13/E14.)

### S21.37 Role-based payload access
- Given một user thường, When stream/đọc event, Then chỉ nhận `ui_payload`; And xem `payload` raw phải qua endpoint có quyền; And truy cập raw trái phép ⇒ từ chối + audit; And mọi truy cập raw hợp lệ đều được log.

### S21.38 Session state machine tường minh
- Given trạng thái hiện tại của session, When yêu cầu một transition, Then chỉ transition trong bảng hợp pháp được chấp nhận (vd `paused→resuming→running`); And transition phi pháp bị từ chối; And mỗi transition hợp lệ phát `state.updated` và được persist.

### S21.39 Session lock đơn-ghi
- Given một session đang được một writer mutate, When một writer khác cố mutate, Then bị từ chối/є retry; And lock có lease/timeout; And lock stale có thể thu hồi; And sự kiện lock quan sát được. (v1: in-process lock; contract sẵn cho phân tán T2.)

### S21.40 Backpressure + large payload
- Given tải event cao vượt trần hàng đợi, When emit, Then event `critical` **không bao giờ** bị drop, event debug có thể bị sample/drop theo policy, và số bị drop được đo; And payload vượt ngưỡng ⇒ lưu by-reference (`payload_ref`), UI tải theo yêu cầu, payload quá khổ bị từ chối hiện rõ.

### S21.41 Causal trace "vì sao X"
- Given agent X đã được thêm vào loop, When mở causal view, Then UI hiện chuỗi: command (ai/khi nào) → quyết định O áp dụng → permission checks → `AgentInvocation` sinh ra; And mỗi mắt xích click mở được event gốc.

### S21.42 Trace tool bị từ chối
- Given một tool call bị từ chối, When mở debug, Then UI nối `tool.call_requested` → `permission.check_result` → permission profile áp dụng → rule từ chối (+ summary request đã redact).

### S21.43 Feature DoD gate
- Given một feature chuẩn bị merge, When chạy DoD check, Then xác nhận đủ: event instrumentation, permission check (nếu liên quan), test, metric, failure-behavior, UI-visibility (hoặc lý do), audit (nếu đổi state); And thiếu bất kỳ mục bắt buộc ⇒ chặn merge.

### S21.44 Release checklist gate
- Given một bản chuẩn bị phát hành, When chạy checklist, Then xác nhận: migration store tested, schema backward-compatible, có rollback plan, có dashboard/metrics, smoke offline xanh; And thiếu mục ⇒ chặn release.

### S21.45 Health + metrics tối thiểu
- Given runtime/server đang chạy, When gọi health/metrics, Then trả health + các metric local (event throughput, checkpoint wait time, permission denial rate, tool failure rate, SSE connection count); And các metric đặc thù cluster (Kafka/Redis lag, scale, alert) **không** bắt buộc ở v1 (T2 sau Port).

## S-INTERRUPT

### S21.46 Ba chế độ chen ngang
- Given agent đang chạy và user submit injection ở chế độ **Wait**, When tới safe-point kế, Then turn hiện tại đã commit và injection mới được áp (không phá token đang sinh).
- Given chế độ **Stop now**, When user submit, Then generation bị hủy ngay và injection áp tại checkpoint cuối.
- Given chế độ **Ask**, When user submit lúc agent đang `running`, Then hiện popup chọn Stop-now/Wait; And popup **timeout 5s** không trả lời ⇒ rơi về **Wait** (mặc định).

### S21.47 Generation hủy được
- Given một worker turn đang sinh token, When `StopAgentTurn` tới, Then generation dừng < ~1s và turn thoát trạng thái `aborted` + phát `agent.aborted`; And `_drive` không bị chặn vĩnh viễn bởi turn đó.

### S21.48 Resume-from-checkpoint-with-injection
- Given một turn bị Stop giữa chừng (đã add `context_packet` artifact in-memory nhưng **chưa** `ctx.save`), When resume, Then state được **reload từ checkpoint cuối** (artifact nửa vời không tồn tại), injection đang chờ được áp, và turn re-run với cấu hình mới.
- Given turn dở **đã** chạy một tool `kind=effect, idempotent=False` trước khi Stop, When re-run, Then tool đó **không** bị chạy lại mù (dedup theo `idempotency_key` hoặc reconcile — S10.13/S21.24).

### S21.49 Injection command types
- Given mỗi loại injection (`InjectHook`/`AddSkill`/`SetSystemPrompt`/`EditAgentInstruction`/`AddAgentToLoop`/`UpdateAgentPermission`), When submit, Then là `RuntimeCommand` hợp lệ qua gate (không sửa state trực tiếp) và `apply_at=next_checkpoint`; And `StopAgentTurn` là command **immediate** (cancel), không đợi checkpoint.
- Given một injection command sai schema / vi phạm policy, When validate, Then reject + `command.rejected` kèm lý do.

### S21.50 Agent node UI (Stop on hover, per-agent)
- Given một node agent đang `running`, When hover, Then hiện control gồm **Stream** + **Stop**; And bấm Stop ⇒ gửi `StopAgentTurn(session_id, agent_id)` chỉ dừng agent đó (**agent khác cùng round vẫn chạy**), node chuyển `aborting→paused`, output dở hiển thị mờ + nhãn *aborted*; And graph chỉ cập nhật trạng thái mới **sau** khi runtime phát event (không optimistic mutate).

### S21.51 Token streaming + cửa sổ xem
- Given một agent đang sinh token, When user bấm **Stream**, Then mở panel theo `agent_id` nhận `agent.token` (delta) **live, đã redact, coalesce theo nhịp**; And đóng panel ⇒ server ngừng đẩy delta cho client đó; And tải token cao **không** làm drop event critical (S21.40).
- Given stream là **live-only**, When session kết thúc/replay, Then `agent.token` **không** có để replay (chỉ `agent.output.raw` cuối được lưu); And mở panel stream cho agent khác ⇒ panel đang mở bị đóng (**mặc định 1 panel**, không đồng thời).

### S21.52 Stop giữ output dở để xem (mặc định vứt)
- Given một turn bị Stop giữa chừng, When xem lại, Then token dở **vẫn xem được** trong cửa sổ stream với cờ `aborted`; And nó **không** được commit, **không** làm input cho turn re-run, **không** sinh `agent.output.validated`; And mặc định hệ thống loại nó khỏi workflow (chỉ giữ để người xem).
