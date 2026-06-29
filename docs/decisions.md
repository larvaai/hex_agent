# Decision Register

---
id: DEC-1
status: active
date: 2026-06-25
actor: "user:uspro"
ts: "2026-06-25T14:37:14.561440+00:00"
affects: "docs/,plans/,MAP.md,docs/spec/,docs/roadmap/"
---

## DEC-1 — Cấu trúc docs/ theo Diátaxis-hybrid; tách docs(spec) / plans(thực thi) / docs-roadmap(tương lai); bỏ lớp per-module mirror-source

docs/ trộn 5 loại không phân tầng + lớp per-module nhúng full code rot ngay + 2 cặp trùng lặp. Áp Diátaxis (tutorial/how-to/reference/explanation) + giữ epic spec; per-module dựa MAP.md auto-gen, chỉ giữ explainer cho module lõi (KNOWN_RISKS); current(E21)=spec/active, future(E11-E15,E20)=roadmap/future kèm dependency-map làm cổng vào /hs:plan.

---
id: DEC-2
status: active
date: 2026-06-25
actor: "user:uspro"
ts: "2026-06-25T14:48:55.723933+00:00"
affects: "supervisor/graph.py,supervisor/contracts.py,supervisor/loop.py,supervisor/state.py,control/commands.py,control/command_registry.py,config/runtime_command_types.yaml,roles/spec.py,roles/registry.py,plans/"
---

## DEC-2 — Delegation linh hoạt qua control plane E21 (hướng C đầy đủ): O là delegator duy nhất; department = alias gom role chạy tuần tự và TỰ kéo member chưa-compose vào team; roster-growth + department đều đi qua RuntimeCommand AddAgentToLoop + pending_commands, apply tại safe checkpoint cuối round

Mục tiêu: cho Agent-O linh hoạt chỉ định agent/department lúc chạy. Chốt qua brainstorm: giữ O-only (không recursive agent-picks-agent), department là alias tuần tự (không parallel/sub-loop), roster catalog + thêm tại checkpoint. Chọn hướng C (E21-first) thay vì A (field ad-hoc) để có MỘT đường duy nhất cho cả O lẫn human-UI mutate team -> DRY; idempotency_key + issued_by audit lấy miễn phí từ contract đã ship (control/commands.py, control/command_registry.py); và advance E21 từ contract-only sang runtime consumer đầu tiên (pending_commands vào _state_view supervisor/graph.py:124-131 + apply_pending_commands tại checkpoint trong _drive). Department được tự kéo agent mới: target department ngầm phát AddAgentToLoop cho member chưa nằm trong selected_agents, rồi expand thành 1 delegate() mỗi member trước authority gate (supervisor/graph.py:142-147). LOẠI hướng B (coordinator handler ở delegation seam) vì phá invariant no-nested-subloop + mất audit/scope per-member. Guardrails: depth không đổi; scope mỗi member chỉ narrow (delegation/policy.py:25-27); apply command CHỈ ở cuối round sau judge_acceptance (không phá resume; pending_commands persist cùng selected_agents); idempotent theo key (control/commands.py); catalog-bound (tái dùng validator compose_team graph.py:93-97); authority gate vẫn là nguồn chân lý sau expansion. Seam delegation + bootstrap agent:general GIỮ NGUYÊN (không unfreeze registry).

---
id: DEC-3
status: active
date: 2026-06-25
actor: "user:uspro"
ts: "2026-06-25T14:53:50.862104+00:00"
affects: "docs/system-architecture.md,docs/code-standards.md,docs/reference/"
---

## DEC-3 — system-architecture.md + code-standards.md giữ ở docs/ root (KHÔNG move vào reference/) — bảo toàn harness self-hosting standards contract

harness/standards/README.md ghi rõ repo self-hosting đọc standards tại docs/system-architecture.md + docs/code-standards.md; hs:plan/hs:cook tham chiếu 2 path này. Move vào reference/ phá contract. Đánh đổi: hơi lệch Diátaxis thuần (standards nằm cạnh root docs/) đổi lấy không vỡ wiring. reference/ + docs/README.md trỏ tới thay vì relocate.

---
id: DEC-4
status: active
date: 2026-06-25
actor: "user:uspro"
ts: "2026-06-25T16:28:49.464770+00:00"
affects: "docs/roadmap/future/,docs/roadmap/dependency-map.md,docs/roadmap/project-roadmap.md,docs/spec/active/E21-realtime-control-plane/"
---

## DEC-4 — E15 Self-eval bỏ khỏi roadmap/future (verdict merge-into-other → gộp E21); sửa map-drift E15 deps E16→E21

