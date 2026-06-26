---
id: 260626-0212-e21-control-plane-ui-fake-backend
title: "E21 Control-plane UI dựng trước trên fake backend (full T1)"
description: "Dựng UI control-plane (Graph/Timeline/Inspector/Approval/Send) trên một fake server Python reuse control/ dataclass — drop-in vào backend thật = đổi URL."
status: completed
mode: hard
tdd: true
priority: P2
branch: feat/o-delegation-flexibility
created: 2026-06-26
decisions: [DEC-6, DEC-9]
brainstorm: plans/reports/e21-ui-first-fake-backend-260626-0133-brainstorm-report.md
epics: [E21]
phases:
  - phase-1-backend-contracts.md
  - phase-2-ts-contract-gen.md
  - phase-3-fake-control-server.md
  - phase-4-frontend-scaffold-adapter.md
  - phase-5-graph-timeline.md
  - phase-6-inspector-approval-send.md
  - phase-7-contract-seam-test.md
touchpoints:
  # Create (backend)
  - control/snapshot.py            # NEW — TaskLoopSnapshot + build_snapshot
  - control/replay.py              # NEW — EventReplayBuffer (ring + Last-Event-ID + reality inject)
  - tools/gen_ts_contracts.py      # NEW — dataclass → .d.ts generator + --check drift-guard
  - tools/gen_t1_fixture.py        # NEW — sinh fixtures qua dataclass thật + Redactor
  - tools/fake_control_server.py   # NEW — stdlib HTTP/SSE fake (reuse control/)
  - fixtures/control_plane/t1_scenario.events.jsonl  # NEW (generated, committed)
  # Create (frontend, Vite React TS, all under ui/control-plane/)
  - ui/control-plane/              # NEW project (scaffold + 4 màn + adapter + tests)
  # Modify (backend)
  - control/commands.py            # +CommandAck dataclass (cạnh RuntimeCommand)
  - config/runtime_command_types.yaml  # +SubmitPrompt (red-team F5 — Send cần command_type)
  - tests/test_control_contracts.py
  - tests_audit/test_contract_roundtrips.py
  - CHANGELOG.md                   # code-standards §5
  - docs/GLOSSARY.md               # thuật ngữ mới
