---
title: "Authoring UI thật (React Flow) trên boundary substrate-agnostic + bakeoff substrate Z·L·Bu"
description: "Xây nửa authoring (Đồ thị 1) còn thiếu của drag_from_zero: React Flow canvas → topology → run → observe → inject mid-run; đóng câu hỏi langchain bằng bakeoff đo được."
slug: dragdrop-ui-real-langchain-bakeoff
status: approved   # human-approved 2026-06-27 by uspro via Plannotator (after REVISE: 12 must-fixes applied)
priority: P2
mode: hard
tdd: true
effort: "4 phases — 1 API/Python, 1 React app, 1 mid-run-join lifecycle, 1 bakeoff substrate"
branch: feat/docs-diataxis-restructure
created: 2026-06-27
owner: uspro
source_brief: plans/260626-2329-dragdrop-ui-real-langchain-bakeoff/discovery-brief.md
source_reports:
  - plans/reports/codebase-map-260626-2229-drag-from-zero-report.md       # runtime map + gap list
  - plans/reports/design-260626-1502-drag-drop-composition-layer-report.md # config-driven composition idiom
  - plans/reports/brainstorm-260626-1615-greenfield-dragdrop-engine-report.md # DEC-11, substrate build-vs-rent
project: drag_from_zero (standalone, chưa commit — git ls-files = 0; plan này cũng đưa nó vào repo)
phases: 4
depends_on: []
risk: "medium — core untouched (orchestrator/read_model/events/topology/wiring/roster/contracts), nhưng phá 2 invariant có chủ đích: 'single static file' (thêm Vite/TS) ở phase 2 + 'zero external dep' (langgraph/burr, optional extra) ở phase 4. Rollback = git checkout server.py run_server.py + rm -rf app dragzero/bakeoff."
standards:
  - docs/code-standards.md §2 Ports→Adapters, §3 naming, §4 TDD, §5 add-file traceability, §6 env  # KHÔNG §1 (microkernel hex_agent — kiến trúc khác)
  - drag_from_zero/README.md  # architecture-of-record: hai đồ thị, event-log là source-of-truth, ports
decisions:
  - DEC-A1 (lật/giới-hạn DEC-11) giữ drag_from_zero (event-sourced, tự xây) cho domain multi-agent; DEC-11 ('generic n8n-builder + bỏ event-sourcing + thuê Burr') re-scope về greenfield-generic-engine đã abandon, KHÔNG áp domain runtime này. Register lúc finish — docs/decisions.md là file commit, không tự ghi.
  - DEC-A2 FE seam = React Flow app MỚI sở hữu cả authoring + live-view nhúng; retire dc-runtime ui/ làm prior-art. dc-runtime source thiếu → mở rộng tại chỗ là ngược dòng.
  - DEC-A3 Canvas IS topology.json (1:1 schema Đồ thị-1); UI-metadata (position…) sống trong node.attrs.ui, INERT với wiring (wiring chỉ đọc key cụ thể, topology.py:31 gom phần dư vào attrs round-trip). Server validate bằng Topology.validate (topology.py:80). Không compiler — YAGNI.
  - DEC-A4 Quyết định substrate HOÃN tới verdict bakeoff; baseline Z (zero-dep) giữ ngôi tới khi challenger thắng NGOÀI noise band trên trục mid-run-inject + observability. Thêm Vite/TS (P2) + langgraph/burr (P4, optional extra) phá invariant có chủ đích — chấp nhận, đo được.
  - DEC-A5 Mid-run join = POST /api/runs/{id}/join {role} → orchestrator.join_agent (orchestrator.py:66); WS thêm case AGENT_JOINED→agent_joined + đổi TASK_WAITING→await_role (translate_event server.py:155-185, cả hai HIỆN không tới WS); Run mọc trạng thái 'awaiting' (parked ≠ done) ở P3. Bug hiện: parked run báo **done** (catch-all _final_status server.py:139-143; root DELEGATED không WAITING), KHÔNG "blocked".
  - DEC-A6 LLM = **factory** (callable 0-arg, mint per-run), KHÔNG shared instance — hai run-thread share một LLM sẽ race state (OpenAICompatLLM.last_meta/RecordedLLM._i/FakeLLM.calls không khoá). DEC-A7 KHÔNG tách server_app.py round này (giữ một file ~580 LOC, file-ownership ổn định xuyên P1/P3; SRP-split = nợ ghi).
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — Authoring UI thật + bakeoff substrate

