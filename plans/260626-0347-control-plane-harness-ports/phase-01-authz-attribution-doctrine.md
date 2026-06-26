---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 01 — Authz ≠ attribution: doctrine + contract predicate

**Epic:** E21 · **Rủi ro:** thấp · **TDD:** bắt buộc

## Overview

Port "ba sự thật" của harness (`harness/rules/harness-contract.md:21-34`) vào control plane,
**đảo kết luận**: harness chấp nhận actor spoofable vì là tool hợp tác; hex_agent xây authz
**thật** (`control/permission.py:26` `can_modify_permissions` = bề mặt leo thang). Deliverable
là **doctrine + một predicate thuần** ở contract layer — KHÔNG build đường enforcement
(`command_bridge` vắng, DEC-7).

## Requirements

1. Doctrine doc `docs/explanation/authz-vs-attribution.md` nêu:
   - (a) `issued_by` (`control/commands.py:29`) + `Actor` (`control/events.py:32`) = **attribution**, do người phát tự khai; sửa docstring `commands.py:6` "for authz + audit" → "for **audit/attribution**; authz quyết bởi `requires_permission` + checkpoint".
   - (b) Authz decision = `requires_permission` (`control/command_registry.py:56`) resolve trên `Permission` của holder **tại checkpoint boundary**, không phải claim của issuer.
   - (c) `trust-O` (GLOSSARY) bỏ qua `requires_permission` — **nhưng** permission-edit (`UpdateAgentPermission` → `can_modify_permissions`) phải cần human `RuntimeCheckpoint`, không self-grantable kể cả dưới trust-O.
   - (d) **Đặt tên call-site enforcement bị hoãn**: "khi `command_bridge` ra đời, nó MUST gọi `control.authz` trước khi áp `UpdateAgentPermission`." (tránh predicate thành speculative API).
2. Module mới `control/authz.py` — predicate thuần, không phụ thuộc bridge:
   - `is_permission_escalating(current: Permission, patch: dict) -> bool`: True nếu patch bật bất kỳ cờ `can_*` từ False→True (đặc biệt `can_modify_permissions`/`can_execute_shell`).
   - `command_needs_human_checkpoint(command_type: str, registry: CommandTypeRegistry) -> bool`: True cho command có `requires_permission` thuộc nhóm permission-edit (`workflow.modify_permissions`).
   - Docstring dòng đầu: `"""Authz predicates — attribution≠authz boundary for the control plane. Epic E21."""`
3. Comment ngắn ở `control/permission.py` (đầu class) + `control/commands.py` (`IssuedBy`) trỏ tới doc.

## Related code files

| File | Vai trò | Anchor |
|---|---|---|
| `control/commands.py` | `IssuedBy`, docstring "authz" cần sửa | `:6`, `:29` |
| `control/permission.py` | `can_modify_permissions`, `patched()` | `:26`, `:38` |
| `control/command_registry.py` | `requires_permission` getter | `:56` |
| `config/runtime_command_types.yaml` | `UpdateAgentPermission` → `workflow.modify_permissions` | `:27` |
| `control/checkpoint.py` | surface human approval đã có | `:1-8`, `:57` |
| `docs/GLOSSARY.md` | `trust-O`, `authority gate` | `:14-15` |

## Implementation steps (TDD)

**Tests Before** — `tests/test_authz_attribution.py` (đỏ trước):
1. `is_permission_escalating(Permission(), {"can_modify_permissions": True})` → True.
2. `is_permission_escalating(Permission(can_execute_shell=True), {"can_execute_shell": False})` → False (hạ quyền không phải leo).
3. `command_needs_human_checkpoint("UpdateAgentPermission", registry)` → True.
4. `command_needs_human_checkpoint("PauseWorkflow", registry)` → False (`requires_permission: null`).
5. Contract: registry load từ `config/runtime_command_types.yaml`, `UpdateAgentPermission.requires_permission == "workflow.modify_permissions"`.

**Implement**: viết `control/authz.py` đủ để xanh; sửa 2 docstring/comment.

**Tests After**: `python -m pytest tests/test_authz_attribution.py -q` xanh; full suite không đỏ.

**Regression gate**: `python -m pytest tests/test_control_contracts.py tests_audit/test_contract_roundtrips.py -q` (đụng control/ contracts).

## Success criteria

- [ ] `docs/explanation/authz-vs-attribution.md` nêu đủ (a)-(d), đặt tên call-site hoãn.
- [ ] `control/authz.py` 2 predicate + docstring "Epic E21" → vào MAP.
- [ ] `tests/test_authz_attribution.py` xanh; 5 case trên.
- [ ] Docstring `commands.py:6` sửa "authz" → "audit/attribution".
- [ ] `python tools/gen_map.py` đã chạy lại; `CHANGELOG.md` thêm dòng `feat(E21): authz≠attribution doctrine + predicate`.

## Known gap (ghi trong doc)

Predicate chỉ bắt cờ boolean `can_*`. Leo quyền qua **mở rộng `allowed_tools`** không nằm trong
scope predicate — nhưng đã được chặn bởi §1.4 (`SessionFactory.create_child` ép scope con ⊆ cha,
`docs/code-standards.md:69`). Doc phải nêu rõ ranh giới này để không tạo ảo giác "authz đầy đủ".

## Risk

`control/authz.py` thành dead code đến khi `command_bridge` ra đời — giảm thiểu: test pin invariant + doc đặt tên call-site (không phải speculative). Không đụng runtime path nào đang chạy → rollback = xoá file + test.
