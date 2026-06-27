---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 6 — Workflow build-along: Roles & Multi-agent delegation
> Cap voi: roadmap [phase-6-roles-delegation.md](../phase-6-roles-delegation.md) · Epic E09+E10 · Invariant I13-I15 · Muc tieu: vua BUILD vua HIEU phase nay qua skill + cong

## 0. Ban se roi phase nay khi

**Build duoc (X):** `python -m pytest -q` xanh het 79 test cua phase (DoD §7 roadmap): `tests/test_roles.py`(14), `tests/test_delegation.py`(6), `tests/test_supervisor_loop.py`(8), `tests/test_supervisor_resume.py`(3), `tests/test_supervisor_llm.py`(5), `tests/test_acceptance_gate.py`(9), `tests/test_evidence.py`(9), cong 3 file `tests_audit/*` adversarial (11+3+11). Cu the:
- Mot role = mot file yaml; `AgentRegistry.build_agent` dung *cung* mot `RoleSpec` cho ca single (Phase 4) lan multi.
- `DelegationManager.delegate` (`manager.py:63`) la cua delegation RIENG — co `delegation.started/progress/finished`, co `policy.validate`, mo child session scope ⊆ cha.
- Agent O loop: `compose_team → o_decide → run_round → judge_acceptance` chay LLM that (`supervisor/llm.py`), pass chi khi cited id resolve + ≥1 evidence that.
- Resume tu SQLite Blackboard, identity-check khoa run lung.

**Giai thich duoc (Y):** ba van co hoc cua phase theo cong thuc *luat → file·ham → pha ra mat gi*:
- **I13** delegation la chokepoint rieng, KHONG co `kernel.delegate()`.
- **I14** scope con ⊆ scope cha, kiem hai lop (`policy.py:26` + `core/session.py:163`).
- **I15** O khong pass bang gian giao cua chinh no (`judge_acceptance` + `NON_EVIDENCE_KINDS`).

Thieu mot trong hai (test do HOAC khong giai thich duoc invariant) → CHUA qua, doc lai §4 + §5.

Lenh tu kiem chung (gate (a) cua giao thuc cong — chay TRONG turn, khong tin loi ke):
```bash
python -m pip install -e ".[dev]"
python run_smoke.py            # → CORE_AGENT_SMOKE_OK (no LLM/network)
python -m pytest -q            # → 0 fail (79 test phase + suite cu)
```

## 1. Y tuong trien khai kha thi (doc la biet lam gi)

Tam y, neo class/ham/bien that, theo dung day phu thuoc roadmap §3: roles (B1-B4) → delegation (B5-B7) → adapter (B8) → supervisor state/nodes/evidence/checkpoint/llm (B9-B15). Moi y kem "ra cai gi de biet xong".

**Y1 — Role suy allowlist o MOT cho, forbidden thang.**
`RoleSpec` la frozen dataclass; trai tim la `allowed_tools(skills, core_tools)` (`spec.py:53`): `union(explicit_tools, core_tools, tool skill khai)` **tru** forbidden cua skill, forbidden THANG (`spec.py:63`). Day la cho duy nhat skill (Phase 5) gap role. `Agent.__init__` lam fail-fast separation-of-duties: role `owns_validation==False` ma khong khai `must_handoff_to` → raise ngay khi dung (`agent.py:31`).
`AgentRegistry.build_agent` (`registry.py:60`) la cho ca single (Phase 4) lan multi (phase nay) dung Agent — mot role co dung mot `RoleSpec`, khong hai catalog troi lech (S09.6). `parse_role` raise `ValueError` neu thieu field, neu ten file.
→ Ra cai gi de biet xong: load `roles/library/code.yaml`, `allowed_tools` chua `fs_read` nhung KHONG chua tool skill `file_edit` cam; bo `must_handoff_to` → dung Agent no ngay.

**Y2 — Allowlist enforce ngay tai agent, khong doi kernel.**
Hai guard loop goi: `guard_tool_call(tool)` tra envelope `finish_reason=="blocker"` + `may_route_to` neu tool ngoai allowlist (`agent.py:45`); `guard_finish(claim_validated)` ep `handoff_to` neu role khong own validation ma doi tu dong dau "da validate" (`agent.py:56`).
→ Ra cai gi: dung Agent tu `code.yaml`; `guard_tool_call("rm_rf")` tra dict co `finish_reason=="blocker"`; `guard_finish(claim_validated=True)` tra `handoff_to=="test"`.

