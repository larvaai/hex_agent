# E21 — Bản đồ phủ 20 Feature của "Production Observable Control Tower"

> Bạn gửi một PRD đầy đủ 20 Feature (superset của bản đầu). File này **đối chiếu từng feature** với E21, để chứng minh đã hấp thụ trọn vẹn và slot đúng chỗ — đồng thời tôn trọng quyết định đã chốt: **right-size hạ tầng (SQLite/JSONL/EventBus sau Port)**.
>
> Mỗi feature gắn **Tier**:
> - **T1** = làm ở v1, hạ tầng local (SQLite/JSONL/EventBus + `POST /api/commands` + SSE).
> - **T2** = giữ nguyên *contract*, nhưng *transport/storage* để **sau Port** (gắn Kafka/Redis/Postgres/WebSocket khi lên multi-node). Không làm ở v1.
> - **X** = phần lớn không áp dụng cho harness local (deploy/scale ngang); chỉ giữ phần tối thiểu (health/metrics).
> - **↗E##** = thuộc epic khác, E21 chỉ tích hợp.

| # | Feature (PRD Control Tower) | Tier | Phủ bởi | Ghi chú |
|---|---|---|---|---|
| F1 | Runtime Event Contract (envelope, registry, trace/span, ui-safe) | T1 | S21.1, S21.2, S21.7, **S21.31** | envelope/registry/redaction đã có; **thêm span hierarchy** |
| F2 | Runtime Instrumentation (agent/hook/skill/rule events) | T1 | **S21.27–S21.30** | **mới**: hook before/after/failed, skill/rule resolved, raw↔validated output |
| F3 | Command & Control (HumanCommand, lifecycle, pause/add-agent) | T1 | S21.3, S21.4, S21.10, S21.11, S21.13 | qua `POST /api/commands` |
| F4 | Checkpoint & Approval System | T1 | S21.5, S21.11, S21.21 | approval-gate + timeout policy |
| F5 | Permission & Policy Engine | T1 | S21.6, S21.12, S21.22, **S21.37** | **thêm** role-based payload access |
| F6 | Agent Orchestration Loop (O decision, AgentInvocation, AC+evidence, loop guard) | T1 | E10 (S10.1/6/7/8) + S21.13, **S21.32, S21.33** | **phần lớn đã có ở E10**; thêm AgentInvocation/Brief + evidence-types + AC report |
| F7 | Realtime Gateway (SSE + WebSocket) | T1 (SSE) / T2 (WS) | S21.15, S21.16, S21.17 | v1 dùng SSE + `POST /api/commands`; WebSocket sau Port |
| F8 | Redis Streams Live Layer | **T2** | `LiveBusPort` | v1 = `EventBus` in-process + ring-buffer/session; Redis adapter sau |
| F9 | Kafka Durable Backbone | **T2** | `EventSinkPort` | v1 = `EventLogger` JSONL + replay; Kafka adapter sau |
| F10 | Postgres Source of Truth (sessions/snapshot/outbox/NOTIFY) | **T2** | `ControlStorePort` | v1 = SQLite (S21.8); **outbox/NOTIFY N/A** đơn tiến trình |
| F11 | UI Control Tower (timeline/graph/inspector/checkpoint) | T1 | S21.18–S21.23 | + span nesting S21.31 |
| F12 | Artifact & Diff Control (before/after write, versioning, rollback) | T1 | **S21.34, S21.35** | **mới** |
| F13 | Security & Redaction (redact + role-based access + audit) | T1 | S21.7, S21.14, **S21.37** | |
| F14 | State Machine & Workflow Safety (legal states, safe points, locking) | T1 | S21.11, **S21.38, S21.39** | **thêm** state machine tường minh + session lock (đơn-ghi) |
| F15 | Reliability & Backpressure | T1 (subset) | S21.24, S21.25, S21.26, **S21.40** | **thêm** bounded queue + large-payload-by-ref |
| F16 | Replay & Debugging (replay + causal debug) | T1 | S21.23, **S21.41, S21.42** | **thêm** causal "vì sao X" + "vì sao tool bị từ chối" |
| F17 | Testing & Quality Gates (schema/integration/chaos) | T1 | [`acceptance.md`](acceptance.md) toàn bộ + S21.24 | chaos right-size: kill-process + drop-SSE |
| F18 | Deployment & Operations (scale, monitor, alert) | **X** + T1(min) | **S21.45** | local: chỉ health + metrics tối thiểu; scale/alert là T2 |
| F19 | Work Management Integration (work_tree, task↔session) | **↗E13/E14** | **S21.36** | E21 chỉ phát artifact/state event + link task_id |
| F20 | Production Readiness Gates (DoD, release checklist) | T1 (process) | **S21.43, S21.44** | gate quy trình, không phải code runtime |

