# Architect Roadmap — neo vào hex_agent (24 tuần)

Khung 24 tuần của bạn là *cấu trúc*. File này là *lớp neo*: mỗi tuần đọc đúng `file:line` nào trong hex_agent, viết artifact của bạn, rồi **diff với bản thật repo đã có**. Khoảng cách giữa bản bạn viết và bản thật chính là bài học.

Anchor system = **hex_agent** (các package ở root: `core/ control/ supervisor/ roles/ delegation/ graph/ orchestrator/ middleware/ safety/ observability/ skills/ rag/ config/ tools/ ui/` + `harness/` + `docs/`). Không phải `drag_from_zero/` (engine mới, tách riêng — chỉ dùng ở W11 vì eval harness thật nằm ở đó).

## Hai cột sống cần đi qua

hex_agent dạy được hai hệ bổ trợ, roadmap này đi qua cả hai:

- **Runtime spine** — `core/kernel.py` (chokepoint `execute_tool`), `graph/`, `supervisor/`, `delegation/`, `orchestrator/`. Dạy: chokepoint, scope ⊆ parent, state serializable, SQLite-là-truth, budget. (W1–7, W13–18)
- **Governance spine** — `harness/` + `docs/` (decisions.md, code-standards.md, system-architecture.md, testing/). Dạy: ADR, invariant-as-gate, contract, AI-coding governance, team enablement. (W8–12, W21–24)

## Cách dùng

- **Nhịp:** 5 ngày học / 1 ngày review+viết / 1 ngày nghỉ. 60–90'/ngày. ≥1 artifact thật/tuần.
- **Format ngày:** 15' đọc anchor → 20' mở code repo tại `file:line` → 20–40' viết artifact → chốt 3 câu (làm rõ gì / boundary-risk-trade-off nào xuất hiện / mai quyết định gì).
- **4 câu hỏi mọi tuần:** boundary ở đâu? responsibility là gì? trade-off là gì? risk là gì?
- **Nơi để bài:** artifact vào `docs/learning/wNN-slug.md`; ADR vào `docs/learning/adr/adr-00N-slug.md`.
- **Vòng học cốt lõi:** TỰ viết artifact từ số 0 trước → MỚI mở cột *Đối chiếu* để so. Đừng đọc bản thật trước, mất hết tác dụng.

## Bản đồ neo nhanh — 24 artifact ↔ bản thật để diff

| Tuần | Artifact bạn viết | Bản thật repo để đối chiếu | Sẵn? |
|---|---|---|---|
| 1 | `w01-system-overview` | `docs/system-architecture.md` §1-3,10 + `MAP.md` | ✅ |
| 2 | `w02-responsibility-map` | `docs/code-standards.md` §1 + `core/ports.py` | ✅ |
| 3 | `w03-dependency-dataflow` | `docs/reference/runtime-flow.md` | ✅ |
| 4 | `w04-architecture-risk` | `docs/reference/known-risks.md` + `code-standards.md` §7 | ✅ |
| 5 | `w05-domain-glossary` | `docs/GLOSSARY.md` | ✅ |
| 6 | `w06-aggregates-invariants` | `code-standards.md` (I1-I9) + learning-roadmap report (I1-I17) | ✅ |
| 7 | `w07-module-map` | `docs/system-architecture.md` (seam table) | ✅ |
| 8 | `adr/adr-001-modular-monolith` | `docs/decisions.md` (DEC-2, DEC-8) | ✅ |
| 9 | `w09-api-output-contract` | `control/commands.py` + `command_registry.py` + `config/runtime_command_types.yaml` | ✅ |
| 10 | `w10-test-strategy` | `docs/testing/README.md` + `tests_audit/AUDIT_MATRIX.md` | ✅ |
| 11 | `w11-eval-strategy` | `drag_from_zero/dragzero/eval/` | ✅ (ở drag_from_zero) |
| 12 | `w12-ai-governance` | `harness/rules/` + `harness/hooks/` + `harness/data/` | ✅ (ví dụ vàng) |
| 13 | `w13-agent-archetype` | `roles/agent.py` + `roles/spec.py` | ✅ |
| 14 | `w14-memory-architecture` | `graph/state.py` + `orchestrator/checkpoint.py` | ⚠️ một phần |
| 15 | `w15-tool-permission` | `core/kernel.py` + `safety/sandbox.py` | ✅ |
| 16 | `w16-agent-runtime-flow` (+`adr-002`) | `orchestrator/loop.py` + `graph/nodes.py` | ✅ |
| 17 | `w17-observability` | `observability/event_log.py` | ✅ |
| 18 | `w18-reliability` | `middleware/retry.py` + `orchestrator/loop.py` resume | ⚠️ retry chưa wire mặc định |
| 19 | `w19-security-threat-model` | `control/authz.py` + `safety/sandbox.py` + `redaction.py` | ⚠️ enforcement pending |
| 20 | `w20-cost-model` | — | ❌ không có, thiết kế từ 0 |
| 21 | `w21-evolution-plan` | `docs/decisions.md` + design-lessons report | ✅ |
| 22 | `w22-refactoring-plan` | code-review report (fix-order P0/P1/P2) | ✅ |
| 23 | `w23-team-enablement` | `docs/getting-started.md` + `guides/add-a-feature.md` | ✅ |
| 24 | `w24-final-review` (capstone) | `docs/system-architecture.md` (full) + architecture-map report | ✅ |

