---
title: "S21.33 — Evidence types + AC report (siết acceptance gate, no command)"
slug: s2133-ac-evidence-types
status: draft
mode: hard
tdd: true
created: 2026-06-26 02:37
owner: namson.nguyen102@gmail.com
decision: DEC-pending (evidence_type DERIVED từ artifact.kind; NON_EVIDENCE_KINDS)
brainstorm: plans/reports/brainstorm-260626-0226-control-tower-ui-delta-report.md
epics: [E10, E21]
phases: 3
depends_on: []          # KHÔNG phụ thuộc command_bridge / o-delegation (đó là lý do chọn H2)
risk: low — supervisor-only, backward-compatible, không đụng contract/transport
standards:
  # path cũ (docs/system-architecture.md, code-standards.md, GLOSSARY.md) ĐÃ bị đợt
  # Diátaxis dời/xoá — KHÔNG còn trên HEAD/main. Neo vào artifact hiện hành:
  - docs/explanation/design-decisions.md   # design-decision doc
  - docs/decisions.md                      # DEC register (DEC số hoá gom ở đây)
  - docs/reference/runtime-flow.md         # luồng runtime đã verify
  - docs/HOW_TO_FOLLOW.md                  # docstring dòng đầu "Epic Exx" → MAP.md
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — Đóng S21.33: evidence **type** + **AC report** (siết acceptance gate)

> hs:cook đọc file này làm hợp đồng. Mọi claim không hiển nhiên có anchor `file:line`/`AC-id`.
> Tag `[UNVERIFIED]` nếu thiếu anchor.

## Vì sao plan này (giải thích cho người mới)

S21.33 đòi: AC `passed` phải có **≥1 evidence thuộc đúng loại** `{artifact, tool_result,
reviewer_report, diff, test_result}` resolve được trên Blackboard; và khi session `finished`
phải sinh một **artifact "AC report"** (trạng thái AC + evidence + session_id).

Hiện trạng (đã verify đọc code, **không** qua agent):
- O **đã** attach được evidence: nó báo `acceptance_status:[{id,status,evidence_ids}]` trong
  decision; `judge_acceptance` set `passed` chỉ khi evidence tồn tại trên board
  ([supervisor/graph.py:229-246](../../supervisor/graph.py)). → đường evidence chạy rồi.
- **Lỗ hổng**: gate chỉ check *tồn tại* (`all(e in state.artifacts ...)`,
  [graph.py:238](../../supervisor/graph.py)), **không** check *loại*. O có thể "pass" một AC
  bằng cách trỏ vào `context_packet`/`session_plan` (scaffolding, không phải evidence thật).
- `AcceptanceCheck` **không có `evidence_type`** ([state.py:29-33](../../supervisor/state.py)).
- **AC report**: không code nào sinh.

Vì sao **không** thêm command `AttachEvidenceToAC`/`RequestReviewer` (feature greenlit ban đầu):
foundation pending-command (`OrchestratorDecision.commands`, `TaskLoopState.pending_commands`,
`supervisor/command_bridge.py`, `apply_pending_commands`) **không tồn tại trên branch này** —
nó là plan `260625-2154-o-delegation-flexibility` (in_progress, branch khác). Command path
phục vụ **human/UI** mà UI/transport cũng chưa có. → H2: đóng gap S21.33 *thật*, build ngay, 0
phụ thuộc. (Quyết định người dùng chốt phiên brainstorm/plan.)

## Expected output (artifact người dùng thấy)

1. `supervisor/evidence.py` **MỚI** — `EVIDENCE_TYPES`, `NON_EVIDENCE_KINDS`,
   `evidence_type_of(artifact)->str|None`, `record_ac_report(state)->str`.
2. `judge_acceptance` siết: evidence chỉ hợp lệ nếu artifact nó trỏ tới có `kind` là loại
   evidence (loại scaffolding `session_plan`/`context_packet`/`ac_report`).
3. Khi loop FINISHED: một artifact `kind="ac_report"` xuất hiện trên Blackboard + trong
   `result["state"]["artifacts"]`, mang `{session_id, task_id, checks:[{id,text,status,
   evidence_ids, evidence_types}]}`.

## Acceptance criteria (đầu vào → đầu ra = "done")

- **AC1** Given O báo `ac1 passed` với `evidence_ids=[<chỉ id scaffolding context_packet/session_plan>]`,
  When judge_acceptance, Then AC `pending` (không evidence hợp lệ nào) — bảo vệ MỚI.
- **AC2** Given evidence có ≥1 id loại hợp lệ (`tool_result`/`delegation_result`/typed
  `diff`/`test_result`/`reviewer_report`) — **kể cả khi kèm thêm 1 id scaffolding** (spec S21.33
  ≥1), When judge, Then `passed`. (Giữ xanh `test_finish_allowed_with_real_evidence` dùng
  `tool_result-0001`, [test_acceptance_gate.py:48-65](../../tests/test_acceptance_gate.py).)