**Y3 — Delegation la cua thu hai, song song execute_tool.**
`DelegationManager.delegate(parent, target, spec, policy)` (`manager.py:63`) la chokepoint. Trinh tu (`manager.py:63-192`):
- chan parent inactive / target rong / objective rong;
- `policy.validate` (loi → ghi request "rejected" roi `_finish`, VAN vao store + event, KHONG nuot im);
- `registry.resolve` → `sessions.create_child(requested_scope=active_policy.allowed_capabilities)` → set `delegation_policy` len child state;
- `handler.run(request, child, progress_sink)`; `progress_sink` kiem `delegation_id` khop + `sequence <= max_steps`, **append store TRUOC, publish event SAU** (`manager.py:147`);
- cuoi: gop artifact (progress truoc, result-only sau, khu trung theo `artifact_id`), dong child (`complete_task`/`fail_task`), `_finish` publish `delegation.finished`.

Cai van scope: `DelegationPolicyEngine.validate` (`policy.py:13`) kiem `max_steps`/`max_depth` trong bien → `parent.depth + 1 <= max_depth` → `scope = requested.allowed_capabilities or parent.allowed_capabilities` → kiem `scope <= parent.allowed_capabilities` (`policy.py:26`), khong subset → `PermissionError`.
→ Ra cai gi: delegate scope vuot cha → `outcome=="rejected"`, error "scope exceeds"; delegate hop le → `outcome=="success"`, store progress dung thu tu; `max_depth=0` → `ValueError`; parent depth = max_depth → `PermissionError`.

**Y4 — Acceptance gate honor evidence, ≥1-valid khong all-valid.**
`judge_acceptance` (`graph.py:238`) honor `passed` chi khi **moi** id cited resolve tren Blackboard **VA ≥1** id co `evidence_type_of != None`. `evidence_type_of(artifact)` (`evidence.py:26`) suy loai tu `artifact.kind` theo ba nhanh:
- rong **hoac** ∈ `NON_EVIDENCE_KINDS` → `None` (scaffolding hoac vo danh);
- ∈ `{artifact, tool_result, reviewer_report, diff, test_result}` → chinh no (evidence co loai);
- worker kind la + `delegation_result` → `"artifact"` (evidence generic, trust-worker).

`NON_EVIDENCE_KINDS={session_plan, context_packet, ac_report}` (`evidence.py:23`) — dung ba thu loop tu de ra ve chinh no (ke hoach team / goi briefing / bao cao AC). `record_ac_report` (`evidence.py:60`) chup AC thanh `kind=ac_report` (id `ac_report-{session_id}` → idempotent qua resume) → vi ac_report ∈ NON_EVIDENCE → khong tu lam evidence cho chinh no. Threat model DEC-7: moi nguy la O TRICH NHAM scaffolding, KHONG phai worker thu dich — nen worker kind la van tin la `artifact`.
Verdict bao cao co BA nhanh, khong nhi phan: `_overall_verdict` (`evidence.py:46-56`) gan `passed_with_risk` khi MOI AC pass nhung ≥1 AC tua DUY NHAT vao evidence kind `artifact` generic (khong co `STRONG_EVIDENCE_TYPES = diff/test_result/tool_result/reviewer_report`). Day la read-model label, KHONG phai gate: decision FINISHED van la `all_accepted` (`state.py`) — nhung verdict report bi ha mot bac de bao "pass nhung mong bang chung".
→ Ra cai gi: AC cite chi mot `session_plan` id → van `pending`; cite `diff` id + `context_packet` id → `passed` (≥1-valid, diff la strong); cite chi `delegation_result`/worker kind la (suy ve `artifact` generic) → all pass nhung report `passed_with_risk`; cite id khong ton tai → `pending` (all-exist fail).