## ⚠️ Khoảng trống thật — đừng tìm code không tồn tại

hex_agent chưa production-hardened đủ. 5 chỗ này là *thiết kế từ số 0 / đọc như hợp đồng chưa thi hành*, không phải "đọc code mẫu":

- **W14 Memory:** KHÔNG có subsystem `memory/` riêng, KHÔNG có Postgres/Qdrant. Memory = session-state serializable + SQLite checkpoint (`graph/state.py`, `orchestrator/checkpoint.py`). Migration path là bài thiết kế, không phải code có sẵn.
- **W20 Cost:** KHÔNG có cost model. Thiết kế từ 0; dùng `observability/event_log.py` (metric roster) + `middleware/budget.py` làm khuôn.
- **W19/E21 Control plane:** contract + UI có thật, nhưng **enforcement chưa wired** — `command_bridge` vắng trên branch này, `control/authz.py` chỉ là predicate thuần chưa ai gọi (DEC-7). Đọc như "hợp đồng đã ký, chưa thi hành".
- **W17/W19 Redaction:** `control/redaction.py` có thật nhưng **chưa wire vào event-log publish** → log đang ghi raw `args` (rủi ro LIVE, `known-risks.md`).
- **W18 Retry:** `middleware/retry.py` có check idempotency nhưng **không bật mặc định** và tool chưa khai báo `metadata.idempotent`. Marker idempotency là bài thiết kế.

Những chỗ này dạy nhiều hơn code hoàn chỉnh: bạn thấy *seam đã đặt nhưng adapter chưa cắm* — đúng trạng thái thật của hầu hết hệ production.

---

# Giai đoạn 1 — Nhìn hệ thống & lấy lại quyền kiểm soát (Tuần 1–4)

### Tuần 1 — System Overview & Boundary
- **Mục tiêu:** mô tả được purpose, user, component, dependency, boundary của hệ.
- **Đọc:** `docs/system-architecture.md:1-40` (hình lục giác + 10 layer + 2 chokepoint) · `core/kernel.py:1-65` (AgentKernel singleton, freeze sau bootstrap; chokepoint `execute_tool` ở `:106`) · `docs/GLOSSARY.md` (ngôn ngữ chung) · `MAP.md` (inventory tự sinh).
- **Viết:** `w01-system-overview.md` — purpose statement, 3-5 use case, system boundary (in/out/deps/not-now), component inventory (UI/API/Orchestrator/Runtime/Memory/DB/Tool/Eval/Logging/Auth/Admin), context map.
- **Đối chiếu:** `docs/system-architecture.md` §1-3,10 + `MAP.md`.
- **Câu hỏi KTS:** thêm 1 tool ngoài (ghi DB / gọi API) thì nó chạm hệ ở boundary nào, và hình lục giác chặn nó làm hỏng core ra sao?

### Tuần 2 — Responsibility & Ownership
- **Mục tiêu:** mỗi component làm gì / không làm gì / ai được ghi state.
- **Đọc:** `docs/code-standards.md:1-100` (8-9 invariant, mỗi cái có file:line) · `core/ports.py:20-65` (ToolPort/DelegationPort/EventSinkPort/VectorStorePort — hợp đồng seam) · `core/session.py` (`SessionFactory.create_child` ép scope con ⊆ cha) · `docs/reference/runtime-flow.md`.
- **Viết:** `w02-responsibility-map.md` — ma trận does/does-not/input/output, ownership (ghi vs đọc), contract giữa các phần, 5-10 boundary rule, boundary-smell checklist.
- **Đối chiếu:** `code-standards.md` §1 + `core/ports.py`.
- **Câu hỏi KTS:** tool ghi file rồi crash trước khi lưu state — trách nhiệm rollback thuộc kernel (trước khi publish `tool.completed`) hay tool (idempotency)?
- **⚠️ Bẫy:** hex_agent có 2 vùng trách nhiệm dễ lẫn — Kernel (E01, `core/`: request/response/lineage) vs Graph/Supervisor (E05/E10, `graph/`+`supervisor/`: topology/state machine). Tách bạch theo DEC-2.

### Tuần 3 — Dependency & Data Flow
- **Mục tiêu:** vẽ chiều phụ thuộc, dòng dữ liệu 1 use case, traceability, failure flow.
- **Đọc:** `docs/reference/runtime-flow.md` (1 task từ vào→ra) · `core/kernel.py:63-150` (chokepoint: args→deep-copy→scope check→middleware chain→resolve→execute→`CapabilityResult`→publish) · `core/bootstrap.py` (thứ tự DI, cái gì freeze lúc nào).
- **Viết:** `w03-dependency-dataflow.md` — dependency direction (core import không gì ngoài port), data flow + điểm publish event, sequence (User→UI→API→Orchestrator→Graph→Kernel→Tool→Memory→Output), failure flow (LLM timeout / tool exception / memory rỗng / schema sai / budget cạn), traceability checklist (request_id, task_id, run_id, session_id, parent_session_id, delegation_id, actor_id — ai set, ở đâu).
- **Đối chiếu:** `docs/reference/runtime-flow.md`.
- **Câu hỏi KTS:** trace 1 `request_id` xuyên 1 run: tạo ở đâu, qua kernel tới tool thế nào, vào event nào, lưu ở đâu, replay được không? Cái gì làm đứt chuỗi?
- **⚠️ Bẫy:** logging hiện ghi raw `args` vào `events.jsonl` (cố ý tạm thời, phải redact trước khi E21/MCP live). `resume()` đọc từ SQLite, không phải `checkpoint.json` (json là projection async, có thể trễ).