- **AC3** Given run FINISHED, Then đúng **một** artifact `kind=ac_report` tồn tại, `checks`
  liệt kê mọi AC + `evidence_types` suy từ `evidence_type_of`.
- **AC4** Given finish-denied (chưa `all_accepted`), Then **không** có `ac_report`.
- **AC5** Given O trỏ evidence = id của một `ac_report`, When judge, Then bị từ chối
  (`ac_report ∈ NON_EVIDENCE_KINDS`) — chặn self-evidence vòng.
- **AC6** Given finish rồi resume từ checkpoint, Then `ac_report` còn nguyên (persist qua
  `encode/decode_taskloop_state`), KHÔNG sinh trùng.
- **AC7** `python -m pytest tests/test_supervisor_*.py tests/test_acceptance_gate.py
  tests_audit/ -q` xanh; `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`;
  `control/*` + `config/runtime_event_types.yaml` + `config/runtime_command_types.yaml`
  **không đổi**.

## Scope boundary — OUT (đợt này)

- Command `AttachEvidenceToAC`/`RequestReviewer` (cần command_bridge foundation — branch khác).
- Lưu `evidence_type` lên `AcceptanceCheck` (suy từ `artifact.kind`, KHÔNG đổi schema →
  không migration checkpoint).
- **Producer** cho `reviewer_report`/`diff`/`test_result` (chấp nhận làm evidence nếu agent
  phát artifact đúng kind; KHÔNG build producer).
- `event_type` mới cho ac_report (artifact-only; emit để sau → `runtime_event_types.yaml`
  không đổi).
- Human-command path / E21 S-TRANSPORT / Control Tower UI.

## Non-negotiable constraints

| Constraint | Nguồn |
|---|---|
| `supervisor/`, `tests/`, `config/` ngoài fence fs_guard | [ownership.yaml](../../harness/data/ownership.yaml) (zones: docs/state/standards/plans) |
| `TaskLoopState` chỉ giữ primitive serializable; field/artifact mới phải qua encode/decode | [state.py:114-145](../../supervisor/state.py) |
| Backward-compatible: AcceptanceCheck **không đổi** → checkpoint cũ decode an toàn | [state.py:42-49](../../supervisor/state.py) |
| TDD red→green, không weaken assertion | [harness/rules/tdd-discipline.md](../../harness/rules/tdd-discipline.md) |
| Docstring dòng đầu `"""<mục đích>. Epic E10/E21 (S21.33)."""` → MAP.md | [docs/HOW_TO_FOLLOW.md](../../docs/HOW_TO_FOLLOW.md) |
| CHANGELOG +1 dòng (path+line) | [CHANGELOG.md](../../CHANGELOG.md) |
| Python snake_case; module mới SRP (chỉ evidence) | code-standards (de-facto) |
| Ngôn ngữ vi; evidence (file:line) giữ nguyên | [output.yaml](../../harness/data/output.yaml) |

## Touchpoints (file thật)

**Tạo mới:**
- `supervisor/evidence.py` — SRP: phân loại evidence + dựng AC report. KHÔNG chạm delegation/command.
- `tests/test_evidence.py` — unit cho `evidence_type_of` + `record_ac_report`.
- `tests_audit/test_acceptance_evidence_adversarial.py` — circular/resume/property.

**Sửa:**
- `supervisor/graph.py:229-246` (`judge_acceptance`) — siết điều kiện dòng 238 + import `evidence_type_of`.
- `supervisor/loop.py:170-176` (nhánh `finished`) — gọi `record_ac_report(state)` trước `_terminate`.
- `tests/test_acceptance_gate.py:48-65` — thêm case scaffolding-rejected.
- `CHANGELOG.md`, `docs/decisions.md` (DEC).

**Đọc làm nguồn (KHÔNG sửa):**
- `supervisor/state.py:29-49` AcceptanceCheck + `:90` artifacts + `:109-111` acceptance_snapshot + `:114-145` encode/decode.
- `supervisor/graph.py:181-184` worker artifact `kind`; `:222` tool_result `kind`; `:100` session_plan `kind`; `:165` context_packet `kind` (revalidator-pinned).
- `supervisor/loop.py:202-206` `_terminate` (save tại đây → ac_report được persist).
- `tests/conftest.py:90-99` `compose_json`/`decision_json`/`make_env`.

## Mô hình evidence (chốt — surface ở approval, ghi DEC)

`evidence_type_of(artifact)` suy **loại từ `kind`** (không lưu trùng trên AC):

