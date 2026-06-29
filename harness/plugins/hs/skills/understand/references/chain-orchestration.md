# Chain orchestration — hs:understand

Details of orchestrating the 3 component skills and the fan-out scout rules.
Backing: `harness/rules/orchestration-protocol.md`.

## Call order

```
scope confirmed
    -> hs-research:repomix   (pack snapshot)
    -> hs:scout     (locate file-key, parallel when SCALE >= 3)
    -> hs-meta:context-engineering  (budget check before synthesis)
    -> synthesize map
    -> hs-mem:docs (optional, only when --persist)
```

Do not reverse the order: repomix must run first so scout knows the scope;
context-engineering must run after scout to estimate actual token usage.

## hs-research:repomix — pack snapshot

Call with:
- `--style markdown` (readable for LLM synthesis)
- `--include "<scope-glob>"` — do not pack the full repo when only a subtree is needed
- `--remove-comments --no-line-numbers` if estimated tokens exceed the budget
- Output: `harness/state/understand-snapshot.<slug>.md` (do not commit)

Feature-detect the CLI first:
```bash
repomix --version 2>/dev/null || echo "MISSING"
```
If CLI is missing -> fallback: read file-key files manually after the scout step;
record `[NO_CLI_FALLBACK]` in the map.

Token guard: if the expected snapshot size exceeds 60% of the context budget ->
narrow scope or ask via `AskUserQuestion` before running.

## hs:scout — locate file-key

### When to use parallel agents
- SCALE < 3: use Grep/Glob directly (do not spawn a subagent).
- SCALE 3-5: spawn 3-5 `Explore` subagents, one agent per directory.
- SCALE >= 6: consult `hs-meta:context-engineering` first; consider limiting scope.

### Subagent prompt (per orchestration-protocol)
Each subagent receives:
```
task: locate file-key in <directory>
files to read: <directory>/**
files to modify: NONE (read-only)
acceptance: list of files + 1-line role per file
constraints: do not read harness/state/, do not read .git/
reports path: plans/reports/
```

### Collecting results
- Wait for all subagents; timeout 3 minutes per agent.
- Merge file lists, dedup paths.
- Write scout report to `plans/reports/scout-understand-<slug>-<date>.md`.

## hs-meta:context-engineering — budget check

Call after obtaining the scout report and snapshot size:
- Provide: token count of the snapshot + number of file-key files to load.
- Receive: strategy (Select / Compress / Isolate) + list of files to load.
- Apply before synthesizing the map — do not load the full snapshot if it
  exceeds the budget.

Reference thresholds (from hs-meta:context-engineering):
- < 70%: continue normally.
- 70-80%: Select — load only file-key files, not the full snapshot.
- > 80%: Compress or Isolate — synthesize the map through a separate subagent.

## hs-mem:docs — persist (optional)

Call only when `--persist` is passed AND the map is a long-lived document
worth keeping. Call mode `update` if the doc already exists, `init` if not.
Backing: `harness/rules/documentation-management.md`.

Do not persist a temporary map (used once to understand, then plan) — keep
temporary maps in `plans/reports/`; do not add noise to `docs/`.

## Subagent status protocol

Require every subagent to end with:
```
Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
Summary: 1-2 sentences
Concerns/Blockers: optional
```

`BLOCKED` / `NEEDS_CONTEXT` -> do not retry with the same prompt; change scope
or ask the user. Advisory subagents must not mutate plan/code (read-only).
