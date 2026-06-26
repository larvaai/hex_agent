---
name: hs-flow:team
description: "Orchestrate parallel Agent Teams — research, cook, review, debug with multiple independent teammates."
category: flow
license: AGPL-3.0
keywords: [team, orchestrate, parallel, agent, teams, research]
when_to_use: "Orchestrate parallel Agent Teams — research, cook, review, debug with multiple independent teammates."
user-invocable: true
argument-hint: "<template> <context> [--devs|--researchers|--reviewers N] [--delegate]"
allowed-tools: [Bash, Read, Write, Glob, Grep, Task]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-flow:team — Agent Teams orchestration

Run multiple independent Claude Code sessions. Each teammate has its own context
window, reads the project CLAUDE.md + skills, and coordinates through a shared
task list and messaging.

**Requirement:** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in settings.json env.
**Requirement:** CLI terminal — `TaskCreate`/`TaskUpdate`/`TaskGet`/`TaskList` and
`TeamCreate`/`TeamDelete` are disabled in the VSCode extension.
**Model:** All teammates must run the Opus model (hard constraint of Agent Teams).

## Syntax

```
/hs-flow:team <template> <context> [flags]
```

**Templates:** `research`, `cook`, `review`, `debug`

| Flag | Meaning |
|---|---|
| `--devs N` / `--researchers N` / `--reviewers N` / `--debuggers N` | team size |
| `--plan-approval` / `--no-plan-approval` | plan approval gate (default: on for cook) |
| `--delegate` | lead coordinates only, does not touch code |
| `--worktree` | git worktree isolation for devs (default: on for cook) |

## Pre-flight (REQUIRED — embedded in step 2 of each template)

1. Step 2 of every template calls `TeamCreate(team_name: "...")`.
2. If SUCCESSFUL: continue with the template.
3. If ERROR or unrecognized: **STOP. Inform user:** "Agent Teams requires
   `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in settings.json."
4. DO NOT fall back to plain subagents. `hs-flow:team` must use Agent Teams or cancel.

When activated, IMMEDIATELY execute the matching template below.
No confirmation, no explanation. Call tools in order. Report progress after each major step.

## Quick tool reference

Team tools: `TeamCreate` · `TeamDelete` · `TaskCreate` · `TaskUpdate` · `TaskGet` · `TaskList` · `SendMessage`.

SendMessage types: `message` (DM — requires `recipient`) · `broadcast` (use sparingly) ·
`shutdown_request` · `shutdown_response` (requires `request_id`) · `plan_approval_response` (requires `request_id`).

Spawn teammate: `Agent(subagent_type: "…", model: "opus", run_in_background: true, isolation: "worktree")`.

## Harness Context Block (inject into every teammate prompt)

```
Harness Context: work dir={CWD} · reports=plans/reports/ · plans=plans/ · branch={current}
Commits: conventional. Address teammates by NAME. Read first:
  harness/plugins/hs-flow/skills/team/references/roles-and-ownership.md
  harness/plugins/hs-flow/skills/team/references/messaging-protocol.md
