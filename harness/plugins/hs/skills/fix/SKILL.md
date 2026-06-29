---
name: hs:fix
description: Fix bugs, test failures, and CI/CD failures with an evidence-based workflow. Use when there is a concrete bug, a clear error, or a red test.
category: core
license: AGPL-3.0
keywords: [fix, bugs, test, failures, evidence-based, workflow]
when_to_use: "Use when there is a concrete bug, a clear error, or a red test."
argument-hint: "[quick | standard | deep]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, Task]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs:fix — evidence-based bug fixing

Standard flow: **debug → fix → red→green test → review → gate**.
No step may be skipped. Diagnose the root cause BEFORE fixing.

**Evidence rule** (Evidence Filter, artifact = source of truth) in
`harness/rules/verification-mechanism.md` — read first; not repeated here.

**TDD red→green**: `harness/rules/tdd-discipline.md` — test fails intentionally first,
implement until green, paired commit, 100% pass before gate.

## Modes

| Mode | When | Behavior |
|---|---|---|
| `quick` | lint/type error, obvious single-file issue | minimal scout → diagnosis off → fix → verify |
| `standard` (default) | multi-file bug, unclear cause | full pipeline: scout→diagnose→fix→test→review→gate |
| `deep` | architectural impact, 3+ failures | escalate: deep hs:debug + hs-think:brainstorm before fixing |

No argument → `AskUserQuestion` asking for error description + mode selection.

## HARD-GATE (real wiring)

Stage `push|pr|ship|deploy` is blocked by `harness/hooks/gate_stage.py` when
`verification.json` is missing, any check is non-PASS/SKIP, or the verdict is `BLOCKED` (schema:
`harness/schemas/artifact-verification.json`). The gate is a presence gate —
it proves the step ran, not who ran it
(`harness/rules/verification-mechanism.md`).

## Standard procedure

### Step 1 — Scout (required, cannot be skipped)

Understand the codebase BEFORE forming hypotheses:
- Use `hs:scout` or an Explore subagent to find: affected files, callers/dependents,
  related tests, `git log --oneline -20` (which recent commit is the cause?).
- Record the "blast radius": every code path that depends on the broken behavior.
- Quick mode: only the affected file + direct deps.

### Step 2 — Diagnose (required, cannot be skipped)

Load `references/triage-and-scope.md`. Principles:
- **Capture state before**: copy-paste the exact error message, test failure output,
  stack trace. This is the baseline for comparison at Step 4.
- Spawn the `debugger` agent: investigate the root cause with an evidence chain
  (observe → hypothesize → test hypothesis → trace back to root cause).
- Do not propose a fix until all 5 questions are answered:
  1. Exact symptom (precise error)?
  2. Reproduction steps (minimal command)?
  3. Expected vs actual?
  4. Root cause at `file:line`?
  5. Blast radius (which paths are affected)?
- If any answer is vague ("probably", "I think") → `AskUserQuestion` or scout further.
- If 2+ hypotheses fail → escalate to mode `deep`, ask the user.

### Step 3 — Fix (minimal scope)

Load `references/minimal-fix-discipline.md`. Principles:
- Fix the ROOT CAUSE, not the symptom.
- Minimal change: only necessary files, following existing patterns in the codebase.
- Do NOT create new abstractions when not needed; do NOT refactor outside bug scope.
- After 3 failures → STOP, reframe the architectural question with the user.

### Step 4 — Red→green test (required)

Load `references/regression-test.md`. Follow `harness/rules/tdd-discipline.md`:
1. Write a regression test **BEFORE** fixing (or confirm an existing test fails at the right point).
2. Run the test → must be **RED** (intentional failure).
3. Apply the fix → re-run → must be **GREEN**.
4. Run the full suite: `python3 -m pytest harness/tests/ -q` (or the repo suite per
   standards). All must pass.
5. Deleting/skipping/weakening tests to go green is forbidden — "Fix regressions, not the test."

Write `verification.json` (`harness/schemas/artifact-verification.json`):
`stage`, `plan`, `actor`, `ts`, `checks[]`, `verdict`. The `verdict` is one of
`PASS` / `PASS_WITH_RISK` / `BLOCKED`; for VERIFICATION a hard stage clears when no
check FAILs and the verdict is not `BLOCKED` (both `PASS` and `PASS_WITH_RISK` pass).
The exact-`PASS` rule applies to review-decision / critique-consensus, not verification.

### Step 5 — Review

Spawn `code-reviewer` agent:
- Input: modified files + blast radius from Step 1 + diagnosis report from Step 2.
- Ask reviewer to check: (a) root cause is genuinely resolved (not a symptom patch), (b) no regression in blast radius, (c) public contract unchanged (signatures, schemas, env vars), (d) no new errors.
- If reviewer flags a regression → `AskUserQuestion` with 2-4 specific options (revert /
  narrow scope / update dependents / accept with explicit note). Do not decide unilaterally.

### Step 6 — Gate and finalize

Load `references/verify-and-gate.md`:
- `harness/hooks/gate_stage.py` reads `verification.json` — missing / verdict BLOCKED
  → gate blocks push/ship.
- After gate passes: ask user whether to commit (spawn `git-manager` agent, conventional
  commit, no AI reference). If a plan is active → update plan status.
- If docs/behavior changed → spawn `docs-manager` agent to update `docs/`.

## Boundaries

- Do NOT modify files outside bug scope (strict YAGNI).
- Do NOT create abstractions, wrappers, or helpers not directly required.
- Do NOT bypass the gate by writing PASS without running real tests.
- Do NOT weaken/skip/delete tests to fake green.
- On completion: report root cause, files modified (absolute paths), tests added, gate verdict.
- If gate blocks → clearly state the reason + the missing checklist items.

## Agent/rule wiring

| Backing | Role |
|---|---|
| `debugger` agent | Root cause investigation (Step 2) |
| `code-reviewer` agent | Review fix + blast-radius sweep (Step 5) |
| `harness/rules/tdd-discipline.md` | Red→green rule, 100% pass (Step 4) |
| `harness/hooks/gate_stage.py` | Presence gate before ship (Step 6) |
| `harness/schemas/artifact-verification.json` | verification.json schema |
| `harness/rules/verification-mechanism.md` | Evidence rule |
| `plans/reports/` | Diagnosis + review reports |

## References (load when needed)

- `references/triage-and-scope.md` — 5-question diagnosis, blast radius
- `references/minimal-fix-discipline.md` — minimal-fix principles, anti-patterns
- `references/regression-test.md` — red→green test procedure, verification.json
- `references/verify-and-gate.md` — pre-gate checklist, side-effect sweep