### Tuần 4 — Architecture Risk & Failure Modes
- **Mục tiêu:** liệt kê, chấm điểm, map action cho risk.
- **Đọc:** `docs/reference/known-risks.md` (tool thoát jail, middleware fail-open double-execute, secret in log, SQL injection vào log query...) · `docs/code-standards.md` §7 (6 file dễ vỡ nhất + sửa sai vỡ gì) · `plans/260626-1358-clone-hex-agent-roadmap/README.md` §3 (pitfall table: Live/Latent/Design) · `docs/decisions.md` (trade-off đã bake vào thiết kế).
- **Viết:** `w04-architecture-risk.md` — 10-15 risk (technical/product/security/cost/maintainability/AI-behavior), scoring (impact×prob×detectability×mitigation-difficulty), top-10, risk→action, System Overview v1.
- **Đối chiếu:** `known-risks.md` + `code-standards.md` §7 + pitfall table.
- **Câu hỏi KTS:** LLM thành adversarial (ghi file ngoài workspace) — các lớp phòng thủ bắt nó theo thứ tự nào? Lỗ hổng nào KHÔNG bắt được?

# Giai đoạn 2 — Domain Modeling & Modular Architecture (Tuần 5–8)

### Tuần 5 — Domain Discovery: Ubiquitous Language
- **Mục tiêu:** glossary domain ↔ entity code, phân biệt khái niệm domain vs impl-detail.
- **Đọc:** `docs/GLOSSARY.md` · `core/schemas.py:12-34` (TaskEnvelope, ToolRequest — frozen VO, có `as_dict`/`from_dict`) · `supervisor/state.py:14-49` (TaskLoopStatus enum = state machine; AcceptanceCheck, AgentTurn) · `roles/spec.py:42-64` (`allowed_tools()` — Permission là *computed*, không *granted*) · `control/events.py:113-150` (RuntimeEvent — 10 seam) · `control/commands.py:61-93` (RuntimeCommand — issued_by ≠ authz).
- **Viết:** `w05-domain-glossary.md` — bảng: Concept | Entity in code (file:line) | Load-bearing? | Mutable? | Ví dụ thật. ≥12 concept; tách true-domain (Agent/Tool/Task) khỏi impl (KernelSession/Middleware/StateGraph).
- **Đối chiếu:** `docs/GLOSSARY.md` + `docs/reference/codebase-summary.md`.
- **Câu hỏi KTS:** khi nào VO (TaskEnvelope) thành entity (có identity), khi nào entity thành aggregate root (TaskLoopState)?

### Tuần 6 — Aggregate & Invariant
- **Mục tiêu:** consistency boundary + invariant neo tới code; commands; domain events; state transitions.
- **Đọc:** `docs/code-standards.md` (I1-I9 mỗi cái có file:line + hậu quả nếu vỡ) · learning-roadmap report `plans/reports/learning-roadmap-260626-1358-clone-hex-agent-from-scratch-report.md` (bảng I1-I17) · `supervisor/state.py:80-112` (TaskLoopState aggregate, chỉ Agent-O mutate, serializable-only) · `delegation/policy.py` (validator I14: scope con ⊆ cha) · `control/events.py:113-160` (event publish khi state đổi, `seq` monotonic per-session).
- **Viết:** `w06-aggregates-invariants.md` — bảng (1) Aggregate | consistency boundary | root | serializable?; bảng (2) Invariant# | rule | enforced at (file:line) | hậu quả vỡ. + 5 command signature + 8 domain event.
- **Đối chiếu:** `code-standards.md` (invariant table) + learning-roadmap report (I1-I17).
- **Câu hỏi KTS:** invariant nào *structural* (không build sai type được) vs *behavioral* (phải validate lúc apply)? Ép "scope con ⊆ cha" ở typing hay runtime?

### Tuần 7 — Module Design
- **Mục tiêu:** responsibility table + public API + anti-coupling cho modular monolith.
- **Đọc:** `docs/system-architecture.md` (seam table + 10 layer) · `core/ports.py:1-90` (core *export seam*, không export implementation) · `supervisor/graph.py` (SupervisorContext inject delegation_service/emitter/kernel/roles/skills) · `roles/spec.py` + `skills/registry.py` cạnh nhau (cách bẻ cycle E07↔E09: skill role-agnostic, role gọi skill chứ không ngược lại) · `delegation/manager.py` (chokepoint, không sở hữu TaskLoopState).
- **Viết:** `w07-module-map.md` — responsibility table (module | owned aggregate | public API | internal | deps | anti-coupling | epic), DAG phụ thuộc (core ở giữa, không inbound), 3 "seam swap" (đổi Qdrant→Pinecone, in-memory delegation→HTTP, embedder→OpenAI).
- **Đối chiếu:** `docs/system-architecture.md` (layer table) + architecture-map report (file:line mỗi module).
- **Câu hỏi KTS:** vì sao "skill role-agnostic" là cách bẻ cycle? Ép `rag/` `toolbox/` không bao giờ import `supervisor/` bằng cách nào?

