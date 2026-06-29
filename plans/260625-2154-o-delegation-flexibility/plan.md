---
title: Delegation linh hoạt cho Agent-O — department alias + roster-growth qua E21
slug: o-delegation-flexibility
status: completed
mode: hard
tdd: true
created: 2026-06-25
decision: DEC-2 (docs/decisions.md)
brainstorm: plans/reports/delegation-flexibility-260625-2102-brainstorm-report.md
epics: [E10, E21]
phases: 5
depends_on: []
touchpoints:
  - supervisor/contracts.py
  - supervisor/state.py
  - supervisor/command_bridge.py   # NEW
  - supervisor/graph.py
  - supervisor/loop.py
  - supervisor/llm.py
  - roles/spec.py
  - roles/registry.py
unchanged_on_purpose:
  - delegation/*        # seam giữ nguyên, không unfreeze registry
  - delegation/bootstrap.py  # agent:general giữ nguyên
  - control/commands.py, control/command_registry.py  # tái dùng, không sửa
  - config/runtime_command_types.yaml  # AddAgentToLoop đã khai báo sẵn
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — Delegation linh hoạt cho Agent-O (E21-first)

## Mục tiêu

Cho **Agent-O** linh hoạt hơn khi delegate, theo [DEC-2](../../docs/decisions.md):
1. **Department alias** — O target một department (tên), loop expand thành các member role, **một `delegate()` mỗi member, tuần tự**, trước authority gate.
2. **Roster-growth** — O thêm agent/role (từ catalog) vào team đang chạy qua command `AddAgentToLoop`, apply tại **safe checkpoint = cuối round**.
3. **Department tự kéo member chưa-compose** — target department ngầm phát `AddAgentToLoop` cho member chưa có trong `selected_agents` (member gia nhập từ round kế).

Tất cả đi qua control plane E21 (`RuntimeCommand`), **O phát ý định trong `OrchestratorDecision.commands`, loop là chỗ DUY NHẤT dịch sang `RuntimeCommand` + chạm control plane**. O **không cần permission** (actor được tin; chấp nhận O fail trong rào cấu trúc).

## Bất biến phải giữ (standards: docs/code-standards.md)

- O là delegator duy nhất; **không recursive agent-picks-agent**; seam `delegation/*` + `agent:general` **không đổi** (không unfreeze registry).
- Scope mỗi member **chỉ narrow** ([delegation/policy.py:25-27](../../delegation/policy.py); [core/session.py:162-164](../../core/session.py)) — department expansion không mở rộng scope; mỗi member mang scope O cấp.
- Apply command **chỉ ở cuối round**, trong MỘT `ctx.save` **atomic** (gộp `round_no += 1` + roster + `applied_command_keys` + clear `pending_commands` vào một checkpoint), đặt TRƯỚC dòng tính `progressed` ([supervisor/loop.py:188-194](../../supervisor/loop.py)). KHÔNG hai save tách rời (tránh cửa sổ crash-giữa-hai-save → double-apply, red-team FM6). Không apply giữa lúc đang delegate.
- **Idempotent** theo `idempotency_key` ([control/commands.py:57](../../control/commands.py)); department expansion là pure function.
- **Catalog-bound** — chỉ thêm agent/department có trong catalog (tái dùng validator [supervisor/graph.py:93-97](../../supervisor/graph.py)).
- **Authority gate** ([supervisor/graph.py:142-147](../../supervisor/graph.py)) vẫn là nguồn chân lý SAU expansion + SAU apply command.
- `pending_commands` + `applied_command_keys` + roster mới **persist cùng `selected_agents`** trong checkpoint để resume nhất quán + không double-apply.
- `TaskLoopState` chỉ giữ primitive (serializable) — mọi field mới phải có trong `encode/decode_taskloop_state` ([supervisor/state.py:114-145](../../supervisor/state.py)).

## Mô hình department (chốt — surface ở approval)

Department target trong round N:
- Member **đã có** trong `selected_agents` → chạy ngay round N (1 `delegate()` mỗi member).
- Member **chưa có** → enqueue `AddAgentToLoop` (apply cuối round N) → gia nhập roster → O re-target ở round N+1 để chạy.

Lý do: tôn trọng guardrail "apply chỉ ở checkpoint" + "authority gate là nguồn chân lý". **Same-round admit bị loại** (phá hai guardrail trên). Hệ quả: member mới của department chạy trễ một round — chấp nhận được, đổi lấy tính nhất quán resume.

**Chi phí round (red-team FM1/FM2):** mỗi đợt admit "đốt" một round. Một department toàn-member-chưa-compose → round N admit (0 turn) + round N+1 chạy. Để round-admit KHÔNG bị BLOCKED oan, Phase 4 đảm bảo: (a) `applied>0` tính là progress; (b) `_decision_signature` bao gồm `commands`/`target_kind` (+ reset repeat khi `applied>0`) để no-repeat-guard không giết department-chờ-member; (c) emit `loop.roster_growth_starved` khi `pending_commands` còn mà sắp hết `max_rounds`. Department lớn cần `max_rounds` đủ — document, không tự nâng.

## Phases (TDD)

| # | Phase | File | Mục tiêu |
|---|---|---|---|
| 1 | Data contracts | [phase-01-data-contracts.md](phase-01-data-contracts.md) | `OrchestratorDecision.commands`, `AgentAssignment.target_kind`, `TaskLoopState.pending_commands`/`applied_command_keys` + encode/decode + parse. Inert, backward-compatible. |
| 2 | Command apply consumer | [phase-02-command-bridge.md](phase-02-command-bridge.md) | NEW `supervisor/command_bridge.py`: dịch O-cmd→`RuntimeCommand`, `apply_pending_commands` cho `AddAgentToLoop` (idempotent, catalog-bound, trust-O). Chưa wire. |
| 3 | Department expansion | [phase-03-department-expand.md](phase-03-department-expand.md) | `AgentRegistry.members_of`, expand department→members trong run_round path; member thiếu → enqueue `AddAgentToLoop`. Pure. |
| 4 | Wire + expose tới O | [phase-04-wire-and-expose.md](phase-04-wire-and-expose.md) | Nối vào `_drive` (enqueue + apply cuối round + progress-counts), `role_catalog`/`_state_view` lộ department + pending_commands, cập nhật prompt `DECIDE_SYSTEM`. |
| 5 | Adversarial + regression | [phase-05-adversarial-regression.md](phase-05-adversarial-regression.md) | `tests_audit` (resume double-apply, unknown role/dept, scope-no-widen) + suite supervisor cũ xanh + xác nhận seam/control/config không đổi. |

Thứ tự TDD: 1→2→3 thêm code có test nhưng CHƯA wire (suite luôn xanh); 4 wire thành live; 5 hardening.

## Acceptance criteria (tổng)

- **AC1** Given catalog có role `reviewer`, When O phát `commands:[{command_type:"AddAgentToLoop", payload:{agent_id:"reviewer"}}]`, Then cuối round `reviewer ∈ selected_agents` và round kế target `reviewer` qua được authority gate. Role ngoài catalog → KHÔNG thêm + emit `command.rejected`.
- **AC2** Given cùng `idempotency_key` apply hai lần (kể cả qua resume), Then roster lớn lên đúng MỘT lần.
- **AC3** Given assignment `{target_kind:"department", agent_id:"engineering"}`, Then expand thành member của department `engineering`; member đã-selected chạy round này; member thiếu → `AddAgentToLoop` queued (chạy round kế); scope mỗi member == `allowed_capabilities` O cấp, không widen.
- **AC4** Given crash giữa round rồi resume, Then `pending_commands`/`applied_command_keys` khôi phục từ checkpoint, KHÔNG double-apply.
- **AC5** Given O-issued `AddAgentToLoop`, Then bỏ qua `workflow.modify_agents`; round chỉ grow roster (không delegate) vẫn tính là progress (loop không bị BLOCKED oan).
- **AC6** Suite `tests/test_supervisor_*` + `tests_audit/test_supervisor_*` xanh; `delegation/*`, `control/{commands,command_registry}.py`, `config/runtime_command_types.yaml` **không đổi**.

## Out of scope (round này)

- Parallel/concurrent delegation; recursive agent-picks-agent.
- `RemoveAgentFromLoop` + 13 command type còn lại; human-issued command + permission enforcement đầy đủ.
- **Re-add một role** (thêm lại role đã add) — `idempotency_key=command_type:agent_id` cố ý khóa add-một-lần/đời-loop; re-add đi cùng `RemoveAgentFromLoop` ở vòng sau.
- Same-round department admit; per-member objective/scope khác nhau trong department (v1: dùng chung của assignment).
- E21 S-TRANSPORT (`POST /api/commands`) + S-UI (Control Tower) — đây chỉ là runtime consumer.

## Rollback

Mỗi phase revert độc lập. Phase 1-3 thêm code **inert** (field default rỗng + module chưa wire) → revert = bỏ wiring ở Phase 4. Không migration dữ liệu (field mới default rỗng, checkpoint cũ decode an toàn nhờ `.get(..., default)`).

## Câu hỏi còn mở (đã giải / theo dõi)

- ✅ #1 O phát command kiểu nào → field `commands` trong decision, loop dịch.
- ✅ #2 Permission O → bỏ qua (trust O).
- ✅ #3 Resume double-apply → `applied_command_keys` persist + check trước apply (Phase 2/4).
- ✅ #4 Nguồn department → group theo `RoleSpec.department` ([roles/spec.py:45](../../roles/spec.py)) đã có disk (DRY); KHÔNG cần YAML alias riêng round này.
- ❓ Theo dõi: nếu sau này cần department con/biến thể (không trùng `department` string) → cân nhắc YAML alias→roles (ngoài scope).

## Verification

Offline: `python -m pytest tests/test_supervisor_*.py tests_audit/test_supervisor_*.py -q` xanh 100%; `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`. Lưu ý env: cần `pip install -e ".[dev,audit]"` (langgraph + hypothesis).
