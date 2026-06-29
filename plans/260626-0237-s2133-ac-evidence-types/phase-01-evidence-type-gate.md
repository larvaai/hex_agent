---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 01 — Evidence-type contract + siết acceptance gate

Context: [plan.md](plan.md) · Touchpoints: `supervisor/evidence.py` (NEW),
`supervisor/graph.py` (sửa `judge_acceptance`). Đọc: [graph.py:229-246](../../supervisor/graph.py),
[state.py:90](../../supervisor/state.py), [test_acceptance_gate.py](../../tests/test_acceptance_gate.py).

## Mục tiêu (SRP)
Module thuần phân loại evidence: cho một artifact trên Blackboard, trả về loại evidence S21.33
hoặc `None` nếu nó là scaffolding. Rồi `judge_acceptance` dùng nó để **từ chối** evidence sai
loại — không chỉ check tồn tại.

## Requirements
1. `supervisor/evidence.py` (docstring dòng đầu: `"""Evidence classification cho acceptance gate. Epic E10/E21 (S21.33)."""`):
   - `EVIDENCE_TYPES = frozenset({"artifact","tool_result","reviewer_report","diff","test_result"})`
   - `NON_EVIDENCE_KINDS = frozenset({"session_plan","context_packet","ac_report"})`
   - `def evidence_type_of(artifact: dict[str, Any]) -> str | None:`
     - `kind = str(artifact.get("kind",""))`
     - `kind == ""` → `None` (artifact không loại = KHÔNG phải evidence; loop luôn set `kind` nên đây là phòng thủ — red-team FM-MED)
     - `kind in NON_EVIDENCE_KINDS` → `None`
     - `kind in EVIDENCE_TYPES` → `kind` (agent phát artifact typed trực tiếp, **gồm cả** `tool_result`)
     - else (`delegation_result` + kind do worker đặt) → `"artifact"` (**trust-worker** — xem DEC)
     - (Đã bỏ nhánh `kind=="tool_result"` riêng: thừa vì `tool_result ∈ EVIDENCE_TYPES`, red-team FM-LOW.)
2. `judge_acceptance` ([graph.py:238](../../supervisor/graph.py)) đổi điều kiện `passed`:
   - cũ: `claimed=="passed" and evidence and all(e in state.artifacts for e in evidence)`
   - **mới**: `claimed=="passed" and evidence and all(e in state.artifacts for e in evidence) and any(evidence_type_of(state.artifacts[e]) is not None for e in evidence)`
   - **Định lượng = spec S21.33 "≥1 evidence hợp lệ"** ([acceptance.md:122-123](../../docs/spec/active/E21-realtime-control-plane/acceptance.md)): mọi id phải **TỒN TẠI** (giữ `all(... in state.artifacts)`) **và** ÍT NHẤT MỘT id thuộc loại evidence. KHÔNG dùng `all`-valid — sẽ chặn oan finish hợp lệ khi O kèm 1 scaffolding id (red-team FM-HIGH).
   - import `from supervisor.evidence import evidence_type_of` (đầu graph.py).
   - Hành vi giữ nguyên cho mọi nhánh khác (failed/pending); chỉ siết nhánh passed.

## TDD

### Tests Before (`tests/test_evidence.py` — red)
- `evidence_type_of({"kind":"tool_result"}) == "tool_result"`.
- `evidence_type_of({"kind":"delegation_result"}) == "artifact"`.
- `evidence_type_of({"kind":"diff"}) == "diff"` (và `test_result`, `reviewer_report`).
- `evidence_type_of({"kind":"context_packet"}) is None` (và `session_plan`, `ac_report`).
- `evidence_type_of({"kind":"weird_unknown"}) == "artifact"` (trust-worker default — pin DEC).
- `evidence_type_of({}) is None` **và** `evidence_type_of({"kind":""}) is None` (không loại = không evidence).

### Tests Before (`tests/test_acceptance_gate.py` — thêm, red)
- `test_finish_rejects_scaffolding_evidence`: round 0 `continue` tạo turn (sinh
  `context_packet`/`session_plan`/`delegation_result`); round 1 `finished` với
  `acceptance_status=[{id:"ac1",status:"passed",evidence_ids:["context_packet-0001"]}]`
  → `result["status"] != "finished"`, `acceptance[0]["status"]=="pending"`. (Dùng
  `compose_json`/`decision_json`/`make_env`, [conftest.py:90-99](../../tests/conftest.py);
  xác nhận id thật của context_packet qua `_next_id` [graph.py:81-82,161](../../supervisor/graph.py)
  `[UNVERIFIED — confirm id format khi cook]`.)
- `test_finish_allows_mixed_when_one_valid`: evidence_ids = [`tool_result-XXXX`, `context_packet-YYYY`]
  (1 hợp lệ + 1 scaffolding, đọc id thật từ `result["state"]["artifacts"]`) → `passed`
  (spec S21.33 "≥1 hợp lệ"; mọi id vẫn tồn tại). Đây là test ghim FM-HIGH (any-valid, không all-valid).

### Implement
- Viết `supervisor/evidence.py` (chỉ phần Phase 1: 2 hằng + `evidence_type_of`; `record_ac_report`
  để Phase 2).
- Sửa `judge_acceptance` đúng 1 điều kiện + 1 import.

### Tests After / Regression
- `pytest tests/test_evidence.py tests/test_acceptance_gate.py -q` xanh.
- **Regression ghim**: `test_finish_allowed_with_real_evidence`
  ([test_acceptance_gate.py:48-65](../../tests/test_acceptance_gate.py)) vẫn xanh —
  `tool_result-0001` là evidence hợp lệ → tightening không phá.
- `pytest tests/test_supervisor_*.py -q` xanh (siết chỉ chạm nhánh passed-with-bad-kind).

## Risks
- Id format artifact (`context_packet-0001`) phải khớp `_next_id` thật → test có thể cần
  đọc id từ `result["state"]["artifacts"]` thay vì hardcode. Cook resolve `[UNVERIFIED]`.
- Rollback: xoá `evidence.py` + revert 1 dòng graph.py.
