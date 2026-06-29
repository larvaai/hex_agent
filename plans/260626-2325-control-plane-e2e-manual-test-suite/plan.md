---
title: "E21 control-plane + IDE — full test suite (real-only E2E + manual runbook)"
slug: control-plane-e2e-manual-test-suite
status: approved         # human-approved 2026-06-27 by uspro ("approve all" — L3+L5 pulled into scope)
mode: hard
tdd: true
created: 2026-06-26 23:25
owner: uspro
scope_target: E21 control-plane + ui.ide IDE (control/, tools/fake_control_server.py, ui/control-plane, ui/ide)
e2e_posture: real-only   # E2E drives the REAL `python -m ui.ide`; NO fake server in the E2E tier
phases: 5                # ALL 5 in scope (approve-all). L3 = agent-run spec only (approval/reconnect CUT per red-team F4/F5 — architectural, → manual L4)
risk: low — test/doc/tooling only; touches NO production code. Rollback = delete new test files + e2e/ + docs/testing/ + revert package.json.
standards:
  - docs/code-standards.md   # §4 TDD discipline, §7 fragile-files→test map
  - docs/system-architecture.md   # §2 seam table (Control plane = control/, E21)
decisions:
  - DEC-T1 E2E tooling = Playwright (@playwright/test), real browser, real `python -m ui.ide` backend; fake_control_server stays ONLY in the existing unit/contract tier
  - DEC-T2 E2E splits two tiers — det (no model, deterministic) + live (real local 35B, gated @live); assertions target STRUCTURAL/SECURITY invariants, never model content
  - DEC-T3 graph/timeline/chat/redaction/reconnect/resync against the REAL backend are asserted IN-PROCESS (pytest L1) — they have NO HTTP seed route, so the browser cannot drive them without the model (verified: snapshot.py folds loop.* only; AgentGraph.tsx:65 root is the only model-free node)
  - DEC-T4 manual runbook lives in docs/testing/; tests are the deliverable — a real defect a test exposes is LOGGED, not silently patched here
  - DEC-T5 CI today is Python-only (.github/workflows/ci.yml = ruff + pytest). L1 is genuinely CI-green. L2(det browser)+L5(vitest) are LOCAL pre-merge gates UNLESS a Node CI job is added (separate decision, out of this round). L3/L4 never in CI.
depends_on: []
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — E21 control-plane + IDE: full test suite

> Revised after red-team (REVISE verdict). Cuts: L2 graph-assertions (mirage — F1), false CI claims (F2),
> the unreachable @live approval spec (F4), and the false-invariant SIGTERM reconnect (F5). Core shrinks to
> the genuinely-valuable, genuinely-deterministic work.

## Test strategy (the ask: "cho tôi biết chiến lược test")

A 5-layer pyramid. The session already built Layer 0; this plan builds **L1 + L4 (core)**, a **trimmed L2**,
and defers **L3 + L5**. **Real-only** = every E2E test drives the *real* `python -m ui.ide`; the fake server
is demarcated to the existing unit/contract tier and never appears in E2E.

```
                 ┌─ L4 MANUAL runbook ─ human, real 35B, irreducible (real-solve/visual/kill-server/approve)  [Phase 4 · CORE]
                 ├─ L3 BROWSER E2E · live ─ real ui.ide + real 35B, @live, ONLY agent-run is runnable          [Phase 3 · DEFERRED]
   real-only ────┤
                 ├─ L2 BROWSER E2E · det ─ real ui.ide, NO model, ONLY the HTTP-backed surface                 [Phase 2 · CORE, trimmed]
                 └─ L1 BACKEND integration ─ real ui.ide in-process, NO model, pytest, CI-green                [Phase 1 · CORE]
   ─────────────  L0 UNIT/CONTRACT ─ EXISTS: 87 pytest + vitest (fake server, pure fns) — keep                 [+ optional Phase 5 fills IDE-half component gaps]
```

### The central constraint (why the layering is shaped this way)
`ui/ide/runner.py:151` — `AgentRunner.start()` **always** calls the real orchestrator → real LLM, **no stub
seam**. And graph/timeline/chat exist **only** as a fold of `loop.*` events (`control/snapshot.py:3-9`), which
enter a session through exactly two doors: a real model run, or in-process `session.emit()` (**no HTTP route**).
A browser can only POST `/api/commands` (→ `command.received`). Therefore:

- **The browser cannot deterministically render agent state without the model.** The only model-free node is
  the hardcoded root "O" (`AgentGraph.tsx:65`) — asserting it proves nothing about the backend. So
  graph/timeline/chat/redaction/reconnect assertions live IN-PROCESS at **L1** (where `emit` is callable), not L2.
- **L2 (det browser) asserts ONLY the real HTTP surface:** file tree/open/save/diff round-trip, CORS preflight,
  session create→store-reset. These are 100% deterministic against the real backend with no model.
