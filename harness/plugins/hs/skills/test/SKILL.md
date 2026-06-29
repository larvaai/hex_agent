---
name: hs:test
description: Run and validate tests for the current change — unit/integration profiles, concise QA report, 100% pass gate.
category: core
license: AGPL-3.0
keywords: [test, run, validate, tests, current, change]
when_to_use: "Run and validate tests for the current change — unit/integration profiles, concise QA report, 100% pass gate."
argument-hint: "[unit | integration]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs:test — disciplined verification

Run tests for the scope that just changed, then report results truthfully. A test failure is information,
not an enemy.

**General rules**: `harness/rules/tdd-discipline.md` (100% pass, fix
do not weaken) + `harness/rules/verification-mechanism.md` (verdict +
checks[] are the evidence the gate reads). When human review of verdict/QA report is needed, apply
`harness/rules/plannotator-review-gates.md` (diff → `review`, report → `annotate`).

## Pre-flight

1. **Resolve the test command for this repo's stack FIRST.** If the target is not Python
   (no `pytest`/`pyproject.toml`), run `python3 harness/scripts/detect_techstack.py --root <repo>`
   and use the reported `test_cmd` (e.g. `go test ./...`, `pnpm test`) — do not assume `pytest`.
   A `test_cmd: null` means the stack declares no runner; ask which one before proceeding.
2. `python3 harness/scripts/preflight_deps.py` — Python targets: if pytest/PyYAML is missing,
   stop with the install command; do not run blindly.
3. Quick import-check of the recently modified module (catching import errors here is cheaper than mid-suite).

## Profiles

| Profile | Scope | When |
|---|---|---|
| `unit` (default) | test the modified module → full unit suite | every TDD cycle |
| `integration` | add e2e (`harness/e2e/run_vertical_slice.py`) | before a hard stage |

Standard command: `python3 -m pytest harness/tests/ -q` (target repos use their own suite
per standards — for a non-Python target use the `test_cmd` from Pre-flight step 1).

Detailed scope by change type (feature/fix/refactor/dep-bump) and coverage
thresholds (line ≥80%, branch ≥70%) → `references/coverage-and-edge-cases.md`.

## Result rules

- **100% pass is the gate** (tdd-discipline rule): failure → fix the code or fix a genuinely
  wrong test (with a reason); deleting/skipping/weakening tests to fake green is forbidden.
- QA report <200 lines: list **ALL** test failures (name + 1-line reason), notable coverage changes,
  final verdict: PASS / PASS_WITH_RISK (state the risk) / BLOCKED.
  Full template → `references/qa-report-format.md`.
- Verdict + checks[] written to `plans/<plan>/artifacts/verification.json` (schema
  `harness/schemas/artifact-verification.json`) — the artifact the hard stage gate reads.
  How to write it correctly + resolve_actor → `references/verification-artifact.md`.

## Fix loop and regression

When failing: QA report → hand off to hs:cook (fix) or hs:fix (single bug) → re-run.
A bug fix must have a regression test written BEFORE the fix (intentional failure). Regression scope and
build verification checklist → `references/regression-and-build.md`.

## Boundaries

hs:test **only runs and reports** — it does not modify code, does not weaken tests, and does not
decide on merge. Modifying code → hs:cook / hs:fix. Post-test review → hs:code-review.
Evidence validation → hs:debug when root cause needs deep tracing.

## HARD-GATE (real wiring)

`gate_stage.py` reads verification.json: any check `FAIL` → hard stage is blocked.
Fraudulent reporting (writing PASS while failing) is exposed immediately when the suite re-runs in CI;
the trace ledger keeps a record of who wrote what (attribution, verification-mechanism rule).
