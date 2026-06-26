---
name: hs-think:bakeoff
description: Empirical bake-off — run 2-4 candidate probes on one mechanical metric, pick the winner by numbers or hand to a human when inside the noise band. Use when reasoning can't separate measurable options.
category: think
license: AGPL-3.0
keywords: [bakeoff, empirical, bake-off, run, candidate, probes]
when_to_use: "Use when reasoning can't separate measurable options."
user-invocable: true
argument-hint: "<decision> [--candidates a,b,c] [--metric '<cmd>'] [--noise low|medium|high]"
allowed-tools: [Bash, Read, Write, Glob, Grep, SlashCommand]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-think:bakeoff — decide by running, not by guessing

Several candidate directions, undecidable by reasoning. Build a cheap probe for each, run every probe on
the SAME input set + the SAME mechanical metric, and let the numbers pick the winner — or refuse to pick
when the gap is inside the measured noise. Trust reality, accept token cost, **but only when justified**.

## When to use / When NOT

| Situation | Use |
|---|---|
| ≥2 viable directions + a mechanical metric + reasoning can't separate them | **hs-think:bakeoff** |
| Decision a minute of reasoning settles | `hs-think:predict` / `hs-think:brainstorm` (cheaper) |
| No mechanical metric (only an LLM "quality score") | `hs-think:predict` — do NOT bake-off (fake objectivity) |
| Improving ONE solution over time against a metric | `hs-flow:loop` (time axis, not comparison axis) |
| Unattended long run | `hs-flow:afk` |

## Inputs

Missing any → `AskUserQuestion` (collect all at once).

| Field | Required | Example |
|---|---|---|
| `Candidates` | Yes (2-4) | `redis`, `in-memory`, `sqlite` |
| `Metric` | Yes | shell command printing **one number**, exit 0 (same contract as hs-flow:loop) |
| `Direction` | Yes | `lower` (ms, bytes) or `higher` (throughput, coverage) |
| `Noise` | No (default medium) | `low`=1 trial · `medium`=2 worse-of · `high`=3-5 median |
| `rel_band` | No (default 0.05) | win margin: gap must beat 5% of the best score |
| `Budget` | Yes (≥1 axis) | `--budget-seconds` and/or `--budget-tokens` per probe |
| `Input set` | Yes | the fixed inputs every candidate runs against |

## Gate-first preconditions

Run BEFORE building any probe — `references/gate-first-preconditions.md`. Two halves:

1. **Machine-checked** — `bakeoff_rank.py preflight` (N∈[2,4], safety-scan, budget ceiling) + a dry-run of
   the metric (exit 0 + one number). Any fail → REFUSE, fall back to `hs-think:predict`.
2. **Judgment checklist** (you confirm with the user): is each probe a cheap *stub* (not a full feature)?
   is this decision load-bearing and costly to reverse? Both "no" → don't bake-off.

## Process

1. **Preflight** — dry-run the metric; `python3 harness/scripts/bakeoff_rank.py preflight --candidate … --metric-cmd … --budget-seconds …`. Refuse on non-zero. Confirm the judgment checklist.
2. **Fan-out** — one isolated worktree per candidate via `hs-flow:worktree`. Minimal throwaway probe ONLY, measuring the contested axis. Details → `references/run-mechanism.md`.
3. **Measure** — run the SAME metric on the SAME input in each worktree, N trials per noise; record each: `bakeoff_rank.py record --run <id> --candidate <c> --trial <i> --value <n> [--elapsed-s --tokens]`.
4. **Rank** — `bakeoff_rank.py rank --run <id> --direction … --noise … --rel-band … --plan-dir <plan>`. Exit 0=winner, 3=tie, 4=insufficient. Details → `references/honesty-ledger-and-verdict.md`.
5. **Report** — print the FULL scoreboard incl. losers + `observed_spread` + any `over_budget`. On tie/insufficient, hand to the human — do NOT invent a winner. Return the winning direction to the caller.
6. **Cleanup** — prune candidate worktrees (`hs-flow:worktree remove`); keep the winner's branch if useful.

## HARD-GATE (real wiring)

- `harness/scripts/bakeoff_rank.py` — `preflight` refuses N∉[2,4] / unsafe metric / over-budget; the verdict
  refuses to name a winner when `gap ≤ band` (`band = max(rel_band·rep, observed_spread)`) or trials are
  below the noise minimum. Ledger is append-only JSONL under `state_dir()/bakeoff/` (actor+ts, no RMW).
- `harness/schemas/artifact-bakeoff-verdict.json` — the verdict shape. The verdict is a **handoff artifact**,
  NOT a stage gate — hs-think:bakeoff does not call `gate_stage.py` and blocks no stage.

## Boundaries

- Do NOT bake-off a decision reasoning settles cheaply, or a metric an LLM scores (fake objectivity).
- Do NOT build full features — probes are throwaway stubs measuring the contested axis only.
- Do NOT silently drop losers; always show every candidate's score + spread.
- Tie within noise or too few trials → hand to the human; never manufacture a winner.
- Do NOT bypass `preflight`. Scope creep / multi-metric → `BACKLOG.md`.
- On completion: verdict path + full scoreboard + the winning direction (or the human-handoff reason).

## Output language

Generated output (the reported scoreboard + summary) follows `harness/data/output.yaml` — read its `language:`
value (default `vi`) and write the prose in that language; then apply `harness/rules/humanizer-and-anti-ai-tells.md`.
Evidence is never translated: candidate names, metric values, `file:line`, IDs, and verbatim quotes stay as-is.

## References (load on demand)

| Drawer | Content |
|---|---|
| `references/gate-first-preconditions.md` | The 4 conditions (machine vs judgment), preflight command, fall-back rule |
| `references/run-mechanism.md` | Worktree-per-candidate, minimal-probe discipline, fairness, budget enforcement |
| `references/honesty-ledger-and-verdict.md` | Noise/band rule, min-trial table, the 3 verdicts, no-silent-cut |
