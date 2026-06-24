---
name: file_edit
description: Make a small, scoped edit to a workspace file and confirm the result.
triggers: [edit, write, patch, fix]
---

## Allowed (tools)
- fs_read
- fs_write
- fs_list

## Forbidden (tools)
- terminal_run

## Steps
1. Read the target file to anchor the exact text to change.
2. Apply the minimal edit; do not reformat unrelated lines.
3. Re-read the region to confirm the change landed.

## Report
- summary: what changed and why.
- file: the path edited.
