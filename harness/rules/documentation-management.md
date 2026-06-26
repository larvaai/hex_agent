# Documentation management (on-demand)

Load when creating a plan or changing project documentation. Matches the repo's
markdown-location hard constraint (CLAUDE.md rule 5) + the `docs-manager` agent
(owner of doc write operations).

## When to update docs

Update only when a change touches: user-visible behavior, setup, commands,
architecture, security posture, public contracts, or decisions for future
maintainers. Do NOT add changelog-noise for purely internal edits unless the
repo already requires it.

Common docs: `docs/code-standards.md`, `docs/system-architecture.md`,
`docs/codebase-summary.md`, `docs/project-roadmap.md` (when present).

## Markdown location -- hard constraint

Markdown ONLY created in `docs/` or `plans/` (root README/CLAUDE/BACKLOG are
explicitly approved). Creating outside those two directories is a violation.
No hook enforces this location rule — it is a convention checked in review
(CLAUDE.md rule 5). The `docs-manager` agent only edits files in `docs/` (does
not mutate code).

## Plan location

Save plans under `plans/<timestamp>-<descriptive-slug>/`:

```text
plans/<slug>/
  plan.md            # short: status, phases, dependencies, acceptance, phase links
  phase-01-<name>.md # enough detail to execute safely (see below)
  reports/
```

Phase files contain only: context links, requirements, files to create/edit/delete,
execution steps, tests/validation, risks + rollback.

## Procedure

1. **Read the current doc FIRST** before editing -- do not overwrite blindly.
2. After editing: verify **dates, links, and claims** match the actual change.
3. Check size: `wc -l docs/*.md | sort -rn` -- split off a reference file when one grows large.
4. Follow-up items from a review go into `BACKLOG.md`, not a separate review file.
