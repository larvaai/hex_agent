---
name: hs-mem:docs
description: Analyze codebase and manage project documentation — init, update, summarize. Use when docs need to be created, refreshed, or audited.
category: mem
license: AGPL-3.0
keywords: [docs, analyze, codebase, manage, project, documentation]
when_to_use: "Use when docs need to be created, refreshed, or audited."
argument-hint: "[init | update | summarize]"
user-invocable: true
allowed-tools: [Bash, Read, Glob, Grep, Task]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-mem:docs — project documentation management

Analyzes the codebase and creates/updates documentation via the `docs-manager` agent.
Do NOT write code; do NOT create markdown outside `docs/` or `plans/`
(hard constraint of this repo — CLAUDE.md rule #5).

**Documentation rule** (when to update, which doc) is in
`harness/rules/` → read `documentation-management.md` before executing any
mode. Read it first — not repeated here.

## Modes

| Mode | When | Procedure |
|---|---|---|
| `init` | first time, no docs yet | scout → docs-manager creates new |
| `update` | after significant code/arch changes | scout → read existing docs → docs-manager updates |
| `summarize` | need a quick codebase-summary | focused scout → update `docs/codebase-summary.md` |

No argument → `AskUserQuestion` asking user to choose a mode.

## When docs MUST be updated

Update only when a change affects:
- user-visible behavior
- setup, install, or CLI commands
- architecture, data flow, or public contract
- security posture or operational procedures
- future decisions that a maintainer should not have to rediscover

Do not add noise for purely internal changes (rule `harness/rules/documentation-management.md` — hard constraint).

## General procedure

1. **Parse argument** — determine mode; if missing → ask.
2. **Scout** — use `hs:scout` to explore the codebase (skip `.git`, `__pycache__`,
   `harness/state/`, `node_modules`); merge reports.
3. **Read existing docs** (`update`/`summarize` mode) — always read before modifying.
4. **Delegate docs-manager** — spawn `docs-manager` agent with merged context;
   the agent acts as a Technical Writer — verify actual code before writing.
5. **Check size** — after docs-manager finishes: `wc -l docs/*.md | sort -rn`;
   file exceeds 800 LOC → warn + ask user whether to split or keep.
6. **Verify** — after update: check that dates, links, and claims match actual changes.

Per-mode details in `references/`.

## HARD-GATE (real wiring)

No dedicated hard gate for docs — but:
- `harness/hooks/gate_stage.py` still runs if a docs workflow triggers a stage
  (cannot be bypassed).
- All documentation files must be under `docs/` or `plans/` — creating elsewhere
  violates CLAUDE.md rule #5 and is caught by the CI invariant.

## Output language

Generated output (reports, docs, human-facing summaries) follows `harness/data/output.yaml`. Read its `language:` value (default `vi`) and write the prose in that language. Before finalizing, apply `harness/rules/humanizer-and-anti-ai-tells.md`: strip AI-writing tells, and when `language: vi`, also strip the Vietnamese translation-tells. Evidence is never translated or rewritten: keep `file:line` references, IDs, SHAs, numbers, and verbatim quotes exactly as found.

## Boundaries

- Do NOT write code or modify harness files outside `docs/` and `plans/`.
- Do NOT create markdown elsewhere (root except pre-approved README/CLAUDE/BACKLOG,
  `harness/` except `harness/rules/` via its own process).
- Docs mirror the real codebase — `docs-manager` verifies each `functionName()`,
  file path, and env var before writing. Describing assumed behavior → stop.
- Read the existing doc BEFORE modifying it (rule `harness/rules/documentation-management.md`).
- On completion: report updated files (absolute paths) + size check result.
