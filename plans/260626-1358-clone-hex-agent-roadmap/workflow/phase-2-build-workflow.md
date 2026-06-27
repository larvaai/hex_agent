---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — Workflow build-along: LLM-as-capability & Output discipline

> Cap voi: roadmap [phase-2-llm-discipline.md](../phase-2-llm-discipline.md) · Epic E03+E02 · Invariant I5-I7 · Muc tieu: vua BUILD vua HIEU phase nay qua skill + cong

## 0. Ban se roi phase nay khi

**Build duoc X:**
- `agent_node` goi LLM qua `session.execute_tool("llm.chat", {...})` (`nodes.py:55-58`) — KHONG co `kernel.call_llm()`. Envelope co `capability=="llm.chat"`, `feature=="llm"`, phat `tool.requested`/`tool.completed`.
- `parse_action(content)` ep dung **mot** action moi turn; JSON hong → `light_json_repair` 7 rule cuu duoc fence/prose/trailing-comma/python-literal; khong cuu duoc → `JsonGateError`.
- `Budget.record_parse_error()` tang `parse_errors`, KHONG dung `steps` (`budget.py:44-46`); node return som truoc `record_step()`.
- `condense` co ket qua tool truoc khi nhet lai cho model, luon ghi `+N` da cat (`condense.py:13-24`) — co nhung khong giau lang le.
- `check_finish` chan `final` khi `code_changed and not validation_passed and finish_reason != "blocker"` (`finish_gate.py:17`).
- DoD: `python -m pytest tests/test_discipline.py tests/test_llm_adapter.py tests/test_llm_retry.py tests/test_llm_capability.py tests/test_json_gate_repair.py -q` xanh 100%, offline (fake client, khong mang).

Dieu kien tot nghiep = (a) DoD test xanh **VA** (b) giai thich duoc I5-I7 theo *luat → file·ham → pha ra mat gi*. Thieu mot ve → chua qua, doc lai muc 4.

**Giai thich duoc Y:** vi sao LLM **khong** la cong dan hang nhat (I5) · vi sao parse-error tach khoi step (I7) · vi sao `discipline/` la module dung chung cho ca node lan middleware (`middleware/condense.py:8`). Quiz ≥70% o muc 6.

## 1. Y tuong trien khai kha thi (doc la biet lam gi)

7 file ban se cham (roadmap muc 2): `discipline/json_gate.py` (`parse_action`), `discipline/budget.py` (`Budget`), `discipline/condense.py` (`condense`), `discipline/finish_gate.py` (`check_finish`), `discipline/__init__.py` (re-export 9 symbol cho ca node lan middleware), `llm/adapter.py` (`call_llm`), `features/llm_chat.py` (`LLMChatTool`+`install`). Bon van `adapter/json_gate/budget/finish_gate` nam *quanh* cua `execute_tool` cua Phase 1 — KHONG thay no.

**Y1 — Dung 4 cai van discipline TRUOC, vi chung khong phu thuoc gi (`json_gate` → `budget` → `condense` → `finish_gate`).**
- `parse_action` (`json_gate.py:475`, raise `stage=="schema"` o `:479`) = `parse_json_object` + bat buoc field `"action"`. Thang sua `_candidates` (`json_gate.py:358-368`): candidate #1 luon la **raw** — JSON dung khong bao gio bi rule cham (`json_gate.py:4-6`). 7 rule thuan `str->str` gom trong `light_json_repair` (`json_gate.py:305-317`): `strip_markdown_fence` (`:35`), `extract_largest_json_region` (`:76`), `remove_trailing_commas` (`:86`), `replace_python_literals` (`:125`), `quote_unquoted_keys` (`:129`), `convert_single_quoted_values` (`:238`), `balance_trailing_delimiters` (`:277`).
- Ra cai gi de biet xong: `parse_action('```json\n{"action":"final","message":"ok",}\n```')` ra `final` (fence+trailing comma); `parse_action('{"tool":"echo"}')` nem `JsonGateError` `stage=="schema"`.

