---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# UI critique — `drag_from_zero/ui/` → nền tảng kéo-thả compose agent/tool/hook/budget/policy

Scope: `drag_from_zero/ui/{Agent IDE.dc.html, project-data.js, support.js}` + server/topology contract. Read-only. 2026-06-26.
Tiền đề: codebase map backend đã có (`plans/reports/codebase-map-260626-2229-drag-from-zero-report.md`) — báo cáo này lấp đúng chỗ map bỏ trống ("`ui/` not deeply read").

## Một câu

Bộ UI hiện tại là **observer của Đồ thị 2 (execution tree)** — đẹp, live, animated — nhưng **không có một mảnh authoring nào**: zero drag, zero palette, zero node-create, zero edge-draw, budget/policy read-only; còn cái user muốn là **editor cho Đồ thị 1 (Topology)**, một graph KHÁC, node KHÁC, edge KHÁC, vòng đời KHÁC.

## Cốt lõi: hai graph, UI đang vẽ nhầm cái

| | Đồ thị 1 — Topology (cái user muốn kéo-thả) | Đồ thị 2 — Execution tree (cái UI đang vẽ) |
|---|---|---|
| thời điểm | design-time, **người soạn** | run-time, **orchestrator mọc ra** |
| node type | `agent / tool / router / memory / hook` (`topology.py:15`) | task instance + status |
| edge type | `delegates_to / uses_tool / subscribes / routes` (`topology.py:16`) | `child` / depends |
| nguồn | JSON người viết, `Topology.from_dict` | projection của event log, `read_model.reduce` |
| trong UI | **KHÔNG TỒN TẠI** | `layout()` + SVG (`Agent IDE.dc.html:537-684`) |

Không thể "thêm kéo-thả" vào view execution-tree. Phải dựng **canvas thứ hai** bind vào `topology.to_dict()`. `topology.py:5` đã ghi rõ ý đồ: *"the React Flow UI reads and writes exactly this"* — UI shipped không đọc cũng không ghi nó.

## Nợ ngữ nghĩa: drawer đang FAKE skills/hooks/rules

Drawer nhìn như đã có SKILLS/HOOKS/RULES — nhưng đó là **nhãn dán đè lên field của execution-tree**, không phải attrs thật của agent:

| Nhãn UI | Thực chất gán | Bằng chứng |
|---|---|---|
| badge "μ / checks / status" | μ, `done_when.length`, runtime status | `:643-645` |
| drawer `skills` | `done_when.map(d=>d.check)` | `:701` |
| drawer `hooks` | `node.depends_on` | `:702` |
| drawer `rules` | dòng `evidence` của verdict | `:696,703` |

`project-data.js` (mock tĩnh) MỚI là spec đúng — mỗi agent có `prompt/skills/hooks/rules/loads` thật (`:197-248`) — nhưng nó là **dead data**, HTML live kéo từ backend chứ không từ `PROJECT/AGENTS/VIRTUAL`. Server (`build_graph`, `server.py:70-77`) còn **stub** `done_when` = `{"check":"writes","artifact":p}` từ artifacts, `mu` = subtree size. Tức "spec" hiển thị là **tổng hợp một phần, không phải do người soạn**.

## Backend đã sẵn 60%, server che mất

Tốt: `topology.py` model + `validate()` đúng cái authoring-UI cần — luật: 1 entry agent (`:104`), required attr theo type (`agent→role, tool→tool, hook→hook, router→rule`, `:90`), edge endpoint phải tồn tại (`:95-98`), phải có ≥1 agent (`:102`). `wiring.build_runtime` biến topology → Orchestrator chạy được. `load_file/dump_json` có sẵn.

Xấu: `server.py` **không expose miếng nào**. Route chỉ run-only:
```
GET  /api/session                      → session + execution graph
GET  /api/runs/{id} | /artifacts | /artifact?path=
POST /api/runs/{id}/reset | /start
WS   /api/runs/{id}/events
```
Thiếu sạch: GET/PUT topology, validate, node/edge CRUD, set budget, build-run-from-posted-graph. UI hôm nay **không có cách nào submit một graph** — run đã được seed sẵn server-side.

## Cần thêm gì — xếp theo tier

**Tier 0 — mở đường cho authoring (backend, bắt buộc trước):**
1. `GET/PUT /api/topology`, `POST /api/topology/validate` (trả `validate()` errors), `POST /api/runs` (build_runtime từ topology POST → runId). Không có cái này thì UI kéo-thả vô nghĩa.
2. Node payload gửi **attrs thật** (role, prompt, skills, hooks, rules, tools, entry, budget) → drawer thôi fake.