```

---

## ON `/hs-flow:team research <topic>` [--researchers N]

*Wraps hs-research:research — scope, gather, analyze, report.*

1. Derive N angles from `<topic>` (N defaults to 3): (1) Architecture/patterns; (2) Alternatives/trade-offs; (3) Risks/failure modes. If N>3, derive additional angles from the topic.
2. **CALL** `TeamCreate(team_name: "<topic-slug>")`
3. **CALL** `TaskCreate` x N — one per angle: Subject `Research: <angle>`; description: investigate + save report to `plans/reports/researcher-{N}-{slug}.md` + notify lead when done.
4. **SPAWN** x N researchers: `subagent_type: "researcher"`, `model: "opus"`, `run_in_background: true`, name `researcher-{N}`.
5. **MONITOR** TaskList after 60s or when a teammate signals completion. If stuck > 5 minutes, message directly.
6. **READ** all reports from `plans/reports/`.
7. **SYNTHESIZE** → `plans/reports/research-summary-{slug}.md` (exec summary, findings, recommendations, open questions).
8. **SHUTDOWN** `SendMessage(type: "shutdown_request")` to each teammate.
9. **CLEANUP** `TeamDelete`.
10. **REPORT** to user: `Research done. Summary: {path}. {N} reports.`

---

## ON `/hs-flow:team cook <plan-path|description>` [--devs N]

*Wraps hs:cook — plan, code, test, review, finalize.*

1. **READ** the plan (if a path is given) OR spawn `Agent(subagent_type: "planner")` to create a plan first. Divide tasks into N independent groups with clear file ownership.
2. **CALL** `TeamCreate(team_name: "<feature-slug>")`
3. **CALL** `TaskCreate` x (N devs + 1 tester): dev tasks record `File ownership: <glob>`; tester task uses `addBlockedBy` on all dev task IDs.
4. **SPAWN** N devs: `subagent_type: "developer"`, `model: "opus"`, `isolation: "worktree"`, `run_in_background: true`, name `dev-{N}`. With `--plan-approval`: devs plan first, wait for approval via `plan_approval_response`.
5. **MONITOR** TaskList until dev tasks complete → spawn tester: `Agent(subagent_type: "tester", model: "opus", name: "tester")`.
6. **MERGE** worktree branches: `git merge <dev-branch> --no-ff` sequentially. Conflict → resolve manually → `git merge --continue`. Clean up with `git worktree remove <path>`.
7. **DOCS EVAL** (required with cook): `Docs impact: [none|minor|major]` / `Action: [no update|updated <page>|separate PR]`.
8. **SHUTDOWN** → **CLEANUP** `TeamDelete`.
9. **REPORT** to user: what was cooked, test results, docs impact.

---

## ON `/hs-flow:team review <scope>` [--reviewers N]

*Wraps hs:code-review — scout, review, synthesize with evidence gates.*

1. Derive N focus areas (N=3): Security, Performance, Test coverage. If N>3, add: architecture, DX, accessibility.
2. **CALL** `TeamCreate(team_name: "review-<scope-slug>")`
3. **CALL** `TaskCreate` x N: one task per focus; findings format `[CRITICAL|IMPORTANT|MODERATE] <finding> — <evidence> — <recommendation>`; save to `plans/reports/reviewer-{N}-{slug}.md`.
4. **SPAWN** x N: `subagent_type: "code-reviewer"`, `model: "opus"`, `run_in_background: true`.
5. **MONITOR** TaskList after 60s or when a reviewer signals completion.
6. **SYNTHESIZE** → `plans/reports/review-{scope-slug}.md` — deduplicate, rank by severity, create action items.
7. **SHUTDOWN** → **CLEANUP** `TeamDelete`.
8. **REPORT** `Review done. {X} findings ({Y} critical). Report: {path}.`

---

## ON `/hs-flow:team debug <issue>` [--debuggers N]

*Wraps hs:debug — root-cause-first, adversarial hypotheses, convergence.*

1. Generate N independent hypotheses from `<issue>` (N=3): each hypothesis is independently testable and predicts different symptoms.
2. **CALL** `TeamCreate(team_name: "debug-<issue-slug>")`
3. **CALL** `TaskCreate` x N: one task per hypothesis; require ADVERSARIAL mode — actively refute other hypotheses; save to `plans/reports/debugger-{N}-{slug}.md`.
4. **SPAWN** x N: `subagent_type: "debugger"`, `model: "opus"`, `run_in_background: true`. Let debuggers message each other to converge.
5. **MONITOR** TaskList + messages. Stuck > 5 minutes → intervene.
6. **READ** all reports, identify the surviving hypothesis as root cause.
7. **WRITE** `plans/reports/debug-{issue-slug}.md`: root cause, evidence chain, eliminated hypotheses, proposed fix.
8. **SHUTDOWN** → **CLEANUP** `TeamDelete`.
9. **REPORT** `Debug done. Root cause: <summary>. Report: {path}.`

---

## Boundaries

- `hs-flow:team` requires Agent Teams — do not fall back to plain subagents.
- File ownership decisions: `references/roles-and-ownership.md`.
- Messaging + task claiming: `references/messaging-protocol.md`.
- Shutdown + cleanup: `references/lifecycle-and-shutdown.md`.
- Reviewer roster and lease claim: `harness/data/team.yaml` (loader: `harness/scripts/team_config.py`).
- Race-free task ownership: `harness/scripts/claims.py` (acquire → release → reclaim; audit trail → trace_log).
- Remote task noticeboard (optional): `harness/scripts/task_store.py` (read+comment only; gate path always network-free).

## References (load-on-demand)

| Drawer | Contents |
|---|---|
| `references/roles-and-ownership.md` | File ownership, git safety, conflict resolution |
| `references/messaging-protocol.md` | Task claiming, SendMessage types, plan approval flow |
| `references/lifecycle-and-shutdown.md` | Shutdown protocol, idle state, TeamDelete, error recovery |
