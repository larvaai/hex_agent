# CATALOG — Mọi dấu vết "CQRS & Event Sourcing" trong hex_agent

Bảng vét cạn các occurrence của pattern (write/read separation, event log, projection, replay, redaction-as-read-scoping) trong codebase. Đường dẫn tương đối so với gốc `/Users/uspro/Desktop/namnson/hex_agent/`. Mọi `path:line` đã được mở kiểm chứng.

| # | path:line | Vai trò trong CQRS + ES — mô tả | Độ rõ |
|---|---|---|---|
| 1 | `control/snapshot.py:189-365` | **Projection / Read Model.** `build_snapshot()` fold chuỗi `loop.*` event thành `TaskLoopSnapshot` (read model UI). CQRS thuần: event = write, snapshot = read, derive-không-mutate. → **Flagship 01** | cao |
| 2 | `control/events.py:113-190` | **Event envelope.** `RuntimeEvent` (frozen=True) — shape chuẩn của mọi event control-plane: `schema_version`, `seq`, `actor`/`trace`, `payload` raw vs `ui_payload` redacted. Nền của event-sourced system. → **Flagship 01/02** | cao |
| 3 | `control/emitter.py:39-96` | **Command handler / emit pipeline.** `EventEmitter.emit_event`: validate → stamp seq → redact → fan-out tới `EventSinkPort`. Đường publish duy nhất. → **Flagship 02** | cao |
| 4 | `observability/event_log.py:41-99` | **Append-only event store.** `EventLogger` implement sink: subscribe bus, append JSONL, đếm metrics, seq tăng dần dưới lock. → **Flagship 02** | cao |
| 5 | `core/events.py:11-31` | **Event Bus.** Pub/sub in-process; giao detached deep-copy cho mỗi subscriber → không observer mutate được event log. Bất biến cốt lõi của ES. → **Flagship 02** | cao |
| 6 | `control/event_registry.py:40-99` | **Event là contract.** `EventTypeRegistry`: catalog mọi `event_type` hợp lệ (nạp từ `runtime_event_types.yaml`); type lạ bị từ chối trước khi emit. Governance pattern. | cao |
| 7 | `control/command_registry.py:36-95` | **Command catalog.** `CommandTypeRegistry`: khai báo `apply_at` (`next_checkpoint`/`immediate_if_waiting`/`immediate`) + `requires_permission` cho từng `RuntimeCommand`. Ánh xạ command → thời điểm/quyền emit. | cao |
| 8 | `control/replay.py:23-81` | **Event log durability + dedup.** `EventReplayBuffer`: ring buffer (max 2048) các event dict cho client catch-up; dedup theo `event_id`, `events_after(seq)`, `needs_resync(seq)`. Key ES pattern. | cao |
| 9 | `control/checkpoint.py:27-50` | **Approval gate (command cần duyệt).** `RuntimeCheckpoint`: điểm pause chờ người duyệt trước hành động nguy hiểm; bắt đầu `waiting`, resolve về 1 terminal status. Không hẳn domain event (không past-tense) nhưng là command cần approval. | trung bình |
| 10 | `supervisor/state.py:80-145` | **Ranh giới của ES.** `TaskLoopState` (round_no, status, turns, artifacts, acceptance_checks): "current state" — **KHÔNG** rebuild từ events mà persist xuống SQLite. Đây là nơi full Event Sourcing dừng lại trong hex_agent. | cao |
| 11 | `orchestrator/checkpoint.py:1-143` | **Read-model update echo.** LangGraph SQLite persistence + JSON projection (`checkpoint.json`) lưu atomic qua `save_checkpoint`/`save_graph_projection`. Giống cập nhật read-model CQRS, nhưng write side (SQLite) không event-sourced. | trung bình |
| 12 | `ui/ide/bridge.py:38-95` | **Event adapter / transformer.** `KernelEventBridge.subscriber`: dịch event kernel (`tool.requested`/`tool.completed`/`tool.failed`) thành `loop.*` event của control-plane. Vai projection giữa hai domain. | trung bình |
| 13 | `control/redaction.py:37-73` | **Read-model scoping.** `Redactor.apply`: mask field nhạy cảm trong `ui_payload` trước khi gửi UI; lọc visibility per-subscriber. Vai projection (ai thấy gì). | trung bình |
| 14 | `tests/test_event_concurrency.py:9-41` | **Kiểm thử toàn vẹn ES.** Test EventBus giao detached + EventLogger seq an toàn dưới đồng thời: 250 event từ 10 worker → JSONL nhất quán, `sequence == 1..251`. | cao |
| 15 | `tests_audit/test_orchestrator_loop_rigor.py:1-804` | **Kiểm thử độ bền read-model.** Test `save_graph_projection` atomic + reload; round-trip projection giữ status/counters. Không phải full ES test (không replay event) nhưng chứng minh read-model durability. | trung bình |

## Phân tầng

- **Write/command path**: #3 (emitter), #6 (event registry), #7 (command registry), #9 (checkpoint gate).
- **Event store / log**: #4 (JSONL logger), #5 (bus), #8 (replay buffer), #2 (envelope).
- **Read/projection path**: #1 (build_snapshot), #11 (graph projection), #12 (bridge adapter), #13 (redaction scoping).
- **Ranh giới ES**: #10 (`TaskLoopState` persist SQLite, không rebuild-from-events) — đây là lý do hex_agent là **partial CQRS + limited ES**, không phải full Event Sourcing.
- **Kiểm thử bất biến**: #14, #15.

## Flagship đã dựng case

- **01** → `01_runtime_event_projection/` distill #1, #2 (+ helper snapshot.py:140-178).
- **02** → `02_event_emission_pipeline/` distill #3, #4, #5 (+ #6 registry, #13 redaction).