**Tier 1 — canvas kéo-thả (cái "kéo thả"):**
3. **Palette** sidebar: 5 node type draggable (`agent/tool/router/memory/hook`). Thả lên canvas → tạo `Node` với attrs mặc định.
4. **Drag-position + connect**: node kéo được; kéo từ handle → handle tạo `Edge`; picker edge-type, **ràng buộc theo endpoint** (vd `uses_tool` chỉ trỏ tới node `tool`).
5. **Node inspector** (thay drawer read-only): form bind theo type — agent: `role*`, prompt, skills[], hooks[], rules[], tools[], entry(bool); tool: `tool*`; hook: `hook*`; router: `rule*`. Đánh dấu required từ map `:90`.
6. **Live validate**: chạy `validate()` mỗi edit (debounce), báo lỗi inline (trùng id, thiếu required, edge treo, không agent, >1 entry). **Khóa Run tới khi sạch.**

**Tier 2 — budget + policy ("set budget, policy linh hoạt"):**
7. **Budget panel**: edit `topology.budget` (registries.Budget **disabled tới khi set limit** — nên field "max steps/tokens/cost" ghi vào budget). Run thì show meter spend-vs-cap (engine emit `BUDGET_EXCEEDED`).
8. **Policy/hook/rule**: chọn từ `builtins.BUILTIN_HOOKS` (deny_delegation/deny_all) + `BUILTIN_RULES` (by_keyword/always) gắn per-node, bind hook vào phase (pre_plan/pre_delegate), rule vào router. ⚠ map đã cảnh báo: **per-agent tool/delegation permission chưa enforce runtime** → soạn xong mới nửa thật, cần enforcement song song.

**Tier 3 — tách mode + tận dụng backend:**
9. **Hai mode, một model**: "Author" (sửa Đồ thị 1) vs "Run/Observe" (xem Đồ thị 2). Đừng trộn. Execution node nên link ngược về topology node sinh ra nó.
10. **Persistence**: save/load topology có tên (`load_file/dump_json` sẵn; schema đã có `version`).
11. **Mid-run injection UI** — đòn bẩy bị bỏ phí: engine có `join_agent` (pause→inject→resume, **tính năng đầu bảng** của backend). Kéo agent mới lên graph đang chạy → `join_agent` → đánh thức task đang park. Backend support sẵn, UI lờ hoàn toàn.

## Một ý kiến mạnh

**Đừng nuôi drag-drop bên trong renderer SVG tay của `.dc.html`.** Đây là framework "DC" riêng (`DCLogic/x-dc/sc-for`, `:312`), renderer hiện tại read-only: `layout()` auto-position, không node-drag, không edge-handle, không persist vị trí, không undo. Nó là **observer tốt** — giữ cho Run/Observe mode. Author canvas cần node-drag + connection-validation + marquee + undo → đó là đất của **React Flow / Svelte Flow**, đọc/ghi thẳng `topology.to_dict()`. `topology.py:5` đã giả định React Flow — cứ theo.

## Vụn cần dọn

- `project-data.js` + `ui_drag/` (bản sao y hệt): nửa-có, gây nhiễu. Hoặc wire làm design-time seed (nó là spec drawer đúng), hoặc xóa.
- Chat dock không phải hội thoại: `send()` chỉ gọi `run()` (`:478-484`). Nếu "policy linh hoạt" định gồm cấu hình bằng ngôn ngữ tự nhiên thì đó là việc khác — hiện chat = nút Run trá hình.
- `langgraph.config.ts` mock (`project-data.js:153`) nghịch memory [[hex-agent-lessons-to-carry]] (DROP langgraph) — chỉ là nội dung demo giả, đừng để nó ngụ ý langgraph là model.

## Thứ tự đề xuất

Tier 0 → Tier 1 (palette+inspector+validate) là MVP authoring. Tier 2 budget/policy phụ thuộc enforcement backend (Slice 6b verifier — gap lớn nhất map đã nêu). Tier 3 mid-run-injection là differentiator rẻ vì backend đã có.

## Unknowns (verify trước khi build)

- `support.js` (1595 dòng) chưa đọc sâu — runtime của framework DC; cần biết nó support drag/pointer-event tới đâu trước khi quyết "extend vs swap React Flow".
- React Flow trong `.dc.html`: nhúng lib ngoài vào framework DC có khả thi không? Chưa kiểm.
- `memory` node type vẫn là placeholder chưa wire (`wiring.py:70`, theo map) — authoring nó sẽ vẽ được nhưng chạy chưa ra gì.
- Multi-user / concurrent edit topology: server `http.server` single-process daemon thread — chưa rõ chịu được PUT đồng thời không.
