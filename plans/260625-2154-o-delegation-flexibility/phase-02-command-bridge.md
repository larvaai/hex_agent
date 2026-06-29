---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 02 — Command apply consumer (NEW supervisor/command_bridge.py)

Context: [plan.md](plan.md) · Touchpoints: `supervisor/command_bridge.py` (NEW). Tái dùng `control/commands.py`, `control/command_registry.py` (KHÔNG sửa).
> Đã siết theo red-team round 2: dedup CHỈ theo `idempotency_key` (không dict-equality vì `as_dict()` mang `command_id`/`created_at` ngẫu nhiên).

## Mục tiêu
Module thuần cầu nối supervisor ↔ control plane: dịch ý định command của O thành `RuntimeCommand`, và `apply_pending_commands(state, ctx)` áp `AddAgentToLoop` — idempotent, catalog-bound, trust-O. **Chưa wire vào loop** (Phase 4).

## Requirements (SRP: chỉ cầu nối command, không chạm delegation)
1. `to_runtime_command(raw: dict, *, session_id: str) -> RuntimeCommand` — dịch một command dict của O thành `RuntimeCommand` với `issued_by=IssuedBy(type="agent", agent_id="orchestrator")`. `idempotency_key`: nếu `raw` có thì dùng; else suy ỔN ĐỊNH từ payload (vd `f"{command_type}:{payload['agent_id']}"` cho AddAgentToLoop) — KHÔNG dùng `command_id`/`created_at` (chúng ngẫu nhiên, [commands.py:59-60](../../control/commands.py)). Validate qua `parse_command` ([commands.py:100](../../control/commands.py)); lỗi → ControlContractError (caller bắt → emit `command.rejected`).
2. `enqueue_commands(state, decision)` — đẩy `decision.commands` (đã dịch sang `RuntimeCommand.as_dict()`) vào `state.pending_commands`. **Dedup CHỈ theo `idempotency_key`** (red-team FM3): bỏ qua nếu key đã có trong `pending_commands` HOẶC `applied_command_keys`. KHÔNG so sánh dict-equality (hai as_dict cùng key vẫn khác vì `command_id`/`created_at`).
3. `apply_pending_commands(state, ctx, *, registry, catalog: set[str]) -> int` — duyệt `state.pending_commands`; mỗi command:
   - `idempotency_key` ∈ `applied_command_keys` → bỏ (idempotent).
   - `registry.assert_known(command_type)`; `apply_at != "next_checkpoint"` → skip + emit `command.skipped`.
   - **Trust-O**: `issued_by.type != "agent"` → skip + emit `command.rejected` (human path + permission enforcement OUT OF SCOPE). `type=="agent"` → bỏ qua `requires_permission`.
   - `AddAgentToLoop`: `agent_id = payload["agent_id"]`. Không ∈ `catalog` → emit `command.rejected`, KHÔNG thêm. ∈ catalog và chưa ∈ `selected_agents` → append + emit `loop.agent_added`. Mark key vào `applied_command_keys`. (Đã ∈ selected → mark key applied, không append lại.)
   - command_type khác (vd `RemoveAgentFromLoop`) → skip + emit `command.skipped` (chỉ `AddAgentToLoop` v1).
   - Trả số command APPLY (Phase 4 dùng tính progress); clear command đã xử lý khỏi `pending_commands`.
4. Không đụng `delegation/*`, không tạo session — chỉ mutate `selected_agents` + `applied_command_keys` + `pending_commands`.

## idempotency_key — semantics (chốt, red-team FM3)
- Key `command_type:agent_id` đảm bảo "**add một role MỘT lần trong vòng đời loop**". KHÔNG hỗ trợ re-add (out of scope cùng `RemoveAgentFromLoop`).
- O phát lại cùng ý định nhiều round → dedup, không emit lại — đúng mong muốn (không spam roster).
- `applied_command_keys` tăng đơn điệu theo số role distinct được add (bounded bởi kích thước catalog, không phải số round) — chấp nhận.

## Files
- ADD `supervisor/command_bridge.py` (docstring dòng đầu: `"""... Epic E21 (S21.13)."""`)
- ADD `tests/test_supervisor_command_bridge.py`

## TDD

### Tests Before
- `to_runtime_command` AddAgentToLoop → `issued_by.type=="agent"`, `idempotency_key` ổn định khi lặp cùng payload (KHÔNG phụ thuộc command_id/created_at).
- `apply_pending_commands` thêm `reviewer` khi ∈ catalog; key vào `applied_command_keys`.
- **Idempotent**: gọi hai lần cùng command → roster lớn 1 lần.
- **Dedup-by-key** (red-team): hai `as_dict()` CÙNG `idempotency_key` nhưng KHÁC `command_id` → `enqueue_commands` chỉ giữ một.
- Role ∉ catalog → KHÔNG thêm, có `command.rejected`.
- `issued_by.type=="human"` → skip, roster không đổi.
- command_type lạ → skip, roster không đổi.
- Trả đúng số applied.

### Implement
Module thuần với `ctx.emit` injectable (FakeCtx có `.emit(topic, payload)`). Catalog truyền vào (Phase 4 lấy từ `ctx.role_catalog()`).

### Tests After / Regression
`pytest tests/test_supervisor_command_bridge.py tests/test_supervisor_*.py -q` xanh (chưa wire → không ảnh hưởng loop).

## Risks + rollback
- Risk: dedup nhầm bằng dict-equality → double-enqueue. → Test dedup-by-key. Rollback: xóa module (chưa ai import).
- Risk: `applied_command_keys` unbounded — thực tế bounded bởi catalog distinct roles; ghi nhận, không cap v1.
