---
name: hs:scout
description: Fast codebase exploration using parallel agents — find files, locate code, gather context before implementing or debugging. Output goes to plans/reports/.
category: core
license: AGPL-3.0
keywords: [scout, fast, codebase, exploration, using, parallel]
when_to_use: "Fast codebase exploration using parallel agents — find files, locate code, gather context before implementing or debugging."
argument-hint: "[ext]"
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob, Task]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs:scout — structured codebase exploration

Find files, patterns, and code relationships token-efficiently by splitting the
codebase and running agents in parallel. Result = scout report in `plans/reports/`.

## Modes / Flags

| Argument | When | Backing |
|---|---|---|
| _(default)_ | internal scouting with `Explore` subagents | `references/internal-scouting.md` |
| `ext` | external scouting with Gemini/OpenCode CLI | `references/external-scouting.md` |

No argument → analyze the prompt and choose the appropriate mode automatically.

## Workflow

### 1. Analyze the task
- Parse prompt: search target, extension, directory, pattern.
- Estimate SCALE (agents needed): small ≤3, medium 4-5, large ≥6.
- If SCALE ≤2: do not spawn subagents — use Grep/Glob directly (overhead not worth it).

### 2. Divide and conquer
- Partition the codebase by directory/pattern — no overlap.
- Each agent receives a distinct, clearly scoped assignment.

### 3. Register tasks (when SCALE ≥ 3)
- `TaskList` first — check for existing scout tasks and reuse if present.
- If none: `TaskCreate` per agent, mark `in_progress` before spawning.
- Schema detail: `references/task-management.md`.

### 4. Spawn agents in parallel
- **Internal (default):** `references/internal-scouting.md` (Explore subagents).
- **External (ext):** `references/external-scouting.md` (Gemini/OpenCode CLI).
- Send all spawns in a single message (1 message = true parallelism).
- 3-minute timeout per agent — drop unresponsive agents, do not retry.

### 5. Collect + report
- `TaskUpdate` each task: `completed` or `metadata.error: "timeout"`.
- Merge results, deduplicate paths, write scout report to `plans/reports/`.
- Return absolute path of the report + list of open questions.

## Report format

```markdown
# Scout Report — <target>

## Relevant files
- `/absolute/path/to/file.py` — short description

## Observed patterns

## Open questions
```

## Boundaries

- DO NOT edit code or create files outside `plans/reports/`.
- Scout output is input for `hs-research:research` (external), `hs:debug`, `hs:fix`,
  `hs:code-review` — scout does not make implementation decisions.
- The `ext` flag requires Gemini/OpenCode to be installed; if missing → fall back to
  internal automatically and record `[FALLBACK_INTERNAL]` in the report.
- Large context budget (SCALE ≥ 6): check `hs-meta:context-engineering` before spawning.
- To pack the full repo before scouting: use `hs-research:repomix` (outputs one XML file for the LLM).

## HARD-GATE (real wiring)

- Reports must exist only inside `plans/reports/` — CLAUDE.md rule #5. Creating markdown
  outside this directory violates the CI invariant.
- Scout does not approve or implement anything — all next steps require a human or
  another skill that takes the scout report as input.
