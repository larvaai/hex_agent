---
name: hs:understand
description: Orchestrate codebase comprehension before touching code — chain hs-research:repomix, hs:scout, hs-meta:context-engineering to build a codebase map. Use before hs:plan on unfamiliar areas.
category: core
license: AGPL-3.0
keywords: [understand, orchestrate, codebase, comprehension, before, touching]
when_to_use: "Use before hs:plan on unfamiliar areas."
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob, Task]
metadata:
  owner: harness
  compliance-tier: workflow
argument-hint: "[path-or-subtree] [--persist] [--budget <token-limit>]"
---

# hs:understand — comprehend a codebase before touching it

Orchestrator READ-ONLY: explore a codebase or subsystem, synthesize a
**codebase map** (markdown), and hand off to hs:plan or hs:triage.
Does not write code, does not create a plan, does not commit.

## Execution steps

1. **Determine scope** — accept path/subtree from the argument or ask via
   `AskUserQuestion`; if missing, ask first, do not guess.

2. **Pack snapshot** — call `hs-research:repomix` with the confirmed scope:
   `--style markdown`, output to `harness/state/` (do not commit).
   Estimate tokens first — if the budget is tight, narrow scope or use
   `--remove-comments`. Details: `references/chain-orchestration.md`.

3. **Scout file-key** — call `hs:scout` in parallel if the codebase is large
   enough (SCALE >= 3); for smaller codebases use Grep/Glob directly (avoid
   overhead). Output -> `plans/reports/`.
   Backing: `harness/rules/orchestration-protocol.md`.

4. **Budget check** — call `hs-meta:context-engineering` to estimate the tokens
   needed for loading; apply Select/Compress/Isolate strategy before
   synthesizing.

5. **Synthesize map** — write the codebase map following the template in
   `references/map-template.md`: module/layer, file-key + responsibility,
   data/control flow, external boundaries, task entry points, unknowns.
   Save to `plans/reports/` (default) or `docs/` when `--persist`.

6. **Persist (optional)** — when `--persist` is passed: call `hs-mem:docs` to
   update or initialize a long-lived doc (e.g. `docs/codebase-summary.md`).
   Only persist when the map is genuinely a long-lived document; temporary
   maps go to `plans/reports/`, not `docs/`.
   Backing: `harness/rules/documentation-management.md`.

7. **Hand off** — return the absolute path of the map, token count, and list
   of open unknowns. Handoff -> hs:plan (the map is comprehension input, not
   a plan). Backing: `harness/rules/workflow-handoffs.md`
   §Orchestrator (understand->plan/triage).

## Backing

| Mechanism | File/rule |
|---|---|
| Output path (docs/ or plans/) | `harness/rules/documentation-management.md` |
| Handoff understand -> hs:plan/hs:triage | `harness/rules/workflow-handoffs.md` |
| Fan-out scout agents | `harness/rules/orchestration-protocol.md` |
| Component skills | hs-research:repomix, hs:scout, hs-meta:context-engineering, hs-mem:docs |

## Boundaries

- READ-ONLY: do NOT edit code, do NOT generate a plan, do NOT commit, do NOT gate.
- Ownership: do not read project zones marked restricted
  (`harness/data/ownership.yaml` when present).
- Out-of-scope findings -> `BACKLOG.md`; do not include in the map.
- Map must reside in `plans/reports/` or `docs/`
  (CLAUDE.md rule #5; `harness/rules/documentation-management.md`).
- Finish: absolute path of the map + token count + list of open unknowns.

## References (load when needed)

| Drawer | Content | When to load |
|---|---|---|
| `references/map-template.md` | Codebase map template, required sections | When starting synthesis |
| `references/chain-orchestration.md` | Details of calling hs-research:repomix/scout/context-engineering | When coordinating the chain |
