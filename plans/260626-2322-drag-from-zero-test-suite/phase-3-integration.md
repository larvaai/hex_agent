---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 3 — integration layer (FakeLLM/RecordedLLM, in-process, no wire)

**Goal:** fill the `integ` column — modules composed together through the orchestrator, still
deterministic and in-process.

## Target files + what each pins

- `integration/test_orchestrator_loop.py` (re-home + fill) — the engine:
  - solo run: root → PLAN_PRODUCED → DELEGATION_DECIDED(solo) → TASK_COMPLETED; tree DONE.
  - delegate: SUBTASK_SPAWNED grows a child; parent settles only after child
    (`_settle` decrement → parent TASK_COMPLETED result="delegated").
  - ReAct: tool action → TOOL_CALLED/TOOL_RESULT → observation fed back → terminal.
  - `max_tool_steps` guard → TASK_FAILED("max_tool_steps exceeded").
  - budget halt: `Budget(1)` → second charge halts → BUDGET_EXCEEDED, queues cleared, tree HALTED.
  - hook block: `deny_delegation` on `pre_delegate` → HOOK_BLOCKED → solo-fallback complete;
    `deny_all` on `pre_plan` → HOOK_BLOCKED → TASK_FAILED.
  - no-agent route → TASK_FAILED("no agent available").
  - **toolless parity:** a run with no tools registered emits the byte-identical event-type
    sequence to the Slice-1 baseline (guards "tools don't perturb toolless runs").
- `integration/test_workqueue_inject.py` (re-home) — delegate to an unfilled role → child
  parks (TASK_WAITING, `waiting_count==1`); `join_agent` → AGENT_JOINED → `_wake_waiting`
  → child runs; event order: TASK_WAITING < AGENT_JOINED < child TASK_STARTED.
- `integration/test_wiring.py` (re-home + fill) — `build_runtime`:
  - agent nodes → roster (entry first); tool/hook/router nodes wire registries from catalogs;
    budget node → gate.
  - unknown tool/hook/rule name → `TopologyError`.
  - `memory` node ignored (round-trips, not wired).
  - router `by_keyword` config routes a matching task; no match → entry agent.
  - LLM injected (same topology runs FakeLLM and RecordedLLM).
- `integration/test_eval_runner.py` (re-home + fill) — `run_trial` builds roster+tools+sandbox;
  `run_scenario(trials=n)` aggregates pass_rate/mean/min/max/variance; a **crashing** llm_factory
  scores every scorer 0.0 (not an exception); `render_report` shape; good-behaviour scenario
  beats bad-behaviour scenario on the discriminating scorer.
- `integration/test_adapter_substitution.py` (re-home + fill) — `RecordedLLM` drives the FULL
  orchestrator loop (plan→delegate→tool→solo) through the same coerce/repair path;
  substitutability: swapping FakeLLM↔RecordedLLM on the same script yields the same tree shape;
  a malformed recorded reply → observable `solo_fallback` (`_meta.fallback`), no crash.
- `integration/test_server_translation.py` — pure server fns (no socket):
  `build_graph(log)` fills goal/mu/done_when/depends_on/children/runtime; `mu` == subtree size;
  `done_when` lists write_file artifacts; `translate_event` maps each EventType → UI vocab
  (activate/propose/decompose/verdict/block/run_end) or `[]`; `_final_status` mapping.

## TDD framing

- **Red proof (mutation):**
  - orchestrator: skip the `_settle` parent-decrement → delegate test hangs/leaves parent
    non-DONE → test fails.
  - wiring: make unknown-tool not raise → `pytest.raises(TopologyError)` fails.
  - translation: drop the `SUBTASK_SPAWNED→decompose` case → `decompose` assertion fails.
- **Green gate:** `pytest tests/integration -q` green.

## Acceptance

- [ ] every `integ` matrix cell filled.
- [ ] budget halt, hook block, max_tool_steps, inject-resume each have a dedicated test.
- [ ] toolless-parity test present (Slice-1 event sequence preserved).
- [ ] ≥3 mutation proofs recorded; full suite green.