> hs:cook đọc file này làm hợp đồng. Mọi claim không hiển nhiên có anchor `file:line`; thiếu anchor → tag `[UNVERIFIED]`.
> Core dragzero KHÔNG sửa. Chỉ thêm endpoint/adapter trên `server.py`/`run_server.py`, một app `app/` mới, một package `dragzero/bakeoff/` mới.

## Vì sao plan này

Scout phơi ra khoảng cách: **Process-view (Đồ thị 2) đã chạy** end-to-end (Slice 6a + 6b verifier, browser-verified — `drag_from_zero/README.md:199-202`), nhưng **Authoring (Đồ thị 1) chưa có một dòng nào** ở UI. Server chỉ phục vụ một run đúc sẵn read-only (`server.py:325-328` `App.runs = {one default}`; builder hard-code `run_server.py:70-99`). Topology→build_runtime→Run ĐÃ chứng minh trong test (`tests/e2e/test_topology_to_server.py:39-51`) nhưng dựng trong builder của TEST — REST không có endpoint tạo/sửa topology hay roster (`server.py:392-426` chỉ /session,/runs/{id}[/reset|start|artifacts|events]). `join_agent` (mid-run injection) **có trong runtime** (`orchestrator.py:66-71`) **nhưng không expose endpoint**, và event `AGENT_JOINED` log rồi (orchestrator.py:68) **nhưng không tới WS** (translate_event không có case, server.py:185). UI thật = dc-runtime (`x-dc`/React qua `support.js`), source build không có trong repo → grep `drag|drop|reactflow|topology` trong HTML = 0 hit.

"Làm UI kéo-thả thành thật" = **xây nửa authoring chưa tồn tại**, không phải nối nốt UI gần xong. Boundary đã gần sẵn (Slice 5 `topology.py` round-trip + validate; Slice 3a `join_agent` pause→inject→resume) — thiếu đúng **REST/WS surface** để UI đọc-ghi chúng.

User chốt (brief §5, 3 câu trả lời): **UI-first · bakeoff orchestrator-swap · drag_from_zero standalone**. Plan gộp 1 mạch, phase order khóa: (1) API boundary → (2) React Flow canvas → (3) mid-run join → (4) bakeoff Z·L·Bu. Bakeoff đứng CUỐI nên UI không chờ nó.

## Kiến trúc (giữ kỷ luật dragzero, không thêm hệ mới)

Hai đồ thị không bao giờ trộn (`README.md:9-22`): **Đồ thị 1 = topology = config** (drag-drop authoring); **Đồ thị 2 = execution tree = projection của event log** (`read_model.reduce`, `read_model.py:29`). Orchestrator là cầu. Event log là source-of-truth DUY NHẤT.

Plan này KHÔNG đụng cây đó. Nó **mở mặt I/O** quanh nó:
- **topology-in / roster-mutate / run-from-topology** → endpoint mới trên `server.py` (App giữ topology store + run factory). Phần lớn = expose Slice 5 (`wiring.build_runtime`, `wiring.py:29`) + Slice 3a (`join_agent`).
- **canvas** đọc-ghi đúng `topology.json` (DEC-A3) → React Flow là producer/consumer của cùng JSON + cùng event stream WS (đúng lời README:20-21 "UI là consumer của boundary cố định").
- **substrate sau boundary** → bakeoff swap adapter ở P4, KHÔNG đụng UI.

Hexagonal đã sẵn (code-standards §2): LLM port (`llm.py`), Tool port (`tools.py`), topology-as-data. "Orchestrator sau boundary" là cùng kỷ luật — đó là vì sao bakeoff khả thi mà không viết lại UI.

Bài học mang theo:
- **Core untouched** — chỉ `reduce(events)` đọc log (build_graph server.py:96-127); thêm endpoint là thêm reader/factory, không thêm state thứ hai (README:18-21). Sealed-room revalidator xác nhận: 4 năng lực (topology-in/run-from-topology/multi-run/join) đều với tới được từ server.py+run_server.py, zero core edit (join an toàn CHỈ với `resume=False`+`threading.Event`, vì orchestrator single-thread không khoá `_ready`/`_recs`, orchestrator.py:61-63).
- **Canvas = topology, không format thứ hai** (DEC-A3) — `topology.Node.from_dict` gom mọi key lạ vào `attrs` (topology.py:31) ⇒ position/UI-meta round-trip miễn phí, `wiring` bỏ qua chúng (`wiring.py:50-71` chỉ đọc role/tool/hook/rule/config/entry). DRY: một schema, một validate.
- **Mid-run inject là tính năng đã có, chỉ thiếu cửa** — `join_agent` → `_wake_waiting` → `run_until_idle` resume (orchestrator.py:66-87). P3 = lifecycle Run + endpoint, KHÔNG đụng orchestrator.

