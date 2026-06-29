---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 4 — Workflow build-along: Single-agent graph & resume (SQLite-truth)

> Cap voi: roadmap [phase-4-graph-resume.md](../phase-4-graph-resume.md) · Epic E05 · Invariant I10-I12 · Muc tieu: vua BUILD vua HIEU phase nay qua skill + cong

## 0. Ban se roi phase nay khi

**Build duoc (X):**
- Mot single-agent loop chay task that: `guard → agent → tool → guard → … → finish`, dong lifecycle dung mot lan (`complete_task` HOAC `fail_task`, khong ca hai).
- `resume(kernel, run_id)` sau khi process chet giua chung: chay tiep tu dung node do dang, **khong** lap lai node da chay; doc tu `langgraph.sqlite` chu khong phai `checkpoint.json`.
- Resume mot run **da xong** tra lai outcome cu, **khong** goi LLM lan nua.

**Giai thich duoc (Y):**
- I10 — vi sao `AgentState` chi-primitive + codec mot-special-case (`TaskEnvelope`) lam "resume mien phi" (`graph/state.py:12`, `:42-57`).
- I11 — vi sao SQLite la truth con `checkpoint.json` chi la projection; `run_id == thread_id` la soi day noi (`orchestrator/loop.py:242-269`, `:40-44`).
- I12 — vi sao moi nhanh hoi tu ve `finish`/`fail` va dong dung mot lan (`graph/runtime.py:49-65`, `graph/nodes.py:232`,`:248`).

Cong dong phase = **(a)** DoD test xanh (§7 roadmap: `tests/test_state.py tests/test_resume.py tests/test_lifecycle.py tests/test_orchestrator.py` + `tests_audit/test_graph_resume_matrix.py tests_audit/test_orchestrator_loop_rigor.py`, `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`) **VA** **(b)** quiz §6 ≥6/8, bat buoc dung cac cau ve I10/I11/I12.

---

## 1. Y tuong trien khai kha thi (doc la biet lam gi)

Bon manh, xay theo dung thu tu §3 roadmap. Moi y kem "ra cai gi de biet xong".

**Y1 — `AgentState` + codec (hop dong serializable).** Dung `graph/state.py`:
- `AgentState` la `TypedDict, total=False` (`graph/state.py:12`) — moi field la primitive JSON.
- `encode_session_state` (`graph/state.py:42`) boc `current_task: TaskEnvelope` thanh `{"__task__": task.as_dict()}`; `decode_session_state` (`:51`) dung lai. Day la **special-case duy nhat**.
- `new_agent_state` (`graph/state.py:70`) factory: set `schema_version=2`, `run_id`/`task_id` tu `session.identity`, encode `session.state.snapshot()` vao `session_state`, `route="guard"`, `status="running"`.
- Key `kernel_state` (`graph/state.py:30`) la **migrate-only** tu schema v1.
- *Ra cai gi de biet xong*: `python -c "from graph.state import AgentState; print(AgentState.__total__)"` → `False`; `python -m pytest tests/test_state.py -q` xanh (codec round-trip).

**Y2 — Topology `build_agent_graph` (6 node, 1 ham route).** Dung `graph/runtime.py`:
- So do (`graph/runtime.py:49-65`): `START→guard`; `guard→agent|fail`; `agent→tool|delegate|finish|guard|fail`; `tool→guard|fail`; `delegate→guard|fail`; `finish→guard(bi-chan)|END`; `fail→END`.
- `_route` (`graph/runtime.py:27`) doc `state["route"]`, default `"fail"` (an toan, khong ket im lang). Moi `add_conditional_edges` dung **dung ham nay**.
- Service bind luc `add_node` qua `partial(guard_node, session=session)` (`graph/runtime.py:39`) → kernel/session **khong** vao state.
- `build_agent_graph` nhan `checkpointer=` (None = khong persist) va `delegation_service=` (None = node `delegate` tra `fail`).
- *Ra cai gi de biet xong*: `python -m pytest tests/test_graph.py -q`; doc duoc 2 canh de bo sot — `delegate` la that, `finish→guard` la that (finish gate chan → quay lai guard, khong terminate).

