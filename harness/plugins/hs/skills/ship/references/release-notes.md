# Release Notes — hs:ship

Guide for generating PR body content and changelog entries.
Do not ask the user for content — everything is inferred from diff + commit log.

## Data sources

```bash
# Commit log since the branch diverged
git log origin/<target>..HEAD --oneline

# Full diff to classify and infer context
git diff origin/<target>...HEAD

# Diff stats for the "Changes" section
git diff origin/<target>...HEAD --stat
```

## Commit classification

| Commit prefix | PR body section |
|---------------|-------------|
| `feat:` | Added |
| `fix:` | Fixed |
| `refactor:` / `perf:` | Changed |
| `chore:` / `build:` / `ci:` | (omit or merge into Changed) |
| `docs:` | Documentation |
| `test:` | (omit from user-facing notes) |
| `revert:` | Removed |

If a commit has no conventional prefix → infer from diff content:
- New file → Added
- Deleted file → Removed
- Logic change → Changed

## PR body template

```markdown
## Summary
- <bullet 1 — inferred from commit/diff>
- <bullet 2>
- <bullet N>

## Pre-Landing Review
<verdict: PASS | PASS_WITH_RISK> (<N> critical, <M> informational)
<if informational findings exist, list: - [file:line] description>
<if clean: "No issues found.">

## Test Results
- [x] All tests pass (<N> tests, 0 failures)
<or>
- [x] Tests skipped (--skip-tests)

## Changes
<output of git diff --stat, trimmed if > 20 files — keep the important files>

## Ship Mode
- Mode: official | beta
- Target: <target-branch>
```

**Keep summary bullets short** — one line per change.
**Do not invent test numbers** — use actual output from `hs:test`.

## Changelog entry (if CHANGELOG.md exists)

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- <feat commits>

### Changed
- <refactor/perf commits>

### Fixed
- <fix commits>

### Removed
- <revert / delete commits>
```

Insert the new entry immediately after the file header, before the oldest existing entry.
Date format: `YYYY-MM-DD` using the actual ship date (`date +%Y-%m-%d`).

## PR title

```
type(scope): short description (≤ 70 characters)
```

Infer `type` from the commit majority:
- Mostly `feat:` → `feat`
- Mostly `fix:` → `fix`
- Mixed → type of the most significant commit (by diff size)

`scope` = the module/area most affected (inferred from changed file paths).

## Example

Commit log:
```
feat(gate): add plan-approval artifact check
fix(hook): correct exit code on missing python3
test(e2e): prove gate blocks without approval
```

PR title: `feat(gate): add plan-approval artifact check`

PR summary bullets:
```
- Add plan-approval artifact check before push/pr/ship
- Fix hook exit code when python3 is not found
```

Changelog entry:
```markdown
## [0.4.1] - 2026-06-15

### Added
- Plan-approval artifact check in gate_stage.py

### Fixed
- Hook exit code when python3 is not found
```
