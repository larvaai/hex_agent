---
name: hs-mem:retro
description: Generate data-driven retrospective reports from git history — velocity, code health, hotspots, plan progress. Use for sprint reviews, periodic assessments, or engineering lookbacks.
category: mem
license: AGPL-3.0
keywords: [retro, generate, data-driven, retrospective, reports, git]
when_to_use: "Use for sprint reviews, periodic assessments, or engineering lookbacks."
argument-hint: "[timeframe] [--compare] [--team]"
user-invocable: true
allowed-tools: [Bash, Read, Write]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-mem:retro — data-driven retrospective

Analyze git history to produce an objective retrospective report — no guesswork,
no invented numbers. Lessons → action proposals; architectural lessons worth
keeping long-term → record as a decision via `decision_register.py`.

**No commits, no code changes.** This skill is read-only.

## Flags

| Flag | Default | Description |
|---|---|---|
| `timeframe` | `7d` | Time range: `7d`, `2w`, `1m`, or `YYYY-MM-DD:YYYY-MM-DD` |
| `--compare` | off | Compare with the preceding period of the same length |
| `--team` | off | Break down by author |

No argument → `AskUserQuestion` to ask for timeframe and mode.

## Workflow

### Step 1 — Resolve the time range

Resolve `timeframe` into `SINCE` / `UNTIL`. With `--compare`, also compute
`PREV_SINCE` / `PREV_UNTIL` (immediately preceding period, same length).

### Step 2 — Collect raw git data

Run the commands in `references/git-queries.md`. If a command returns nothing,
record `0` or `N/A`. **Never invent numbers.**

Data groups:
- **Velocity**: total commits, commits/day, active days, files changed
- **Code health**: LOC added/removed/net, churn rate, test-to-code ratio
- **Commit types**: conventional commit type distribution
- **File hotspots**: top 10 most-changed files

### Step 3 — Compute derived metrics

See formulas in `references/metrics-guide.md`. Include the formula in the report
so readers can verify the figures.

### Step 4 — Scan plans/

```bash
find plans/ -name "*.md" -newer /tmp/retro-since-sentinel 2>/dev/null | head -20
grep -r "\- \[x\]" plans/ | wc -l   # tasks done
grep -r "\- \[ \]" plans/ | wc -l   # tasks still open
```

Count `[x]` / `[ ]` checkboxes in plan files modified during the period.

### Step 5 — Analyze and propose

From real data:
- **What went well** (≥2): grounded in specific numbers — no generic praise
- **What to improve** (≥2): linked directly to a metric (hotspot, high churn, low test ratio)
- **Action items** (3-5): specific, actionable, tied to a metric

If an action item is an architectural decision worth recording long-term:
```bash
python3 harness/scripts/decision_register.py --append-alloc ...
```

Short-term technical lessons (not substantial enough for a decision) → entry in `BACKLOG.md`.

### Step 6 — Export report

Use the template at `references/retro-output-template.md`. Fill every cell with real data.

Save to: `plans/reports/retro-{YYMMDD}-{slug}.md`
- `YYMMDD` = today's date (`date +%y%m%d`)
- `slug` = timeframe (e.g. `7d`, `1m`, `2w-compare`)

With `--team`: add a per-author breakdown table.

After saving: print the absolute path of the report file.

### Step 7 — Journal when needed

If a serious failure pattern is detected (test ratio < 10% sustained, hotspot
≥ 30% of commits, churn rate > 3x consecutively) → suggest the user activate
the `journal-writer` agent to record it with full context
(agent at `harness/plugins/hs/agents/journal-writer.md`).

## Boundaries

- Read git history, `plans/`, `docs/` only. **DO NOT** edit any source files.
- Markdown output goes only to `plans/reports/` (rule `harness/rules/harness-contract.md`).
- If `gh` CLI is unavailable: mark `N/A` instead of skipping a table row.
- Lessons → `BACKLOG.md` (as an entry; do not create a standalone REVIEW.md).
- Recurring architectural decisions → `decision_register.py`, not code comments.
- On exit: return the absolute path of the report + a 3-bullet summary
  (what-went-well / what-to-improve / top action item).

## HARD-GATE (real wiring)

No dedicated blocking gate — this skill is read-only. However:
- All bash commands pass through `harness/hooks/gate_stage.py` (PreToolUse monitor);
  Bash does not trigger the stage gate for pure read commands.
- Invocation telemetry is written via `harness/hooks/track_skill_invocation.py`
  (fail-open, does not block).
- Report files are only valid inside `plans/reports/` — violations are caught by the CI invariant.
