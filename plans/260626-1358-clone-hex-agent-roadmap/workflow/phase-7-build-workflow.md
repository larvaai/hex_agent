---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 7 — Workflow build-along: Realtime control plane
> Cap voi: roadmap [phase-7-control-plane.md](../phase-7-control-plane.md) · Epic E21 · Invariant I16,I17 · Muc tieu: vua BUILD vua HIEU phase nay qua skill + cong

## 0. Ban se roi phase nay khi

Phase nay la **control plane chay ABOVE kernel** giong `supervisor` ngoi tren kernel: no *quan sat* event ma agent phat va *bom* command nguoi gui xuong, ma KHONG *la* logic chay. Cong vao: Phase 6 + observability. Trang thai roadmap: contracts + emitter + redaction + fake backend + read-model **da chay co test**; enforcement quyen + bien envelope thanh duong mac dinh runtime live con **SE LAM** (`phase-7-control-plane.md:48`). Tot nghiep = build duoc X + giai thich duoc Y + biet ranh gioi done/PENDING.

Build duoc (X):
- `control/` chi la dataclass + validation, KHONG mo socket / `open()` / HTTP. Transport song sau `control/ports.py:EventSinkPort`. Dau hieu pha ranh gioi: import `requests`/`socket`/`open()` vao bat ky file `control/` nao → cai do thuoc transport.
- Moi event chui qua DUNG MOT duong: `EventEmitter.emit_event` (`control/emitter.py:53`) — thu tu cung **gate → seq → redact → fan-out**, raise truoc fan-out neu type la.
- `Redactor.apply` (`control/redaction.py:65`) tach `payload` (tho, noi bo) khoi `ui_payload` (mask, cho UI/SSE), **khong mutate** goc (tra ban sao qua `replace`); UI/SSE chi phat `ui_payload`. Mask ~14 secret key (`redaction.py:16`) de quy qua dict AND list.
- Predicate authz tach attribution: `command_needs_human_checkpoint("UpdateAgentPermission", reg)` → True (`control/authz.py:43`), quyet tu `registry.requires_permission` khong tu `issued_by`; `is_permission_escalating` (`authz.py:29`) bat co `can_*` False→True.
- `tools/fake_control_server.py` reuse cung `Redactor`/`parse_command`/`build_snapshot` (DEC-6); stream chi phat event `public`/`ui_safe` (`:99`), `data` luon la `ui_payload`, thieu → `{}` khong raw (`:101`); dedup idempotency theo `(session_id, idempotency_key)` (`:140`).
- `build_snapshot` (`snapshot.py:189`) la read-model UI render — whitelist field scalar + copy dict free-form **chi** tu `ui_payload` da redact (`snapshot.py:251`); resolve gate khi gap `approval.approved/rejected`. Mot snapshot khong bao gio mang secret.
- `RuntimeCheckpoint.with_status` (`checkpoint.py:57`) mot chieu: `waiting`→terminal, tu choi re-resolve. `CommandAck.status` chi `received`/`rejected`, `rejected` thieu ly do → raise (`commands.py:109-134`).
- DoD test xanh: `test_control_contracts.py` (19) + `test_control_emitter.py` (6) + `test_fake_control_server.py` (19) + `test_authz_attribution.py` (7) = 51, + `run_smoke.py` → `CORE_AGENT_SMOKE_OK`. Phu tro: `test_control_snapshot.py`, `tests_audit/test_acceptance_evidence_adversarial.py` (3, cross-ref Phase 6/DEC-7, I15).

Giai thich duoc (Y):
- **I16** — vi sao secret chet o BIEN (mot ham, mot cho) la thuoc tinh cua he, khong phai ky luat tung dev; vi sao `ui_payload` thieu thi gateway tra `{}` chu KHONG fallback raw (`fake_control_server.py:101`); vi sao allowlist visibility (chi `public`/`ui_safe` ra wire) khac denylist 'secret' (denylist de lot `internal`).
- **I17** — vi sao "tu khai minh la O" KHONG leo quyen duoc (quyet boi `requires_permission`+checkpoint, khong boi claim issuer, DEC-8); predicate co nhung enforcement call-site (`command_bridge`) con VANG (PENDING, `phase-7-control-plane.md:183`) — biet ranh gioi done/chua-done, KHONG tuong predicate tu chan.

Chua dat 2 dieu kien tren (xem muc 4) → KHONG sang phase ke (day la 00-curriculum-guide chot cua chuoi 7 phase).

## 1. Y tuong trien khai kha thi (doc la biet lam gi)

