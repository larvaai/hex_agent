---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Whole-repo hard critique — hex_agent (core_agent)

- Date: 2026-06-26 12:49 +07
- Branch: `feat/docs-diataxis-restructure`
- Method: 12-dimension multi-agent review (7 subsystem + 5 cross-cutting), every critical/high finding adversarially re-verified against the real source (39 agents, ~2.2M tok). Scope = app code + tests + ui + docs. `harness/` excluded (vendored).
- Surface: ~10.5k LOC app Python (18 modules) + ~4.3k UI TS/TSX + ~16k test LOC.
- Result: **84 findings.** 27 critical/high; **26 verified HOLD**, 1 refuted (arch-3, deflated to low). Confidence high on essentially all.

---

## Verdict (one paragraph)

The architecture is genuinely good on paper and the *unit* discipline is real — but the system has one pervasive disease: **safety/discipline machinery that is declared, unit-tested, and never wired into the live run.** Five separate guards (role allowlist, finish-gate, redact-for-ui flag, separation-of-duties, authz predicates) exist as code with passing tests but **zero runtime call-sites.** Combined with three string-pattern "sandboxes" that cannot actually contain a subprocess, the result is a security model that is green in CI and open in production. The README over-claims ("one compiled LangGraph substrate", "SQLite is checkpoint truth") against a reality with two divergent execution stacks. Fix the kill-chain first; then either wire the dead guards or delete them — keeping unwired enforcement classes is worse than not having them.

---

## The four themes (read these, the findings are just evidence)

1. **Declared-but-unwired guards.** `roles.Agent.guard_tool_call` (domain-1/arch-2), `finish_gate` inputs (safety-2), `redact_for_ui` flag (control-2), `guard_finish` (domain-3), `authz` predicates (control-5) — each is real code, each is invoked **only by its own tests.** The suite is green because every guard passes in isolation; none runs in `graph/nodes.py` or `supervisor/graph.py`. The test-quality audit independently put the suite at **~35% theater**, with the unwired allowlist as the single biggest miss.

2. **String-pattern security where you need an OS sandbox.** The workspace jail (sec-2), the no-shell guard (safety-1), the git-mutation block (safety-4) all try to constrain a Turing-complete subprocess with regex/argv matching. That is structurally impossible. One fix covers all three: real OS isolation (landlock/seccomp/bwrap/nsjail) + scrubbed env + resolve-then-jail every path.

3. **README over-claims vs built reality.** "One compiled LangGraph substrate" is false — `supervisor/` is a second hand-rolled loop with its own checkpoint DB and event path (arch-1). MAP.md claims to self-maintain but never recurses into subpackages, so the live `ui/ide/` backend is invisible (docs-1).

4. **Invariant violations the design forbids.** "No duplication / single chokepoint" is breached concretely: envelope control-flags split across `data`/`metadata` (core-1), a duplicated state codec buggier than the shared one it imports (graph-1), budget logic in three places (arch-4), a triple tool-safety gate (arch-5).

---

## CRITICAL — security kill-chain (all verified HOLD, fix before running with real creds)

These four compose: an agent runs arbitrary code (safety-1) **outside** the jail (sec-2) with the **full server env** (sec-1), and the captured secret **streams to the UI + disk unredacted** (sec-3/control-1).

### sec-2 — workspace command jail only blocks ABSOLUTE paths; relative `..` escapes
`safety/policy.py:17-38,67-70` · `_ABS_PATH_RE` matches only `C:\…` or `/…`-rooted paths. A relative arg has no match; subprocess `cwd=var/workspace`, so `['ls','-la','..']` lists the parent (verifier planted `secret_outside.txt` one level up and read it). The core E06 jail claim is bypassable by any subprocess taking a relative path.
**Fix:** stop matching argv strings. Resolve every `argv[1:]` path against `workspace_dir()`, reject if `.resolve()` is not `relative_to` the workspace (same logic the file jail `_resolve` already uses). Better: OS sandbox.

### safety-1 — "no-shell" terminal bypassed via interpreters
`safety/policy.py:53-71` · `toolbox/terminal.py:21-39` · `classify_terminal` blocks shell exes/tokens/destructive exes but never restricts the interpreter. Live: `['node','-e','require("child_process").execSync("id")']` → ALLOWED; `['python','-c','os.execvp("bash",...)']` → ALLOWED. Pattern-matching cannot constrain a Turing-complete interpreter.
**Fix:** forbid inline-code flags (`-c/-e/-p/--eval`) under an allowlist of interpreter subcommands, or (correct) run inside an OS sandbox.

