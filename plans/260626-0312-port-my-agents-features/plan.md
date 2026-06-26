---
title: "Port my_agents capabilities → hex_agent (offline agent-capability bundle)"
slug: port-my-agents-features
status: done   # all 7 phases shipped + green; adversarial review = PASS_WITH_FOLLOWUPS (0 must-fix)
mode: hard
tdd: true
created: 2026-06-26 03:12
owner: namson.nguyen102@gmail.com
brainstorm: plans/reports/brainstorm-260626-0312-port-my-agents-features-report.md
gap_analysis: plans/260626-0312-port-my-agents-features/gap-analysis-raw.json
epics: [E02, E06, E07, E09]
risk: low — new files + non-contested edits only; offline; behind existing seams
collision_guard:
  # DO NOT TOUCH — owned by concurrent session S21.33:
  - supervisor/evidence.py
  - supervisor/graph.py
  - supervisor/state.py
  - safety/sandbox.py            # read-only OK, no edits
  - control/__init__.py
  - control/commands.py
  - control/snapshot.py
  - tests/test_acceptance_gate.py
  - tests/test_control_contracts.py
  - tests/test_control_snapshot.py
  - tests/test_evidence.py
  - tests_audit/test_contract_roundtrips.py
  - docs/decisions.md
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Plan — Port my_agents capabilities into hex_agent

> Contract for the AFK build. Every item is offline, behind an existing seam, no new dependency,
> and touches **no** file in `collision_guard`. TDD: write the test, then the impl, run pytest.

## Seam facts (verified by reading source)

- **Tool** = class with `.name: str` + `.execute(request: ToolRequest) -> dict` reading `request.args`
  (`toolbox/filesystem.py:10`). Returns `{"ok": bool, ...}`.
- **Path jail** = `safety.sandbox.resolve_in_workspace(raw) -> Path` raising `SandboxError`
  (`safety/sandbox.py:46`); workspace = `safety.sandbox.workspace_dir()`.
- **Registration** = inside `toolbox/feature.py:install`, wrap in `SafeToolPort(name, tool, policy)`
  and `kernel.registry.register_tool(name, …, kind=…, idempotent=…, risk=…)` (`toolbox/feature.py:27`).
  The `toolbox` feature is already enabled (`config/features.yaml:8`) — no config change.
- **Policy gate** (`safety/policy.py:88`) special-cases only `terminal_run`/git/whole-file-write;
  new `code_*`/`fs_str_replace`/`fs_insert`/`fs_write_lines`/`lint_*` pass through cleanly.
- **JSON gate** public API to preserve: `parse_json_object(text)->dict`, `parse_action(text)->dict`,
  `JsonGateError`, `build_retry_message` (`discipline/json_gate.py`).
- **Lens** YAML schema: `name`, `purpose`, `allowed_tools[]`, `forbidden_tools[]`, `output_schema{}`
  (`roles/lenses.py:43`); loaded by `LensRegistry.load_dir` glob `*.yaml` (`roles/lenses.py:79`).

## Phase 1 — JSON repair-rule pipeline  ·  `discipline/json_gate.py`

**Why:** `_repair` (`json_gate.py:24-50`) only handles trailing commas + bracket balance. Local models
emit python literals, single quotes, unquoted keys, fenced/prose-wrapped output.

**Build:** port deterministic rules from `my_agents/output_gate/repair_rules.py` as pure `str->str`
functions: `strip_markdown_fence`, `extract_largest_json_region`, `remove_trailing_commas`,
`replace_python_literals`, `quote_unquoted_keys`, `escape_control_chars_in_strings`,
`convert_single_quoted_values`, `balance_trailing_delimiters`. Wire a **candidate ladder** in
`_load_object`: raw → light-repair → largest-region → `ast.literal_eval` (dict only). Keep all public
signatures. **Raw is tried first** so valid JSON is never mutated → backward compatible.

**Tests:**
- `tests/test_json_gate_repair.py` — one case per rule + combined messy payloads.
- `tests_audit/test_json_repair_properties.py` (NEW file) — `@property`: `json.loads(dumps(d))==d`
  unchanged through the gate; fenced/trailing-comma-mangled dumps round-trip back to `d`.

**Gate:** existing `tests_audit/test_discipline_and_rag_properties.py` still green.

## Phase 2 — `code_index`  ·  `toolbox/code_index.py` (NEW)

Port `my_agents/mcp_servers/code_index_server.py` AST visitor + JS regex, re-homed to hex:
root via `resolve_in_workspace`, excluded dirs, `max_files` bound. Tools (classes):
`CodeIndex(code_index)`, `CodeFindSymbol(code_find_symbol)`, `CodeFindReferences(code_find_references)`,
`CodeDependencyGraph(code_dependency_graph)`. `kind=read, idempotent=True, risk=low`.