Vi sao dung thu tu B0→B6: moi buoc *khoa* mot bat bien roi moi cho buoc sau xay len. Contract khoa hinh dang → registry khoa ten → emitter khoa duong publish → redact khoa bien secret → fake khoa seam → UI xay tren seam da khoa (`phase-7-control-plane.md:56`). Dao thu tu (vd viet UI truoc khi co `TaskLoopSnapshot` dataclass) = seam thanh "lo by-discipline": UI va backend *trong* khop nhung khong gi ep chung khop.

Hai neo cot loi de doc truoc khi cham (verbatim tu source — KHONG bia):

```python
# control/emitter.py:53 — duong publish DUY NHAT, 4 buoc cung
def emit_event(self, event: RuntimeEvent) -> RuntimeEvent:
    spec = self._registry.get(event.event_type)                                 # 1. gate (raise neu la)
    staged = event if event.seq else replace(event, seq=self._seq.next(event.session_id))  # 2. seq
    final = self._redactor.apply(staged, level=spec.visibility)                  # 3. redact
    for sink in self._sinks:                                                     # 4. fan-out
        sink.emit(final)
    return final

# control/authz.py:43 — authz quyet tu registry, KHONG tu issued_by
def command_needs_human_checkpoint(command_type: str, registry: CommandTypeRegistry) -> bool:
    return registry.requires_permission(command_type) in PERMISSION_EDIT_PERMISSIONS
```

**Y1 — Envelope + registry-as-allowlist (B0+B1).**
- Viet `control/events.py:RuntimeEvent` (`events.py:113`, frozen dataclass) TRUOC; validate trong `__post_init__` nen event sai **khong the ton tai** — dung noi toi chuyen publish. Frozen + `as_dict`/`from_dict` khop repo, khong pydantic.
- Roi `event_registry.py` / `command_registry.py` load `config/runtime_event_types.yaml` / `runtime_command_types.yaml`; `assert_known` (`event_registry.py:47`, `command_registry.py:43`) chan ten tu che.
- Registry **mang policy** chu khong chi chan ten: moi event-spec khai `visibility`/`durable`/`redact_for_ui`/`checkpoint_candidate` (`event_registry.py:23` `EventTypeSpec`) — do la ly do emitter biet redact o muc nao; moi command khai `apply_at` + `requires_permission` (vd `UpdateAgentPermission → workflow.modify_permissions`, `runtime_command_types.yaml:27`) — chinh la cho predicate authz moc vao.
- Ra cai gi de biet xong: `RuntimeEvent(event_type="", ...)` raise `ControlContractError`; `registry.assert_known("agent.invented")` raise.

**Y2 — Mot duong publish + redact-at-boundary (B3).**
- Viet `EventEmitter.emit_event` (`control/emitter.py:53`) la duong DUY NHAT, thay `bus.publish(topic, dict)` rai rac. Bon buoc cung: `registry.get(...)` gate → `replace(event, seq=...)` (seq don dieu per-session qua `SessionSeq`) → `redactor.apply(staged, level=spec.visibility)` → `for sink: sink.emit(final)`.
- `Redactor.apply` (`redaction.py:65`) goi `self.redact(event.payload)` roi `replace(event, ui_payload=..., redaction=...)` — `event.payload` goc KHONG bi sua; mask ~14 key (`redaction.py:16`) de quy qua dict AND list, tra ban sao.
- Ra cai gi de biet xong: `Redactor().apply()` khong doi `event.payload` goc; emit event type la → raise TRUOC khi cham sink dau tien.

**Y3 — Authz predicate tach attribution (DEC-8, I17).**
- Viet `control/authz.py`: `is_permission_escalating(current, patch)` bat co `can_*` False→True (`authz.py:29`). Downgrade/no-op re-grant KHONG la escalation; known gap: chi soat boolean `can_*`, widening `allowed_tools` rang buoc o `SessionFactory.create_child` (khong doc day la "full authz").
- `command_needs_human_checkpoint(cmd, registry)` ep permission-edit can human `RuntimeCheckpoint` ke ca duoi trust-O (`authz.py:43`), quyet tu `registry.requires_permission(...) in PERMISSION_EDIT_PERMISSIONS` chu khong tu claim issuer.
- Ra cai gi de biet xong: `command_needs_human_checkpoint("UpdateAgentPermission", reg)` True; doi `issued_by` thanh "O" khong doi ket qua.
- CHU Y: enforcement call-site (`command_bridge`) con VANG tren branch (DEC-7/DEC-8) — predicate co test, *duong thuc thi* chua wire; day la phan SE LAM lon nhat de wire trong workflow muc 2.

