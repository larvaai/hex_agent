---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 01 — Data contracts (inert, backward-compatible)

Context: [plan.md](plan.md) · Touchpoints: `supervisor/contracts.py`, `supervisor/state.py`

## Mục tiêu
Thêm các field dữ liệu thuần để O phát command + để Blackboard mang hàng đợi command, **không đổi hành vi loop** (default rỗng → checkpoint cũ decode an toàn).

## Requirements
1. `OrchestratorDecision` ([supervisor/contracts.py:47-55](../../supervisor/contracts.py)) thêm `commands: tuple[dict[str, Any], ...] = ()`.
2. `AgentAssignment` ([supervisor/contracts.py:39-44](../../supervisor/contracts.py)) thêm `target_kind: str = "agent"` (giá trị `"agent"|"department"`; default giữ backward-compat).
3. `parse_decision` ([:107-153](../../supervisor/contracts.py)) parse `commands` (mỗi phần tử phải là dict có `command_type` non-empty; loại không hợp lệ → `JsonGateError` stage="schema") + parse `target_kind` mỗi call (validate ∈ {"agent","department"}, default "agent").
4. `TaskLoopState` ([supervisor/state.py:80-93](../../supervisor/state.py)) thêm `pending_commands: list[dict[str, Any]] = field(default_factory=list)` + `applied_command_keys: list[str] = field(default_factory=list)`.
5. `encode_taskloop_state`/`decode_taskloop_state` ([:114-145](../../supervisor/state.py)) serialize/deserialize hai field mới (decode dùng `.get(..., [])` để checkpoint cũ không vỡ).

## Files
- EDIT `supervisor/contracts.py`
- EDIT `supervisor/state.py`
- ADD test `tests/test_supervisor_contracts_commands.py` (hoặc nối vào file test contracts hiện có nếu có)

## TDD

### Tests Before (đỏ trước)
- `parse_decision` với `commands:[{"command_type":"AddAgentToLoop","payload":{"agent_id":"reviewer"}}]` → `decision.commands` có đúng 1 dict.
- `parse_decision` với `commands:[{"payload":{}}]` (thiếu `command_type`) → raise `JsonGateError`.
- `parse_decision` call có `target_kind:"department"` → `AgentAssignment.target_kind=="department"`; thiếu → default `"agent"`; giá trị lạ → `JsonGateError`.
- `encode→decode` round-trip giữ nguyên `pending_commands` + `applied_command_keys`.
- `decode_taskloop_state` trên dict CŨ (không có hai key) → trả state với hai list rỗng (không KeyError).
- Backward-compat: `parse_decision` với decision cũ (không `commands`) → `commands == ()`.

### Implement
Thêm field + nhánh parse tối thiểu; giữ frozen dataclass; `commands` chỉ validate hình thức (dict + `command_type`), KHÔNG resolve/apply ở phase này.

### Tests After (xanh)
Chạy `pytest tests/test_supervisor_contracts_commands.py tests/test_supervisor_*.py -q`.

### Regression Gate
`pytest tests/test_supervisor_*.py tests_audit/test_supervisor_*.py -q` xanh — field mới default rỗng nên không phá test cũ.

## Risks + rollback
- Risk: thêm field positional phá constructor cũ ở test. → Mitigate: field mới đặt CUỐI + có default. Rollback: xóa field (không dữ liệu nào phụ thuộc).