**Tests:** `tests/test_code_index.py` — temp workspace (`AGENT_WORKSPACE_DIR`), sample `.py`,
assert symbols/imports/find_symbol(partial)/find_references/dep-graph; syntax-error file → captured in `errors`.

## Phase 3 — File-editor primitives  ·  `toolbox/filesystem.py`

Append classes: `FsStrReplace(fs_str_replace)` count-guarded (refuse on mismatch),
`FsInsert(fs_insert)` before 1-based line, `FsWriteLines(fs_write_lines)` from JSON list.
Jail via `resolve_in_workspace`. `kind=effect, idempotent=False, risk=medium`.

**Tests:** `tests/test_file_editor.py` — replace happy path; count-mismatch refusal; insert in range +
out-of-range rejection; write_lines create + overwrite-guard + non-list rejection.

## Phase 4 — `lint_test`  ·  `toolbox/lint_test.py` (NEW)

Port `my_agents/mcp_servers/lint_test_server.py`, re-homed to workspace jail. Tools:
`LintCompile(lint_compile)` (`py_compile` over workspace), `RuffCheck(ruff_check)`
(degrade → `dependency_failure`), `PytestRun(pytest_run)`. Fixed argv `sys.executable -m …`,
`cwd=workspace_dir()`, `PYTHONPATH` includes workspace, timeout-bounded. `kind=effect, idempotent=False`.

**Tests:** `tests/test_lint_test.py` — workspace with clean `.py` (compile ok) + broken `.py`
(compile fail w/ failures); `pytest_run` on a tiny passing test → ok; `ruff_check` runs (ruff in dev deps)
or returns `dependency_failure`. Timeouts small.

## Phase 5 — Register new tools  ·  `toolbox/feature.py`

Extend `FEATURE.capabilities` and `install()` to register Phase 2-4 tools behind `SafeToolPort`
with their descriptors. **Test:** `tests/test_toolbox_feature_registration.py` — build kernel from
config, assert every new capability resolves (not `NullToolPort`) and has the right `kind`.

## Phase 6 — Lens catalog  ·  `roles/library/lenses/*.yaml`

Author curated lenses from `my_agents/agents/lenses/*.py`, **tools remapped to hex-canonical names**
(`fs_read`, `fs_write`, `fs_str_replace`, `fs_insert`, `code_index`, `code_find_symbol`,
`code_find_references`, `lint_compile`, `pytest_run`, `ruff_check`, `terminal_run`). Unique names.
Departments: architect, code, research, review, planner, test, business_analyst, final.

**Tests:** `tests/test_lens_catalog.py` — `LensRegistry.load_dir` loads all; names unique; every
referenced tool ∈ known hex tool set (lint).

## Phase 7 — `inspect.py` filters (STRETCH)  ·  `observability/inspect.py`

Add `--status` / `--tool` / `--text` event filters + `summarize_event()` one-line formatter + metrics
columns in summary. Operates on existing JSONL schema. **Test:** `tests/test_inspect_filters.py`.

## Done = all green

```
python -m pytest tests/ -q
python -m pytest tests_audit/test_json_repair_properties.py tests_audit/test_discipline_and_rag_properties.py -q
python run_smoke.py    # CORE_AGENT_SMOKE_OK
python tools/gen_map.py   # refresh MAP.md for new modules
```

## Outcome (2026-06-26)

All 7 phases shipped, **offline, green, ruff-clean, smoke-OK**. 8 new test files (+60 test funcs,
many parametrized) + 2 audit assertions updated to the intended new behavior. 43 new lens YAMLs
(2 → 45 total). `code_index`/`lint_test` + 3 editor primitives registered (toolbox: 4 → 14 tools).

**Adversarial 16-agent review → `PASS_WITH_FOLLOWUPS`, 0 must-fix.** The 6 "protected-scope
violation" findings were false-attribution (those files = concurrent S21.33/E21 work, present at
session start; this port never opened them — verified by `git diff` on owned dirs). One genuine code
finding (NUL-byte `ValueError` leak, pre-existing) was hardened in the new tools by catching
`(SandboxError, ValueError)`; `pytest_run` executes workspace code by design (documented, risk=medium).

**Handoff note (commit hygiene):** stage ONLY the port pathspec (see brainstorm/summary) so the PR
does not carry S21.33/E21 changes that share this working tree. Left uncommitted for review.

## Roadmap (deferred — see brainstorm §Deferred)

ArtifactRef sha256 (after S21.33) · `core/runtime_paths.py` de-dup (1 clean pass w/ sandbox.py) ·
queryable ledger · IntentRouter · per-tool arg-schema registry · live user-directive injection (E21) ·
MCP stdio transport bridge · business_prompt_lab grader · capability-suite/doctor.
