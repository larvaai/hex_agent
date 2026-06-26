---
name: hs-flow:loop
description: In-session self-optimization loop — N iterations against a measurable metric, learns from git history, auto-keep/discard changes. Use for mechanical metrics (coverage, bundle size). In-session only.
category: flow
license: AGPL-3.0
keywords: [loop, in-session, self-optimization, iterations, against, measurable]
when_to_use: "Use for mechanical metrics (coverage, bundle size)."
argument-hint: "<Goal> <Scope> <Verify> [Guard] [Iterations] [Direction] [Min-Delta] [Noise]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit, MultiEdit, Glob, Grep]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-flow:loop — iterative in-session self-optimization

**When to use**: a metric is measurable by a shell command (single number) and you want to
improve it through multiple try-keep/discard iterations.

**When NOT to use**:

| Situation | Use instead |
|---|---|
| Subjective goal ("make it cleaner") | hs:cook |
| Bug with known cause | hs:fix / hs:debug |
| One-off, not iterative | hs:cook |
| No measurable metric | hs:cook --interactive |
| Unattended run, Docker sandbox | **hs-flow:afk** (see Boundaries) |

## Inputs

Any required field missing → `AskUserQuestion` to collect all at once.

| Field | Required | Example |
|---|---|---|
| `Goal` | Yes | `"Increase coverage in harness/scripts/"` |
| `Scope` | Yes | `"harness/scripts/**/*.py"` |
| `Verify` | Yes | shell command that prints a **single number** |
| `Guard` | No | command that exits 0 = nothing is broken |
| `Iterations` | No (default 10) | maximum number of iterations |
| `Direction` | No (default higher) | `higher` or `lower` |
| `Min-Delta` | No (default 0) | minimum improvement threshold to count as progress |
| `Noise` | No (default medium) | `low` / `medium` / `high` |

Need a `Verify` command or unsure how to set `Direction`/`Noise`/`Guard`? Copy a
ready-made preset from `references/metric-presets.md` (coverage, lint, type errors,
LOC) and the per-metric rubric.

## Procedure (8 phases per iteration)

**Phase 0 (first iteration only) — prerequisite check:**
- git repo is clean (`git status --porcelain` → empty)
- HEAD is on a named branch (not detached)
- Scope glob matches ≥1 file
- Dry-run `Verify` → exit 0 + prints a number
- Dry-run `Guard` (if provided) → exit 0
- Record baseline in `loop-results.tsv` (iteration 0)

**Phase 1 — Review (required, never skip):**
Load `references/iteration-control.md` — read git log + diff + `loop-results.tsv`
to recognize patterns: what worked, what failed repeatedly.

**Phase 2 — Ideate:** select **1 atomic change** within Scope. If the description contains
"and", split into 2 iterations. Rotate to a different area/technique after ≥3 consecutive discards.

**Phase 3 — Modify:** edit files within Scope; do not touch the Guard file.

**Phase 4 — Commit before measuring:**
```
git add <files>
git commit -m "loop(iter-N): <one-sentence description>"
```
Git is the memory and undo mechanism — commit BEFORE verifying.

**Phase 5 — Verify:** run the Verify command, read the number. See
`references/exit-conditions.md` — crash/timeout → discard the iteration, record the error.

**Phase 5.5 — Guard (if provided):** non-zero exit → revert + rework up to 2 times →
record `guard-failed`, discard the iteration.

**Phase 6 — KEEP / DISCARD decision:**
- KEEP: delta ≥ Min-Delta + guard passes → update `PREV_METRIC`, reset discard counter.
- DISCARD: `git revert HEAD --no-edit` (preferred) / reset only when revert conflicts.

**Phase 7 — Record trace:** `trace_log.py` + append a TSV row to `loop-results.tsv`.
TSV schema: `iteration | commit | metric | delta | status | description`.
See `references/progress-tracking.md` for format + status values.

**Phase 8 — Iterate or stop:** see `references/exit-conditions.md` — any one stop
condition is sufficient; print final report.

## HARD-GATE (real wiring)

- **Trace**: `harness/hooks/trace_log.py` — each KEEP/DISCARD decision + loop end
  records 1 event. Append-only, fail-open (trace never blocks the loop).
- **Verify safety scan**: before the dry-run, scan the Verify command for:
  `rm -rf /`, `rm -rf $HOME`, `curl|sh`, `wget|bash` → REFUSE.
  Outbound writes, `sudo`, credentials in literals → WARN + ask.
- **Guard read-only**: the Guard file is read-only throughout the loop — never
  modify test/spec files to game the metric.
- **Clean git prerequisite**: dirty tree → STOP before Phase 0, prompt `git stash`.

## Boundaries

- **IN-SESSION, does not ship**: loop only commits locally. `push|pr|ship|deploy`
  must go through `harness/hooks/gate_stage.py` + a human reviewer — the loop does not invoke these.
- **Unattended / Docker sandbox**: use **hs-flow:afk** instead. hs-flow:loop is lightweight,
  in-session, has no container boundary and no Ralph reviewer-stage.
- **Hard scope**: do not modify files outside the declared Scope; do not modify the Guard file.
- **Do not self-edit `stage-policy.yaml`** to bypass the gate mid-loop.
- On completion: return the absolute path to `loop-results.tsv` + final summary + next-step suggestion
  (continue / plateau reached / manual review needed).

## Any-one stop conditions

Load `references/exit-conditions.md` for the full matrix. Summary:

| Condition | Action |
|---|---|
| `Iterations` budget exhausted | Stop, report |
| 10 consecutive discards | Stop, report, suggest manual intervention |
| Metric reaches Goal | Stop, report success |
| File `loop-stop` exists in CWD | Stop immediately (soft interrupt) |
| Ctrl-C / user interrupt | Stop, record trace interrupt |
