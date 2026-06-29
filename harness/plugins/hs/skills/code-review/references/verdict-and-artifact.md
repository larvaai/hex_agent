---
name: verdict-and-artifact
description: How to map a review verdict to review-decision.json and its relationship with gate_stage.py
---

# Verdict and artifact

After review completes, `hs:code-review` must emit an artifact conforming to
`harness/schemas/artifact-review-decision.json`. The gate `gate_stage.py` reads
this artifact to decide whether to allow or block the pr/ship/deploy stage.

---

## Verdict to artifact mapping

| Review outcome | Verdict artifact | Gate action |
|---|---|---|
| No Critical/Important findings | `PASS` | Stage allowed to proceed |
| Findings exist but owner consciously accepts | `PASS_WITH_RISK` | Stage allowed; risk recorded |
| Unresolved Critical findings | `BLOCKED` | Gate blocks — no artifact emitted |

`PASS_WITH_RISK` is a **conscious soft-accept**, not a free ship license.
Rationale must explain why the risk is being accepted.

---

## Required schema

```json
{
  "verdict": "PASS | PASS_WITH_RISK | BLOCKED",
  "reviewer": "<resolve_actor() output>",
  "role": "reviewer",
  "rationale": "<WHY — a paragraph explaining the verdict>"
}
```

**Optional fields:**
- `plan_hash`: sha of plan.md at review time — detects plan drift after approval
- `ticket_id`: seam for task-store issue/MR link

Full backing schema: `harness/schemas/artifact-review-decision.json`.

---

## Artifact path

Write to the active plan's artifact path:

```
plans/<active-plan>/artifacts/review-decision.json
```

If no plan is active (ad-hoc review): write the report to `plans/reports/`
and clearly state that no gate-able artifact exists — the gate will not activate.

---

## Gate relationship

`harness/hooks/gate_stage.py` is a **presence gate**:

- Verifies the artifact EXISTS at the correct path
- Verifies `verdict` satisfies policy (`harness/data/stage-policy.yaml`,
  stage's `requires:` lists `review-decision`)
- Hard stages require **exactly `PASS`** — `PASS_WITH_RISK` is not sufficient for a hard stage
- The gate does NOT verify the reviewer is different from the author — that is a role check
  in `plan_approval`, not in this gate

**When the gate blocks:**
- Exit 2 with an actionable reason
- No exceptions — fail-closed

---

## Artifact emit procedure

```
1. Review complete → determine verdict
2. If BLOCKED → report findings, do NOT write artifact → gate will block
3. If PASS or PASS_WITH_RISK:
   a. Call resolve_actor() to get reviewer identity
   b. Fill all required fields (verdict, reviewer, role, rationale)
   c. Optionally: compute plan_hash from sha256 of current plan.md
   d. Write JSON to plans/<active-plan>/artifacts/review-decision.json
   e. Report absolute artifact path in chat
4. Report verdict + unresolved questions
```

---

## Example PASS artifact

```json
{
  "verdict": "PASS",
  "reviewer": "agent:code-reviewer",
  "role": "reviewer",
  "rationale": "No Critical or Important findings. 2 Suggestions for micro slop
    are noted but do not block. Gate logic, error handling,
    and test coverage are adequate for the change scope.",
  "plan_hash": "a3f9c1d4e8b2"
}
```

## Example PASS_WITH_RISK artifact

```json
{
  "verdict": "PASS_WITH_RISK",
  "reviewer": "agent:code-reviewer",
  "role": "reviewer",
  "rationale": "1 Important finding: cache invalidation missing on updateUser().
    Owner accepts the risk because this PR scope only fixes an auth bug; cache refactor is
    tracked in BACKLOG.md. Shipping with the known stale-cache risk.",
  "plan_hash": "b7d2e5f1c9a4"
}
```
