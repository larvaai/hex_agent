---
slug: drag-from-zero-test-suite
title: Complete test pyramid for drag_from_zero — unit → integration → E2E → browser → real-LLM → manual
mode: hard
tdd: true
created: 2026-06-26
target: drag_from_zero/
branch: feat/docs-diataxis-restructure
verification_tier: full   # 6 phases
standards_read:
  - docs/code-standards.md   # §2 ports-first, §3 naming, §4 TDD discipline (transferable; the kernel/sqlite invariants describe OLD hex_agent, not dragzero)
  - harness/standards/README.md
decisions:
  - e2e_transport: stdlib-over-wire (deterministic) + Playwright browser (opt-in)   # user-chosen
  - scope: rebuild the full pyramid (re-derive coverage matrix, re-home existing, fill gaps)  # user-chosen
  - real_llm: env-gated automated tests (skip unless OPENAI_BASE_URL) + manual runbook  # user-chosen
phases: 6
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Test suite for `drag_from_zero`

## 0. The strategy (read this first — it's the answer to "cho tôi biết chiến lược test")

The system has **one law**: the event log is the only state; tree, UI graph, and eval
scores are pure projections of it. So the test strategy is: **pin the law deterministically,
quarantine non-determinism, and prove every test can fail.**

### Three principles

1. **Determinism boundary is the spine.** Everything in the default suite runs on
   `FakeLLM` (scripted) or `RecordedLLM` (replay through the real parse/repair path) →
   byte-reproducible. Real weights (`OpenAICompatLLM`) are non-deterministic → they live
   **behind markers** (`real_llm`, `browser`), excluded by default, plus a manual runbook.
   This is the README's invariant-vs-eval split, made structural.

2. **Test the projection, not a parallel truth.** Scorers and assertions read the event
   log + `reduce()` tree only — never private orchestrator state. A test that reaches into
   `orch._recs` is testing the wrong thing; the UI can't see it either.

3. **No vacuous green (the TDD analog for a test suite).** A test that passes against
   broken code is theater. Every new test must be shown **red** at least once — by a
   *mutation proof*: temporarily violate the invariant it pins (flip a budget compare,
   drop an event, weaken a sandbox check) and confirm the test fails for the *right
   reason*. code-standards §4.1: "chạy đỏ, không fake." Mutation proofs are recorded per
   phase, not committed.

### The pyramid (wide+fast at the base, few+slow at the top)

```
                    ╱ MANUAL runbook (human · real LLM + browser · judgment) ╲     phase 6
                   ╱  BROWSER e2e (Playwright · real ui/ in Chromium · opt-in) ╲    phase 5
                  ╱   REAL-LLM e2e (LM Studio · env-gated · assert SHAPE)        ╲  phase 6
                 ╱    DETERMINISTIC e2e (topology.json → build_runtime → server)  ╲ phase 4
                ╱     INTEGRATION (orchestrator loop · wiring · eval · adapters)   ╲ phase 3
               ╱      UNIT (events · contracts · reduce · registries · sandbox …)   ╲ phase 2
              ───────────────────────────────────────────────────────────────────────
                                 scaffold + strategy + re-home (phase 1)
```

Determinism boundary sits between phase-4 and phase-5/6: **below = CI-default, deterministic;
above = opt-in, non-deterministic.** Default `pytest` runs phases 1–4 only.

### Coverage matrix (module × layer — the contract for "complete")

| module | unit | integ | e2e |
|---|---|---|---|
| `events` | append/seq/subscribe/of_type/types | — | (via projection) |
| `contracts` | to/from_dict round-trip, enum coerce | — | — |
| `read_model.reduce` | every `EventType` → node mutation | tree shape under delegation | round-trip vs UI graph |
| `registries` | empty-default pass-through, `Budget` charge math | budget halt mid-loop | — |
| `roster` | by_role_or_id / first / add-remove | mid-session add | — |
| `builtins` | by_keyword / always / deny_* | router routes by keyword | (via topology) |
| `topology` | `validate()` cases, JSON round-trip idempotent | — | **load `examples/topology.json`** |
| `wiring.build_runtime` | — | wire tools/hooks/rules, unknown-cap raises | topology→runtime→run |
| `orchestrator`+`agent` | — | ReAct loop, spawn/settle, hook block, max_tool_steps | full run over wire |
| `llm` (Fake/by_role) | dispatch, missing-role raises | — | — |
| `adapters/llm_local` | extract_json/coerce/repair/`solo_fallback` (pure) | `RecordedLLM` drives full orch | recorded→server→WS |
| `adapters/tools_fs` | jail, `..` escape, ToolResult-never-raises | tool loop writes artifact | artifact on disk via API |
| `live_view` | render_tree/render_log glyphs | — | — |
| `server` (`build_graph`/`translate_event`) | pure-fn mapping each event | snapshot coherence | REST+WS over ephemeral port |
| `eval` (scorers/runner) | each scorer good≠bad | run_scenario aggregate + variance | `run_eval` deterministic smoke |
| entrypoints (`demo`/`run_eval`/`run_server`) | — | — | import+run no-crash smoke |
| `ui/` Agent-IDE | — | — | **browser**: boot→Run→tree→chip→chat |
| real local model | — | — | **real_llm**: one run, shape-only |