- **L3 (@live) is the only tier that drives real agent state**, and only its `agent-run` spec is reachable —
  the backend has no live approval gate (`server.py:173-174`), so Approve is manual (L4); a server-bounce
  reconnect across an in-memory buffer can't assert resume semantics (L4 manual).
- **Invariants over content.** Every E2E assertion targets structural/security facts (a file appears, a
  `loop.tool` event flows, the wire carries `ui_payload` not raw secret), never the model's exact text.

### Determinism handling for the live tier (L3)
Fixed prompt `create var/workspace/calc.py with add(a,b)` reliably drives one `fs_write` (proven this session).
Assertions: a workspace file exists + a `loop.tool{tool:fs_write,ok:true}` event + chat `assistant` bubble +
a diff row + final `status:finished` — none depend on the model's exact text.

## Scope boundary
- **IN (all 5, approve-all):** L1 backend-integration (pytest), trimmed L2 det browser E2E (Playwright harness
  + HTTP-surface specs), L4 manual runbook + tier README, L3 live `agent-run` spec (needs 35B), L5 IDE-half
  component tests.
- **OUT:** changing any production code in `ui/ide`, `control/`, `ui/control-plane/src` (test-only). Fixing
  defects the tests expose (logged → separate fix). The fake server's own tests. decompose_agent (other subsystem).
  Adding a Node CI job (separate decision — DEC-T5).

## Touchpoints (new files; no existing source modified)
| Layer | New files | Exercises (code under test, file:line) |
|---|---|---|
| L1 | `tests/test_ide_stream.py`, `tests/test_ide_files_edges.py`, `tests/test_ide_http_cors_auth.py`, `tests/test_ide_run_lifecycle.py` | server.py:387-436 (SSE redaction/visibility/resume/resync), files.py:94-114/180-181/60 (jail/binary/size), server.py:55-56/188-193 (CORS), server.py:111-155 (idempotency), runner.py:138-159 (cancel), runner.py:99-101 (baseline) |
| L2 | `ui/control-plane/playwright.config.ts`, `e2e/global-setup.ts`, `e2e/files.spec.ts`, `e2e/sessions.spec.ts`, `e2e/cors.spec.ts` | FileExplorer/CodeEditor/DiffPanel/SessionBar HTTP-backed flows; config.ts:3 BASE_URL; server.py:188-193 CORS |
| L3 (deferred) | `ui/control-plane/e2e/live/agent-run.spec.ts` + `test:e2e:live` script | runner.py:151 real run; bridge.py:60-79 loop.tool |
| L4 | `docs/testing/manual-runbook-control-plane.md`, `docs/testing/README.md` | human checklist (incl. Approve, kill-server reconnect) + how-to-run each tier |
| L5 (optional) | `ui/control-plane/src/components/__tests__/{FileExplorer,DiffPanel,ChatPanel,SessionBar,Terminal,CodeEditor}.test.tsx` | the 6 zero-coverage components |

## Phases
1. **L1 backend real-integration (no model)** — `phase-1-backend-integration.md` — CORE; biggest gap; CI-green.
2. **L2 Playwright harness + trimmed det browser E2E** — `phase-2-playwright-det.md` — CORE; new tooling (DEC-T1); HTTP-surface only (F1).
3. **L3 live agent-run E2E (gated @live)** — `phase-3-live-e2e.md` — IN SCOPE; needs local 35B; 1 viable spec (agent-run).
4. **L4 manual runbook + tier README** — `phase-4-manual-runbook.md` — CORE.
5. **L5 IDE-half component tests** — `phase-5-component-gapfill.md` — IN SCOPE (approve-all).

## Acceptance (whole plan)
- `python -m pytest tests/ tests_audit/ -q` green (L1 added, no weakening) — currently 1072 passed. **This is the CI gate.**
- `npm --prefix ui/control-plane run test:e2e` (det, no model) green locally and deterministic — local pre-merge gate, NOT in current CI (DEC-T5).
- `npm --prefix ui/control-plane test` green (L5 if included) — local gate.
- L3 `test:e2e:live` documented + passes with the 35B up (not in CI); evidence in artifacts/.
- `docs/testing/` runbook + README exist; every tier has a one-command runner; the README's "In CI?" column matches reality (only L0+L1).
- Each phase is TDD where it is code (red→green), per code-standards §4.

## Rollback
Additive only. `rm` the new test files, `ui/control-plane/e2e/`, `playwright.config.ts`, `docs/testing/`;
revert `ui/control-plane/package.json` (scripts + `@playwright/test` dep). No production code touched.

## Open questions (resolve at approval)
- Defer L3 + L5 as marked, or pull either into this round?
- Add a Node CI job (so L2/L5 actually gate merges), or keep them as local-only pre-merge checks? (DEC-T5)
- Playwright acceptable as a new devDep + chromium binary, or prefer a lighter real-browser driver?
