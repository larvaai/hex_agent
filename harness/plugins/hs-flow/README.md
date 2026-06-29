<!-- generated: plugin-readme -->

# hs-flow

SDLC harness — điều phối / tự động hoá / chạy song song (hs-flow:loop / afk / autonomous-bell / team / worktree / compound / project-management / plans-kanban). Sibling của plugin hs (spine).

**Default:** opt-in. Enable with `hs-cli components --enable flow` (or choose it at install time).
**Version:** 2.0.0

## Skills (8)

| Invoke | Purpose |
|---|---|
| `/hs-flow:afk` | Run a plan/PRD in unattended (AFK) mode — preflight readiness, then route to Ralph sandbox or native fallback; loop commits freely in the m… |
| `/hs-flow:autonomous-bell` | Use when starting an unattended /goal or AFK loop that should end itself. |
| `/hs-flow:compound` | Compound the harness's own self-knowledge — telemetry lenses + skill-formalization candidates + open backlog + a completeness critic — into… |
| `/hs-flow:loop` | In-session self-optimization loop — N iterations against a measurable metric, learns from git history, auto-keep/discard changes. |
| `/hs-flow:plans-kanban` | View a file-based kanban board for all plans in plans/ — grouped by status (pending / in-progress / completed), navigate into a plan, check… |
| `/hs-flow:project-management` | Track plan progress, update task status, manage tasks, generate reports, coordinate docs updates. |
| `/hs-flow:team` | Orchestrate parallel Agent Teams — research, cook, review, debug with multiple independent teammates. |
| `/hs-flow:worktree` | Create, inspect, and clean up isolated git worktrees. |

Each skill's full contract lives in its `SKILL.md`; load-on-demand detail lives under the skill's `references/`. This index is generated — regenerate with `harness/scripts/generate_plugin_readme.py`.