### sec-1 — terminal_run inherits the full server environment → secret exfiltration
`toolbox/terminal.py:32-39` · `subprocess.run(... )` with **no `env=`** → child inherits `os.environ`. Live: `printenv MY_API_KEY` → `sk-LEAKED-SECRET-1234`. The sibling `ui/ide/files.py:374-406` already scrubs via `_safe_env()` **and documents this exact attack** — the team knows; `terminal.py` and `lint_test.py` just don't use it.
**Fix:** lift `_safe_env()` into `safety/`, call it from `terminal.py` + `lint_test.py` + `files.run_command` — one scrubbed-env policy.

### control-1 / sec-3 — redaction is key-name-only; free-text secrets stream unredacted
`control/redaction.py:16-33,41-63` · `_walk` masks a value only when its **dict key** matches `SECRET_KEYS`; it never inspects values. Live: a payload with `https://user:hunter2@…`, `AWS_SECRET_ACCESS_KEY=…`, `Bearer sk-proj-…`, a JWT → `redacted_fields=[]`, unchanged. These stream to every SSE client and persist to `var/agent_runs/*/events.jsonl`. The `runner` emits exactly the unguarded field names (`text`, `result`, `stdout`).
**Fix:** add a value-shape regex pass over string leaves (`AKIA[0-9A-Z]{16}`, `sk-[A-Za-z0-9]{20,}`, `ghp_`, `Bearer …`, `://user:pass@`, `KEY=VALUE` env lines, PEM headers); mask span, record path. Keep key-based pass as fast path.

---

## HIGH — broken invariants & real bugs (all verified HOLD unless noted)

| id | title | locations | fix (short) |
|---|---|---|---|
| **domain-1 / arch-2** | Role allowlist **never enforced at runtime** — whole E07/E09 epic is advisory prompt text | `roles/agent.py:42-54`, `graph/nodes.py:106-128`, `core/kernel.py:128` | **DECIDED: wire it (not delete) — E07/E09 is not-yet-wired, not abandoned.** Default the root session's `context.allowed_capabilities` to the bound role's `Agent.allowed_tools` (`orchestrator/loop.py`), and in `supervisor/graph.py:175` intersect `assignment.allowed_capabilities` with the role's scope. `core/kernel.py:128` already enforces `context.allowed_capabilities` — feed it the role set. Then fix `domain-2` (SKILL.md parser) **before** wiring, or the allowlist ingests "disallowed" tools. |
| **safety-2** | `finish_gate` never fed its inputs — "done without validation" always allowed | `discipline/finish_gate.py:7-22`, `graph/nodes.py:220` | in `tool_node`, set `code_changed=True` after fs writes, `validation_passed=True` after a green pytest/ruff; reset on new edit. |
| **arch-1** | "One compiled LangGraph substrate" is **false** — `supervisor/` is a second hand-rolled loop w/ own checkpoint DB + event path | `supervisor/loop.py:148`, `supervisor/graph.py:5`, `supervisor/checkpoint.py:18` | **DECIDED: finish the lift.** Express `compose_team/o_decide/run_round/judge` as LangGraph nodes on a `StateGraph` with `SqliteSaver`; retire `SqliteTaskLoopStore` + the bespoke `SupervisorContext.emit` path. Until lifted, README must state the present-tense reality (two stacks), not the target. |
| **sup-1** | Empty `allowed_capabilities` silently widens child to **full parent scope** | `delegation/policy.py:25`, `supervisor/graph.py:175`, `supervisor/contracts.py:44` | distinguish `None` (inherit) from `frozenset()` (deny-all); `x or parent` is a falsy-empty bug. |
| **sup-2** | `need_tool` round **re-executes non-idempotent tools on resume** (no dedup) | `supervisor/graph.py:214-226`, `supervisor/loop.py:179-190` | key tool requests by `hash(round+tool+args)`, skip if already in `tool_results`; checkpoint inside `run_tool`. |
| **safety-4** | Git-mutation block bypassed by `git -C` — only `argv[1]` inspected | `safety/policy.py:16,63-66` | skip leading global flags (and their values) to find the real subcommand before matching `GIT_MUTATIONS`. |
| **safety-3** | `json_gate` region extractor O(n²), no input cap → DoS (`{`×20000 = 9.8s) | `discipline/json_gate.py:43-73,305-317` | cap input (`MAX_GATE_INPUT=64KB`); replace nested scan with one O(n) stack pass. |
| **ui-1 / sec-4** | `/api/snapshot` **unauthenticated** while every sibling endpoint requires the token | `ui/ide/server.py:230-237` | add `if not self._require_token(): return`; update `getSnapshot` in `adapter/controlPlane.ts` to send the header. |
| **ui-2 / sec-5** | Static default token `'dev-token'` + CORS reflecting **any** localhost origin | `ui/ide/server.py:51,176-181,455`, `config.ts:4` | generate `secrets.token_urlsafe(32)` per process when unset; print once; drop cross-port localhost CORS for mutating routes; `hmac.compare_digest`. |
| **ui-3** | `scope=project` allows write/delete over the whole repo incl `.claude/settings.json` (hook injection), invisible to diff review | `ui/ide/files.py:75-83`, `ui/ide/server.py:286-362` | **DECIDED: keep write (intentional for IDE) — do NOT make read-only.** So the protections become mandatory, not optional: (1) deny-list execution-affecting paths `.claude/`, `harness/`, `CLAUDE.md`, `pyproject.toml`, `.git/` for write/delete/rename; (2) extend `snapshot_baseline`/`compute_diffs` to cover `scope=project` so project edits show in the Changes review surface (currently invisible); (3) keep the auth/token fixes (`ui-1/2`) — write surface is only as safe as the token. |
| **control-2** | `redact_for_ui` flag is **dead** — declared on 8 event types, consulted by nobody | `control/event_registry.py:27,90`, `control/emitter.py:56-58` | make it meaningful (whitelist ui_payload when true) or delete it so the contract stops lying. |
| **control-3** | Replay buffer re-accepts an evicted re-delivered event → corrupts `oldest_seq`, suppresses resync | `control/replay.py:28-39,55-66` | track `_evicted_high` watermark; reject `seq <= _evicted_high`. |
| **control-4** | Snapshot shows a re-dispatched agent as `done` — read-model contradicts the stream | `control/snapshot.py:260-264,339-344` | order status check so a pending call beats a stale turn; track `turned` per round. |
| **domain-2** | `SKILL.md` parser matches `'allowed'` as **substring** → "not allowed"/"disallowed" read as the allowlist | `skills/spec.py:69,113-114` | exact canonical-heading match, not `needle in heading`. |
| **conc-1** | IDE runs never finalize `EventLogger` → no `summary.json`/`index.jsonl`; run eternally "started" | `ui/ide/runner.py:148`, `observability/event_log.py:80-99` | bind the logger, call `.finish(status,…)` in success/fail/cancel paths (mirror `ui/server.py:253-258`). |
| **docs-1** | MAP.md generator never recurses into subpackages → `adapters/agents/` & live `ui/ide/` invisible | `tools/gen_map.py:36,42` | `rglob('*.py')` filtered by DENY; regenerate; add a test asserting `ui/ide/server.py` appears. |
| **graph-1** *(adj → medium)* | Duplicated session-state codec in `checkpoint.py`, buggier than the shared one it already imports | `orchestrator/checkpoint.py:43-56`, `graph/state.py:42-57` | delete `_encode_state/_decode_state`; import `encode/decode_session_state`. |

