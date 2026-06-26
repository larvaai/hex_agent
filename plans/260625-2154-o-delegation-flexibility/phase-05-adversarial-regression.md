---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 05 — Adversarial + regression gate

Context: [plan.md](plan.md) · Touchpoints: `tests_audit/`. Không thêm code sản phẩm; chỉ siết bằng test đối kháng + xác nhận không regress.

## Mục tiêu
Chứng minh các bất biến của [plan.md](plan.md) đứng vững dưới điều kiện đối kháng (đặc biệt resume + idempotency + scope-no-widen), và toàn bộ suite cũ vẫn xanh.

## Requirements (tuân `tests_audit`: no-xfail, no-lowered-assertion)
1. **Resume double-apply guard.** Mô phỏng: apply một `AddAgentToLoop` ở round N (roster grow) trong MỘT save atomic (Phase 4), rồi "crash" và `resume_task_loop` ([supervisor/loop.py:107](../../supervisor/loop.py)) → `applied_command_keys` khôi phục, command KHÔNG apply lại (roster không grow lần hai). Khẳng định trên `SqliteTaskLoopStore` round-trip thật. **Cửa sổ crash-giữa-hai-save (red-team FM6) đã đóng** vì apply gộp vào cùng checkpoint với `round_no += 1`; thêm một test khẳng định checkpoint sau round N chứa ĐỒNG THỜI roster mới + `applied_command_keys` + `pending_commands` đã clear (không có trạng thái nửa-vời trên đĩa).
2. **Idempotency dưới lặp.** O phát cùng `AddAgentToLoop` ở nhiều round liên tiếp → roster grow đúng một lần; key chỉ xuất hiện một lần trong `applied_command_keys`.
3. **Unknown role/department.** `AddAgentToLoop` role ngoài catalog → KHÔNG thêm + `command.rejected`; department không tồn tại → `run_round` raise rõ ràng (không nuốt lỗi thành team rỗng).
4. **Scope-no-widen.** Department expand: mỗi member delegate với scope == O cấp; khẳng định `DelegationPolicy.allowed_capabilities` mỗi member ⊆ supervisor scope (không member nào có cap ngoài assignment). Bổ sung: O không thể cấp member cap mà supervisor không có (đã chặn bởi [delegation/policy.py:25-27](../../delegation/policy.py) — test xác nhận vẫn còn hiệu lực sau expansion).
5. **Authority gate vẫn là chân lý.** Sau expansion, một member chưa-admit (chưa vào roster) mà bị ép vào `next_agent_calls` agent-level → `run_round` raise `PermissionError` ([graph.py:142-147](../../supervisor/graph.py)).
6. **Trust-O không rò sang human.** Command `issued_by.type=="human"` trong `pending_commands` → KHÔNG mutate roster (permission path chưa làm) — chốt ranh giới scope.
7. **Bất biến "không đổi".** Xác nhận `delegation/*`, `control/commands.py`, `control/command_registry.py`, `config/runtime_command_types.yaml` không bị sửa (git diff trống cho các path đó).

## Files
- ADD `tests_audit/test_supervisor_roster_growth_adversarial.py`
- (chạy lại) toàn bộ `tests/` + `tests_audit/`

## TDD

### Tests Before
Viết 6 test đối kháng (mục 1-6) — kỳ vọng đỏ nếu thiếu guard (vd bỏ `applied_command_keys` check → double-apply đỏ).

### Implement
Không code sản phẩm mới; nếu một test đối kháng đỏ vì lỗi thật → quay lại phase tương ứng sửa (TDD), không hạ assertion.

### Tests After / Regression Gate (DoD plan)
```
pip install -e ".[dev,audit]"   # langgraph + hypothesis
python -m pytest tests/test_supervisor_*.py tests/test_roles.py \
                 tests_audit/test_supervisor_*.py -q     # 100% pass
python -m pytest tests_audit/ -q                          # strict audit xanh (trừ 2 artifact Windows-path đã biết)
python run_smoke.py                                       # CORE_AGENT_SMOKE_OK
git diff --stat delegation/ control/commands.py control/command_registry.py config/runtime_command_types.yaml  # rỗng
```

## Risks + rollback
- Risk: 2 test `tests_audit/test_security_boundaries.py` fail trên macOS (`..\escape`, `C:/Windows`) là artifact Windows-path, KHÔNG phải regression của plan này — ghi rõ, không sửa ở đây.
- Risk: env thiếu `langgraph`/`hypothesis` → suite không collect. → DoD ghi rõ lệnh install. Rollback: phase này chỉ test, gỡ file test không ảnh hưởng sản phẩm.