### Tuần 8 — First ADR
- **Mục tiêu:** viết ADR-001 theo phong cách DEC-* thật của repo.
- **Đọc:** `docs/decisions.md:1-50` (DEC-1..5: id/status/date/actor/affects/context/decision/consequence, neo file:line) · DEC-2 (roster-growth, sâu 10 dòng) + DEC-8 (attribution≠authz, ADR nguyên tắc) · design-lessons report `plans/reports/design-lessons-260626-1528-worth-learning-from-hex-agent-report.md` (lý do đằng sau quyết định).
- **Viết:** `adr/adr-001-modular-monolith.md` — context → 2-4 option → trade-off matrix (correctness/latency/observability/testability/simplicity) → decision → consequence → rollback. + 100 từ "họ làm gì, tôi sẽ làm gì" so với DEC-2 hoặc DEC-8.
- **Đối chiếu:** `docs/decisions.md` DEC-2 (rộng) và DEC-8 (nguyên tắc). ADR của bạn hẹp hơn DEC-2 nhưng cùng độ chặt.
- **Câu hỏi KTS:** khi nào mở ADR vs chỉ code thẳng? ADR là quyết định code, quy trình, hay nguyên tắc?

# Giai đoạn 3 — Contract, Testing, Quality & AI Coding Control (Tuần 9–12)

### Tuần 9 — API & Output Contract
- **Mục tiêu:** thiết kế API surface, schema request/response, error format, output contract của agent.
- **Đọc:** `control/commands.py:62-93` (RuntimeCommand frozen, bắt buộc `idempotency_key`, `issued_by`=attribution, `schema_version`) · `control/command_registry.py:23-50` (`apply_at`: next_checkpoint|immediate_if_waiting|immediate; `requires_permission`) · `control/events.py:134-151` (`__post_init__` validate ngay lúc dựng — contract-enforced-by-structure) · `core/kernel.py:63-110` (`execute_tool` → `CapabilityResult` envelope).
- **Viết:** `w09-api-output-contract.md` — schema envelope, error taxonomy (enum vs field), command-type registry YAML, verdict types (PASS/FAIL/PENDING), idempotency strategy, lý do attribution ≠ authz.
- **Đối chiếu:** `control/commands.py`, `command_registry.py`, `config/runtime_command_types.yaml`.
- **Câu hỏi KTS:** ép output contract mà không có lớp validate downstream — bằng cách nào? (Repo: validate trong `__post_init__`, freeze dataclass, projection-is-fold nên verdict không mutate được.)

### Tuần 10 — Testing Strategy
- **Mục tiêu:** critical path + 4 loại test + áp 5-tier pyramid.
- **Đọc:** `docs/testing/README.md` (L0 unit pytest / L0 contract vitest / L1 backend-integration / L2 browser E2E deterministic / L3 live — CI chỉ gate L0+L1, DEC-13) · `tests_audit/AUDIT_MATRIX.md` (taxonomy critical-path: contract roundtrip, kernel adversarial, resume matrix, security boundary) · `docs/code-standards.md` (cột test file mỗi invariant) · `harness/rules/tdd-discipline.md` (red→green gate).
- **Viết:** `w10-test-strategy.md` — 5 critical path (kernel→event, resume→SQLite, delegation→scope, output→contract, error→redaction), ma trận test scope/module, pyramid áp lên thiết kế của bạn, 1 chu trình red→green.
- **Đối chiếu:** `tests_audit/AUDIT_MATRIX.md` + `docs/testing/README.md`.
- **Câu hỏi KTS:** vì sao test 3 cách (L0/L1/L2)? Mỗi tier bắt cái gì 2 tier kia bỏ sót?

### Tuần 11 — AI System Evaluation
- **Mục tiêu:** scenario eval, golden dataset, prompt regression, tool-permission test, hallucination eval.
- **Đọc (eval thật ở drag_from_zero):** `drag_from_zero/dragzero/eval/runner.py` (EvalRunner: chạy scenario, thu verdict trace, so baseline) · `drag_from_zero/dragzero/eval/scorers.py` (scorer: task-completion, output-shape, no-hallucination) · `drag_from_zero/dragzero/eval/scenario.py` (Scenario: input/expected/constraints) · `docs/code-standards.md:31-47` (I5-I6: LLM-as-capability, JSON gate sửa output hỏng, đúng 1 action/round).
- **Viết:** `w11-eval-strategy.md` — mục tiêu eval (accuracy/safety/permission/termination), 3-5 golden scenario, scorer (completion, hallucination-free, permission-respected), regression harness (load fixture, seed model, so baseline), risk matrix.
- **Đối chiếu:** `drag_from_zero/dragzero/eval/` + `drag_from_zero/run_eval.py`.
- **Câu hỏi KTS:** test agent tôn trọng permission boundary mà không cần backend thật — bằng cách nào? (Repo: mock scope trong scenario constraints; runner check `capability_claims ⊆ allowed`.)

