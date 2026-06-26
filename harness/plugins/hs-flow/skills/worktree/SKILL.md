---
name: hs-flow:worktree
description: "Create, inspect, and clean up isolated git worktrees. Use for feature isolation, worktree health audits, and stale metadata cleanup."
category: flow
license: AGPL-3.0
keywords: [worktree, create, inspect, clean, isolated, git]
user-invocable: true
when_to_use: "Invoke when an isolated worktree needs to be created, listed/checked, or stale worktrees need pruning."
argument-hint: "create <feature> | list | status | remove <name> | prune [--dry-run]"
allowed-tools: [Bash, Read, Glob]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-flow:worktree — isolated git worktrees

Manage git worktrees using the native `git worktree` CLI — no script wrapper needed.
Use to run two branches in parallel without affecting each other (isolated dev).

## Command table

| Command | Description |
|---------|-------------|
| `create <feature>` | Create a new worktree on a new branch |
| `list` | List all worktrees |
| `status` | Check health and divergence from the base branch |
| `remove <name>` | Delete a worktree (clean up metadata) |
| `prune [--dry-run]` | Clean up stale metadata (`--dry-run` to preview) |

## Worktree creation procedure

### Step 1 — Identify base branch + slug

```bash
git symbolic-ref --short HEAD          # current branch
git branch -r | grep -E 'main|master|dev'  # find base if unclear
```

Prefix from description:
- "fix / bug / error" → `fix`
- "refactor / restructure" → `refactor`
- "docs / documentation" → `docs`
- "test / spec" → `test`
- "chore / cleanup / deps" → `chore`
- anything else → `feat`

Slug: convert to kebab-case, max 50 characters.
Final branch name: `<prefix>/<slug>` (example: `feat/add-auth`).

If the user provides a full branch name (contains `/`, uppercase, ticket key like `ABC-1234`)
→ use it as-is, do not add a prefix.

### Step 2 — Create the worktree

```bash
# Worktree in a sibling directory (avoid nesting inside the current repo)
git worktree add "../<repo>-<slug>" -b "<branch>" <base-branch>
```

If the user specifies `--base <branch>` → override the base-branch.

### Step 3 — Install dependencies (if needed)

Run in the background inside the new worktree:

| Lock file | Command |
|-----------|---------|
| `poetry.lock` | `poetry install` |
| `requirements.txt` | `pip install -r requirements.txt` |
| `pyproject.toml` (no poetry.lock) | `pip install -e .` |

### Step 4 — Confirm + remove / clean up

```bash
git worktree list                         # confirm creation succeeded
git worktree remove <path>                # clean removal (fails if dirty)
git worktree remove --force <path>        # only when user confirms discarding uncommitted changes
git worktree prune --dry-run && git worktree prune  # clean stale metadata
```

Report: absolute path + branch name.

## Output

```
✓ worktree: /absolute/path/to/<slug>  (branch: feat/<slug>)
✓ base: main (auto-detected)
✓ list: 2 worktrees
```

## Error handling

| Error | Action |
|-------|--------|
| Branch already exists | Ask user: reuse existing branch or use a different name |
| Path conflict | Suggest an alternative path |
| `remove` on dirty worktree | Warn about uncommitted changes — require user confirmation before `--force` |
| Not a git repository | Stop + guide to `git init` or check cwd |

## HARD-GATE (real wiring)

No dedicated harness gate for worktrees — `git worktree` is the native CLI.
Pushes from inside the worktree go through the **pre-push hook** `harness/install/git-pre-push-hook.sh`
exactly as in the main checkout: calls `artifact_check.check_stage("push", root)` —
missing artifact → exit 2, push blocked. Do not bypass the hook to pass the gate.

## Boundaries

- Do NOT delete a worktree containing uncommitted changes without asking the user first.
- Do NOT create a worktree nested inside the repo's `.git/` directory.
- Do NOT push from a worktree if the push gate has not passed — see `hs:git` for commit/push.
- YAGNI applies: do not initialize submodules, remotes, or new config outside the request scope.
- When commit/push inside the worktree is needed → invoke `hs:git`.

## References

| Topic | Reference |
|-------|-----------|
| Worktree lifecycle | `references/lifecycle.md` |
| Parallel isolation rules | `references/isolation-rules.md` |
| Git ops inside a worktree | `hs:git` |
