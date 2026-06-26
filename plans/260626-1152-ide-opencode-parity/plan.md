---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# IDE opencode-parity — chat thread · stop/interrupt · terminal · session history

Extends the committed control-plane IDE (`fcde369`) to full opencode parity. Self-plan + code,
review after. Isolated env, no approval gates.

## A — Chat thread
Runner emits `chat.user`{text} at run start, `chat.assistant`{text} on finish, `chat.error`{text}
on fail/cancel — so the conversation reconstructs from the event buffer (reload + session switch).
Unknown types default `ui_safe` → stream through; add the 3 to `KNOWN_EVENT_TYPES`.
`ChatPanel` folds `store.events` (chat.* + loop.tool steps) into bubbles; composer = existing
`PromptBox` at its foot + a Stop button when running.

## B — Stop / interrupt
`AgentRunner` holds a `threading.Event` cancel flag. In `_run`, after `create_kernel()` (unfrozen),
`kernel.use(cancel_mw)` where `cancel_mw` raises `RunCancelled` when the flag is set. Raise at the
tool chokepoint → Retry passes it (no try/except) → `_stream` re-raises → runner catches
`RunCancelled` → `chat.error` + `loop.failed`(status cancelled). Endpoint `POST /api/runs/cancel`.

## C — Terminal
`files.run_command(argv|command, timeout)` reuses `classify_terminal` + `workspace_dir` (no shell;
shlex-split a command string). Endpoint `POST /api/terminal` (token). `Terminal` panel = input +
output log, collapsible bottom dock.

## D — Session history
`SessionRegistry` replaces the singleton: `sessions: {id: IdeSession}` + per-session `runner`, each
with its own baseline + cancel. Endpoints `GET/POST /api/sessions`; snapshot/stream/commands/diff/
cancel resolve `?session=` (default = `--session`). `IdeSession` gains `title` + `created_at`.
Frontend `sessionStore` (current + list); `SESSION_ID` const → `currentSession()`; switching resets
the control store and re-wires the stream (effect keyed on current session; stream URL gains
`&session=`).

## Layout
Header: logo · run pill · **SessionBar** · conn badge. Body: Explorer | Editor/Changes |
right tabs **Chat | Agent**(graph+timeline+inspector). Bottom dock: **Terminal** (toggle).
Stop button lives in the Chat header when running.

## Verify
Backend: curl sessions/cancel/terminal; submit a prompt then cancel mid-run. tsc + vite build +
vitest + pytest + ruff. In-browser: chat bubbles, stop, terminal, switch session. Then adversarial
review workflow → fix.

## Status — IMPLEMENTED + VERIFIED (2026-06-26)

All four shipped on top of the committed IDE (`fcde369`).
- Backend: `runner.py` (cancel Event + `RunCancelled` middleware on the execute_tool chokepoint +
  chat.user/assistant/error emits), `server.py` (`SessionRegistry`, `?session=` routing, `GET/POST
  /api/sessions`, `POST /api/runs/cancel`, `POST /api/terminal`), `files.py` (`run_command`,
  policy-gated, no shell), `session.py` (title/created_at/meta).
- Frontend: `ChatPanel`, `Terminal`, `SessionBar`; `sessionStore` (current+list); session-scoped
  stream/snapshot/diff/commands; right rail = Chat|Agent tabs; terminal dock; store.resetForSession.
- Live proof (LM Studio was DOWN — runs fail-fast, honestly): chat thread renders YOU → ✓llm.chat →
  ERROR bubble and **reconstructs from the buffer on reload**; terminal ran `ls -la` (ok badge,
  workspace output); Stop button appears while a run is live; `+New` creates + switches session
  (graph/timeline/chat reset, stream re-points). Cancel-propagation pinned by a deterministic test
  (raise survives Retry). tsc + vite build clean; vitest 22/22; pytest 330 passed / 1 skipped; ruff clean.

## Cancel caveat
Stop is COOPERATIVE: the middleware raises at the next `execute_tool` boundary, so an in-flight LLM
call finishes first (≈ one step). A genuine multi-step interrupt needs LM Studio up to demo; with it
down, runs fail before a second tool boundary so cancel returns `cancelled:false` (correct — nothing
was still running). The mechanism is proven by `test_cancel_raise_propagates_through_retry`.