### Tuần 12 — AI Coding Agent Governance ⭐ ví dụ vàng
- **Mục tiêu:** rule cho AI coding agent, scope template, checklist, Definition of Done — map thẳng lên `harness/`.
- **Đọc:** `harness/rules/tdd-discipline.md` (test-first, 100% pass non-negotiable) · `harness/rules/verification-mechanism.md:1-50` (5 invariant: evidence neo file:line/SHA, artifact=JSON-source-of-truth không phải prose, self-report ≠ self-approve) · `harness/rules/harness-contract.md:1-35` (3 hook class: telemetry/fail-open, nudge/fail-open, compliance/fail-closed; gate=presence không phải authz) · `harness/hooks/gate_stage.py` (đọc `verification.json` → áp `stage-policy.yaml` → PASS/FAIL) · `harness/data/{stage-policy,agent-permissions,work-ownership}.yaml` (policy-as-data).
- **Viết:** `w12-ai-governance.md` — (1) scope template + 3 acceptance criteria, (2) pre-cook checklist, (3) Definition of Done, (4) post-ship trace, (5) review checklist cho code AI sinh, (6) phản ứng khi AI vi phạm I1. Map mỗi cái lên file `harness/` tương ứng.
- **Đối chiếu:** `harness/rules/` + `harness/hooks/gate_stage.py` + `harness/data/`.
- **Câu hỏi KTS:** harness ép governance mà KHÔNG tin self-report của AI — bằng cách nào? (Đáp: gate đọc *artifact* không đọc *prose*; áp policy deterministic; ghi trace. Governance = structure+policy, không phải lời hứa.)

# Giai đoạn 4 — Data, Memory & Agent Architecture (Tuần 13–16)

### Tuần 13 — Agent as Domain Entity
- **Mục tiêu:** Agent = bó capability có scope, role-based allowlist, lifecycle guard.
- **Đọc:** `roles/agent.py:20-86` (Agent = RoleSpec + SkillRegistry + LensRegistry; `is_tool_allowed()`, `guard_tool_call()`, `guard_finish()`) · `roles/spec.py` (RoleSpec: role, system_prompt, allowed_tools, test_ownership, may_route_to) · `core/session.py:163` (`create_child` ép scope con ⊆ cha, raise nếu leo thang) · `control/permission.py:26` (Permission: can_modify_permissions, can_execute_shell, allowed_tools).
- **Viết:** `w13-agent-archetype.md` — định nghĩa Agent → (allowed_tools, allowed_skills, system_prompt); `guard_tool_call` chặn tool ngoài allowlist; separation of duties (agent không có `owns_validation` phải handoff); permission inheritance không leo thang. + skeleton Agent + SessionFactory tối thiểu.
- **Đối chiếu:** `roles/agent.py`, `roles/spec.py`; test `tests/test_delegation.py`.
- **Câu hỏi KTS:** agent delegate cho con — scope hẹp lại hay rộng ra? Luật chống leo thang ép ở đâu?

### Tuần 14 — Memory Architecture ⚠️ một phần
- **Mục tiêu:** hiểu memory = session-state serializable + SQLite checkpoint, resume không chạy lại side-effect.
- **Đọc:** `graph/state.py:12-57` (AgentState TypedDict: schema_version, run_id, messages, budget, allowed_capabilities, session_state encoded; `encode/decode_session_state`) · `core/state.py:8-28` (StateStore snapshot/restore) · `orchestrator/checkpoint.py:35` (**SQLite là truth duy nhất** `var/agent_runs/<run_id>/langgraph.sqlite`; `checkpoint.json` chỉ là projection UI) · `orchestrator/loop.py:139-147` (run với `checkpoint=True`).
- **Viết:** `w14-memory-architecture.md` — phân loại memory; ownership kernel(shared) vs session(per-run); AgentState là checkpoint schema; snapshot/restore; **SQLite=truth, json=projection**; resume flow; migration path JSON→Postgres/Qdrant (thiết kế từ 0). Có thể tách thành `adr/adr-003-memory-architecture.md`.
- **Đối chiếu:** `graph/state.py` + `orchestrator/loop.py:139-147`; test `tests/test_resume.py`.
- **Câu hỏi KTS:** vì sao session state ở ngoài kernel hoàn toàn? Để budget counter trong shared kernel thì vỡ gì?
- **⚠️ Gap:** KHÔNG có `memory/` subsystem riêng, KHÔNG có vector DB. Migration là bài thiết kế (E11+ tương lai).

### Tuần 15 — Tool Permission & Safety Boundary
- **Mục tiêu:** map chokepoint tool, permission matrix, risk classification, audit event.
- **Đọc:** `core/kernel.py:106-225` (`execute_tool` = chokepoint duy nhất: publish `tool.requested` → scope check → middleware chain → executor → publish `tool.completed/failed` → `CapabilityResult`) · `core/kernel.py:128-150` (scope guard: tool ngoài `allowed_capabilities` → `tool.failed` scope_block=True trước khi chạy) · `control/authz.py:29-49` (`is_permission_escalating`, `command_needs_human_checkpoint`) · `safety/sandbox.py` (`resolve_in_workspace`, workspace jail).
- **Viết:** `w15-tool-permission.md` — tool = capability (name/kind/risk/idempotent), permission matrix (allowed ⊆ role.allowed_tools), execute_tool chokepoint, audit trail (tool.requested/completed/failed + metadata), escalation detect (can_* False→True), SafeToolPort jail. Có thể tách `adr/adr-004-tool-permission-model.md`.
- **Đối chiếu:** `core/kernel.py:106-225` + `safety/sandbox.py`; test `tests_audit/test_security_boundaries.py`.
- **Câu hỏi KTS:** bỏ scope check ở `core/kernel.py:128-150` thì invariant audit/safety nào vỡ, và phát hiện trong test bằng cách nào?