| artifact.kind | → evidence_type | Lý do |
|---|---|---|
| `tool_result` | `tool_result` | kết quả tool thật ([graph.py:222](../../supervisor/graph.py)) |
| `delegation_result` | `artifact` | output worker thật ([graph.py:186-196](../../supervisor/graph.py)) |
| `diff`/`test_result`/`reviewer_report` (agent tự phát) | chính nó | agent phát artifact typed ([graph.py:181-184](../../supervisor/graph.py)) |
| kind khác (do worker đặt) | `artifact` | **trust-worker**: sản phẩm coi là evidence chung |
| **kind rỗng / thiếu** | **None** | artifact không loại = không phải evidence (phòng thủ — red-team FM-MED) |
| `session_plan`/`context_packet`/`ac_report` | **None** (NON_EVIDENCE_KINDS) | scaffolding/meta — KHÔNG phải evidence |

`None` ⇒ evidence_id đó không tính là evidence hợp lệ. **Định lượng để AC `passed` = spec S21.33
"≥1 evidence hợp lệ"** ([acceptance.md:122-123](../../docs/spec/active/E21-realtime-control-plane/acceptance.md)):
mọi id phải **TỒN TẠI** trên board **và** ≥1 id có `evidence_type ≠ None`. KHÔNG đòi *mọi* id hợp lệ
— sẽ chặn oan finish khi O kèm 1 scaffolding id (red-team FM-HIGH). **DEC cần chốt:**
`NON_EVIDENCE_KINDS` + kind-rỗng→None + "kind-lạ-worker→artifact" (trust-worker) + quantifier ≥1 —
ghi `docs/decisions.md` khi approve.

## Phases (TDD)

| # | Phase | File | Phụ thuộc | Gate |
|---|---|---|---|---|
| 1 | Evidence-type contract + siết gate | [phase-01-evidence-type-gate.md](phase-01-evidence-type-gate.md) | — | pytest |
| 2 | AC report artifact khi finish | [phase-02-ac-report.md](phase-02-ac-report.md) | 1 | pytest |
| 3 | Adversarial + regression + DEC/CHANGELOG | [phase-03-adversarial-regression.md](phase-03-adversarial-regression.md) | 1,2 | pytest + smoke |

Thứ tự: P1 dựng + dùng `evidence.py` (siết gate, suite xanh) → P2 thêm report (cùng module) →
P3 hardening + chốt sổ. P1→P2 tuần tự (P2 import P1); P3 sau cùng.

## Rollback

Mỗi phase một commit `feat(E21): ... S21.33`. Revert = `git revert <range>`. Không migration
(AcceptanceCheck không đổi; ac_report là artifact mới, checkpoint cũ decode an toàn — `.get`).
`supervisor/evidence.py` mới → xoá file + bỏ 2 dòng wire (graph/loop) là sạch.

## Red-team (sẽ chạy gate riêng — đây là seed)

| Failure mode | Mitigation |
|---|---|
| Siết gate phá test cũ | AC2 ghim `tool_result` vẫn pass; đọc trước [test_acceptance_gate.py](../../tests/test_acceptance_gate.py) — không test nào dựa scaffolding-as-evidence |
| `ac_report` tự trỏ chính nó làm evidence | AC5: `ac_report ∈ NON_EVIDENCE_KINDS` |
| Resume sinh report trùng | AC6: report chỉ sinh ở nhánh FINISHED một lần; resume từ terminal trả `_result` ngay ([loop.py:142-143](../../supervisor/loop.py)) |
| "kind khác → artifact" quá lỏng (pass evidence rác) | DEC ghi rõ trade-off; chỉ loại 3 scaffolding kinds — đủ đóng lỗ thật, không over-engineer |
| Đổi `runtime_event_types.yaml` ngoài ý | AC7: config không đổi (ac_report artifact-only, no emit) |

## Verification

Offline: `python -m pytest tests/test_supervisor_*.py tests/test_acceptance_gate.py
tests/test_evidence.py tests_audit/ -q` xanh 100%; `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`.
Env: `pip install -e ".[dev,audit]"`.

## Câu hỏi còn mở

1. `NON_EVIDENCE_KINDS` đúng tập chưa? (`session_plan`/`context_packet`/`ac_report`) — có cần
   loại thêm `delegation_result` khi `outcome=error`? (đề xuất: vẫn tính artifact; O chịu trách
   nhiệm chọn evidence đúng). → chốt ở validate.
2. AC report có cần `event_type` riêng để Control Tower nghe không? Đợt này artifact-only
   (YAGNI tới khi UI/transport có). Theo dõi.
3. Path-drift standards (system-architecture/code-standards/GLOSSARY mất) — follow-up ngoài
   plan này: hồi phục hay trỏ chính thức sang docs/explanation + docs/reference.
