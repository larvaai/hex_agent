---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 3 — L3 live full-stack E2E (real ui.ide + real local 35B), gated @live — DEFERRED

**Status:** DEFERRED (flag at approval). Needs the 35B up. After red-team, only ONE spec is actually
reachable — `agent-run`. The approval and SIGTERM-reconnect specs were CUT (see "Cut" below).

**Goal:** the only tier that drives a real agent run end-to-end through the browser. Non-deterministic
content → assert STRUCTURAL invariants only. `@live`, excluded from CI (`test:e2e` uses `--grep-invert @live`).

## Prereq
Local 35B served (LM Studio per memory; TEXT-mode JSON, no `response_format=json_object`). Document the exact
endpoint/env in `docs/testing/README.md`. Script: `"test:e2e:live": "playwright test --grep @live"`.

## Files
`ui/control-plane/e2e/live/agent-run.spec.ts`

## Tests Before (red) → spec → assertions (content-agnostic)

### agent-run.spec.ts — prompt → agent writes file (FLOW 1-2 live)
- `@live submit prompt → file created + events flow + diff appears` — type
  `create var/workspace/calc.py with add(a,b)` in PromptBox, Send. Assert (poll, generous timeout):
  - a `loop.tool` row `{tool:fs_write, ok:true}` in EventTimeline (bridge.py:60-79),
  - a chat `assistant` bubble + a tool step ✓ in ChatPanel (ChatPanel.tsx:57),
  - `var/workspace/calc.py` exists via GET `/api/files/read` (runner→kernel→fs_write),
  - a diff row for it in DiffPanel; final snapshot `status:finished` (runner.py:175-182).
  None assert the file's exact contents (model-dependent).
- **Fail-fast, don't fake-skip:** if the 35B endpoint is unreachable, the spec fails with a clear message
  (one guarded `test.skip(reason)` is the ONLY allowed skip — never a silent green).

## Cut after red-team (logged findings, not specs)
- **approval.spec — CUT (F4).** The IDE backend has NO live approval gate: `server.py:173-174` —
  ApproveCheckpoint/RejectCheckpoint are no-ops beyond `command.received`. A real *waiting* checkpoint never
  reaches the UI, so the modal can't be triggered end-to-end. Approve interaction → **manual runbook step 5 (L4)**.
  LOGGED: "ui.ide single-agent runner lacks a live approval gate" (per DEC-T4) — candidate for a future backend slice.
- **reconnect.spec (SIGTERM same-port) — CUT (F5).** A restarted ui.ide is a fresh process with an EMPTY
  in-memory buffer (`session.py:43`, no persistence) → Last-Event-ID hits `needs_resync`, emitting a resync
  frame, NOT a resume. "No duplicate rows" would be an artifact of total state loss, not real resume — and the
  same-port relaunch is TIME_WAIT-flaky. True resume is already covered at L0 (contract-seam) against a
  persistent buffer. Server-bounce behavior → **manual runbook step 6 (L4)**, asserting the honest invariant
  (badge RECONNECTING → reconnect → resync frame).

## Regression Gate
`test:e2e` (det) MUST stay green with NO model — verify `--grep-invert @live` actually excludes this spec.
`test:e2e:live` passes locally with the 35B up; record run evidence in artifacts/.
