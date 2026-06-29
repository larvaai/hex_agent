# Gate Sequence — hs:ship

Detail for each pipeline step. Read when tracing a gate error or debugging an artifact.

## Step 1 — Preflight

Load `references/preflight-checklist.md`. Summary: branch check → mode detect
→ diff summary → secret scan → dry-run gate → early artifact warning.

## Step 2 — Merge target

```bash
git fetch origin <target>
git merge origin/<target> --no-edit
```

- Auto-resolvable conflicts (lockfile, version file): resolve and continue.
- Complex conflicts → **STOP**, show the list of conflicting files.
- Already up-to-date → continue silently.

## Step 3 — Test

Skip if `--skip-tests`.

Auto-detect runner in order:
`pytest.ini/pyproject.toml[tool.pytest]` → `pytest` |
`package.json scripts.test` → `npm test` |
`Makefile test:` → `make test` |
`Cargo.toml` → `cargo test` |
`go.mod` → `go test ./...`

Delegate to `hs:test`. Do not inline test execution.

- Any test FAIL → **STOP**. Do not continue the pipeline.
- No runner found → AskUserQuestion: ["Skip tests", "Enter test command"].

## Step 4 — Review → review-decision.json

Skip only if `review-decision.json` already exists with verdict PASS
(a prior cook run already performed the review).

If missing or verdict ≠ PASS: delegate to `hs:code-review`.

`hs:code-review` writes:
```
plans/<active-plan>/artifacts/review-decision.json
  verdict: PASS | PASS_WITH_RISK | BLOCKED
```

**Verdict rule (hard)**:
- `PASS` → continue.
- `PASS_WITH_RISK` → **STOP**: AskUserQuestion
  ["Fix now and re-review", "Accept risk (BLOCKED ship)", "Cancel"].
  Gate `stage-policy.yaml` requires exactly `PASS` — no workaround.
- `BLOCKED` → **STOP**: must fix, re-review, get a new verdict.

## Step 5 — Verification artifact check

`verification.json` must exist at `plans/<active-plan>/artifacts/verification.json`.
Pass conditions:
- File exists.
- No check has `status: FAIL`.
- `verdict` is `PASS` (not `BLOCKED`).

This artifact is produced by `hs:cook` when a phase runs — if missing, the user
must run cook or create it manually per schema `harness/schemas/artifact-verification.json`.

```bash
python3 -c "
import json, pathlib, sys
sys.path.insert(0, 'harness/scripts'); import artifact_check
d = artifact_check.resolve_active_plan('.')
if not d: sys.exit('verification.json: no active plan')
p = pathlib.Path(d) / 'artifacts' / 'verification.json'
if not p.exists(): sys.exit('verification.json: MISSING')
v = json.loads(p.read_text())
fails = [c for c in v.get('checks',[]) if c.get('status')=='FAIL']
if fails: sys.exit(f'verification FAIL checks: {fails}')
if v.get('verdict') == 'BLOCKED': sys.exit('verification verdict: BLOCKED')
print('verification:', v.get('verdict'))
"
```

## Step 6 — Plan approval artifact check

`plan-approval.json` must exist at `plans/<active-plan>/artifacts/plan-approval.json`.

Check using the official script:
```bash
python3 -c "import sys,pathlib; sys.path.insert(0,'harness/scripts'); import artifact_check; d=artifact_check.resolve_active_plan('.'); sys.exit(0 if d and (pathlib.Path(d)/'artifacts'/'plan-approval.json').exists() else 1)" || echo "plan-approval: MISSING"
```

The artifact is created by the approver via `plan_approval.py`. The gate checks:
- `verdict: APPROVED`
- `reviewer` ≠ `author` (unless `allow_self_review`)
- `reviewer` is in the `harness/data/team.yaml` roster
- `plan_hash` matches the current plan hash (drift → FAIL)

If the plan is edited after approval → hash drift → gate blocks.
Resolution: re-approve after editing the plan.

## Step 7 — Changelog + Version (conditional)

**Changelog**: look for `CHANGELOG.md` / `CHANGES.md` / `HISTORY.md`.
If none → skip silently.

Generate entry from `git log origin/<target>..HEAD --oneline` + diff.
Classify: Added (feat:) | Changed (refactor:/perf:) | Fixed (fix:) | Removed.
Do not ask the user for content — infer from commits + diff.

**Version**: look for `VERSION` / `package.json` / `pyproject.toml` / `Cargo.toml`.
If none → skip silently.

Bump logic:
- Default → patch (the safe default, regardless of diff size)
- Breaking change / major feature → AskUserQuestion: ["Minor", "Patch"]

## Step 8 — Release notes

Load `references/release-notes.md` to generate PR body content.

## Step 9 — Commit + Push

Stage everything:
```bash
git add -A
```

Final secret scan before committing:
```bash
git diff --cached | grep -iE "(AKIA|api[_-]?key|token|password|secret|credential|private[_-]?key|mongodb://|postgres://|-----BEGIN)"
```
Match found → **STOP immediately**.

Conventional commit:
```bash
git commit -m "$(cat <<'EOF'
type(scope): description

Short body from changelog entry or commit log.
EOF
)"
```

Push:
```bash
git push -u origin $(git branch --show-current)
```

**Pre-push hook** `harness/install/git-pre-push-hook.sh` runs automatically:
- Scrubs `HARNESS_*` env
- Calls `artifact_check.check_stage("push", root)`
- Missing `verification.json` → exit 2 (fail-closed)

Stage `ship` from `gate_stage.py` + `stage-policy.yaml` also checks
`review-decision` and `plan-approval` before the Bash tool completes.

If push is rejected: suggest `git pull --rebase` → retry once.
No force push.

## Step 10 — PR

```bash
gh pr create \
  --base <target-branch> \
  --title "type(scope): description" \
  --body "$(cat <<'EOF'
## Summary
<bullets from commit log>

## Pre-Landing Review
<verdict + findings from step 4>

## Test Results
- [x] All tests pass (<N> tests)

## Changes
<git diff --stat trimmed>

## Ship Mode
- Mode: official|beta
- Target: <target-branch>
EOF
)"
```

If a PR already exists for the branch → use `gh pr edit` instead of create.

**Final output**: PR URL. This is what the user sees.

## Error handling summary

| Error | Action |
|-----|-----------|
| Artifact MISSING | Show which artifact is missing, suggest how to create it |
| Gate exit 2 | Read gate stderr, report the artifact error |
| Push rejected | `git pull --rebase`, retry |
| `gh` not installed | Guide installation, stop after push |
| Plan hash drift | Re-approve plan via `plan_approval.py` |
