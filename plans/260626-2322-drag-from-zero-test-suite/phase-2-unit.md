---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 2 — unit layer (pure, fast, total < 0.5s)

**Goal:** every core module + adapter-pure-fn + eval-pure-fn has a unit file. Fill the matrix's
`unit` column. No I/O, no threads, no network.

## Target files + what each pins

- `unit/test_events.py` — `EventLog.append` stamps monotonic `seq`; `subscribe` fan-out fires
  on append; `of_type`/`types`/`__len__`/`__iter__`; `Event` is frozen (replace-only).
- `unit/test_contracts.py` — `DelegationDecision`/`PlanSpec`/`PlanStep`/`ToolCall`
  `from_dict∘to_dict == identity`; `DelegationMode`/`TaskStatus` str-enum coercion;
  `ToolCall.from_dict` drops non-dict args → `{}`.
- `unit/test_read_model.py` — **fold completeness**: a hand-built event list exercising EACH
  `EventType` → assert the exact `TaskNode` mutation (root create, subtask child-link,
  waiting+blocked_on, tool_result append, started→running+agent, plan→next_step,
  delegate→DELEGATED, completed→DONE, failed→FAILED, hook→BLOCKED, budget→HALTED). Pure
  determinism: `reduce(evts) == reduce(evts)`.
- `unit/test_registries.py` — empty `HookRegistry`/`RuleRegistry`/`ToolRegistry` are
  pass-through; `Budget(None)` disabled (always charges); `Budget(n)` returns False on the
  charge that would exceed, does NOT increment on refusal; `enabled` flag.
- `unit/test_roster.py` — `by_role_or_id` prefers id then role; `first`; `add`/`remove`;
  empty roster → `first() is None`.
- `unit/test_builtins.py` — `by_keyword` matches case-insensitively only on keyword present;
  `always` returns role unconditionally; `deny_delegation`/`deny_all` return reasons.
- `unit/test_topology.py` (from re-home + fill) — `validate()` flags: dup id, unknown
  node/edge type, missing required attr per type, dangling edge endpoints, no-agent,
  >1 entry; `dump_json∘load_json == identity`.
- `unit/test_llm_local_parse.py` (from re-home + fill) — `extract_json` from fenced / prose /
  nested-brace / garbage(None); `_first_balanced_object` string-aware brace matching;
  `coerce_response` valid solo/delegate, delegate-without-target raises, tool-action passthrough,
  missing-decision raises; `solo_fallback` carries `_meta.fallback`.
- `unit/test_tools_fs.py` (from re-home + fill) — `FsSandbox.resolve` confines; `..` → `SandboxError`;
  read/write/list round-trip; each Tool returns `ToolResult(ok=False)` on bad input
  **never raises**; `run_command` needs non-empty argv; `default_tool_catalog` excludes
  `run_command` unless asked.
- `unit/test_llm.py` — `by_role` dispatches on role, callable vs dict values, missing-role raises `KeyError`.
- `unit/test_live_view.py` — `render_tree` glyph per status; child indentation; `render_log`
  one line per event; `render(empty) == "(empty)"`.
- `unit/test_scorers.py` (from re-home) — each scorer scores a good trace 1.0 and a bad
  trace 0.0 (`expects_delegation_to`, `expects_solo`, `reached_role`, `completed`,
  `max_plan_calls`, `no_fallback`, `used_tool`, `tool_succeeded`).

## TDD framing

- **Red proof (mutation) — sample, log each in the phase report:**
  - `read_model`: comment out the `TASK_WAITING` branch → `test_read_model` fails on
    `blocked_on`.
  - `registries`: change `Budget.charge` `>` to `>=` → boundary test fails.
  - `tools_fs`: weaken `resolve` to skip the `..` check → escape test fails.
- **Green gate:** `pytest tests/unit -q` all green.

## Acceptance

- [ ] every module in the matrix's `unit` column has a file; no empty cell.
- [ ] `pytest tests/unit -q` green, < 0.5s, no network/threads.
- [ ] ≥3 mutation proofs recorded (one structural per risky module).
- [ ] full suite still green (`pytest -q`).
