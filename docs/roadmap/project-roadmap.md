# Project Roadmap — Epic Status & Timeline

Cập nhật: 2026-06-25 · Nguồn: git log, CHANGELOG.md, docs/spec/*, docs/roadmap/*, architecture-map-260625-2009

> **Chú ý về CHANGELOG.md**: File này **không cập nhật** cho E21 — mục mới nhất là E08 (2026-06-25). Commit log và PR #1 xác nhận E21 Phase A & B B1 đã ship. Tài liệu này lấy sự thật từ code thực tế, không từ CHANGELOG.

---

## Tóm tắt tình hình

| Giai đoạn | Trạng thái |
|---|---|
| **Nền tảng (P0)** | Xong: E01 Kernel, E02 Discipline, E03 LLM, E04 Observability |
| **Single-agent + tools (P1–P2)** | Xong: E05 Graph, E06 Safety, E07 Skills, E08 RAG (Qdrant) |
| **Multi-agent (P3)** | Xong: E09 Roles, E10 Delegation + TaskLoop |
| **Điều khiển realtime (P4, cross)** | Partial: E21 Phase A (contracts) + Phase B B1 (EventEmitter) — pending: transport, UI, reliability |
| **Khác** | Chưa bắt đầu: E11 Departments, E12 Router/Supervisor, E13 Factory, E14 Ledger, E15 Self-eval, E20 Labs |
| **Test & CI** | E19 Test Harness: 198 hàm test + 129 test audit (kiểm nghiệm strict) · CI .github/workflows/ci.yml gating |

---

## Epic Status Table (E01–E21)

| Epic | Tên | Sprint | Trạng thái | Commit/Anchor | Ghi chú |
|---|---|---|---|---|---|
| **E01** | Microkernel Core | S0 | ✓ Done | S0 · core/ | AgentKernel, registry, schemas, EventBus, chokepoint execute_tool |
| **E02** | Output Discipline | S0 | ✓ Done | S0 · discipline/ | JSON parse+repair, budget (max_steps 30), finish-gate |
| **E03** | LLM Adapter | S0 | ✓ Done | S0 · llm/ | OpenAI-compatible, JSON-mode, lazy init, retry (transient vs permanent) |
| **E04** | Observability | S0 | ✓ Done | S0 · observability/ | EventLogger JSONL + summary.json, EventBus, inspect CLI |
| **E05** | Single-agent Graph | S1 | ✓ Done | S1 · graph/, orchestrator/ | LangGraph compiled runtime, nodes: agent, tool, delegate, finish/fail |
| **E06** | Tools & Safety | S1 | ✓ Done | S1 · toolbox/, safety/, middleware/ | fs_read/write/list, terminal_run, SafeToolPort, sandbox jail, PolicyGate |
| **E07** | Skills System | S2 | ✓ Done | S2 · skills/ | Role-agnostic SKILL contracts, render(contract\|full) progressive disclosure |
| **E08** | RAG (Qdrant) | S2 | ✓ Done | f9e7870 · rag/ | VectorStorePort/EmbedderPort, Qdrant adapter (lazy client, uuid5 ids), health-gated |
| **E09** | Roles & Lenses | S2 | ✓ Done | S2 · roles/ | RoleView, allowed_tools = union − forbidden (cycle-break vs E07) |
| **E10** | Multi-agent + Delegation | S3–S4 | ✓ Done | 4377daa · supervisor/, delegation/ | TaskLoop, DelegationManager (separate chokepoint), session scope inherit |
| **E11** | Departments | P3 | ✗ Not started | — | Chỉ có trường string "department" ở RoleSpec, chưa có hạ tầng |
| **E12** | IntentRouter/Supervisor | P4 | ✗ Not started | PRD draft · supervisor/ dir = **E10**, không E12 | Phụ thuộc E10, E11, E13 |
| **E13** | Software Factory | P4 | ✗ Not started | — | Phụ thuộc E09, E10 |
| **E14** | Ledger & Memory | P4 | ✗ Not started | — | Phụ thuộc E06, E08 |
| **E15** | Self-eval & Governance | P4 | ⊝ Đã gộp vào E21 | — | merge-into-other → E21 (S21.33); deps E04, E10, E21 |
| **E19** | Test Harness (cross) | — | ✓ Done | 49b403c · tests/, tests_audit/ | 327 test functions, CI gates ruff + pytest, strict audit mode, no-xfail rule |
| **E21** | Realtime Control Plane | P4 (cross) | ⊕ Partial | Phase A: 7998c27, Phase B B1: f73d377 | Gộp E16+E17+E18; contracts ship, EventEmitter path ship; transport/UI/reliability pending |
| **E20** | Labs | sau S5 | ✗ Not started | — | Tiện ích dùng chung, xây sau nền vững |

**Legend**: ✓ Done (shipped + tested) · ⊕ Partial (một phần ship) · ✗ Not started · — (không có hoặc data)

---

## Sprint Mapping & Critical Path

### Phân bổ Sprint (từ docs/roadmap/dependency-map.md)

| Sprint | Phase | Epics | Cổng vào | Definition of Done |
|---|---|---|---|---|
| **S0** | P0 | E01, E03, E02, E04 | — | Kernel + LLM adapter (JSON-mode) + discipline + observability; smoke offline ✓ |
| **S1** | P1+P2 | E06, E05 | S0 | Tool chokepoint + sandbox; single-agent loop ✓ |
| **S2** | P2+P3 | E07, E08, E09 | S0, S1 | Skills + RAG + roles allowlist ✓ |
| **S3** | P3 | E10, E11 | S2 | TaskLoop + departments (E11 chưa hoàn thành) ⊕ |
| **S4** | P4 | E13, E12, E14 | S3 | Factory + router + ledger (chưa bắt đầu) |
| **S5** | P4 (cross) | E18, E16, E15, E17 | S4 | UI + review + self-eval + live control ⇒ **merged into E21** |
| **E19** | cross | — | tất cả | Test mỗi AC epic · CI gates · **327 functions** |

### Đường găng (Critical Path)

```
E01 ── E03 ── E02 ── E05 ── E09 ── E10 ── [E13? E12?]
└─ E04          └─ E06 ────┘
```

Con đường dài nhất quyết định timeline. **Đã hoàn thành đến E10** (xong cả S0–S4 cũng chưa để ý). E21 (P4 cross) vừa mở: Phase A done, Phase B B1 done, nhưng S-TRANSPORT/S-UI/S-CONTROL/S-RELIABILITY pending.

---

## E21 Realtime Control Plane — Chi tiết Frontier

### Bối cảnh

E21 **gộp ba epic cũ** E16 (Human Review Gate) + E17 (User Live Control) + E18 (UI Dashboard) thành một "mặt phẳng điều khiển realtime" cho vòng lặp đa-agent (TaskLoop Agent O + workers). Quyết định thiết kế: **right-size hạ tầng về SQLite/JSONL/EventBus đặt sau Port**, không bê nguyên Postgres/Kafka/Redis vào v1 local.

### 9 Giai đoạn nội bộ E21 (xem docs/spec/active/E21-realtime-control-plane/)

| Pha | Tên | Scope | Status | Commit/File |
|---|---|---|---|---|
| **A** | **S-CONTRACT** | RuntimeEvent envelope, RuntimeCommand, RuntimeCheckpoint, Permission, Redaction + 2 registry | ✓ Done | 7998c27 · control/events.py, control/commands.py, control/checkpoint.py, control/permission.py, control/redaction.py, control/{event,command}_registry.py |
| **B1** | **EventEmitter canonical path** | Envelope publish qua EventSinkPort; BusEventSink bridge → EventBus/EventLogger | ✓ Done | f73d377 · control/emitter.py |
| **B2–B14** | **Control-store + queue + intervention** | SQLite command queue + idempotency; approval-checkpoint engine; pending_human_commands vào O; permission record; audit log | ✗ Pending | — |
| **S-TRANSPORT** | **HTTP command endpoint + SSE** | POST /api/commands (auth + idempotency); SSE phát envelope đã redact; Last-Event-ID resume | ✗ Pending | — |
| **S-UI** | **Control Tower** | Graph · Timeline · Inspector · Approval modal · Permission editor | ✗ Pending | — |
| **S-CONTROL** | **Live command lifecycle** | pending_human_commands xuyên suốt; wait/stop/ask + pause/resume logic | ✗ Pending | — |
| **S-RELIABILITY** | **Crash recovery + degrade** | Resume từ approval-checkpoint; reconnect; degrade SSE; ring-buffer | ✗ Pending | — |

### Cái gì đã có (Phase A + B B1)

- **`control/events.py:113`** — `RuntimeEvent` envelope (event_id, kind, actor, ts, redaction, ui_payload)
- **`control/commands.py`** — `RuntimeCommand` frozen contract + validation
- **`control/checkpoint.py`** — `RuntimeCheckpoint` (state, risk_level)
- **`control/permission.py`** — `Permission` (scope, capabilities, effective_from)
- **`control/redaction.py:37`** — `Redactor` recursive secret-mask (14 keys), never mutates original
- **`control/event_registry.py`** — allowlist (visibility, durable, redact fields)
- **`control/command_registry.py`** — allowlist (apply_at, requires_permission)
- **`control/emitter.py:53`** — `EventEmitter.emit_event()` — gate → seq → redact → fan-out
- **`control/ports.py:15`** — `EventSinkPort` — swap seam cho adapter (v1: `BusEventSink`, T2: Kafka/Redis/etc)

**KHÔNG yet wired vào live runtime hay UI**:
- supervisor emitter opt-in, default None (supervisor/graph.py:47)
- command queue, approval-checkpoint, pending_human_commands chưa tồn tại
- POST /api/commands, SSE redaction chưa có
- Control Tower UI chưa có

### Tầng hạ tầng (T1 MVP vs T2 multi-node)

| Vai trò thiết kế | T1 MVP (local, now) | T2 after-Port (multi-node, future) |
|---|---|---|
| Durable backbone | JSONL + SQLite (EventLogger) + seq | `EventSinkPort` → Kafka |
| Live fanout | in-process EventBus + ring-buffer | `LiveBusPort` → Redis Streams |
| Command store | SQLite (extend TaskLoopStore) | `ControlStorePort` → Postgres |
| Command channel | POST /api/commands + polling | WebSocket / async command API |

---

## Sắp xếp cách triển khai tiếp theo

### Điều kiện trước khi bắt tay UI (xem docs/spec/active/E21-realtime-control-plane/01_BACKEND_STANDARDIZATION_BEFORE_UI.md)

Bắt đầu S-TRANSPORT + S-UI chỉ khi **xong**:
1. Control-store (SQLite): commands, checkpoints, permissions, audit tables
2. Command queue + idempotency logic
3. Approval-checkpoint engine ở `supervisor/_drive` (pause-before-tool, approval-wait)
4. `pending_human_commands` vào `_state_view` cho O
5. Redaction boundary test (0 secret lọt ra `ui_payload`)
6. Audit trail có actor (command/permission/checkpoint/tool/approval events)

### Theo thứ tự gợi ý (từ 00_UNDERSTANDING_AND_RECONCILIATION.md)

1. **B2–B14 (Control-store + queue)** — mở khoá command persistence + approval logic
2. **S-CONTROL** — wire command lifecycle vào supervisor._drive
3. **S-TRANSPORT** — POST /api/commands + auth + SSE redaction
4. **S-UI** — Control Tower panels
5. **S-RELIABILITY** — crash recovery, reconnect, degrade
6. **S-EXPANDED** — instrumentation/evidence/artifact/work-tree (long tail)

---

## Epic chưa bắt đầu (E11, E12, E13, E14, E15, E20)

| Epic | Tên | Phụ thuộc | Ghi chú |
|---|---|---|---|
| **E11** | Departments | E09, E06, E08 | Chỉ có string field ở RoleSpec. Phần hạ tầng phân chia công việc theo department/team chưa có. |
| **E12** | IntentRouter / GlobalSupervisor | E10, E11, E13 | **Chú ý**: thư mục `supervisor/` hiện có là **E10** (TaskLoop, Agent O, _drive), không phải E12. E12 là bộ định tuyến intent đa nhiệm chưa bắt đầu. |
| **E13** | Software Factory | E09, E10 | Spec → handoff. Chưa có. |
| **E14** | Ledger & Memory | E06, E08 | Durable work + state ledger. Chưa có. |
| **E15** | Self-eval & Governance | E04, E10, E21 | Acceptance criteria evaluation, self-judgment. **Đã gộp vào E21** (verdict merge-into-other → siết `judge_acceptance` ở E21 S21.33; không còn epic future độc lập). |
| **E20** | Labs | sau S5 | Tiện ích dùng chung, xây sau khi nền vững. |

---

## Test Harness (E19) — Verify Everything

**Tổng cộng**: 198 test functions (tests/) + 129 test audit (tests_audit/) = **327 functions**.

**Kỷ luật E19**:
- No xfail / no lowered assertion (tất cả AC phải xanh)
- CI gating (.github/workflows/ci.yml): ruff (lint) + pytest tests/ + pytest tests_audit/ trên Python 3.11
- Qdrant integration test skip nếu server không reachable (default offline, không docker)
- Audit strict: resolves **42 findings** (49b403c)

**Coverage**:
- E01–E10: tests hoàn chỉnh, AC xanh
- E19: 327 functions kiểm chứng
- E21 (Phase A+B): unit tests cho contract/emitter (chưa integration)
- E11–E15, E20: chưa có test (chưa code)

---

## Key Invariants (Verified Core)

Đã verify trực tiếp trên codebase (architecture-map-260625-2009):

1. **Chokepoint duy nhất LLM + tool**: `AgentKernel.execute_tool` (core/kernel.py:63) — lõi không có đường tắt
2. **Delegation chokepoint riêng**: `DelegationServicePort.delegate` (delegation/manager.py:63) — không phải method kernel
3. **Kernel frozen trước session đầu**: core/kernel.py:48 → freeze registry/config/middleware
4. **Per-run state ở KernelSession**: session scope inherit ⊆ parent (core/session.py:163)
5. **SQLite là truth duy nhất**: orchestrator/checkpoint.py `langgraph.sqlite`; checkpoint.json chỉ là UI projection
6. **AgentState serializable**: schema_version=2, encode/decode (graph/state.py)
7. **Hai safety layer song song**: PolicyGate (chokepoint name-deny) + SafeToolPort (per-tool, argv/git/destructive) + workspace sandbox
8. **Budget ở graph nodes**: step/parse/same-tool enforced tại các node, BudgetGuard cố ý **không wire** ở bootstrap (per-run state)

---

## Cảnh báo: Tài liệu cũ

Các file dưới đây là **snapshot lịch sử**, không phải sự thật hiện tại:

- **README.md** — sprint S0 snapshot (E01–E04 only)
- **project_context.txt** — S0 snapshot
- **MAP.md** — auto-generated, không được regen lại (chạy `python tools/gen_map.py` để cập nhật)
- **CLASS_ENCYCLOPEDIA.md** — explicit historical snapshot, trước KernelSession/delegation/control

**Các file có thẩm quyền**: CHANGELOG.md (E01–E08, chưa cập nhật E21), git log, docs/spec/, docs/roadmap/, architecture-map-260625-2009.

---

## Liên kết

- **Thiết kế E21 đầy đủ**: docs/spec/active/E21-realtime-control-plane/
  - 00_UNDERSTANDING_AND_RECONCILIATION.md — bối cảnh + quyết định right-size
  - 01_BACKEND_STANDARDIZATION_BEFORE_UI.md — điều kiện trước UI
  - PRD.md, stories.md, acceptance.md — spec chi tiết
- **Build order**: docs/roadmap/dependency-map.md
- **Runtime flow**: docs/reference/runtime-flow.md (chokepoint, graph topology, endpoints)
- **Known risks**: docs/reference/known-risks.md (failure modes, edge cases)
- **Architecture**: plans/reports/architecture-map-260625-2009-hex-agent-report.md
