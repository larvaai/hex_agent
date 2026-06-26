---
name: hs:code-review
description: Review code with technical rigor — bugs, regressions, security. Supports pending changes, PR number, commit hash, codebase scan. Verdict in review-decision.json; failing review blocks pr/ship/deploy.
category: core
license: AGPL-3.0
keywords: [code-review, review, code, technical, rigor, bugs]
when_to_use: "Review code with technical rigor — bugs, regressions, security."
argument-hint: "[--pending | <#PR|commit|codebase>] [--fix] [--reply] [--spec <plan>]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob, Task]
metadata:
  owner: harness
  compliance-tier: gate
---

# hs:code-review — evidence-based code review

Review focused on production risk: logic defects, regressions, trust-boundary
violations, security, performance. No rubber-stamping; no praise-padding. Evidence
before claims.

**Posture**: assume code was written by an AI agent until proven otherwise.
Clean structure, confident comments, and happy-path tests are not evidence of correctness.
The reviewer is rulebook-first, not a collaborator avoiding friction with the author.

## Input modes

Auto-detect from argument. No argument → `AskUserQuestion`.

| Input | Mode | Diff source |
|---|---|---|
| `--pending` | Pending | staged + unstaged (`git diff`) |
| `#123` or PR URL | PR | `gh pr diff` |
| `abc1234` (7+ hex) | Commit | `git show` |
| `codebase` | Full scan | `hs-research:repomix` compact then analyze |
| *(none)* | Recent | changes in current context |

Argument resolution details: `references/input-mode-resolution.md`.

## Orthogonal flags

| Flag | Effect |
|---|---|
| `--fix` | After review, delegate fix to `hs:fix --mode quick`; commit+push; re-review until no actionable findings remain |
| `--reply` | Post review to PR via `gh pr review` after review (or after fix loop) |
| `--spec <plan>` | Enable Stage 1 spec-compliance before Stage 2 quality review |

Flags are composable: `hs:code-review #123 --fix --reply` runs the fix loop then posts the final review.

## Workflow

```
1. Parse argument → determine mode + flags
2. Edge-case scout (required when ≥3 files changed): hs:scout before review
3. [If --spec] Stage 1 — Spec compliance (references/spec-compliance.md)
   → FAIL? fix → re-review Stage 1 → then continue
4. Stage 2 — Quality review: delegate to code-reviewer agent
   Checklist: correctness · security · breaking-changes ·
   performance · testing · anti-slop (references/review-dimensions.md)
5. Verdict: Approve / Request changes / Comment
6. Write artifact review-decision.json (references/verdict-and-artifact.md)
7. [If --fix] Fix loop: hs:fix --mode quick → hs:git cp → re-review
8. [If --reply] Post review to PR (references/pr-review-workflow.md)
```

## Severity taxonomy

| Level | Meaning | Action |
|---|---|---|
| **Critical** | Bug, security, data loss, breaking change | Must fix before merge |
| **Important** | Wrong logic, missing validation, structural slop | Should fix |
| **Suggestion** | Style, minor, micro slop | Nice-to-have |

Full taxonomy + anti-slop patterns: `references/severity-taxonomy.md`.

## Output language

Generated output (reports, docs, human-facing summaries) follows `harness/data/output.yaml`. Read its `language:` value (default `vi`) and write the prose in that language. Before finalizing, apply `harness/rules/humanizer-and-anti-ai-tells.md`: strip AI-writing tells, and when `language: vi`, also strip the Vietnamese translation-tells. Evidence is never translated or rewritten: keep `file:line` references, IDs, SHAs, numbers, and verbatim quotes exactly as found.

## Boundaries

- Do NOT self-merge, do NOT self-deploy; review is a gate — the merge decision belongs to the human.
- Verdict `BLOCKED` → no artifact emitted → `gate_stage.py` blocks pr/ship/deploy.
- Verdict `PASS` → artifact written with verdict PASS → a hard stage may proceed.
- Verdict `PASS_WITH_RISK` → artifact written, but a HARD stage (pr/ship/deploy)
  still BLOCKS: only an exact PASS clears it. `PASS_WITH_RISK` is a conscious
  soft-accept (record the risk, keep moving on soft stages), never a ship license.
- Re-review cycle maximum 3 times — if no convergence, escalate to user.
- Do not modify files outside `plans/reports/` (reports) and the active plan's artifact path.
- On completion: report verdict + absolute artifact path + unresolved questions.

## HARD-GATE (real wiring)

```
harness/hooks/gate_stage.py          — blocks stage pr|ship|deploy when
                                       plans/<plan>/artifacts/review-decision.json
                                       is absent or verdict != PASS
harness/schemas/artifact-review-decision.json
                                     — verdict schema (PASS|PASS_WITH_RISK|BLOCKED)
                                       + reviewer + role + rationale + plan_hash
harness/plugins/hs/agents/code-reviewer.md
                                     — agent that performs the review (Stage 2)
plans/reports/                       — long-term review report storage
```

Stage policy is read from `harness/data/stage-policy.yaml` — when a stage's `requires:` lists
`review-decision`, the gate activates for that stage. The gate is a presence gate (verifies artifact EXISTS
and verdict satisfies policy), not a role gate.

## Verification gate

Before any claim of "review complete" or "PASS":

1. **IDENTIFY** — which command proves this claim?
2. **RUN** — run it fully, do not reuse cached results
3. **READ** — read the output, count failures, check exit code
4. **VERIFY** — does the output confirm? If not → report the true status
5. **THEN claim** — with evidence

No verification evidence → no PASS claim. (This rule has no exceptions.)

## Observe checkpoint (end-of-work)

When the review is done, if this run surfaced a judgment a counter cannot see, record ONE closed-vocab
signal so the harness learns from it — emit only a REAL observation, not every run. Vocabulary lives in
`harness/data/observation-signals.yaml`.

```bash
python3 harness/scripts/emit_observation.py --skill hs:code-review \
    --signal <thin-evidence|gate-repeat-block|trigger-near-miss> \
    --payload "<one line: what happened>"
```

Surfaces in the read-only `observations` lens (honesty-gated). Skip it silently when nothing notable
happened — a fabricated signal is worse than none.

## Workflow position

Typically runs after: `hs:cook` (review after implement) · `hs:fix` (review after bug fix)
Typically runs before: `hs:git` ship · `hs-flow:afk` submit
Related: `hs:scout` (scout before review) · `hs:test` (test before review)

## References (load on demand)

| Drawer | Content | When to load |
|---|---|---|
| `references/checklists/base.md` | Universal two-pass checklist (critical/informational): injection, race conditions, security boundaries, auth, test gaps, performance | Always load when running checklist-based review |
| `references/checklists/web-app.md` | Overlay for frontend frameworks: XSS, CSRF, N+1 queries, a11y, responsive layout | When project has React/Vue/Svelte/Next or JSX/TSX in diff |
| `references/checklists/api.md` | Overlay for REST/GraphQL/gRPC: rate limiting, input validation, data exposure, API design, observability | When project exposes API routes or OpenAPI spec exists |
| `references/checklist-workflow.md` | Step-by-step workflow to apply checklists: auto-detect type, load overlays, two-pass diff review, suppression check, output format | When running structured pre-landing or security-audit review |
