---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — React Flow authoring canvas (app mới, ăn boundary P1)

**Mục tiêu:** "UI thật". App Vite/React/TS độc lập: palette → kéo node lên React Flow canvas → nối edge → serialize ra `topology.json` → POST → Run → xem Đồ thị-2 stream live trong **cùng app**. Vertical slice: 1 topology, author→run→observe TRƯỚC mọi polish (mitigation risk "UI phình").

**Files:**
- Create: `drag_from_zero/app/**` (toàn bộ app mới — `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/canvas/*`, `src/topology/serialize.ts`, `src/live/*`, `src/api/client.ts`, `README.md`)
- KHÔNG đụng: server.py (P1 đã làm `--ui-dir` resolve `app/dist`), core, `ui/`
- Delete: không xóa `ui/` (giữ prior-art — DEC-A2)

## Requirements

**Functional:**
- **Palette** 5 node-type khớp `NODE_TYPES` (topology.py:15): agent / tool / router / memory / hook. Kéo lên canvas → React Flow node mang `attrs` tối thiểu bắt buộc (`Topology.validate`: agent→`role`, tool→`tool`, hook→`hook`, router→`rule`; topology.py:90).
- **Edge** kéo nối, type ∈ `EDGE_TYPES` (topology.py:16): delegates_to / uses_tool / subscribes / routes.
- **Serialize** canvas → topology JSON: `{version, nodes:[{id,type,...attrs, ui:{position}}], edges:[{from,to,type}], budget?}`. Đúng shape `Node.to_dict`/`Edge.to_dict` (topology.py:33,47). UI-meta vào `attrs.ui` (DEC-A3, inert với wiring.py:50-71).
- **Run flow:** "Run" → `POST /api/topology` (hiện errors nếu 422) → `POST /api/runs {topology_id, task}` → `POST /api/runs/{id}/start` → mở WS `/api/runs/{id}/events` → render execution tree từ `snapshot.graph` + animate theo event frames (`activate/propose/decompose/verdict/block/run_end` — translate_event:118-135).
- **Live tree view** nhúng cùng app (DEC-A2): consume cùng WS frames Slice 6a/6b phát; render `{root,nodes,edges}` graph (`build_graph` server.py:96-127). Node shape server gửi đã đủ: `{id, goal, mu, done_when, verdict, depends_on, children, runtime:{status,agent}}`. **Verifier Slice 6b ĐÃ live** — `runtime.status` đã GỘP verdict (FAIL→blocked, PASS→done, server.py:110-114) + field `verdict`∈{PASS,FAIL,pending,unverified}. FE render `runtime.status` + `verdict` VERBATIM, KHÔNG recompute. Topology authoring không có done_when → node `unverified` (honest), KHÔNG faked-pass — đó là cách "tolerate" đúng (KHÔNG phải stub).
- **Dev:** `npm run dev` (Vite) proxy `/api/*` + WS `/api/runs/*/events` → `127.0.0.1:8000`. **Prod:** `npm run build` → `app/dist` → server serve static (P1 `--ui-dir`).

**Non-functional:**
- App cô lập: CI Python KHÔNG phụ thuộc. `app/README.md` ghi `npm i && npm run build`.
- `@xyflow/react` (React Flow v12) là canvas; KHÔNG fork platform (DEC-A2 / brief option C loại).
- OUT round này: save-topology-to-disk, topology library/list-UI, multi-canvas, theming, undo/redo, validation-as-you-type (chỉ validate lúc Run). Mid-run inject affordance = P3.

## Tests Before (đỏ)

- **vitest** `src/topology/serialize.test.ts` (pure fn, không DOM):
  - canvas {2 agent node + 1 delegates_to edge} → topology JSON; `nodes[i].type`/`attrs.role` đúng; edge `{from,to,type}` đúng.
  - position/UI-meta đi vào `attrs.ui`, KHÔNG vào top-level required key (round-trip an toàn qua server validate).
  - agent node thiếu `role` → serializer KHÔNG tự bịa (để server 422 bắt) — assert field vắng, không silent-default.
  - `version` mặc định 1; budget node optional.
