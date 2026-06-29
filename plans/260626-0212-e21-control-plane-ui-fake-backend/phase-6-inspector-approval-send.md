---
phase: 6
title: "Agent Inspector + Approval modal + Prompt/Send (control path)"
status: pending
plan: 260626-0212-e21-control-plane-ui-fake-backend
created: 2026-06-26
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 6 — Inspector + Approval modal + Prompt/Send

## Overview

3 mảnh **control path** (write) — biến nút bấm thành `RuntimeCommand`. Phụ thuộc
**Phase 3** (commands endpoint) + **Phase 4** (adapter `postCommand`). Không phụ thuộc
Phase 5 (file riêng; chia sẻ `state/store.ts` đọc-only ngoài select).

- **Agent Inspector** (S21.20): role/context_packet(redacted)/allowed_tools/last_output/
  permission — hàm thuần của `AgentView` (Phase 1). Không secret.
- **Approval modal** (S21.21): checkpoint `waiting` → modal risk+diff; Approve→
  `ApproveCheckpoint`, Reject→`RejectCheckpoint`; **không** optimistic mutate.
- **Prompt box & Send** (S21.15): submit → `POST /api/commands`; hiện ACK + lifecycle.

Bất biến xuyên suốt: **UI không sửa state trực tiếp** — mọi hành động phát command, chờ
runtime event rồi mới đổi hiển thị (S21.21/S21.50).

## Files

**Create (dưới `ui/control-plane/src/`):**
- `components/AgentInspector.tsx` — panel đọc `AgentView` của agent đang chọn; ẩn secret.
- `components/ApprovalModal.tsx` — đọc `snapshot.checkpoints` (waiting); Approve/Reject → `adapter.postCommand`.
- `components/PromptBox.tsx` — textarea + Send → command (new-run / wait-command); hiện `CommandAck` + trạng thái `received/accepted/rejected/applied` (từ stream).
- `lib/commands.ts` — helper dựng `RuntimeCommand` (command_type + idempotency_key=uuid + issued_by) đúng shape [commands.py:52-84](../../../control/commands.py).
- `components/__tests__/{AgentInspector,ApprovalModal,PromptBox}.test.tsx`.

**Modify:**
- `src/App.tsx` (gắn inspector + modal + prompt box).
- `config/runtime_command_types.yaml` — thêm `SubmitPrompt` (F5/D8). Test Python: `tests/test_control_contracts.py` assert `load_command_registry()` chứa `SubmitPrompt`.

### Command shape (lib/commands.ts)
`RuntimeCommand{command_type, session_id, issued_by:{type:'human',user_id}, idempotency_key:uuid(),
payload}`. command_type hợp lệ từ [runtime_command_types.yaml](../../../config/runtime_command_types.yaml):
`ApproveCheckpoint`/`RejectCheckpoint` (immediate_if_waiting); **Send = `SubmitPrompt`**
(apply_at: next_checkpoint — F5/D8, thêm vào registry trong phase này, payload `{prompt}`).
`idempotency_key` mới mỗi click → double-click an toàn ở server (S21.10).
> **F5/D8:** `SubmitPrompt` CHƯA có trong registry → phase này **Modify**
> `config/runtime_command_types.yaml` thêm dòng `SubmitPrompt: { apply_at: next_checkpoint,
> requires_permission: null }`. Fake (Phase 3) đã `assert_known()` → nếu quên khai = 400.

## TDD

### Tests Before (RED — vitest + @testing-library/react)
- [ ] `inspector_hides_secret` (S21.20): `AgentView` có context_packet đã redact → render `[REDACTED]`, không secret; hiện role/allowed_tools/last_output/permission. **Khoá:** R3.
- [ ] `approve_sends_command_not_mutate` (S21.21): bấm Approve → `postCommand(ApproveCheckpoint)` gọi đúng; state checkpoint **không** đổi UI-side trước khi runtime phát `approval.approved`. **Khoá:** bất biến không-optimistic.
- [ ] `reject_blocks_action` (S21.21): Reject → `RejectCheckpoint`; modal cập nhật sau quyết định. **Khoá:** S21.21.
- [ ] `send_posts_command_and_shows_ack` (S21.15): Send → `postCommand` + hiển thị `CommandAck.command_id` + status. **Khoá:** write path.
- [ ] Run → FAIL (chưa có component).

### Implement
1. `lib/commands.ts`: builder + uuid idempotency_key.
2. `AgentInspector.tsx`: đọc selected `AgentView`; render fields; guard secret.
3. `ApprovalModal.tsx`: `snapshot.checkpoints.filter(waiting)`; Approve/Reject → adapter; cập nhật theo stream event, không optimistic.
4. `PromptBox.tsx`: Send → adapter.postCommand; theo dõi lifecycle qua `command.*` event trên stream.
5. Min code 4 test xanh.

### Tests After (xanh)
- [ ] 4 test trên xanh. `npm run build` (tsc) sạch.

### Regression Gate
`npm --prefix ui/control-plane run test && npm --prefix ui/control-plane run build` → PASS.

## Success
- [ ] Inspector hiện đủ field S21.20, không secret.
- [ ] Approve/Reject phát đúng command, **không** mutate state UI-side trước event.
- [ ] Send phát command + hiển thị ACK + lifecycle `received→…`.
- [ ] Mọi write đi qua `adapter.postCommand` (một cửa) — không component tự fetch.

## Risks
- **Optimistic mutate lén** (cao nếu lọt): vi phạm bất biến "UI không sửa state". Mitigation: test `approve_sends_command_not_mutate` assert không đổi state trước event; contract-seam test (Phase 7) chốt lại.
- **idempotency_key tái dùng** (tb): double-click cùng key → server áp 1 lần nhưng UX có thể nhầm. Mitigation: key mới mỗi lần dựng command; server dedup là lưới an toàn.
