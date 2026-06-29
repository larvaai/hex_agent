---
name: hs-flow:afk
description: Run a plan/PRD in unattended (AFK) mode — preflight readiness, then route to Ralph sandbox or native fallback; loop commits freely in the middle, human reviews at both ends.
category: flow
license: AGPL-3.0
keywords: [afk, run, plan, prd, unattended, mode]
when_to_use: "Run a plan/PRD in unattended (AFK) mode — preflight readiness, then route to Ralph sandbox or native fallback; loop commits freely in the middle, human reviews at both ends."
argument-hint: "\"<plan> <prd>\" [N]"
user-invocable: true
allowed-tools: [Bash, Read, Glob, Grep, Task, SlashCommand]
metadata:
  owner: harness
  compliance-tier: workflow
---

# hs-flow:afk — guarded unattended execution

Input: `/hs-flow:afk "<plan> <prd>" [N]` — plan must already have HUMAN approval (same as hs:cook).
`N` = number of loop iterations (keep small; diff review is clearer with smaller N).

**Safety model** (read `docs/afk-mode.md` first — not repeated here): **review at both ends, free in the middle**. Human reviews the plan (entry) + reviews diff and ships (exit). The MIDDLE section = autonomous loop that ONLY commits, NO push/pr/ship. In-loop hook gates are a safety wire, NOT a guarantee — the real guarantee is the reviewer-stage + human-reviews-diff-before-ship.
**R3 (self-cert):** "having a gate does not mean safe" — the agent can write a verification PASS for incorrect code; therefore the human-diff-review step is REQUIRED, never skipped.

## Workflow

1. **Preflight (fail-open)**:
   `python3 harness/afk/preflight.py --json --plan <plan> --prd <prd>`.
   Read findings (`status: ok|warn|fail`). Preflight NEVER blocks the workflow —
   it is advisory; exit is always 0.
2. **Route by findings**:
   - **GREEN** (no `fail`): run the Ralph branch —
     `bash harness/afk/afk-run.sh "<plan> <prd>" N`. Still surface any `warn`
     items (arch/version) for the user to see; do not block.
   - **RED** (>=1 `fail`): do NOT run Ralph. Print findings with `fix` + `fallback_hint`,
     then ask **AskUserQuestion 3-option** (plain non-technical language, everyday analogy, recommended option first):
     1. *Fix the issue and run Ralph* — Recommended when the fix is light (e.g. start Docker, grant docker group permission, build image).
     2. *Run in normal mode on this machine (fallback)* — with the warning banner below.
     3. *Cancel*.
3. **Native fallback** (if option 2 chosen): soft-call `/loop "<task seed from input>"`
   (task-only, host) or `/goal` (task + objective interview). Seed the task from the input;
   if a prior Ralph-fail marker exists, surface it again. If `/loop`/`/goal` are absent
   (external skills — names/API may change) → provide manual run instructions, do NOT block (fail-open).
   > **WARNING BANNER** (print before releasing fallback): running ON THE HOST machine — Docker
   > isolation is LOST, loop is SIMPLIFIED (no sandbox, no Ralph reviewer-stage).
   > Harness hook gates still run if installed, but container walls no longer apply.

## Boundaries

- NO self-ship: every branch only commits; `push|pr|ship|deploy` go through the gate +
  human reviewer. Human reviews the entire diff BEFORE any merge/push.
- Do NOT modify `stage-policy.yaml`/`harness-hooks.yaml` to bypass the gate (tracked,
  tamper-visible). Genuinely stuck → ask the human.
- ONLY `ralph-afk` (plan-driven); NOT `ralph-ghafk`.
- Docker socket is off by default; enabling it = informed opt-out via the launcher's `--i-know`
  flag (prints blast radius). Do not enable it autonomously.
- Ralph/Plannotator versions are NOT pinned — `version_aware` only warns; if things break,
  they are "prime suspect"; break-glass pin in place (`RALPH_IMAGE=...@sha256:...`).
- Work that arises outside the plan → `BACKLOG.md`; do not steer the plan mid-run.