Bỏ lại (YAGNI round này — brief §8): verifier μ/done_when thật (Slice 6b, plan riêng `decompose_agent`), generic n8n-builder (DEC-11 vision — không theo), thay orchestrator trước khi bakeoff ra số, multi-user/authz/remote/persistence cross-session, plugin sandbox, schema-migration cho topology lưu đĩa.

## DEC (quyết định chốt round này)

- **DEC-A1 — Giữ drag_from_zero, giới-hạn DEC-11.** DEC-11 (`docs/decisions.md:142`, `affects:` line `:139` = "new-greenfield-repo, engine-core, config-spec, canvas-contract" — bằng chứng văn-bản DEC-11 scoped repo greenfield, KHÔNG toàn cục) chốt *generic n8n-builder + bỏ event-sourcing + thuê Burr* cho một **greenfield-generic-engine**. 3 câu trả lời session này chọn drag_from_zero (event-sourced, tự xây, domain multi-agent) → ngược DEC-11 nếu đọc là toàn cục. Quyết: DEC-11 re-scope về cái repo greenfield đã abandon (đúng affects line); domain runtime này KHÔNG bị nó ràng. Register DEC mới (hoặc `--append-alloc` DEC-11) lúc finish — KHÔNG tự ghi (`docs/decisions.md` commit). **NON-NEGOTIABLE spine của DEC-11 vẫn giữ:** ba state-lifetime tách (per-run / ledger ngoài graph / display ephemeral — brief §3, risk "gộp 3 vòng đời"); LLM không author route/verdict (đã đúng — `read_model`/gates/verifier là CODE, server.py:70-127).
- **DEC-A2 — FE seam = app React Flow mới sở hữu cả hai.** Authoring canvas + live-view (Đồ thị 2) nhúng cùng app, cùng WS. Retire `ui/` (giữ prior-art). dc-runtime source thiếu (`support.js` generated, không có `dc-runtime/src/*.ts`) → mở rộng tại chỗ ngược dòng. FE/BE tách sạch, một toolchain Vite/TS.
- **DEC-A3 — Canvas IS topology.json.** React Flow node/edge ↔ Đồ thị-1 schema 1:1. UI-meta (position, collapsed…) ∈ `node.attrs.ui` — inert với wiring. Server validate bằng `Topology.validate` (topology.py:80); invalid → 422 + list lỗi. Không canvas-format thứ hai, không compiler (YAGNI; design report §composition ủng hộ config-driven 1 lớp).
- **DEC-A4 — Substrate hoãn tới verdict bakeoff.** Baseline Z (zero-dep, đã thỏa boundary + mid-run-inject) giữ ngôi mặc định; challenger (L/Bu) phải **thắng** trên trục mid-run-inject + observability NGOÀI noise band mới soán. Burden of proof ở kẻ thách thức (verified-work-per-token). Thêm Vite/TS (P2) + langgraph/burr (P4 optional extra, base vẫn zero-dep) phá invariant có chủ đích — chấp nhận, **đo**.
- **DEC-A5 — Mid-run join lifecycle.** `POST /api/runs/{id}/join {role,[id]}` → `Agent(id|role, role, llm_provider())` → `orch.join_agent(agent, resume=False)` + `_join_evt.set()` → thread re-drive. Run mọc trạng thái **awaiting** (parked-on-missing-role ≠ done): hiện `_run` gọi `run_until_idle` một lần rồi mark **done** (KHÔNG blocked — catch-all `_final_status` server.py:139-143, root DELEGATED không WAITING) kể cả khi `waiting_count()>0` (server.py:264-276) → P3 sửa Run (KHÔNG sửa orchestrator) để park giữ thread sống + guard `reset/start` khi awaiting + `close()`/`/cancel` lúc shutdown + `_ws` keep-alive >60s. WS: thêm case `AGENT_JOINED`→`agent_joined` + đổi `TASK_WAITING`→`await_role` (translate_event server.py:155-185; cả hai HIỆN không tới WS).

## Module map (mới / sửa)

