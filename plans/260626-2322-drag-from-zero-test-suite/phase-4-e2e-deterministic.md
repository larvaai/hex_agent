---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 4 — deterministic E2E (over-the-wire, no weights, no browser)

**Goal:** prove the production chain `config (topology.json) → build_runtime → run → server →
WS/REST` end-to-end, deterministically. This is the headline hole. Default-suite tier.

## Target files

- `e2e/test_topology_to_runtime.py` — **the config→behaviour proof**:
  - `load_file("examples/topology.json")` → `topology.validate(raise_on_error=True)` passes.
  - `build_runtime(topology, FakeLLM(script))` where `script` covers planner/coder/reviewer/devops.
  - `runtime.run("Fix parse_config and add a test")` → planner delegates to coder, coder
    writes a file via the sandbox, tree reaches DONE; assert event log + `reduce` tree shape.
  - **router teeth:** a task containing "deploy" → root routed to `devops` (via `by_keyword`).
  - budget node (50) present and not exceeded.
- `e2e/test_topology_to_server.py` (re-home of `test_slice6a_server` + rewire) — same
  `make_server` over an ephemeral port, but the `Run.builder` is built from
  `examples/topology.json` via `build_runtime` (+ a fresh `FsSandbox`), NOT a hand-built
  Roster. Drive `/api/session` → POST `/reset` → POST `/start` → poll `/api/runs/{id}` to
  done → GET `/artifacts` shows the written file → GET `/artifact?path=` returns content;
  WS stream yields translated frames (run_start, activate, decompose, propose, verdict,
  run_finished) + coherent final snapshot. 404 on unknown run.
- `e2e/test_recorded_full_loop.py` — same server, builder uses `RecordedLLM` (canned replies
  through the real parse path) instead of FakeLLM → proves the real-LLM *plumbing* end-to-end
  without weights; a malformed canned reply surfaces as an observable block/fallback, server
  thread survives (status resolves, no 500).
- `e2e/test_projection_roundtrip.py` — **the law, as an invariant test:**
  - run any deterministic scenario; for the resulting log, assert the UI graph node-set
    (`build_graph(log)["nodes"]` ids) == `reduce(log)` node-set (the projection is total).
  - every emitted event is either translated by `translate_event` to ≥1 UI frame OR is in the
    known-dropped set (`PLAN_PRODUCED`, `DELEGATION_DECIDED`, `TOOL_RESULT`, `AGENT_JOINED/LEFT`,
    `ROOT_TASK_CREATED`) — no event silently lost without being on the list.
  - `reduce(events) == reduce(events)` and `reduce(prefix)` is a consistent prefix of the
    final tree (fold monotonicity for replay-on-connect).
- `e2e/test_entrypoints_smoke.py` — `demo.main()` runs without raising and prints a tree;
  `run_eval` deterministic suite produces a report with the expected scorer rows;
  `run_server.make_server(...)` boots on port 0, `/api/session` answers, then shuts down.
  (Import the entry modules; call their `main`/builders directly — no subprocess needed.)

## Determinism boundary note

Everything here is FakeLLM/RecordedLLM. No `OPENAI_BASE_URL`, no `playwright`. These run in
the default `pytest -q`. If any test needs a sleep, it polls a status endpoint with a bounded
retry loop (pattern already in `_await_done`), never a bare `time.sleep` as a sync primitive.

## TDD framing

- **Red proof:**
  - point `test_topology_to_runtime` at a topology with an unknown tool → expect
    `TopologyError` (confirms validation is load-bearing), then restore the good file.
  - break `build_graph` to drop child edges → round-trip node-set test fails.
- **Green gate:** `pytest tests/e2e -q` green and deterministic (run twice, identical pass).

## Acceptance

- [ ] `examples/topology.json` is loaded, validated, built, and run by a test.
- [ ] the over-wire server test is driven from `build_runtime`, not a hand Roster.
- [ ] projection round-trip invariant test present (node-set equality + event-coverage).
- [ ] entrypoint smoke covers demo / run_eval / run_server boot.
- [ ] `pytest -q` (default) green twice in a row (determinism); full suite green.
- [ ] if `examples/topology.json` proves unrunnable, the fix is recorded as a finding and the
      file patched in a clearly-scoped, separately-reviewable edit.
