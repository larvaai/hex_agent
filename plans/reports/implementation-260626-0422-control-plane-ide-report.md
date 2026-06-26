---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Control-plane UI → Agent IDE — implementation report

**Date:** 2026-06-26 · **Branch:** feat/docs-diataxis-restructure · **Plan:** [plan](../260626-0422-control-plane-ide/plan.md)

Turned the E21 control-plane React UI into an **opencode-style IDE**: prompt the agent, watch it run
(graph + timeline), and **browse / edit / review the agent's file changes**. Built on the control-plane
UI only (legacy `ui/static` console untouched).

## What shipped

**Backend `ui/ide/`** (`python -m ui.ide --port 8800`; serves the built UI + API):
- `files.py` — workspace/project file ops behind the `safety.sandbox` jail: tree, read, write, create,
  rename, delete, and a `difflib` **diff** vs a per-run baseline. Sensitive-file + binary + size + ignored-dir guards.
- `session.py` — live `EventReplayBuffer` per session; `emit()` stamps seq + redacts (reuses `control/`).
- `bridge.py` — KernelEvent (`tool.*`) → control `loop.tool` (correlates request→completion for the file path).
- `runner.py` — runs the real agent on a thread; frames it as `loop.team_composed/decision/turn/finished`.
- `server.py` — control contract (snapshot / **held-open** SSE / commands) + `/api/files/*`; serves `dist/`.

**Frontend** (`ui/control-plane/src/`): `adapter/files.ts`, `state/fileStore.ts`, components `FileExplorer`,
`CodeEditor` (CodeMirror 6, syntax highlight, ⌘/Ctrl+S), `DiffPanel`; IDE layout in `App.tsx` + `App.css`.
Existing Graph/Timeline/Inspector/Approval kept.

## Two fixes the IDE needed to actually edit files
1. **`llm/adapter.py`** — the user's local model 400s on `response_format=json_object` ("must be json_schema
   or text"); added a one-shot downgrade to `text` (the JSON gate parses text anyway). Env fact, not a bug we caused.
2. **`ui/ide/runner.py`** — `DEFAULT_SYSTEM` lists no tools, so the model guessed `write_file`/`file_editor`
   and failed; now injects a live tool catalog (exact names + arg hints) into the system prompt.

## Security hardening (from the adversarial review — 11 confirmed findings)
- **[HIGH] file API was unauthenticated** → every `/api/files/*` now requires the `X-Auth-Token` (frontend
  sends it on all calls). Verified: no-token read/write/tree → **401**.
- **[HIGH] wildcard CORS** → ACAO reflected only for localhost dev origins; verified evil.com gets **no ACAO**,
  localhost:5173 reflected. Together these close the cross-origin read/write (CSRF + hook-planting) chain.
- **[MED]** broadened sensitive-file guard (`.env*` prefix, `.git-credentials/.netrc/.npmrc/.pgpass/.htpasswd`,
  `id_ecdsa/id_dsa`); concurrent-run guard (`runner.start` refuses over a live run → no baseline clobber).
- **[LOW]** bounded `_dedup` (4096) and bridge `_pending` (1024); debounced the per-event refresh storm;
  `reloadTab` re-checks dirty at commit (no lost edits); FileExplorer rows take props (no full-tree re-render).
- Skipped (cosmetic): adapter error-message attempt under-count.

## Verification
- `tsc --noEmit` + `vite build` clean; **vitest 22/22**; **pytest 310 offline (incl. 13 new IDE tests)**; **ruff clean**.
- Live, in-browser: prompted *"create calc.py with add(a,b)"* → agent ran `fs_write` → file appeared;
  *"add subtract"* → agent ran `fs_read`+`fs_write` → **Changes** showed `calc.py modified +4/-0`; CodeMirror
  edit/save + token-gated reads confirmed. Security: no-token → 401, evil-origin → no ACAO.

## Run
```bash
npm --prefix ui/control-plane run build && python3 -m ui.ide --port 8800   # → http://127.0.0.1:8800
```
Needs the local LLM (`LLM_BASE_URL`, default LM Studio :1234) for agent runs; file editing works without it.

## Open / unresolved
- Agent reliability is bounded by the local model's instruction-following, not the IDE.
- `/api/snapshot` is intentionally token-free (matches the original control contract; exposes only redacted UI state).
- Right-rail graph fitView clips the second node at narrow widths (cosmetic; react-flow timing).