| path | action | trách nhiệm | nguồn |
|---|---|---|---|
| `drag_from_zero/dragzero/server.py` | modify | App: topology store + llm-factory + `create_run(topology,task)` + GET/POST `/api/topology`, POST `/api/runs`; (P3) `/api/runs/{id}/join`+`/cancel` + Run awaiting-lifecycle + `close()` + `agent_joined`/`await_role` frame + `_ws` keep-alive | expose wiring.py:29 + orchestrator.py:66; back-compat 5 make_server site |
| `drag_from_zero/run_server.py` | modify | inject llm-**factory** (callable) vào make_server + Run; `--ui-dir` resolve `app/dist`→fallback `ui/`; shutdown `app.close()` | run_server.py:70-123 |
| `drag_from_zero/app/**` | create | Vite+React+TS app: palette → React Flow canvas → serialize topology → POST → WS live tree (render verdict/status THẬT) → inject affordance | net-new (DEC-A2) |
| `drag_from_zero/dragzero/bakeoff/**` | create | `SubstratePort` + 3 adapter (Z reuse Orchestrator, L LangGraph, Bu Burr) + deterministic scenario + scalar scorer + drive `bakeoff_rank.py` | brief §4 trục 2 |
| `drag_from_zero/tests/test_authoring_api.py` | create | P1 contract: topology CRUD, run-from-topology, 422-on-invalid, multi-run | mirror test_slice6a_server.py |
| `drag_from_zero/tests/test_midrun_join.py` | create | P3: park→join→resume→child done qua HTTP; await_role frame | mirror test_slice3_workqueue.py + 6a |
| `drag_from_zero/tests/test_bakeoff_substrate.py` | create | P4: mỗi adapter chạy scenario; scorer cho điểm; verdict shape | brief §4 |
| `drag_from_zero/app/**/*.test.ts(x)` | create | P2/P3: serializer canvas↔topology (vitest) + e2e smoke (Playwright) | code-standards §4 |

## Phases (sequential — không phase nào song song; mỗi phase tự chứa)

1. **[phase-1-api-boundary.md](phase-1-api-boundary.md)** — Khóa API boundary substrate-agnostic trên `server.py`: topology store + run factory từ posted topology + multi-run registry. Core untouched. (Python, TDD)
2. **[phase-2-react-flow-canvas.md](phase-2-react-flow-canvas.md)** — App React Flow mới ăn boundary đó: palette→canvas→topology→Run→observe live tree. Vertical slice, 1 topology, trước mọi polish. (TS/React)
3. **[phase-3-midrun-join.md](phase-3-midrun-join.md)** — Wire mid-run inject: Run awaiting-lifecycle + `/api/runs/{id}/join` + `await_role` frame + FE affordance. Kịch bản chuẩn root→plan→delegate-empty→waiting→inject→resume→done từ UI. (Python + TS)
4. **[phase-4-substrate-bakeoff.md](phase-4-substrate-bakeoff.md)** — Bakeoff Z·L·Bu sau boundary, chạy scenario chuẩn, quyết bằng số → `bakeoff-verdict.json`. Gated SAU khi UI slice xanh. Off critical path. (Python + research nhẹ)

## Acceptance (toàn plan)

1. Author topology trong canvas (kéo agent/tool + nối edge), click **Run** → một run dragzero THẬT chạy, execution tree stream live trong **cùng app**.
2. Canvas serialize ra topology.json hợp lệ (`Topology.validate` pass); invalid → 422 + lỗi hiển thị trên UI; round-trip giữ UI-meta (position).
3. Kịch bản inject từ UI: planner delegate role trống → node hiện **await_role** → click inject role → run **resume** → child **done**. Event trace có `task_waiting`→`agent_joined`→child completed (P3 thêm case `AGENT_JOINED`→WS, server.py:185, vì hiện nó không tới WS — nếu không clause `agent_joined` này bất khả thi).
4. Bakeoff phát verdict pass schema `artifact-bakeoff-verdict` (`harness/schemas/…`) qua `bakeoff_rank.py record`+`rank --plan-dir <plandir>/artifacts` với **≥2 candidate đã chấm scalar**; <2 (thiếu langgraph/burr) → REFUSE "insufficient candidates", KHÔNG tự-đăng-quang Z. DEC substrate ghi CHỈ sau verdict ≥2.
5. **No regression:** TOÀN BỘ `drag_from_zero/tests` XANH — đặc biệt test_slice6a_server.py, test_slice6b_verifier.py, e2e/test_topology_to_server.py, e2e/test_entrypoints_smoke.py, integration/test_server_translation.py, test_invariants.py (core files diff rỗng — chứng minh seam thật).

## Rollback

Mọi thứ additive/cô lập: `git checkout drag_from_zero/dragzero/server.py drag_from_zero/run_server.py` + `rm -rf drag_from_zero/app drag_from_zero/dragzero/bakeoff drag_from_zero/tests/test_authoring_api.py drag_from_zero/tests/test_midrun_join.py drag_from_zero/tests/test_bakeoff_substrate.py`. Core (orchestrator/read_model/events/topology/wiring/roster/contracts/agent/llm/tools) KHÔNG đụng → revert không chạm chúng. Bakeoff dep ∈ optional extra → base install vẫn zero-dep dù không rollback.