**Y5 — Worker = graph Phase 4, de quy delegation TAT.**
`LangGraphDelegationAgent(target)` (`adapters/agents/langgraph_agent.py`) implement `DelegationPort`: `can_handle` so ten, `run` dung `AgentState` moi cho child session, build graph Phase 4 voi `build_agent_graph(..., delegation_service=None)` — **de quy tat o v1** (worker khong tu goi worker, O la delegator duy nhat). Stream tung step, emit `ArtifactEnvelope(kind="agent_step")` qua `progress_sink`. `bootstrap.create_delegation_service` chi wire khi `config["delegation"]["enabled"]`.
→ Ra cai gi: delegate qua adapter voi objective don gian → `result.summary["child_session_id"]` khac parent.

**Y6 — Scope worker CHI tu O, Broker khong bao gio set scope.**
`AgentAssignment.allowed_capabilities` la cho DUY NHAT scope worker duoc dat. `ContextPacket` (Broker viet) **khong co field scope** (`contracts.py:59`, `to_spec` khong map scope). Trong `run_round`: authority check toan batch truoc (assignment phai target agent da compose — `graph.py:142-148`), roi moi assignment: Broker viet packet → kiem `packet.target == assignment.agent_id` (Broker khong duoc doi huong) → `DelegationPolicy(allowed_capabilities=assignment.allowed_capabilities)` (scope CHI tu O — `graph.py:176`, comment neo `:175`) → `delegation_service.delegate` → checkpoint sau moi turn. Broker SHAPE thong tin, O SHAPE quyen — hai vai tach bach.
→ Ra cai gi: assignment toi agent chua compose → `run_round` raise `PermissionError`; Broker tra packet target lech → raise `PermissionError`.

**Y7 — Blackboard serializable + checkpoint SQLite = chan ly resume.**
`TaskLoopState` (`state.py`) la dataclass mutable nhung **moi field serializable**: `selected_agents: list[str]`, `acceptance_checks`, `turns`, `artifacts: dict[str,dict]`, `tool_results`, `final_output`. `encode/decode_taskloop_state` round-trip qua JSON. `SqliteTaskLoopStore(run_id)` (`checkpoint.py`): `run_id` phai la MOT path segment (path-like → `ValueError`, chan escape khoi `runs_dir`); `save` upsert vao mot row, `load` decode hoac `None`. `resume_task_loop` (`loop.py:108`): load state → identity-check (`session_id`+`task_id` khop — `loop.py:128`) → neu terminal tra luon, nguoc lai `_drive` tiep; `run_round` skip agent da co turn trong round.
→ Ra cai gi: `decode(encode(s)) == s` ve noi dung; resume tu session khac identity → `ValueError`; resume dung session → tiep tu round dang do.

**Y8 — Loop-guard co hoc tach roi O (`loop.py`).**
`_drive` lap: check `max_rounds` → `o_decide` → route theo `decision.decision` (finished→judge+`all_accepted`→record_ac_report→terminate; need_tool→run_tool+judge; continue→run_round+judge; blocked/failed→terminate). Loop-guard KHONG tin O: terminate neu het `max_rounds`, neu mot round khong tien trien (artifact + acceptance snapshot khong doi — `loop.py:193`), hoac O lap y het decision qua `max_decision_repeats`. Checkpoint o moi round boundary.
→ Ra cai gi: O luon tra `continue` ma khong sinh artifact → loop terminate `BLOCKED "no progress"`, khong treo vo han.

## 2. Workflow skill-by-skill (vong lap build)

Bam buildLoop kernel: understand/scout → brainstorm/plan → critique → cook TDD → test → code-review → debug/fix → remember. Prompt copy-dan-duoc, tham chieu path THAT cua phase.

Cook chia ba lan (6/6b/6c) bam dung day phu thuoc roadmap §3: `roles/` truoc (khong phu thuoc gi trong phase) → `delegation/` (can roles cho scope, doc lap supervisor) → `supervisor/` (can ca hai). Moi lan cook tu kiem offline xong moi sang lan ke; KHONG cook ca ba mot luot.