**Y3 — 6 node lifecycle (moi node mot viec).** Dung `graph/nodes.py`. Quy uoc chung: mo bang `_restore_session(state, session)` (`graph/nodes.py:20`), dong bang dict partial-update **luon kem** `route` + `session_state` moi (`_session_snapshot`, `:25`):
- `guard` (`:40`) — step budget gate truoc moi LLM call: `budget.steps >= budget.max_steps` → `route="fail"` + emit `graph.budget_blocked`.
- `agent` (`:51`) — `execute_tool("llm.chat", …)` → `parse_action` → `record_step` (`:84`, chi o day step moi tang) → route theo verb.
- `tool` (`:106`) — `record_tool_call(key)`; `same_tool_exceeded(key)` → `fail`; nguoc lai `execute_tool` → noi envelope → `route="guard"`.
- `delegate` (`:141`) — `delegation_service is None` → `fail`; o phase nay thuong la None.
- `finish` (`:202`) — `check_finish(...)` (`:220`): gate cho qua → `complete_task` (`:232`), `route="end"`; gate chan → quay `guard`.
- `fail` (`:243`) — `fail_task` (`:248`), `route="end"`.
- *Ra cai gi de biet xong*: `python -m pytest tests/test_lifecycle.py -q` (dong lifecycle dung mot lan).

**Y4 — Facade `run`/`resume` + SQLite checkpoint.** Dung `orchestrator/loop.py` + `orchestrator/checkpoint.py`:
- `run` (`orchestrator/loop.py:89`): 3 guard validate chat (`:107`,`:109-111`,`:112`) → `new_agent_state` → `_stream`; `_config` (`:40-44`) dat `thread_id == run_id`.
- `resume` (`:213`) re nhanh bang `checkpoint_db_path(run_id).exists()`. Duong chinh (`:242-269`): `open_checkpointer` → `saver.get_tuple` doc raw → `_restore_persisted_session` (`:184`) → `graph.get_state` → cong chay-tiep `persisted["status"] != "running"` HOAC `not snapshot.next` → `_outcome(persisted)`; nguoc lai `_stream(graph, None, …)` (`graph_input=None` → noi tu checkpoint).
- `open_checkpointer(run_id)` (`orchestrator/checkpoint.py:35`) = `SqliteSaver` per-run; `save_graph_projection` (`:134`) ghi `checkpoint.json` atomic (`{name}.{uuid}.tmp` + `os.replace` duoi `_REPLACE_LOCK`, `:128-130`).
- *Worked trace (crash giua chung, roadmap dong 130)*: run ton 2 step, ghi SQLite sau moi transition, process chet tai `tool` thu 3 → khoi dong lai → `resume(kernel, run_id)` → co SQLite → doc state o step 2, `status=="running"`, `snapshot.next=("tool",)` → stream tiep tu dung node `tool`, **khong** chay lai 2 step dau. Day chinh la dieu `test_crash_after_effect_does_not_replay_effect_on_resume` bao chung.
- *Ra cai gi de biet xong*: chay 1 run roi `ls var/agent_runs/<run_id>/` thay du 4 file (`events.jsonl`, `summary.json`, `langgraph.sqlite`, `checkpoint.json`); `python -m pytest tests/test_resume.py tests/test_orchestrator.py -q`.

---

## 2. Workflow skill-by-skill (vong lap build)

