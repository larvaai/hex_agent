---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 3 — Workflow build-along: Toolbox, Safety jail & middleware

> Cặp với: roadmap [phase-3-toolbox-safety.md](../phase-3-toolbox-safety.md) · Epic E06 · Invariant I8,I9 · Mục tiêu: vừa BUILD vừa HIỂU phase này qua skill + cổng

## 0. Bạn sẽ rời phase này khi

**Build được (X):**
- `safety/sandbox.py::resolve_in_workspace()` giam mọi path về `var/workspace`; traversal raise `SandboxError`.
- `safety/policy.py::SafeToolPort` bọc mọi tool toolbox; `classify_terminal` chặn shell/destructive/git/path-escape.
- 6 fs tool + terminal + lint_test + code_index, mỗi tool jail trước, descriptor `kind/idempotent/risk` đúng.
- 5 middleware (`timing/policy/budget/retry/condense`), wire 4 cái ở `core/bootstrap.py::_install_middleware` theo order ngoài→trong, **budget cố ý không wire**.
- DoD: `python -m pytest tests/test_safety.py tests/test_toolbox.py tests/test_middleware.py tests/test_file_editor.py tests_audit/test_toolbox_sandbox_rigor.py tests_audit/test_security_boundaries.py -q` xanh 100%, không file nào sinh ngoài `var/workspace`.

**Giải thích được (Y):**
- I8 theo *luật → file·hàm → phá ra mất gì*: jail là lớp vật lý, không đoán ý đồ — thu hẹp không gian path khả thi (`sandbox.py:46`).
- I9: một-cửa-safety = một nơi để vá; mở rộng luật chỉ ở `ToolPolicy.check` (`policy.py:88`), không rải per-tool.
- Vì sao middleware order là `timing→policy→budget→retry→condense`, vì sao `retry` trong cùng, vì sao `BudgetGuard` không wire ở kernel (`bootstrap.py:30`).
- Vì sao tool effect PHẢI khai `idempotent: False` (`feature.py:40`) — mắt xích yếu của Retry là *descriptor sai*, không phải retry sai.

Chưa giải thích được → quay lại §4-§5, KHÔNG sang Phase 4.

## 1. Ý tưởng triển khai khả thi (đọc là biết làm gì)

Bốn lát cắt cụ thể, neo thẳng vào roadmap. Mỗi lát kèm "ra cái gì để biết xong".

**Ý 1 — Path-jail là một hàm, không phải rải khắp tool.** Viết `resolve_in_workspace()` (`sandbox.py:46`): `_reject_foreign_path_syntax()` (`sandbox.py:25`) chặn syntax Windows *lexically trước* `resolve()`, rồi ép relative về `workspace`, `resolve()`, kiểm `is_relative_to(workspace)`. Điểm tinh tế: trên POSIX `..\escape` là tên file hợp lệ và `C:/x` là *relative* → nếu không reject up-front, `resolve()` giữ chúng *trong* workspace. → **Ra:** `resolve_in_workspace("../../etc/passwd")` raise `SandboxError`; `"sub/file.txt"` trả `var/workspace/sub/file.txt`.

**Ý 2 — SafeToolPort là chokepoint một-cửa.** Viết `SafeToolPort.execute` (`policy.py:113`): gọi `ToolPolicy.check(name, args)` (`policy.py:88`) *trước*; nếu `not allowed` → trả envelope `policy_blocked=True` + `policy_code` + `error`, **không** chạm `inner`. `classify_terminal` (`policy.py:53`) chứa luật terminal: `SHELL_EXES` (bash/sh/zsh...), `SHELL_TOKENS` (`| & ; > $( &&`), `rm/dd/mkfs`, git mutation, argv path tuyệt đối ngoài workspace. Mở rộng luật = sửa duy nhất `ToolPolicy.check`. → **Ra:** `SafeToolPort("x", inner).execute(req)` với `terminal_run argv=["bash","-c",...]` → `policy_blocked=True`, `inner` không gọi.

