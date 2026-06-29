---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# IDE opencode-parity — implementation report

**Date:** 2026-06-26 · **Branch:** feat/docs-diataxis-restructure · **Base:** `fcde369` (committed IDE)

Extended the control-plane IDE to opencode parity: **chat thread · stop/interrupt · terminal · session
history**. Self-planned + coded + verified end-to-end. Not committed (awaiting review).

## What shipped

### A — Chat thread
`AgentRunner` emits `chat.user` (run start), `chat.assistant` (finish), `chat.error` (fail/cancel) into
the session buffer, so the conversation reconstructs from the event ring on reload and session switch.
`ChatPanel` folds `store.events` (`chat.*` + `loop.tool` steps) into bubbles, ordered by seq. Composer is
the existing `PromptBox` (one door for `SubmitPrompt`). Unknown event types default `ui_safe` → stream
through; the three are added to the client's `KNOWN_EVENT_TYPES`.

### B — Stop / interrupt
`AgentRunner` holds a `threading.Event`. In `_run`, after `create_kernel()` (returns unfrozen), it
registers a middleware on the single `execute_tool` chokepoint that raises `RunCancelled` once the flag
is set. The raise survives `Retry` (which only re-invokes on a falsy result, never on a raise) and
`orchestrator._stream` (which re-raises), reaching `_run` → `chat.error` + `loop.failed`, status
`cancelled`. Endpoint `POST /api/runs/cancel`. Cooperative: aborts at the next tool/LLM boundary.

### C — Terminal
`files.run_command` reuses `safety.policy.classify_terminal` + `safety.sandbox.workspace_dir`: no shell
(shlex-split a command string), output capped, 30s timeout, jailed to `var/workspace`. Endpoint
`POST /api/terminal` (token-gated). `Terminal` panel = request/response command runner in a collapsible
bottom dock.

### D — Session history
`SessionRegistry` replaces the singleton: many `IdeSession` + per-session `AgentRunner`, each with its own
event buffer + diff baseline. `GET/POST /api/sessions`; snapshot/stream/commands/diff/cancel resolve a
`?session=` param (default = `--session`). Frontend `sessionStore` (current + list); `SESSION_ID` const →
`currentSession()`; switching resets the control store and re-points the SSE stream (App effect keyed on
current session; stream URL gains `&session=`). Right rail is now tabbed **Chat | Agent**.

## Verification

- **tsc** clean · **vite build** clean · **vitest 22/22** · **pytest 330 passed / 1 skipped** · **ruff** clean.
- New backend tests (`tests/test_ide_backend.py`): chat-event emit on fail/cancel, idle-cancel → false,
  cancel-raise-survives-Retry (the load-bearing Stop proof), sessions list/create/404, terminal ok/blocked/
  token-gate, cancel idle/unknown.
- **In-browser (LM Studio DOWN → honest fail-fast):** chat thread renders `YOU → ✓ llm.chat → ERROR` and
  **reconstructs from the buffer after a full page reload**; terminal ran `ls -la` (ok badge + workspace
  listing); Stop button appears during a live run; `+New` creates + switches a session (graph/timeline/chat
  reset, stream re-points); no console errors.

## Caveats / unresolved

- **Stop is cooperative**, not a hard kill — an in-flight LLM call completes before the abort (~one step).
  A genuine multi-step interrupt needs LM Studio up to demo; the propagation mechanism is pinned by a
  deterministic test instead.
- **Sessions share one `var/workspace`** on disk — each session's diff is vs its own baseline, but file
  edits are global. Inherent to a single-sandbox agent; acceptable for the dev IDE.
- Agent edit quality is bounded by the local model, not the IDE.

## Adversarial review — 16 findings, 13 confirmed, all fixed

Multi-lens (correctness / security / concurrency / frontend) → adversarial verify → consolidate. 21
agents, ~782k tokens. The verify pass killed 3 (unbounded-dedup — already FIFO-capped; a "lock
hierarchy" mislabel; a ChatPanel stale-closure that doesn't exist). The 13 confirmed, all fixed:

**HIGH**
1. **Stop never propagated** (`core/kernel.py:141`) — the kernel's `execute_tool` boundary guards with
   `except Exception` and converts a raise into a tool-error envelope, so `RunCancelled` was swallowed
   and the run limped on. My old test only checked `Retry` in isolation and missed this. **Fix:**
   `RunCancelled(BaseException)` — slips past every `except Exception` on the path (kernel core,
   kernel boundary, Retry, `_stream`). New test `test_cancel_raises_through_kernel_boundary` exercises
   the **real** `create_kernel()` + `execute_tool` stack.
2. **Unbounded session creation DoS** (`server.py`) — each `POST /api/sessions` snapshots the workspace
   (~MBs). **Fix:** `MAX_SESSIONS = 64`, `create()` raises `FileOpError(429)`; test added.
3. **Terminal env exfil** (`files.py`) — `subprocess.run` inherited the server's full env, so an allowed
   `env`/`printenv`/`node -e` dumped the IDE token + ssh agent + keys. **Fix:** `env=_safe_env()`
   whitelist (PATH/HOME/LANG/…); test added.
4–5,9–10. **Cross-lock data races** on `run_status` / `baseline` / `last_prompt` (written under the
   runner's lock, read under another or none). **Fix:** the session now owns them under its one
   condition — `try_begin_run` (atomic claim), `snapshot_status`, `diff_baseline`, locked `meta()`;
   `cancel()` and the diff endpoint read through those.
6. **Stale tabs across session switch** (`App.tsx`/`fileStore`) — only the control store reset on switch.
   **Fix:** `fileStore.resetForSession()` + called in the switch effect (+ `refreshTree`). **Verified
   live:** opening notes.md then switching session clears the tab.

**MEDIUM**
7. CORS rejected IPv6 `[::1]` → added to the origin regex.
8. Session id was 32-bit (`hex[:8]`, ~65k-collidable) → full `uuid4().hex` (128-bit); verified live (34-char id).
11–13. fileStore `prevTree` / tree / diffs stale on switch → covered by `resetForSession()`.

**Re-verified after fixes:** tsc + vite build clean · vitest 22/22 · pytest 345 passed / 1 skipped
(deterministic) · ruff clean · IDE backend 24/24.

## Unresolved

- A rare `pytest-randomly` ordering exposes a **test-isolation flake in `tests/test_acceptance_gate.py`**
  (a concurrent session's +46 lines — passes in isolation and under 12 fixed seeds; deterministic order
  is 0 failures). Not in this change's surface; flagged for that session's owner.
