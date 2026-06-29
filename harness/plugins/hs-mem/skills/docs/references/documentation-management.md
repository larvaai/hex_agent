# Documentation update decision

Load this file when another skill/workflow needs to decide whether to update docs.
To run the full docs flow, use `/hs-mem:docs init`, `/hs-mem:docs update`, or `/hs-mem:docs summarize`.

## When to update

Update docs when a change affects:

- user-visible behavior
- setup, install, or CLI commands
- architecture, data flow, or public contract
- security posture or operational procedures
- future decisions that a maintainer should not have to rediscover

Do **not** add noise for purely internal changes unless the repo has its own rule requiring it.

## Standard docs for this repo

| File | Purpose |
|---|---|
| `docs/codebase-summary.md` | codebase overview, entry point |
| `docs/system-architecture.md` | architecture, data flow, components |
| `docs/code-standards.md` | code standards, naming, patterns |
| `docs/project-roadmap.md` or `docs/development-roadmap.md` | roadmap |
| `docs/project-changelog.md` | changelog when present |

## Plan and report locations

- Plans: `plans/<timestamp>-<slug>/plan.md` + phase files
- Reports: `plans/reports/` (or `plans/<slug>/reports/`)
- Hard constraint: markdown is created **only** in `docs/` or `plans/` (CLAUDE.md rule #5)

## Handoff with other skills

- `hs:cook` / `hs:fix`: call docs update at finalize time only when the criteria above are met.
- `hs:plan`: read existing docs before creating architecture plans or phase files.

Read the existing doc BEFORE modifying it. After modifying: verify that dates, links, and claims match actual changes.