**Ý 3 — Terminal: argv-no-shell + timeout + defense-in-depth.** Viết `Terminal.execute` (`terminal.py:15`): nhận `argv` *là list*, `subprocess.run([...], cwd=workspace, timeout=...)` — không `shell=True`. `timeout` clamp `1..30s` (`terminal.py:29`). Tool **tự** gọi `classify_terminal` (`terminal.py:21`) *bên cạnh* SafeToolPort — kẻ gọi tool trực tiếp (bỏ port) vẫn bị chặn. → **Ra:** `argv=["python","-c","print(1)"]` ok; `argv=["sh","-c","ls"]` → `policy_blocked`; lệnh treo → `timeout after Ns`.

**Ý 4 — Wire chain + descriptor đúng.** `toolbox/feature.py::install` (`feature.py:67`): tạo `ToolPolicy()`, lặp `_TOOL_CLASSES`, đăng ký mỗi tool **đã bọc** `SafeToolPort(tool.name, tool, policy)` (`feature.py:74`) kèm descriptor từ `_DESCRIPTORS` (`feature.py:37`) — `fs_write` phải `{"kind":"effect","idempotent":False,...}` (`feature.py:40`). `_install_middleware` (`bootstrap.py:28`): `kernel.use(...)` theo `timing→policy→retry→condense`; kernel bọc `reversed` (`kernel.py:193`) nên order *gọi* = order *khai báo*. **`BudgetGuard` KHÔNG wire** (`bootstrap.py:30`) — counter per-run rò giữa run nếu sống cùng kernel. → **Ra:** `create_kernel()` → `kernel.execute_tool("fs_read", {"path":"x"})` chạy qua middleware + SafeToolPort + jail, không crash.

## 2. Workflow skill-by-skill (vòng lặp build)