| Buoc | Skill (invoke) | Prompt mau (copy-duoc, path that) | Artifact ra (path that) | Muc dich |
|---|---|---|---|---|
| 1. Hieu vung code | `hs:understand` | `/hs:understand graph/ orchestrator/` — sau do: "Map quan he giua graph/state.py, graph/runtime.py, graph/nodes.py, orchestrator/loop.py, orchestrator/checkpoint.py. Tra loi: state primitive di vao SQLite o dau, resume doc tu dau (loop.py:242-269), va vi sao service khong vao state (partial bind o runtime.py:39)." | `plans/reports/<slug>-<YYMMDD-HHMM>-report.md` | Co ban do truoc khi cham vao code |
| 2. Dinh vi file/anchor | `hs:scout` | `/hs:scout` — "Dinh vi cho thuc thi Phase 4 E05: AgentState + codec (graph/state.py:12,:42-57), build_agent_graph topology (graph/runtime.py:49-65), 6 node lifecycle (graph/nodes.py), run/resume (orchestrator/loop.py:89,:213), open_checkpointer + save_graph_projection (orchestrator/checkpoint.py:35,:134). Liet ke Relevant files + Open questions ve schema_version migrate va run_id==thread_id." | `plans/reports/<scope>-<YYMMDD-HHMM>-<slug>-report.md` | Co "Relevant files" + dong "Open questions" truoc khi plan |
| 3. Ban huong (tuy chon) | `hs-think:brainstorm` | `/hs-think:brainstorm "Resume nen doc truth tu langgraph.sqlite (saver.get_tuple) hay tu checkpoint.json projection?" --critique` | `plans/reports/<slug>-<YYMMDD-HHMM>-brainstorm-report.md` | Khoa I11 bang trade-off co evidence file:line; chot SQLite |
| 4. Lap plan kiem chung | `hs:plan` | `/hs:plan hard --tdd` — "Plan Phase 4 E05 theo phase-4-graph-resume.md §3 (4 buoc: AgentState+codec → topology → 6 node → facade run/resume). Acceptance (lenh chay duoc) gom: `python -m pytest tests/test_state.py tests/test_resume.py tests/test_lifecycle.py tests/test_orchestrator.py -q`; `python -m pytest tests_audit/test_graph_resume_matrix.py tests_audit/test_orchestrator_loop_rigor.py -q`; `python run_smoke.py` in CORE_AGENT_SMOKE_OK. Map moi AC ↔ I10/I11/I12 theo bang §7 roadmap." | `plans/<YYMMDD-HHMM>-<slug>/plan.md` + `phase-NN-*.md` | 0 mau thuan; moi `[UNVERIFIED]` resolved; moi AC la lenh chay duoc |
| 5. **Phe duyet plan (HUMAN #1)** | `hs:plan` | AskUserQuestion [Review/Approve/Reject] — reviewer ≠ author | `plans/<slug>/artifacts/plan-approval.json` | `plan_hash` khop, APPROVED moi duoc cook |
| 6. Thuc thi TDD red→green | `hs:cook` | `/hs:cook <abs-path>/plan.md --phase 1` (lap qua tung phase). Lech plan → STOP hoi. | `plans/<slug>/artifacts/verification.json` (+ `review-decision.json` per-phase) | Suite green 100%; moi AC co evidence file:line; khong lint/type moi |
| 7. Chay & kiem chung test | `hs:test` | `/hs:test unit` roi `/hs:test integration` — bao chung I11/I12: `test_crash_after_effect_does_not_replay_effect_on_resume` (`tests_audit/test_graph_resume_matrix.py:153`), `test_resume_completed_run_does_not_call_llm_again` (`:139`), `test_resume_interrupted_run_continues_from_sqlite_to_completion` (`tests_audit/test_orchestrator_loop_rigor.py:278`). | `verification.json` (verdict + checks[]) + QA report | 100% pass; bat ky check FAIL → hard stage chan |
| 8. Review code (gate) | `hs:code-review` | `/hs:code-review --pending --spec <abs-path>/plan.md` — soi: co object khong-primitive nao len vao `session.state` ngoai codec? Moi nhanh terminal co dong dung mot lan? `thread_id` co luon == `run_id`? | `plans/<slug>/artifacts/review-decision.json` | Verdict **PASS** chinh xac (PASS_WITH_RISK van chan) |
| 9. Tim root cause (khi do) | `hs:debug` | `/hs:debug` — "resume raise FileNotFoundError du run da chay" / "resume chay lai tool da ghi dia lan 2". Tao failing repro test truoc. | `plans/reports/<slug>-debug-report.md` + failing repro | Co failing repro test |
| 10. Fix bug | `hs:fix` | `/hs:fix standard` — RED→GREEN, khong xoa/skip test; regression test viet TRUOC fix. | `verification.json` + bao cao root cause | RED→GREEN, full suite pass, verdict ≠ BLOCKED |
| 11. Ghi quyet dinh | `hs-mem:remember` | `/hs-mem:remember` — chot DEC: "resume = saver.get_tuple, KHONG load_checkpoint; run_id==thread_id" + I10/I11/I12 da hoc. | `docs/decisions.md` (DEC-N) | Khong relitigate sau nay |

Curriculum toi thieu phase nay: **scout(2) → plan(4) → approve(5) → cook(6) → test(7) → review(8)**.

---

## 3. Artifact: doc & quan ly the nao

**Report (scout/understand/brainstorm)** — `plans/reports/<scope>-<YYMMDD-HHMM>-<slug>-report.md`.
- *La gi*: input cho plan/debug. *Doc muc nao*: **Relevant files** truoc (phai co `graph/state.py`, `graph/runtime.py`, `graph/nodes.py`, `orchestrator/loop.py`, `orchestrator/checkpoint.py` voi anchor that), roi **Open questions**.
- *Tot*: moi finding neo file:line; brainstorm co cot Evidence(file:line) + Decision chot 1 huong (SQLite-truth).
- *Do co*: 🔴 finding khong file:line → downstream REJECT; `[FALLBACK_INTERNAL]`; path stale.
- *Hanh dong khi do*: Open questions load-bearing chua dong (vd "resume doc tu dau?") → mo rong scout, chua plan.

**plan.md** — `plans/<YYMMDD-HHMM>-<slug>/plan.md`.
- *Doc field nao*: frontmatter `status` (chi `approved` + ten nguoi duyet moi duoc cook) → bang **Phases** → **Acceptance (plan-level)** (moi AC la LENH CHAY DUOC, vd `python -m pytest tests/test_resume.py -q`) → Out of scope (delegation day du la Phase 6 — node `delegate` o day chi la canh route hop le) → Locked decisions.
- *Tot*: moi AC map ≥1 test theo bang §7 roadmap; 0 `[UNVERIFIED]`.
- *Do co*: 🔴 `status: draft` ma da cook; AC chung chung khong chay duoc; claim khong file:line.
- *Hanh dong*: red-team co repro file:line → sua plan roi red-team lai.

**plan-approval.json** — `plans/<slug>/artifacts/plan-approval.json`.
- *Shape*: `{schema:"plan-approval/v1", plan, plan_hash, file_hashes{plan.md+phase-*.md}, author, reviewer, verdict:"APPROVED", rationale, ts}`.
- *Doc*: `verdict=="APPROVED"` + `plan_hash` khop plan.md hien tai ⇒ cook duoc.
- *Do co*: 🔴 `author==reviewer` (`plan_approval.py` ep luat role); hash lech = plan-drift.
- *Hanh dong*: drift → duyet lai qua `plan_approval.py` (reviewer ≠ author).

**verification.json** — `plans/<slug>/artifacts/verification.json` (schema `harness/schemas/artifact-verification.json`).
- *Shape*: `{stage, plan, actor, ts, checks[]{name,status PASS|FAIL|SKIP,detail}, verdict PASS|PASS_WITH_RISK|BLOCKED}`.
- *Doc*: verdict → tung check[]: `detail` phai co output that — vd `pytest tests/test_resume.py → N passed, exit 0`, `CORE_AGENT_SMOKE_OK run_id=…`, hoac commit SHA.
- *Do co*: 🔴 bat ky check FAIL → hard stage chan; verdict PASS ma co check FAIL (gian doi); detail rong = UNVERIFIABLE.
- *Hanh dong*: check FAIL → STOP, sua code KHONG sua artifact, chay lai den moi check PASS.

**review-decision.json** — `plans/<slug>/artifacts/review-decision.json` (schema `harness/schemas/artifact-review-decision.json`).
- *Shape*: `{verdict, reviewer, role, rationale, ts, [plan_hash], [ticket_id]}`.
- *Doc*: `verdict=="PASS"` dung chu moi la ship license; rationale neu da kiem gi (vd "khong object nao len session.state ngoai codec; moi nhanh dong mot lan").
- *Do co*: 🔴 BLOCKED chan ship; PASS_WITH_RISK ≠ ship license; reviewer trung author; rationale chi "LGTM".
- *Hanh dong*: ≠PASS → STOP; PASS_WITH_RISK → AskUserQuestion(fix/accept/cancel); BLOCKED → `hs:fix` → re-review (≤3 vong).

**Run artifact (dau ra cua chinh phase, KHONG phai harness)** — `var/agent_runs/<run_id>/`.
- *La gi*: 4 file `events.jsonl`, `summary.json`, `langgraph.sqlite` (**truth**), `checkpoint.json` (**projection cho UI**).
- *Doc*: debug resume = doc `langgraph.sqlite` + `events.jsonl`, KHONG sua tay `checkpoint.json` (`orchestrator/checkpoint.py:139` docstring noi thang "Resume intentionally does not call this function").
- *Do co*: thieu `langgraph.sqlite` ma resume → `FileNotFoundError`; co `checkpoint.json` ma khong co sqlite = run legacy (duong migrate `orchestrator/loop.py:146-181`).
- *Hanh dong*: `var/` gitignored — khong commit.

**Map test ↔ invariant (doc khi `verification.json` checks[] tham chieu, roadmap §7).** Moi check phai neo dung test nay:

| Test (file:line) | Bao chung | Invariant |
|---|---|---|
| `tests/test_state.py` | codec round-trip + serializable contract | I10 |
| `tests/test_resume.py`, `tests/test_lifecycle.py` | resume qua restart; dong lifecycle 1 lan | I11, I12 |
| `tests/test_orchestrator.py` | facade run/resume hanh xu dung | I11, I12 |
| `test_resume_completed_run_does_not_call_llm_again` (`tests_audit/test_graph_resume_matrix.py:139`) | resume run da xong KHONG goi LLM lai | I11 |
| `test_crash_after_effect_does_not_replay_effect_on_resume` (`:153`) | resume KHONG replay side-effect | I11 |
| `test_resume_interrupted_run_continues_from_sqlite_to_completion` (`tests_audit/test_orchestrator_loop_rigor.py:278`) | noi tiep tu SQLite toi hoan tat | I11 |
| `test_run_checkpoint_on_writes_sqlite_and_langgraph_projection` (`:89`) | bat checkpoint ghi ca SQLite + projection | I11 |
| `test_resume_reproduces_task_identity_across_process_boundary` (`:307`) | identity giu nguyen qua restart | I11 |

---

## 4. Cong hieu (phai dat moi sang phase ke)

Checklist dieu kien (b). Moi muc gan invariant: ban phai GIAI THICH / CHI RA trong code / CHAY duoc.

- [ ] **I10** — GIAI THICH duoc: vi sao `AgentState` chi-primitive lam "luu/khoi phuc = sao chep khong mat mat"; CHI RA `encode_session_state` (`graph/state.py:42`) boc `TaskEnvelope` la special-case duy nhat; CHAY `python -c "from graph.state import AgentState; print(AgentState.__total__)"` → `False` va `tests/test_state.py` xanh.
- [ ] **I11** — CHI RA `resume` doc `saver.get_tuple` (`orchestrator/loop.py:242-249`) chu khong `load_checkpoint`; CHI RA `run_id == thread_id` o `_config` (`:40-44`); CHAY `test_crash_after_effect_does_not_replay_effect_on_resume` (`tests_audit/test_graph_resume_matrix.py:153`) + `test_resume_completed_run_does_not_call_llm_again` (`:139`) xanh.
- [ ] **I12** — CHI RA `complete_task` chi o `finish_node:232`, `fail_task` o `finish_node:211` + `fail_node:248`; GIAI THICH moi nhanh ve `finish`/`fail` dong dung mot lan, `_route` default `"fail"` (`graph/runtime.py:28`) khong ket im lang; CHAY `tests/test_lifecycle.py` xanh.
- [ ] **I11 (projection atomic)** — GIAI THICH duoc vi sao `save_graph_projection` ghi temp ten-duy-nhat-per-write roi `os.replace` duoi `_REPLACE_LOCK` (`orchestrator/checkpoint.py:128-130`): reader luon thay **mot** JSON hop le, khong bao gio nua voi, ke ca khi nhieu run ghi song song; CHAY `test_json_projection_same_run_concurrent_writes_remain_atomic_and_valid` (`tests_audit/test_graph_resume_matrix.py:192`) xanh.
- [ ] **I7 (lien quan, budget)** — CHI RA `record_step` chi o `agent_node` (`graph/nodes.py:84`) → budget dem **action hop le**, parse loi khong ton step; guard chan truoc moi LLM call (`graph/nodes.py:40`).
- [ ] **DoD tong** — CHAY full: `python -m pytest tests/test_state.py tests/test_resume.py tests/test_lifecycle.py tests/test_orchestrator.py tests_audit/test_graph_resume_matrix.py tests_audit/test_orchestrator_loop_rigor.py -q` 0 fail; `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`. Da vao `verification.json` verdict PASS + moi check PASS, detail neo output that.

Khong giai thich duoc bat ky I10/I11/I12 nao theo *luat → file·ham → pha ra mat gi* → CHUA dat (b), khong sang Phase 5.

> Mau cau tra loi dat chuan (I11): "Luat: resume doc truth tu SQLite. File·ham: `orchestrator/loop.py:242-269` (`saver.get_tuple`), `run_id==thread_id` o `:40-44`. Pha ra mat gi: doc nham `checkpoint.json` (projection ghi *sau* transition) → mat tien trinh hoac chay lai node side-effect." Tra loi thieu mot trong ba ve → chua dat.

---

## 5. Quy tac quay lai (rollback bat buoc)

| Trigger cu the | Hanh dong |
|---|---|
| Khong chi ra duoc resume doc SQLite o `orchestrator/loop.py:242-269` (chi ra nham `checkpoint.json`) | Quay lai buoc 1 (`hs:understand`), doc lai roadmap §3 Buoc 4 + §5 + I11; KHONG sang phase ke |
| `test_crash_after_effect_does_not_replay_effect_on_resume` DO (resume chay lai side-effect) | `/hs:debug` (root cause: nham projection la truth? `graph_input` khong None?) → `/hs:fix`, KHONG xoa/skip test |
| `resume` raise `FileNotFoundError: No checkpoint for run_id=…` | `/hs:debug` — kiem `thread_id == run_id` o `_config` (`:40-44`); dung sinh ID moi o resume; sua roi re-run |
| resume mot run cu khoi phuc state **lech field** (khong crash, chi sai) | Quay lai §6 pitfall roadmap "doi shape state quen bump schema_version" — bump `schema_version` (`graph/state.py:82`) + them nhanh doc key cu trong codec/`_restore_session` (`graph/nodes.py:21` co fallback `session_state or kernel_state` lam mau) |
| run khong terminate (dung `recursion_limit`) HOAC `complete_task`/`fail_task` chay 2 lan | `/hs:debug` — node tra `route` khong khai bao trong `add_conditional_edges`, hoac nhanh khong ve `finish`/`fail`; sua topology (`graph/runtime.py:49-65`) |
| DoD test bat ky DO | `/hs:debug` roi `/hs:fix`; regression test viet TRUOC fix; KHONG sang phase ke khi chua xanh |
| `verification.json` co check FAIL nhung verdict PASS | STOP — gian doi artifact; sua code (KHONG sua artifact), chay lai den moi check PASS |
| review verdict ≠ PASS | PASS_WITH_RISK → AskUserQuestion(fix/accept/cancel); BLOCKED → `hs:fix` → re-review ≤3 vong |
| Quiz §6 < 6/8, hoac sai cau ve I10/I11/I12 | Doc lai `phase-4-graph-resume.md` §3-§6 + bang I# README §2 + artifact run, chay lenh tu kiem chung, quiz lai |
| Lech plan khi cook | STOP hoi. Plan drift sau approve → duyet lai qua `plan_approval.py` (reviewer ≠ author) |

---

## 6. Cau hoi kiem tra hieu (tu cham / nho Claude cham)

Muc dau: **≥6/8**, bat buoc dung cac cau 1, 3, 5 (I10/I11/I12 cot loi).

1. **(I10)** Vi sao moi field cua `AgentState` phai primitive, va dieu gi xu ly truong hop `current_task` la `TaskEnvelope`?
   - *Diem phai cham*: SQLite checkpointer chi serialize primitive; `AgentState` la `TypedDict total=False` (`graph/state.py:12`). Special-case duy nhat: `encode_session_state` boc `{"__task__": task.as_dict()}` (`:42`), `decode_session_state` dung lai (`:51`). Nhet object thuong ngoai codec → resume vo am tham. (I10)

2. **(I7/budget)** Step budget tang o node nao, va vi sao parse loi KHONG ton step?
   - *Diem phai cham*: `record_step` chi o `agent_node` (`graph/nodes.py:84`), goi sau khi `parse_action` OK. Parse loi → `record_parse_error` rieng, route ve `guard` (thu lai). Budget dem **action hop le**. (I7)

3. **(I11)** `resume(kernel, run_id)` doc state tu dau? `checkpoint.json` dung de lam gi?
   - *Diem phai cham*: doc `langgraph.sqlite` qua `open_checkpointer` + `saver.get_tuple` (`orchestrator/loop.py:242-249`); `checkpoint.json` chi la **projection cho UI**, `load_checkpoint` co docstring "Resume intentionally does not call this function" (`orchestrator/checkpoint.py:139`). (I11)

4. **(I11)** Soi day nao noi mot run voi checkpoint cua no qua restart? Doi no thi sao?
   - *Diem phai cham*: `run_id == thread_id`, dat o `_config` (`orchestrator/loop.py:40-44`). Doi → LangGraph khong tim thay thread → `FileNotFoundError`. (I11)

5. **(I12)** Co bao nhieu cho goi `complete_task`/`fail_task`, va lam sao bao dam khong dong 2 lan?
   - *Diem phai cham*: `complete_task` chi o `finish_node:232`; `fail_task` o `finish_node:211` + `fail_node:248`. Moi nhanh terminal ve `finish`/`fail`, route `"end"` → END. `_route` default `"fail"` (`graph/runtime.py:28`) → khong ket im lang. (I12)

6. **(I11/resume)** Resume mot run da `status="completed"` lam gi? Co goi LLM khong?
   - *Diem phai cham*: cong chay-tiep `persisted["status"] != "running"` HOAC `not snapshot.next` → `return _outcome(persisted)`, KHONG `_stream` → khong goi LLM. Bao chung: `test_resume_completed_run_does_not_call_llm_again` (`tests_audit/test_graph_resume_matrix.py:139`). (I11)

7. **(topology)** `finish → guard` co that khong? Khi nao xay ra?
   - *Diem phai cham*: that (`graph/runtime.py:49-65`). Khi `check_finish` gate `allowed=False` (vd doi code chua validate) → noi ly do + `route="guard"` + emit `graph.finish_blocked` → quay lai lam tiep, KHONG terminate. (I12)

8. **(VAN DUNG)** Ban them mot field moi `retries: list[dict]` vao `session.state`. No co tu dong resume dung khong? Vi sao? Phai lam gi?
   - *Diem phai cham*: `list[dict]` la primitive JSON → resume duoc **neu** chi chua primitive. Nhung doi shape state ⇒ phai bump `schema_version` (`graph/state.py:82`) + viet test resume cho field moi; neu field chua object khong-primitive thi phai mo rong `encode/decode_session_state`. Khong tu dong "mien phi" — chi mien phi khi giu dung hop dong serializable. (I10)

---

## 7. Prompt cham hieu cho Claude

```
Toi tra loi the nay:
[1] AgentState chi-primitive vi: ___
[3] resume doc tu: ___  ; checkpoint.json de: ___
[5] complete_task/fail_task o cac cho: ___ ; khong dong 2 lan vi: ___
[8] (van dung) them field retries: ___

Dua tren Phase 4 (plans/260626-1358-clone-hex-agent-roadmap/phase-4-graph-resume.md),
invariant I10-I12 va bang §7 DoD, cham toi da hieu chua. Voi MOI cau:
- chi ro toi sai/thieu o dau, neo file:line that (graph/state.py, graph/runtime.py,
  graph/nodes.py, orchestrator/loop.py, orchestrator/checkpoint.py);
- map cau tra loi ve I10/I11/I12;
- ket luan CHO QUA hay KHONG (nguong >=6/8, bat buoc dung cau 1,3,5).
Neu chua dat, chi ra muc roadmap toi phai doc lai truoc khi sang Phase 5.
```

---

← phase truoc workflow: [phase-3-build-workflow.md](phase-3-build-workflow.md) · → phase sau workflow: [phase-5-build-workflow.md](phase-5-build-workflow.md) · Roadmap goc: [phase-4-graph-resume.md](../phase-4-graph-resume.md)
