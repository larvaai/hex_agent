# Orchestration protocol (on-demand)

Load when spawning subagents or coordinating parallel work. Backing implementation
for skill `hs-flow:team`; matches the harness multi-agent primitives (`claims.py`,
`task_store.py`, `team_config.py`, `SendMessage` + Task*).

## Delegation context — required in every subagent prompt

task · files allowed to read · files allowed to modify · acceptance criteria ·
constraints · work-context path · reports path (default `plans/reports/`). Include
env (CWD, OS) when handing off work.

## Context isolation

- Do NOT pass the full conversation history; summarize ONLY the decisions needed for
  the subtask.
- Give exact file paths instead of "look around the repo" — unless scouting is the task.
- Keep coordination, merge decisions, and human approvals in the controller session.

## Parallel work — safety conditions

Only run in parallel when **file ownership is clear** and integration points are known.
Do not edit in parallel: the same file, a generated artifact, a migration sequence, or
shared config. Ownership is split 1-winner via `harness/scripts/claims.py`; shared task
list via `harness/scripts/task_store.py`; team config via
`harness/scripts/team_config.py`. Advisory subagents (report-only) do NOT mutate
plan/code unless explicitly assigned to do so.

## Status protocol

Require each subagent to end with:

```text
Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
Summary: 1-2 sentences
Concerns/Blockers: optional
```

`BLOCKED` / `NEEDS_CONTEXT` means change context, scope, or approach. Do NOT repeat
the same failing prompt unchanged. Multi-session or team work uses skill `hs-flow:team`
and communicates via `SendMessage`.