unchanged_on_purpose:
  - ui/server.py                   # console cũ — DEC-6 #6, transport khác, để yên
  - control/events.py              # RuntimeEvent reuse, không sửa
  - control/checkpoint.py, control/permission.py, control/redaction.py  # reuse
  - config/runtime_event_types.yaml  # event type đã khai báo đủ (loop.* + command.*)
  - supervisor/**                  # build_snapshot ĐỌC loop.* event supervisor PHÁT SẴN (graph.py) → thật-sự unchanged; wiring live = drop-in sau
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan: E21 Control-plane UI dựng trước trên fake backend (full T1)

> hs:cook ĐỌC file này làm hợp đồng. Mọi claim không hiển nhiên có anchor
> (`file:line` / AC-id). Tag `[UNVERIFIED]` nếu thiếu anchor.

## Tổng quan

Dựng **UI control-plane** (lát T1) chạy trên một **fake backend** trước khi backend
thật emit event. Giá trị nằm ở **cái seam** (đường nối): nếu fake "nói đúng tiếng
backend thật", lúc đấu nối UI chỉ đổi URL chứ không sửa render.

Vì sao (giải thích cho người mới): UI vẽ lên *hình dạng dữ liệu* (data shape). Có 5
shape UI tiêu thụ; 3 đã là dataclass thật trong `control/`, **2 còn thiếu**
(`TaskLoopSnapshot`, `CommandAck`). Nếu fake bịa shape khác backend thật → lúc nối,
UI render sai field, vỡ màn Graph/Inspector. Nên kế hoạch **tạo 2 dataclass còn
thiếu TRƯỚC**, rồi sinh TypeScript **từ** dataclass (single source of truth), rồi mới
viết UI. Fidelity là **by-construction** (serialize từ dataclass thật), không phải
by-discipline.

Cách giữ "drop-in chỉ sửa chút" *đúng thật*: cho fake chạy **cùng đường ống** với
real — fake là Python reuse `control/`: dùng `Redactor().apply()` thật
([control/redaction.py:65](../../control/redaction.py)), `SessionSeq.next()` thật
([control/events.py:204](../../control/events.py)), chỉ stream `ui_payload`
([control/events.py:7-9](../../control/events.py)). Khác đường ống thì mọi cái khó
(reconnect, dedup, redaction, latency) bị giấu tới phút cuối.

## Quyết định đã khoá

**User chốt (phiên này — scope gate):**
- **L1** — Scope = **full T1**: observe (Graph+Timeline+Inspector) **+ control**
  (Approval modal + prompt-box/Send + write path `POST /api/commands`). (DEC-6 #5).
- **L2** — Authz fake = **static-token seam** trên `POST /api/commands`: thiếu/sai token
  → 401/403 (AC S21.15 [acceptance.md:61](../../docs/spec/active/E21-realtime-control-plane/acceptance.md)).
  Không có hệ login thật — chỉ cái seam, để đường reject **honest** + drop-in giữ contract.
- **L3** — Fake **inject reality**: random latency, ép SSE drop→reconnect, trùng
  `event_id`, trùng `idempotency_key`. UI phải thật-sự xử lý dedup / Last-Event-ID /
  idempotency trước khi chạy được (trị R2 "fake quá sạch").

**DEC-6 (brainstorm) đã khoá:** fake = Python reuse `control/` (Hướng B); stack
React+Vite+TS; console cũ `ui/server.py` để yên, dựng mới song song `ui/control-plane/`;
Done = demo tương tác trên fixtures + **contract-seam test**.

**DEC-9 (tự chốt phiên này — đã ghi register `docs/decisions.md`; sub-label D1–D8):**
- **D1 — `CommandAck` shape** = `{command_id, status∈received|rejected, seq?,
  rejection_reason?, created_at}`. ACK là *biên nhận đồng bộ* (<~300ms); `accepted`/
  `applied` đến **sau** qua SSE (AC S21.15 [acceptance.md:62](../../docs/spec/active/E21-realtime-control-plane/acceptance.md)).
  Đặt trong `control/commands.py` cạnh `RuntimeCommand` (DRY, gateway đọc cùng module).
- **D2 — Generate-TS** = sinh `.d.ts` **trực tiếp** từ field-list của `as_dict`
  (introspect dataclass), **không** qua JSON-Schema trung gian (YAGNI, không thêm dep).
  Drift-guard = `python tools/gen_ts_contracts.py --check` (regenerate vào buffer + so
  file đĩa, exit 1 nếu lệch) — đặc tả độc lập, KHÔNG mượn `gen_map.py` (gen_map không có
  `--check`/argparse — red-team F10).
- **D3 — `TaskLoopSnapshot` v1 field-set** (xem Phase 1): `build_snapshot` fold trên
  **`loop.*` event supervisor PHÁT SẴN** ([graph.py](../../supervisor/graph.py):
  `loop.team_composed/decision/turn/tool/parse_error`), **không** `agent.*` (chưa ai
  phát — red-team F1). `AgentView.permission/allowed_tools/context_packet` là
  **optional**, chỉ điền khi có event mang permission (fixture cấp; binding live hoãn —
  F6). Hoãn `pending_human_commands`/audit/span sang v2.
- **D4 — Ring-buffer** = **2048 event/session**; **vượt ring → resync** (client re-fetch
  `GET /api/snapshot` + replay JSONL, AC S21.16 — red-team F7), không im lặng mất event.
- **D5 — Fake server stdlib-only** (`http.server.ThreadingHTTPServer`, giống
  [ui/server.py:16](../../ui/server.py)) — **không** thêm dep Python. SSE = 1 thread/conn
  → demo single-client + cap connection (F12).
- **D6 — Visibility gate thật** (red-team F2): fake SSE **drop** event có registry
  `visibility=='secret'` (logic thật dù chưa type nào secret hôm nay — test dựng 1 event
  secret để chứng minh gate); test redaction key-masking (`api_key→[REDACTED]`) trên event
  `ui_safe`/`internal` **reachable**, không phải đường chết.
- **D7 — Read-path token qua query-param** (red-team F8): `EventSource` không set header
  được → token cho SSE qua `?token=`; cả fake lẫn real honor cùng cách → drop-in giữ
  contract đọc. Write (`POST /api/commands`) vẫn token header (L2).
- **D8 — `SubmitPrompt` command_type** (red-team F5, user-chốt): thêm vào
  `config/runtime_command_types.yaml` (`apply_at: next_checkpoint, requires_permission:
  null`) — Send = inject task O đọc ở checkpoint kế (B7). Fake gọi
  `CommandTypeRegistry.assert_known()` → command_type lạ → 400+`command.rejected` (F4).

## Ràng buộc (constraint-scan)

- **ownership.yaml** ([harness/data/ownership.yaml](../../harness/data/ownership.yaml)):
  fence chỉ `docs/ state/ standards/ plans/`. `control/`, `ui/`, `tools/`, `fixtures/`
  **ngoài fence** → không có ràng buộc fs_guard, tự do tạo file.
- **stage-policy.yaml**: `pr/ship/deploy` cần `[verification, review-decision,
  plan-approval]`; `require_plan` true cho hard stage. Plan này LÀ artifact mở cổng ship.
- **code-standards** ([docs/code-standards.md](../../docs/code-standards.md)): Python
  `snake_case`, class `PascalCase` (§3); docstring dòng đầu `"""<mục đích>. Epic E21."""`
  (§5) → tự vào MAP.md; CHANGELOG +1 dòng (§5); TDD red→green, không weaken assertion (§4).
- **system-architecture** ([docs/system-architecture.md:248-271](../../docs/system-architecture.md)):
  control-plane = E21; `EventSinkPort` là seam transport ([control/ports.py:15](../../control/ports.py)).
  Fake là một *consumer* của envelope, **không** đụng chokepoint (`execute_tool`,
  `delegate`) → không vi phạm bất biến §1.1/§1.8.
- **Bất biến UI** ([01_BACKEND...md:3](../../docs/spec/active/E21-realtime-control-plane/01_BACKEND_STANDARDIZATION_BEFORE_UI.md)):
  "UI không sửa state trực tiếp" → mọi hành động = phát `RuntimeCommand`.

## Phases

| # | Theme | Phụ thuộc | Ngôn ngữ | Cỡ | Gate |
|---|---|---|---|---|---|
| 1 | Backend Contracts (`snapshot.py`, `CommandAck`) | — | Python | M (3 file) | pytest |
| 2 | TS Contract Gen + drift-guard | 1 | Python | S (3 file) | pytest |
| 3 | Fake Control Server (replay+SSE+cmd+authz+reality) | 1 | Python | L (5 file) | pytest |
| 4 | Frontend scaffold + thin adapter | 2 | TS | M (project) | vitest+tsc |
| 5 | Agent Graph + Event Timeline (read path) | 3,4 | TS | M | vitest+tsc |
| 6 | Inspector + Approval modal + Prompt/Send (control) | 3,4 | TS | M | vitest+tsc |
| 7 | Contract-seam test + demo (định nghĩa Done) | 3,5,6 | Both | M | pytest+vitest |

**Thứ tự = thứ tự seam:** shape (1) → type (2) → fake nói shape (3) → UI đọc shape
(4-6) → chốt seam đúng (7). Mỗi phase tự-chứa, không phụ thuộc runtime vào phase song
song. Phase 5 & 6 đều phụ thuộc 3+4 nhưng **không** phụ thuộc lẫn nhau (file riêng).

> **Cảnh báo cỡ (phase-decomposition #3/#4):** 7 phase, Phase 3 chạm 5 file. Đây là
> trần đã cân nhắc cho "full T1" (user khoá L1). Ranh giới commit tự nhiên: sau Phase
> 3 (backend seam xong) và sau Phase 6 (UI xong, trước seam-test).

## Out of scope (đợt này)

- **Backend wiring thật**: supervisor emit live → snapshot. Slice này build_snapshot là
  hàm thuần đọc event; nối live = drop-in sau (ghi BACKLOG).
- **B5/B7/B8/B10/B11** (permission editor live, pending_human_commands vào O, audit query,
  cancellation/Stop, token streaming) — ngoài T1, ở slice sau.
- **Hợp nhất console cũ** `ui/server.py` (R4) — nợ kỹ thuật, không phình lát 1.
- **Runtime validator (zod)** TS-side — fake server đã validate qua `__post_init__` thật.
- **Replay view (S21.23), Permission Editor (S21.22)** — T2/T3.

## Acceptance (toàn plan)

- [ ] Mỗi phase red→green TDD; gate của phase đó xanh **trước** khi sang phase kế.
- [ ] 5 shape đều là dataclass thật trong `control/`; `tools/gen_ts_contracts.py --check`
      exit 0 (TS đồng bộ dataclass).
- [ ] Fake server: `GET /api/snapshot`→`TaskLoopSnapshot` (no raw secret); SSE chỉ
      `ui_payload` + `seq` + Last-Event-ID catch-up không trùng; `POST /api/commands`
      → 401 không token, 400+`command.rejected` sai schema, ACK<300ms khi hợp lệ,
      `idempotency_key` trùng áp 1 lần.
- [ ] **Contract-seam test xanh** (Phase 7): UI (1) chỉ đọc `ui_payload`, (2) render
      `[REDACTED]` đúng [redaction.py:34](../../control/redaction.py), (3) Approve gửi
      `RuntimeCommand` thật qua POST (không mutate state UI-side), (4) reconnect dùng
      Last-Event-ID.
- [ ] Demo tương tác chạy: `python tools/fake_control_server.py` + `npm --prefix
      ui/control-plane run dev` → kịch bản T1 (O chọn A,B,C → checkpoint waiting →
      Approve) hiển thị đúng.
- [ ] `python -m pytest tests/ tests_audit/ -q` xanh; `python run_smoke.py` →
      `CORE_AGENT_SMOKE_OK`.

## Rollback

Mỗi phase một commit `feat(E21): ...` (code-standards §3). Hoàn tác = `git revert
<range>`. Không có migration DB / file guarded → revert sạch. Frontend là project mới
biệt lập `ui/control-plane/` → xoá thư mục là gỡ hoàn toàn, không ảnh hưởng `ui/server.py`.

## Risks

| Rủi ro | Mức | Mitigation |
|---|---|---|
| **R1 — 2 shape thiếu (`TaskLoopSnapshot`,`CommandAck`) → drift/vách đá tại điểm nối** | cao | Phase 1 tạo trước MỌI thứ khác; derive snapshot từ `TaskLoopState` [supervisor/state.py:80-116](../../supervisor/state.py) + `OrchestratorDecision` [contracts.py:54-65](../../supervisor/contracts.py) + spec B2 [01_BACKEND...md:20](../../docs/spec/active/E21-realtime-control-plane/01_BACKEND_STANDARDIZATION_BEFORE_UI.md) |
| **R2 — "fake quá sạch" che reality** | cao | L3: fake inject latency/reconnect/dup; contract-seam test (Phase 7) assert UI xử lý thật |
| **R3 — rò secret / approval giả lúc demo** | cao nếu bỏ | Fake **bắt buộc** `Redactor().apply()` thật + chỉ stream `ui_payload`; `visibility=secret` → không stream (AC S21.16); Approve gửi command thật |
| **R4 — TS drift im lặng khỏi dataclass** | tb | Phase 2 drift-guard `--check`+`git diff`; CI đỏ nếu quên regen |
| **R5 — Frontend phình (React Flow + virtualization)** | tb | Junior reader: React Flow ecosystem chín; auto-layout `dagre`; chỉ T1 surface, không thêm screen |
| **R6 — fake chạy `import control.*` từ `tools/` lỗi path** | thấp | Chạy từ repo root; test `tests/test_fake_control_server.py` import như module |

## Red-team disposition (gate trước cook)

Report: [reports/from-code-reviewer-to-planner-red-team-plan-review-report.md](reports/from-code-reviewer-to-planner-red-team-plan-review-report.md).
15 finding, **15 Accept / 0 Reject**. 3 finding (F1/F2/F5) đã verify bằng `grep` lại
codebase trước khi nhận (two-way Evidence Filter).

| # | Sev | Disposition | Propagate vào |
|---|---|---|---|
| F1 | C | **Accept** — `build_snapshot` fold `loop.*` (supervisor phát sẵn), KHÔNG `agent.*` (verify: `grep` supervisor chỉ ra `loop.team_composed/decision/turn/tool/parse_error`, 0 `agent.*`) | Phase 1 (fold table+status), Phase 3 (fixture phát `loop.*`) |
| F2 | C | **Accept** — visibility-gate thật (drop `secret`) + redaction test trên event reachable (verify: 0 event `visibility=secret` trong registry; `Redactor.apply` không drop) | Phase 3 (2 test tách: gate + key-mask) |
| F3 | H | **Accept** — fixture stamp `seq` qua `SessionSeq`/emitter (seq default 0, chỉ stamp ở [emitter.py:57](../../control/emitter.py)) | Phase 3 (gen fixture) |
| F4 | H | **Accept** — fake gọi `CommandTypeRegistry.assert_known()` ([command_registry.py:43](../../control/command_registry.py)) | Phase 3 (POST validate) |
| F5 | H | **Accept (user-chốt)** — thêm `SubmitPrompt` command_type (verify: 0 command_type cho Send) | config + Phase 6 |
| F6 | H | **Accept** — `AgentView.permission/allowed_tools/context_packet` optional, điền từ event (Permission không có `agent_id` [permission.py:19-27](../../control/permission.py)) | Phase 1 (optional), Phase 3 (fixture) |
| F7 | H | **Accept** — out-of-ring → resync (snapshot+JSONL), test drop-past-ring | Phase 3 (fallback+test) |
| F8 | M | **Accept** — read-path token qua `?token=` (EventSource no-header) | Phase 3 (fake), Phase 4 (adapter) |
| F9 | M | **Accept** — dedup keyed `(session_id, idempotency_key)`, bounded | Phase 3 |
| F10 | M | **Accept** — bỏ analogy `gen_map.py --check` sai; đặc tả `--check` độc lập | Phase 2, plan D2 |
| F11 | M | **Accept** — bảng `loop.*`-event→status tường minh (merge F1) | Phase 1 |
| F12 | M | **Accept** — cap SSE connection + demo single-client | Phase 3 |
| F13 | L | **Accept** — seam assert qua adapter API surface (key vắng mặt), không grep `.payload` | Phase 7 |
| F14 | L | **Accept** — bỏ claim MAP.md phủ `tools/` (deny-listed [gen_map.py:8]); chỉ `control/snapshot.py` vào MAP | Phase 1 |
| F15 | L | **Accept** — thêm test reality-ON dedup/order | Phase 3 |

**Blast radius (từ report):** không có đường mất-dữ-liệu (frontend là dir biệt lập,
revert sạch). Rủi ro thật = **rework tập trung ở seam**: F1/F3/F6/F11 cùng đánh vào
snapshot/SSE model — đã sửa tại Phase 1/3 trước khi cook chạm UI.

## Liên quan
- Brainstorm/DEC-6: [e21-ui-first-fake-backend...report.md](../reports/e21-ui-first-fake-backend-260626-0133-brainstorm-report.md)
- Spec backend chuẩn hoá: [01_BACKEND_STANDARDIZATION_BEFORE_UI.md](../../docs/spec/active/E21-realtime-control-plane/01_BACKEND_STANDARDIZATION_BEFORE_UI.md)
- AC: [acceptance.md](../../docs/spec/active/E21-realtime-control-plane/acceptance.md) (S21.9/15/16/17/18/19/20/21)
- Standards: [system-architecture.md](../../docs/system-architecture.md) · [code-standards.md](../../docs/code-standards.md) · [GLOSSARY.md](../../docs/GLOSSARY.md)
