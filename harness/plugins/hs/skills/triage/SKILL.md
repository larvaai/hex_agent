---
name: hs:triage
description: Orchestrate the defect lifecycle — reproduce, classify, and gate bugs via hs:scout→hs:debug→hs:fix→hs:test. Use when a bug, test failure, or unexpected behavior is reported.
category: core
license: AGPL-3.0
keywords: [triage, orchestrate, defect, lifecycle, reproduce, classify]
when_to_use: "Use when a bug, test failure, or unexpected behavior is reported."
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob, Task]
argument-hint: "[hotfix|standard|escalate] [defect description]"
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs:triage — defect lifecycle orchestration

Orchestrator: receive defect → reproduce → classify → route to component skills.
**Triage does NOT patch code itself** — fixing is the responsibility of `hs:fix`.

**Evidence rule** + presence gate: `harness/rules/verification-mechanism.md`.
**TDD red→green**: `harness/rules/tdd-discipline.md` — read first, not repeated here.

## Modes

| Mode | When | Flow |
|---|---|---|
| `hotfix` | severity critical, defect scope clearly local | scout → debug → fix → test → gate |
| `standard` (default) | ordinary bug, cause not yet clear | full pipeline + review |
| `escalate` | architecture affected / 3+ hypotheses failed | route to `hs:plan` |

No argument → `AskUserQuestion`: describe the defect + select mode.

## Step 1 — Triage & reproduction

Load `references/triage-routing.md`.

- Collect: full error message, reproduction steps, expected vs actual.
- Stable reproduction: record the minimal command — this is the baseline for comparison after the fix.
- Classify severity + reproducibility → select mode (table above).
- Cannot reproduce → gather more data (no guessing).

## Step 2 — Scout

Use `hs:scout` to identify: affected files, callers/dependents, related tests,
`git log --oneline -20`. Record "blast radius". Output → `plans/reports/`.

## Step 3 — Debug (root cause)

Use `hs:debug`: 4 phases (evidence → pattern → hypothesis-loop → finalize root cause).
`hs:debug` stops at **root cause + failing repro test** (`harness/rules/tdd-discipline.md`).
If 3+ hypotheses fail → STOP, switch to `escalate` → `hs:plan`.

## Step 4 — Fix (delegate)

Use `hs:fix` with the failing repro test from Step 3 as input.
`hs:fix` runs its own pipeline: fix → test red→green → review → gate.
Triage does NOT interfere with `hs:fix`'s internal pipeline.

Mode `standard` → `hs:fix` mode `standard` (full review).
Mode `hotfix` → `hs:fix` mode `quick` (abbreviated review).

**Escalation:** multiple candidate patches for a flaky/perf defect, undecidable by reasoning →
`hs-think:bakeoff` on the stable repro + a mechanical metric (% pass over N runs, latency) to pick the
patch by numbers, instead of arguing which fix is better.

## Step 5 — Verify (regression sweep)

Use `hs:test` to run the full suite for the affected scope — 100% pass required to proceed.
QA report → `plans/reports/`.

## Step 6 — Gate

Load `references/gate-wiring.md`.

`harness/hooks/gate_stage.py` (presence gate) blocks stage `push|pr|ship|deploy` when:
- `plans/<plan>/artifacts/verification.json` is missing or verdict ≠ PASS
  (schema `harness/schemas/artifact-verification.json`).
- For severe defects: additionally `plans/<plan>/artifacts/review-decision.json` PASS
  (schema `harness/schemas/artifact-review-decision.json`; produced by `hs:code-review`).

Trace significant steps via `harness/hooks/trace_log.py` (`append_event`).

## HARD-GATE (real wiring)

| Backing | Role |
|---|---|
| `harness/hooks/gate_stage.py` | Presence gate — blocks stage when artifact is missing |
| `harness/schemas/artifact-verification.json` | Schema for `verification.json` |
| `harness/schemas/artifact-review-decision.json` | Schema for `review-decision.json` |
| `harness/rules/verification-mechanism.md` | Evidence rule, 5 invariants |
| `harness/rules/tdd-discipline.md` | Red→green, 100% pass |
| `harness/rules/workflow-handoffs.md` | Fix-loop chains 6/7; escalate path |

## Boundaries

- Do NOT patch code — delegate entirely to `hs:fix`.
- Do NOT bypass the gate (do not edit `harness-hooks.yaml`/`stage-policy.yaml` — tracked in git, diff + trace expose it).
- Do NOT fast-fix architectural defects — escalate to `hs:plan`.
- Discovery outside bug scope → `BACKLOG.md`, do not expand the fix.
- On completion: root cause (file:line), files modified, gate verdict, report link.

## References (load when needed)

| Drawer | Content | When to load |
|---|---|---|
| `references/triage-routing.md` | Severity matrix, reproduction protocol, escalation criteria | Step 1 |
| `references/escalation-criteria.md` | When to escalate vs fast-fix, architectural signals | Mode decision |
| `references/defect-repro.md` | Defect reproduction protocol, handling flaky / non-reproducible defects | Hard-to-reproduce defects |
| `references/gate-wiring.md` | Pre-gate artifact checklist, side-effect sweep, review surface | Step 6 |
