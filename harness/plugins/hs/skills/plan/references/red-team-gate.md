# Red-team gate — adversarial plan review (on-demand)

Runs AFTER plan.md + phase files are written, BEFORE validate. Goal: find where
the plan will break in practice, not to praise the plan.

## Personas (choose 2-4 based on the plan's risk surface)

| Persona | Examines |
|---|---|
| Security Adversary | bypass paths, write permissions, injection, secrets, spoofable input |
| Failure Mode Analyst | crash paths, fail-open vs fail-closed, races, partially corrupt state |
| Maintainer 6-months-later | hidden coupling; **naming/SRP**: does the module/script/class name accurately and completely describe its real responsibility? (`core` that also handles artifact I/O is a misleading name -> split) High finding; config drifting away from code |
| Bad-day Operator | rescue commands when a gate is stuck, observability, real rollback |

## Rules

1. **Evidence Filter (two-way)**: every finding MUST point to specific evidence
   (file:line in plan/phase/existing code, or a reproducing command). No evidence
   -> reject, do not include in the report. The same standard applies to **the
   planner's own decisions**: an open decision finalized by analogy with no file:line
   is a finding (the planner owes evidence) — it is not an exempt choice.
2. **Cap at 15 findings** after dedup — above the cap, keep highest severity;
   group the rest. A long report nobody reads is a dead report.
3. Each finding: severity (C/H/M/L) + failure scenario in 1 sentence + suggested
   fix in 1 sentence. No essays.
4. Report saved to `plans/<plan>/reports/from-code-reviewer-to-planner-red-team-<persona>-plan-review-report.md`.

## Disposition (required, done inside plan.md)

Table: finding -> Accept (how and in which phase the plan is updated) / Reject
(with verification source per the "Verified Decisions" rule). An Accepted finding
not yet propagated into phase files means the gate is not done. Deferred items ->
entry in root `BACKLOG.md` with a link to the report; do not create a separate
REVIEW.md file.
