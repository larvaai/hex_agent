# CATALOG — Event Storming trong hex_agent (vét cạn)

Bảng MỌI nơi pattern Event Storming (event/command/registry/emitter/projection/replay/redaction/log) xuất hiện trong codebase `hex_agent`. Mọi `path:line` đã được mở và xác nhận khớp tại thời điểm viết.

Root thật: `/Users/uspro/Desktop/namnson/hex_agent/`

| path:line | Vai trò trong pattern Event Storming | Mô tả | Độ rõ |
|-----------|--------------------------------------|-------|-------|
| `config/runtime_event_types.yaml:11-83` | **Bức tường sticky orange** (catalog event) | Catalog 57 domain event past-tense, nhóm theo bounded context ẩn: session / agent / hook-skill-rule / tool / permission-checkpoint / command / artifact / loop-delegation. Mỗi event khai báo `visibility` / `durable` / `redact_for_ui` / `checkpoint_candidate`. Đây là "discovery domain" đông cứng vào file. | cao |
| `config/runtime_command_types.yaml:9-36` | **Sticky blue** (catalog command) | Catalog 16 command imperative (`PauseWorkflow`, `ApproveCheckpoint`, `SubmitPrompt`...). Mỗi cái khai `apply_at` (next_checkpoint / immediate_if_waiting / immediate) + `requires_permission`. Command chưa khai báo bị reject ở gateway. | cao |
| `control/events.py:113-152` | **Envelope của domain event** (orange sticky) | `RuntimeEvent` frozen dataclass: event_type, session_id, actor, trace, redaction, seq, payload, ui_payload. `__post_init__` validate nên event sai không thể tồn tại. | cao |
| `control/events.py:32-51` | Actor của event | `Actor(type, id)` — ai/cái gì gây ra event (human/agent/tool/system/runtime). Tương ứng sticky yellow (actor). | cao |
| `control/events.py:85-110` | Phân loại "hot spot" theo visibility | `RedactionInfo(level, has_secret, redacted_fields)` — phân lớp ai được thấy event. Song song với sticky đỏ (hot spot / phân loại nhạy cảm) trong Event Storming. | trung bình |
| `control/events.py:193-212` | Đánh số sequence cho event stream | `SessionSeq` — bộ cấp số tăng đơn điệu per-session, thread-safe; emitter dùng để UI order/dedup. | trung bình |
| `control/commands.py:62-106` | **Envelope của command** (blue sticky) | `RuntimeCommand`: command_type, session_id, issued_by, idempotency_key, payload. UI không sửa state — nó submit command này. | cao |
| `control/commands.py:34-58` | Attribution của command | `IssuedBy(type, user_id, agent_id)` — ai phát command (audit/attribution, KHÔNG phải authz). Tương ứng sticky yellow actor phát lệnh. | cao |
| `control/commands.py:110-153` | Biên nhận đồng bộ cho command | `CommandAck` — receipt `received`/`rejected`; rejection bắt buộc kèm lý do. | trung bình |
| `control/commands.py:156-166` | Gate validate command | `parse_command` — thiếu `idempotency_key`/`issued_by` thì raise để gateway reject + emit `command.rejected`. | cao |
| `control/event_registry.py:40-61` | **Registry = bức tường** (gate event) | `EventTypeRegistry.assert_known` — event_type chưa khai báo trong YAML → `ControlContractError`. Emitter gọi trước khi publish. Cơ chế ép vocabulary domain. | cao |
| `control/event_registry.py:64-99` | Loader của tường event | `parse_event_registry` / `load_event_registry` — đọc YAML, ép event_type phải có dấu chấm (dotted), visibility hợp lệ. | cao |
| `control/command_registry.py:36-60` | **Registry = bức tường** (gate command) | `CommandTypeRegistry.assert_known` + `apply_at` + `requires_permission` — command lạ bị reject. | cao |
| `control/command_registry.py:63-95` | Loader của tường command | `parse_command_registry` / `load_command_registry` — validate `apply_at` thuộc tập hợp lệ. | cao |
| `control/emitter.py:53-61` | **Facilitator** (validate + seq + redact + fan-out) | `EventEmitter.emit_event` — đường publish DUY NHẤT đã validate: lấy spec từ registry (reject nếu lạ), stamp `seq`, redact `ui_payload`, gửi tới các sink. | cao |
| `control/emitter.py:28-37` | Sink adapter | `BusEventSink.emit` — đẩy envelope dict lên `EventBus` cũ để subscriber (EventLogger) persist không đổi. Swap Kafka = thêm sink, không đổi caller. | cao |
| `control/redaction.py:65-73` | Biên an toàn secret (hot spot) | `Redactor.apply` — tách `payload` thô thành `ui_payload` đã che secret + `RedactionInfo`. UI chỉ thấy `ui_payload`. | trung bình |
| `control/redaction.py:44-63` | Che secret đệ quy | `Redactor.redact` / `_walk` — mask key nhạy cảm trong dict/list lồng nhau, ghi lại path bị che; không mutate payload gốc. | trung bình |
| `control/replay.py:23-81` | Event store cho replay/resync | `EventReplayBuffer` — ring buffer 2048 event/session, dedup theo `event_id`, `events_after(seq)` catch-up, `needs_resync` báo client rớt ring. Cho phép UI reconnect. | trung bình |
| `core/events.py:11-32` | Bus pub/sub nền | `EventBus` — pub/sub thread-safe; observability subscribe ở đây. Legacy kernel event chảy qua đây trước khi migrate sang envelope. | trung bình |
| `observability/event_log.py:41-99` | "Chụp ảnh + transcribe" (output workshop) | `EventLogger` — subscribe EventBus, ghi event vào `events.jsonl` + `summary.json` + metrics. Tương ứng bước photo + glossary export của Event Storming. | trung bình |
| `observability/event_log.py:102-134` | Nối logger vào bus | `attach_to_bus` — mirror mọi kernel event vào event log, đếm metrics theo topic. | trung bình |
| `core/kernel.py:106-150` | Event bracket quanh tool call | `execute_tool` publish `tool.requested` (trước), `tool.failed` (khi out-of-scope) — mọi capability invocation được kẹp bởi event. | trung bình |
| `core/kernel.py:216` | Event kết thúc tool | publish `tool.completed`/`tool.failed` sau khi tool chạy — fact past-tense ghi kết quả. | trung bình |
| `core/session.py:87-98` | Event vòng đời task | `complete_task` publish `task.completed` hoặc `task.failed` — mỗi chuyển trạng thái task được ghi nhận. | cao |
| `supervisor/graph.py:56-75` | Cầu nối business logic → envelope | `SupervisorContext.emit` — khi có emitter, mọi event supervisor chảy qua envelope chuẩn (registry-validated, seq-stamped, redacted); không thì publish raw legacy. | cao |
| `supervisor/graph.py:103` | Emit `loop.team_composed` | `compose_team` emit fact "đã chọn team" sau khi mutate state. | cao |
| `supervisor/graph.py:122` | Emit `loop.decision` | `o_decide` emit fact "orchestrator đã quyết định". | cao |
| `supervisor/graph.py:209` | Emit `loop.turn` | `run_round` emit fact "agent đã chạy xong 1 lượt". | cao |
| `supervisor/graph.py:226` | Emit `loop.tool` | `run_tool` emit fact "đã gọi tool, ok?". | cao |
| `control/snapshot.py:88-134` | **Read model** (green sticky / projection) | `TaskLoopSnapshot` — view UI render cho 1 session; KHÔNG phải state, là projection fold từ event. | cao |
| `control/snapshot.py:36-85` | Node của read model | `AgentView` — 1 node trong Agent Graph; trường tự do (permission/allowed_tools) chỉ điền khi event mang theo. | cao |
| `control/snapshot.py:140-148` | Policy fold event → status | `_STATUS_BY_EVENT` — map loop event sang session status; terminal status thắng. | cao |
| `control/snapshot.py:189-365` | **Fold** (event sourcing thuần) | `build_snapshot` — fold tuyến tính, order-sensitive: derive agent status (pending→running→done→waiting), orchestrator decision, tool call, checkpoint. Replay cùng event ⇒ cùng snapshot. | cao |
| `tests_audit/test_contract_roundtrips.py:180-199` | Bất biến immutable/serializable | `test_task_loop_snapshot_roundtrip_preserves_agents_and_nested_type` — property test: `TaskLoopSnapshot.from_dict(snap.as_dict()) == snap`, container detached. Bảo chứng tính bất biến + serializable của artifact. | trung bình |
| `tests_audit/test_contract_roundtrips.py:172-178` | Roundtrip command receipt | `test_command_ack_roundtrip_lossless` — `CommandAck` roundtrip không mất dữ liệu. | trung bình |
| `tests_audit/test_contract_roundtrips.py:46-121` | Roundtrip các contract khác | Property test cho `TaskEnvelope`, `CapabilityResult`, `DelegationSpec`, `SessionIdentity` — đảm bảo immutability + serializability của artifact Event Storming. | trung bình |
