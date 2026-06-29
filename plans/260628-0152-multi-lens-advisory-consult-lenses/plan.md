---
title: "multi-lens advisory — consult_lenses + hệ→combo→cascade (MoA-lite, advisory)"
slug: multi-lens-advisory-consult-lenses
status: approved   # human-approved 2026-06-28 by uspro
mode: hard
tdd: true
created: 2026-06-28 01:52
owner: uspro
source_report: plans/reports/brainstorm-260628-0049-multi-lens-advisory-thinking-primitive-report.md
project: drag_from_zero/dragzero (additive; start()/run()/_solve_gated byte-identical)
phases: 4
depends_on: []
risk: low-medium — additive (tool + 2 event + Agent.he + LensRegistry). Risk thật = (1) hệ-mandate chèn observation vào _react_until_terminal (đường dùng chung gated+ungated) phải không đổi suite cũ; (2) cascade synthesis lens giữ propose-only.
standards:
  - drag_from_zero/README.md   # quy ước: event-log-là-truth, port qua Protocol, empty-by-default, additive
  - docs/code-standards.md      # §3 naming, §4 TDD, §5 add-file traceability (KHÔNG áp §1 microkernel — drag_from_zero divergent)
decisions:
  - DEC-17 — shape A: consult_lenses là tool, lens ADVISORY, agent chốt (docs/decisions.md:208)
  - DEC-18 — design: MoA-lite, permission HARD-CODE vào capability, bỏ budget/echo-detector/fixed-order, hệ-mandate code-enforced (docs/decisions.md:234)
phases_list:
  - phase-1-lens-core.md
  - phase-2-consult-tool-permission.md
  - phase-3-he-mandate-wiring.md
  - phase-4-config-adapter-determinism.md
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — multi-lens advisory (consult_lenses + hệ→combo→cascade)

> Hợp đồng cho hs:cook. Claim không hiển nhiên có anchor `file:line`; tag `[UNVERIFIED]` nếu thiếu.
> Additive: KHÔNG sửa logic `start()`/`run()`/`run_until_idle`/`_solve_gated`. Suite cũ xanh nguyên.

## Vì sao plan này

Cho con 35B-local một "thinking primitive": khi cần nghĩ kỹ, agent chạy một **combo lens** (do user viết) — mỗi lens là 1 góc nhìn ngắn từ cùng model với prompt khác — rồi **agent tự chốt** output. Lens **góp ý**, không quyết (no-forge). Thiết kế đầy đủ + prior-art ([report](../reports/brainstorm-260628-0049-multi-lens-advisory-thinking-primitive-report.md)); plan này là đường thực thi TDD additive.

Hiện `drag_from_zero` không có lens: agent chạy ReAct loop (agent.py:50, orchestrator.py:220) rồi emit terminal decision. Plan thêm: (1) `LensRegistry` + lens-runner; (2) tool `consult_lenses` (agent gọi thêm lens); (3) `hệ` = attr agent, CODE **ép** chạy combo nếu enabled; (4) config `lenses.yaml` + nhánh adapter.

## Kiến trúc slice

```
agent thuộc hệ X (enabled)
   │  ← CODE ép: chạy combo X lúc agent vào task (mandate, agent không skip)
   ▼
run_lenses(plan, base_ctx, llm, log)        ← lens-runner thuần, KHÔNG truy cập ToolRegistry
   │   mỗi lens: llm.complete(ctx{request:"lens", lens_id, prompt, upstream})
   │   emit LENS_QUERIED → LENS_RETURNED{lens_id, line}   (KHÔNG field verdict)
   │   cascade: lens "tổng hợp" (reads:[A,B]) chạy SAU A,B; ctx có line A,B
   ▼
TẤT CẢ dòng (raw + tổng-hợp) → observations  ← agent thấy hết, tổng-hợp chỉ append
   │
   ├── (mid-loop) agent có quyền gọi thêm: action tool consult_lenses{lenses|combo}
   │       → lens KHÔNG có đường này (structural); capability gate (orchestrator.py:268) chỉ chặn opt-in khi set
   ▼
agent.step → terminal DelegationDecision    ← AGENT chốt; verdict vẫn ở agent + verifier.py
```

Event-log là truth. Lens chạy = LLM call thuần (không Task, không `_recs`, không `_ready` → leaf-only, không recurse, giữ DEC-09).

## Luật phải giữ (đừng phá)

1. **Lens góp ý — agent/code chốt (no-forge).** Lens output là 1 dòng free-text vào observations; KHÔNG có key verdict/route/mode (mirror `FORBIDDEN_VERDICT_KEYS` verifier.py:26). DelegationDecision do agent emit (contracts.py:92), PASS/FAIL do `run_checks` (orchestrator.py:340). Không đường code nào đọc dòng lens thành verdict. **Cascade:** agent LUÔN nhận TẤT CẢ dòng thô + dòng tổng-hợp; tổng-hợp **append, không thay thế** raw.
2. **Permission HARD-CODE — STRUCTURAL, không phải capability gate.** (a) "Lens không gọi được tool/consult" = structural: `run_lenses` KHÔNG cầm ToolRegistry, và `_run_tool` chỉ có **1 call site** (orchestrator.py:272) chỉ reachable từ `_react_until_terminal` → lens vật lý không tới được. (b) "hệ+enabled → ép combo" = CODE trong `_mandatory_lens` (agent không skip). (c) "toggle `enabled` chỉ user" = config frozen lúc load → agent không có đường ghi. **Capability gate (orchestrator.py:268) là lớp opt-in PHỤ:** nó CHỈ chặn khi một `Capability` được set; mặc định `capability=None` (wiring.py không truyền capability) → KHÔNG gate (permissive-consult). KHÔNG dựa vào capability làm default-deny — L2 đứng trên (a)(b)(c).
3. **Additive.** Không lens/hệ configured → `tools.names()` + event stream byte-identical; suite cũ xanh nguyên (proven baseline: 56/56 trên 6 suite target). Consult KHÔNG tiêu `AttemptBudget` attempt (`record_attempt` chỉ chạy SAU react pass, orchestrator.py:373) — chỉ là tool step như mọi tool. LENS_QUERIED/RETURNED **không** vào `reduce()` (read_model.py:80) → bảo vệ L1 (dòng lens không bao giờ thành node verdict); disk-truth test assert trên `log.of_type(LENS_RETURNED)`, không trên cây reduce.