### Refuted
- **arch-3** — claim "control plane is ~1.5k LOC of speculative dead code, one optional consumer" is **wrong**: `ui/ide/{session,server,runner,bridge}.py` consume most of `control/` at runtime. Surviving narrow truth: `authz.py` has no enforcement call-site (by its own docstring, DEC-7) and `EventSinkPort` is single-impl. Treat as low.

---

## MEDIUM / LOW (verified at summary level; fix opportunistically)

**core:** core-2 Retry re-runs permanent failures (missing-capability flag invisible to `_retryable`) · core-3 `freeze()` not thread-safe · core-4 registry silently overwrites duplicate capability name · core-5 `execute_tool(context=None)` bypasses scope · core-6 EventBus swallows all subscriber exceptions silently · core-7/8/9 single-impl ports, post-freeze mutable `_middlewares`, per-subscriber deep-copy cost.
**control:** control-5 authz doctrine no call-site · control-6 frozen RuntimeEvent payload mutable in place · control-7 single-impl EventSinkPort · control-8 `needs_resync` misses in-ring gaps.
**supervisor:** sup-3 worker `artifact_id` collides with `len()`-based id · sup-4 broker exposes whole Blackboard to every worker · sup-5 depth budget non-monotonic · sup-6 progress_sink rejects valid seq > max_steps before dedup · sup-7 acceptance gate accepts any cited evidence id without binding to the AC.
**safety:** safety-5 `repair_mode` patch-gate dead · safety-6 single-quote JSON repair corrupts string content · safety-7 `condense()` unbounded recursion.
**graph:** graph-2 adapter fabricates synthetic `final` on exhausted failure · graph-3 feature loader no partial-install rollback · graph-4 dead `step_exceeded()` w/ wrong comparator · graph-5 default prompt never teaches `delegate` verb · graph-6 resume widens scope to ALL tools · graph-7 `_sync_budget` reaches into `Budget._tool_calls` private state · graph-8 retry classifier blind to wrapped status codes.
**domain:** domain-3 separation-of-duties guard dead · domain-4 RAG jail validates only ingest root, not per-file symlink target · domain-5 Qdrant `_collection_ready` racy · domain-6 ingest crashes run on embedder cardinality mismatch.
**ui:** ui-4 runner emits undeclared `chat.*` event types · ui-5 duplicate file-jail/tree/sensitive impl (`ui/server.py` vs `ui/ide/files.py`) · ui-6 IDE server sets no baseline security headers · ui-7 App.tsx re-fetches everything on every event · ui-8 dead `IdeSession.next_seq()`.
**architecture:** arch-4 budget discipline in three places · arch-5 triple tool-safety gate (PolicyGate + SafeToolPort + classify) · arch-6 `graph/runtime.py` god module · arch-7 single-impl ports as fake swap-points · arch-8 committed root debris `read_file_and_list.py`.
**security:** sec-6 SSE token in URL query (logs/Referer leak) · sec-7 path-escape regex false-positives block legit relative paths · sec-8 context-dump script writes secret-adjacent plaintext.
**concurrency:** conc-2 "thread-safe JSONL" locks are process-local (multi-proc unsafe) · conc-3 delegation store single-writer-by-construction (claim oversold) · conc-4 EventBus only catches `Exception` (not BaseException) · conc-5 summary.json written outside the lock · conc-6 `complete_task/fail_task` non-atomic check-then-act.
**docs:** docs-2 MAP.md committed stale · docs-3 README says E21 UI "pending" but React control-plane exists · docs-4 getting-started documents wrong failure field · docs-5 `.gitignore` gaps (`.hypothesis/`, `node_modules/`, `dist/`, `.coverage`) · docs-6 unresolved "thiếu docstring" markers · docs-7 no LICENSE · docs-8 stale scratch dumper · docs-9 mcp-tools.md in unaccented Vietnamese.