**Y2 — `Budget` la dataclass dem, hai bo dem TACH ROI (I7).**
- `record_step()` → `steps += 1`; `record_parse_error()` → `parse_errors += 1` KHONG dung `steps` (`budget.py:37-46`). `tool_key` bam `tool+args` (sort key) phat hien lap y het.
- Ra cai gi de biet xong: goi `record_parse_error()` 2 lan → `steps == 0` va `parse_exceeded() == False` (can 8 lan LIEN TIEP, vi gate doc `consecutive_parse_errors`, reset khi `record_step`/`record_parse_success`). Goi 8 lan lien tiep → `parse_exceeded() == True`.

**Y3 — `llm/adapter.py` bon viec, KHONG bao gio raise.**
- Lazy client: `_get_client()` chi `from openai import OpenAI` va dung client khi *duoc goi*, cache vao `_client` global (`adapter.py:25-32`) — khong network luc import. Ep JSON: `json_mode=True` → `kwargs["response_format"]={"type":"json_object"}` (`adapter.py:80-81`). Retry transient: chi khi `_is_transient(exc)` (timeout/conn/429/5xx), backoff `retry_base*2**attempt` (`adapter.py:99-100`); 4xx khac dung ngay. Kiet retry → tra `{"action":"final","finish_reason":"error","message":...}` (`adapter.py:115-119`), loop khong sap.
- Ra cai gi de biet xong: `tests/test_llm_retry.py` — 5xx retry roi thanh cong; 4xx `calls==1`.

**Y4 — `condense.py` co nho ket qua tool, CHI CO khong BIA (van thu 3, dung chung).**
- De quy (`condense.py:13-24`): dict de quy theo value; list cat con `max_list` roi gan `"... [+N items]"`; str cat con `max_chars` roi gan `"... [+N chars]"`; con lai giu nguyen. Luon ghi so da cat de model biet co du lieu bi giau. Song trong `discipline/`, ca `agent_node` lan `middleware/condense.py:8` goi cung ham nay.
- Ra cai gi de biet xong: `condense({"text":"x"*5000}, max_chars=100)` → `len < 200` va chuoi chua `"+4900"`.

**Y5 — `features/llm_chat.py` boc adapter thanh capability, noi vao `agent_node`.**
- `LLMChatTool.execute(request)` doc `request.args`, goi `call_llm(...)`, tra `{"ok":True,"content":...,"model":...}` (`llm_chat.py:23-32`). `install(kernel, client=)` dang ky FEATURE+tool (`llm_chat.py:35-37`), client injectable de test offline. `agent_node` goi qua cua (`nodes.py:55-58`), `parse_action(content)` (`nodes.py:64`); loi → `record_parse_error`+retry message (`nodes.py:66-82`); hop le → `record_step` route theo verb (`nodes.py:84-103`); `finish_node` chay `check_finish` (`nodes.py:220`).
- Ra cai gi de biet xong: `kernel.execute_tool("llm.chat", {...})` tra envelope co `capability=="llm.chat"`, metric `llm_calls==1`, kind `LLMCallEvent`.

Thu tu trong `agent_node` la load-bearing (`nodes.py:64-84`, rut gon) — `record_step` chi chay khi action HOP LE:

```python
try:
    action = parse_action(content)
except JsonGateError as exc:
    budget.record_parse_error()             # dot parse-error, KHONG dot step (I7)
    if budget.parse_exceeded(): return {... "route": "fail"}
    messages.append({"role": "user", "content": build_retry_message(exc)})
    return {... "route": "guard"}            # return SOM, chua toi record_step
budget.record_step()                         # chi toi day khi action HOP LE
```

**Cai neo (sua file nao → pha invariant nao):** dung bang nay lam ban do khi cook + review.