| Buoc | Skill (invoke that) | Prompt mau dua cho Claude | Artifact ra (path that) | Muc dich |
|---|---|---|---|---|
| 1 | `hs:understand` | `/hs:understand plans/260626-1358-clone-hex-agent-roadmap/phase-6-roles-delegation.md` — "Dung ban do module §2 + dscuong dung phu thuoc §3. Tra ve thu tu xay roles→delegation→adapter→supervisor va 3 chokepoint." | `plans/reports/<slug>-report.md` | Map vung code la truoc khi dong |
| 2 | `hs:scout` | `/hs:scout` — "Dinh vi cho dat 3 van: `delegation/policy.py:26` (scope<=parent), `supervisor/graph.py:238` (judge_acceptance), `supervisor/evidence.py:23` (NON_EVIDENCE_KINDS). Tham chieu roadmap §4 bang neo. Liet ke Relevant files + Open questions." | `plans/reports/<scope>-<YYMMDD-HHMM>-<slug>-report.md` | Co file:line that lam input plan |
| 3 | `hs-think:brainstorm` *(tuy chon)* | `/hs-think:brainstorm "Cong acceptance nen ≥1-valid hay all-valid?" --critique` — "Neo DEC-7 + roadmap §6 pitfall 3-4: all-valid chan oan khi O kem 1 scaffolding id canh evidence that. Moi option co trade-off." | `plans/reports/<slug>-<YYMMDD-HHMM>-brainstorm-report.md` | Chot quantifier co trade-off |
| 4 | `hs:plan` | `/hs:plan hard --tdd` — "Plan E09+E10 theo B1-B15 roadmap §3. Moi AC la lenh chay duoc map ve test DoD §7 (vd `pytest tests/test_acceptance_gate.py` → 9 passed). Phase: roles, delegation, adapter, supervisor-state, nodes, evidence-gate, checkpoint, llm. Red-team I13-I15." | `plans/<YYMMDD-HHMM>-<slug>/plan.md` + `phase-NN-*.md` | Plan kiem chung, 0 mau thuan |
| 5 | `hs:plan` (approve) | AskUserQuestion [Review/Approve/Reject] — reviewer≠author. | `plans/<slug>/artifacts/plan-approval.json` | HUMAN #1, `plan_hash` chua troi |
| 6 | `hs:cook` | `/hs:cook <abs-plan-path> --phase roles` — "TDD red→green. Bat dau B1 `roles/spec.py` `allowed_tools` forbidden-thang, B3 `agent.py:31` fail-fast. Moi AC co evidence file:line. Lech plan → STOP hoi." | `plans/<slug>/artifacts/verification.json` (+ `review-decision.json` per-phase) | Thuc thi phase, suite green |
| 6b | `hs:cook` | `/hs:cook <abs-plan-path> --phase delegation` — "B5 `policy.py:26` scope<=parent (chu y empty-scope=inherit, KHAC create_child empty=deny-all `session.py:160-162`), B7 `manager.py:147` persist-truoc-publish-sau." | `verification.json` | Chokepoint delegation xanh |
| 6c | `hs:cook` ×5 | `/hs:cook <abs-plan-path> --phase supervisor-state` → `--phase nodes` → `--phase evidence-gate` → `--phase checkpoint` → `--phase llm` (tung lan, dung id da khai o buoc 4). "B9 state serializable, B11 nam node, B12 `judge_acceptance graph.py:238` ≥1-valid, B14 `loop.py:128` identity-check resume, B15 `llm.py` O+Broker qua `execute_tool('llm.chat')`." | `verification.json` | Agent O loop xanh |
| 7 | `hs:test` | `/hs:test unit` — "Chay 7 file `tests/*` + 3 file `tests_audit/*` cua DoD §7. 100% pass la gate. Ghi verdict + checks[] detail co output that (vd `pytest -q → 79 passed`)." | `verification.json` (verdict + checks[]) + QA report | 100% pass, check FAIL → hard stop |
| 8 | `hs:code-review` | `/hs:code-review --pending --spec <abs-plan-path>` — "Soat I13 (khong co `kernel.delegate`), I14 (scope check ca 2 lop), I15 (`any(evidence_type_of)` chu khong `all`). Verdict PASS chinh xac moi la ship license." | `plans/<slug>/artifacts/review-decision.json` | Gate review, ≠PASS → STOP |
| 9 | `hs:debug` *(khi do)* | `/hs:debug` — "Test `tests_audit/test_acceptance_evidence_adversarial.py` do. Tim root cause, viet failing repro truoc. Kiem `judge_acceptance` dung `any` hay nham `all`." | `plans/reports/<slug>-debug-report.md` + repro test | Root cause + repro |
| 10 | `hs:fix` *(khi do)* | `/hs:fix standard` — "RED→GREEN. KHONG xoa/skip/lam yeu test. Sua code khong sua artifact. Chay lai full suite." | `verification.json` | RED→GREEN, verdict≠BLOCKED |
| 11 | `hs-mem:remember` | `/hs-mem:remember` — "Ghi quyet dinh: empty-scope inherit (delegation) vs deny-all (create_child); ≥1-valid khong all-valid (DEC-7)." | `docs/decisions.md` (DEC-x) | Khong relitigate |

