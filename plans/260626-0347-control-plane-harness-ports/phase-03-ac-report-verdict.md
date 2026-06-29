---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 03 — Overall verdict trên ac_report (additive)

**Epic:** E10/E21 · **Rủi ro:** thấp (additive, không đụng logic gate) · **TDD:** bắt buộc

## Overview

Port "presence-gate + enum verdict, policy trong CODE" của harness
(`harness/hooks/gate_stage.py:149-154`). S21.33 **đã** làm gate (8 test xanh) — phase này
**chỉ thêm** một field `verdict` tổng lên `ac_report` cho read-model, **không** đổi quyết định
FINISHED (`supervisor/state.py:102` `all_accepted`). Tier `passed_with_risk` ánh xạ harness
`PASS_WITH_RISK` vào tín hiệu **thật** của hex_agent: AC passed nhưng chỉ dựa evidence `artifact`
generic (không có loại mạnh).

## Requirements

1. `supervisor/evidence.py` `record_ac_report` (`:39-66`): thêm `payload["verdict"]`:
   - `pending` — nếu bất kỳ AC nào `status != "passed"`.
   - `passed_with_risk` — mọi AC passed, **nhưng** ≥1 AC mà tất cả evidence_types resolve được chỉ là `"artifact"` generic (không có `{tool_result, test_result, diff, reviewer_report}` mạnh).
   - `passed` — mọi AC passed và mỗi AC có ≥1 evidence type **mạnh**.
2. Policy nằm trong `evidence.py` (code), enum đặt cạnh `EVIDENCE_TYPES` (`:16`). Thêm
   `STRONG_EVIDENCE_TYPES = EVIDENCE_TYPES - {"artifact"}`.
3. Gate FINISHED **không đổi** — `verdict` chỉ là annotation read-model.

## Related code files

| File | Vai trò | Anchor |
|---|---|---|
| `supervisor/evidence.py` | `record_ac_report`, `evidence_type_of`, vocab | `:16`, `:22`, `:39-66` |
| `supervisor/state.py` | `AcceptanceCheck.status`, `all_accepted` | `:29`, `:102` |
| `tests/test_acceptance_gate.py` | 8 test hiện hành (PHẢI vẫn xanh) | `:127-145` |

## Implementation steps (TDD)

**Tests Before** — mở rộng `tests/test_acceptance_gate.py` (đỏ trước):
1. `test_finished_emits_ac_report` (đã có): thêm assert `reports[0]["verdict"] == "passed"` (evidence `tool_result` mạnh).
2. AC mới `test_verdict_passed_with_risk_on_generic_artifact`: AC passed bằng evidence `kind` lạ → `evidence_type_of` trả `"artifact"` generic → `verdict == "passed_with_risk"`.
3. AC mới `test_verdict_pending_when_not_finished`: run bị từ chối → nếu có ac_report thì `verdict == "pending"` (hoặc không có report — khớp `test_finish_denied_no_ac_report`).
4. 8 test cũ giữ nguyên xanh (additive field, không phá assert cũ).

**Implement**: thêm hàm thuần `_overall_verdict(checks, artifacts) -> str` trong `evidence.py`; gọi trong `record_ac_report`.

**Tests After**: `python -m pytest tests/test_acceptance_gate.py -q` xanh (8 cũ + 2 mới); full suite không đỏ.

**Regression gate**: `python -m pytest tests_audit/test_supervisor_adversarial_matrix.py -q`.

## Success criteria

- [ ] `ac_report.verdict ∈ {passed, passed_with_risk, pending}`, policy thuần trong `evidence.py`.
- [ ] 8 test acceptance cũ vẫn xanh; 2 test verdict mới xanh.
- [ ] Gate FINISHED (`all_accepted`) **không** thay đổi hành vi.
- [ ] `CHANGELOG.md` thêm `feat(E21): overall verdict (passed/passed_with_risk/pending) on ac_report`.

## Risk

Thấp — thêm field, không ai phụ thuộc cứng (UI fake backend, DEC-6). Caveat YAGNI: chưa có consumer cho `verdict`; chấp nhận vì user chốt làm đủ ba + chi phí rẻ + tier neo vào evidence-strength có thật. Rollback = bỏ field.
