# Pattern overview — autonomous iteration vs. single-pass research

## Two fundamentally different models

| Dimension | hs-research:research | hs-research:autoresearch (router) / hs-flow:loop |
|---|---|---|
| **Passes** | 1 guided pass | N autonomous iterations |
| **Output** | Evidence report in `plans/reports/` | Committed code changes + TSV trace |
| **Metric** | Not required (qualitative quality) | Required — single number from a shell command |
| **Rollback** | Not applicable | Automatic when verify fails |
| **Termination** | User reads report and decides | Stops on condition (Iterations, plateau, goal) |
| **Human-in-loop** | Start (set the question) + end (read the report) | Start (declare params) + end (review results) |

## When to use which

**Use hs-research:research when:**
- Technology or architecture evaluation is needed before implementation.
- The result is a text report with evidence anchors (URL, file:line).
- No measurable shell metric exists.
- A single pass is sufficient.

**Use hs-flow:loop (via the hs-research:autoresearch router) when:**
- A mechanical metric measurable by a shell command exists (single number).
- You want to improve the metric over multiple try-keep/discard iterations.
- Automatic code changes within the declared scope are acceptable.
- A commit-by-commit audit trail is needed.

## Atomic-commit pattern (autoresearch core)

Every loop in the autoresearch group follows a sequence that must not be violated:

```
Review (learn from history)
  → Ideate (1 atomic change)
    → Modify (within Scope)
      → Commit (BEFORE verify — git is the memory)
        → Verify (exit 0 + number)
          → Guard (if set)
            → KEEP / DISCARD (revert if discarded)
              → Write trace
                → Loop or stop
```

Committing before verify is the defining characteristic of this pattern: git
serves as memory, not in-session state. Revert = a clean undo with no extra logic.

## Lineage

The pattern originates from the Modify -> Verify -> Keep/Discard -> Repeat loop:
bounded, atomic, reversible experimental optimization. The harness implements
this pattern through `hs-flow:loop`; the `hs-research:autoresearch` page is the conceptual
anchor so other skills can reference the shared safety posture without duplicating
content.