### Tuần 16 — Agent Runtime Flow
- **Mục tiêu:** trace 1 task từ run/resume qua graph (guard→agent→tool→finish); budget/retry/timeout/cancel.
- **Đọc:** `orchestrator/loop.py:93-147` (run: session→new_agent_state→build_agent_graph→stream; resume: load SQLite→restore→tiếp) · `graph/runtime.py:49-65` (`build_agent_graph` compile LangGraph + SqliteSaver) · `graph/nodes.py` (guard node: step budget, parse-error streak, same-tool repeat) · `discipline/budget.py:11-67` (**tách parse-error streak [reset mỗi parse tốt] khỏi step budget [per-root]**) · `core/kernel.py:192-194` (middleware chain: fail-closed [policy,budget] + fail-open [telemetry,condense], thứ tự quan trọng).
- **Viết:** `w16-agent-runtime-flow.md` — entry→run/resume→graph; guard/agent/tool/decide nodes; budget split; middleware chain; multi-agent supervisor round loop; checkpoint resume idempotent. + `adr/adr-002-agent-runtime-boundary.md`.
- **Đối chiếu:** `orchestrator/loop.py` + `graph/nodes.py` + `supervisor/graph.py`; test `tests_audit/test_budget_enforcement.py`.
- **Câu hỏi KTS:** tool fail giữa chừng rồi resume — budget sync sao để không đếm 2 lần? Chặn LLM cấp UUID mới cho cùng tool call (tạo bản sao) bằng gì?

# Giai đoạn 5 — Production, Security, Cost & Observability (Tuần 17–20)

### Tuần 17 — Observability
- **Mục tiêu:** event log bắt mọi LLM/tool call qua chokepoint → JSONL + summary.json + metrics.
- **Đọc:** `observability/event_log.py:1-120` (EventLogger sub EventBus; `emit(kind, **fields)`→JSONL; `count(metric)`; `var/agent_runs/<run_id>/{events.jsonl,summary.json,index.jsonl}`) · `core/kernel.py:79-125` (nơi `publish('tool.requested'/'tool.completed|failed')` — 1 chỗ gắn observability) · `docs/reference/runtime-flow.md` (thứ tự trace + lineage).
- **Viết:** `w17-observability.md` — vì sao emit ở chokepoint thay vì log rải rác; cấu trúc JSONL+summary + cách resume đọc; 3 metric (steps, tool_calls, parse_errors); fake event-sink để test offline.
- **Đối chiếu:** `observability/event_log.py:1-120`; `run_smoke.py` output.
- **Câu hỏi KTS:** publish ở chokepoint (1 chỗ, mọi call) hay rải call-site? Chặn log rò secret (raw args) trước khi xuống đĩa bằng gì?
- **⚠️ Gap:** token count / latency aggregation chưa có (E20). Redaction chưa wire vào publish. UI control-plane là React IDE, không phải dashboard tối giản — dùng làm reference.

### Tuần 18 — Reliability ⚠️ retry chưa wire mặc định
- **Mục tiêu:** timeout, retry phân biệt idempotent/side-effect, resume tránh chạy lại side-effect, fallback.
- **Đọc:** `middleware/retry.py:1-34` (check `metadata.idempotent` trước khi retry; không retry `policy_block` hay side-effect non-idempotent) · `middleware/timing.py:1-27` (wrap wall-time, fail_open=True, outermost) · `orchestrator/loop.py:116-210` (resume: mở SQLite checkpoint=truth, restore, stream tiếp; không bao giờ resume từ `checkpoint.json`) · `docs/reference/known-risks.md` §Phần 2 ("Retry không biết idempotency").
- **Viết:** `w18-reliability.md` — timeout+retry stack; metadata schema đánh dấu read_only vs side-effecting; serialization rule (chỉ primitive + encoded); resume flow + checklist (không chạy lại node đã xong).
- **Đối chiếu:** `middleware/retry.py` + `orchestrator/checkpoint.py:35-50`; test `tests/test_resume.py`.
- **Câu hỏi KTS:** retry an toàn nghĩa là gì cho tool side-effect? Ai quyết idempotency — tool registry hay chính tool?
- **⚠️ Gap:** retry không bật mặc định (`middleware:` vắng trong bootstrap); tool chưa khai `metadata.idempotent`; timeout/deadline chưa implement trong graph. Marker idempotency là bài thiết kế.