| Bước | Skill (invoke thật) | Prompt mẫu (copy-được) | Artifact ra (path thật) | Mục đích |
|---|---|---|---|---|
| 1. Hiểu vùng | `/hs:scout` | `/hs:scout "Phase 3 E06: định vị safety/sandbox.py resolve_in_workspace, safety/policy.py SafeToolPort+classify_terminal, toolbox/feature.py install+_DESCRIPTORS, core/bootstrap.py _install_middleware. Liệt kê file:line thật + open questions về middleware order"` | `plans/reports/<scope>-<YYMMDD-HHMM>-toolbox-safety-report.md` | Neo file:line trước khi plan; đóng open questions load-bearing |
| 2. Bàn hướng (tùy chọn) | `/hs-think:brainstorm` | `/hs-think:brainstorm "Phase 3: đặt same-tool guard ở middleware BudgetGuard hay ở graph node per-run? Trade-off rò counter giữa run" --critique` | `plans/reports/<slug>-<YYMMDD-HHMM>-brainstorm-report.md` | Mỗi option có trade-off; chốt 1 hướng (roadmap đã chốt: graph node, `bootstrap.py:30`) |
| 3. Lập plan TDD | `/hs:plan hard --tdd` | `/hs:plan hard --tdd "Implement E06 theo plans/260626-1358-clone-hex-agent-roadmap/phase-3-toolbox-safety.md: sandbox jail (I8), SafeToolPort+classify_terminal (I9), 6 fs tool + terminal + lint_test + code_index, 5 middleware wire 4 ở bootstrap. AC = các lệnh self-check ở §3 roadmap + DoD §7"` | `plans/<YYMMDD-HHMM>-<slug>/plan.md` + `phase-NN-*.md` | 0 mâu thuẫn; mọi `[UNVERIFIED]` resolved; mỗi AC là lệnh chạy được |
| 4. Phê duyệt (HUMAN #1) | `/hs:plan` (AskUserQuestion) | (reviewer≠author duyệt plan trong phiên) | `plans/<slug>/artifacts/plan-approval.json` | `verdict:APPROVED` + `plan_hash` khớp plan.md mới được cook |
| 5. Cook red→green | `/hs:cook <abs-plan-path>` | `/hs:cook /Users/uspro/Desktop/namnson/hex_agent/plans/<slug>/plan.md --phase 3` | `plans/<slug>/artifacts/verification.json` (+`review-decision.json`) | Suite green 100%; mỗi AC có evidence file:line; jail/policy thật chặn |
| 6. Chạy test (gate) | `/hs:test unit` | `/hs:test unit` rồi đối chiếu DoD: `python -m pytest tests/test_safety.py tests/test_toolbox.py tests/test_middleware.py tests/test_file_editor.py tests_audit/test_toolbox_sandbox_rigor.py tests_audit/test_security_boundaries.py -q` | `verification.json` (verdict+checks[]) + QA report | 100% pass; bất kỳ check FAIL → hard stage chặn |
| 7. Review code (gate) | `/hs:code-review --spec <plan>` | `/hs:code-review --spec /Users/uspro/Desktop/namnson/hex_agent/plans/<slug>/plan.md "Soi I8/I9: tool fs mới có jail? terminal có shell=True? descriptor effect có idempotent:False? BudgetGuard có lỡ wire ở kernel?"` | `plans/<slug>/artifacts/review-decision.json` | Verdict chính xác `PASS` (PASS_WITH_RISK vẫn chặn) |
| 8. Debug (khi test đỏ) | `/hs:debug --system` | `/hs:debug --system "test_toolbox_sandbox_rigor đỏ: path X thoát workspace. Tìm root cause ở resolve_in_workspace/_reject_foreign_path_syntax, viết failing repro test"` | `plans/reports/<slug>-debug-report.md` + failing repro test | Có failing repro test trước khi fix |
| 9. Fix bug | `/hs:fix standard` | `/hs:fix standard "RED→GREEN cho repro jail-escape, KHÔNG nới lỏng/skip test; sửa logic jail không sửa test"` | `verification.json` + báo cáo root cause | RED→GREEN, full suite pass, verdict≠BLOCKED |
| 10. Ghi quyết định | `/hs-mem:remember` | `/hs-mem:remember "Phase 3 chốt: BudgetGuard không wire ở kernel (per-run counter); same-tool guard sống ở graph node — map bootstrap.py:30"` | cập nhật memory / `docs/decisions.md` | Không relitigate quyết định kiến trúc |

Curriculum tối thiểu: scout(1)→plan(3)→approve(4)→cook(5)→test(6)→review(7). Đỏ ở bước nào → debug(8)→fix(9).

## 3. Artifact: đọc & quản lý thế nào

**Report scout** — `plans/reports/<scope>-<YYMMDD-HHMM>-toolbox-safety-report.md`.
- *Là gì*: bản đồ file:line + open questions trước plan.
- *Đọc*: **Relevant files** (phải có `sandbox.py:46`, `policy.py:88,113`, `feature.py:74`, `bootstrap.py:30`) → **Open questions**.
- *Tốt*: mỗi finding có `file:line` thật; open questions về middleware order/budget đã đóng.
- *Đỏ*: finding không file:line · path stale · `[FALLBACK_INTERNAL]` → mở rộng scout, KHÔNG plan.

**plan.md** — `plans/<YYMMDD-HHMM>-<slug>/plan.md`.
- *Là gì*: kế hoạch kiểm chứng được.
- *Đọc*: frontmatter `status: approved` + tên reviewer → bảng Phases → **Acceptance (plan-level)**: mỗi AC là LỆNH CHẠY ĐƯỢC (vd `resolve_in_workspace("../../etc/passwd")` raise) → Out of scope (không graph/LLM) → Locked decisions.
- *Tốt*: AC ánh xạ 1-1 với self-check §3 roadmap + DoD §7.
- *Đỏ*: `status: draft` mà đã cook · AC chung chung ("an toàn hơn") không chạy được · `[UNVERIFIED]` chưa đóng → quay lại plan.

**plan-approval.json** — `plans/<slug>/artifacts/plan-approval.json`.
- *Là gì*: license để cook.
- *Đọc*: `verdict:"APPROVED"` + `plan_hash` khớp plan.md hiện tại + `author`≠`reviewer`.
- *Tốt*: hash khớp ⇒ plan chưa drift sau duyệt.
- *Đỏ*: `author==reviewer` (`plan_approval.py` ép luật) · hash lệch = plan-drift → duyệt lại, KHÔNG cook.

**verification.json** — `plans/<slug>/artifacts/verification.json` (schema `harness/schemas/artifact-verification.json`).
- *Là gì*: bằng chứng test xanh, NGUỒN không phải lời kể.
- *Đọc*: `verdict` → từng `checks[]{name,status,detail}`: `detail` phải neo output thật (`pytest → N passed, exit 0`).
- *Tốt*: mọi check `PASS`, detail có số liệu pytest 6 file DoD.
- *Đỏ*: bất kỳ check `FAIL` → hard stage chặn · `verdict:PASS` mà có check FAIL (gian dối) · detail rỗng = UNVERIFIABLE → STOP, sửa code không sửa artifact.

**review-decision.json** — `plans/<slug>/artifacts/review-decision.json` (schema `harness/schemas/artifact-review-decision.json`).
- *Là gì*: ship license của code review.
- *Đọc*: `verdict=="PASS"` đúng chữ; `rationale` nêu đã kiểm I8/I9 + finding LOW/INFO.
- *Tốt*: rationale chỉ rõ "đã kiểm jail ở filesystem/lint_test/code_index, descriptor effect idempotent:False".
- *Đỏ*: `BLOCKED` chặn ship · `PASS_WITH_RISK` ≠ license · reviewer trùng author · rationale chỉ "LGTM" → re-review.

**debug-report.md** — `plans/reports/<slug>-debug-report.md`.
- *Là gì*: root cause + repro khi test đỏ.
- *Đọc*: hypothesis → repro test file:line → fix đề xuất.
- *Tốt*: có failing repro test chạy được trước khi fix.
- *Đỏ*: 3+ hypothesis fail → STOP, xem lại kiến trúc jail.

## 4. Công hiệu (phải đạt mỗi sang phase kế)

Điều kiện (b) của giao thức cổng. Checklist — mỗi mục GIẢI THÍCH / CHỈ RA / CHẠY được:

- [ ] **(I8) Giải thích** vì sao jail không đoán ý đồ mà ép path → kiểm. **Chỉ ra** `resolve_in_workspace` (`sandbox.py:46`) + `_reject_foreign_path_syntax` (`sandbox.py:25`). **Chạy** `resolve_in_workspace("../../etc/passwd")` → `SandboxError`.
- [ ] **(I8) Chỉ ra** jail được áp tại `filesystem.py:21`, `lint_test.py`, `code_index.py:159` — không tool đụng đĩa nào bỏ qua. Phá ra: path traversal ghi `/etc/passwd`.
- [ ] **(I9) Giải thích** một-cửa-safety: luật sống duy nhất ở `ToolPolicy.check` (`policy.py:88`); **chỉ ra** `SafeToolPort.execute` (`policy.py:113`) check trước, mới gọi `inner`. **Chạy** `argv=["bash","-c",...]` → `policy_blocked=True`, inner không gọi.
- [ ] **(I9 defense-in-depth) Chỉ ra** terminal *tự* gọi `classify_terminal` (`terminal.py:21`) bên cạnh port. Phá ra: bỏ port vẫn phải an toàn.
- [ ] **(Retry/I7-liên đới) Giải thích** chuỗi: descriptor `kind/idempotent` (`feature.py:40`) → `kernel.py:173` gắn vào envelope.metadata → `Retry._retryable` (`retry.py:14`) tha non-idempotent effect. **Chỉ ra** mắt xích yếu = descriptor sai. Phá ra: `fs_write` retry 2 lần.
- [ ] **(Middleware order) Giải thích** `timing→policy→budget→retry→condense`: timing ngoài để đo cả retry; retry trong cùng để vòng lặp chỉ chạy lõi; **chỉ ra** `kernel.use` + `reversed` (`kernel.py:193`).
- [ ] **(Budget) Chỉ ra** `BudgetGuard` cố ý KHÔNG wire ở kernel (`bootstrap.py:30`) — counter per-run rò giữa run. **Chạy** DoD suite 6 file → 100% pass, không file ngoài `var/workspace`.

Quiz ≥70% (§6), bắt buộc đúng các câu I8/I9.

## 5. Quy tắc quay lại (rollback bắt buộc)

| Trigger cụ thể | Hành động |
|---|---|
| Không chỉ ra được jail trong `filesystem.py:21` / `code_index.py:159` cho 1 tool đụng đĩa | Quay lại §1 ý 1, đọc lại roadmap §3 bước 3+6, thêm `resolve_in_workspace` dòng đầu tool |
| `resolve_in_workspace("../../etc/passwd")` KHÔNG raise | `/hs:debug --system` tìm root cause ở `_reject_foreign_path_syntax`/`is_relative_to`, viết repro → `/hs:fix` |
| `policy_blocked` không xuất hiện cho `argv=["sh","-c",...]` | Quay lại §1 ý 2; kiểm `classify_terminal` `SHELL_EXES`/`SHELL_TOKENS` (`policy.py:53,56`) |
| DoD suite ĐỎ (bất kỳ trong 6 file) | `/hs:debug` (root cause + failing repro test) → `/hs:fix` RED→GREEN. KHÔNG xóa/skip/nới test. KHÔNG sang Phase 4 |
| `verification.json` có check `FAIL` | STOP; sửa code KHÔNG sửa artifact; chạy lại đến mọi check PASS |
| review `verdict≠PASS` | `PASS_WITH_RISK`→AskUserQuestion(fix/accept/cancel); `BLOCKED`→`/hs:fix`→re-review ≤3 vòng |
| Tool effect mới khai `idempotent: True` | Quay lại `_DESCRIPTORS` (`feature.py:37`), sửa thành `False` TRƯỚC khi xét logic retry |
| Lỡ wire `BudgetGuard` ở `bootstrap.py` | Gỡ wire; đọc lại roadmap §3 bước 8 + pitfall "Nhân đôi same-tool guard" |
| Plan drift sau approve (`plan_hash` lệch) | Duyệt lại qua `plan_approval.py` (reviewer≠author), KHÔNG cook bản drift |
| 3 lần fix fail / 3+ hypothesis fail | STOP, hỏi user, xem lại kiến trúc jail/policy |
| Quiz <70% hoặc không giải thích được I8/I9 | KHÔNG sang Phase 4; đọc lại `phase-3-toolbox-safety.md` §4-§5 + bảng I# README, chạy self-check, quiz lại |

## 6. Câu hỏi kiểm tra hiểu (tự chấm / nhờ Claude chấm)

Mục đậu: **≥6/8**, bắt buộc đúng Q1,Q2,Q3 (I8/I9 cốt lõi).

1. **(I8)** Vì sao `_reject_foreign_path_syntax` chặn `..\escape`/`C:/x` *trước* `resolve()` chứ không sau? — *Chấm:* trên POSIX chúng là tên file hợp lệ / relative → `resolve()` vô tình giữ *trong* workspace; fail-closed up-front (`sandbox.py:25`). Map I8.
2. **(I9)** Muốn thêm luật "chặn `curl` ra mạng" thì sửa ở đâu cho áp *mọi* tool, KHÔNG rải per-tool? — *Chấm:* `ToolPolicy.check` (`policy.py:88`) — một-cửa-safety. Sửa nhiều nơi = sai I9. Map I9.
3. **(I9)** `SafeToolPort.execute` gọi `inner` lúc nào? Nếu policy block thì `inner` có chạy không? — *Chấm:* chỉ gọi `inner` khi `decision.allowed`; block → trả `policy_blocked=True`, `inner` KHÔNG chạm (`policy.py:113`). Map I9.
4. **(Terminal/I9)** Vì sao `argv-no-shell` an toàn ngay cả với `argv=["echo","a; rm b"]`? — *Chấm:* không `shell=True` để diễn giải `;`, và `SHELL_TOKENS` bắt `;` trước khi tới subprocess (`policy.py:56`). Chặn cả hai đường.
5. **(Retry)** Chuỗi nào khiến `fs_write` lỗi KHÔNG bị retry chạy 2 lần? Mắt xích yếu là gì? — *Chấm:* descriptor `idempotent:False` (`feature.py:40`)→`kernel.py:173` gắn metadata→`retry.py:14` tha. Mắt xích yếu = *descriptor sai*, không phải retry.
6. **(Middleware order)** Vì sao `retry` đặt *trong cùng*, `timing` *ngoài cùng*? — *Chấm:* timing đo *toàn bộ* gồm retry; retry trong cùng để vòng lặp chỉ chạy lõi, không kích hoạt lại timing/policy mỗi lần (`bootstrap.py` order + `kernel.py:193` reversed).
7. **(Budget)** Vì sao `BudgetGuard` *cố ý* không wire ở kernel? — *Chấm:* counter per-run; instance sống cùng kernel-lifetime → rò giữa các run. Same-tool guard sống ở graph node per-run (`bootstrap.py:30`).
8. **(VẬN DỤNG)** Bạn thêm tool `fs_append` (ghi nối file). Nó có *tự* được jail + policy + đúng retry không? Vì sao? — *Chấm:* jail/policy: CÓ tự, nếu đăng ký qua `feature.py::install` (bọc `SafeToolPort`, `feature.py:74`) + dòng đầu gọi `resolve_in_workspace`. Retry: KHÔNG tự đúng — phải tự thêm `_DESCRIPTORS["fs_append"] = {"kind":"effect","idempotent":False,...}`; quên → retry chạy ghi 2 lần. Đây là điểm "observability/safety free, đúng-retry phải khai".

## 7. Prompt chấm hiểu cho Claude

```
Tôi đang học Phase 3 (Toolbox, Safety jail & middleware, Epic E06, invariant I8 + I9) của repo hex_agent.
Tôi trả lời các câu kiểm tra hiểu như sau:

[DÁN CÂU TRẢ LỜI CỦA BẠN — đặc biệt Q1 (I8: vì sao reject syntax trước resolve),
 Q2/Q3 (I9: ToolPolicy.check một-cửa, SafeToolPort gọi inner khi nào),
 Q5 (chuỗi descriptor→metadata→retry), Q7 (vì sao BudgetGuard không wire), Q8 (vận dụng fs_append)]

Đối chiếu với plans/260626-1358-clone-hex-agent-roadmap/phase-3-toolbox-safety.md
(neo: sandbox.py:46, policy.py:88/113, terminal.py:21, feature.py:40/74, bootstrap.py:30, kernel.py:173/193, retry.py:14).
Chấm tôi đã thật sự hiểu I8 + I9 chưa, chỉ rõ chỗ hổng (đặc biệt nếu tôi nhầm "thêm tool là tự có đúng-retry"),
và nói có nên cho tôi qua Phase 4 không (ngưỡng ≥6/8 và bắt buộc đúng Q1-Q3). Terse, neo file:line, không khen xã giao.
```

---
*Điều hướng: ← phase trước [phase-2-build-workflow.md](phase-2-build-workflow.md) · → phase sau [phase-4-build-workflow.md](phase-4-build-workflow.md) · Roadmap gốc: [phase-3-toolbox-safety.md](../phase-3-toolbox-safety.md)*