**Y4 — Fake = that ve cau truc (B4+B5+B6).**
- `tools/fake_control_server.py` chay CUNG `Redactor`/`parse_command`/`CommandTypeRegistry`/`build_snapshot` ma backend that se chay (DEC-6) — "drop-in = doi URL" thanh that chu khong khau hieu.
- Stream allowlist visibility: chi `public`/`ui_safe` ra wire (`fake_control_server.py:99`), `data` luon `ui_payload`, `ui_payload` thieu → `{}` khong raw (`:101`).
- Idempotency: dedup theo `(session_id, idempotency_key)` de "apply exactly once" du client retry (`:140`); `RuntimeCommand` mang `idempotency_key` bat buoc (`parse_command` raise neu rong, `commands.py:162`).
- Reliability mo phong qua `replay.py` dung 3 viec transport that phai lam: dedup theo `event_id`, `events_after(seq)` catch-up theo Last-Event-ID (`replay.py:68`), `needs_resync(last_seq)` bao rot-khoi-ring (`replay.py:61`).
- UI (`ui/control-plane/`, React Flow + tanstack-virtual) song **song song** console cu, khong dung `ui/server.py` (DEC-6). Ra cai gi de biet xong: contract-seam test (`ui/control-plane/src/test/contract-seam.test.ts`) khang dinh UI doc `ui_payload`, khong doc `payload`.

Self-check tung buoc B (chay truoc khi sang buoc ke — moi cai khoa mot bat bien):
- **B0** contract: `RuntimeEvent(event_type="", ...)` → `ControlContractError`.
- **B1** registry: `registry.assert_known("agent.invented")` raise.
- **B2** backend-truoc-UI: `CommandAck` + `TaskLoopSnapshot` import duoc, `.as_dict()` chay (2/5 shape phai co *truoc* mot dong UI — `01_BACKEND_STANDARDIZATION_BEFORE_UI.md`).
- **B3** emitter+redact: `Redactor().apply()` khong doi `event.payload` goc; event la → raise truoc khi toi sink.
- **B4** fake: `FakeControlPlane.stream()` chi tra frame cua event `public`/`ui_safe`, `data` luon `ui_payload` (khong bao gio raw).
- **B5** UI-on-fake: contract-seam test khang dinh UI doc `ui_payload`.
- **B6** reliability: buffer dedup theo `event_id`, `events_after(seq)` catch-up, `needs_resync` bao rot-khoi-ring.

## 2. Workflow skill-by-skill (vong lap build)

