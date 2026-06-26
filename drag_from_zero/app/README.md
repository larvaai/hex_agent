# dragzero authoring UI (React Flow)

The drag-drop half of Đồ thị 1: author a topology on a canvas, hit **Run**, and watch the
execution tree (Đồ thị 2) stream live in the same app. The canvas **is** `topology.json`
(DEC-A3) — UI-meta (positions) round-trips through `node.attrs.ui`, inert to wiring.

This app is isolated from the Python core. The Python CI does not depend on it.

## Develop

```bash
cd app
npm install
# terminal 1 — backend (serves the boundary on :8000)
python ../run_server.py
# terminal 2 — Vite dev server, proxies /api + WS -> :8000
npm run dev            # http://localhost:5173
```

## Build (what the server serves in prod)

```bash
npm run build          # -> app/dist
python ../run_server.py --ui-dir app/dist   # serves the built app at :8000
```

## Test

```bash
npm run test           # vitest — serializer + verdict-render units (no DOM, no server)
npm run test:e2e       # Playwright smoke — author -> run -> tree (needs a built dist + server)
npm run typecheck      # tsc --noEmit
```

## Boundary used (Phase 1)

- `POST /api/topology` → validate (`Topology.validate`) → `{id}`; invalid → **422** `{errors:[...]}`
- `POST /api/runs` `{topology_id|topology, task}` → `{id}`
- `POST /api/runs/{id}/start`, WS `/api/runs/{id}/events`
- `POST /api/runs/{id}/join` `{role}` (Phase 3, mid-run inject)

The client renders `runtime.status` + `verdict` **verbatim** — it never recomputes pass/fail.
A node with no authored `done_when` shows **unverified** (honest), never a faked green pass.
