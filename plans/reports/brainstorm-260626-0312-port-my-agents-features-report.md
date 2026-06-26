---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Brainstorm — Port "good features" from `my_agents` → `hex_agent`

- **Date:** 2026-06-26 03:12 (+07)
- **Reference repo:** `larvaai/my_agents` (cloned `/tmp/my_agents_ref`, `58ebb71 v0.3.1`)
- **Method:** 12-agent gap-analysis workflow (parallel deep-readers per feature area + hex-state map + synthesis). Raw output: [`gap-analysis-raw.json`](../260626-0312-port-my-agents-features/gap-analysis-raw.json).
- **Plan:** [`plans/260626-0312-port-my-agents-features/plan.md`](../260626-0312-port-my-agents-features/plan.md)

## TL;DR for the reviewer

`hex_agent` is **architecturally ahead** of `my_agents` on the hard parts (frozen microkernel + single tool chokepoint, middleware pipeline, ToolPort/DelegationPort, SafeToolPort gating, RoleSpec/Skill/Lens model, SQLite-checkpointed Agent-O supervisor, E21 control-plane contracts). So we do **not** port the kernel/orchestration/roles framework — that would regress.

What `my_agents` has that `hex_agent` genuinely **lacks** is *breadth of agent capability*: robust model-output salvage, code-aware tools (index / surgical edit / validate), and richer review lenses. That is the port surface.

**Building now (offline, behind existing seams, zero new deps):** a 5-capability "agent can actually read, edit, validate code + survive messy model JSON" bundle, plus 2 dev-experience polishes.

**Hard constraint that shaped scope:** a concurrent session is mid-flight on **S21.33** (`supervisor/evidence.py`, `supervisor/graph.py`, `safety/sandbox.py`, several `tests/`). Per the shared-tree rule, this build **only adds new files + edits non-contested files**, and **defers** every port that lands in those files.

## Gap analysis (verified by reading source, not guessed)

| # | Gap in hex | Evidence | Decision |
|---|------------|----------|----------|
| 1 | `discipline/json_gate.py` `_repair` only strips trailing commas + balances brackets | `json_gate.py:24-50` | **Port now** — full repair-rule pipeline |
| 2 | No code symbol/reference index | grep: no `ast.parse` in toolbox | **Port now** — `code_index` |
| 3 | Only whole-file `fs_write`; no surgical edit | `toolbox/filesystem.py` 3 tools | **Port now** — `str_replace`/`insert`/`write_lines` |
| 4 | No structured compile/lint/test validation tool | absent | **Port now** — `lint_test` |
| 5 | Only 2 review lenses | `roles/library/lenses/` | **Port now** — lens catalog |
| 6 | `inspect.py` only filters `--kind` | `observability/inspect.py` | **Port now** — richer filters |
| 7 | Evidence has `kind` but no content-addressing (sha256) | `supervisor/evidence.py` | **Defer** — collides with S21.33 |
| 8 | `PROJECT_DIR` duplicated in 4 files; no `var/` owner | grep 4 hits | **Defer** — 1 of 4 (`sandbox.py`) is contested; do the de-dup in one clean pass later |
| 9 | No queryable ledger, MCP transport bridge, intent router, live HITL injection | various | **Roadmap** (see plan §Roadmap) |

## What we are building (Tier-1 AFK bundle)

All items: **offline-testable, behind an existing seam, no new dependency, no contested file touched.**

