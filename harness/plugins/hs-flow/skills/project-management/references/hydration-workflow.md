# Hydration workflow — on-demand

Tasks (session-scoped) disappear when a session ends. Plan files are the persistent
layer. The hydration pattern connects these two layers across sessions.

## Flow

```
┌──────────────────┐  Hydrate   ┌───────────────────┐
│ Plan files       │ ─────────► │ Claude Tasks      │
│ (persistent)     │            │ (session-scoped)  │
│ [ ] Phase 1      │            │ ◼ pending         │
│ [ ] Phase 2      │            │ ◼ pending         │
└──────────────────┘            └───────────────────┘
                                        │ Work
                                        ▼
┌──────────────────┐  Sync-back ┌───────────────────┐
│ Plan files       │ ◄───────── │ Task Updates      │
│ (updated)        │            │ (completed)       │
│ [x] Phase 1      │            │ ✓ completed       │
│ [ ] Phase 2      │            │ ◼ in_progress     │
└──────────────────┘            └───────────────────┘
```

## Tool availability

`TaskCreate / TaskUpdate / TaskGet / TaskList` — CLI only; disabled in the VSCode
extension. If a tool errors, fall back to `TodoWrite` for progress tracking.
Plan files remain the source of truth; sync-back updates checkboxes regardless of
whether Task tools are available.

## Session start: Hydration

1. Read `plan.md` + `phase-XX-*.md`.
2. Identify remaining `[ ]` items — work not yet done.
3. `TaskCreate` each item with metadata:
   `{ phase, priority, effort, planDir, phaseFile }` —
   or use `TodoWrite` if Task tools are unavailable.
4. Use `addBlockedBy` to set up dependency chains between phases
   (skip if using `TodoWrite` fallback).
5. `[x]` items = already done; skip them.

**Pre-check**: `TaskList()` — if tasks already exist (same session), do not recreate them.

## While working

- `TaskUpdate(status: "in_progress")` when picking up a task.
- `TaskUpdate(status: "completed")` immediately after finishing.
- Parallel agents coordinate through the shared task list.
- Blocked tasks unblock automatically when their dependency completes.

## Session end: Sync-back

1. Collect completed tasks along with their metadata (`phase`, `phaseFile`, `planDir`).
2. Scan ALL `phase-XX-*.md` files in the target plan dir.
3. Reconcile and backfill: update `[ ]` to `[x]` in every phase file
   (including older phases that have become stale).
4. Update YAML frontmatter `plan.md`: `status` field.
5. Update progress % in `plan.md` overview from actual checkbox counts.
6. Report unresolved mappings if a task cannot be mapped to any phase file.
7. Git commit to finalize the state transition for the next session.

## Cross-session resume

When the user runs `/hs:cook path/to/plan.md` in a new session:
1. `TaskList()` — empty (tasks were lost with the old session).
2. Read plan files — re-hydrate from remaining `[ ]` items.
3. `[x]` = done — create tasks only for unfinished work.
4. Dependency chain rebuilds automatically.

## YAML frontmatter to sync

```yaml
---
title: Feature name
description: Short description
status: in-progress  # pending | in-progress | completed
priority: P1
effort: medium
branch: feature-branch
tags: [auth, api]
created: 2026-01-15
---
```

Update the `status` field during sync-back when the plan state changes.
