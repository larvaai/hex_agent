---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 1 — Workflow build-along: Microkernel, chokepoint & observability

> Cap voi: roadmap [phase-1-microkernel-chokepoint.md](../phase-1-microkernel-chokepoint.md) · Epic E01+E04 · Invariant I1-I4 · Muc tieu: vua BUILD vua HIEU phase nay qua skill + cong

## 0. Ban se roi phase nay khi

**Build duoc (X):**
- `python run_smoke.py` in `CORE_AGENT_SMOKE_OK run_id=...` (`run_smoke.py:35`).
- Moi run de `events.jsonl` + `summary.json` duoi `var/agent_runs/<run_id>/`.
- `python -m observability.inspect summary latest` va `events latest` doc lai duoc run vua chay.
- Suite xanh: `tests/test_kernel.py tests/test_trace_ids.py tests/test_observability.py tests/test_state.py tests/test_session.py tests/test_event_concurrency.py`.

**Giai thich duoc (Y) — 4 invariant nen, theo luat → file·ham → pha ra mat gi:**
- I1 mot cua: moi tool qua `AgentKernel.execute_tool` (`kernel.py:106`).
- I2 freeze: `freeze()` (`kernel.py:91`) khoa registry+config truoc session dau; `use()` sau freeze nem (`kernel.py:102`).
- I3 state co lap: `KernelSession` + `StateStore.snapshot/restore` deep-copy (`state.py:21`).
- I4 lineage: moi event mang 6 truong tu `ToolCallContext.event_fields()` (`schemas.py:48`).

