---
name: code_review
description: Review a change for correctness, risks, and missing tests; read-only.
triggers: [review, diff, pull request, pr]
---

## Allowed (tools)
- fs_read
- fs_list

## Forbidden (tools)
- fs_write
- terminal_run

## Steps
1. List the changed files and read each one.
2. Check correctness against the stated intent; flag risky edits.
3. Verify tests exist for the changed behaviour.

## Report
- summary: one-line verdict (approve / request changes).
- findings: list of `file:line` issues with severity.