## 3. Artifact: doc & quan ly the nao

Luat cot loi: artifact la NGUON, khong phai loi ke. Claim khong `file:line`/command → UNVERIFIABLE → loai. Hard stage (push/pr/ship) doi verdict dung chu `"PASS"`; `PASS_WITH_RISK` KHONG phai ship license. Voi MOI artifact o §2:

**Report scout/understand** — `plans/reports/<scope>-<YYMMDD-HHMM>-<slug>-report.md`. Doc **Relevant files** truoc (input plan), **Open questions** sau (dong truoc khi plan). Tot: moi finding neo `file:line` that (vd `policy.py:26`, `graph.py:238`). Do co: finding khong file:line, hoac `[FALLBACK_INTERNAL]`, path stale. Hanh dong khi do: mo rong scout, dong open question load-bearing truoc khi sang buoc 4.

**brainstorm-report** — `plans/reports/<slug>-<YYMMDD-HHMM>-brainstorm-report.md`. Doc cot **Evidence(file:line)** + **Decision**. Tot: moi option (≥1-valid / all-valid) co trade-off do duoc, chot mot huong. Do co: chot thieu trade-off, hoac ≥2 huong khong tach → roi sang `hs-think:bakeoff`.

**plan.md** — `plans/<YYMMDD-HHMM>-<slug>/plan.md`. Doc frontmatter `status` (chi `approved`+ten nguoi duyet moi cook) → bang Phases → **Acceptance (plan-level)** (moi AC la LENH CHAY DUOC, vd `pytest tests/test_delegation.py → 6 passed`) → Out of scope (Departments/Router E12 — park) → Locked decisions. Tot: 0 `[UNVERIFIED]` con mo. Do co: status `draft` ma da cook · AC chung chung khong chay duoc · claim khong file:line. Hanh dong: status draft → khong cook; AC mo → sua plan roi red-team lai.

**plan-approval.json** — `plans/<slug>/artifacts/plan-approval.json`. Shape: `{schema:"plan-approval/v1", plan, plan_hash, file_hashes, author, reviewer, verdict:"APPROVED", rationale, ts}`. Tot: `verdict==APPROVED` + `plan_hash` khop plan.md hien tai + `author != reviewer`. Do co: `author==reviewer` (`plan_approval.py` ep luat role) · hash lech = plan-drift. Hanh dong: hash lech → duyet lai; author==reviewer → doi reviewer.

**verification.json** — `plans/<slug>/artifacts/verification.json` (schema `harness/schemas/artifact-verification.json`). Shape: `{stage, plan, actor, ts, checks[]{name,status PASS|FAIL|SKIP,detail}, verdict PASS|PASS_WITH_RISK|BLOCKED}`. Doc `verdict` → tung `check[]`: `detail` phai co output THAT (`pytest -q → 79 passed, exit 0` / `CORE_AGENT_SMOKE_OK run_id=...`). Tot: verdict `PASS` + moi check `PASS` + moi AC epic co ≥1 test. Do co: bat ky check `FAIL` → hard stage chan (`gate_stage.py` fail-closed, doc tu dia) · verdict `PASS` ma co check `FAIL` (gian doi) · detail rong = UNVERIFIABLE. Hanh dong: check FAIL → STOP, sua code khong sua artifact, chay lai den moi check PASS. Iron Law: khong claim "done/passing" neu chua chay lenh chung minh TRONG turn nay.

