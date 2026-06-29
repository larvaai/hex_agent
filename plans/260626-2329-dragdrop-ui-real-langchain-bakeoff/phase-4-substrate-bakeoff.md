---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 4 — Bakeoff substrate Z·L·Bu (đóng câu hỏi langchain bằng số)

> Bakeoff handoff re-aligned với `harness/scripts/bakeoff_rank.py` THẬT (verbs: `preflight`, `record --run --candidate --trial --value`, `rank --run --direction --noise --rel-band --plan-dir`). `compute_verdict` (bakeoff_rank.py:74-95) **raise** nếu candidate ∉ 2..4 hoặc candidate nào thiếu trial; schema `artifact-bakeoff-verdict.json:17` đòi `minItems:2`. ⇒ metric phải là MỘT scalar/trial; <2 candidate → REFUSE, không tự-đăng-quang Z.

**Mục tiêu:** Trả lời "có bao giờ thay orchestrator zero-dep không?" bằng đo. **Gated SAU khi UI slice (P1-3) xanh** — off critical path. Phá invariant "zero external dep" có chủ đích (DEC-A4); base install vẫn zero-dep (dep ∈ optional extra, lazy-import).

**Files:**
- Create: `drag_from_zero/dragzero/bakeoff/__init__.py`, `port.py`, `candidate_zerodep.py`, `candidate_langgraph.py`, `candidate_burr.py`, `scenario.py`, `score.py`, `run_bakeoff.py`
- Create: `drag_from_zero/tests/test_bakeoff_substrate.py`
- Modify: `drag_from_zero/pyproject.toml` (`[project.optional-dependencies] bakeoff=["langgraph","burr"]`)
- Artifact out: `plans/260626-2329-dragdrop-ui-real-langchain-bakeoff/artifacts/` (verdict ghi bởi `bakeoff_rank.py rank --plan-dir <…>/artifacts`)
- KHÔNG đụng: core, server.py, app/

## Pre-step — research nhẹ lấp substrate table DEC-11

DEC-11 (`docs/decisions.md:142`, affects line :139 = "new-greenfield-repo…") KHÔNG có langchain/langgraph. Lấp 4 ô cho L+Bu: **local?** **license** **headless?** **mid-run mutation?** (thêm agent vào graph ĐANG chạy — giả thuyết L=KHÔNG, StateGraph compiled). 1 researcher pass → `artifacts/substrate-table.md`. L rõ ràng không hỗ trợ mid-run mutation → VẪN chạy bakeoff để verdict ghi thất bại đó bằng số (đó LÀ kết quả).

## Requirements

**Functional:**
- **`SubstratePort`** (port.py) — hợp đồng HÀNH VI tối thiểu, KHÔNG Z-shaped: `compose(topology)→Substrate`, `run_until_idle()→ScenarioResult`, `inject(role)`, và một bộ **capability-probe** trung tính.
- **Metric = MỘT scalar/candidate** (sửa shape-mismatch): `score = observability_fraction if inject_clean else 0.0`, `inject_clean∈{0,1}` (inject giữa phiên resume tới child done KHÔNG recompile/restart). `direction=higher`. Một `--value` mỗi trial.
- **Observability = capability-checklist TRUNG LẬP** (sửa rigged-bakeoff): KHÔNG `|vocab ∩ vocab_dragzero|` (Z auto-1.0). Mỗi candidate (Z **không** auto-1.0) chấm trên: (1) tái dựng được task tree? (2) phát hiện task parked/waiting? (3) attribute event→agent? (4) quan sát được roster đổi mid-run? `observability_fraction = #đạt / 4`. **Sign-off:** một probe item KHÔNG được phrase "emits dragzero event X" — red-team/non-Z review rubric trước khi tin verdict.
- **Scenario chuẩn** (scenario.py): root→plan→delegate role-trống→waiting→inject→resume→child done. **Deterministic**: một `ScriptedPolicy` substrate-agnostic (role→decision table giống FakeLLM dùng) mọi adapter lái — KHÔNG LLM thật, KHÔNG per-substrate divergence. Assert `ScenarioResult.events` byte-identical qua lần lặp (`spread==0`) TRƯỚC khi tin ranking (chống challenger non-deterministic thổi noise band thành "tie" giả).
- **3 candidate:** **Z** (`candidate_zerodep.py`, wrap Orchestrator/Roster, reuse core), **L** (`candidate_langgraph.py`, StateGraph, lazy-import), **Bu** (`candidate_burr.py`, cyclic-FSM+SQLite, lazy-import). Z chấm trên CÙNG rubric như L/Bu, không miễn.
- **Verdict CLI (drive script THẬT, không reimplement):** `run_bakeoff.py` (optional `preflight --metric-cmd`) → mỗi (candidate,trial) `bakeoff_rank.py record --run <id> --candidate <c> --trial <i> --value <s>` → `bakeoff_rank.py rank --run <id> --direction higher --noise low --rel-band 0.05 --plan-dir <plandir>/artifacts`. KHÔNG tự viết compute_verdict.
- **Refuse <2:** langgraph/burr VẮNG (default zero-dep posture) → bakeoff **EXIT "insufficient candidates — install .[bakeoff]"**, KHÔNG ghi verdict 1-candidate, KHÔNG đăng-quang Z khi không có đối thủ. DEC-register (bước finish) gate trên `verdict.candidates ≥ 2` đã chấm.

