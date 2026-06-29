---
name: hs-flow:plans-kanban
description: View a file-based kanban board for all plans in plans/ — grouped by status (pending / in-progress / completed), navigate into a plan, check progress. Use for a quick work-status snapshot.
category: flow
license: AGPL-3.0
keywords: [plans-kanban, view, file-based, kanban, board, plans]
when_to_use: "Use for a quick work-status snapshot."
argument-hint: "[--active | --done | --plan <slug> | --filter <tag>]"
user-invocable: true
allowed-tools: [Bash, Read, Glob, Grep]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-flow:plans-kanban — file-based plan kanban board

Reads the YAML frontmatter `status` from every `plans/<ts>-<slug>/plan.md` and
renders a kanban board directly in the CLI. No server or browser required.

**Cross-ref**: use `hs-flow:project-management` when you need to update status, sync tasks,
or generate detailed reports — `hs-flow:plans-kanban` is read-only navigation, it does not write.

## Modes / arguments

| Argument | Effect |
|---|---|
| (empty) | Show full board: 3 columns, all plans |
| `--active` | Only the `in-progress` + `awaiting_human_approval` column |
| `--done` | Only the `completed` column |
| `--plan <slug>` | Show detail for one plan: title, phases, % done |
| `--filter <tag>` | Filter by tag in frontmatter `tags:` |

## Workflow

1. **Scan** — `find plans/ -name "plan.md" -not -path "*/reports/*"` (exclude
   `plans/reports/` and `plans/templates/`).
2. **Parse frontmatter** — read the `---...---` YAML block at the top of each file; extract:
   `title`, `status`, `priority`, `tags`, `created`, `branch`.
3. **Group by status**:

   | Column | Status value |
   |---|---|
   | TODO | `pending` |
   | IN PROGRESS | `in-progress`, `in_progress`, `awaiting_human_approval`, `implemented` |
   | DONE | `completed` |
   | OTHER | any other value (displayed as-is, with a warning) |

4. **Render board** — print a 3-column table (markdown table or compact list
   depending on width), one row per plan: `priority | slug | title | branch | created`.
5. **Navigate** — print the absolute path to `plan.md` for every plan that is
   IN PROGRESS; prompt the user to open it or invoke `hs-flow:project-management status`.
6. **Warn** — a plan missing frontmatter or `status` → warn clearly with the file name;
   do not crash the board.

## Boundaries

- **READ-ONLY** — do not modify any file in `plans/`.
- Do not create markdown outside `plans/` or `docs/` (CLAUDE.md rule #5 — not
  applicable here because this skill does not create files).
- Do not write tasks, mark done, or sync — that is the responsibility of
  `hs-flow:project-management`.
- Source of truth for status is the local `plan.md` file, not a remote task provider
  (`harness/scripts/task_store.py` is advisory-only for task tracking).
- End with: board printed + list of absolute paths for active plans.

## Actual backing (wiring)

This skill reads files — it has no dedicated hard gate. However:
- `plans/*/plan.md` YAML frontmatter `status` is the sole data source.
- `harness/hooks/gate_stage.py` still blocks the `push|pr|ship|deploy` stage
  independently of this skill — the kanban view does not bypass the gate.
- To update status: use `hs-flow:project-management sync` and then re-run
  `hs-flow:plans-kanban` to see the updated board.

## Example output (compact)

```
TODO (1)
  P2 | 260615-1430-search-filter | add search filter | main

IN PROGRESS (2)
  P1 | 260614-0900-auth-refresh | refresh login token | feature/auth-refresh
  P1 | 260613-1100-cache-layer  | query cache layer   | main

DONE (2)
  P1 | 260612-1600-payment-webhook | payment webhook | main
  P1 | 260611-1400-onboarding-flow | onboarding flow | main
```
