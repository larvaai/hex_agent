---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Agent loop robustness — parse-budget + tool-arg normalization

**Symptom (user):** "Output đang quá ngu. Mỗi parse error mà cũng dừng là không chấp nhận được."
`error {"reason":"too many parse errors","steps":3,"parse_errors":3}` — and even when it didn't
die on parse errors, the agent couldn't produce useful work.

## Root causes (two, both load-bearing)

1. **Cumulative parse-error budget.** `Budget.parse_errors` counted lifetime fumbles, never reset,
   `max_parse_errors=3`. A run making real progress died on 3 *scattered* fumbles. A local 35B
   fumbles JSON occasionally — guaranteed death on any non-trivial task.

2. **Flattened tool calls dropped all args.** The model emits
   `{"action":"tool","tool":"fs_write","path":"x","content":"y"}` — params at the top level, not
   nested under `"args"`. `tool_node` reads `action.get("args")` → `{}` → `fs_write` resolves to
   the workspace **root dir** → `[Errno 21] Is a directory` on *every* write. The agent never wrote
   a file and fabricated success: *"Due to filesystem restrictions I couldn't write the file."*

## Fix (minimal, both loops)

- `discipline/budget.py` — gate on **consecutive** streak (`consecutive_parse_errors`, reset on
  `record_step`/`record_parse_success`); `parse_errors` kept as lifetime telemetry. Default
  `max_parse_errors` 3→8. `Budget.from_env()` (AGENT_MAX_PARSE_ERRORS / AGENT_MAX_STEPS / AGENT_MAX_SAME_TOOL).
- `discipline/json_gate.py` — `normalize_action()` in `parse_action()`: coerces (a) flattened
  top-level params → `args`, (b) tool-name-as-`action` → `{"action":"tool","tool":..}`,
  (c) double-encoded dict-string args → object. Canonical/`final`/`delegate` envelopes untouched.
  Corrective `build_retry_message` now shows the exact JSON skeleton.
- `supervisor/graph.py` — `o_decide` calls `record_parse_success()` on a good decision (it consumes
  no step, so it can't rely on `record_step`'s reset).
- `orchestrator/loop.py` — `recursion_limit` formula raised to cover `max_parse_errors` retries
  before each step; `run()` defaults to `Budget.from_env()`.

## Evidence

| | before | after |
|---|---|---|
| tool.failed | 8 | 0 |
| parse errors | 3 (fatal) | 1 (recovered) |
| wall clock | 280s | 28s |
| `text_stats.py` written | **no** (fabricated) | **yes** — imports & runs, correct output |

- Red→green: 3 new tests fail with the fix stashed (integration shows `failed==completed`), pass with it.
- Live end-to-end against LM Studio twice (before/after), file verified to import and return the spec'd dict.
- Adversarial review (workflow, 12 agents): 1 confirmed medium (accepted limitation), 8 dismissed.
- `pytest -m 'not integration_llm'`: 354 pass / 1 skip. ruff clean.

## Accepted limitation

Double-encoded **non-dict** tool args (`args="[...]"` / `"42"`) stay a string → `tool_node` coerces
to `{}`. Non-regressive; no sound normalization (our args contract is always an object); self-heals
via the tool-error retry. The reviewer's suggested fix is a dispatch no-op, so not applied.

## Unresolved

- Delegated sub-agents run with bare `DEFAULT_SYSTEM` (no tool catalog) and invent `write_file`/`bash`.
  Latent now — the root agent writes directly and no longer delegates one-file tasks — but worth
  injecting `_tool_guide` into delegated prompts if multi-agent runs become common. Out of scope here.