Thieu mot trong hai (test do HOAC khong giai thich noi I#) → CHUA roi phase. Xem §4, §5.

Vi sao phase nay lam TRUOC het: day la **cai lo song toi thieu** — mot cua chung (`execute_tool`) de dan observability/safety/envelope mot lan, ap cho moi tool ke ca tool chua viet. Khong co cua nay, moi feature phase sau (LLM ph2, toolbox ph3, graph ph4, delegation ph6) phai tu lo log/an toan rieng → he thong vo lam tung khi lon. Build cua + khung truoc, feature chi la cam adapter vao port (roadmap §8).

## 1. Y tuong trien khai kha thi (doc la biet lam gi)

Bon manh CU THE, moi manh kem "ra cai gi de biet xong". Bam thu tu phu thuoc o roadmap §3 (B1→B8).

**Y1 — Cai cua + try/except quanh executor (trai tim phase, I1).**
Viet `core/kernel.py::execute_tool` (`kernel.py:106`) chay dung trinh tu: deep-copy `args` → publish `tool.requested` → scope check → middleware chain boc `core` → `registry.resolve_tool` → `executor.execute` trong try/except → chuan hoa `CapabilityResult` → publish `tool.completed|failed`. `core(req)` (`kernel.py:152`) bat moi exception cua tool tra `kernel_error=True` (`kernel.py:131`).
*Ra cai gi de biet xong:* goi mot tool co tinh `raise` → envelope `ok=False, kernel_error=True`, kernel **van song** goi tiep duoc (test `test_kernel.py`).

**Y2 — Registry fallback khong nem (I1 phu tro).**
Viet `core/registry.py`: `resolve_tool` uu tien khop chinh xac → `_fallback` → `NullToolPort` (`registry.py:103`); `NullToolPort.execute` tra `ok=False, missing_capability=True` thay vi nem (`registry.py:34`). `freeze()` khoa dang ky (`registry.py:60`).
*Ra cai gi de biet xong:* `resolve_tool("ten_la")` → executor la `null_tool`, **khong** exception; `test_unknown_tool_null_fallback` xanh.

**Y3 — freeze tach cai-dong-bang khoi cai-thay-doi (I2+I3).**
Viet `freeze()` (`kernel.py:91`): `registry.freeze()` + `config = _deep_freeze(deepcopy(config))`. `SessionFactory.create_root` goi `kernel.freeze()` roi publish `task.accepted` (`session.py:141`). State theo-run song trong `KernelSession.state` (`StateStore`), `snapshot/restore` deep-copy (`state.py:21`).
*Ra cai gi de biet xong:* `use()` sau freeze nem RuntimeError (`kernel.py:102`); `test_snapshot_not_affected_by_later_set` (`test_state.py:18`) xanh → khong alias state.

**Y3b — EventBus giao detached, observer co lap.**
Viet `core/events.py::EventBus.publish` (`events.py:22`): chup subscriber trong lock roi giao **ngoai** lock, moi observer nhan **ban deep-copy rieng**, observer nem thi nuot (`events.py:29`). Day la nen de logger (Y4) khong bao gio gay runtime.
*Ra cai gi de biet xong:* `tests/test_event_concurrency.py` xanh; mot observer raise → cac observer khac van nhan, runtime khong gay.

**Y4 — Lineage gan o cua + logger bam EventBus (I4+E04).**
`ToolCallContext.event_fields()` (`schemas.py:48`) sinh 6 truong `run_id/task_id/session_id/parent_session_id/delegation_id/actor_id`; cua `setdefault` lineage vao metadata moi envelope (`kernel.py:210-213`). `observability/event_log.py::EventLogger.emit` append-JSONL co seq+timestamp+run_id (`event_log.py:60`); `attach_to_bus` subscribe `sink` mirror moi event + dem metrics (`event_log.py:102`); `finish()` ghi `summary.json` dung mot lan (`event_log.py:80`). `KernelSession.execute_tool` bom `call_context()` vao kernel (`session.py:75`) → lineage khong bao gio do tay.
*Ra cai gi de biet xong:* `test_tool_events_carry_task_id` (`test_trace_ids.py:18`) xanh; `inspect events latest` thay chuoi `tool.requested → tool.completed` co `task_id`.

**Trinh tu middleware (lam dung mot lan, ap cho moi tool).**
`ToolMiddleware` (`middleware.py:11`) la callable `(request, nxt) -> dict`: act *truoc* (sua request) → goi `nxt` di vao trong → act *sau* (sua envelope), hoac short-circuit (khong goi `nxt`). Dang ky `use()` theo thu tu **ngoai→trong** (`kernel.py:100`); cua boc `reversed(self._middlewares)` quanh `core` (`kernel.py:193`) → mw dau la lop ngoai cung (thay request som nhat, envelope muon nhat). Vi du wire `[timing, policy, retry, condense]` (`bootstrap.py:36-53`): request di `timing → policy → retry → condense → core`, envelope ve nguoc lai — `timing` do ca thoi gian lop trong, `policy` chan som truoc khi ton retry. Posture mac dinh **fail-closed**: mw raise → propagate ra bien cua (`ok=False`); chi ai khai `fail_open=True` (advisory) moi skip khi raise (`kernel.py:58`, `middleware.py:14-20`).
*Ra cai gi de biet xong:* `test_kernel.py::test_describe_capabilities` (`test_kernel.py:40`) thay `echo`; goi qua kernel co middleware → envelope van 6-khoa, mw raise khong sap cua.

**B8 — run_smoke la cong dong phase (no LLM/network).**
`run_smoke.py::main` rap kernel+logger, chay `echo`, chung minh: envelope `ok` + `metadata.task_id` truy vet duoc (`run_smoke.py:18-20`), tool ngoai `allowed_capabilities` cua session bi chan boi scope-check → `metadata.scope_block` (`run_smoke.py:22-23`) — KHAC voi tool chua dang ky (`missing_capability`, NullToolPort, Y2), lifecycle dong (`run_smoke.py:31-32`), in `CORE_AGENT_SMOKE_OK` (`run_smoke.py:35`).
*Ra cai gi de biet xong:* stdout co dung `CORE_AGENT_SMOKE_OK run_id=...`; exit 0.

## 2. Workflow skill-by-skill (vong lap build)

Bam buildLoop kernel brief: scout(2) → plan(4) → approve(5) → cook(6) → test(7) → review(8). Prompt copy-dan-duoc, tham chieu path that cua phase nay.

| Buoc | Skill (invoke) | Prompt mau dua cho Claude | Artifact ra (path that) | Muc dich |
|---|---|---|---|---|
| 1 *(tuy chon)* | `hs:understand` `/hs:understand core/` | "Map vung core/ + observability/ truoc khi plan Phase 1. Muc tieu hieu seam: ToolPort (core/ports.py:20), chokepoint (core/kernel.py execute_tool), envelope (core/schemas.py CapabilityResult). Tra abs-path + unknowns. Tham chieu roadmap §2 bang module." | `plans/reports/<slug>-report.md` | Hieu vung code la truoc khi plan (bo qua neu da quen) |
| 2 | `hs:scout` `/hs:scout` | "Scout vung lam Phase 1 microkernel/chokepoint. Liet ke file/anchor: core/kernel.py (execute_tool, freeze, _LatchedNext), core/registry.py (NullToolPort, resolve_tool), core/schemas.py (CapabilityResult, ToolCallContext), core/events.py (EventBus.publish), core/state.py, core/session.py, observability/event_log.py + inspect.py, run_smoke.py. Tham chieu plans/260626-1358-clone-hex-agent-roadmap/phase-1-microkernel-chokepoint.md. Tra 'Relevant files' + 'Open questions'." | `plans/reports/<scope>-<YYMMDD-HHMM>-<slug>-report.md` | Dinh vi file/anchor truoc khi plan |
| 4 | `hs:plan` `/hs:plan hard --tdd` | "Lap plan TDD cho Phase 1 (E01+E04, I1-I4) tu roadmap plans/260626-1358-clone-hex-agent-roadmap/phase-1-microkernel-chokepoint.md §3 (B1-B8). Moi phase nho = mot manh chay duoc. AC moi cai la LENH CHAY DUOC: `python run_smoke.py` in CORE_AGENT_SMOKE_OK; `pytest -q tests/test_kernel.py tests/test_trace_ids.py tests/test_observability.py tests/test_state.py tests/test_session.py tests/test_event_concurrency.py` 0 fail; `inspect summary latest` doc duoc. Red-team: tool raise co sap kernel? middleware fail-open chay tool 2 lan? args raw vao JSONL?" | `plans/<YYMMDD-HHMM>-<slug>/plan.md` + `phase-NN-*.md` | Plan co kiem chung, 0 `[UNVERIFIED]` |
| 5 | `hs:plan` (AskUserQuestion) | (review/approve/reject — **reviewer ≠ author**) | `plans/<slug>/artifacts/plan-approval.json` | Cong HUMAN #1: chot plan, `plan_hash` chua troi |
| 6 | `hs:cook` `/hs:cook <abs-plan-path> --phase B4` | "Cook Phase 1 theo plan da duyet, TDD red→green. Bat dau B4 (core/kernel.py::execute_tool): viet test_kernel.py::test_execute_registered_tool + test_unknown_tool_null_fallback TRUOC, do, roi xanh. Giu try/except quanh executor (kernel.py:152) va _LatchedNext one-shot (kernel.py:24-46). KHONG xoa/skip test. Lech plan → STOP hoi." | `plans/<slug>/artifacts/verification.json` (+ `review-decision.json` per-phase) | Thuc thi phase, sinh artifact truy vet |
| 7 | `hs:test` `/hs:test unit` | "Chay suite Phase 1: `python run_smoke.py` (mong CORE_AGENT_SMOKE_OK) + `pytest -q tests/test_kernel.py tests/test_trace_ids.py tests/test_observability.py tests/test_state.py tests/test_session.py tests/test_event_concurrency.py`. Bat ky check FAIL → bao detail that (so passed/failed, exit code)." | `verification.json` (verdict + checks[]) + QA report | Cong 100% pass |
| 8 | `hs:code-review` `/hs:code-review --pending --spec <plan>` | "Review thay doi Phase 1 vs plan. Soat dung I1-I4: moi tool co that su qua execute_tool? freeze co chan use() sau session? StateStore co deep-copy? lineage co vao moi event? Pitfall P1 (args raw vao events.jsonl, kernel.py:125) va P2 (_LatchedNext)." | `plans/<slug>/artifacts/review-decision.json` | Cong review: verdict PASS chinh xac |
| 9-10 | `hs:debug` / `hs:fix` `/hs:debug` → `/hs:fix standard` | "Test <ten> do. Tim root cause + viet failing repro test TRUOC, roi fix RED→GREEN. Vd test_event_concurrency do → kiem EventBus.publish giao detached + deep-copy (events.py:22-29)." | `plans/reports/<slug>-debug-report.md` + `verification.json` | Khi test do: root cause → fix, khong lam yeu test |
| 12 | `hs-mem:remember` `/hs-mem:remember` | "Ghi DEC moi: vi sao mot-cua (chokepoint) + freeze/session, va vi sao _LatchedNext fail-open one-shot. De remember TU sinh so hieu DEC." | `docs/decisions.md` (DEC-N) | Khoa quyet dinh kien truc, khong relitigate |

> So buoc giu khop kernel brief buildLoop. Buoc 3 (`hs-think:brainstorm`) bo qua o phase nay (huong da ro tu roadmap); buoc 11 (`hs:ship`) thuoc cong HUMAN #2 cuoi roadmap, khong chay per-phase. Buoc 12 (`remember`) chay sau cook khi can khoa quyet dinh.

Tham chieu DoD goc: roadmap §7 (`phase-1-microkernel-chokepoint.md:194-211`).

## 3. Artifact: doc & quan ly the nao

Voi MOI artifact o §2 — la gi, doc field nao, "tot/do" trong sao, hanh dong. **Luat nen:** artifact la NGUON, khong phai loi ke; claim khong `file:line`/command → UNVERIFIABLE → loai.

**Report understand** — `plans/reports/<slug>-report.md`.
Doc **Codebase map** (seam/port o dau) + **Unknowns**.
*Tot:* map du de plan, abs-path that, unknowns liet ke ro.
*Do:* con qua nhieu unknown load-bearing → scout sau hon hoac hoi user truoc khi plan.

**Report scout** — `plans/reports/<scope>-<YYMMDD-HHMM>-<slug>-report.md`.
Doc **Relevant files** truoc (input cho plan), roi **Open questions** (dong truoc khi plan).
*Tot:* moi finding neo `file:line` that (vd `kernel.py:106`); open questions co the dong.
*Do:* finding khong `file:line`, hoac `[FALLBACK_INTERNAL]`, hoac path stale → downstream REJECT.
*Hanh dong:* open question load-bearing chua dong → mo rong scope scout, KHONG sang plan.

**plan.md** — `plans/<YYMMDD-HHMM>-<slug>/plan.md`.
Doc frontmatter `status` (chi `approved` + ten nguoi duyet moi cook) → bang **Phases** → **Acceptance (plan-level)** (moi AC la LENH CHAY DUOC) → **Out of scope** → **Locked decisions**.
*Tot:* 0 mau thuan; moi AC chay duoc (vd `pytest ... → 0 fail`); 0 `[UNVERIFIED]`.
*Do:* `status: draft` ma da cook; AC chung chung ("kernel chay dung"); claim khong `file:line`.
*Hanh dong:* AC khong chay duoc → sua plan roi red-team lai; status sai → khong cook.

**plan-approval.json** — `plans/<slug>/artifacts/plan-approval.json`.
Shape `{schema:"plan-approval/v1", plan, plan_hash, file_hashes{plan.md+phase-*.md}, author, reviewer, verdict:"APPROVED", rationale, ts}`.
*Tot:* `verdict=="APPROVED"` + `plan_hash` khop plan.md hien tai → cook duoc.
*Do:* `author==reviewer` (`plan_approval.py` ep luat role); hash lech = plan-drift.
*Hanh dong:* hash lech → duyet lai; author==reviewer → doi reviewer khac, KHONG tu-duyet.

**verification.json** — `plans/<slug>/artifacts/verification.json` (schema `harness/schemas/artifact-verification.json`).
Shape `{stage, plan, actor, ts, checks[]{name,status PASS|FAIL|SKIP,detail}, verdict PASS|PASS_WITH_RISK|BLOCKED}`.
Doc `verdict` → tung `check[].detail`: phai co output that (`pytest → N passed, exit 0` / `CORE_AGENT_SMOKE_OK run_id=...`).
*Tot:* verdict PASS + moi check PASS, detail neo output that.
*Do:* check FAIL bat ky → hard stage chan; verdict PASS ma co check FAIL (gian doi); detail rong = UNVERIFIABLE.
*Hanh dong:* check FAIL → STOP, sua CODE (khong sua artifact), chay lai den moi check PASS.

**review-decision.json** — `plans/<slug>/artifacts/review-decision.json` (schema `harness/schemas/artifact-review-decision.json`).
Shape `{verdict, reviewer, role, rationale, ts, [plan_hash]}`.
*Tot:* `verdict=="PASS"` dung chu; rationale neu da kiem I1-I4 + finding LOW/INFO.
*Do:* `BLOCKED` chan ship; `PASS_WITH_RISK` ≠ ship license; reviewer trung author; rationale chi "LGTM".
*Hanh dong:* ≠PASS → STOP; PASS_WITH_RISK → AskUserQuestion(fix/accept/cancel); BLOCKED → `hs:fix` → re-review ≤3 vong.

**Report debug** — `plans/reports/<slug>-debug-report.md` + failing repro test.
*Tot:* co **failing repro test** that (khong test = debug chua xong).
*Do:* gia thuyet khong repro file:line.
*Hanh dong:* 3+ gia thuyet fail → STOP, xem lai kien truc.

**DEC-N** — `docs/decisions.md` (DEC moi cho `_LatchedNext`/chokepoint, so hieu do `remember` tu sinh). `status:active` = con hieu luc; sticky — khong dao nguoc bang abstract concern khong evidence moi.

**Map AC → test (doc khi review verification.json):** moi AC epic phai co ≥1 test that, neo `file:line`:
- chokepoint chay (I1): `test_kernel.py::test_execute_registered_tool` + `test_unknown_tool_null_fallback` (`test_kernel.py:7,16`).
- event phat (E04): `test_kernel.py::test_events_emitted` (`test_kernel.py:31`); `test_observability.py::test_run_writes_events_and_summary` (`test_observability.py:5`).
- lineage (I4): `test_trace_ids.py::test_envelope_metadata_has_task_and_request_id` (`test_trace_ids.py:32`); `test_task_id_none_without_accept_is_safe` (`test_trace_ids.py:41`).
- state co lap (I3): `test_state.py::test_snapshot_restore_roundtrip` (`test_state.py:5`).
- logging tat → khong ghi: `test_observability.py::test_disabled_logging_writes_nothing` (`test_observability.py:22`).
AC nao khong map duoc test → UNVERIFIABLE, khong dong phase.

## 4. Cong hieu (phai dat moi sang phase ke)

Dieu kien (b): giai thich invariant theo *luat → file·ham → pha ra mat gi*. Checklist — moi muc gan I#:

- [ ] **GIAI THICH duoc I1:** vi sao "mot cua" → chi `AgentKernel.execute_tool` (`kernel.py:106`); pha ra → mat observability+safety+envelope cho *toan bo* call (roadmap §4 `kernel.py:106`).
- [ ] **CHI RA duoc trong code (I1 phu):** try/except quanh executor o `core(req)` (`kernel.py:152,158`) — tool raise tra `kernel_error` envelope, kernel khong sap.
- [ ] **GIAI THICH duoc I2:** `freeze()` (`kernel.py:91`) khoa registry+config truoc session dau; `use()` sau freeze nem (`kernel.py:102`). Pha ra → config sua giua chung, state ro giua run.
- [ ] **CHI RA duoc I3:** `KernelSession` giu `StateStore` rieng; `snapshot/restore` deep-copy (`state.py:21`). Pha ra → hai run alias chung mutable → nhiem cheo.
- [ ] **CHI RA duoc I4:** 6 truong lineage tu `ToolCallContext.event_fields()` (`schemas.py:48`) `setdefault` vao metadata moi envelope (`kernel.py:210-213`). Pha ra → khong truy vet ai goi gi.
- [ ] **CHI RA duoc (envelope dong nhat):** moi call tra `CapabilityResult.as_dict()` 6-khoa (`schemas.py:103`); `from_raw` goi ca dict tho lan envelope (`schemas.py:74`).
- [ ] **CHI RA duoc (observer co lap):** `EventBus.publish` giao detached + deep-copy + nuot loi observer (`events.py:22,29`).
- [ ] **CHI RA duoc (_LatchedNext):** vi sao `nxt` one-shot (`kernel.py:24-46`) chan tool chay 2 lan khi mw advisory raise sau `nxt`; chi `fail_open=True` moi latch (`kernel.py:58`).
- [ ] **CHI RA duoc (thu tu middleware):** dang ky ngoai→trong (`kernel.py:100`), cua boc `reversed` quanh `core` (`kernel.py:193`); giai thich vi sao `timing` do duoc lop trong con `policy` chan som (`bootstrap.py:36-53`).
- [ ] **CHAY duoc:** `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`; `inspect events latest` thay `tool.requested → tool.completed` co `task_id`.

DoD test (dieu kien a) — chay TRONG turn nay, dan output that:
```bash
python run_smoke.py
python -m pytest -q tests/test_kernel.py tests/test_trace_ids.py tests/test_observability.py tests/test_state.py tests/test_session.py tests/test_event_concurrency.py
python -m observability.inspect summary latest
python -m observability.inspect events latest
```

## 5. Quy tac quay lai (rollback bat buoc)

| Trigger CU THE | Hanh dong |
|---|---|
| DoD test DO (vd `test_kernel.py::test_events_emitted` fail) | `/hs:debug` (root cause + failing repro test) → `/hs:fix`. KHONG xoa/skip/lam yeu test. KHONG sang phase ke. |
| `verification.json` co check FAIL | STOP. Sua CODE, khong sua artifact. Chay lai den moi check PASS, verdict PASS. |
| `review-decision.json` verdict ≠ PASS | BLOCKED → `hs:fix` → re-review (≤3 vong). PASS_WITH_RISK → AskUserQuestion(fix/accept/cancel), KHONG coi la ship license. |
| Khong chi ra duoc I1 trong `kernel.py:106` (execute_tool) | Quay lai roadmap §4-§5 (`phase-1-microkernel-chokepoint.md:90-164`), doc bang "class & bien kiem soat" + I1-I4, roi quiz lai. |
| `use()` sau freeze KHONG nem (I2 vo) | Doc lai roadmap §3 B4 + §4 `freeze()` (`kernel.py:91`, `:102`); kiem `_frozen` flag. |
| `test_snapshot_not_affected_by_later_set` do (I3 vo) | Doc roadmap I3 (`README.md:80`) + `state.py:21`; kiem `snapshot/restore` co deep-copy that khong (alias bug). |
| Event thieu `task_id` (I4 vo) | Doc `schemas.py:48` `event_fields()` + `kernel.py:210-213` setdefault; kiem lineage co bi nuot. |
| `test_event_concurrency` do (observer khong co lap) | Doc `events.py:22-29`: kiem `publish` co chup subscriber trong lock roi giao NGOAI lock, moi observer deep-copy rieng, nuot loi observer. |
| Envelope khong dong nhat (caller phai doan hinh dang) | Doc `schemas.py:63,74,103`: kiem `from_raw` goi ca dict tho lan envelope, `as_dict()` luon ra 6-khoa. |
| Tool tra non-dict / metadata mat lineage (P4) | Doc `kernel.py:158` (tool non-dict → kernel_error), `kernel.py:205` (mw non-dict bi bat), `kernel.py:210-213` (lineage setdefault). Dung bo may lop nay. |
| Thay `args` raw nam trong `events.jsonl` (P1, `kernel.py:125`) | Phase 1 chi co `echo` nen con lanh — GHI NHO: dung de qua Phase 3 ma chua redact (`args_digest`). |
| Middleware advisory raise sau `nxt` → tool chay 2 lan (P2 FM-HIGH) | KHONG lam hong `_LatchedNext` (`kernel.py:24-46`): `nxt` one-shot, replay ket qua/exception dau. Chi `fail_open=True` moi latch. |
| Lech plan khi cook | STOP hoi user. Plan drift sau approve → duyet lai qua `plan_approval.py` (reviewer ≠ author). |
| Quiz §6 < diem dau (xem duoi) | KHONG sang Phase 2. Doc lai `phase-1-microkernel-chokepoint.md` §4-§6 + chay lenh tu kiem, quiz lai. |

## 6. Cau hoi kiem tra hieu (tu cham / nho Claude cham)

**Muc dau: dung ≥6/8; BAT BUOC dung Q1-Q4 (I1-I4 cot loi).**

1. **(I1)** Vi sao moi tool phai qua `execute_tool` thay vi goi `executor` truc tiep?
   *Diem phai cham:* mot cua = chi cha observability/safety/envelope mot lan, ap cho *toan bo* call hien tai+tuong lai (`kernel.py:106`); duong tat = mat ca ba [I1].

2. **(I1 phu)** Mot tool `raise RuntimeError` giua chung. Dieu gi xay ra voi kernel va voi envelope tra ve?
   *Diem phai cham:* `core(req)` try/except (`kernel.py:152`) bat → envelope `ok=False, kernel_error=True` (`kernel.py:131,158`); kernel **van song**. Tool KHONG duoc sap kernel [I1].

3. **(I2)** Sau khi `create_root` da chay, ban goi `kernel.use(mw)` — chuyen gi xay ra? Vi sao thiet ke vay?
   *Diem phai cham:* nem RuntimeError vi `freeze()` da set `_frozen` (`kernel.py:91,102`; `session.py:141`). Tach cai-dong-bang khoi cai-thay-doi → khong sua config giua run [I2].

4. **(I4)** Sau mot event log, lam sao biet call nay thuoc task/run nao?
   *Diem phai cham:* 6 truong lineage tu `ToolCallContext.event_fields()` (`schemas.py:48`) `setdefault` vao metadata moi envelope (`kernel.py:210-213`); event mang `run_id/task_id/...` [I4].

5. **(I3)** Hai session chay song song, ca hai sua mot dict trong state. Co nhiem cheo khong? Co che nao chan?
   *Diem phai cham:* khong, vi `StateStore.snapshot/restore` deep-copy (`state.py:21`), moi `KernelSession` co store rieng → khong alias [I3].

6. **(observer)** Mot observer (logger) trong `EventBus` nem exception khi nhan event. Runtime co gay khong?
   *Diem phai cham:* khong — `publish` giao detached, deep-copy rieng moi observer, **nuot** loi observer (`events.py:22,29`).

7. **(P2/_LatchedNext)** Mot middleware advisory goi `nxt` (tool chay) roi `raise`. Co the chay tool lan hai khong?
   *Diem phai cham:* khong — `_LatchedNext` (`kernel.py:24-46`) one-shot, lan goi sau replay ket qua/exception dau, KHONG re-execute. Chi `fail_open=True` moi latch (`kernel.py:58`).

8. **(VAN DUNG)** Ban them mot tool moi `features/example_reverse.py` (cap `reverse`) qua `install(kernel)` giong `echo`. No co **tu co** observability (event log + lineage) khong? Vi sao? Va neu ban goi `kernel.use(reverse_mw)` SAU khi `create_root` da chay thi sao?
   *Diem phai cham:* CO observability — vi no chay qua dung mot cua `execute_tool`, cua da publish `tool.requested/completed` + gan lineage cho *moi* call [I1+I4]. Day la suc manh chokepoint: them tool thu 50 khong dung lai cua (roadmap §8). Dieu kien: phai `install` (dang ky registry + middleware) qua `build_kernel` TRUOC session dau (`bootstrap.py:56`); goi `use()` sau `create_root` se nem RuntimeError vi kernel da `freeze()` (`kernel.py:102`; `session.py:141`) [I2]. → Khong "them tool nong" giua run (P3).

## 7. Prompt cham hieu cho Claude

Copy-dan (dien cau tra loi cua ban vao `[...]`):

```
Toi dang hoc Phase 1 (Microkernel, chokepoint, observability) cua roadmap
plans/260626-1358-clone-hex-agent-roadmap/phase-1-microkernel-chokepoint.md.
Toi tra loi cac cau §6 the nay: [...].
Dua tren invariant I1-I4 (kernel.py:106 execute_tool, kernel.py:91 freeze,
state.py:21 snapshot/restore, schemas.py:48 event_fields) va pitfall P1/P2
(kernel.py:125 args raw, kernel.py:24-46 _LatchedNext), cham toi da hieu chua:
chi tung cho hong (neo file:line), tinh diem /8, va noi ro co nen cho qua
sang Phase 2 khong (luat: ≥6/8 va bat buoc dung Q1-Q4).
```

---

*Dieu huong: ← [Phase truoc (workflow index)](00-curriculum-guide.md) · → [Phase 2 (workflow)](phase-2-build-workflow.md) · Roadmap goc: [phase-1-microkernel-chokepoint.md](../phase-1-microkernel-chokepoint.md)*
