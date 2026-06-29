# Reporting patterns — on-demand

Used in `report` mode or after sync-back to generate progress reports.

## Report types

### 1. Session report — summary of the current session

```markdown
## Session Report: [Date]

### Completed
- [x] [task/feature description]

### In progress
- [ ] [description] — [% done, blocker if any]

### Tasks
- [N] tasks hydrated from [plan]
- [M] completed, [K] remaining

### Next session
1. [Priority item]
2. [Follow-up]
```

### 2. Plan completion report — when a plan finishes

```markdown
## Plan completed: [Plan name]

### Summary
- **Duration:** [start] → [end]
- **Phases:** [N] completed
- **Files changed:** [count]
- **Tests:** [pass/total]

### Delivered
- [Feature / capability delivered]

### Known limitations
- [Caveats or follow-up work]

### Docs updated
- [Which doc was updated]
```

### 3. Progress report — multi-plan overview

```markdown
## Project progress: [Date]

| Plan | Status | Progress | Priority | Next step |
|------|--------|---------|----------|-----------|
| [name] | [status] | [%] | P[N] | [action] |

### Highlights
- [Key milestone or achievement]

### Risks
- [Risk] — [Mitigation path]

### Blockers
- [Blocker] — [Resolution path]
```

## Report file naming

Pattern: `plans/reports/pm-{date}-{time}-{slug}.md`

Example: `plans/reports/pm-260615-0139-auth-progress.md`

Do not use generic names such as `report.md`, `status.md`, or `notes.md`.

## Report generation workflow

1. `TaskList()` — collect all task statuses.
2. Glob `plans/*/plan.md` — scan active plans.
3. Read phase files — count checkboxes.
4. Aggregate metrics into the template.
5. Write to `plans/reports/`.
6. Highlight: achievements, blockers, risks, next steps.

## Report writing principles

- Sacrifice grammar for brevity.
- Use tables instead of prose paragraphs.
- List unresolved questions at the end.
- Metrics over prose (numbers, %, tables).
- Skip obvious context; focus on actionable insights.

## Doc triggers — when to update docs

Delegate to `docs-manager` agent when any of the following changes occur:

| Trigger | Which doc |
|---|---|
| Phase status changes | `docs/project-roadmap.md` |
| Major feature completed | `docs/codebase-summary.md`, `docs/project-roadmap.md` |
| API contract changes | `docs/system-architecture.md`, `docs/code-standards.md` |
| Architecture decision | `docs/system-architecture.md` |
| Breaking changes | `docs/code-standards.md` |

Read `harness/rules/documentation-management.md` to determine when an update is
warranted before triggering — do not update for purely internal edits.

Project manager decides when; `docs-manager` handles how.