**QA report (hs:test)** — di kem `verification.json` o buoc 7. Tot: liet ke tung profile (unit) voi so test pass + thoi gian; chi ro 10 file DoD §7 deu chay. Do co: profile bo sot file `tests_audit/*` (adversarial khong chay = invariant chua duoc ghim). Hanh dong: bo sot → chay lai `hs:test unit` cho het.

**review-decision.json** — `plans/<slug>/artifacts/review-decision.json` (schema `harness/schemas/artifact-review-decision.json`). Shape: `{verdict, reviewer, role, rationale, ts, [plan_hash]}`. Tot: `verdict=="PASS"` dung chu + rationale neu da kiem I13-I15 + finding LOW/INFO. Do co: `BLOCKED` chan ship · `PASS_WITH_RISK` ≠ ship license · `reviewer` trung author · rationale chi "LGTM". Hanh dong: ≠PASS → STOP; PASS_WITH_RISK → AskUserQuestion(fix/accept/cancel); BLOCKED → `hs:fix` → re-review ≤3 vong.

**debug-report** — `plans/reports/<slug>-debug-report.md`. Tot: co failing repro test viet TRUOC fix. Do co: 3+ hypothesis fail → STOP xem lai kien truc.

**DEC-x** — `docs/decisions.md`. Block YAML (`id,status,date,actor,ts,affects`). `status:active` con hieu luc; sticky-decision: khong dao nguoc DEC bang abstract concern khong evidence moi (vd dung lat ≥1-valid thanh all-valid neu khong co red-team moi).

## 4. Cong hieu (phai dat moi sang phase ke)

Sau khi test xanh, ban phai GIAI THICH / CHI RA trong code / CHAY duoc tung muc duoi (dieu kien (b) cua giao thuc cong):

- [ ] **GIAI THICH I13:** vi sao delegation la cua RIENG, khong phai `kernel.delegate()`. Chi ra `DelegationManager.delegate` (`manager.py:63`). Pha ra → mat audit (`delegation.started/finished`) + bypass scope check, kernel `freeze()` phinh ra. (I13)
- [ ] **CHI RA I14 trong code:** dong `scope = policy.allowed_capabilities or parent.allowed_capabilities` + `if not scope <= parent.allowed_capabilities: raise PermissionError` o `policy.py:26`; va lop thu hai `create_child` `core/session.py:163`. Phong thu HAI lop. (I14)
- [ ] **GIAI THICH cam bay empty-scope:** trong delegation, `requested` rong → worker KE THUA nguyen scope cha (`policy.py`); doi lap `create_child` `requested_scope=None`=inherit con `frozenset()` rong=deny-all (`session.py:160-162`). Hai cho hai mac dinh KHAC nhau. (I14)
- [ ] **CHI RA I15 trong code:** `judge_acceptance` (`graph.py:238`) dung `all(e in state.artifacts ...)` (all-exist) VA `any(evidence_type_of(...) is not None)` (≥1-valid). `NON_EVIDENCE_KINDS` (`evidence.py:23`) loai `session_plan/context_packet/ac_report`. Pha ra → O pass bang gian giao chinh no. (I15)
- [ ] **GIAI THICH vi sao ≥1-valid khong all-valid:** all-valid chan OAN khi O kem mot scaffolding id canh evidence that (pitfall 4 roadmap §6); ≥1-valid du ngat chan scaffolding-only, du long khong chan oan trich dan trung thuc. (I15, DEC-7)
- [ ] **CHAY:** `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`; `python -m pytest -q` → 0 fail; rieng `pytest tests_audit/test_acceptance_evidence_adversarial.py -q` xanh (ac_report khong tu lam evidence, AC5). (I15)
- [ ] **CHI RA AgentRegistry single-store:** `build_agent` (`registry.py:60`) chia se single (Phase 4) ↔ multi → mot role mot `RoleSpec`, khong hai catalog troi lech. (S09.6)
- [ ] **CHI RA Blackboard resume:** `TaskLoopState` chi primitive (`state.py`); identity-check `loop.py:128` chan session la nhat Blackboard run khac; `run_round` skip agent da co turn trong round.

**Bang neo phai chi tay duoc (copy tu roadmap §4 — hoc thuoc cho diem):**