Critique workflow: governance/audit của E15 đã bị E21 S21.33 nuốt (evidence types + AC report); phần judge≠doer rẻ nhất là siết judge_acceptance (supervisor/graph.py:238) trong E21, không cần epic riêng. Bảng 01_BUILD_ORDER:23 còn ghi E15→E16 trong khi E16 đã gộp E21 (map tự mâu thuẫn) → sửa thành E04,E10,E21. User chốt 'bỏ đi'.

---
id: DEC-5
status: active
date: 2026-06-25
actor: "user:uspro"
ts: "2026-06-25T16:28:49.540554+00:00"
affects: "docs/roadmap/future/E11-departments.md,docs/roadmap/future/E12-router-supervisor.md,docs/roadmap/future/E13-software-factory.md,docs/roadmap/README.md"
---

## DEC-5 — Roadmap routing-cluster: ranh giới E12/E13 + mồi phá vòng E11↔E12

Synthesis phát hiện 2 tension cứng: (1) E12 'plan nhiều bước' chồng vai E13 'dây chuyền cố định' → chốt định nghĩa load-bearing: multi-step trong-MỘT-task = E13 (pin_route), dispatch nhiều-TASK = E12 (GlobalSupervisor). (2) Deadlock ngưỡng: E12 chờ E11 ship nhưng trigger mạnh nhất của E11 là 'E12 in-progress' → nguyên tắc phá vòng: E11 rã đông MỨC TỐI THIỂU (DepartmentRegistry+validate, roles/spec.py:104) ngay khi E12 vào THIẾT KẾ, không chờ E12 chạy hẳn. Ghi để Thaw Protocol Bước 2 áp.

---
id: DEC-6
status: active
date: 2026-06-26
actor: "user:uspro"
ts: "2026-06-25T19:02:22.913278+00:00"
affects: "control/snapshot.py,control/commands.py,supervisor/state.py,ui/control-plane/,config/runtime_event_types.yaml,config/runtime_command_types.yaml,plans/"
---

## DEC-6 — E21 build UI-first trên fake backend: fake = HTTP/SSE server Python reuse control/ dataclass (seam by-construction, đổi backend = đổi URL); stack React+Vite+TS (React Flow + tanstack-virtual); lát 1 = full T1 (Graph/Timeline/Inspector/Approval) + prompt box & Send; tạo TaskLoopSnapshot + CommandAck dataclass TRƯỚC khi viết UI; UI mới sống song song console cũ (không sửa ui/server.py)

Đảo thứ tự so với discovery brief (spine-backend-first) nhưng KHÔNG xây trên facade: fake chạy Redactor().apply() + .as_dict() thật nên secret không rò và 'drop-in khi đấu nối' là bảo đảm bằng cấu trúc, không bằng kỷ luật. 2/5 shape (TaskLoopSnapshot, CommandAck) chưa có dataclass → phải tạo trước (dataclass-only, không wire) nếu không seam còn lỗ by-discipline. React vì reader junior cần ecosystem/ví dụ. Done = demo fixtures + contract-seam test (UI chỉ đọc ui_payload, không đọc payload raw).

---
id: DEC-7
status: active
date: 2026-06-26
actor: "user:uspro"
ts: "2026-06-25T20:06:12.664866+00:00"
affects: "supervisor/evidence.py,supervisor/graph.py,supervisor/loop.py"
---

## DEC-7 — S21.33 evidence-type gate: derived-from-kind + >=1-valid quantifier + trust-worker

evidence_type derived tu artifact.kind (khong luu tren AcceptanceCheck -> 0 migration); NON_EVIDENCE_KINDS={session_plan,context_packet,ac_report}; kind rong->None; kind-la-worker->artifact (trust-worker, threat model = O mis-cite scaffolding); judge_acceptance passed = all-exist + >=1-valid-type (spec S21.33, KHONG all-valid, red-team FM-HIGH); ac_report id=ac_report-{session_id}. Chon H2 re-scope thay command-based vi command_bridge/pending_commands khong ton tai tren branch feat/docs-diataxis-restructure.

---
id: DEC-8
status: active
date: 2026-06-26
actor: "user:uspro"
ts: "2026-06-25T21:09:30.228891+00:00"
affects: "control/authz.py,control/commands.py,control/permission.py,docs/explanation/authz-vs-attribution.md"
---

## DEC-8 — attribution≠authz: issued_by/Actor là ghi nhận, không phải quyền; permission-edit (UpdateAgentPermission→can_modify_permissions) cần human RuntimeCheckpoint kể cả dưới trust-O

