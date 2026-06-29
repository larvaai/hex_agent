# Phase decomposition — phase design and plan.md (on-demand)

Runs AFTER research, WHEN the planner writes plan.md + phase files. This is the
correct technique for decomposing phases so cook can execute them — not a
descriptive outline.

## Plan directory structure

```
plans/<timestamp>-<slug>/
├── research/          # researcher reports (path passed to planner)
├── reports/           # red-team / validate reports
├── plan.md            # overview, required YAML frontmatter
├── phase-01-<name>.md
└── phase-0N-<name>.md
```

Slug name: kebab-case, describing scope (e.g. `260615-1200-auth-refactor`).

Stamp this skeleton deterministically instead of hand-typing it:
`python3 harness/scripts/scaffold.py plan --slug <slug> --title "<title>" --phases a,b,c`
creates the dir, plan.md, and one phase file each — already carrying the correct
`harness_version`/`kit_digest`/`schema_version` stamp (reused from `artifact_stamp`, so a new
plan never ships a stale digest). Then fill the TBD sections with the real decomposition below;
`scaffold.py report --type <t> --slug <slug> --title "<title>"` does the same for a report.

## Required YAML frontmatter for plan.md

```yaml
---
title: "<concise>"
description: "<1 sentence for card preview>"
status: pending
priority: P2          # P1 | P2 | P3
effort: "<total estimate>"
branch: "<current git branch>"
tags: [relevant, tags]
created: <YYYY-MM-DD>
---
```

## Each phase file must contain

- **Overview** — 1-2 sentence deliverable.
- **Requirements** — explicit functional + non-functional.
- **Related Code Files** — Create / Modify / Delete with full paths.
- **Implementation Steps** — numbered, specific enough for another developer to execute.
- **Success Criteria** — measurable checkboxes (not subjective).
- **Risk Assessment** — likelihood x impact; mitigation for High items.

## Decomposition rules

1. **Each phase is self-contained**: no runtime dependency on a parallel phase.
2. **File ownership**: each file belongs to only one phase — overlap is a conflict.
3. **>8 files in one phase**: challenge -> split or merge (YAGNI).
4. **>3 phases**: ask the user "can any phases be merged?" before committing the
   structure.
5. **Naming honesty / SRP** (the Maintainer red-team persona will check): new
   file/module names must accurately and completely describe their real
   responsibility — `core.py` that also handles artifact I/O is a misleading name
   and needs splitting.

## Parallel mode — additional requirements

With `--parallel`: add a **dependency matrix** to plan.md (which phases run
concurrently, which are sequential) and a **file ownership table** (phase -> files).
Cook reads the matrix to spawn agents in parallel without conflicts.

## Deep mode (`--deep`) — per-phase scout

Each phase file in `--deep` must include:
- File inventory table (action, rough size, test impact).
- Test scenario matrix (critical / high / medium paths).
- Dependency map (links to phases this one depends on).

## Backing

- `harness/plugins/hs/agents/planner.md` — agent that writes plans using this template.
- `harness/rules/workflow-handoffs.md` — handoff structure plan -> cook.
- `harness/data/ownership.yaml` — confirm zone before placing a path (-> constraint-scan.md).
- `harness/scripts/plan_approval.py` — record approval after the user approves the plan.