Vong lap chuan (kernel brief): understand/scout → brainstorm/plan → approve(HUMAN #1) → cook TDD → test → code-review → debug/fix → remember. Curriculum toi thieu moi phase: scout(2)→plan(4)→approve(5)→cook(6)→test(7)→review(8). Task chinh cua phase nay khi build tiep: **wire authz enforcement o `command_bridge`** (phan SE LAM) — neo I17, khong pha I16. Cac buoc duoi tham chieu path THAT cua E21.

| Buoc | Skill (invoke) | Prompt mau dua cho Claude (copy-duoc) | Artifact ra (path that) | Muc dich |
|---|---|---|---|---|
| 1 | `hs:understand` | `/hs:understand control/` — "Map vung control/: envelope `RuntimeEvent` (events.py:113), emitter 4-buoc (emitter.py:53), redactor (redaction.py:65), authz predicate (authz.py:43). Lam ro cai gi DA xong vs SE LAM theo phase-7-control-plane.md muc 2." | `plans/reports/<slug>-report.md` | Hieu seam truoc khi cham |
| 2 | `hs:scout` | `/hs:scout` — "Tim moi call-site nhe: noi `bus.publish` con goi truc tiep khong qua `EventEmitter.emit_event`; noi `command_bridge` SE ap `requires_permission`+checkpoint (hien VANG, DEC-7/DEC-8); cho `supervisor/graph.py:48` emitter default None. Liet ke file:line." | `plans/reports/control-plane-<YYMMDD-HHMM>-<slug>-report.md` | Dinh vi chokepoint + lo enforcement |
| 3 | `hs-think:brainstorm` | `/hs-think:brainstorm "Wire authz enforcement o command_bridge: ap requires_permission + ep human checkpoint cho UpdateAgentPermission TRUOC khi apply command. So sanh: (a) check trong emitter vs (b) call-site rieng truoc apply" --critique` | `plans/reports/<slug>-<YYMMDD-HHMM>-brainstorm-report.md` | Chot 1 huong co trade-off + DEC |
| 4 | `hs:plan` | `/hs:plan hard --tdd` — "Plan wire enforcement: predicate authz.py:43 da co; them call-site command_bridge ap requires_permission + checkpoint. AC = lenh chay duoc, neo I17. Khong pha I16 (van redact-at-boundary). Red-team: leo quyen bang issued_by giả." | `plans/<YYMMDD-HHMM>-<slug>/plan.md` | Plan kiem chung, 0 [UNVERIFIED] |
| 5 | `hs:plan` (approve) | AskUserQuestion [Review/Approve/Reject] — reviewer≠author | `plans/<slug>/artifacts/plan-approval.json` | HUMAN #1, plan_hash chua troi |
| 6 | `hs:cook` | `/hs:cook <abs-plan-path> --phase <id>` — "Thuc thi TDD red→green. Moi AC neo evidence file:line. KHONG sua `control/` thanh co I/O (giu no-I/O above kernel). Lech plan → STOP hoi." | `plans/<slug>/artifacts/verification.json` (+`review-decision.json`) | Suite green, evidence that |
| 7 | `hs:test` | `/hs:test unit` — "Chay `python -m pytest -q tests/test_control_contracts.py tests/test_control_emitter.py tests/test_fake_control_server.py tests/test_authz_attribution.py` + `python run_smoke.py`. 100% pass = gate." | `verification.json` (verdict+checks[]) + QA report | Kiem chung DoD test xanh |
| 8 | `hs:code-review` | `/hs:code-review --pending --spec <abs-plan-path>` — "Soat: co dau import `requests`/`socket`/`open()` vao `control/` khong (pha no-I/O)? Co cho nao UI/snapshot doc `payload` thay `ui_payload` (pha I16)? Authz co tin `issued_by` khong (pha I17)?" | `plans/<slug>/artifacts/review-decision.json` | Gate, verdict PASS chinh xac |
| 9 | `hs:debug` → `hs:fix` | `/hs:debug` roi `/hs:fix standard` — "Test do o `test_fake_control_server.py` (secret ro / visibility leak). Tim root cause + viet failing repro test TRUOC, roi RED→GREEN. KHONG xoa/skip test." | `plans/reports/<slug>-debug-report.md` + `verification.json` | Khi DoD do |
| 10 | `hs:explain` (tuy chon) | `/hs:explain plans/reports/<slug>-report.md` — "Report nay kho tham (qua nhieu anchor mot luc). Chunk lai theo I16/I17, gia jargon `ui_payload`/`requires_permission`, dan bang noi dau felt (secret ro = gi)." | report da viet lai (in-place / canh report) | Lam report tham duoc truoc plan |
| 11 | `hs-mem:remember` | `/hs-mem:remember` — "Ghi DEC: wire authz enforcement o command_bridge (DEC-7/DEC-8), I17 enforcement done; ranh gioi I16 giu nguyen." | `docs/decisions.md` (DEC-N) | Khong relitigate |

Hai cong NGUOI (gated, khong tu dong qua): **HUMAN #1** o buoc 5 — duyet plan, reviewer≠author, `plan_hash` chua troi (`plan-approval.json`). **HUMAN #2** o `hs:ship` (sau buoc 8) — `gate_stage.py` doi CA BA artifact `verification.json`+`review-decision.json`+`plan-approval.json`, verdict dat policy, hash khong troi. Iron Law: khong claim "done/passing" neu chua chay lenh chung minh TRONG turn nay. Giua hai cong: cook tu do red→green nhung KHONG sang phase ke khi DoD do.

## 3. Artifact: doc & quan ly the nao

Nguyen tac doc artifact (dong bo harness): **artifact la NGUON, khong phai loi ke.** Claim khong file:line/command → UNVERIFIABLE → loai. Hard stage (push/pr/ship) doi verdict dung chu **"PASS"**; PASS_WITH_RISK KHONG phai ship license. Voi MOI artifact o muc 2:

**Report (scout/understand/brainstorm)** — `plans/reports/...-report.md`. *La gi*: input cho plan/debug. *Doc field nao*: **Relevant files** truoc (dau la `bus.publish` con direct, dau la `command_bridge` vang, `supervisor/graph.py:48` emitter default None), roi **Open questions** (dong truoc khi plan). Brainstorm them cot **Evidence(file:line)**+**Decision**. *Tot trong ra sao*: moi finding neo file:line that, open questions load-bearing da dong. *Do co*: finding khong file:line / `[FALLBACK_INTERNAL]` / path stale. *Hanh dong khi do*: downstream REJECT → mo rong scout, dong open question truoc khi plan.

**plan.md** — `plans/<slug>/plan.md`.
- *Frontmatter*: `status(draft|in_progress|approved+ai), mode, tdd, epics:[E21], phases, risk, source_report`.
- *Doc*: `status: approved`+ten nguoi duyet moi cook → bang Phases → **Acceptance (plan-level)** (moi AC la LENH CHAY DUOC, vd `pytest test_authz_attribution.py → 7 passed`) → Out of scope → Locked decisions.
- *Do co* 🔴: status draft ma da cook · AC chung chung khong chay duoc · claim khong file:line / `[UNVERIFIED]` chua dong. *Hanh dong*: quay buoc 4, red-team lai.

**plan-approval.json** — `plans/<slug>/artifacts/plan-approval.json`.
- *Shape*: `{schema:"plan-approval/v1", plan, plan_hash, file_hashes, author, reviewer, verdict:"APPROVED", rationale, ts}`.
- *Doc*: APPROVED + `plan_hash` khop plan.md hien tai ⇒ cook duoc.
- *Do co* 🔴: `author==reviewer` (`plan_approval.py` ep luat role — authz=attribution dung tinh than I17) · hash lech = plan-drift · verdict≠APPROVED nhung cook. *Hanh dong*: duyet lai, reviewer≠author.

**verification.json** — `plans/<slug>/artifacts/verification.json` (schema `harness/schemas/artifact-verification.json`).
- *Shape*: `{stage, plan, actor, ts, checks[]{name,status PASS|FAIL|SKIP,detail}, verdict PASS|PASS_WITH_RISK|BLOCKED}`.
- *Doc*: verdict → tung check[]: `detail` phai co output that (`pytest → 51 passed, exit 0` / `CORE_AGENT_SMOKE_OK run_id=...` / commit SHA).
- *Do co* 🔴: bat ky check FAIL → hard stage chan · verdict PASS ma co check FAIL (gian doi) · detail rong = UNVERIFIABLE. *Hanh dong*: STOP, sua code khong sua artifact, chay lai den moi check PASS.

**review-decision.json** — `plans/<slug>/artifacts/review-decision.json` (schema `harness/schemas/artifact-review-decision.json`).
- *Shape*: `{verdict, reviewer, role, rationale, ts, [plan_hash]}`.
- *Doc*: `verdict=="PASS"` dung chu moi la ship license; rationale neu da kiem gi (vd "kiem no-I/O trong control/: 0 import requests/socket; UI doc ui_payload").
- *Do co* 🔴: BLOCKED chan ship · PASS_WITH_RISK ≠ ship license · reviewer trung author · rationale chi "LGTM". *Hanh dong*: ≠PASS → STOP; `--fix`→`hs:fix`→re-review ≤3 vong.

**DEC-x** — `docs/decisions.md`. *La gi*: register quyet dinh kien truc de khong relitigate. *Doc field nao*: block YAML (`id,status,date,actor,ts,affects`)+heading+giai trinh (huong LOAI & vi sao). `status:active`=con hieu luc. Phase nay neo: DEC-6 (fake reuse `control/`, drop-in = doi URL), DEC-7/DEC-8 (authz≠attribution, permission-edit can human). *Hanh dong khi do*: **sticky-decision** — khong dao nguoc DEC-6/DEC-8 bang abstract concern khong evidence moi; muon doi → ghi DEC moi qua `hs-mem:remember`, link DEC cu.

Honest line (nho khi doc moi artifact phase nay): contracts + emitter + redaction + fake + read-model **da chay co test**; *thuc thi quyen* (`command_bridge`) + *bien envelope thanh duong mac dinh runtime live* (`supervisor/graph.py:48` emitter default None) la thiet ke **chua wire**. Artifact tot phai phan biet 2 phan nay — verification PASS cho phan da xong KHONG dong nghia enforcement done.

## 4. Cong hieu (phai dat moi sang phase ke)

Gate dong phase = CA HAI:
- **(a) DoD test xanh** — `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`; `python -m pytest -q` → 0 fail → `verification.json` verdict PASS + moi check PASS, detail neo output that; moi AC epic → ≥1 test.
- **(b) Cong hieu** — giai thich duoc I16/I17 theo *luat → file·ham → pha ra mat gi*, quiz muc 6 ≥70%.

Checklist dieu kien (b) — phai dat HET:

- [ ] **GIAI THICH** I16 theo luat→file·ham→pha-ra-mat-gi: secret chet o `Redactor.apply` (`redaction.py:65`), mask ~14 key (`redaction.py:16`) de quy dict+list, **khong mutate** goc; UI/SSE chi phat `ui_payload`; thieu → `{}` khong raw (`fake_control_server.py:101`). Pha ra → secret/PII ro client. **(I16)**
- [ ] **CHI RA trong code** duong allowlist visibility: chi `public`/`ui_safe` ra wire (`fake_control_server.py:99`); event `internal`/`restricted` du co `ui_payload` KHONG leak — la *allowlist* khong phai denylist 'secret'. **(I16)**
- [ ] **GIAI THICH** I17: `issued_by`/`Actor` = tu khai (audit, `commands.py:31`), KHONG phai quyen; `command_needs_human_checkpoint` (`authz.py:43`) ep `UpdateAgentPermission`→human checkpoint, quyet tu `registry.requires_permission` khong tu claim. **(I17)**
- [ ] **CHI RA** ranh gioi PENDING: enforcement call-site (`command_bridge`) con VANG (`phase-7-control-plane.md:183`); predicate co test, *duong thuc thi* chua wire. Khong tuong predicate tu chan. **(I17)**
- [ ] **GIAI THICH** no-I/O above kernel: `control/` chi dataclass+validation; transport song sau `control/ports.py:EventSinkPort`; doi sang Kafka = sink moi, khong doi caller (`emitter.py:28` `BusEventSink`). **(no-I/O)**
- [ ] **CHI RA** mot duong publish: `EventEmitter.emit_event` la cua duy nhat — gate→seq→redact→fan-out (`emitter.py:53`); module tu che ten → `registry.get()` raise truoc fan-out. **(I1/registry-gate)**
- [ ] **CHAY duoc**: `python -m pytest -q tests/test_control_contracts.py tests/test_control_emitter.py tests/test_fake_control_server.py tests/test_authz_attribution.py` → 51 passed; `python run_smoke.py` → `CORE_AGENT_SMOKE_OK`. Verdict `verification.json` PASS + moi check PASS, detail neo output that.
- [ ] **CHI RA** checkpoint mot chieu: `RuntimeCheckpoint.with_status` chi `waiting`→terminal (`approved`/`rejected`/`expired`/`auto_approved`), tu choi re-resolve (`checkpoint.py:57`). Khong co "duyet lai" mot gate da dong. **(I17 phu tro)**
- [ ] **CHI RA** ack hai trang thai: `CommandAck.status` chi `received`/`rejected`; `rejected` thieu `rejection_reason` → `__post_init__` raise (`commands.py:109-134`) — mot rejected khong noi ly do la lo contract. **(I17 phu tro)**
- [ ] **CHI RA** acceptance honor evidence that (cross-ref Phase 6): gate evidence-typed adversarial o `tests_audit/test_acceptance_evidence_adversarial.py` (3 test) — Agent-O khong "pass" bang cach tro vao giay nhap cua chinh no (`supervisor/evidence.py` `NON_EVIDENCE_KINDS`). **(I15)**
- [ ] **CHAY duoc** (phu tro): `python -m pytest -q tests/test_control_snapshot.py` xanh — snapshot khong bao gio mang secret; `python -m pytest -q tests_audit/test_acceptance_evidence_adversarial.py` xanh.

Phai GIAI THICH duoc bon quyet dinh ghep lai thanh "realtime control ma khong ro secret / khong leo quyen" (roadmap muc 8):
1. **Contracts-first** — mot envelope + hai allowlist ⇒ moi thu chay qua co hinh dang biet truoc + ten hop le; bug bi chan o `__post_init__`/`assert_known`, khong phai o review.
2. **Redact-at-boundary** — secret chet o `Redactor.apply`, mot ham mot cho; an toan secret la thuoc tinh cua bien, khong phai ky luat tung dev.
3. **Authz ≠ attribution** — tach "ai tu khai" khoi "ai duoc phep" lam leo quyen *khong kha thi bang noi doi*; permission-edit luon can human.
4. **Fake-by-construction (DEC-6)** — fake reuse `control/` nen UI build tren seam that; drop-in dam bao *bang cau truc*, khong bang loi hua.

Bai hoc: kiem soat realtime khong den tu them checkpoint, ma tu **thu hep so cho mot thu nguy hiem co the xay ra** — mot envelope, mot duong publish, mot bien redact, mot dinh nghia authz.

Quiz muc 6 ≥70% (≥6/8) VA dung het cac cau I16/I17 cot loi.

## 5. Quy tac quay lai (rollback bat buoc)

| Trigger CU THE | Hanh dong |
|---|---|
| Khong chi ra duoc `Redactor.apply` la **khong mutate** goc (file:line) | Quay buoc 1, doc lai roadmap muc 4 + `control/redaction.py:65`; chay `Redactor().apply()` quan sat `event.payload` truoc/sau |
| Tuong predicate authz `tu chan` leo quyen | Quay buoc 2, doc roadmap muc 7 (PENDING) + `phase-7-control-plane.md:183`; enforcement call-site con VANG |
| Thay import `requests`/`socket`/`open()` trong `control/` | STOP — pha no-I/O above kernel; cai do thuoc transport sau `control/ports.py`. Quay buoc 6, sua code, re-review |
| Snapshot/UI doc `payload` thay `ui_payload` (secret ro) | `/hs:debug` → repro test → `/hs:fix`; sua doc tu redacted view (`snapshot.py:251`), KHONG noi long redact |
| DoD test DO (`test_fake_control_server.py` visibility leak / idempotency) | `/hs:debug` (root cause + failing repro test) → `/hs:fix` (RED→GREEN). KHONG xoa/skip/lam yeu test. KHONG sang phase ke |
| `verification.json` co check FAIL | STOP, sua code KHONG sua artifact, chay lai den moi check PASS |
| review verdict≠PASS (PASS_WITH_RISK / BLOCKED) | PASS_WITH_RISK→AskUserQuestion(fix/accept/cancel); BLOCKED→`/hs:fix`→re-review ≤3 vong |
| `author==reviewer` o plan-approval | Duyet lai qua `plan_approval.py`, reviewer≠author (luat role = I17 trong harness) |
| Plan drift sau approve (hash lech) | Duyet lai; KHONG cook tren plan_hash da troi |
| Khong giai thich duoc I16/I17 / quiz <70% | KHONG sang phase ke; doc lai `phase-7-control-plane.md` muc 5 + bang I# README + artifact, chay lenh tu kiem, quiz lai |
| 3 lan fix fail / 3+ hypothesis fail | STOP hoi user, xem lai kien truc |

Pitfall phase nay (trieu chung → nguyen nhan → cach tranh, roadmap muc 6):
- **Secret hien trong UI/Inspector** → snapshot/UI doc `payload` tho thay `ui_payload` → luon doc `ui_payload`; trong fold whitelist field + copy dict free-form chi tu redacted view (`snapshot.py:251`).
- **Agent "tu khai O" roi leo quyen** → tin `issued_by`/`Actor` nhu authz → authz quyet boi `requires_permission`+checkpoint; `UpdateAgentPermission` luon can human (`authz.py:43`). Nho: enforcement call-site con PENDING.
- **Module tu che ten event → mat sink/replay/visibility** → goi `bus.publish("agent.whatever", ...)` truc tiep → moi publish qua `EventEmitter.emit_event`; `registry.get()` raise truoc fan-out (`emitter.py:56`).
- **UI "chay" tren fake nhung vo khi dau backend that** → fake la facade tay nan, khac shape → fake PHAI reuse `control/`; 2 shape thieu (`TaskLoopSnapshot`/`CommandAck`) tao dataclass truoc UI (DEC-6).
- **Client mat thu tu / khong resync** → emitter bo buoc seq, hoac transport khong ho tro Last-Event-ID → `EventEmitter` stamp `seq` per-session; buffer dedup `event_id`, `events_after(seq)` catch-up, `needs_resync` bao rot-khoi-ring.
- **Resolve checkpoint hai lan / phantom Approval modal** → cho re-resolve, hoac snapshot van ship `waiting` sau khi stream bao approve → `with_status` chi `waiting`→terminal (`checkpoint.py:57`); `build_snapshot` resolve gate khi gap `approval.approved/rejected`.

## 6. Cau hoi kiem tra hieu (tu cham / nho Claude cham)

Tu tra loi truoc, doi chieu *Diem cham* (dap an rut gon + map I#). Muc dau: **≥6/8**, BAT BUOC dung cac cau I16 (Q1,Q2,Q3) va I17 (Q4,Q5). Tra loi khong neo file:line = chua dat du dung y.

1. **(I16)** Vi sao secret chet o BIEN — mot ham `Redactor.apply` — an toan hon "nho mask o moi cho ghi event"? — *Diem cham*: an toan secret la thuoc tinh cua bien, khong phai ky luat tung dev; mot cho phai dung thay N cho phai nho (`redaction.py:65`). Map I16.
2. **(I16)** `ui_payload` cua mot event la `None` (chua qua Redactor). Gateway SSE phat gi ra wire — va vi sao KHONG fallback `payload` raw? — *Diem cham*: phat `{}` (`fake_control_server.py:101`); fallback raw = ro secret. Map I16.
3. **(I16, allowlist)** Mot event `internal` da co `ui_payload` mask. No co ra wire khong? Vi sao la allowlist khong phai denylist? — *Diem cham*: KHONG — chi `public`/`ui_safe` ra (`fake_control_server.py:99`); denylist 'secret' se de lot `internal`. Map I16.
4. **(I17)** Agent "tu khai issued_by=O" roi gui `UpdateAgentPermission`. Co leo quyen duoc khong? Cai gi chan? — *Diem cham*: KHONG; `command_needs_human_checkpoint` ep human checkpoint, quyet tu `registry.requires_permission` (`authz.py:43`, `runtime_command_types.yaml:27`), khong tu claim. Map I17.
5. **(I17, ranh gioi)** Predicate authz da co test va xanh. Vay leo quyen da bi CHAN trong runtime live chua? — *Diem cham*: CHUA — enforcement call-site `command_bridge` con VANG (`phase-7-control-plane.md:183`); predicate co, *duong thuc thi* chua wire. Map I17.
6. **(no-I/O)** Tai sao `control/` KHONG duoc import `requests`/`socket`/`open()`? Doi backend Kafka thi sua cho nao? — *Diem cham*: `control/` la dataclass+validation above kernel; transport sau `control/ports.py:EventSinkPort`; Kafka = sink moi, khong doi caller (`emitter.py:28`). Map no-I/O.
7. **(emitter)** Thu tu 4 buoc cua `emit_event` la gi, vi sao gate phai TRUOC fan-out? — *Diem cham*: gate→seq→redact→fan-out (`emitter.py:53`); type la → `registry.get()` raise TRUOC khi cham sink, khong leak ten tu che. Map I1/registry.
8. **VAN DUNG** — Ban them mot event-type moi `agent.tool_result` voi field `raw_stdout` chua secret. Ban viet `bus.publish("agent.tool_result", {...})` truc tiep. (a) Event co tu co redact + seq + visibility-gate khong? (b) Vi sao? (c) Sua dung la gi?
   - *Diem cham*: (a) KHONG; (b) vi bo qua `EventEmitter.emit_event` la duong DUY NHAT co redact/seq/gate — observability+an toan chi co o cua, them feature = cam adapter vao port da co, khong mo cua moi; (c) khai type trong `runtime_event_types.yaml` (visibility hop ly + `redact_for_ui`) roi phat qua `emitter.emit_event`, KHONG goi `bus.publish` truc tiep. Map I16+registry.

Cau mo rong (tu chon, chung minh hieu sau): payload co `{"headers": [{"authorization": "Bearer xxx"}]}` — mot secret nam trong **list**. Redactor co mask khong? Vi sao? — *Diem cham*: CO; `Redactor` walk de quy qua dict AND list (`redaction.py:65-69`), khong chi top-level dict. Neu chi mask dict → secret trong list lot ra UI. Map I16.

## 7. Prompt cham hieu cho Claude

Dan nguyen van cau tra loi cua ban vao `[...]` roi gui prompt nay cho Claude:

```
Toi tra loi the nay [...dan cau tra loi cua ban cho Q1-Q8...].
Dua tren Phase 7 — Realtime control plane (roadmap plans/260626-1358-clone-hex-agent-roadmap/phase-7-control-plane.md),
invariant I16 (secret chet o bien: Redactor.apply khong mutate goc, UI chi doc ui_payload, fake khong fallback raw)
va I17 (attribution≠authz: command_needs_human_checkpoint quyet tu registry khong tu issued_by; enforcement call-site command_bridge con PENDING),
cham toi da hieu chua. Voi tung cau:
  - dung/sai/mot-phan, va NEU sai thi sai o dau (vi du toi co tuong predicate tu chan, tuong fake fallback raw, tuong mask la denylist?).
  - moi cho sai neo file:line that trong control/ + roadmap de toi tu kiem lai.
  - rieng cau VAN DUNG (Q8): kiem toi co nhan ra bus.publish truc tiep KHONG tu co redact/seq/visibility-gate khong.
Chot: toi co dat >=6/8 + dung het cau I16 (Q1,Q2,Q3) va I17 (Q4,Q5) khong? Neu chua, liet ke 1-2 doan roadmap toi phai doc lai TRUOC khi quiz lai. Co nen cho toi qua phase ke khong?
```

---
*Dieu huong: ← [Phase 6 workflow](phase-6-build-workflow.md) · → [Curriculum guide](00-curriculum-guide.md) · Roadmap goc: [phase-7-control-plane.md](../phase-7-control-plane.md)*