| neo | o dau | giu gi |
|---|---|---|
| `Agent.guard_tool_call` | `roles/agent.py:45` | tool ngoai allowlist → blocker, role tu enforce |
| `RoleSpec.allowed_tools` | `roles/spec.py:53-63` | union skill+core, forbidden thang — MOT cho suy scope |
| `AgentRegistry.build_agent` | `roles/registry.py:60` | single & multi cung dung tu MOT store |
| `DelegationManager.delegate` | `delegation/manager.py:63` | chokepoint rieng, khong phai method kernel (I13) |
| `DelegationPolicyEngine.validate` | `delegation/policy.py:26` | `scope <= parent.allowed_capabilities` (I14) |
| `DelegationRegistry.resolve` | `delegation/registry.py:33-35` | >1 match → LookupError mo ho |
| `judge_acceptance` | `supervisor/graph.py:238-249` | passed = all-exist + ≥1-valid evidence (I15) |
| `NON_EVIDENCE_KINDS` | `supervisor/evidence.py:23` | scaffolding khong bao gio tinh la evidence (I15) |
| identity-check resume | `supervisor/loop.py:128` | Blackboard chi resume boi session so huu |

Quiz §6 ≥6/8 va BAT BUOC dung 3 cau ve I13/I14/I15 → moi qua.

## 5. Quy tac quay lai (rollback bat buoc)

| Trigger CU THE | Hanh dong |
|---|---|
| DoD test DO (`pytest -q` co fail) | `/hs:debug` (root cause + failing repro test) → `/hs:fix` (RED→GREEN). KHONG xoa/skip/lam yeu test. KHONG sang phase ke. |
| `verification.json` co check `FAIL` | STOP. Sua CODE khong sua artifact. Chay lai den khi moi check PASS, detail neo output that. |
| review verdict `PASS_WITH_RISK` | AskUserQuestion(fix/accept/cancel). PASS_WITH_RISK ≠ ship license. |
| review verdict `BLOCKED` | `/hs:fix` → re-review, toi da 3 vong. |
| Khong chi ra duoc dong `scope <= parent.allowed_capabilities` o `policy.py:26` | Quay lai buoc 2 (scout) + doc lai roadmap §3 B5 + §4 bang neo. |
| Khong giai thich duoc vi sao ≥1-valid (khong all-valid) | Doc lai roadmap §6 pitfall 3-4 + DEC-7 + `graph.py:238-249`. KHONG sang phase ke. |
| delegation chay nhung khong co `delegation.started/finished` event | Ban da them `kernel.delegate()` hoac goi `handler.run()` thang. Quay ve `manager.py:63`, moi giao viec qua DelegationManager. (roadmap §6 pitfall 1) |
| child lam duoc tool parent khong co quyen | Bo `policy.validate`. Khoi phuc `policy.py:13` + giu `scope <= parent` `policy.py:26`. (pitfall 2) |
| resume nhat nham Blackboard run khac / chay lai turn da xong | Thieu identity-check. Khoi phuc `loop.py:128` + `run_round` skip theo `done_this_round`. (pitfall 5) |
| Lech plan khi cook | STOP hoi. Plan drift sau approve → duyet lai qua `plan_approval.py` (reviewer≠author). |
| 3 lan fix fail / 3+ hypothesis fail | STOP, hoi user, xem lai kien truc. |
| Quiz <6/8 hoac sai cau I13/I14/I15 | Doc lai `phase-6-roles-delegation.md` §4-§5-§6 + artifact, chay lenh tu kiem, quiz lai. |

## 6. Cau hoi kiem tra hieu (tu cham / nho Claude cham)

Muc dau: **≥6/8 dung, va BAT BUOC dung ca 3 cau invariant cot loi (Q2,Q4,Q5).**

**Q1.** Trong so duong `compose_team`, `o_decide`, `run_round`, `judge_acceptance` — cua nao validate scope worker, va scope do DEN TU dau?
*Diem phai cham:* scope check o `run_round` qua `DelegationPolicy(allowed_capabilities=assignment.allowed_capabilities)` (`graph.py:176`); scope CHI tu `AgentAssignment` cua O, KHONG bao gio tu Broker (ContextPacket khong co field scope, `contracts.py:59`). (I14)

