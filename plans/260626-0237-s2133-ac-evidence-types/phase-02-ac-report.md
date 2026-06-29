---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 02 — AC report artifact khi FINISHED

Context: [plan.md](plan.md) · Touchpoints: `supervisor/evidence.py` (thêm `record_ac_report`),
`supervisor/loop.py` (nhánh finished). Đọc: [loop.py:170-176,202-206](../../supervisor/loop.py),
[state.py:96-97](../../supervisor/state.py).

## Mục tiêu
Khi loop đạt FINISHED (mọi AC `is_satisfied`), sinh một artifact `kind="ac_report"` chụp lại
trạng thái AC + evidence + loại evidence + session_id. Artifact nằm trên Blackboard → tự persist
qua `_terminate`→`ctx.save` ([loop.py:206](../../supervisor/loop.py)).

## Requirements
1. `record_ac_report(state) -> str` trong `supervisor/evidence.py`:
   - Dựng payload: `{"kind":"ac_report","session_id":state.session_id,"task_id":state.task_id,
     "checks":[{"id":c.id,"text":c.text,"status":c.status,"evidence_ids":list(c.evidence_ids),
     "evidence_types":[evidence_type_of(state.artifacts[e]) for e in c.evidence_ids if e in state.artifacts]}
     for c in state.acceptance_checks]}`.
   - id deterministic, một-report-một-run: **`report_id = f"ac_report-{state.session_id}"`**
     → idempotent (resume/gọi lại ghi cùng key, không sinh trùng — AC6) **và** chống worker
     squat key `"ac_report"` trần: worker đặt `artifact_id` verbatim
     ([graph.py:182](../../supervisor/graph.py)), id gắn `session_id` thì worker không vô tình
     trùng (red-team FM-LOW). Phân loại evidence theo `kind`, không theo id → vẫn bị
     `NON_EVIDENCE_KINDS` loại.
   - `state.add_artifact(report_id, payload)` ([state.py:96-97](../../supervisor/state.py)); return `report_id`.
   - KHÔNG emit event (artifact-only; `runtime_event_types.yaml` không đổi).
2. Wire `supervisor/loop.py` nhánh `finished` ([loop.py:170-176](../../supervisor/loop.py)):
   - sau `if state.all_accepted():`, **trước** `_terminate(...)`:
     `state.final_output = decision.final_output or {}` → `record_ac_report(state)` →
     `_terminate(state, ctx, TaskLoopStatus.FINISHED, ...)`.
   - import `from supervisor.evidence import record_ac_report`.
   - Nhánh finish-denied (`else`/`state.reason=...`) KHÔNG gọi → AC4.

## TDD

### Tests Before (`tests/test_evidence.py` — red)
- `record_ac_report` trên state có 1 AC passed (evidence=`tool_result-X`) → artifacts có **đúng một**
  entry `kind=="ac_report"`; `checks[0]["evidence_types"]==["tool_result"]`; `session_id/task_id` đúng.
- Gọi `record_ac_report` hai lần → vẫn **đúng một** artifact `kind=="ac_report"` (id deterministic theo session).

### Tests Before (`tests/test_acceptance_gate.py` — red)
- `test_finished_emits_ac_report`: kịch bản như `test_finish_allowed_with_real_evidence` →
  tồn tại **đúng một** artifact `kind=="ac_report"` (tìm theo kind, **không** hardcode key)
  với `checks[0]["status"]=="passed"`.
- `test_finish_denied_no_ac_report`: kịch bản `test_no_finish_without_evidence` →
  **không** artifact nào `kind=="ac_report"`.

### Implement
- Thêm `record_ac_report` vào `evidence.py`; wire 2 dòng vào `loop.py`.

### Tests After / Regression
- `pytest tests/test_evidence.py tests/test_acceptance_gate.py tests/test_supervisor_*.py -q` xanh.
- `result["state"]["artifacts"]` round-trip qua `encode/decode_taskloop_state`
  ([state.py:114-145](../../supervisor/state.py)) — ac_report là dict primitive → an toàn.

## Risks
- ac_report sinh ra **sau** khi `all_accepted` nên không tự làm evidence cho chính AC (và
  `ac_report ∈ NON_EVIDENCE_KINDS` từ P1 chặn trỏ vòng — verify ở P3 AC5).
- Rollback: bỏ `record_ac_report` + 2 dòng loop.py.
