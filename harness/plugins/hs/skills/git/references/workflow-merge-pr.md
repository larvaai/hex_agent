# Workflow — merge an open PR

`merge-pr` merges an already-open Pull Request on the remote, distinct from `merge`
(a local branch merge) and `pr` (which *creates* a PR). It wraps `gh pr merge`.

## Preconditions

- `gh` authenticated (`gh auth status`).
- The PR exists and is open. With no number, target the PR for the current branch.
- Required checks are green and required reviews approved — do not force a merge past a
  failing gate; if checks are red, STOP and report rather than overriding.

## Steps

1. Resolve the PR: `gh pr view [number] --json number,state,mergeable,reviewDecision,statusCheckRollup`.
2. Refuse to proceed when `state != OPEN`, `mergeable == CONFLICTING`, or checks are failing —
   report the blocker and let the user decide.
3. Merge with the requested strategy (default `--squash`):

   ```bash
   gh pr merge [number] --squash --delete-branch
   ```

   Use `--merge` or `--rebase` only when the user asks; keep `--delete-branch` unless told otherwise.
4. Confirm: `gh pr view [number] --json state,mergedAt` and report the merged SHA.

## Boundaries

- This is a remote-state operation; it is gated like other ship-class stages
  (`harness/hooks/gate_stage.py`). Satisfy the gate honestly — never edit gate config to pass.
- No force-merge past failing required checks. Surface the failure; the human decides.