| neo `file:line` | invariant | sai thi mat gi |
|---|---|---|
| `_client` global + `_get_client` `adapter.py:25-32` | network chi cham khi goi, khong khi import | import-time hang / test offline gay |
| `kwargs["response_format"]` `adapter.py:80-81` | `json_mode` ⇒ request ep `json_object` | model tra van xuoi, gate ganh nhieu hon |
| `_is_transient` `adapter.py:40-50` | chi retry timeout/conn/429/5xx | retry 4xx vo ich, hoac bo qua loi tam |
| `parse_action` `json_gate.py:475-480` | dung 1 object, bat buoc `"action"` (I6) | turn nhap nhang nhieu action / thieu verb |
| `Budget.record_parse_error` `budget.py:44-46` | parse-error KHONG dot step (I7) | model hay hong JSON tieu sach step budget |
| `check_finish` `finish_gate.py:15-22` | chan final neu doi code chua validate | agent "bao xong" voi code chua chay duoc |
| `condense` `condense.py:13-24` | co nhung luon ghi `+N` da cat | mat du lieu lang le, model quyet dinh mu |

## 2. Workflow skill-by-skill (vong lap build)

| Buoc | Skill (invoke that) | Prompt mau dua cho Claude (copy-duoc) | Artifact ra (path that) | Muc dich |
|---|---|---|---|---|
| 1. Hieu vung code | `hs:understand` → `/hs:understand discipline/ llm/ features/llm_chat.py` | `Doc plans/260626-1358-clone-hex-agent-roadmap/phase-2-llm-discipline.md muc 2-3. Map ban do module discipline/json_gate.py + budget.py + condense.py + finish_gate.py + llm/adapter.py + features/llm_chat.py. Chi ra chokepoint execute_tool ma agent_node se goi.` | `plans/reports/<slug>-report.md` | Lap ban do truoc khi cham code la |
| 2. Dinh vi file/pattern | `hs:scout` → `/hs:scout` | `Tim trong repo: noi agent_node goi llm.chat (nodes.py:55-58), parse_action (json_gate.py:475), Budget.record_parse_error (budget.py:44-46), check_finish (finish_gate.py:17). Liet ke Relevant files + Open questions cho Phase 2 (I5-I7).` | `plans/reports/<scope>-<YYMMDD-HHMM>-<slug>-report.md` | Co "Relevant files"+"Open questions" truoc khi plan |
| 3. Ban huong (tuy chon) | `hs-think:brainstorm` → `/hs-think:brainstorm "thang sua JSON: candidate-ladder hay regex-don?" --critique` | `Phase 2 can light_json_repair 7 rule thuan str->str (json_gate.py:305-317). Banh: A) candidate-ladder raw-first vs B) repair-in-place. Moi option neu trade-off + Evidence(file:line). Chot 1 huong.` | `plans/reports/<slug>-<YYMMDD-HHMM>-brainstorm-report.md` (+DEC) | Moi option co trade-off; chot 1 huong |
| 4. Lap plan kiem chung | `hs:plan` → `/hs:plan hard --tdd` | `Lap plan TDD cho Phase 2 (E03+E02, I5-I7) tu phase-2-llm-discipline.md. Phase: B1 json_gate, B2 budget, B3 condense, B4 finish_gate, B5 adapter, B6 llm_chat, B7 noi agent_node. Acceptance moi AC la LENH CHAY DUOC (python -m pytest tests/test_*.py -q). Resolve moi [UNVERIFIED].` | `plans/<YYMMDD-HHMM>-<slug>/plan.md` + `phase-NN-*.md` | 0 mau thuan; moi `[UNVERIFIED]` resolved |
| 5. Phe duyet plan (HUMAN #1) | `hs:plan` (AskUserQuestion) | `Review plan Phase 2. Kiem: status, AC chay duoc, neo file:line that. reviewer != author. Approve/Reject.` | `plans/<slug>/artifacts/plan-approval.json` | `verdict:"APPROVED"` & `plan_hash` khop & reviewer≠author → `/clear` roi cook |
| 6. Thuc thi TDD red→green | `hs:cook` → `/hs:cook <abs-plan-path> --phase B1` (lap toi B7) | `Cook phase B1 (json_gate.py). RED truoc: viet tests/test_json_gate_repair.py + tests/test_discipline.py (parse 1 action, missing-action stage=="schema", parse_does_not_consume_steps). GREEN: implement parse_action raw-first ladder. KHONG xoa/skip test. Lech plan → STOP hoi.` | `plans/<slug>/artifacts/verification.json` (+`review-decision.json` per-phase) | Suite green 100%; moi AC co evidence file:line |
| 7. Chay & kiem chung test | `hs:test` → `/hs:test unit` | `Chay python -m pytest tests/test_discipline.py tests/test_llm_adapter.py tests/test_llm_retry.py tests/test_llm_capability.py tests/test_json_gate_repair.py tests/test_supervisor_discipline.py -q. 100% pass=gate. Bat ky FAIL → hard stage chan. Neo output that vao verification.json.` | `verification.json` (verdict+checks[]) + QA report | 100% pass; check FAIL → hard stage chan |
| 8. Review code (gate) | `hs:code-review` → `/hs:code-review --pending --spec <plan>` | `Review pending Phase 2. Soi: co kernel.call_llm() back-door khong (pha I5)? record_step goi truoc parse_action (pha I7)? condense cat ma khong ghi +N (pha condense)? Verdict PASS chinh xac moi qua.` | `plans/<slug>/artifacts/review-decision.json` | Verdict **PASS** chinh xac (PASS_WITH_RISK van chan) |
| 9-10. Debug/fix (khi do) | `hs:debug` → `/hs:debug`; `hs:fix` → `/hs:fix standard` | `Test tests/test_llm_retry.py::test_no_retry_on_permanent_4xx do (calls!=1). Tim root cause, viet failing repro test TRUOC. Sau do fix: _is_transient chi True cho timeout/conn/429/5xx (adapter.py:40-50). RED→GREEN.` | `plans/reports/<slug>-debug-report.md` + `verification.json` | Co failing repro test; RED→GREEN full suite pass |
| 11. Ghi quyet dinh | `hs-mem:remember` → `/hs-mem:remember` | `Ghi DEC: chon candidate-ladder raw-first cho json_gate (JSON dung khong bi rule cham, json_gate.py:4-6). status:active, affects: discipline/json_gate.py.` | `docs/decisions.md` (DEC-N) | Khong relitigate quyet dinh |

Curriculum toi thieu: scout(2)→plan(4)→approve(5)→cook(6)→test(7)→review(8). `hs:ship` chi khi ca 3 artifact (verification+review-decision+plan-approval) du va verdict dat policy.

**Thu tu cook (buoc 6, lap `--phase` tung B):** discipline TRUOC vi khong phu thuoc gi → adapter → wire qua kernel.
- B1 `json_gate.py` → test `tests/test_json_gate_repair.py` + `tests/test_discipline.py` (parse 1 action, missing-action `stage=="schema"`).
- B2 `budget.py` → test `tests/test_discipline.py::parse_does_not_consume_steps` + same-tool.
- B3 `condense.py` → test condense trong `tests/test_discipline.py`.
- B4 `finish_gate.py` → test finish-gate; B7 `tests/test_supervisor_discipline.py` chung minh **cung module**.
- B5 `llm/adapter.py` → `tests/test_llm_adapter.py` + `tests/test_llm_retry.py`.
- B6 `features/llm_chat.py` → `tests/test_llm_capability.py` (envelope+event+`llm_calls`).
- B7 noi `agent_node` (`nodes.py:55-103`, `:220`) → re-run full suite.
RED truoc moi B (test do), GREEN sau (implement). Lech B1-B7 → STOP hoi.

## 3. Artifact: doc & quan ly the nao

**Report (scout/understand)** — `plans/reports/<scope>-<YYMMDD-HHMM>-<slug>-report.md`.
- *La gi:* input cho plan/debug. Doc **Relevant files** truoc (phai co `nodes.py:55-58`, `json_gate.py:475`, `budget.py:44-46`, `finish_gate.py:17`), roi **Open questions**.
- *Tot:* moi finding neo file:line that; open questions load-bearing da dong truoc khi plan.
- *Do co:* finding khong file:line → downstream REJECT · `[FALLBACK_INTERNAL]` · path stale.
- *Hanh dong khi do:* mo rong scout, dong open question truoc khi sang buoc 4.
- *brainstorm-report (buoc 3, tuy chon)* dung chung khung doc voi Report nhung them cot **Evidence(file:line)**+**Decision**; *do co:* option khong trade-off / chot thieu Evidence → lam lai. Quyet dinh chot ghi tiep vao DEC-x.

**plan.md** — `plans/<YYMMDD-HHMM>-<slug>/plan.md`.
- *La gi:* hop dong thuc thi. Doc frontmatter `status: approved`+ten nguoi duyet → bang Phases (B1-B7) → **Acceptance (plan-level)** (moi AC la LENH `python -m pytest ... -q`) → Out of scope (graph topology day du, delegation — Phase 4+) → Locked decisions.
- *Tot:* `status: approved`, AC chay duoc, claim neo file:line.
- *Do co:* 🔴 `status: draft` ma da cook · AC chung chung khong chay duoc · `[UNVERIFIED]` chua dong.
- *Hanh dong khi do:* STOP, sua plan, red-team lai roi moi cook.

**plan-approval.json** — `plans/<slug>/artifacts/plan-approval.json`.
- *La gi:* license de cook. Shape `{schema:"plan-approval/v1", plan, plan_hash, file_hashes{...}, author, reviewer, verdict:"APPROVED", rationale, ts}`.
- *Tot:* `verdict:"APPROVED"` + `plan_hash` khop plan.md hien tai ⇒ cook duoc.
- *Do co:* 🔴 `author==reviewer` (`plan_approval.py` ep luat role) · hash lech = plan-drift · `verdict != APPROVED` nhung cook.
- *Hanh dong khi do:* hash lech → duyet lai qua `plan_approval.py` (reviewer≠author).

**verification.json** — `plans/<slug>/artifacts/verification.json` (schema `harness/schemas/artifact-verification.json`).
- *La gi:* nguon su that test, KHONG phai loi ke. Shape `{stage, plan, actor, ts, checks[]{name,status,detail}, verdict}`.
- *Tot:* `verdict:"PASS"` + moi check PASS; `detail` co output that (`pytest → 345 passed, exit 0`, hoac `test_llm_retry → calls==1`).
- *Check Phase 2 phai thay (DoD roadmap muc 7):* `test_llm_adapter` (lazy import, json-mode, injected client khong ghi cache, loi → final `finish_reason=="error"`), `test_llm_retry` (5xx/429/timeout retry; 4xx `calls==1`), `test_llm_capability` (envelope+event+`llm_calls==1`), `test_json_gate_repair` (fence/prose/trailing-comma/python-literal), `test_discipline` (`parse_does_not_consume_steps`, same-tool), `test_supervisor_discipline` (cung module).
- *Do co:* 🔴 bat ky check FAIL → hard stage chan · verdict PASS ma co check FAIL (gian doi) · `detail` rong = UNVERIFIABLE.
- *Hanh dong khi do:* check FAIL → STOP, sua **code** khong sua artifact, chay lai den moi check PASS.

**review-decision.json** — `plans/<slug>/artifacts/review-decision.json` (schema `harness/schemas/artifact-review-decision.json`).
- *La gi:* ship license. Shape `{verdict, reviewer, role, rationale, ts, [plan_hash]}`.
- *Tot:* `verdict=="PASS"` dung chu; rationale neu da soi I5 (khong back-door), I7 (record_step sau parse), finding LOW/INFO.
- *Do co:* 🔴 BLOCKED chan ship · PASS_WITH_RISK ≠ ship license · reviewer trung author (tu soi) · rationale chi "LGTM".
- *Hanh dong khi do:* ≠PASS → STOP; `--fix`→`hs:fix`→re-review (≤3 vong).

**DEC-x** — `docs/decisions.md`.
- *La gi:* so dang ky quyet dinh kien truc de khong relitigate. Block YAML (`id,status,date,actor,ts,affects`)+heading+giai trinh (huong LOAI & vi sao loai).
- *Tot:* `status:active`+`affects` tro dung file (vd `discipline/json_gate.py`); giai trinh neu vi sao chon candidate-ladder thay vi regex.
- *Do co:* dao nguoc DEC bang abstract concern khong evidence moi (vi pham sticky-decision).
- *Hanh dong khi do:* muon doi huong → mo DEC moi voi evidence file:line, KHONG sua lén DEC cu.

## 4. Cong hieu (phai dat moi sang phase ke)

Checklist — moi muc gan invariant. Day la dieu kien (b) cua giao thuc cong (b cong = giai thich duoc I# theo *luat → file·ham → pha ra mat gi*):

- [ ] **GIAI THICH duoc I5:** vi sao LLM la `llm.chat` qua `execute_tool` chu khong phai `kernel.call_llm()`. Luat → `features/llm_chat.py` `install` (`llm_chat.py:35-37`), `agent_node` cham qua `session.execute_tool` (`nodes.py:55`) → pha ra: mat envelope+event `tool.*`+lineage+dem `llm_calls`, LLM thanh lo den khong quan sat duoc.
- [ ] **CHI RA duoc trong code I6:** dong nao ep dung 1 action. `parse_action` (`json_gate.py:475-480`) tra dung 1 dict co `"action"`, nem `JsonGateError` neu khong → node bien thanh dung 1 route. Chi ra candidate #1=raw (`json_gate.py:358-368`) — JSON dung khong bi rule sua lam meo.
- [ ] **CHI RA duoc trong code I7:** parse-error KHONG dot step. `record_parse_error` tach khoi `record_step` (`budget.py:37-46`); trong `agent_node` thu tu load-bearing: parse loi → `record_parse_error` + **return som** truoc `record_step` (`nodes.py:66-84`).
- [ ] **CHAY duoc DoD:** `python -m pytest tests/test_discipline.py tests/test_llm_adapter.py tests/test_llm_retry.py tests/test_llm_capability.py tests/test_json_gate_repair.py -q` → 0 fail, offline. Va `tests/test_supervisor_discipline.py` chung minh finish-gate la **cung module** worker turn chay qua (khong duplicate).
- [ ] **GIAI THICH duoc module dung chung:** `condense`/`check_finish` song trong `discipline/`, ca node lan `middleware/condense.py:8` (`from discipline import condense`) goi. Pha ra: nhan doi logic finish-gate → doi luat (`finish_reason="blocker"`) sua 1 cho quen cho kia → agent "bao xong doi".
- [ ] **CHI RA duoc lazy client:** `_get_client` `from openai import OpenAI` *ben trong* ham, cache `_client` global (`adapter.py:25-32`). Pha ra: import-time hang / test offline gay.
- [ ] **CHI RA duoc finish-gate:** cua thoat hop phap duy nhat khi code doi ma chua validate la `finish_reason="blocker"` (`finish_gate.py:15-22`). Pha ra: agent "bao xong" voi code chua chay duoc.
- [ ] **CHI RA duoc condense ghi `+N`:** `condense` co nhung luon noi so da cat (`condense.py:13-24`). Pha ra: mat du lieu lang le, model quyet dinh mu.

Hai khoi code phai chi tay duoc khi tu cham (`phase-2-llm-discipline.md` muc 4):

```python
# json_gate.py:358-368 — candidate #1 luon raw, JSON dung khong bi rule sua lam meo (I6)
base = strip_bom(raw)
add(base)                                   # raw truoc nhat
add(_safe(strip_markdown_fence, base))
add(_safe(extract_largest_json_region, region_src))
add(_safe(light_json_repair, base))         # manh tay nhat, cuoi cung
```

```python
# budget.py:37-46 — parse-error va step la HAI bo dem tach roi (I7)
def record_step(self) -> None:        self.steps += 1; self.consecutive_parse_errors = 0
def record_parse_error(self) -> None: self.parse_errors += 1   # KHONG dung steps
                                      self.consecutive_parse_errors += 1   # bo dem THUC SU drive gate
```

Gate doc `consecutive_parse_errors` (reset khi `record_step`), nen parse-error rai rac giua cac step thanh cong KHONG tich luy — chi 8 lan LIEN TIEP moi trip (`budget.py:21,53-54`).

Dat (a) DoD test xanh **VA** (b) giai thich duoc I5-I7 → moi sang Phase 3.

## 5. Quy tac quay lai (rollback bat buoc)

| Trigger (cu the) | Hanh dong |
|---|---|
| Khong chi ra duoc dong `record_step` goi SAU `parse_action` trong `nodes.py:66-84` | Quay lai buoc 1 (`hs:understand`), doc lai roadmap muc 4 (khoi code `budget.py:37-46`) + muc 5 (I7) |
| `import llm.adapter` treo / pytest collect can mang | STOP. Bug "Network luc import" (roadmap muc 6). Sua: lazy client `adapter.py:25-32` + `reset_client()`. `/hs:fix standard` |
| `test_no_retry_on_permanent_4xx` do (`calls!=1`) | `/hs:debug` (root cause: retry moi exception) → `/hs:fix`: `_is_transient` chi True timeout/conn/429/5xx (`adapter.py:40-50`) |
| DoD test DO bat ky | `/hs:debug` (failing repro test TRUOC) → `/hs:fix`. KHONG xoa/skip/lam yeu test. KHONG sang phase ke |
| `verification.json` co check FAIL nhung verdict PASS | STOP — gian doi artifact. Sua code khong sua artifact, chay lai den moi check PASS |
| review verdict = PASS_WITH_RISK | AskUserQuestion(fix/accept/cancel); BLOCKED → `/hs:fix` → re-review ≤3 vong. PASS_WITH_RISK KHONG phai ship license |
| `plan-approval.json` hash lech sau approve (plan-drift) | Duyet lai qua `plan_approval.py` (reviewer≠author). KHONG cook plan da troi |
| Lech plan khi cook (them module ngoai B1-B7) | STOP hoi. Module ngoai phase (graph topology, delegation) = Phase 3+ |
| Agent "bao xong" sau khi doi code ma test chua tung xanh (finish-gate bypass) | Kiem `finish_node` co goi `check_finish` + `allowed=False` → emit `graph.finish_blocked` route `guard` (`nodes.py:220-229`). Sua, `/hs:fix` |
| Model "quen" phan cuoi ket qua tool, quyet dinh sai (condense cat au) | Kiem `condense` co noi `"... [+N chars/items]"` (`condense.py:7-21`). Khong co dau vet → sua de luon ghi `+N` |
| 400 `"response_format.type must be json_schema or text"` tren llama.cpp/vLLM | Bat loi, ha xuong `{"type":"text"}` *mot lan* khong ton attempt (`adapter.py:62-69`, `95-98`); gate van parse text |
| Khong giai thich duoc 1 muc I5-I7 / quiz muc 6 < 70% HOAC sai cau I5/I6/I7 | KHONG sang phase ke. Doc lai `phase-2-llm-discipline.md` muc 4-5 + artifact, chay lenh tu kiem, quiz lai |

## 6. Cau hoi kiem tra hieu (tu cham / nho Claude cham)

Muc dau: **≥6/8 dung VA bat buoc dung 3 cau ve I5/I6/I7 (Q1, Q3, Q5).**

1. **(I5)** Vi sao agent KHONG duoc co `kernel.call_llm()` rieng? — *Diem phai cham:* LLM phai la capability `llm.chat` qua `execute_tool` (`nodes.py:55`); back-door = mat envelope+event `tool.*`+lineage+`llm_calls`, thanh lo den khong quan sat. Map I5.
2. **(adapter)** `json_mode=True` thay doi request shape the nao, va vi sao van can json_gate? — *Diem:* set `kwargs["response_format"]={"type":"json_object"}` (`adapter.py:80-81`); van can gate vi server local co the tra van xuoi hoac chi nhan `json_schema`/`text` (ha xuong text 1 lan, `adapter.py:62-69`).
3. **(I6)** `parse_action` lam gi khi model tra `{"tool":"echo"}` (thieu `"action"`)? — *Diem:* nem `JsonGateError` `stage=="schema"` (`json_gate.py:475-480`, raise o `:479`); ep dung 1 dict co `"action"`. Map I6.
4. **(json_gate)** Tai sao candidate #1 phai la raw, khong duoc sua truoc? — *Diem:* JSON hop le luon duoc raw bat (`json_gate.py:4-6`, `:358-368`); rule sua khong bao gio cham object da dung → tranh lam meo JSON tot.
5. **(I7)** Goi `record_parse_error()` 2 lan thi `steps` bang may? Vi sao quan trong? — *Diem:* `steps == 0`, chi `parse_errors`+`consecutive_parse_errors` tang (`budget.py:44-46`); model hay hong JSON van co co hoi sua ma khong cut step budget. Phai-cham: gate la CONSECUTIVE — `parse_exceeded()` doc `consecutive_parse_errors >= max=8` (`budget.py:53-54`), KHONG phai lifetime; 2 lan → van `False`. Map I7.
6. **(finish_gate)** Cua thoat hop phap duy nhat khi `code_changed=True, validation_passed=False` la gi? — *Diem:* `finish_reason="blocker"` → `check_finish` cho `allowed=True` (`finish_gate.py:17`); nguoc lai chan + route `guard`.
7. **(adapter)** Server tra 400 vs timeout: cai nao retry, cai nao khong, vi sao? — *Diem:* timeout/conn/429/5xx → `_is_transient` True → retry backoff; 4xx khac permanent dung ngay (`adapter.py:40-50`, `99-103`). 400=prompt sai, retry vo ich.
8. **(VAN DUNG)** Ban them tool `weather.get` qua `install(kernel)` giong `llm_chat`. No co **tu** co observability (event `tool.*`, envelope, lineage) khong? Vi sao? — *Diem:* CO — vi no chui qua cung `execute_tool` chokepoint (I1+I5); observability ap o cua, khong phai per-tool. Day la chokepoint Phase 1 tra co tuc. Neu ban viet `weather.get` goi network truc tiep khong qua cua → mat het, dung sai pattern.

## 7. Prompt cham hieu cho Claude

```
Toi tra loi the nay:
- I5: [...]
- I6: [...]
- I7: [...]
- Cau van dung (them tool weather.get): [...]

Dua tren Phase 2 (plans/260626-1358-clone-hex-agent-roadmap/phase-2-llm-discipline.md)
va invariant I5-I7, cham toi da hieu chua. Voi moi cau: dung/sai, chi cho ho diem nao
(neo file:line that, vd nodes.py:66-84, budget.py:44-46, json_gate.py:475). Toi co dat
muc ≥6/8 va dung ca 3 cau I5/I6/I7 khong? Co nen cho qua sang Phase 3 khong? Neu khong,
chi ro toi phai doc lai muc nao cua roadmap va chay lenh tu kiem nao.
```

---

← phase truoc: [phase-1-build-workflow.md](phase-1-build-workflow.md) · → phase sau: [phase-3-build-workflow.md](phase-3-build-workflow.md) · Roadmap goc: [phase-2-llm-discipline.md](../phase-2-llm-discipline.md)