## Rủi ro đã biết (chấp nhận / deferred)

- **Echo-chamber** (1×35B đội N mũ → góc nhìn na ná, arXiv:2605.00914). User **chấp nhận** vì tự kiểm soát lens; chỉ giữ **log thường** mỗi lens (LENS_QUERIED/RETURNED) để soi sau. KHÔNG build echo-detector.
- **Không budget cho lens.** User chạy local → lens call không charge budget; combo hữu hạn + lens-không-gọi-lens → luôn dừng. (Nếu sau muốn metered: thêm charge — ngoài slice này.)
- **Thứ tự lens không cố định.** Lens độc lập → order không đổi tập dòng agent nhận. Cascade có phụ thuộc dữ liệu (tổng-hợp sau reads). Replay test key theo **lens-id** (phase 4), không theo call-order.

## Acceptance (toàn slice)

- Agent gọi `consult_lenses{lenses:[a,b]}` → 2 dòng lens vào observations; log có TOOL_CALLED/TOOL_RESULT + 2×(LENS_QUERIED+LENS_RETURNED); KHÔNG có DelegationDecision do lens tạo.
- Lens output KHÔNG có key verdict/route/mode/passed/status/score.
- `run_lenses` KHÔNG phát TOOL_CALLED nào (structural: không cầm ToolRegistry) — kể cả khi 1 lens responder trả dạng tool-action.
- Khi MỘT `Capability` được set mà KHÔNG có `consult_lenses` → TOOL_DENIED (gate opt-in, orchestrator.py:268). Mặc định `capability=None` → consult cho phép (permissive — đúng posture local).
- Combo cascade A,B→C: agent nhận đủ 3 dòng (A,B AND C); C's ctx có dòng A,B; C chạy sau.
- Agent hệ X + enabled → combo auto-chạy (LENS_QUERIED có, agent KHÔNG emit consult); enabled=false → không chạy; agent he=None → byte-identical.
- Cascade self/back-ref → lỗi lúc build combo (acyclic).
- `lenses.yaml` load → LensRegistry; config sai (lens thiếu / cascade cycle / hệ→combo không tồn tại) → lỗi lúc LOAD, không runtime.
- RecordedLLM key theo lens-id → combo replay y hệt bất kể order.
- **Toàn suite cũ xanh nguyên** (`python -m pytest drag_from_zero -q`), 0 sửa file test cũ.

## Rollback

Xóa `lens.py` + 2 EventType + nhánh `consult_lenses` trong `_run_tool` + `Orchestrator.lenses` param + `Agent.he` + nhánh wiring + nhánh adapter `request:"lens"` + `harness/data/lenses.yaml` + test mới. Không file cũ nào đổi logic ⇒ revert = drop hunk additive.

## Phases

1. [phase-1-lens-core.md](phase-1-lens-core.md) — 2 EventType + `lens.py` (Lens/ComboStage/ComboSpec/LensRegistry + `run_lenses` cascade) trên FakeLLM. No-forge + cascade-feeds-all-raw chứng minh ở đây.
2. [phase-2-consult-tool-permission.md](phase-2-consult-tool-permission.md) — `consult_lenses` dispatch trong `_run_tool` + `Orchestrator.lenses` param + capability gate. Lens-không-consult + empty-by-default.
3. [phase-3-he-mandate-wiring.md](phase-3-he-mandate-wiring.md) — `Agent.he` + wiring + hệ-mandate auto-run combo + toggle enabled. Mandate + agent-thêm-lens + byte-identical.
4. [phase-4-config-adapter-determinism.md](phase-4-config-adapter-determinism.md) — `lenses.yaml` loader + nhánh adapter `request:"lens"` (OpenAICompat/Recorded) + determinism key-by-lens-id.

## Câu hỏi mở (đã chốt default — xác nhận lúc duyệt)

- **Agent gọi thêm lens — phạm vi?** Default: **toàn catalog** (catalog = tập cho phép; hệ chỉ MANDATE combo, không RESTRICT extra). Nếu muốn siết "chỉ lens cùng hệ" → đổi 1 chỗ resolve, ghi DEC. *(governance — user xác nhận)*
- **Catalog seed?** Ship `harness/data/lenses.yaml` 1 hệ mẫu (`thanh_tra`/`inspect_v1`) **inert** (không topology nào tham chiếu) → empty-by-default giữ.
- **Cascade biểu diễn?** `reads: [lens_ids]` trên combo-stage; chỉ ref stage TRƯỚC (back-ref) → acyclic by construction, self/forward-ref reject lúc build.