### Tuần 19 — Security ⚠️ enforcement pending
- **Mục tiêu:** threat model, workspace jail, attribution≠authority, secret redaction, gate capability nguy hiểm.
- **Đọc:** `control/authz.py:1-50` (predicate: `is_permission_escalating` bắt can_* False→True; doctrine: issued_by/Actor = *claim*, authz quyết ở checkpoint boundary so với Permission holder, không theo lời tự khai) · `docs/explanation/authz-vs-attribution.md` (gate≠auth, actor≠authz, scope con⊆cha) · `safety/sandbox.py:1-57` (`resolve_in_workspace` + reject `../` `C:/` backslash, fail-closed mọi OS) · `control/redaction.py:1-60` (mask SECRET_KEYS đệ quy, tách ui_payload + redacted_paths; gateway chỉ stream ui_payload).
- **Viết:** `w19-security-threat-model.md` — threat model (asset: workspace files, secret in log, escalation qua self-issued command; actor: malicious LLM, injection, path traversal); SECRET_KEYS + redaction rule; `resolve_in_workspace` + cross-platform guard; authz predicate + nơi gắn (chưa enforce); scope check `create_child`.
- **Đối chiếu:** `control/authz.py` + `safety/sandbox.py`; test `tests/test_authz_attribution.py`, `test_safety.py`.
- **Câu hỏi KTS:** nếu model tự khai bất kỳ `issued_by`, chặn nó tự duyệt nâng quyền bằng gì? Quyết định authz sống ở đâu — trong code, không phải field model thấy được?
- **⚠️ Gap:** authz predicate có nhưng call-site (`command_bridge`) vắng trên branch này (DEC-7). Redaction chưa wire vào publish (rủi ro LIVE). Workspace jail thì production-ready.

### Tuần 20 — Cost ❌ không có, thiết kế từ 0
- **Mục tiêu:** thiết kế cost tracking (token, latency, cognitive load) + guardrail.
- **Đọc (làm khuôn):** `observability/event_log.py:17-30` (`_METRICS` roster — nền sẵn để gánh thêm cost metric; token/latency chưa có) · `middleware/timing.py` (đo wall-time — khuôn cho latency histogram) · `docs/code-standards.md` §1.7 (Budget per-run, check ở chokepoint) · `harness/rules/harness-contract.md` (telemetry fail-open vs compliance fail-closed — cost guardrail nên là compliance).
- **Viết:** `w20-cost-model.md` — cost source (LLM call×token, tool latency, parse-retry cycle, delegation overhead); cost model (per-run budget + per-call sink); instrumentation (thêm token_in/out, latency_ms, cost_usd vào event); guardrail fail-closed khi vượt; cognitive-load metric (condense overhead, re-prompt).
- **Đối chiếu:** KHÔNG có — thiết kế từ 0. Dùng `event_log.py` + `middleware/budget.py` làm khuôn.
- **Câu hỏi KTS:** cost có 3 chiều (token=tiền, latency=thời gian, retry/parse=cognitive). Cái nào quan trọng nhất cho guardrail, đo cognitive cost mà không instrument mọi re-prompt bằng cách nào?

# Giai đoạn 6 — Evolution, Team Enablement & Capstone (Tuần 21–24)

### Tuần 21 — Evolutionary Architecture
- **Mục tiêu:** phân loại quyết định (delay được vs khó rollback), seam để thay adapter, 90-day roadmap.
- **Đọc:** `docs/decisions.md:1-193` (DEC-1..15: cái nào khóa seam [DEC-2 delegation chokepoint, DEC-3 standards contract] vs rescope được [DEC-4/5]) · `docs/system-architecture.md:38-75` (10 seam: mỗi cái bỏ thì vỡ gì, swap adapter được không, vì sao tách) · design-lessons report `:59-87` (checklist must-carry vs ~70% LOC cắt) · `docs/code-standards.md` (invariant nào *seam* [I1 chokepoint] vs *impl* [I10 SQLite-truth có thể swap]).
- **Viết:** `w21-evolution-plan.md` — bảng 10-seam (seam, vì sao tách, khóa bởi, swap-được?, risk nếu sai); 3 quyết định PRO/CON; 90-day roadmap (5 quyết FIRST, 3 DELAY, 2 REJECT, lý do theo seam=mãi mãi vs impl=refactor được).
- **Đối chiếu:** design-lessons report (ranking must-carry) + DEC-2/3/8.
- **Câu hỏi KTS:** quyết định "load-bearing đủ" để khóa thành seam khi nào? Khi nào scaffolding là overfit vào vấn đề hệ sau không có?

### Tuần 22 — Refactoring Judgment
- **Mục tiêu:** phân loại bad-but-stable vs bad-causing-bugs, strangler cho 1 subsystem.
- **Đọc:** code-review report `plans/reports/code-review-260626-1249-whole-repo-hard-critique-report.md:35-75` (12 security kill-chain + 8 broken invariant — phân KILL-CHAIN [fix trước prod] vs INVARIANT [debt cấu trúc]) · design-lessons `:78-87` (§Anti-bài-học: 5 subsystem ~70% LOC cắt — control/, roles/+skills/+delegation/, langgraph onion, freeze in-memory, thread-safety, với lý do target-model mismatch) · code-review `:107-118` (fix order P0/P1/P2 — dependency chain) · `harness/data/work-ownership.yaml`.
- **Viết:** `w22-refactoring-plan.md` — triage 27 finding critical/high (kill-chain vs debt, refactor cost 1-5, fix-order dependency); chọn 1 subsystem viết strangler migration 4 phase (wrap→parallel→flip→retire) + test gate mỗi phase; 3 subsystem từ Anti-bài-học mà target của bạn KHÔNG cần → gạch + giải thích.
- **Đối chiếu:** code-review §Fix-order + design-lessons §Checklist.
- **Câu hỏi KTS:** biết refactor "quá lớn để làm live" vs "parallelize được bằng strangler" bằng cách nào? Invariant nào (từ W21) là cái van throttle?

