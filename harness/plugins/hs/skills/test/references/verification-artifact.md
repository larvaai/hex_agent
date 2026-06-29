# Verification artifact (on-demand)

Load when: `verification.json` needs to be written after running the suite.

Backing: schema `harness/schemas/artifact-verification.json` +
rules `harness/rules/verification-mechanism.md` +
`harness/rules/tdd-discipline.md`.

## When to write

Required after every hs:test run — before handing off to a hard stage
(push / pr / ship). `gate_stage.py` reads this file from disk; if missing → stage is blocked.

## Location

```
plans/<active-plan>/artifacts/verification.json
```

If no plan is active the verification is not gate-able and the hard stage is blocked — create a plan with `status: in_progress` (or set `HARNESS_ACTIVE_PLAN`) so the artifact resolves at `plans/<active>/artifacts/`.

## Required structure (from schema)

```json
{
  "stage":   "push",
  "plan":    "<plan-dir-name>",
  "actor":   "<resolve_actor() output>",
  "ts":      "<ISO-8601>",
  "checks": [
    { "name": "pytest-unit",        "status": "PASS" },
    { "name": "pytest-integration", "status": "PASS", "detail": "e2e slice OK" },
    { "name": "coverage-line",      "status": "PASS", "detail": "87%" },
    { "name": "coverage-branch",    "status": "SKIP", "detail": "62% < 70% target waived this run" }
  ],
  "verdict": "PASS_WITH_RISK"
}
```

- `status` per check: `PASS` | `FAIL` | `SKIP`
- **Any check `FAIL` → hard stage is blocked** (gate_stage.py)
- `verdict`: `PASS` | `PASS_WITH_RISK` | `BLOCKED`
- `actor`: output of `resolve_actor()` — this is attribution, not authorization

## Honesty rules

- Do not self-report PASS when a check is FAIL — CI will expose it immediately on re-run
- Trace records are maintained via `trace_log.append_event` (actor + ts auto-resolved)
- `PASS_WITH_RISK` = risk exists but does not block — provide specific detail in the check
- Claims without a `file:line` or real command output → `UNVERIFIABLE` → downstream rejects

## Resolve actor

```python
from harness.hooks.hook_runtime import resolve_actor
actor = resolve_actor()   # returns "user:<u>[/agent:<a>]" or "ci"
```
