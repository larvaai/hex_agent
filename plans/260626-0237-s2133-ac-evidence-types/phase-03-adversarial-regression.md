---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 03 — Adversarial + regression + chốt sổ

Context: [plan.md](plan.md) · Touchpoints: `tests_audit/test_acceptance_evidence_adversarial.py`
(NEW), `CHANGELOG.md`, `docs/decisions.md`. Đọc: [loop.py:107-144](../../supervisor/loop.py)
(resume), [state.py:114-145](../../supervisor/state.py).

## Mục tiêu
Đóng các góc tối adversarial của siết-gate + AC report, rồi chốt CHANGELOG/DEC. Không thêm
code runtime mới — chỉ test + tài liệu.

## TDD

### Tests Before (`tests_audit/test_acceptance_evidence_adversarial.py` — red)
- **AC5 self-evidence vòng**: state có artifact `ac_report` (kind=ac_report); O báo AC passed
  với `evidence_ids=["ac_report"]` → `judge_acceptance` để AC `pending` (NON_EVIDENCE_KINDS chặn).
- **AC6 resume không trùng report**: chạy tới FINISHED (checkpoint_store SQLite,
  [loop.py:107-144](../../supervisor/loop.py)); `resume_task_loop` trên checkpoint terminal →
  trả `_result` ngay ([loop.py:142-143](../../supervisor/loop.py)), `artifacts["ac_report"]` còn
  đúng một, nội dung không đổi.
- **Property (hypothesis)**: với mọi tập AC + acceptance_status, nếu `result["status"]=="finished"`
  thì **mọi** `acceptance[i]["status"]=="passed"` và mỗi cái có ≥1 evidence_id mà
  `evidence_type_of(artifact) is not None`. (Bất biến S21.33: finished ⇒ mọi AC có evidence đúng loại.)
- **Mixed-kind (≥1 valid)**: evidence_ids = [tool_result_id, context_packet_id] → AC **pass**
  (spec S21.33 "≥1 evidence hợp lệ"; mọi id vẫn phải TỒN TẠI). Sửa theo red-team FM-HIGH:
  quantifier = `any`-valid + `all`-exist, KHÔNG `all`-valid.
- **Only-scaffolding**: evidence_ids = [context_packet_id] (chỉ scaffolding) → AC **pending**.
- **Ghost/missing vẫn pending**: id không tồn tại fail `all`-exist bất kể quantifier loại.

### Implement
- Chỉ viết test. Nếu property phát hiện hành vi ngoài ý (vd lenient default cho kind lạ làm
  "finished" với evidence rác) → quay lại P1 siết `NON_EVIDENCE_KINDS` (đừng weaken test).

### Tests After / Regression (gate phase)
- `python -m pytest tests/test_supervisor_*.py tests/test_acceptance_gate.py
  tests/test_evidence.py tests_audit/ -q` xanh 100%.
- `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`.
- Xác nhận **không đổi**: `control/*`, `config/runtime_event_types.yaml`,
  `config/runtime_command_types.yaml` (git diff trống ở các path này).

## Chốt sổ (sau khi xanh)
- `CHANGELOG.md` +mục: `## E21 — S21.33 evidence types + AC report · 2026-06-26` với bullet
  path+line (`supervisor/evidence.py`, `graph.py:238`, `loop.py:170-176`).
- `docs/decisions.md`: ghi DEC — "evidence_type **DERIVED** từ `artifact.kind` (KHÔNG lưu trên AC);
  `NON_EVIDENCE_KINDS={session_plan,context_packet,ac_report}`; kind rỗng→None; kind-lạ-do-worker→artifact
  (**trust-worker**: threat model = O mis-cite scaffolding, KHÔNG phòng worker thù địch);
  **quantifier passed = ≥1 evidence hợp lệ (spec S21.33) + mọi id phải tồn tại**, KHÔNG all-valid;
  `ac_report` id = `ac_report-{session_id}`". (Chạy `harness/scripts/decision_register.py` lúc approve.)
- MAP.md tự cập nhật từ docstring `supervisor/evidence.py` (gen_map) — verify dòng xuất hiện.

## Risks
- Property test có thể lộ rằng "lenient default" cho phép artifact rác (kind lạ) pass →
  đó là tín hiệu siết `NON_EVIDENCE_KINDS` rộng hơn HOẶC đảo default thành strict (chỉ
  EVIDENCE_TYPES + tool_result + delegation_result tính). Quyết định cuối ở validate-gate.
- Rollback: test-only + doc → revert sạch, 0 ảnh hưởng runtime.