1. **JSON repair-rule pipeline** — `discipline/json_gate.py`. Compose the deterministic rules from `my_agents/output_gate/repair_rules.py` (python-literal `True→true`, single-quote→double, unquoted-key quoting, largest-JSON-region extraction, control-char escaping) into a candidate ladder with an `ast.literal_eval` fallback. **Strict superset** — valid JSON still parses via the raw-first candidate, so existing `tests_audit` stays green. *Highest value-to-risk in the set: local models emit messy JSON; this salvages it deterministically.*
2. **`code_index`** — new `toolbox/code_index.py`. Read-only stdlib `ast` (Python) + regex (JS/TS) symbol / reference / dependency-graph index, workspace-jailed, bounded by `max_files`. Pairs with `rag/` for code-aware retrieval.
3. **File-editor primitives** — `toolbox/filesystem.py`. `fs_str_replace` (count-guarded — refuses on match-count mismatch), `fs_insert` (before-line), `fs_write_lines` (JSON list → avoids fragile multiline payloads). These are *patch* tools, so they're exactly what `repair_mode` wants instead of a clobbering rewrite.
4. **`lint_test`** — new `toolbox/lint_test.py`. `lint_compile` (`py_compile`), `ruff_check` (degrades to `dependency_failure` if ruff absent), `pytest_run`. Feeds `discipline/finish_gate` evidence; fixed allowlisted argv (no arbitrary shell).
5. **Lens catalog** — `roles/library/lenses/*.yaml`. Curated, high-value lenses from `my_agents/agents/lenses/` **remapped to hex-canonical tool names** (drops references to un-ported `issue.*`/`ledger.*`/`document.*` infra). Lifts hex's thinnest content area from 2 → ~15+ reusable viewpoints.
6. **`inspect.py` filters** *(stretch)* — `--status` / `--tool` / `--text` + `summarize_event()` human formatter + metrics columns, over the existing event-log JSONL schema.

Registration: tools 2-4 register inside the **already-enabled** `toolbox` feature (`toolbox/feature.py`) — no config change, no new feature wiring.

## Explicitly NOT porting (and why)

- **Kernel / registry / schemas / roles-loader / orchestrators** — `hex` is strictly better; porting regresses (e.g. `my_agents` LangGraph `compile()` has *no checkpointer*; hex has SQLite checkpoint/resume).
- **`core/capabilities.py` singleton** — module-level `get_default_kernel()` actively conflicts with hex's frozen-kernel + per-session `ToolCallContext`/`allowed_capabilities`. Anti-pattern here.
- **Hard tool policy / git-mutation opt-in / path-jail** — already in `safety/policy.py` + `safety/sandbox.py` (verified `classify_terminal` + `GIT_MUTATIONS` + `AGENT_ALLOW_GIT_MUTATIONS`).
- **rag / pdf / document / obsidian / playwright / docker / search / fetch servers** — overlap existing tools or need live network/daemon/browser; not offline.
- **v0.5 department agents, FinalSynthesis/Ledger agents, knowledge stubs** — mostly hardcoded stub dicts; their only durable asset (the lens DATA) is harvested in item 5.

## Deferred to roadmap (valuable, but not this unattended pass)

- **ArtifactRef sha256 content-addressing** → `supervisor/evidence.py` — *collides with active S21.33*. Do after that lands.
- **`core/runtime_paths.py`** var-layout owner — needs to edit `safety/sandbox.py` (contested) to actually de-dup; do all 4 sites in one clean commit later.
- **Queryable ledger** (`observability/ledger.py` + tools), **IntentRouter**, **per-tool arg-schema registry**, **live user-directive injection** (E21 executable gap), **MCP stdio transport bridge** (high value but needs live subprocess — only the result-normalizer is offline-unit-testable), **business_prompt_lab offline grader**, **capability-suite/doctor**. Rationale per item in [`gap-analysis-raw.json`](../260626-0312-port-my-agents-features/gap-analysis-raw.json) `tier2_roadmap`.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Repair pipeline mis-parses previously-valid JSON | Raw-first candidate ladder: unmodified text is tried before any repair rule. Property test asserts valid JSON is unchanged. |
| Collision with concurrent S21.33 | New files only; zero edits to `supervisor/*`, `safety/sandbox.py`, contested `tests/*` and `tests_audit/test_contract_roundtrips.py`. |
| `lint_test` subprocess safety | Fixed allowlisted argv (`sys.executable -m …`), workspace cwd, timeout-bounded; not arbitrary shell. |
| Regression in existing suites | Run `pytest tests/` + targeted `tests_audit` after each module; 100% green gate before done. |

## Open questions (for reviewer)

1. Confirm the deferred **ArtifactRef** + **runtime_paths** should be picked up *after* S21.33 merges (recommended), vs. a coordinated worktree now.
2. Want the **MCP stdio bridge** (the one high-value *online* item) as a follow-up design spike?
