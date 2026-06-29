# iteration-control — loop control

Load at the start of Phase 1 (Review) each iteration.

## Required reads each iteration (never skip)

```bash
git log --oneline -20          # change history + order
git diff HEAD~1                # exact diff from the previous iteration
cat loop-results.tsv           # metric trend + keep/discard
```

Three questions to answer before Ideate:
1. **What worked?** (kept=yes, delta in the right direction)
2. **What failed?** (kept=no repeatedly, same file path recurring)
3. **Where is the trend heading?** (last 5 deltas — increasing, flat, or reversing?)

## Exploiting successful patterns

- Files of the same type that improved before → try adjacent files
- Technique that was KEPTed (e.g., adding null guard) → apply to unchecked functions
- Module that yielded large delta → prioritize next

## Avoiding failed patterns

- File + technique pair already DISCARDed → do not retry the same pair
- Zero-delta change (refactor that did not move the metric) → skip
- Metric fluctuating on one file → leave it, move to another file

## Atomicity test (Phase 2 — Ideate)

Describe the change in 1 sentence. If the sentence contains "and" → split into 2 iterations.

WRONG: "add null guard for `parse()` and extract helper function"
RIGHT: "add null guard for empty input in `parse()`"

## Stuck — rotate strategy

| Consecutive discards | Action |
|---|---|
| 3 | Re-read log, switch to a different file area or technique |
| 5 | Analyze loop-results.tsv for patterns → change direction explicitly |
| 10 | Stop — see `references/exit-conditions.md` |

## Commit convention

```
loop(iter-N): <one-sentence description>
```

- Enables querying: `git log --oneline --grep="loop(iter-"`
- Reverts preserve the convention: `Revert "loop(iter-4): ..."` — try-discard
  history is data, do not delete it.

## Technique selection by metric

| Metric | Starting technique |
|---|---|
| Test coverage | Add test cases for uncovered branches; fill edge cases |
| Lint / type error | Fix individual errors, do not mass-refactor |
| Bundle size | Tree-shake unused imports; replace heavy dependencies |
| Build time | Split chunks; remove synchronous dependencies |

Full metric library (verify commands by stack): see hs-flow:loop references — adapt
commands to the project's toolchain.
