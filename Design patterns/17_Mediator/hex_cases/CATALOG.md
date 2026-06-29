# CATALOG — Mọi occurrence của Mediator (và họ hàng) trong hex_agent

Bảng vét cạn các nơi pattern Mediator (hoặc biến thể gần: Command-Bus, Blackboard,
Event-Bus routing) xuất hiện. Hai dòng `★` là flagship, đã distill thành case con.
Mọi `path:line` đã mở file thật để kiểm chứng.

| path:line | Mô tả vai trò Mediator | Độ rõ |
|---|---|---|
| ★ `core/kernel.py:106-225` | `AgentKernel.execute_tool` — chokepoint DUY NHẤT cho mọi request gọi tool. Middleware (gate, billing, retry, logging) bọc thành chuỗi quanh resolver `core`. Không có đường tắt caller→executor; mọi thứ chảy qua pipeline composition. Xem **case 01**. | cao |
| ★ `core/kernel.py:24-73` | `_wrap` + `_LatchedNext` — bind 1 middleware (colleague) quanh handler kế; phân biệt fail-open (advisory, skip khi raise) vs fail-closed. (`_LatchedNext` ở `:24-46`, `_wrap` ở `:49-73`.) | cao |
| ★ `core/kernel.py:100-104` | `AgentKernel.use` — đăng ký middleware; thứ tự = outer → inner. | cao |
| ★ `core/registry.py:103-112` | `CapabilityRegistry.resolve_tool` — map `tool_name` → executor (exact thắng; thiếu → `NullToolPort`). Registry mà caller không bao giờ bypass. | trung bình |
| ★ `core/registry.py:29-40` | `NullToolPort` — giữ mediator sống khi tool thiếu (graceful fallback). | trung bình |
| ★ `supervisor/graph.py:39-80` | `SupervisorContext` — ConcreteMediator giữ orchestrator/broker/delegation_service/checkpoint. Các node thao tác trên Blackboard qua ctx, không trực tiếp. Xem **case 02**. | cao |
| ★ `supervisor/loop.py:71-201` | `run_task_loop` + `_drive` — vòng compose_team → o_decide → run_round → judge. Mỗi quyết định của O route việc qua `ctx.delegation_service`; agent không giao tiếp trực tiếp. | cao |
| ★ `supervisor/state.py:80-111` | `TaskLoopState` — Blackboard chia sẻ: selected_agents, turns, artifacts, acceptance_checks. Agent ghi artifact; mediator đọc và route bước kế. | cao |
| ★ `supervisor/graph.py:137-211` | `run_round` — phân việc cho từng agent qua Broker + DelegationService; authority check chặn agent ngoài team. | cao |
| ★ `supervisor/orchestrator.py:21-39` | `ScriptedOrchestrator` (+ `OrchestratorPort:15-18`) — routing decisions (compose_team, decide). Là colleague trong mediator supervisor, đồng thời là sub-mediator cho state machine của chính nó. | trung bình |
| ★ `supervisor/broker.py:24-55` | `DeterministicBroker` (+ `BrokerPort:17-21`) — shape context: nhận AgentAssignment + store_slice → ContextPacket. Agent không tự lấy context cho nhau; Broker điều phối. | cao |
| `control/emitter.py:39-91` | `EventEmitter` (+ `BusEventSink:28-37`) — route `RuntimeEvent` qua pipeline validate → seq-stamp → redact → fan-out tới sinks. Event không tới sink trực tiếp; Emitter là điều phối viên duy nhất. | cao |
| `supervisor/llm.py:57-110` | `KernelChatLLM` + `LLMOrchestrator` + `LLMBroker` — sub-mediator: mọi lời gọi LLM route qua một interface `ChatLLM` (`supervisor/llm.py:53`), wrap `session.execute_tool('llm.chat')` (`:65`). Chống LLM client sprawl. | trung bình |
| `drag_from_zero/dragzero/orchestrator.py:63-307` | `Orchestrator` — pausable work-queue: quản `_task_seq`/`_ready`/`_waiting`/`_recs` (`:91-95`), route task qua `_route` (`:122`), chạy `run_until_idle` (`:145`). Agent (colleague) không biết nhau; mọi điều phối qua Orchestrator. | cao |
| `middleware/retry.py:23-33` | `Retry` — colleague trong pipeline mediator của kernel; gọi `nxt` lặp khi `!ok`, không biết logging/timing tồn tại. | trung bình |
| `middleware/timing.py:10-26` | `TimingLog` — colleague advisory (`fail_open = True`); đo wall-time, không bao giờ biến tool ok thành fail. | trung bình |
| `control/ports.py:14-22` | `EventSinkPort` — Protocol biên cho phép thay sink (Kafka/Redis) mà không đụng emitter/supervisor/kernel; là seam cho Mediator. | trung bình |
| `observability/event_log.py:102-134` | `attach_to_bus` — `EventLogger` subscribe `EventBus`. Thiên về Observer/Pub-Sub hơn Mediator thuần, nhưng EventBus đóng vai điều phối routing event → sink. | thấp |
| `core/session.py:75-85` | `KernelSession.execute_tool` — wrap `kernel.execute_tool` thêm session context. Đóng vai Facade/Adapter trước mediator kernel. | thấp |

## Ghi chú phân loại

- **Mediator "thuần" (chokepoint/centralized routing)**: `core/kernel.py`,
  `supervisor/graph.py` + `loop.py`, `drag_from_zero/.../orchestrator.py`.
- **Biến thể Command-Bus + middleware**: kernel `execute_tool` (case 01).
- **Biến thể Blackboard + state machine**: TaskLoop (case 02).
- **Biên Event-Bus (gần Observer)**: `control/emitter.py`, `observability/event_log.py`
  — đưa vào vì chúng làm rõ ranh giới Mediator ↔ Observer mà bài gốc nhấn mạnh
  (mục 2.5): emitter có routing/redact (nghiêng Mediator); event_log chỉ subscribe
  (nghiêng Observer).