Harness tuyên bố actor≠authz vì là tool hợp tác; hex_agent xây authz THẬT nên port sự phân biệt và ĐẢO kết luận: authz quyết bởi requires_permission+checkpoint, không phải claim của issuer. requires_permission mới khai báo (runtime_command_types.yaml) chưa thực thi; command_bridge vắng trên branch (DEC-7). Phase 1 chỉ doctrine+predicate thuần (control/authz.py), enforcement hoãn cho epic command-application.

---
id: DEC-9
status: active
date: 2026-06-26
actor: "user:uspro"
ts: "2026-06-26T09:18:24.128605+00:00"
affects: "decompose_agent/accept.py,decompose_agent/solve.py"
---

## DEC-9 — decompose_agent μ = done_when_count as sole convergence measure (drop scope_token_len tiebreak)

Tokenizer drift across decomposer_version breaks the lex tiebreak silently (spec.md:343,345). Single-int well-order is clean; accepted limit: a dwc<=2 node needing honest multi-criterion children is BLOCKED(NOT_SMALLER). Plan 260626-1528-decompose-agent-recursion-slice DEC-D1.

---
id: DEC-10
status: active
date: 2026-06-26
actor: "user:uspro"
ts: "2026-06-26T09:18:24.209800+00:00"
affects: "decompose_agent/solve.py,decompose_agent/gates.py"
---

## DEC-10 — decompose_agent runtime-decomposed parent gate = all_children_done (len>=1) AND re-assert original done_when; else BLOCKED(COMPOSE_FAIL)

Red-team F1/F2: dropping _reduce + fencing D12 let a decomposed parent pass vacuously (all([])==True) and lost its original metric gate. Un-fence minimal D12: COMPOSE_FAIL detects the need for reduce, does not re-decompose. Plan 260626-1528 DEC-D4.

---
id: DEC-11
status: superseded
date: 2026-06-26
actor: "user:uspro"
ts: "2026-06-26T09:31:55.085138+00:00"
affects: "new-greenfield-repo, engine-core, config-spec, canvas-contract"
---

## DEC-11 — Greenfield drag-drop LLM-workflow+chat engine: build the spec/safety layer, spike Burr for the FSM runtime

Target locked single-user-local + generic workflow builder + existing React-Flow canvas + greenfield. Platforms (Flowise/Langflow/Dify/n8n) rejected: own-UI makes their canvas dead weight + UI-lock/license traps. Real fork = build runtime (D1) vs rent Burr FSM (D2-prime). Decision: build the YAML-spec+parse-gateway+registry+compile-time-cycle-check+canvas-contract (the IP, Report A 5x idiom); decide build-vs-rent FSM via a one-weekend Burr spike (clean=>D2-prime, fighting-abstractions=>D1). NON-NEGOTIABLE spine regardless of substrate: three separate state lifetimes (per-run graph state resets / cross-turn ledger persists OUTSIDE graph / display stream never source-of-truth); compile-time cycle check (every loop traverses a budget node); LLM never authors route/verdict; plugins not importlib-any-string; saved workflows carry schema_version+migration. Engine is headless: spec-load + run + SSE stream API behind the existing canvas.

---
id: DEC-12
status: active
date: 2026-06-27
actor: "user:uspro"
ts: "2026-06-26T17:26:42.658618+00:00"
affects: "drag_from_zero/tests,drag_from_zero/pyproject.toml,drag_from_zero/MANUAL_TESTING.md"
---

## DEC-12 — drag_from_zero test pyramid: determinism boundary + marker policy

Default pytest runs deterministic layers (unit/integration/e2e on FakeLLM/RecordedLLM) only. Real weights behind marker 'real_llm' (skip unless OPENAI_BASE_URL); real browser behind marker 'browser' (skip unless playwright). Manual runbook in drag_from_zero/MANUAL_TESTING.md. Every test must have a mutation proof (no vacuous green).

---
id: DEC-13
status: active
date: 2026-06-27
actor: "user:uspro"
ts: "2026-06-26T17:27:46.736822+00:00"
affects: "tests/test_ide_*, ui/control-plane/e2e, ui/ide, control/snapshot.py, .github/workflows/ci.yml"
---

## DEC-13 — control-plane E2E = real-only Playwright, two-tier; browser asserts ONLY HTTP surface

ui.ide AgentRunner always calls real LLM (runner.py:151, no stub seam); graph/timeline/chat fold loop.* events with NO HTTP seed route (snapshot.py:3-9, AgentGraph.tsx:65 root is only model-free node). So browser cannot render agent state without the model: det-browser tier (L2) asserts only file-API/CORS/session; agent-state asserts live IN-PROCESS (L1 pytest) or @live (L3). CI is python-only (ci.yml) -> L2/L5 are local gates, not CI.

