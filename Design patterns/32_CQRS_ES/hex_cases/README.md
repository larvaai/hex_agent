# CQRS & Event Sourcing trong hex_agent — hex_cases

> Bộ case học rút ra từ codebase thật `hex_agent`, đi kèm bài học gốc [`../32_CQRS_ES.md`](../32_CQRS_ES.md).
> Mỗi case có một file `.py` **chỉ dùng stdlib, chạy được** (`python3 <file>.py` thoát code 0) và một `README.md` 6 mục.

---

## Pattern này có trong hex_agent không?

**Có — nhưng là partial CQRS + limited Event Sourcing**, không phải full ES. Đây là điều quan trọng nhất cần nắm:

- **CQRS (write/read tách)** — CÓ và rõ. Control plane (Epic E21) tách **command** (`RuntimeCommand`) khỏi **event** (`RuntimeEvent`), publish event lên một **event log JSONL append-only** qua `EventBus`, rồi **project** event đó thành read model `TaskLoopSnapshot` để UI vẽ. Write side (supervisor phát event) hoàn toàn tách khỏi read side (snapshot UI query).
- **Event Sourcing (state = fold(events))** — CÓ MỘT PHẦN. Event được dùng cho **audit trail, projection UI, giao tiếp giữa component**, và có đầy đủ envelope versioned + redacted + dedup + replay buffer. NHƯNG hệ thống **không** rebuild *trạng thái nghiệp vụ* từ event stream — nguồn sự thật để persist là **LangGraph SQLite** (`supervisor/state.py`). Đó là chỗ "full Event Sourcing" dừng lại.

Nói gọn: hex_agent dùng events như **kênh sự thật cho read/audit/replay**, còn write side vẫn ghi state vào DB. Đây chính là biến thể *"CQRS without full ES"* mà bài gốc liệt kê trong bảng variants.

---

## Bản đồ pattern trong code

```
         WRITE / COMMAND PATH                         READ / QUERY PATH
   ┌──────────────────────────────┐            ┌──────────────────────────────┐
   │ RuntimeCommand (gateway)      │            │  UI query thẳng snapshot      │
   │   ↓ apply_at + permission     │            │            ↑                  │
   │ command_registry.py           │            │  TaskLoopSnapshot (read model)│
   └──────────────┬───────────────┘            │            ↑ fold             │
                  ↓                              │  build_snapshot()  ← CASE 01 │
   ┌──────────────────────────────┐            └──────────────┬───────────────┘
   │ EventEmitter.emit_event   ◄── CASE 02                     │
   │  validate(event_registry)    │                            │ đọc ui_payload
   │  → stamp seq (SessionSeq)    │                            │
   │  → redact (Redactor)         │                            │
   │  → fan-out sinks             │                            │
   └──────────────┬───────────────┘                            │
                  ↓                                             │
   ┌──────────────────────────────┐    publish     ┌───────────┴──────────┐
   │ EventBus (detached deep-copy) │ ─────────────► │ RuntimeEvent stream  │
   └──────────────┬───────────────┘                └──────────────────────┘
                  ↓ subscribe
   ┌──────────────────────────────┐     ┌──────────────────────────────────┐
   │ EventLogger → events.jsonl    │     │ EventReplayBuffer (ring, dedup)   │
   │ (append-only event store)     │     │ catch-up cho client reconnect     │
   └──────────────────────────────┘     └──────────────────────────────────┘

   RANH GIỚI ES:  TaskLoopState (supervisor/state.py) → persist LangGraph SQLite
                  (KHÔNG rebuild-from-events → đây là "limited ES")
```

---

## Các case con

| Case | Thư mục | Distill từ (file:line thật) | Trọng tâm pattern |
|---|---|---|---|
| **01** | [`01_runtime_event_projection/`](./01_runtime_event_projection/) | `control/snapshot.py:189-365`, `control/events.py:113-190` | **Projection / Read Model**: fold `loop.*` events → `TaskLoopSnapshot`. State là *derived*, không mutate. |
| **02** | [`02_event_emission_pipeline/`](./02_event_emission_pipeline/) | `control/emitter.py:39-96`, `observability/event_log.py:41-99`, `core/events.py:11-31`, `control/redaction.py:37-73` | **Command→Event publish path**: validate → stamp seq → redact → fan-out → append-only log; idempotency + detached delivery. |

Mỗi case là một bản **distill trung thực**: giữ đúng vai trò/cấu trúc pattern, đổi tên cho dễ đọc, thay hạ tầng nặng (LLM/SQLite/SSE/file/YAML) bằng fake stdlib tối thiểu. Docstring đầu mỗi `.py` ghi rõ `path:line` nguồn.

Danh sách **vét cạn** mọi occurrence (15 mục): xem [`CATALOG.md`](./CATALOG.md).

---

## Chạy thử nhanh

```bash
python3 01_runtime_event_projection/runtime_event_projection.py
python3 02_event_emission_pipeline/event_emission_pipeline.py
```

Cả hai in narration tiếng Việt từng bước, có assert chứng minh bất biến pattern, có đối chứng "khi KHÔNG dùng pattern thì hỏng thế nào", và thoát code 0.

---

## Đọc thêm theo thứ tự

1. Bài học gốc [`../32_CQRS_ES.md`](../32_CQRS_ES.md) — concept, neuroscience analogy, trade-offs, checklist PR.
2. Case 01 — hiểu **read side** (projection / fold).
3. Case 02 — hiểu **write side** (emit pipeline / event store).
4. [`CATALOG.md`](./CATALOG.md) — soi mọi dấu vết còn lại trong codebase, đặc biệt `supervisor/state.py` để thấy **ranh giới** giữa "CQRS có" và "full ES chưa".
