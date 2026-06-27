---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 5 — L5 (OPTIONAL) IDE-half component tests

**Status:** OPTIONAL — trim at approval. Not E2E/manual (the named ask), but required for "đầy đủ":
the 6 IDE components have ZERO coverage. Cheapest coverage win (vitest+jsdom, adapter mocked,
`@testing-library/user-event` already a devDep).

## Files (mirror existing `components/__tests__/*.test.tsx` style)
`FileExplorer.test.tsx` · `DiffPanel.test.tsx` · `ChatPanel.test.tsx` · `SessionBar.test.tsx` ·
`Terminal.test.tsx` · `CodeEditor.test.tsx`

## Tests Before (red) → assertions (pure-fn + render, mock adapter)
- **FileExplorer** (FileExplorer.tsx:79) — tree recursion renders nested dirs/files; `changed` Set marks a
  file with the dot indicator; scope toggle switches workspace/project; click file → `openFile` called.
- **DiffPanel** (DiffPanel.tsx:43) — diff list renders status color + `+`/`−` stat; click row → open in editor;
  empty state when no diffs.
- **ChatPanel** (ChatPanel.tsx:57) — folds `chat.user/assistant/error` + `loop.tool` events into bubbles;
  tool step ✓/✗; Stop button shows only when snapshot.status ∈ RUNNING; no secret in rendered text.
- **SessionBar** (SessionBar.tsx:13) — dropdown lists sessions, current highlighted; New → create called;
  status chip renders.
- **Terminal** (Terminal.tsx:20) — entry log renders cmd/stdout/stderr/rc; input disabled while busy;
  Enter runs.
- **CodeEditor** (CodeEditor.tsx:36) — tab bar renders scope:path; dirty pill ● on edit; Cmd/Ctrl+S → save;
  language detection picks highlighter. (CodeMirror under jsdom — assert on the wrapper/state, not paint.)

## "Is the test real?" gate
Pure-function extraction where possible (like `agentsToFlow`/`filterEvents` in existing tests) so assertions
bite logic, not jsdom paint. Each test must fail if the mapping is inverted.

## Regression Gate
`npm --prefix ui/control-plane test` green; build (`tsc --noEmit && vite build`) clean.