## Điều gì **mới** so với E21 ban đầu (S21.1–S21.26)

Các story bổ sung **S21.27–S21.45** (chi tiết ở [`stories.md`](stories.md) mục *S-EXPANDED*, AC ở [`acceptance.md`](acceptance.md)):

- **Instrumentation breadth** (F2): `hook.before_run/after_run/failed`, `skill.resolved`, `rule.resolved` (+conflict), tách `agent.output.raw` ↔ `agent.output.validated` với field-path errors.
- **Span hierarchy** (F1/F11): agent-run là parent span; skill/rule/hook/tool là child → timeline lồng nhau.
- **Orchestration depth** (F6): `AgentInvocation`+`AgentBrief` (mở rộng `AgentAssignment`/`ContextPacket` của E10); evidence-types cho AC (artifact/tool-result/reviewer/diff/test) + artifact "AC report".
- **Artifact control** (F12): before/after-write event + diff; versioning + rollback có audit.
- **Role-based payload access** (F13): default `ui_payload`; xem raw cần endpoint có quyền + bị log.
- **State machine + locking** (F14): tập trạng thái hợp lệ tường minh (mở rộng `TaskLoopStatus`), chặn transition phi pháp; session lock đơn-ghi + lease + thu hồi stale.
- **Backpressure** (F15): hàng đợi event có trần, critical-không-bao-giờ-drop, payload lớn lưu by-reference.
- **Causal debugging** (F16): truy "vì sao agent X được thêm" (command→O decision→permission→invocation) và "vì sao tool bị từ chối" (request→permission result→rule).
- **Work-tree integration** (F19, cross-epic): link `task_id`/`subtask_id`; cập nhật task status chỉ khi AC passed.
- **Production gates** (F20): feature-DoD + release-checklist.

## Vì sao KHÔNG kéo Kafka/Redis/Postgres vào v1 (nhắc lại, đã chốt)

PRD Control Tower viết cho **multi-node, multi-user, production cluster**. Harness này chạy **một tiến trình, local, một người dùng**. Ở quy mô đó:
- **Outbox + NOTIFY + consumer-group** giải bài toán *nhiều tiến trình đua nhau* — bài toán **chưa tồn tại** ở đơn tiến trình. Kéo vào = phức tạp thừa, đúng cái "core phình to" bạn muốn tránh.
- Giá trị thật của PRD nằm ở **contracts + kỷ luật** (envelope, command, checkpoint, permission, redaction, idempotency, "event-trước/effect-sau", "UI không sửa state"). Những thứ này **độc lập hạ tầng** và E21 giữ trọn.
- Khi thật sự cần production cluster: gắn adapter vào `EventSinkPort` (Kafka), `LiveBusPort` (Redis), `ControlStorePort` (Postgres), nâng `POST /api/commands`→WebSocket. **Không đụng core/supervisor.** Đó chính là phần T2 ở bảng trên.

> Muốn lật sang làm T2 ngay từ v1? Nói một câu, tôi viết lại tier + thêm các story hạ tầng (outbox relay, consumer-group, deadletter, NOTIFY listener) thành nhóm chính thay vì "sau Port".
