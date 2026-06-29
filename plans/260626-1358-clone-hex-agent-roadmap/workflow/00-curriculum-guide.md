---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Curriculum build-along hex_agent — cách học qua skill + công hiệu

> **Cho ai:** người học vừa **dùng skill `/hs:*`** để dựng lại `hex_agent` theo 7 phase,
> vừa **tự kiểm tra hiểu biết** (công hiệu) trước khi sang phase kế.
> **Đặt trên:** roadmap [`../README.md`](../README.md) + `phase-1..7-*.md`.
> **Quy tắc vàng:** một phase chỉ **DONE** khi **DoD test xanh** *và* **giải thích được invariant** — thiếu một, chưa qua.

---

## 0. Curriculum này vận hành thế nào (đọc trước)

Hai trục song song, mỗi phase chạy cả hai:

1. **Trục BUILD** — bạn theo `phase-N-build-workflow.md` (tầng này) + `../phase-N-*.md` (roadmap),
   dùng vòng lặp chuẩn ở §1 để biến mỗi epic thành **code chạy được + test xanh**.
2. **Trục HIỂU (công hiệu)** — sau khi test xanh, bạn phải **giải thích được invariant** của phase
   (bảng I1..I17 trong [`../README.md`](../README.md) §2). Quiz ở §5 chấm trục này.

**Cơ chế nền — gate đọc artifact, không tin lời kể.** Mọi kết luận "xong/pass" phải neo vào **artifact JSON
trên filesystem** (verification.json, review-decision.json, plan-approval.json) hoặc **output lệnh chạy trong
chính turn này** — không phải "chắc là chạy được". Đây là luật của cả harness lẫn curriculum.

**Một phase = một năng lực mới, qua một cửa đã có.** Không nhảy cóc. Đóng phase trước khi mở phase sau.

---

## 1. Vòng lặp chuẩn "học + build một phase" (the universal loop)

Mỗi phase chạy hết bảng này theo thứ tự. Cột **Skill/Invoke** là lệnh `/hs:*` thật; cột **Artifact** là
file thật ghi ra; cột **Gate** là điều kiện qua bước. Bỏ qua bước có dấu *(tuỳ chọn)* khi không cần.

