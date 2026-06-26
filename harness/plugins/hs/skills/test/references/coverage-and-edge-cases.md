# Coverage and edge cases (on-demand)

Load when: coverage needs checking, test scope needs defining, or error paths need validating.

## Scope by change type

| Change | Minimum scope |
|---|---|
| New feature | new test (intentional failure → implement → green) + full unit suite |
| Bug fix | regression test targeting the exact bug + full related suite |
| Refactor | existing suite (no new tests unless a gap is found) |
| Coverage check | full suite with `--cov` |

## Coverage thresholds

| Metric | Standard threshold | Notes |
|---|---|---|
| Line | ≥ 80% | project-wide minimum |
| Branch | ≥ 70% | watch for hidden `if/else` |
| Function | ≥ 80% | critical paths must be 100% |

Critical paths (auth, state mutation, gate logic) require 100% — below threshold → write
`PASS_WITH_RISK` in verdict and name the specific file/function.

Command: `python3 -m pytest harness/tests/ -q --cov=harness --cov-report=term-missing`

## Error paths and edge cases

Checklist before closing a TDD cycle:

- [ ] Happy path has a test
- [ ] Boundary inputs (empty, None, overflow, wrong type) are tested
- [ ] Error handlers and exception paths have coverage
- [ ] State mutation after failure is safe (rollback / fail-closed)
- [ ] No flaky tests (race condition, shared state) — if found → record in
  `PASS_WITH_RISK`, do not skip
- [ ] Test isolation: every test is self-contained, no ordering dependency

## Analyzing results

Prioritize in this order:
1. **Test FAIL** — read the stack trace, identify root cause before fixing
2. **Flaky** — inconsistent pass/fail → race condition or state leak
3. **Slow** (>5s/test) — a smell; record in risk if no plan exists
4. **Intentional skip?** — a skip that hides a failure is treated as FAIL until confirmed

Every coverage gap requires a specific `file:function` — a percentage alone is not sufficient evidence.