### Tuần 23 — Team Enablement
- **Mục tiêu:** review checklist + onboarding + ownership để dev mới land feature không cần 1:1.
- **Đọc:** `docs/getting-started.md` (5-layer nav: MAP.md→CHANGELOG→spec/→tests/→code) · `docs/code-standards.md` (9 invariant → mỗi cái 1 test-proof cho PR checklist) · `docs/guides/add-a-feature.md` (golden path 3 bước: module+docstring → config → smoke+pytest+gen_map) · `harness/data/work-ownership.yaml` (ownership glob) · `MAP.md` (auto-gen = truth, không commit stale).
- **Viết:** `w23-team-enablement.md` — onboarding script (auto-check dev đọc MAP, chạy smoke, kể 9 invariant, giải thích 2 seam); PR review checklist (smoke+pytest, mỗi invariant có proof-test, MAP regen, CHANGELOG entry, không seam mới mà không có port+adapter); module ownership map (5-7 unit + epic + glob); flowchart thêm feature.
- **Đối chiếu:** `getting-started.md` + `add-a-feature.md` + `code-standards.md` + `work-ownership.yaml`.
- **Câu hỏi KTS:** kiến thức nào PHẢI explicit trong code/config/checklist vs cái gì dev giỏi infer được từ MAP+tests? Tribal knowledge thành bottleneck scale ở đâu?

### Tuần 24 — Capstone
- **Mục tiêu:** tổng hợp toàn hệ thành C4 maps + risk/cost synthesis + 90-day execution plan.
- **Đọc:** `docs/system-architecture.md` (full §1-12) · architecture-map report `plans/reports/architecture-map-260625-2009-hex-agent-report.md` (module responsibility + data/control flow — single-agent/multi-agent/delegation/resume/observability tách flow) · code-review report `:17-32` (verdict + 4 theme → risk register) · `docs/decisions.md` (decision-type) · DEC-15 (horizon: hex_agent bị bỏ cho agentplat — bạn evolve hex_agent hay nhảy sang agentplat?).
- **Viết:** `w24-final-review.md` — C4 context (actor ngoài: user/LLM API/Qdrant/SQLite/terminal/HTTP), C4 container (kernel/graph/supervisor/delegation/control/ui/rag + seam), C4 component (lấy KERNEL: execute_tool internals); risk register (threat+file+severity+mitigant+residual); observability map; cost/effort estimate; 90-day roadmap (0-30 / 30-60 / 60-90 với decision+PR+test-gate); 1 trang synthesis "vì sao thiết kế thế này, giữ gì, cắt gì cho hệ của TÔI".
- **Đối chiếu:** `docs/system-architecture.md` + architecture-map report + code-review report + design-lessons report.
- **Câu hỏi KTS:** phải SIMPLIFY hệ 40% LOC — xóa subsystem nào trước, vì sao? Phải EVOLVE thêm 3 capability (tool streaming, real-time collab, auto-refactor) — seam nào thêm mới vs tái dùng?

---

## Tiêu chí tiến bộ (kiểm mỗi cuối giai đoạn)

Bạn đang lên tay nếu: (1) giải thích hệ ngắn hơn mà rõ hơn; (2) biết module nào chịu trách nhiệm gì; (3) biết cái gì *không* nên làm lúc này; (4) chỉ ra risk lớn nhất nằm ở file nào; (5) không để AI coding agent tự mở scope; (6) viết decision có context + consequence + rollback; (7) quay lại sau 1 tháng vẫn hiểu hệ; (8) thêm feature mà hệ không rối hơn; (9) debug được theo trace/log; (10) biết khi nào refactor, khi nào không.

## Checklist hoàn thành sau 24 tuần

```
docs/learning/
  w01-system-overview.md        w13-agent-archetype.md
  w02-responsibility-map.md     w14-memory-architecture.md
  w03-dependency-dataflow.md    w15-tool-permission.md
  w04-architecture-risk.md      w16-agent-runtime-flow.md
  w05-domain-glossary.md        w17-observability.md
  w06-aggregates-invariants.md  w18-reliability.md
  w07-module-map.md             w19-security-threat-model.md
  w09-api-output-contract.md    w20-cost-model.md
  w10-test-strategy.md          w21-evolution-plan.md
  w11-eval-strategy.md          w22-refactoring-plan.md
  w12-ai-governance.md          w23-team-enablement.md
                                w24-final-review.md
  adr/
    adr-001-modular-monolith.md      adr-003-memory-architecture.md
    adr-002-agent-runtime-boundary.md adr-004-tool-permission-model.md
```

## Bước tiếp

Tuần 1, việc đầu tiên: tạo `docs/learning/w01-system-overview.md`. Mở 4 anchor của W1, viết purpose + boundary + component inventory TRƯỚC, rồi mới diff với `docs/system-architecture.md`.
