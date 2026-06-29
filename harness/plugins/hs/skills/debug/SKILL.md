---
name: hs:debug
description: Systematic debugging with root-cause analysis before fixing. Use for bugs, test failures, unexpected behavior, performance issues, log analysis, CI/CD, and system investigation.
category: core
license: AGPL-3.0
keywords: [debug, systematic, debugging, root-cause, analysis, before]
when_to_use: "Use for bugs, test failures, unexpected behavior, performance issues, log analysis, CI/CD, and system investigation."
argument-hint: "[--system | --perf | --bisect]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob, Task]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs:debug — systematic root-cause investigation

This skill stops at **root cause + failing repro test**. The actual fix
belongs to `hs:fix` — always cross-reference after debugging is complete.

**Core rule**: DO NOT FIX before the root cause is identified.
Guess → patch → guess again = waste and new bugs.

## Modes / flags

| Mode | When to use |
|---|---|
| (default) | bug / test failure / unexpected behavior — code level |
| `--system` | system incident: server error, CI/CD failure, multi-component |
| `--perf` | performance degradation, slow query, high latency |
| `--bisect` | unclear which commit caused the regression — load `references/reproduction-and-bisection.md` |

## Main procedure (4 phases — code-level)

Load details: `references/root-cause-method.md`.

**Phase 1 — Collect evidence** (required BEFORE thinking about a fix):
- Read the stack trace and error message in full — skip no lines.
- Reproduce the failure consistently: record the exact steps. Cannot reproduce → collect more data.
- Check recent changes: `git log --oneline -20`, diff config, dependency updates.
- Trace data flow: where does the bad value originate? Trace back up the call stack.

**Phase 2 — Analyze patterns**:
- Find similar working code in the repo — compare every difference.
- Identify dependencies: which component, config, or env is involved?

**Phase 3 — Hypothesis → evidence loop**:
Load `references/hypothesis-loop.md`.
- Formulate 2-3 competing hypotheses — do not lock onto the first one.
- Test each: smallest possible change, one variable at a time.
- Confirm or eliminate with evidence. If > 3 fix attempts fail → stop,
  consider the architecture (may need `hs-think:brainstorm`).

**Phase 4 — Finalize root cause + failing repro test**:
- **Write a failing test that reproduces the bug** (`harness/rules/tdd-discipline.md` — red→green
  rule: test must fail INTENTIONALLY before the fix).
- Do not delegate a fix here — hand the root cause + test to `hs:fix`.

## System procedure (`--system`, 5 steps)

Load `references/instrumentation.md` + `references/root-cause-method.md`.

1. **Initial assessment**: collect symptoms, identify affected components,
   check recent changes (deploy, config, dep update).
2. **Data collection**: server/app logs for the relevant time window; CI/CD via `gh run view
   <id> --log-failed`; DB state via the project stack's CLI; system metrics.
3. **Analysis**: reconstruct the timeline, identify patterns, trace the request path.
4. **Identify root cause**: systematically eliminate hypotheses; document the full event chain
   from trigger to symptom.
5. **Propose a fix**: immediate (minimum to restore service) + root fix +
   preventive (monitoring gap). Actual fix is performed via `hs:fix`.

## Instrumentation and log analysis

Load `references/instrumentation.md` when additional trace/log observation is needed.

Stack-agnostic tools:
- Log parsing: `grep`, `awk`, `sed` — always use `grep --line-buffered` when piping.
- CI/CD: `gh run list --limit 10`, `gh run view <id> --log-failed`.
- DB: project stack CLI (sqlite3, psql, mysql, etc.) per project.
- Codebase: read `docs/codebase-summary.md` if < 2 days old; otherwise use `hs:scout`.

## Skill output

The skill ends with:
1. **Confirmed root cause** (evidence chain, not "possibly").
2. **Failing repro test** committed (or ready to commit) — this test is the
   input for `hs:fix`.
3. **Report** at `plans/reports/<slug>-debug-report.md` (format:
   `references/root-cause-method.md` section Report).
4. Cross-reference: `/hs:fix <path-to-failing-test>` — guides user to the next step.

## Delegating the investigation

For complex investigations (multi-component, CI/CD, system), spawn the
`debugger` agent — it runs the full behavioral checklist
(gather evidence → 2-3 hypotheses → eliminate → root cause chain →
recurrence prevention). Agent reports are written to `plans/reports/`.

```
hs:debug → spawn debugger agent (investigation)
         → failing repro test (tdd-discipline.md)
         → hs:fix (fix)
```

## Boundaries

- Do NOT implement a fix — fixing belongs to `hs:fix`.
- Do NOT skip Phase 1 even if the issue "looks simple".
- Do NOT claim "fixed" without a failing test confirming the root cause.
- If 3+ hypotheses all fail: STOP, reconsider the architecture, ask the user.
- Reports must distinguish "confirmed cause" vs "likely cause" — be honest about certainty.

## HARD-GATE (real wiring)

- `harness/rules/tdd-discipline.md`: a failing repro test is required evidence —
  no test → debug not complete, cannot hand off to fix.
- `harness/plugins/hs/agents/debugger.md`: the investigation agent has a behavioral
  checklist (evidence-first, multi-hypothesis, elimination documented).
- Reports → `plans/reports/` (harness-contract rule).

## Red flags — STOP

If you are thinking any of the following, return to Phase 1:
- "Quick fix to get it done, investigate later"
- "Let me try changing X and see"
- "It's probably X, let me just fix it"
- "Tests are passing, done" (when no failing repro test existed beforehand)

## References (load on demand)

| Drawer | Content | When to load |
|---|---|---|
| `references/root-cause-method.md` | Full 4-phase procedure, evidence chain, report format | When the main debug procedure needs detailed steps |
| `references/hypothesis-loop.md` | Formulate/test/eliminate competing hypotheses | When entering Phase 3 (hypothesis testing) |
| `references/instrumentation.md` | Log/trace/metric tooling, stack-agnostic commands | When Phase 1 evidence collection needs instrumentation |
| `references/reproduction-and-bisection.md` | `git bisect` workflow for regression hunting | When using `--bisect` mode |
| `references/defense-in-depth.md` | Four-layer validation pattern: entry, business logic, environment guards, debug instrumentation | When root cause is invalid data reaching unsafe code and multi-layer validation is needed |