"Rebuild the pyramid" = realize this matrix end-to-end: re-home the existing 51 tests by
layer/module **without weakening any assertion**, then fill every empty cell. The count
never drops below 51 (Phase-1 gate).

## Current state (baseline)

51 tests, all green (`python -m pytest -q` → 51 passed in ~2.8s). Slice-named files:
`test_invariants` (8), `test_slice2_adapter` (8), `test_slice3_workqueue` (6),
`test_slice3b_eval` (8), `test_slice4_tools` (8), `test_slice5_topology` (8),
`test_slice6a_server` (5). `test_slice6a_server` is **already** a real over-the-wire E2E
(ephemeral port, urllib REST, hand-rolled stdlib WS client) — but only through a hand-built
`Roster`, never via `topology.json → build_runtime`. That chain is the headline E2E hole.

## Target layout

```
drag_from_zero/
  pytest.ini-equiv (in pyproject): markers=[browser, real_llm]; addopts=-m "not browser and not real_llm";
                                   import-mode=importlib   # same basenames across dirs
  tests/
    conftest.py            # rootdir sys.path (exists) + shared fixtures + marker skips
    unit/                  # phase 2 — pure, <0.5s total
    integration/           # phase 3 — FakeLLM/RecordedLLM, in-process
    e2e/                   # phase 4 — over-the-wire, deterministic
    e2e_browser/           # phase 5 — Playwright, marker=browser
    real_llm/              # phase 6 — marker=real_llm, skip unless OPENAI_BASE_URL
  MANUAL_TESTING.md        # phase 6 — human runbook (explicitly requested deliverable)
```

## Phases

| # | phase | layer | gate |
|---|---|---|---|
| 1 | [scaffold + strategy + re-home](phase-1-scaffold-rehome.md) | infra | `pytest -q` == ≥51 passed; default selection excludes browser/real_llm; markers registered |
| 2 | [unit completion](phase-2-unit.md) | unit | every core module has a unit file; `pytest tests/unit -q` green; mutation proofs logged |
| 3 | [integration completion](phase-3-integration.md) | integ | loop/wiring/eval/adapter cells filled; green; mutation proofs |
| 4 | [deterministic E2E](phase-4-e2e-deterministic.md) | e2e | `examples/topology.json` loaded+run; topology→server over wire; projection round-trip; entrypoint smoke |
| 5 | [Playwright browser E2E](phase-5-e2e-browser.md) | browser | `pytest -m browser` green w/ chromium; boots offline; default run still excludes it |
| 6 | [real-LLM E2E + manual runbook](phase-6-real-llm-and-manual.md) | real_llm + manual | real_llm skips cleanly w/o env; runbook every step has a pass criterion |

## Acceptance (whole plan)

- `python -m pytest -q` (default) is green and **deterministic** — no network, no weights,
  no browser. Count ≥ 51 + all new deterministic tests.
- Every core module + adapter + eval primitive has a unit or integration test (matrix full).
- `examples/topology.json` is exercised by an E2E test (config→behaviour proven).
- `pytest -m browser` drives the real `ui/` in headless Chromium when playwright is present;
  `pytest -m real_llm` exercises a local model when `OPENAI_BASE_URL` is set; both **skip
  cleanly** (not fail) when their prerequisite is absent.
- `MANUAL_TESTING.md` exists with prerequisites + numbered steps, each carrying an explicit
  expected-result and pass/fail criterion, incl. failure-mode probes.
- No assertion from the original 51 was weakened or deleted (diff-reviewable).

## Rollback

Pure additive + a test re-home. Revert = `git checkout drag_from_zero/tests
drag_from_zero/pyproject.toml drag_from_zero/MANUAL_TESTING.md` and drop the new dirs.
No `dragzero/` source changes — if a test reveals a real bug, that fix is a **separate**
change (this plan adds tests, it does not patch the SUT). Production source is untouched
except possibly `examples/topology.json` if Phase 4 finds it unrunnable (recorded as a finding).