---

## Test-quality audit (backfilled separately)

Verdict: **~35% theater.** Strong: checkpoint/resume round-trips, path-jail escape property tests, JSON-repair rules, keyed-secret redaction. Missing on the dangerous paths: **no integration test proves the role allowlist blocks a disallowed tool** (only unit tests of the never-called guard), **no json_gate DoS/size test** (hypothesis `max_size=100`), **no free-text-secret redaction test**, **no crash-during-checkpoint-write test**. Two real bugs sit as `xfail(strict=False)` in `tests_audit/test_toolbox_sandbox_rigor.py` (CR/CRLF round-trip corruption; NUL-byte path crash). The `tests/` vs `tests_audit/` split is principled but undocumented.

---

## Fix order

**P0 — security kill-chain:** sec-1 (scrub env) → sec-2 (resolve-and-jail argv paths) → safety-1 (constrain interpreters / OS sandbox) → control-1/sec-3 (value-shape redaction) → ui-1/2/3 (token snapshot, random default token, lock down scope=project).
**P1 — broken invariants:** domain-1/arch-2 (wire or delete role allowlist) → safety-2 (feed finish_gate) → sup-1 (None vs empty scope) → sup-2 (resume tool dedup) → safety-4, domain-2, control-3, control-4, conc-1, safety-3.
**P2 — architecture honesty + dedup:** arch-1 (LangGraph lift or README downgrade) → core-1 (canonical envelope flags) → graph-1/arch-4/arch-5 (dedup) → docs-1 + .gitignore + control-2.

## Decisions (resolved by owner, 2026-06-26)
- **arch-1 — `supervisor/` → LangGraph.** Intended end-state is a compiled substrate. Fix = finish the lift; README must not claim it present-tense until done.
- **E07/E09 role layer → not-yet-wired (not abandoned).** Fix = WIRE the allowlist into `context.allowed_capabilities` (domain-1/arch-2). Order: fix `domain-2` (SKILL.md substring parser) first, else the allowlist ingests "disallowed" entries.
- **`scope=project` write → intentional for the IDE.** Keep write; the deny-list of execution-affecting paths + diff visibility (ui-3) are now mandatory, not optional.

These three answers all close the "delete/downgrade" branch and open the "finish/harden" branch — none of the dead code is disposable; it is unfinished. That raises the priority of **wiring the role allowlist** (domain-1): once it is the real runtime authz boundary, `sup-1` (empty-scope widening) and `graph-6` (resume widens to all tools) become genuine privilege-escalation bugs, not latent ones — fix them in the same pass.
