# hex_cases — Entity / Value Object / Domain Event trong hex_agent

> Tài liệu dạy học đi kèm **Lesson 36 — Entity vs Value Object vs Domain Event**.
> Mỗi case là một bản *distill trung thực* từ code thật trong codebase `hex_agent`,
> chỉ dùng thư viện chuẩn Python 3.14, chạy được độc lập.

---

## Pattern này xuất hiện ở đâu trong hex_agent

Codebase hex_agent phân tách rất rõ ba building block DDD tactical xuyên suốt control plane và runtime:

- **Entity** (mutable, có identity bền vững, equality by id, có lifecycle): xuất hiện ở quản lý trạng thái như `KernelSession` (`core/session.py:49-102`), `TaskLoopState` / `AcceptanceCheck` (`supervisor/state.py`), `CapabilityRegistry` (`core/registry.py`); và dạng "frozen-nhưng-tiến-hoá-qua-replace" như `Node` (`decompose_agent/node.py`), `RuntimeCheckpoint` (`control/checkpoint.py`).
- **Value Object** (immutable, không identity, equality by attribute, validate ở constructor): dùng dày đặc cho mọi structural contract — `Actor`, `TraceContext`, `RedactionInfo` (`control/events.py`), `Permission` (`control/permission.py`), `IssuedBy`/`CommandAck` (`control/commands.py`), `DoneWhen` (`decompose_agent/node.py`), và cả một thư viện VO trong `core/schemas.py`.
- **Domain Event** (frozen, past-tense, timestamped, broadcast): `RuntimeEvent` (`control/events.py`) là envelope event canonical; `Event` + `EventType` (`drag_from_zero/dragzero/events.py`) là hệ event enum-based append-only.

Pattern được áp dụng nghiêm ngặt nhất ở module `control/` (contract đòi hỏi immutability + validate) và `decompose_agent/` (Node và DoneWhen enforce invariant ngay khi construct).

---

## Hai case flagship

| # | Case | Building block minh hoạ | Nguồn thật |
|---|------|------------------------|-----------|
| [01](./01_runtime_event_actor_context/) | **RuntimeEvent + Actor + TraceContext** | Domain Event compose nhiều Value Object | `control/events.py:32-190` |
| [02](./02_node_donewhen_value_objects/) | **Node + DoneWhen** | Entity sở hữu Value Object | `decompose_agent/node.py:33-176` |

- **Case 01** dạy đặc trưng **Domain Event** (frozen, `event_id`, `created_at`, `schema_version`, broadcast) và cách nó *compose* các **Value Object** ngữ cảnh (`Actor`, `TraceContext`, `RedactionInfo`). Có đối chứng "event mutable thì hỏng".
- **Case 02** dạy quan hệ **Entity sở hữu Value Object**: `Node` (id, lifecycle, equality by id, tiến hoá qua `replace()`) chứa tuple `DoneWhen` (frozen, validate, equality by attribute). Có đối chứng "Entity equality theo attribute thì cache vỡ".

Mỗi case gồm: `README.md` (6 mục đầy đủ) + một file `.py` self-contained có `demo()`, narration tiếng Việt, assert chứng minh bất biến, và ít nhất một đối chứng anti-pattern.

---

## Vét cạn mọi occurrence

Xem [`CATALOG.md`](./CATALOG.md) cho bảng đầy đủ MỌI nơi pattern xuất hiện trong codebase (path:line, mô tả, độ rõ).

---

## Cách chạy

```bash
python3 01_runtime_event_actor_context/runtime_event_actor_context.py
python3 02_node_donewhen_value_objects/node_donewhen_value_objects.py
```

Cả hai thoát code 0, in narration từng bước, không traceback.

---

## Bản đồ về Lesson 36

```
        DDD TACTICAL — 3 BUILDING BLOCK  (ánh xạ vào hex_agent)
   ═══════════════════════════════════════════════════════════════
        ┌──────────────────────────┐
        │  ENTITY                   │  identity bền vững, mutable
        │  Node (decompose_agent)   │  KernelSession (core/session)
        │  equality by id           │  TaskLoopState (supervisor)
        │  ──────────────────────   │
        │   ↓ sở hữu (owns)         │
        │  ┌────────────────────┐   │
        │  │  VALUE OBJECT       │   │  immutable, no identity
        │  │  DoneWhen, Actor    │   │  Permission, IssuedBy
        │  │  TraceContext       │   │  equality by attribute
        │  │  validate @construct │  │
        │  └────────────────────┘   │
        └───────────┬──────────────┘
                    │ emits / publishes
                    ▼
        ┌──────────────────────────┐
        │  DOMAIN EVENT             │  past-tense fact, frozen
        │  RuntimeEvent (control)   │  Event (drag_from_zero)
        │  event_id + created_at    │  broadcast, idempotent
        │  + schema_version          │
        └──────────────────────────┘
```