**Q2 [invariant].** Vi sao delegation phai la chokepoint RIENG thay vi `kernel.delegate()`? Pha ra mat gi?
*Diem phai cham:* gom ve `manager.py:63` de (a) kernel `freeze()` van nho/bat bien, (b) moi delegation de lai audit `started/progress/finished` + qua `policy.validate`. Tron vao kernel = mat ca hai. (I13)

**Q3.** Trong delegation, O khong khai `allowed_capabilities` (rong). Worker scope la gi? Cau nay khac voi `create_child` the nao?
*Diem phai cham:* delegation rong → worker KE THUA nguyen scope cha (`scope = requested or parent`). `create_child`: `requested_scope=None`=inherit, `frozenset()` rong=deny-all (`session.py:160-162`). Hai mac dinh nguoc nhau. (I14)

**Q4 [invariant].** AC cua O cite hai id: mot `diff` artifact + mot `context_packet`. `judge_acceptance` cho pass khong? Con cite chi mot `session_plan` thi sao?
*Diem phai cham:* diff+context_packet → PASS (all-exist + ≥1-valid: diff la evidence that, context_packet la scaffolding nhung khong sao). Chi session_plan → KHONG pass (0 evidence valid). Quantifier la ≥1-valid khong all-valid. (I15)

**Q5 [invariant].** Tai sao `record_ac_report` de ra `kind=ac_report` ma bao cao do khong bao gio tu lam evidence cho chinh AC?
*Diem phai cham:* `ac_report ∈ NON_EVIDENCE_KINDS` (`evidence.py:23`) → `evidence_type_of` tra `None` → khong dem la evidence. Chong O dong dau bang chinh bao cao cua minh (AC5). (I15)

**Q6.** Khi resume tu SQLite, kiem gi de khong nhat nham Blackboard cua run khac?
*Diem phai cham:* identity-check `loop.py:128` — `session_id`+`task_id` cua checkpoint phai khop supervisor session dang chay, lech → `ValueError`; `SqliteTaskLoopStore` chan `run_id` path-like (`checkpoint.py`); `run_round` skip agent da co turn. (Blackboard truth)

**Q7.** `DelegationRegistry.resolve("x")` co hai handler cung `can_handle("x")`. Tra gi? Vi sao khong chon bua?
*Diem phai cham:* `>1 match → LookupError` mo ho TUONG MINH (`registry.py:33-35`), khong chon bua → tranh giao viec sai target am tham.

**Q8 [VAN DUNG].** Ban them mot role moi `data_analyst` (yaml) `owns_validation: false` nhung QUEN `must_handoff_to`. Dung `build_agent` co chay khong? No co tu co separation-of-duties khong? Vi sao?
*Diem phai cham:* KHONG chay — `Agent.__init__` fail-fast raise ngay (`agent.py:31`) vi viec cua role se khong ai validate. Separation-of-duties la BAT BUOC khai tuong minh, khong tu suy. Day la "thiet ke dam bao bang construction": role la danh tinh, vi pham bi chan luc DUNG chu khong luc chay. (I15-lien quan, S09.6)

## 7. Prompt cham hieu cho Claude

```
Toi tra loi phan cong hieu Phase 6 (Roles & Multi-agent delegation) the nay:

Q2 (I13): [dan cau tra loi cua ban]
Q4 (I15): [...]
Q5 (I15): [...]
Q8 (van dung): [...]

Dua tren plans/260626-1358-clone-hex-agent-roadmap/phase-6-roles-delegation.md
(invariant I13-I15, §4 bang neo, §6 pitfall), cham toi:
1. Moi cau dung/sai/thieu o dau — chi ra file:line ma toi bo sot
   (vd policy.py:26, graph.py:238, evidence.py:23, manager.py:63).
2. Toi co nham ≥1-valid voi all-valid khong? Co nham empty-scope
   delegation (inherit) voi create_child (deny-all) khong?
3. Co nen cho toi qua phase 7 khong? Neu chua, chi dung muc roadmap toi phai doc lai.
Cham nghiem: thieu mot trong I13/I14/I15 la CHUA qua.
```

---
*Dieu huong: ← [Phase 5 workflow](phase-5-build-workflow.md) · → [Phase 7 workflow](phase-7-build-workflow.md) · Roadmap goc: [phase-6-roles-delegation.md](../phase-6-roles-delegation.md)*