## Risk (toàn plan — chi tiết per-phase trong file phase)

| Risk | L×I | Mitigation |
|---|---|---|
| "UI thật" phình thành React Flow app + backend CRUD + gỡ dc-runtime | high×slice-slip | Vertical slice P2: 1 topology, author→run→observe TRƯỚC mọi polish; P3 thêm inject; save-to-disk/library/theming = OUT |
| Boundary KHÔNG đủ substrate-agnostic → L/Bu không slot được, P4 vô nghĩa | med×P4-waste | P1 định nghĩa `SubstratePort` tối thiểu {compose-from-topology, run, park-on-empty-role, inject, observable-events}; P4 đo trên port đó, KHÔNG ép L/Bu lái full UI |
| Run awaiting-lifecycle (P3) sửa sai → regress (run báo **done** khi đáng lẽ park; second /start orphan thread; WS rớt 60s; thread treo lúc shutdown) | high×regress | P3 sửa CHỈ Run/_Handler (server.py), orchestrator diff rỗng; guard `reset/start` khi awaiting + `close()`/`/cancel` + `_ws` keep-alive; diagnosis-pin test (parked hiện báo done); chi tiết phase-3 |
| Bakeoff: shape-mismatch bakeoff_rank.py / observability Z-shaped / <2 candidate tự-đăng-quang | high×broken-or-rigged | metric scalar/trial drive `record`+`rank` THẬT; observability = checklist TRUNG LẬP (Z không auto-1.0, non-Z sign-off); <2 → REFUSE; chi tiết phase-4 |
| Bakeoff tràn critical path / relitigate DEC-11 mãi | med×token-bleed | Bakeoff = phase CUỐI (chỉ sau UI xanh), deterministic scenario, verdict đóng câu hỏi vĩnh viễn |
| Gộp 3 vòng đời state khi sau thêm chat/turn | low(chưa tới)×murder-to-undo | Ghi invariant (DEC-A1 spine): ledger ngoài graph, reset per-run, display ephemeral — KHÔNG implement chat round này, chỉ giữ cửa |
| Authoring topology KHÔNG có done_when → trạng thái node | med×UX | Verifier Slice 6b **đã live** (server.py:70-127): node không-done_when = `unverified` (honest, KHÔNG faked-pass); FE render `verdict` + `runtime.status` (đã gộp verdict, server.py:110-114) VERBATIM, KHÔNG tự suy pass/fail. (KHÔNG còn "stub" — verdict là CODE thật.) |
| node v26/Vite toolchain lạ trong repo Python-thuần | low×friction | `app/` cô lập, có README + `npm run build`→`app/dist`; server chỉ serve static; CI Python không phụ thuộc app |

## Resolved (post adversarial review — sealed-room + red-team)

- **server_app.py split** → KHÔNG tách round này (DEC-A7): giữ một file ~580 LOC, file-ownership ổn định xuyên P1/P3. SRP-split = nợ ghi.
- **LLM-provider** → **factory** (DEC-A6), KHÔNG shared instance (race red-team). Per-run override = OUT.
- **Run awaiting bug diagnosis** → parked run hiện báo **done** (catch-all `_final_status` server.py:139-143), KHÔNG "blocked" (sealed-room overturn). P3 pin bằng test.
- **Bakeoff handoff** → `bakeoff_rank.py` là scalar ledger (record/rank, 2..4 candidate, mỗi candidate ≥1 trial). Metric = MỘT scalar/candidate; observability = checklist trung lập; <2 → REFUSE (phase-4).

## Mở (resolve khi cook)

- `[ ]` Bakeoff observability rubric chính xác 4 probe + trọng số inject_clean vs observability — chốt đầu P4 sau research lấp substrate table DEC-11.
- `[ ]` `drag_from_zero` **chưa commit** (`git ls-files`=0). "core-untouched" chỉ git-enforce được SAU commit — handoff cook nên commit baseline trước phase 1 (hoặc phase 0).

## GLOSSARY (thuật ngữ load-bearing plan này coin — append docs/GLOSSARY.md lúc approve)

`awaiting` (Run parked-on-missing-role, `waiting_count()>0`, thread sống chờ join Event — khác `done`, khác `blocked` vốn đã map WAITING→blocked trong `_UI_STATUS`), `await_role` (WS frame typed thay `block` cho TASK_WAITING), `SubstratePort` (hợp đồng hành vi bakeoff), `Đồ thị 1 / Đồ thị 2` (topology-config / execution-tree-projection).
