---
name: hs:ship
description: "Gated ship pipeline: review PASS → verification PASS → human approval → push/pr. Highest-risk stage — all gates must be real. Use when a completed branch needs to become a PR."
category: core
license: AGPL-3.0
keywords: [ship, gated, pipeline, review, pass, verification]
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, Task]
when_to_use: "Invoke when a feature/fix branch is done and needs a PR to main/target."
argument-hint: "[official|beta] [--skip-tests] [--dry-run]"
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs:ship — gated ship pipeline

`hs:ship` is the highest-risk skill in the harness. It **does not bypass gates** —
it orchestrates all prerequisites before push/PR reaches the transport layer.

**Real gates**: `harness/hooks/gate_stage.py` + `harness/data/stage-policy.yaml`
hard-block stage `ship` when artifacts are missing. The pre-push hook
`harness/install/git-pre-push-hook.sh` adds a second block at the transport layer.

Stage `ship` requires **3 artifacts simultaneously**:
- `verification.json` — verdict PASS (no FAIL checks)
- `review-decision.json` — verdict **exactly PASS** (PASS_WITH_RISK does not qualify)
- `plan-approval.json` — reviewer ≠ author, plan hash has not drifted

An org wanting a stricter gate can add a 4th — `critique-consensus.json` (produced
by `/hs-think:critique --gate`) — by listing `critique-consensus` in the stage's
`requires` in `stage-policy.yaml`. It ships **off** so a spine-only install is
never blocked by a plugin it has not enabled.

## Arguments

| Flag | Effect |
|------|----------|
| `official` | Target main/master — full pipeline |
| `beta` | Target dev/beta — skip docs update |
| (empty) | Infer from branch name; ambiguous → ask |
| `--skip-tests` | Skip the test step (use when tests were already run separately) |
| `--dry-run` | Show the plan, do not execute |

> `--skip-tests` reuses the existing `verification.json` — only sound when it was
> produced in THIS branch state. A stale artifact from an earlier state passes the
> gate on evidence that no longer matches the diff (the Iron Law: a stale run is not
> a pass). Re-run tests if HEAD moved since the artifact was written.

## When to STOP (blocking)

- Currently on the target branch → ABORT
- Merge conflict that cannot be auto-resolved → STOP, show conflicts
- Tests fail → STOP, show failures
- `hs:code-review` returns `review-decision` verdict ≠ PASS → STOP, ask
- Artifact missing → gate blocks, do not continue
- Artifact drift (plan modified after approval) → gate blocks

## When NOT to ask

- Commit message → compose from diff + commit log
- Patch version bump → decide autonomously
- Changelog → generate automatically (do not ask for content)
- No version/changelog file present → skip silently

## Pipeline

```
Step 1: Preflight         → check branch, mode, diff, dry-run
Step 2: Merge target      → fetch + merge origin/<target>
Step 3: Test              → delegate hs:test (auto-detect runner)
Step 4: Review            → delegate hs:code-review → write review-decision.json
Step 5: Verification      → hs:cook has written verification.json (check artifact)
Step 6: Plan approval     → plan-approval.json artifact must exist
Step 7: Changelog/Version → generate automatically, no prompts
Step 8: Release notes     → load references/release-notes.md
Step 9: Commit + Push     → conventional commit + git push (via pre-push hook)
Step 10: PR               → gh pr create with standard body
```

Detail: `references/gate-sequence.md`
Preflight checklist: `references/preflight-checklist.md`
Release notes: `references/release-notes.md`

## Step 4 — Review (real gate)

`hs:code-review` writes `review-decision.json` to
`plans/<active-plan>/artifacts/review-decision.json`.
Verdict must be `PASS` — `PASS_WITH_RISK` does not qualify for ship.
If verdict ≠ PASS: AskUserQuestion (fix now / accept risk / cancel).

**Simplify before review**: scan the branch diff first — a special case, a duplicated
pattern, or an abstraction earning its keep nowhere should be collapsed before review.
A smaller diff is a cheaper review and a smaller risk surface. Pattern library:
`harness/plugins/hs-think/skills/problem-solving/references/simplification-cascades.md`.

## Steps 5-6 — Artifact check

Before pushing, verify manually:
```bash
python3 -c "
import json, pathlib, sys
sys.path.insert(0, 'harness/scripts'); import artifact_check
d = artifact_check.resolve_active_plan('.')
if not d: sys.exit('No active in-progress plan resolved')
arts = pathlib.Path(d) / 'artifacts'
for f in ['verification.json','review-decision.json','plan-approval.json']:
    p = arts / f
    if not p.exists(): sys.exit(f'MISSING {f}')
    print(f'{f}: OK', json.loads(p.read_text()).get('verdict','?'))
"
```
The gate blocks automatically on push — manual check is for early detection.

## Output format

```
✓ Preflight: branch feature/foo, 5 commits, +200/-50 lines (mode: official)
✓ Merged: origin/main
✓ Tests: 42 passed
✓ Review: PASS (0 critical)
✓ Verification: PASS
✓ Approval: reviewer: alice (hash match)
✓ Changelog: updated
✓ Commit: feat(scope): description
✓ Pushed: origin/feature/foo
✓ PR: https://github.com/org/repo/pull/123
```

## HARD-GATE (real wiring)

| Gate | Real backing |
|------|-------------|
| Stage ship (artifact check) | `harness/hooks/gate_stage.py` + `harness/data/stage-policy.yaml` |
| Transport layer (pre-push) | `harness/install/git-pre-push-hook.sh` |
| Plan approval artifact | `harness/scripts/plan_approval.py` + `harness/schemas/artifact-plan-approval.json` |
| Review decision artifact | `harness/schemas/artifact-review-decision.json` (verdict PASS strict) |
| Verification artifact | `harness/schemas/artifact-verification.json` (no FAIL check) |

**Do not shortcut the gate.** If a gate blocks incorrectly, investigate the artifact — do not edit the hook.

## Boundaries

- DO NOT force-push any branch.
- DO NOT proceed when artifacts are missing — the gate will block; no further prompting needed.
- DO NOT commit secrets — scan the staged diff before committing (pattern: `AKIA|token|password|secret`).
- On exit: return the PR URL. If the gate blocks, return which artifact is missing.
- Enable `hs-meta:context-engineering` if context is nearly full before starting this long pipeline.
