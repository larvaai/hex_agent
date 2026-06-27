---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 4 — L4 manual runbook + tier README

**Goal:** a human checklist for the irreducible cases automation can't cheaply cover (visual/feel,
real-solve judgment, server-bounce), plus the one-command runner doc for every tier. Docs only.

## Files
`docs/testing/manual-runbook-control-plane.md` · `docs/testing/README.md`

## docs/testing/README.md — how to run each tier
| Tier | Command | Needs model? | In CI? |
|---|---|---|---|
| L0 unit (pytest) | `pytest -q` | no | yes |
| L0 contract (vitest) | `npm --prefix ui/control-plane test` | no | **no** (no Node in CI — DEC-T5) |
| L1 backend-integration | `pytest tests/test_ide_*.py -q` | no | yes |
| L2 browser E2E (det) | `npm --prefix ui/control-plane run test:e2e` | no | **no** — local gate (needs `playwright install chromium`; DEC-T5) |
| L3 browser E2E (live) | `npm --prefix ui/control-plane run test:e2e:live` | **yes (35B)** | no |
| L4 manual | follow runbook | yes | no |
Plus: how to boot real ui.ide (`python -m ui.ide --port 8800 …`, server.py:463), the 35B endpoint/env
(LM Studio, TEXT-mode JSON), and the fake server for offline demo (`fake-control-server-paused`).

## docs/testing/manual-runbook-control-plane.md — checklist (each step: action → expected → ✅/❌)
1. **Boot** real ui.ide + Vite UI pointed at it (`VITE_CP_BASE_URL`).
2. **Cold load** — graph shows root, chat placeholder, file tree populates.
3. **Real solve** — prompt `create calc.py with add(a,b)`; watch timeline stream, chat bubbles fold,
   tool step ✓, file appears in tree (changed flash), diff shows `+`. Judge: did it actually solve it?
4. **Redaction visible** — trigger/seed an event with a secret; confirm `[REDACTED]` on screen, secret
   never in DOM or devtools console/network (the human-eye security check).
5. **Approve interaction** — at a checkpoint, modal bottom-right; click Approve; modal clears, run resumes.
6. **Kill-server reconnect** — `kill` the ui.ide process mid-run; relaunch; badge `RECONNECTING`→reconnect;
   timeline does not duplicate. (The real-world version of the seam test.)
7. **Editor** — open file, edit, dirty pill ●, Cmd/Ctrl+S, diff updates; syntax highlight correct.
8. **Terminal** — run a command; stdout/stderr/exit-code render; a blocked command (`rm`, `sudo`) is refused.
9. **Multi-session** — New session; switch; graph/timeline/chat/explorer reset to clean.
10. **Visual/responsive** — layout intact; `RECONNECTING` badge styling; dark/light if applicable.

## Acceptance
Runbook covers every L3-skippable + visual case; README's table is accurate (commands actually work).
A new dev can run any tier from the README with zero tribal knowledge.
