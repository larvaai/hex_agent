---
name: hs:review-pr
description: Review GitHub PR — diff, CI, correctness, security, breaking changes, anti-slop. Supports --fix (fix + commit) and --reply (post to GitHub). Use for a full PR review; for small local diffs use hs:code-review.
category: core
license: AGPL-3.0
keywords: [review-pr, review, github, diff, correctness, security]
when_to_use: "Use for a full PR review; for small local diffs use hs:code-review."
argument-hint: "<#PR|url> [--fix] [--reply]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, Task]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs:review-pr — comprehensive pull request review

Review PR `$ARGUMENTS` in this repository.

Relationship to **hs:code-review**: hs:code-review is suited for a specific diff, a single commit,
or pending changes. hs:review-pr covers the PR/branch level — including CI status,
PR metadata, scope mismatch, and the --fix loop.

## Modes

| Mode | When |
|---|---|
| Review-only (default) | Print findings to chat. No edits, commits, or pushes. |
| `--fix` | Review -> fix findings -> commit+push -> re-review. Loop until no actionable findings remain. |
| `--reply` | After review (or after the fix loop), post the review to GitHub via `gh pr review`. |

Flags can be combined: `review-pr 123 --fix --reply` runs the fix loop then posts the final review.

## Argument parsing

Extract `PR_REF` from `$ARGUMENTS` by stripping `--fix` and `--reply`. Detect flags
by substring match (order does not matter).

No argument -> `AskUserQuestion`: PR number/URL, mode, whether to use --fix.

## Workflow (hard)

### 1. Gather PR context

```bash
gh pr view "$PR_REF" --json title,body,author,baseRefName,headRefName,headRefOid,files,additions,deletions,changedFiles
gh pr diff "$PR_REF"
gh pr checks "$PR_REF" 2>/dev/null || echo "No checks found"
gh pr diff "$PR_REF" --name-only 2>/dev/null | head -50
```

### 2. Read project context

Read `CLAUDE.md`, `docs/code-standards.md`, `docs/system-architecture.md` if they exist.
Use them to detect project-specific convention violations. Load
`references/project-rules-example.md` to see the pattern for encoding project rules.

### 3. Mandatory gates

Run before the verdict — they produce findings even when the code itself is correct.
Load `references/mandatory-gates.md` for the full procedure:

- **Duplicate / prior-work gate** — search PRs/issues/log + the codebase for an existing
  implementation; a merged/overlapping prior is an **Important** finding.
- **Strategic-necessity gate** — review as product owner: does the PR create clear value?
  Correct-but-unnecessary / scope-creep is an **Important** product-risk finding.

(Project standards are already loaded in step 2 — no separate standards gate needed.)

### 4. Analyze the diff

Read each changed file. For modified files, read the full file (not just the diff) to
understand surrounding context. Check:

**Correctness**: logic error, off-by-one, nil/null dereference, missing error
handling, race condition, edge case.

**Security**: injection (SQL/XSS/command/SSRF/path traversal), hardcoded secrets,
missing input validation at system boundary, auth gap.

**Breaking changes**: API contract change without migration/shim, schema change
without migration, removed/renamed public interface.

**Anti-slop**: Load `references/anti-ai-slop.md` when any of the following is true:
diff >300 lines; PR creates >2 new files in `utils/`/`helpers/`/`lib/common/`; a new
generic file name appears, a parallel reimplementation of an existing utility, an
abstraction with a single caller, a config flag for a constant, catch-and-swallow,
a linter silencer, phantom coverage, scope mismatch (title vs diff size), or
LLM-style commit messages. The reference contains the full taxonomy, severity rules,
phrasing guide, and stack appendix.

**Testing**: Are new code paths tested? Do existing tests still pass? Phantom coverage?

### 5. Synthesize findings

**Summary**: 1-2 sentences describing what the PR does.

**Mandatory gates**: Duplicate — clear | overlap | duplicate · Strategic necessity — clear value | questionable | not justified. A failed gate is a blocker at **Important** severity.

**Risk level**: Low / Medium / High — based on scope, complexity, and breakage potential.

**Findings** by severity:
- **Critical**: must fix before merge (bug, security, data loss)
- **Important**: should fix (logic issue, missing validation, structural slop)
- **Suggestion**: nice-to-have (style, micro slop)

> Severity rule: structural slop -> Important; micro slop -> Suggestion.
> If you cannot articulate a **concrete cost** in this codebase -> do not flag.

**Verdict**:
- **Approve** — no Critical or Important findings
- **Request changes** — has Critical or Important findings
- **Comment** — Suggestions only, safe to merge

## Fix loop (`--fix`)

1. If no actionable findings -> stop, report **Approve**.
2. Fix findings using `hs:fix` with full context (PR ref, base/head branch,
   changed files, each finding: severity / file / line / expected / actual / why).
   Constraints: stay within PR scope, do not refactor outside scope, do not break the
   public contract unless the finding requires it.
3. Before committing, verify the worktree is still on the PR head: `git rev-parse HEAD`
   must match the `headRefOid` captured in step 1. If it diverged, re-fetch PR metadata and
   warn of concurrent changes — do not commit to the wrong branch.
   After `hs:fix` verifies -> use `hs:git` to commit and push to the PR head branch.
   Do not push if verification failed, secrets are present, or the working tree has
   unrelated changes.
4. Re-review: repeat from step 1 with `--fix` (and `--reply` if it was set initially).

Stop when:
- Re-review has no remaining actionable findings
- `hs:fix` is blocked by an open user/business decision
- The same finding survives 3 fix attempts (loop does not converge)
- CI fails in a way `hs:fix` cannot resolve without user input

Final `--fix` output: iteration count, final verdict, commits pushed, remaining
findings, blockers.

## Reply mode (`--reply`)

Posts the review to the PR. Load `references/reply-mode.md` for the full procedure: gh
pre-flight (falls back to printing locally if gh is absent/unauthenticated, never fails the
skill), body format + footer + 60k cap, the verdict→`gh pr review` flag map, the self-PR
422→`--comment` fallback, and `--fix --reply` (post the final re-review on convergence).

## Final output

- Verdict (Approve / Request changes / Comment)
- Iteration count if `--fix` ran
- Commits pushed if `--fix` ran
- `--reply` succeeded / fell back / printed-locally
- Remaining findings or blockers
- Open questions if any