- **vitest** `src/live/treeview.test.ts` (verdict render — verifier live, KHÔNG stub): node `{verdict:"FAIL", runtime:{status:"blocked"}}` → render trạng thái blocked (đỏ), KHÔNG xanh; `verdict:"unverified"` → trạng thái trung tính, KHÔNG faked-pass. (Chống FE tự suy pass/fail; mirror server.py:110-114.)
- **Playwright e2e** `src/e2e/author-run.spec.ts` (smoke DOM canvas, chạy với server thật `--ui-dir app/dist`):
  - load app → kéo planner + coder agent + edge delegates_to → click Run → trong N giây execution tree xuất hiện root + ≥1 child (decompose) + 1 verdict; KHÔNG console error.
  - **Phân vai test (tránh trùng pytest browser-marker DEC-12):** JS Playwright phủ DOM canvas React mới; backend author→run đã được `tests/e2e/test_topology_to_server.py` phủ → JS e2e là smoke MỎNG, KHÔNG nằm trong pytest `browser` marker, KHÔNG chạy trong CI Python.

## Implement

1. **Scaffold** `app/`: `npm create vite@latest` (react-ts) thủ công hoá → `package.json` deps `react`, `react-dom`, `@xyflow/react`; dev `vitest`, `@playwright/test`. `vite.config.ts` proxy `/api`→8000 (+ `ws:true` cho `/api/runs`).
2. **`src/api/client.ts`:** `postTopology(t)`, `createRun(topologyId, task)`, `startRun(id)`, `openEvents(id, onFrame)` (WebSocket). Map 422 → throw với `errors`.
3. **`src/canvas/`:** React Flow `<ReactFlow>` + `Palette` (5 node-type) + node component hiện `type` + field bắt buộc (input role/tool/...). onDrop tạo node id duy nhất.
4. **`src/topology/serialize.ts`:** `canvasToTopology(nodes, edges, budget?) -> TopologyJSON` (pure). Đảo: `topologyToCanvas` (để load example) — đọc `attrs.ui.position`.
5. **`src/live/`:** `TreeView` render `graph` từ snapshot; `useRunStream` apply event frames (highlight node theo `activate/verdict/block`). Reuse vocab translate_event.
6. **`src/App.tsx`:** layout canvas trái + tree phải; nút Run chạy flow; panel lỗi 422.
7. **`app/README.md`:** build/dev/test; ghi rõ `dist` là cái server serve.

## Tests After / Regression Gate

- `cd app && npm run test` (vitest) xanh; `npm run build` thành công → `app/dist` tồn tại.
- `npm run test:e2e` (Playwright, tự spin `python run_server.py --ui-dir app/dist` hoặc dev proxy) — author→run→tree smoke xanh.
- Python suite KHÔNG đổi (app không chạm core/server) → 6a/invariants vẫn xanh.
- Verify thật (preview tools / hs-devops:web-testing): screenshot canvas + tree sau Run.

## Success Criteria

- [ ] Kéo ≥2 agent + 1 edge lên canvas, Run → run THẬT chạy, tree stream live trong cùng app.
- [ ] Serializer test xanh; topology POST hợp lệ pass `Topology.validate`; topology hỏng → UI hiện 422 errors.
- [ ] UI-meta (position) round-trip qua `attrs.ui`, không phá validate.
- [ ] `npm run build` → `dist`; server `--ui-dir app/dist` phục vụ app; 0 console error.
- [ ] Vertical slice ONLY — không save-to-disk/library/theming (YAGNI giữ).

## Risk

| Risk | L×I | Mitigation |
|---|---|---|
| App phình quá vertical slice | high×slice-slip | Definition-of-done = author→run→observe 1 topology; mọi thứ khác OUT (liệt kê rõ Requirements) |
| WS qua Vite dev proxy không upgrade | med×dev-friction | `vite.config.ts` proxy `ws:true` cho path `/api/runs`; e2e chạy với `--ui-dir dist` (server serve trực tiếp, không proxy) làm nguồn chân lý |
| React Flow node id va với topology id rule | low×bug | serializer sinh id slug an toàn, unique-check trước POST (server validate dup: topology.py:83) |
| FE tự suy pass/fail thay vì đọc verdict CODE | med×UX-sai | verifier 6b live; FE render `runtime.status`+`verdict` VERBATIM (server.py:110-114,123), KHÔNG recompute; vitest pin FAIL→blocked |
| Playwright nặng/chậm CI | low×time | e2e = 1 smoke; unit serializer mang phần lớn coverage |
