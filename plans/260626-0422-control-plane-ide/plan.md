---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Control-plane IDE — turn the E21 UI into an opencode-like IDE

**Goal.** The React control-plane UI (`ui/control-plane/`) becomes a working IDE: prompt the
agent, watch it run (graph + timeline), **see files, edit files, and review the agent's diffs** —
feature parity with opencode's core loop. No approval gates; isolated env.

**Base = the control-plane UI only** (per user). The legacy `ui/static` console is untouched.

## Architecture

```
ui/ide/ (NEW live backend)            ui/control-plane/src/ (extend React app)
  files.py   workspace file ops         adapter/files.ts   file transport
  bridge.py  KernelEvent → loop.*        components/FileExplorer.tsx
  runner.py  run agent in a thread       components/CodeEditor.tsx  (CodeMirror)
  server.py  HTTP: control + files       components/DiffPanel.tsx
  __main__.py                            state/fileStore.ts
                                         App.tsx + App.css  (IDE layout)
```

The live backend speaks the **same control contract** the fake server does (reuses `control/`:
`build_snapshot`, `EventReplayBuffer`, `Redactor`, `parse_command`, registries) so the existing
adapter/store/graph/timeline keep working unchanged — but it **runs the real agent** and adds a
**file API**. Drop-in: point `VITE_CP_BASE_URL` at it.

## Backend HTTP seam (the contract frontend builds against)

Control (unchanged shape, now live):
- `GET  /api/snapshot?session=…` → `TaskLoopSnapshot`
- `GET  /api/stream?token=…&lastEventId=…` → SSE, **held open**, pushes new events live
- `POST /api/commands` (X-Auth-Token) → `CommandAck`; `SubmitPrompt` starts a real run

Files (NEW, all under workspace path-jail via `safety.sandbox`; CORS + OPTIONS like the fake):
- `GET    /api/files/tree?scope=workspace|project` → `{root, scope, tree, entries, truncated}`
- `GET    /api/files/read?scope=&path=` → `{path,name,content,size,language}`
- `PUT    /api/files/write` `{scope,path,content}` → `{ok,bytes}`  (user edits)
- `POST   /api/files/create` `{scope,path,kind:file|dir}` → `{ok}`
- `POST   /api/files/rename` `{scope,path,to}` → `{ok}`
- `DELETE /api/files?scope=&path=` → `{ok}`
- `GET    /api/files/diff?session=` → `[{path,status,additions,deletions,diff}]`
  (unified diff vs a **baseline** snapshotted at run start; `difflib`, stdlib)

Guards (reuse legacy console's): path-jail, sensitive names/suffixes, binary/size limit,
ignored dirs, project-scope hidden paths.

## Event bridge (only emits types the adapter listens for)

`kernel.events.subscribe(fn)` → emit redacted `RuntimeEvent`s into the session buffer:
- run start → `loop.team_composed`{selected:[agent:root]} + `loop.decision`(root running)
- `tool.*` → `loop.tool`{tool, ok, status, path}  (path lifted from fs-tool args → timeline gold)
- run end → `loop.turn`{agent_id:agent:root, outcome:final} + `loop.finished`|`loop.failed`

seq via `SessionSeq`; redaction via `Redactor.apply`; buffer dedups by event_id; SSE resumes by seq.

## Frontend

- **CodeMirror** (`@uiw/react-codemirror`, one-dark, lang-python/js/json/markdown) — view+edit,
  Cmd/Ctrl+S save, dirty state, external-change (agent wrote) reload prompt.
- **FileExplorer** — tree, scope toggle, new/rename/delete, click→open tab; flashes agent-changed files.
- **DiffPanel** — per-file unified diff of the agent's changes for the current session.
- **App layout** — left Explorer · center Editor/Diff tabs · right Agent (Graph+Timeline+Inspector) ·
  bottom PromptBox+status. ApprovalModal overlay kept.

## Verify
Backend: start `python -m ui.ide`, curl tree/read/write/diff, submit a prompt (LLM optional;
errors stream honestly). Frontend: `tsc --noEmit` + `vite build` + dev preview, exercise edit/save/diff.
Then adversarial review workflow → fix.

## Status — IMPLEMENTED + VERIFIED (2026-06-26)

Built & proven end-to-end:
- Backend `ui/ide/` (files, session, bridge, runner, server) — `python -m ui.ide --port 8800`.
- Frontend extended: `adapter/files.ts`, `state/fileStore.ts`, `FileExplorer`/`CodeEditor`/`DiffPanel`,
  IDE layout in `App.tsx`/`App.css`. `tsc` + `vite build` clean; 20/20 existing vitest pass.
- Backend tests `tests/test_ide_backend.py` (11) pass; full offline suite (308) green; ruff clean.
- Live proof: prompted "create calc.py with add(a,b)" → agent ran `fs_write` → file created;
  "add subtract" → agent ran `fs_read`+`fs_write` → diff showed `calc.py modified +4/-0`. Editor
  (CodeMirror, Python highlight), Changes diff, live timeline, FINISHED status all verified in-browser.

Two fixes the IDE needed to actually work:
1. **`llm/adapter.py`** — the local model 400s on `response_format={"type":"json_object"}` ("must be
   'json_schema' or 'text'"). Added a one-shot downgrade to text mode (JSON gate parses text anyway).
2. **`ui/ide/runner.py`** — `DEFAULT_SYSTEM` lists no tools, so the model guessed `write_file`/`file_editor`
   and failed. Now injects a live tool catalog (exact names + arg hints) into the system prompt.

## Security review (adversarial workflow, 11/13 confirmed → all fixed/triaged)
- HIGH: file API now token-gated (was open); CORS reflects localhost-only (was `*`) — closes the
  cross-origin read/write + hook-planting chain. MED: broader sensitive-file guard; concurrent-run guard.
  LOW: bounded dedup/pending; debounced refresh; reloadTab no-lost-edit; explorer row props.
  See [report](reports/implementation-260626-0422-control-plane-ide-report.md).

## Open questions
- LLM at `localhost:1234` (LM Studio) must be up for real agent runs; file editing works without it.
- Agent reliability is bounded by the local model's instruction-following, not the IDE.