## Red-team (failure modes + mitigations)

1. **"Rebuild" silently loses coverage.** → Phase-1 gate asserts count never drops below
   51; assertions re-homed verbatim; coverage matrix is the explicit contract; diff reviewed.
2. **Vacuous green tests.** → Mutation-proof discipline (principle 3): each new test shown
   red against a deliberate invariant violation before it counts.
3. **Playwright flakiness poisons CI.** → marker-excluded by default; never a required gate;
   `reduceMotion` prop on; waits anchor on rendered text (chat strings / button label), not
   `sleep`; `importorskip("playwright")`.
4. **DC custom framework (`x-dc`/`support.js`) may not render headless/offline.** → Phase-5
   step 1 is "UI boots + root node visible" *before* any interaction assertion; `ui/` loads
   only local `./support.js` (sole external = Google Fonts, cosmetic). If it can't render,
   the documented fallback is browser-as-manual-only (decision point inside the phase).
5. **Real-LLM test passes vacuously when the model always falls back.** → assert
   `decision.mode ∈ {solo,delegate}` AND surface fallback count as **informational** (not
   gating); a separate `no_fallback` assertion guards the happy path when the model is sane.
6. **Same-name test files across dirs collide.** → `import-mode=importlib` in pyproject
   (no `__init__.py` needed); unique basenames anyway.
7. **`examples/topology.json` unrunnable as shipped.** → [VERIFIED runnable] entry=planner,
   roles planner/coder/reviewer/devops, tools read/write/list all in `default_tool_catalog`,
   rule `by_keyword` in `BUILTIN_RULES`, budget 50, `memory` node ignored by `wiring.py:70`.
   Phase-4 first assertion is `topology.validate(raise_on_error=True)` + `build_runtime`.

## Open unknowns — RESOLVED

- **U1 ✅ RESOLVED (positive).** The custom DC UI renders + runs fully in headless Chromium
  *offline*; all 4 Playwright scenarios pass deterministically (×2). Only artifact: a benign
  SVG-template console warning (`<path d="{{ e.d }}"`), not a JS crash. Browser ships as the
  automated `marker=browser` layer (DEC-14) — the manual-only fallback was NOT taken.
- **U2 ✅ RESOLVED.** `support.js` loads + executes headless with no uncaught error.
- **U3 ✅ confirmed.** Ran against LM Studio `http://localhost:1234/v1`, model
  `qwen3.6-35b-a3b-uncensored-claude-genesis`. Runbook states the assumption.

## COMPLETION (executed 2026-06-27)

**Deviation from approved plan (new facts):** mid-execution a *concurrent session* landed
**Slice 6b** (`verifier.py` + `server.py`/UI upgrade + 16 tests) and kept editing `dragzero/`
source. Pivoted from **re-home → additive-only** (re-home risked clobbering its uncommitted
work) and synced one contract test to a new `DelegationDecision.children` field. Baseline moved
51 → 67 → (now) 257 collected as that session added tests too. No `dragzero/` source touched by
this work (tests + pyproject + conftest + MANUAL_TESTING.md only).

**Delivered + EXECUTED green (not just authored):**

| layer | files | result |
|---|---|---|
| unit | `tests/unit/` ×10 | part of 250 passed (deterministic ×2) |
| integration | `tests/integration/test_server_translation.py` | ↑ |
| e2e (deterministic) | `tests/e2e/` ×5 (topology→runtime, topology→server, **verifier anti-gaming**, projection round-trip, entrypoints) | ↑ |
| browser (opt-in) | `tests/e2e_browser/` ×4 | **4/4 pass** in real headless Chromium |
| real-LLM (opt-in) | `tests/real_llm/` ×3 | **2 passed + 1 xpassed** vs the live 35B |
| manual | `drag_from_zero/MANUAL_TESTING.md` | written, flags verified |

- Default `python -m pytest -q` → **250 passed, 7 deselected**, deterministic (run twice).
- `-m browser` skips cleanly w/o playwright; passes 4/4 with it. `-m real_llm` skips cleanly
  w/o `OPENAI_BASE_URL`; 2P+1xpass against the 35B.
- Vacuity swept (no `assert True`, every file asserts ≥ its test count); the anti-gaming e2e
  and the artifact-content browser test have real teeth (proven via red→green during the run).
- Records: `plan-approval.json` (APPROVED), DEC-12 (determinism boundary), DEC-14 (browser stays
  automated). Side effect: playwright + chromium headless-shell (~92MB) installed to a throwaway
  scratchpad venv + `~/Library/Caches/ms-playwright` (the runbook documents this install).
- **Not committed** (no user request; a concurrent session shares this tree).