**Non-functional:**
- `import dragzero` (base) KHÔNG kéo langgraph/burr — chỉ candidate_* lazy-import trong hàm; thiếu extra → candidate `skipped` (reason observable), KHÔNG crash (mirror tools.py unknown-tool→observable-failure).
- Bakeoff headless (`python -m dragzero.bakeoff.run_bakeoff`), KHÔNG đụng UI/server.

## Tests Before (đỏ) — `tests/test_bakeoff_substrate.py`

- **Z thỏa port + chấm THẬT trên rubric** (KHÔNG hard-assert 1.0): `candidate_zerodep` compose→scenario→`inject_clean==1`; `observability_fraction` = số probe Z thực-sự đạt (có thể <1.0 nếu probe (4) roster-change Z không expose rõ — chấm trung thực, KHÔNG "Z LÀ nguồn vocab").
- **Port contract:** mọi candidate cùng signature; thiếu dep → `skipped` reason, test KHÔNG fail (`pytest.importorskip` cho L/Bu chạy thật).
- **Score đơn điệu:** substrate fake "không-park" (mis-route role trống) → `inject_clean==0` → score 0 < Z (good≠bad, kỷ luật eval Slice 3b README:109-113).
- **Determinism:** scenario chạy 2 lần → `events` identical, `spread==0`.
- **Verdict CLI shape:** record 2 candidate giả (Z + fake) → `rank` → file pass schema `artifact-bakeoff-verdict` (required keys; candidates≥2). 1-candidate → `run_bakeoff` EXIT "insufficient candidates" (KHÔNG verdict).

## Implement

1. `port.py`: `SubstratePort` Protocol + `ScenarioResult`(events, inject_clean, capabilities:dict[str,bool]) + `CAPABILITY_PROBES` (4 câu trung lập).
2. `scenario.py`: topology-park + `ScriptedPolicy` deterministic; `run_scenario(substrate)→ScenarioResult`.
3. `candidate_zerodep.py`: adapter mỏng quanh Orchestrator (reuse, không copy core).
4. `candidate_langgraph.py`/`candidate_burr.py`: lazy-import; map sang capability-probe hết mức; probe không đạt = False (điểm trừ THẬT, ghi rationale).
5. `score.py`: `score(result)=observability_fraction if inject_clean else 0.0`.
6. `run_bakeoff.py`: chạy candidate khả dụng (skip vắng dep); nếu `<2` → exit message; else shell `bakeoff_rank.py record…` rồi `rank … --plan-dir <plandir>/artifacts`; in ranking+rationale.
7. `pyproject.toml`: extra `bakeoff`.
8. **Finish:** đọc `artifacts/*verdict*.json`; CHỈ khi `candidates≥2` → đề xuất DEC substrate (DEC-A1/A4) qua `decision_register.py --append-alloc` — KHÔNG tự ghi `docs/decisions.md`.

## Tests After / Regression Gate

- `python -m pytest drag_from_zero/tests/test_bakeoff_substrate.py -q` xanh (Z + fake-bad + determinism + verdict-shape; L/Bu importorskip).
- `python -c "import dragzero"` KHÔNG kéo langgraph/burr (assert base zero-dep).
- `python -m pytest drag_from_zero/tests -q` toàn bộ xanh (bakeoff cô lập, core untouched).

## Success Criteria

- [ ] Metric = MỘT scalar/candidate; `run_bakeoff` drive `bakeoff_rank.py record`+`rank` THẬT (không reimplement verdict).
- [ ] Observability = checklist trung lập; Z chấm cùng rubric (KHÔNG auto-1.0); non-Z sign-off rubric.
- [ ] L+Bu cài sau extra cho điểm THẬT (kể cả thấp — fail là dữ liệu); base `import dragzero` zero-dep.
- [ ] `bakeoff-verdict.json` pass schema, `candidates≥2`; <2 → REFUSE "insufficient candidates".
- [ ] DEC substrate đề xuất CHỈ khi verdict có ≥2 candidate đã chấm.

## Risk

| Risk | L×I | Mitigation |
|---|---|---|
| Bakeoff Z-shaped (observability = Z enum) → L/Bu không thể thắng | high×bias | capability-checklist trung lập, Z không miễn; non-Z sign-off "không probe nào nói emits-event-X" |
| Handoff shape-mismatch bakeoff_rank.py | high×broken | metric scalar/trial, drive `record`/`rank` THẬT, `--plan-dir`; KHÔNG composite/skip-on-missing |
| <2 candidate tự-đăng-quang Z | med×false-verdict | EXIT "insufficient candidates"; DEC gate `candidates≥2` |
| Bakeoff token-burn | med×bleed | scenario deterministic (ScriptedPolicy, no LLM), N trial nhỏ (noise=low); `spread==0` gate |
| langgraph/burr leak vào base | high×invariant | lazy-import, optional extra, test assert `import dragzero` sạch |
| Scenario bất công với FSM Burr | med×bias | research pre-step; map probe hết mức; ô không đạt ghi rõ rationale |
