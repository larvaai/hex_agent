---
name: hs-create:bootstrap
description: Bootstrap a new project from scratch -- clarify requirements, init git, create doc structure, delegate to hs:plan + hs:cook. Use when starting a new repo or resetting a project's SDLC foundation.
category: create
license: AGPL-3.0
keywords: [bootstrap, new, project, scratch, clarify, requirements]
when_to_use: "Use when starting a new repo or resetting a project's SDLC foundation."
argument-hint: "[--full|--fast|--auto] [requirements]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, Task]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-create:bootstrap -- project bootstrap

Orchestrate the full new-project initialization flow: git init, clarify requirements,
create doc structure, then delegate to `hs:plan` and `hs:cook`.

**Does not write code directly.** All implementation goes through plan + cook.

## Modes

| Flag | When | User gate |
|---|---|---|
| (none) -> `--full` | Fully interactive | After each major phase |
| `--fast` | Skip long clarify, run quickly | After research synthesis |
| `--auto` | Autonomous (explicit opt-in) | Only at the final step |

## Workflow

### Step 0: Git init (all modes)

Check whether git is already initialized. If not:
- `--full`: ask the user first, then `git-manager` agent inits the `main` branch.
- Other modes: auto-init via `git-manager` agent.

### Step 1: Clarify requirements (`--full` / `--fast`)

Load `references/clarify.md`.

`--auto`: skip gate, synthesize requirements from input directly.

### Step 2: Quick research (optional)

Use `researcher` agent (<=5 sources) when technology or feasibility is unclear.
Report <=150 lines, saved to `plans/reports/`.

Gate `--full`: present results, wait for approval. `--fast`/`--auto`: continue automatically.

### Step 3: Create doc structure

`docs-manager` agent creates the minimal skeleton (only missing files):

- `docs/codebase-summary.md`
- `docs/code-standards.md`
- `docs/system-architecture.md`

`project-manager` agent creates:

- `docs/project-roadmap.md`

Do not overwrite existing files -- only create what is missing.

### Step 4: Planning -> implementation

Activate `hs:plan`:
- `--full` -> `/hs:plan <requirements>`
- `--fast` -> `/hs:plan --fast <requirements>`
- `--auto` -> `/hs:plan --auto <requirements>`

Plan returns an absolute path. Gate `--full`: wait for user to approve the plan before
continuing.

After the plan is approved, activate `hs:cook <plan-path>` (matching mode).

### Step 5: Completion report

Load `references/final-report.md`. After cook finishes:

1. Summarize changes
2. Onboarding guide (getting-started instructions)
3. Ask about commit/push -> `git-manager` agent if agreed
4. Call `hs-mem:journal` to record the session

## Boundaries

- Do NOT write code directly -- delegate through plan + cook.
- Do NOT choose a specific stack (framework, language) autonomously -- ask or write into requirements so that plan decides.
- New markdown files are only created in `docs/` or `plans/` (harness rule).
- `--auto` is only used when the user explicitly requests it.

## Cross-references

- `hs:plan` -- generate a plan from requirements
- `hs:cook` -- implement according to the plan
- `hs-mem:docs` -- deepen documentation if needed after bootstrap
- `hs-flow:project-management` -- track progress after launch
- `hs-mem:journal` -- record the session when done