| # | Bước | Skill | Invoke | Artifact (path thật) | Gate (qua khi) | Rollback |
|---|---|---|---|---|---|---|
| 0 | *(tuỳ chọn)* Hiểu vấn đề mơ hồ | `hs-research:discover` | `/hs-research:discover "<vấn đề>"` | `plans/<slug>/discovery-brief.md` | Chốt 1 hướng + liệt kê open questions (no hard gate) | Frame không hội tụ → `hs-think:problem-solving` rồi quay lại. Bỏ qua nếu yêu cầu đã rõ |
| 1 | *(tuỳ chọn)* Hiểu vùng code lạ | `hs:understand` | `/hs:understand <path>` | `plans/reports/<slug>-report.md` | Map đủ để plan; trả abs-path + unknowns | Còn quá nhiều unknown → scout sâu hơn / hỏi user |
| 2 | Định vị file/pattern | `hs:scout` | `/hs:scout` | `plans/reports/<scope>-<YYMMDD-HHMM>-<slug>-report.md` | Report tồn tại trong `plans/reports/`; có "Relevant files" + "Open questions" | Open questions load-bearing chưa đóng → mở rộng scope scout |
| 3 | *(tuỳ chọn)* Bàn hướng trước khi chốt | `hs-think:brainstorm` | `/hs-think:brainstorm "<q>" [--diverge\|--converge\|--critique]` | `plans/reports/<slug>-<YYMMDD-HHMM>-brainstorm-report.md` (+ DEC nếu chốt kiến trúc) | Mỗi option có trade-off (Evidence Filter); chốt 1 hướng | Chốt mà thiếu trade-off → vi phạm Evidence Filter, làm lại. ≥2 hướng đo-được không tách → `hs-think:bakeoff` |
| 4 | Lập plan có kiểm chứng | `hs:plan` | `/hs:plan [fast\|hard] [--tdd]` | `plans/<YYMMDD-HHMM>-<slug>/plan.md` + `phase-NN-*.md` | 0 mâu thuẫn sau consistency sweep; mọi `[UNVERIFIED]` đã resolve | Red-team tìm failure mode có file:line → sửa plan rồi red-team lại |
| 5 | **Phê duyệt plan (HUMAN #1)** | `hs:plan` | AskUserQuestion [Review / Approve / Reject] | `plans/<slug>/artifacts/plan-approval.json` | **reviewer ≠ author** và `plan_hash` chưa trôi | annotated → sửa plan rồi RE-GATE. Reject → quay về `hs:plan`. Approve → `/clear` rồi `/hs:cook <abs-path>` |
| 6 | Thực thi phase (TDD red→green) | `hs:cook` | `/hs:cook <abs-plan-path> [--phase <id>] [--parallel]` | `plans/<slug>/artifacts/verification.json` (+ `review-decision.json` per-phase) | Suite green 100%; mỗi AC có evidence file:line; không lỗi lint/type mới | Test đỏ → sửa **code** (không xoá/skip/làm yếu test). Lệch plan → STOP hỏi |
| 7 | Chạy & kiểm chứng test | `hs:test` | `/hs:test [unit\|integration]` | `verification.json` (verdict + checks[]) + QA report | **100% pass**; bất kỳ check FAIL → hard stage bị chặn | Có failure → `hs:fix` (1 bug) hoặc `hs:cook` (fix), regression test viết **trước** fix |
| 8 | Review code (gate) | `hs:code-review` | `/hs:code-review [--pending\|<#PR\|commit>] [--fix] [--spec <plan>]` | `plans/<slug>/artifacts/review-decision.json` | Verdict **PASS chính xác** (PASS_WITH_RISK vẫn chặn hard stage) | Verdict ≠ PASS → STOP; với `--fix` delegate `hs:fix` → re-review (tối đa 3 vòng) |
| 9 | *(khi có bug)* Tìm root cause | `hs:debug` | `/hs:debug [--system\|--perf\|--bisect]` | `plans/reports/<slug>-debug-report.md` + failing repro test | Có **failing repro test** (không test = debug chưa xong) | 3+ giả thuyết fail → STOP, xem lại kiến trúc (có thể `hs-think:brainstorm`) |
| 10 | *(khi có test đỏ)* Fix bug | `hs:fix` | `/hs:fix [quick\|standard\|deep]` | `verification.json` + báo cáo root cause | Test RED→GREEN, full suite pass, verdict ≠ BLOCKED | 3 lần fix fail → STOP, đặt lại câu hỏi kiến trúc với user |
| 11 | **Ship (HUMAN #2, gated)** | `hs:ship` | `/hs:ship [official\|beta] [--dry-run]` | tiêu thụ 3 artifact: `verification.json`+`review-decision.json`+`plan-approval.json`; ra PR URL | gate_stage.py: ship requires cả 3, verdict đạt policy, hash không trôi | Artifact thiếu/drift → điều tra artifact (KHÔNG sửa hook). review ≠ PASS → AskUserQuestion |
| 12 | *(tuỳ chọn)* Ghi tri thức | `hs-mem:remember` / `hs-mem:journal` | `/hs-mem:remember` · `/hs-mem:journal` | `docs/decisions.md` (DEC) / `docs/journals/YYYY-MM-DD-<slug>.md` | Human duyệt từng entry; mỗi fact 1 home | Không có gì đáng giữ → ghi 0 entry |

**Trong curriculum, một phase tối thiểu chạy:** scout (2) → plan (4) → approve (5) → cook (6) → test (7) → review (8).
Bước 0/1/3 dùng khi vùng code lạ hoặc hướng chưa rõ; 9/10 khi có bug; 11 khi gom nhiều phase thành PR.

---

## 2. Kỷ luật ĐỌC ARTIFACT để quản lý

Artifact là **nguồn sự thật**, không phải lời kể. Với mỗi loại: đọc mục nào, "đang ổn" trông ra sao, red flag, hành động.

> **Luật vàng để KHÔNG ngộp:** đừng đọc JSON thô để quản lý. JSON (`verification.json`, `review-decision.json`,
> `plan-approval.json`) là cho **máy gate** (`gate_stage.py`), không phải cho mắt người. Để quản lý, **render nó**:
> - Toàn cảnh mọi phase: `python plans/260626-1358-clone-hex-agent-roadmap/workflow/status.py` (xem §9 + [`STATUS.md`](STATUS.md)).
> - Một file, hiểu sâu: `/hs:explain plans/<slug>/artifacts/verification.json` hoặc prompt 1-dòng "tóm tắt thành: stage, verdict, check nào FAIL, hành động".
>
> Phần dưới mô tả *field nào quan trọng* để bạn (và `status.py`) biết đường suy — không phải lệnh "ngồi đọc JSON".

### plan.md — hợp đồng thực thi cho cook
- **Path:** `plans/<YYMMDD-HHMM>-<slug>/plan.md` (vd `plans/260626-0347-control-plane-harness-ports/plan.md`)
- **Đọc:** frontmatter `status:` (chỉ `approved` + tên người duyệt mới được cook) → bảng **Phases** (tiến độ tổng) →
  **Acceptance (plan-level)** (định nghĩa "xong" — mỗi AC phải là **lệnh chạy được**) → **Out of scope** → **Locked decisions** (LD).
- **Đang ổn:** `status: approved`, mọi AC là lệnh (pytest/smoke), có Rollback per-phase, claim "Hiện trạng" neo file:line.
- **🔴 Red flag:** `status: draft` mà đã cook · AC viết chung chung ("hoạt động đúng") không chạy được ·
  claim không file:line hoặc còn `[UNVERIFIED]` · phase đụng file lõi (`kernel.py`) mà risk ghi "low".
- **Hành động:** AC mơ hồ → quay lại `hs:plan` viết lại thành lệnh. `[UNVERIFIED]` chưa đóng → resolve trước khi cook.

### verification.json — bằng chứng từ chạy suite
- **Path:** `plans/<slug>/artifacts/verification.json` · schema `harness/schemas/artifact-verification.json`
- **Shape:** `{ stage, plan, actor, ts, checks[]{name,status PASS|FAIL|SKIP,detail}, verdict PASS|PASS_WITH_RISK|BLOCKED }`.
- **Đọc:** `verdict` trước → duyệt **từng** `checks[]`: `detail` phải có command-output thật (vd `pytest → 345 passed, exit 0`,
  commit SHA, `CORE_AGENT_SMOKE_OK run_id=...`). `detail` thường ánh xạ 1-1 với AC plan-level (full_suite, smoke, lint).
- **Đang ổn:** verdict PASS + mọi check PASS + detail neo output/exit-0/SHA thật.
- **🔴 Red flag:** **bất kỳ** check `FAIL` → hard stage bị chặn · verdict PASS nhưng có check FAIL (tự-báo-PASS gian dối) ·
  detail rỗng / không có output thật (UNVERIFIABLE) · PASS_WITH_RISK mà không nêu file/function cụ thể.
- **Hành động:** check FAIL → `hs:fix`/`hs:debug`, không sửa artifact. detail rỗng → chạy lại lệnh, dán output thật.

### review-decision.json — verdict review code → gate ship
- **Path:** `plans/<slug>/artifacts/review-decision.json` · schema `harness/schemas/artifact-review-decision.json`
- **Shape:** `{ verdict, reviewer, role, rationale, ts, [plan_hash], [ticket_id] }`.
- **Đọc:** `verdict == "PASS"` (đúng chữ, **không** phải PASS_WITH_RISK) mới là giấy phép ship. `rationale` cho biết
  reviewer đã kiểm gì (gate quantifier, idempotent, không KeyError, số test xanh + smoke + ruff) và finding nào còn (LOW/INFO).
- **Đang ổn:** verdict PASS, rationale liệt kê cái đã confirm sound + finding LOW/INFO không block + số test/smoke thật.
- **🔴 Red flag:** verdict BLOCKED → chặn pr/ship/deploy · PASS_WITH_RISK bị nhầm là "ship license" (sai: hard stage vẫn đòi PASS) ·
  `reviewer` trùng author (presence gate không bắt — phải tự soi, authz=attribution) · rationale chỉ "LGTM" không nêu kiểm gì.
- **Hành động:** verdict ≠ PASS → STOP. PASS_WITH_RISK → AskUserQuestion (fix now / accept risk / cancel).

### plan-approval.json — chữ ký duyệt plan (HUMAN #1)
- **Path:** `plans/<slug>/artifacts/plan-approval.json` (vd `plans/260625-2123-docs-diataxis-restructure/artifacts/plan-approval.json`)
- **Shape:** `{ schema:"plan-approval/v1", plan, plan_hash, file_hashes{plan.md+phase-*.md}, author, reviewer, verdict:"APPROVED", rationale, ts }`.
- **Đọc:** `verdict APPROVED` + `plan_hash`/`file_hashes` ⇒ plan đã khoá, cook được. `plan_hash` phát hiện **plan-drift**:
  nếu plan.md đổi sau duyệt, hash lệch ⇒ approval cũ vô hiệu, phải duyệt lại.
- **Đang ổn:** verdict APPROVED, `reviewer ≠ author`, hash khớp plan.md hiện tại, rationale nêu trade-off đã chấp nhận.
- **🔴 Red flag:** `author == reviewer` (không tách vai — `plan_approval.py` ép luật role nên đây là điểm cần soi) ·
  `plan_hash` trong artifact khác hash plan.md hiện tại (drift) · verdict ≠ APPROVED nhưng vẫn cook.
- **Hành động:** drift → duyệt lại. author==reviewer → đổi reviewer khác người, ghi lại qua `plan_approval.py`.

### Report (scout/brainstorm/research) — bản đồ & hướng
- **Path:** `plans/reports/<scope>-<YYMMDD-HHMM>-<slug>-report.md` (vd `architecture-map-260625-2009-hex-agent-report.md`).
- **Đọc:** **Relevant files** trước (input cho plan/debug/fix) → **Open questions** (cái scout CHƯA biết, phải đóng trước plan).
  Brainstorm/research thêm bảng có cột **Evidence (file:line)** + **Decision/Verdict** (Port now / Defer / YAGNI).
- **Đang ổn:** mọi claim/finding neo `file:line`; có cột Decision right-sized; có mục "Out of scope".
- **🔴 Red flag:** finding không file:line → downstream REJECT (coi như không tồn tại) · `[FALLBACK_INTERNAL]` (chỉ scan nội bộ) ·
  path trỏ file không tồn tại (bản đồ stale) · chốt bằng analogy/cảm tính, Evidence rỗng → evidence debt, phải tag `[UNVERIFIED]`.

### DEC-x — sổ cái quyết định kiến trúc
- **Path:** `docs/decisions.md` (DEC-1, DEC-2, …); plan.md trỏ qua field `decision: DEC-x` + `source_report`.
- **Đọc:** khi artifact nói "theo DEC-x": đọc `affects` (đụng file nào) + thân (hướng nào bị **LOẠI** và vì sao). `status: active` = còn hiệu lực.
- **🔴 Red flag:** DEC `active` nhưng thực tế đã bị thay thế (map-drift) · audit/red-team đòi đảo ngược DEC chỉ bằng
  abstract concern (không evidence mới) → **vi phạm luật sticky-decision**: phải trình lại cho user, không tự sửa.

---

## 3. Giao thức CỔNG (gate) — phase chỉ ĐÓNG khi cả hai cột xanh

Một phase **đóng** khi đạt **cả hai**, thiếu một là **chưa qua**:

**(a) DoD test xanh** — bằng chứng máy:
```bash
python run_smoke.py            # phải in: CORE_AGENT_SMOKE_OK
python -m pytest -q            # phải xanh hết (0 fail)
```
→ kết quả phải vào `verification.json`: `verdict: PASS` + mọi `checks[].status == PASS`, `detail` neo output thật.
Mỗi AC của epic → ≥1 test (xem DoD từng phase ở `../README.md` §1).

**(b) Công hiệu đạt** — bằng chứng người: bạn **giải thích được invariant** của phase (I# tương ứng, `../README.md` §2):
*luật là gì → file·hàm nào thực thi → phá ra thì mất gì*. Đạt = quiz §5 ≥ **70%** và nói trôi chảy được câu "phá ra mất gì".

> **Luật gate cốt lõi (đồng bộ với harness):**
> - Artifact là NGUỒN, không phải lời kể. Claim không file:line/command → UNVERIFIABLE → downstream loại.
> - Hard stage (push/pr/ship/deploy) đòi verdict **đúng "PASS"**; PASS_WITH_RISK là soft-accept có ý thức, KHÔNG phải ship license.
> - Bất kỳ check FAIL → hard stage bị chặn (`gate_stage.py` đọc từ đĩa, fail-closed).
> - **Iron Law:** không claim "done/passing" nếu chưa chạy lệnh chứng minh **trong chính turn này**.
> - actor/reviewer = ATTRIBUTION, không tự-duyệt; role check thật nằm ở `plan_approval.py`, không ở presence gate.

---

## 4. Giao thức QUAY LẠI (rollback bắt buộc)

| Trigger | Hành động (không bỏ qua) |
|---|---|
| Test đỏ khi cook/test | `/hs:debug` (tìm root cause + viết failing repro test) → `/hs:fix` (RED→GREEN). **KHÔNG** xoá/skip/làm yếu test |
| `verification.json` có check FAIL | STOP. Sửa **code**, không sửa artifact. Chạy lại đến khi mọi check PASS |
| `review-decision.json` verdict ≠ PASS | STOP. PASS_WITH_RISK → AskUserQuestion (fix/accept/cancel). BLOCKED → `hs:fix` → re-review (≤3 vòng) |
| **Không giải thích được invariant I#** | KHÔNG sang phase kế. Đọc lại `../phase-N-*.md` + bảng I# (`README.md` §2) + artifact liên quan, làm lại quiz |
| Quiz < 70% | Đọc lại phase + chạy lại lệnh tự kiểm chứng (§0 README) để thấy invariant **bằng mắt**, rồi quiz lại |
| Lệch khỏi plan khi cook | STOP, hỏi user. Side-effect bất ngờ → AskUserQuestion 2-4 lựa chọn |
| Plan drift (hash lệch) sau approve | Duyệt lại plan qua `plan_approval.py` (reviewer ≠ author) trước khi cook tiếp |
| `plan-approval.json` author==reviewer | Đổi reviewer khác người; ghi lại qua `plan_approval.py` (CLI ép luật role) |
| Red-team/critique tìm failure có repro | Sửa plan/code rồi chạy lại bước đó; không sang bước sau khi chưa đóng |
| 3 lần fix fail / 3+ hypothesis fail | STOP, đặt lại câu hỏi kiến trúc với user (có thể `hs-think:brainstorm`) |

**Luật xương sống:** rollback **đi ngược đúng một bước**, đóng nó, rồi mới tiến. Không "nhảy qua" một gate đỏ.

---

## 5. Câu hỏi kiểm tra hiểu (quiz công hiệu)

Mỗi phase có quiz neo vào invariant của phase đó. Mẫu (chi tiết đầy đủ trong từng `phase-N-build-workflow.md`):

- **Phase 1 (I1–I4):** Vì sao mọi LLM/tool phải qua đúng `execute_tool`? `freeze()` ngăn điều gì? State theo-run sống ở đâu để hai run không nhiễm chéo? Event mang lineage gì?
- **Phase 2 (I5–I7):** Vì sao LLM là một capability chứ không phải đường tắt? "Đúng một action mỗi vòng" (JSON gate) ngăn điều gì? Ba cái chặn loop của budget?
- **Phase 3 (I8–I9):** path-jail dùng hàm gì để chặn traversal? Vì sao retry phải biết idempotency? Tool nào cần qua policy gate?
- **Phase 4 (I10–I12):** Vì sao resume đọc SQLite chứ không `checkpoint.json`? Nhét object thường vào state thì vỡ ở đâu? Vì sao mỗi nhánh graph kết thúc đúng một lần?
- **Phase 5:** Skill progressive-disclosure render thế nào? RAG `health/ingest/search` qua cửa nào? Vì sao suite offline không cần docker?
- **Phase 6 (I13–I15):** Vì sao delegation là chokepoint RIÊNG, không phải method kernel? `scope con ⊆ scope cha` thực thi ở đâu? Acceptance honor evidence thật nghĩa là gì?
- **Phase 7 (I16–I17):** Redact xảy ra trước hay sau khi payload ra SSE? `attribution ≠ authz` — vì sao không tin `issued_by`?

**Cách tự chấm:** với mỗi câu, trả lời theo khuôn *luật → file·hàm → phá ra mất gì*. Đúng cả ba mệnh đề = 1 điểm.

**Prompt mẫu nhờ Claude chấm:**
> "Chấm câu trả lời quiz Phase N của tôi theo bảng invariant trong `plans/260626-1358-clone-hex-agent-roadmap/README.md` §2.
> Với mỗi câu cho điểm 0/0.5/1 theo *luật → file·hàm → phá ra mất gì*; chỉ ra mệnh đề nào sai/thiếu, neo file:line thật trong repo. Tổng %, đạt nếu ≥70%."

**Mức đạt:** ≥ **70%** mỗi phase. < 70% → rollback (§4): đọc lại phase + chạy lệnh tự kiểm chứng, rồi quiz lại. Không sang phase kế.

---

## 6. Bảng điều khiển học tập (progress ledger)

Mặt quản lý **sống** là [`STATUS.md`](STATUS.md) — mở nó để thấy: đang ở phase/bước nào, gate máy + gate hiểu,
và **AC checklist từng phase** ("đạt hoàn toàn AC" = tick hết 3 nhóm Build·DoD·Hiểu). Gate máy do `status.py` điền
(§9); gate hiểu bạn tự tick sau quiz. Bảng dưới là bản rút gọn cùng cấu trúc. **Done = CẢ HAI cột xanh.**

| Phase | DoD test xanh? (smoke+pytest+verification PASS) | Công hiệu đạt? (quiz ≥70%, giải thích I#) | Ngày | Ghi chú (commit SHA / bug / câu sai) |
|---|---|---|---|---|
| 1 — Microkernel + chokepoint (E01,E04) | ☐ | ☐ | | |
| 2 — LLM discipline (E03,E02) | ☐ | ☐ | | |
| 3 — Toolbox + safety jail (E06) | ☐ | ☐ | | |
| 4 — Graph + resume (E05) | ☐ | ☐ | | |
| 5 — Skills + RAG (E07,E08) | ☐ | ☐ | | |
| 6 — Roles + delegation (E09,E10) | ☐ | ☐ | | |
| 7 — Control plane realtime (E21) | ☐ | ☐ | | |

> **Quy tắc:** một dòng chỉ ✔ khi cả hai cột ✔. Một cột ✔ = phase **chưa xong** → quay lại §4. Ghi commit SHA thật vào "Ghi chú" (Iron Law: bằng chứng, không lời kể).

---

## 7. Cheat-sheet skill theo tình huống

| Khi bạn cần… | Dùng | Invoke |
|---|---|---|
| Vấn đề mơ hồ, chưa biết hướng | `hs-research:discover` | `/hs-research:discover "<vấn đề>"` |
| Hiểu vùng code lạ trước khi plan | `hs:understand` | `/hs:understand <path>` |
| Định vị nhanh file/pattern | `hs:scout` | `/hs:scout` |
| Bàn 2-3 hướng + trade-off trước khi cam kết | `hs-think:brainstorm` | `/hs-think:brainstorm "<q>" [--diverge\|--converge\|--critique]` |
| Tấn công 1 artifact bằng nhiều lens | `hs-think:critique` | `/hs-think:critique <artifact> [--gate\|--advisory]` |
| Lập plan có kiểm chứng (feature/refactor) | `hs:plan` | `/hs:plan [fast\|hard] [--tdd]` |
| Thực thi plan ĐÃ duyệt, từng phase TDD | `hs:cook` | `/hs:cook <abs-plan-path> [--phase <id>] [--parallel]` |
| Chạy & kiểm chứng test (100% pass là gate) | `hs:test` | `/hs:test [unit\|integration]` |
| Review rủi ro production (bug/regression/security) | `hs:code-review` | `/hs:code-review [--pending\|<#PR\|commit>] [--fix] [--spec]` |
| Có bug/test fail → tìm root cause (không fix) | `hs:debug` | `/hs:debug [--system\|--perf\|--bisect]` |
| Có test đỏ/error rõ → fix theo flow | `hs:fix` | `/hs:fix [quick\|standard\|deep]` |
| Bug được báo → điều phối reproduce→classify→gate | `hs:triage` | `/hs:triage` |
| Branch xong → thành PR (gate cao nhất) | `hs:ship` | `/hs:ship [official\|beta] [--dry-run]` |
| Review GitHub PR đầy đủ | `hs:review-pr` | `/hs:review-pr [--fix] [--reply]` |
| ≥2 hướng đo-được (latency/size/%pass) không tách | `hs-think:bakeoff` | `/hs-think:bakeoff` |
| Report/giải thích đúng nhưng khó "thấm" | `hs:explain` | `/hs:explain [file\|section]` |
| Vẽ workflow/kiến trúc bằng diagram | `hs-viz:preview` | `/hs-viz:preview` |
| Commit/push/PR theo conventional commit | `hs:git` | `/hs:git` |
| Vừa chốt quyết định kiến trúc / nhận feedback | `hs-mem:remember` | `/hs-mem:remember [--since <ref>]` |
| Ghi journal sau ship/cook/incident | `hs-mem:journal` | `/hs-mem:journal [topic]` |
| Không chắc skill nào hợp / xem full catalog | `hs-meta:find-skills` | `/hs-meta:find-skills` |

---

## 8. 7 phase nối nhau thế nào

Đường găng (chuỗi phụ thuộc dài nhất): **Phase1 → Phase2 → Phase4 → Phase6**.
Phase 3 song song được sau Phase 1; Phase 5 rẽ nhánh sau Phase 3; Phase 7 sau Phase 6.

```
                       ┌──────── Phase 3 (toolbox+safety, E06) ───┐
                       │                                          ▼
Phase 1 ──► Phase 2 ───┤                                   Phase 5 (skills+RAG, E07,E08)
(kernel+   (LLM         │                                          │
 chokepoint  discipline,└──► Phase 4 (graph+resume, E05) ──► Phase 6 (roles+delegation, E09,E10) ──► Phase 7
 E01,E04)    E03,E02)                                                                                (control plane, E21)
```

**Handoff giữa phase = artifact của phase trước là input của phase sau.** Mỗi phase chỉ mở khi **cổng vào (deps) đủ**
và đóng khi **DoD test xanh + công hiệu đạt** (§3). Cụ thể: chokepoint Phase 1 là cửa mọi capability sau cắm vào;
state-serializable Phase 4 là tiền đề resume; delegation-chokepoint Phase 6 là tiền đề control plane Phase 7.

Link tới workflow từng phase (tầng này):
[`phase-1-build-workflow.md`](phase-1-build-workflow.md) ·
[`phase-2-build-workflow.md`](phase-2-build-workflow.md) ·
[`phase-3-build-workflow.md`](phase-3-build-workflow.md) ·
[`phase-4-build-workflow.md`](phase-4-build-workflow.md) ·
[`phase-5-build-workflow.md`](phase-5-build-workflow.md) ·
[`phase-6-build-workflow.md`](phase-6-build-workflow.md) ·
[`phase-7-build-workflow.md`](phase-7-build-workflow.md)

---

## 9. Quản lý human-readable — `status.py` + `STATUS.md` (đừng theo dõi bằng JSON thô)

Đây là tầng trả lời câu "theo dõi artifact có khó / có human-readable không". Câu trả lời thiết kế: **có 1 mặt
quản lý, mọi JSON được render về đó.**

**`status.py` — render mọi artifact gate thành 1 màn hình người-đọc-được.** Chạy từ repo root:
```bash
python plans/260626-1358-clone-hex-agent-roadmap/workflow/status.py
```
Nó quét `plans/*/artifacts/{plan-approval,verification,review-decision}.json`, in mỗi plan một khối:
```
▌ <slug>
  plan-approval: ✓ APPROVED  (author=… reviewer=…)
  verification : ✓ PASS           (checks: 13✓ 0✗ 0–)
  review       : ✓ PASS           (reviewer=… role=…)
  -> TONG: ✓ SAN SANG SHIP (ca 3 giay phep xanh)
  🔴 <cờ đỏ nếu có: check FAIL/verdict PASS gian dối · author==reviewer · detail rỗng · PASS_WITH_RISK>
```
Đọc đúng **dòng `-> TONG:`** (SẴN SÀNG SHIP / ĐANG BỊ CHẶN / CHƯA ĐỦ) + **dòng 🔴**. Đó là toàn bộ trạng thái gate
máy của dự án, không cần mở một file JSON nào. Script **offline, stdlib, luôn exit 0** (báo cáo, không phải gate).

**`STATUS.md` — mặt quản lý duy nhất bạn nhìn vào.** Gồm: (A) bảng tổng 7 phase × vòng lặp 6 bước × 2 gate;
(B) **AC checklist từng phase** để biết "đạt hoàn toàn AC" tới đâu; (C) cách làm mới. Quy trình mỗi lần ngồi vào:
chạy `status.py` → chép verdict vào §A `STATUS.md` → tự tick gate hiểu sau quiz → một dòng chỉ ✔ khi **cả hai** gate ✔.

**Một file, muốn hiểu sâu thay vì lướt:** `/hs:explain plans/<slug>/artifacts/<file>.json` — biến JSON dày thành lời
giải thích "cái gì đỏ, vì sao, làm gì". Dùng khi `status.py` báo cờ đỏ mà bạn chưa rõ gốc.

> Vì sao thiết kế thế này quản lý được: gate máy **tự render** (không phụ thuộc trí nhớ/đọc tay), gate người **một
> chỗ tick** (`STATUS.md`), AC **phẳng và đếm được** (3 nhóm/phase). Bạn luôn trả lời được trong 10 giây: *đang ở đâu,
> cái gì chặn, còn bao nhiêu AC.*

---

*Roadmap gốc: [`../README.md`](../README.md). Bắt đầu build: [Phase 1 — Microkernel & chokepoint](../phase-1-microkernel-chokepoint.md) + [`phase-1-build-workflow.md`](phase-1-build-workflow.md). Mặt quản lý: [`STATUS.md`](STATUS.md) + `status.py`.*