---
id: DEC-14
status: active
date: 2026-06-27
actor: "user:uspro"
ts: "2026-06-26T18:04:38.883842+00:00"
affects: "drag_from_zero/tests/e2e_browser"
---

## DEC-14 — drag_from_zero browser E2E stays an automated opt-in layer (not manual fallback)

U1 resolved: the custom DC UI renders + runs fully in headless Chromium offline (only a benign SVG-template console warning, no JS crash). All 4 Playwright scenarios (boot/run/artifact-open/reset) pass deterministically. So the phase-5 manual-only fallback is NOT taken — browser E2E ships as the marker=browser automated layer (opt-in via test-browser extra).

---
id: DEC-15
status: active
date: 2026-06-27
actor: "user:uspro"
ts: "2026-06-26T18:36:04.040747+00:00"
affects: "agentplat (greenfield), docs/decisions.md"
supersedes: DEC-11
---

## DEC-15 — agentplat = fusion 2-lop (topology authoring x decompose-until-trivial) tren 1 event-log/projection, hexagonal headless; bo Burr

8 quyet dinh interview (discovery-brief 260627-0054): Fusion 2-lop; cay-long-cay (per-agent decomposer, budget_child=min(authored,parent_remaining)); 1 event-log append-only nest by parent-id, verdict/mu/budget re-derive o fold (khong luu); Agent entity giau, LLM port mang agent (1 model gio, multi sau); runtime tu viet vendored stdlib-first (event-log-projection khong khop FSM-transition cua Burr); palette full 6 Agent/Tool/Router/Memory/Hook/Gate voi invariant Router/Memory khong-thanh-truth-2; chat = turn-ledger rieng ngoai engine; UI headless 2-format canvas-JSON<->spec qua compiler. Hexagonal adapters->ports->domain enforce import-rule.

---
id: DEC-16
status: active
date: 2026-06-27
actor: "user:uspro"
ts: "2026-06-27T15:13:31.525270+00:00"
affects: "drag_from_zero/dragzero/verifier.py, drag_from_zero/dragzero/accept.py, drag_from_zero/dragzero/orchestrator.py, ui/Agent IDE.dc.html"
---

## DEC-16 — drag_from_zero rebuild: supervisor LLM la trong tai verdict toi cao, phan tren artifact that + code gate lam chung cu, context tach roi worker, cung model 35B

Re-build tu user-experience: 1 worker mac dinh tu phan loai hoi-vs-task + dinh o vuong task; supervisor LLM (1 con toan cuc) adjudicate. Dao nguoc verifier.py (code la trong tai duy nhat) -> LLM-co-chung-cu. Giu propose/adjudicate split vi supervisor context rieng + phan tren disk that. Rui ro: 35B bia verdict xanh; guard: log mau thuan khi code gate FAIL nhung supervisor PASS. User chon A sau khi nghe rui ro.

---
id: DEC-17
status: active
date: 2026-06-28
actor: "user:uspro"
ts: "2026-06-27T18:28:06.460751+00:00"
affects: "drag_from_zero/dragzero/tools.py,drag_from_zero/dragzero/orchestrator.py,drag_from_zero/dragzero/agent.py,drag_from_zero/dragzero/adapters/llm_local.py,plans/"
---

## DEC-17 — drag_from_zero: multi-lens advisory tool (consult_lenses) = Mixture-of-Agents thinking primitive, shape A (KHONG phai extended thinking)

Brainstorm 260628 chot shape A (tool consult_lenses) over B (DelegationMode ADVISE: doi terminal-decision contract, nang) va C (supervisor ensemble: giup tham phan khong giup worker, sai muc tieu). Co che: agent goi tool trong ReAct loop -> orchestrator chay N lens-agent (moi lens 1 system-prompt khac, tra 1 dong cuc ngan) -> feed lai lam observation -> agent tu tra loi/quyet. Luat giu nguyen: lens ADVISORY only (propose, never adjudicate -> no-forge, verifier.py); leaf-only (lens la LLM call khong phai task, khong recurse -> khong dung invariant no-nested-subloop DEC-09); tai dung tool mechanism (tools.py + tool_called/tool_result event); budget cap N. Insight: decompose-until-trivial ap cho SUY NGHI khong phai task; ten dung Mixture-of-Agents/LLM-jury. RUI RO GHI NHAN: 1x35B doi N mu -> correlated errors/echo chamber, harness critique work vi lens doc lap that + consolidator MANH ma 35B khong co; baseline self-consistency (N mau cung prompt + vote da so) CHUA do; user CHON build truoc, bo qua bake-off measure-first du da de xuat -> chap nhan rui ro, vut lens machinery neu sau do khong thang sample+vote. Guard khi build: lens-prompt ep divergent that, log khi lens dong thuan trivial, verdict o agent/code. Report: plans/reports/brainstorm-260628-0049-multi-lens-advisory-thinking-primitive-report.md

