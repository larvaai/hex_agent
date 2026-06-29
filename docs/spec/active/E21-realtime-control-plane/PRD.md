# E21 — Realtime Control Plane (PRD)

Phase: P4 (cross) · Hợp nhất: **E16** (Human Review Gate) + **E17** (User Live Control) + **E18** (UI Dashboard) + phần contract/observability còn thiếu.
Quyết định nền (đã chốt): **right-size hạ tầng về SQLite/JSONL/EventBus đặt sau Port**; command channel v1 = **`POST /api/commands`**; SSE giữ vai trò phát event một chiều.

> Bối cảnh & lý do: [`00_UNDERSTANDING_AND_RECONCILIATION.md`](00_UNDERSTANDING_AND_RECONCILIATION.md). Điều kiện-trước-UI: [`01_BACKEND_STANDARDIZATION_BEFORE_UI.md`](01_BACKEND_STANDARDIZATION_BEFORE_UI.md). Phủ trọn 20 Feature của PRD "Production Control Tower" + phân tầng T1/T2: [`02_FULL_FEATURE_MAP.md`](02_FULL_FEATURE_MAP.md).

## Problem
Vòng lặp đa-agent (Agent O + worker, E10) chạy "kín": người dùng không thấy O đang gọi ai, ai pending/running, và **không can thiệp được giữa chừng** một cách an toàn. UI hiện tại chỉ *quan sát* (polling-diff snapshot), không có kênh điều khiển, không contract chuẩn cho event/command, không redaction, không audit.

## Goal
Một mặt phẳng điều khiển realtime tuân **một luật bất biến**:

> UI chỉ **observe snapshot** + **gửi command**. Runtime kiểm policy → Agent O nhận **command đã validate, có cấu trúc** → áp dụng tại **checkpoint an toàn** → UI thấy thay đổi **qua event stream**. Mọi can thiệp sinh event có **redaction + idempotency + audit**; agent không tự vượt quyền; mọi state-transition quan trọng đều có event.

## Scope — In
- **Contracts (sau Port, không I/O):** `RuntimeEvent` envelope + event-type registry; `RuntimeCommand` + command-type registry; `RuntimeCheckpoint`; `Permission`; `Redaction`.
- **Backend chuẩn hoá:** control-store SQLite (commands/checkpoints/permissions/audit); `TaskLoopSnapshot` read-model (live status); command queue + idempotency; intervention points + pause/resume + approval-checkpoint trong `_drive`; permission do người chỉnh (`effective_from=next_checkpoint`); `pending_human_commands` vào input của O; audit log có actor.
- **Transport:** `POST /api/commands` (auth + idempotency); SSE phát envelope **đã redact** + resume bằng `Last-Event-ID`; `GET /api/snapshot` trả `TaskLoopSnapshot`.
- **UI Control Tower:** Agent Graph · Event Timeline · Agent Inspector · Checkpoint/Approval modal · Permission Editor · Payload Inspector · Replay.
- **Reliability (right-size):** resume tại approval-checkpoint; reconnect; degrade khi event-sink lỗi.

## Scope — Out
- Postgres/Kafka/Redis/outbox/WebSocket (để **sau Port** cho giai đoạn multi-node; không làm ở v1).
- Logic sinh plan/proposal (E13/E15) — E21 chỉ *review/điều khiển*, không sinh.
- Multi-user RBAC đầy đủ (v1 chỉ authz tối thiểu cho kênh mutate).

## Phân tầng v1 (T1) vs sau-Port (T2)
Toàn bộ 20 Feature của PRD "Production Control Tower" được bắt trọn (bản đồ ở [`02_FULL_FEATURE_MAP.md`](02_FULL_FEATURE_MAP.md)), nhưng chia tầng để giữ "core thin":
- **T1 — làm ở v1 (local):** F1–F7 (SSE), F11–F17, F20 + health/metrics tối thiểu của F18. Hạ tầng: SQLite/JSONL/`EventBus`/`POST /api/commands`/SSE.
- **T2 — sau Port (multi-node, không làm v1):** F8 Redis (`LiveBusPort`), F9 Kafka (`EventSinkPort`), F10 Postgres+outbox+NOTIFY (`ControlStorePort`), WebSocket của F7, scale/alert của F18. Contract giữ nguyên; chỉ gắn adapter khi cần — **không đụng core/supervisor**.
- **Cross-epic:** F19 Work Management thuộc E13/E14; E21 chỉ phát event + link `task_id`.

> Nếu muốn lật T2 thành mục tiêu v1 ngay (làm thẳng Kafka/Redis/Postgres), đây là chỗ đảo quyết định — báo một câu, tôi re-tier và thêm nhóm story hạ tầng tương ứng.

## Slices (đơn vị giao hàng)
- **S-CONTRACT** (S21.1–S21.7): envelope/command/checkpoint/permission/redaction + 2 registry.
- **S-BACKEND** (S21.8–S21.14): control-store, snapshot projection, command queue, intervention/approval, permission editable, commands→O, audit. ⇐ *điều kiện-trước-UI*.
- **S-TRANSPORT** (S21.15–S21.17): command endpoint + authz, SSE redacted, snapshot API.
- **S-UI** (S21.18–S21.23) ⊇ **E18** + **E16**: các panel Control Tower + approval modal.
- **S-CONTROL** (xuyên suốt) ⊇ **E17**: `pending_human_commands` (S21.13) + command lifecycle.
- **S-RELIABILITY** (S21.24–S21.26): resume/reconnect/degrade.
- **S-EXPANDED** (S21.27–S21.45): instrumentation breadth (hook/skill/rule, raw↔validated, span), orchestration depth (invocation/brief, evidence), artifact control + versioning, role-based payload access, state machine + lock, backpressure, causal debugging, work-tree linkage, production gates. Xem [`02_FULL_FEATURE_MAP.md`](02_FULL_FEATURE_MAP.md).

## Dependencies
E10 (TaskLoop + `_drive` + Blackboard), E04 (EventLogger/JSONL), E06 (`PolicyGate`/`execute_tool`), E09 (role catalog cho `AddAgentToLoop`). Thay thế các draft E16/E17/E18.

## Success metrics / Exit
- UI thấy event mới qua SSE < ~500ms (local); command được ACK < ~300ms sau khi server nhận.
- 100% command có `command_id` + `idempotency_key`; duplicate không áp dụng hai lần.
- 100% event đi qua envelope chuẩn (có `event_id`, `actor`, `redaction`); **0** secret lọt ra `ui_payload` (test).
- `Pause` không kill agent đang chạy; tool high-risk không chạy khi checkpoint chưa `approved`.
- Crash giữa chừng → resume từ approval-checkpoint, không chạy lại turn đã xong.
- Từ audit dựng lại được "agent X được thêm vì sao, ai, round nào, quyền lúc đó".
- Không có core/supervisor import trực tiếp transport/storage (đều sau Port).

## Open questions
- `auto_approve` cho checkpoint `risk_level=low` bật mặc định hay tắt mặc định?
- Token cho `POST /api/commands`: token-per-session sinh lúc start run, hay chỉ same-origin guard cho v1 local?
- Ring-buffer SSE giữ tối đa bao nhiêu event/session trước khi fallback đọc JSONL?