---
id: DEC-18
status: active
date: 2026-06-28
actor: "user:uspro"
ts: "2026-06-27T18:49:55.348227+00:00"
affects: "drag_from_zero/dragzero/registries.py,drag_from_zero/dragzero/orchestrator.py,drag_from_zero/dragzero/agent.py,drag_from_zero/dragzero/events.py,drag_from_zero/dragzero/wiring.py,drag_from_zero/dragzero/topology.py,harness/data/lenses.yaml,plans/"
---

## DEC-18 — drag_from_zero: lens-combo design (he->combo->cascade), advisory MoA-lite; permissions HARD-CODED in capability; budget/echo-detector/fixed-order REMOVED (local + user-controlled)

REVISED sau 3 vong user refine (thay noi dung over-engineered ban dau). Khung: role-conditioned ensemble tren 1 base 35B + optional cascade synthesis (MoA-lite, arXiv:2406.04692 synthesis>selection). Lens = gop y ADVISORY, AGENT chot output. MODEL 3 LOP. (1) CONFIG (user viet, load-once-frozen): lens={id,prompt} 1 cau hoi 35B-trivial 1 dong ra; combo=list lens (co the 1 lens tong-hop doc lens khac); he=attr tren agent node (topology Node.attrs, da mo); enabled moi he default true. (2) PERMISSION (HARD-CODE vao capability.py — Gate doc token khong doc loi agent, orchestrator.py:233): agent CO quyen consult, lens KHONG (lens khong goi them lens -> lens consult bi tu choi nhu TOOL_DENIED san co); agent thuoc he X + enabled bi CODE EP chay combo, khong skip duoc; toggle enabled CHI user (config frozen -> agent vat ly khong co duong ghi, "chi toi toggle" tu dung dung). (3) RUNTIME: he X+enabled -> combo BAT BUOC; agent duoc goi THEM lens ngoai combo (named tu catalog, unknown id drop khong crash); moi lens 1 call 35B -> 1 dong -> LOG 1 event (no verdict field); tat ca dong (combo+extra) ve agent -> agent chot. CASCADE = diem DUY NHAT cham no-forge: giu propose-only bang 1 luat — agent LUON nhan TAT CA dong tho + dong tong-hop, khong bao gio thay raw bang moi dong tong-hop (tong-hop = 1 giong nua, khong phai verdict); tong-hop chay SAU input no doc (phu thuoc du lieu, khong phai luat order). THU TU LENS KHONG CO DINH (user chot); replay test key theo lens-id thay vi call-order. BO (co ly do — local + user kiem soat): budget/cap-N/unlimited/hard_backstop (combo huu han + local, khong ton tien khong lo can), echo-detector thong minh (user kiem soat chat luong -> chi log thuong moi lens), free-pick-THAY-combo (combo bat buoc, agent chi THEM), fixed-order. EVENT moi (lean, chi 2): LENS_QUERIED {he,combo|adhoc,lens_id,reads}, LENS_RETURNED {lens_id,line} (no verdict, mirror FORBIDDEN_VERDICT_KEYS verifier.py:26); bracket consult=TOOL_CALLED/RESULT san co, deny=TOOL_DENIED san co. ACs: empty-by-default byte-identical + consult khong tieu AttemptBudget (orchestrator.py:373); permission hard-code (lens consult -> denied, test); mandate (combo chay agent khong skip; enabled=false khong chay; agent khong flip enabled); agent them lens duoc; cascade feed ALL raw lines + synthesis sau input; lens output no verdict key; determinism key theo lens-id. TOUCHPOINTS: capability.py (consult cap flag), registries.py (LensRegistry), orchestrator.py (_run_tool nhanh consult_lenses + mandate dispatch), agent.py (Agent.he), events.py (2 event), wiring.py (seed config + he attr), harness/data/lenses.yaml, topology.py (he attr da mo). Verdict: ADOPT (gon, KISS, "lens gop y — agent chot"). Risk con lai = echo (1x35B doi N mu, arXiv:2605.00914) — user CHAP NHAN vi tu kiem soat lens. Report: plans/reports/brainstorm-260628-0049-multi-lens-advisory-thinking-primitive-report.md. Fork mo cho plan: catalog seed (he/lens ship san); agent-them-lens tu do toan catalog hay chi cung he; bieu dien cascade reads trong combo config.
